"""Direct legal-analysis chain with deterministic source verification.

Normal chat no longer initializes or calls Chroma, BM25, or a reranker. The LLM
returns analysis plus candidate legal references. Exact statutory wording is
then populated only from :mod:`legal_sources.registry`.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Optional

import httpx

from langchain_core.messages import HumanMessage, SystemMessage

from config import settings
from key_manager import (
    QuickModelUnavailableError,
    clear_quick_temporarily_unavailable,
    get_active_provider_pools,
    get_current_provider_key_record,
    get_active_key_count,
    get_current_key_record,
    is_quota_error,
    is_quick_temporarily_unavailable,
    mark_quick_temporarily_unavailable,
    record_provider_attempt,
    record_provider_key_attempt,
    rotate_provider_key,
    rotate_key,
)
from legal_sources.registry import LawSourceRegistry, get_registry
from llm.prompts import DIRECT_ANALYSIS_PROMPT, SYSTEM_PROMPT
from models.schemas import AnalysisResponse, SourceChunk, StructuredAnalysis
from utils.logger import get_logger

logger = get_logger(__name__)

_llms = {}
_REPEATED_WORDS = re.compile(r"\b(\w+)(?:\s+\1){2,}\b", re.IGNORECASE)

_PROVIDER_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}


def _model_family(model: str) -> str:
    value = (model or "").lower()
    if "gpt-oss" in value or "gpt_oss" in value:
        return "gpt-oss"
    if "llama" in value:
        return "llama"
    return "other"


def _quick_routes():
    """Return active Quick Thinking records in model-family priority order."""

    provider_order = {"groq": 0, "cerebras": 1, "nvidia": 2, "google": 3}
    routes = []
    for (provider, model, mode), records in get_active_provider_pools().items():
        if mode != "quick":
            continue
        for record in records:
            family = _model_family(model)
            if family == "gpt-oss":
                route_priority = 0
            elif provider == "nvidia":
                route_priority = 1
            elif family == "llama":
                route_priority = 2
            else:
                route_priority = 3
            routes.append((
                route_priority,
                provider_order.get(provider, 9),
                record.rotation_order,
                record,
            ))
    return [item[3] for item in sorted(routes, key=lambda item: item[:3])]


def _provider_url(record) -> str:
    return (getattr(record, "base_url", None) or _PROVIDER_BASE_URLS.get(record.provider, "")).rstrip("/")


def _message_text(message) -> str:
    content = message.content
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
    return str(content)


async def _invoke_openai_compatible(record, messages, timeout: float | None) -> StructuredAnalysis:
    base_url = _provider_url(record)
    if not base_url:
        raise RuntimeError(f"No compatible base URL configured for provider {record.provider}.")
    payload = {
        "model": record.model,
        "messages": [{"role": "system" if isinstance(message, SystemMessage) else "user", "content": _message_text(message)} for message in messages],
        "temperature": settings.llm_temperature,
        "max_tokens": 1024,
    }
    headers = {"Authorization": f"Bearer {record.secret}", "Content-Type": "application/json"}
    request_timeout = timeout or 20.0
    async with httpx.AsyncClient(timeout=request_timeout) as client:
        response = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"{record.provider} HTTP {response.status_code}: {response.text[:300]}")
    body = response.json()
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
    content = str(content).strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        return StructuredAnalysis.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise RuntimeError(f"{record.provider} returned invalid structured analysis JSON.") from exc


async def _run_quick_provider_pipeline(messages, deadline: float | None):
    routes = _quick_routes()
    if not routes:
        raise QuickModelUnavailableError("Quick Thinking is temporarily unavailable because no Quick Thinking providers are configured.")
    attempted = set()
    for record in routes:
        if record.id in attempted:
            continue
        attempted.add(record.id)
        remaining = max(0.1, (deadline - time.monotonic()) if deadline else 8.0)
        try:
            if record.provider == "google":
                llm, _, key_id = _get_llm("quick", force_reinit=True, key_record=record)
                structured = llm.with_structured_output(StructuredAnalysis)
                response = await asyncio.wait_for(structured.ainvoke(messages), timeout=remaining)
                analysis = response if isinstance(response, StructuredAnalysis) else StructuredAnalysis.model_validate(response)
            else:
                key_id = record.id
                analysis = await _invoke_openai_compatible(record, messages, remaining)
            record_provider_key_attempt(record.id, record.provider, record.model, record.mode, "success")
            clear_quick_temporarily_unavailable()
            return _sanitize_analysis(analysis), f"quick:{record.provider}:{record.model}"
        except Exception as exc:
            quota_error = is_quota_error(exc) or isinstance(exc, asyncio.TimeoutError)
            record_provider_key_attempt(record.id, record.provider, record.model, record.mode, "quota" if quota_error else "failure", exc)
            logger.warning("Quick provider route failed: provider=%s model=%s error=%s", record.provider, record.model, exc)
            error_text = str(exc).lower()
            retryable = quota_error or any(marker in error_text for marker in (
                "http 408", "http 500", "http 502", "http 503", "connection", "temporarily",
            ))
            if not retryable:
                raise RuntimeError(f"Quick Thinking provider configuration failed: {exc}") from exc
            continue
    mark_quick_temporarily_unavailable()
    raise QuickModelUnavailableError("Quick Thinking is temporarily unavailable because all configured Quick Thinking providers are rate-limited or unavailable.")


def _clean_model_text(value: str, max_length: int = 1200) -> str:
    """Remove obvious provider repetition before content reaches the user."""

    cleaned = re.sub(r"\s+", " ", value or "").strip()
    cleaned = _REPEATED_WORDS.sub(r"\1", cleaned)
    return cleaned[:max_length].rstrip()


def _sanitize_analysis(analysis: StructuredAnalysis) -> StructuredAnalysis:
    """Bound structured fields so malformed long generations remain readable."""

    for field_name in (
        "conversational_reply",
        "general_analysis",
        "situation_meaning",
        "bail_status",
        "handling_authority",
    ):
        value = getattr(analysis, field_name)
        if isinstance(value, str):
            setattr(analysis, field_name, _clean_model_text(value))

    for field_name in ("next_24_hours", "rights"):
        cleaned_values = []
        for value in getattr(analysis, field_name)[:5]:
            cleaned = _clean_model_text(value, max_length=400)
            if cleaned and cleaned not in cleaned_values:
                cleaned_values.append(cleaned)
        setattr(analysis, field_name, cleaned_values)

    return analysis


def _get_llm(model_preference: str = "deep", force_reinit: bool = False, key_record=None):
    """Lazily initialize the selected Google model for the active API key."""

    global _llms
    key_record = key_record or get_current_key_record()
    if key_record is None:
        raise RuntimeError("No active Gemini API keys are configured.")
    target_model = getattr(key_record, "model", None) or (
        "gemini-2.5-flash" if model_preference == "quick" else settings.llm_model
    )

    cache_key = (target_model, key_record.id)
    if cache_key in _llms and not force_reinit:
        return _llms[cache_key], target_model, key_record.id

    from langchain_google_genai import ChatGoogleGenerativeAI

    _llms[cache_key] = ChatGoogleGenerativeAI(
        model=target_model,
        temperature=settings.llm_temperature,
        google_api_key=key_record.secret,
        # The response is a compact structured analysis. A large output budget
        # makes Gemma spend much longer producing JSON and increases the risk of
        # repetitive generations without improving the user-facing answer.
        max_output_tokens=3072 if model_preference == "deep" else 1024,
    )
    logger.info(
        "LLM initialized: provider=google_genai, model=%s, temp=%.2f",
        target_model,
        settings.llm_temperature,
    )
    return _llms[cache_key], target_model, key_record.id


def _verify_law_candidates(
    analysis: StructuredAnalysis,
    registry: LawSourceRegistry,
) -> list[SourceChunk]:
    """Hydrate model candidates from the registry and discard model quotations."""

    source_chunks: list[SourceChunk] = []
    verified_laws = []
    for law in analysis.applicable_laws:
        # Never trust quote/exact_text supplied by the provider, even if a model
        # ignores the prompt and returns a plausible-looking quotation.
        law.quote = ""
        law.exact_text = None
        law.source_url = None
        law.source_version = None
        law.source_hash = None
        law.quote_status = "unverified"
        law.verified = False

        record = registry.lookup(
            law.act,
            law.section,
            code=law.code,
            subsection=law.subsection,
        )
        if record is None:
            logger.info(
                "Legal citation left unverified: act=%r code=%r section=%r",
                law.act,
                law.code,
                law.section,
            )
            continue

        law.act = record.act
        law.code = record.code
        law.section = record.section
        law.subsection = record.subsection
        law.exact_text = record.exact_text
        law.quote = record.exact_text
        law.source_url = record.source_url
        law.source_version = record.source_version
        law.source_hash = record.source_hash
        law.quote_status = "backend_verified"
        law.verified = True
        verified_laws.append(law)

        source_chunks.append(
            SourceChunk(
                content=record.exact_text,
                document_name=record.act,
                act=record.act,
                code=record.code,
                section=record.section,
                subsection=record.subsection,
                exact_text=record.exact_text,
                quote=record.exact_text,
                verified=True,
                relevance_score=0.0,
                source_url=record.source_url,
                source_version=record.source_version,
                source_hash=record.source_hash,
                quote_status="backend_verified",
            )
        )

    # Keep the user-facing answer focused and never expose citations that the
    # authoritative registry could not resolve.
    analysis.applicable_laws = verified_laws[:3]
    return source_chunks[:3]


async def run_analysis_pipeline(
    query: str,
    document_filter: Optional[str] = None,
    top_k: Optional[int] = None,
    model_preference: Optional[str] = "deep",
    user_id: Optional[str] = None,
    ephemeral_context: Optional[str] = None,
    source_registry: LawSourceRegistry | None = None,
) -> AnalysisResponse:
    """Run direct model analysis and deterministic legal-source verification.

    ``document_filter``, ``top_k``, and ``user_id`` remain accepted for API
    compatibility with older callers, but normal chat does not use local RAG.
    ``ephemeral_context`` is still passed to the model as user-provided context.
    """

    del document_filter, top_k, user_id

    if model_preference == "quick" and is_quick_temporarily_unavailable() and not _quick_routes():
        raise QuickModelUnavailableError(
            "Quick Thinking is temporarily unavailable because all configured Quick Thinking providers are rate-limited or unavailable."
        )

    start_time = time.time()
    prompt = DIRECT_ANALYSIS_PROMPT.format(
        question=query,
        ephemeral_context=ephemeral_context or "(No uploaded document was provided.)",
    )
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    if model_preference == "deep":
        messages.append(
            SystemMessage(
                content=(
                    "The user selected Deep Thinking. Be comprehensive where it helps, "
                    "but do not invent legal text or citations."
                )
            )
        )
    messages.append(HumanMessage(content=prompt))

    if model_preference == "quick":
        structured_analysis, actual_model_used = await _run_quick_provider_pipeline(
            messages,
            time.monotonic() + min(settings.analysis_deadline_seconds, 20.0),
        )
        registry = source_registry if source_registry is not None else get_registry()
        source_chunks = _verify_law_candidates(structured_analysis, registry)
        elapsed = round(time.time() - start_time, 2)
        return AnalysisResponse(
            query=query,
            analysis=structured_analysis,
            sources=source_chunks,
            model_used=actual_model_used,
            processing_time_seconds=elapsed,
        )

    active_model_preference = model_preference
    deep_fallback_used = False
    deadline = (
        time.monotonic() + settings.analysis_deadline_seconds
        if model_preference == "deep"
        else None
    )
    llm, actual_model_used, key_id = _get_llm(active_model_preference)
    quick_key_attempts = 0
    while True:
        try:
            structured_llm = llm.with_structured_output(StructuredAnalysis)
            timeout = None
            if deadline is not None:
                remaining = max(0.1, deadline - time.monotonic())
                timeout = min(settings.deep_timeout_seconds, remaining) if active_model_preference == "deep" else remaining
            invoke = structured_llm.ainvoke(messages)
            response = await asyncio.wait_for(invoke, timeout=timeout) if timeout else await invoke
            structured_analysis = (
                response
                if isinstance(response, StructuredAnalysis)
                else StructuredAnalysis.model_validate(response)
            )
            structured_analysis = _sanitize_analysis(structured_analysis)
            record_provider_attempt(key_id, actual_model_used, "success")
            if active_model_preference == "quick":
                clear_quick_temporarily_unavailable()
            break
        except asyncio.TimeoutError as exc:
            record_provider_attempt(key_id, actual_model_used, "failure", exc)
            if model_preference == "deep" and active_model_preference == "deep" and not deep_fallback_used:
                logger.warning(
                    "Deep Thinking exceeded %.1fs; falling back to Gemini Flash before the %.1fs deadline.",
                    settings.deep_timeout_seconds,
                    settings.analysis_deadline_seconds,
                )
                if is_quick_temporarily_unavailable():
                    raise RuntimeError(
                        "Deep Thinking exceeded its response deadline and Quick Thinking is temporarily unavailable."
                    ) from exc
                active_model_preference = "quick"
                deep_fallback_used = True
                llm, actual_model_used, key_id = _get_llm("quick", force_reinit=True)
                continue
            logger.error("LLM generation exceeded the response deadline.")
            raise RuntimeError(
                "The analysis exceeded the 20-second response deadline. Please try again."
            ) from exc
        except Exception as exc:
            quota_error = is_quota_error(exc)
            record_provider_attempt(
                key_id,
                actual_model_used,
                "quota" if quota_error else "failure",
                exc,
            )
            if quota_error:
                logger.warning("Rate limit hit during LLM generation. Attempting key rotation...")
                if active_model_preference == "quick":
                    quick_key_attempts += 1
                    if quick_key_attempts >= max(1, get_active_key_count()):
                        mark_quick_temporarily_unavailable()
                        raise QuickModelUnavailableError(
                            "Quick Thinking is temporarily unavailable because Gemini Flash "
                            "has reached the limit on all configured API keys."
                        ) from exc
                if rotate_key():
                    llm, actual_model_used, key_id = _get_llm(
                        active_model_preference,
                        force_reinit=True,
                    )
                    continue
            logger.error("LLM generation failed: %s", exc)
            raise RuntimeError(f"LLM generation failed: {exc}") from exc

    registry = source_registry if source_registry is not None else get_registry()
    source_chunks = _verify_law_candidates(structured_analysis, registry)
    elapsed = round(time.time() - start_time, 2)
    logger.info(
        "Direct analysis complete — %d verified sources, %.2fs elapsed.",
        len(source_chunks),
        elapsed,
    )

    return AnalysisResponse(
        query=query,
        analysis=structured_analysis,
        sources=source_chunks,
        model_used=actual_model_used,
        processing_time_seconds=elapsed,
    )

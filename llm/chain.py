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

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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
from pydantic import BaseModel, Field
from utils.logger import get_logger

logger = get_logger(__name__)

_llms = {}
_REPEATED_WORDS = re.compile(r"\b(\w+)(?:\s+\1){2,}\b", re.IGNORECASE)
_EXPLICIT_LAW_SECTION = re.compile(
    r"(?<!\w)(?:(BNS|BNSS|BSA)\s*(?:section\s*)?(\d+[A-Za-z]?(?:\(\d+\))?)|"
    r"(?:section\s*)?(\d+[A-Za-z]?(?:\(\d+\))?)\s+(?:of\s+)?(BNS|BNSS|BSA))(?!\w)",
    re.IGNORECASE,
)
_DIRECT_SECTION_INTENT = re.compile(
    r"\b(?:explain|describe|meaning\s+of|what\s+is|tell\s+me\s+about)\b",
    re.IGNORECASE,
)
_SECTION_SOURCE_SYSTEM_PROMPT = """\
You explain one specific Indian statutory provision using the verified source
record supplied in the user's message. Treat the record as the sole authority
for the requested provision. The Act code and section number identify one exact
provision; never replace it with a similarly numbered section from another Act.
Do not use memory or other Acts to fill gaps in this provision. Explain the
provided text in plain language, and do not claim anything that the text does
not support. Return a valid JSON object matching the analysis schema. Put the
explanation in general_analysis and return the exact requested code and section
as the only applicable_laws item. Leave quote and exact_text empty; the backend
will attach the verified source text.
"""
_SECTION_VERIFIER_PROMPT = """\
You are an independent statutory-source auditor. Decide whether every factual
claim in the proposed explanation is supported by the supplied exact text for
the exact requested Act and section. The statute text is the only authority.
Reject claims that are absent, contradict the text, or describe another Act's
same-numbered section. Return only JSON: {\"supported\": true} or
{\"supported\": false}. Do not use outside knowledge.
"""


class _SectionVerification(BaseModel):
    supported: bool = Field(...)

_PROVIDER_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
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

    provider_order = {"groq": 0, "cerebras": 1, "google": 2}
    routes = []
    for (provider, model, mode), records in get_active_provider_pools().items():
        if mode != "quick" or provider not in provider_order:
            continue
        for record in records:
            family = _model_family(model)
            if family == "gpt-oss":
                route_priority = 0
            elif family == "llama":
                route_priority = 1
            else:
                route_priority = 2
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


def _normalize_analysis_payload(payload: object) -> dict:
    """Make common provider JSON conventions safe for our Pydantic schema."""

    if not isinstance(payload, dict):
        raise ValueError("provider response JSON was not an object")
    normalized = dict(payload)

    def as_text(value, default=""):
        if value is None:
            return default
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def as_bool(value, default=False):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1"}:
                return True
            if lowered in {"false", "no", "0", ""}:
                return False
        return bool(value)

    def as_text_list(value):
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        return [as_text(item) for item in value if item is not None]

    for field_name in (
        "general_analysis",
        "situation_meaning",
        "bail_status",
        "handling_authority",
    ):
        normalized[field_name] = as_text(normalized.get(field_name))
    for field_name in ("is_conversational", "requires_sources", "suggest_lawyer"):
        normalized[field_name] = as_bool(normalized.get(field_name), False)
    normalized["conversational_reply"] = (
        None if normalized.get("conversational_reply") is None
        else as_text(normalized.get("conversational_reply"))
    )
    normalized["next_24_hours"] = as_text_list(normalized.get("next_24_hours"))
    normalized["rights"] = as_text_list(normalized.get("rights"))
    source_indices = normalized.get("relevant_source_indices") or []
    if not isinstance(source_indices, list):
        source_indices = [source_indices]
    normalized["relevant_source_indices"] = [
        int(value) for value in source_indices
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().lstrip("-").isdigit())
    ]

    laws = normalized.get("applicable_laws", [])
    if isinstance(laws, dict):
        laws = [laws]
    normalized_laws = []
    for law in laws if isinstance(laws, list) else []:
        if not isinstance(law, dict):
            continue
        normalized_law = dict(law)
        for field_name in (
            "act",
            "code",
            "section",
            "quote",
            "explanation",
            "quote_status",
        ):
            normalized_law[field_name] = as_text(normalized_law.get(field_name))
        for field_name in ("subsection", "exact_text", "source_url", "source_version", "source_hash"):
            if normalized_law.get(field_name) is not None:
                normalized_law[field_name] = as_text(normalized_law[field_name])
        normalized_law["verified"] = as_bool(normalized_law.get("verified"), False)
        normalized_laws.append(normalized_law)
    normalized["applicable_laws"] = normalized_laws
    return normalized


def _parse_structured_analysis_content(content) -> StructuredAnalysis:
    """Parse provider JSON while tolerating harmless prose/fence wrappers."""

    if isinstance(content, list):
        content = "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in content
        )
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()

    decoder = json.JSONDecoder()
    start = text.find("{")
    if start < 0:
        raise ValueError("provider response did not contain a JSON object")
    payload, _ = decoder.raw_decode(text[start:])
    return StructuredAnalysis.model_validate(_normalize_analysis_payload(payload))


async def _invoke_openai_compatible(record, messages, timeout: float | None) -> StructuredAnalysis:
    base_url = _provider_url(record)
    if not base_url:
        raise RuntimeError(f"No compatible base URL configured for provider {record.provider}.")
    payload = {
        "model": record.model,
        "messages": [
            {
                "role": (
                    "system"
                    if isinstance(message, SystemMessage)
                    else "assistant"
                    if isinstance(message, AIMessage)
                    else "user"
                ),
                "content": _message_text(message),
            }
            for message in messages
        ],
        "temperature": settings.llm_temperature,
        "max_tokens": 1024,
    }
    if record.provider == "groq":
        # GPT-OSS exposes reasoning separately. JSON Object Mode keeps the
        # assistant content parseable across Groq responses, while disabling
        # the reasoning field prevents it from being mixed into the answer.
        payload["response_format"] = {"type": "json_object"}
        payload["include_reasoning"] = False
        if _model_family(record.model) == "gpt-oss":
            payload["reasoning_effort"] = "low"
    headers = {"Authorization": f"Bearer {record.secret}", "Content-Type": "application/json"}
    request_timeout = timeout or 20.0
    async with httpx.AsyncClient(timeout=request_timeout) as client:
        response = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"{record.provider} HTTP {response.status_code}: {response.text[:300]}")
    body = response.json()
    try:
        content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        return _parse_structured_analysis_content(content)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        if hasattr(exc, "errors"):
            details = "; ".join(
                f"{'.'.join(str(part) for part in error.get('loc', ())) or 'root'}:{error.get('type', 'validation')}"
                for error in exc.errors()
            )
            logger.warning("%s structured response validation fields: %s", record.provider, details[:500])
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


async def _independent_section_verification(record, explanation: str, generation_model: str) -> bool:
    """Verify an answer with a separately configured provider; fail closed."""
    try:
        generation_provider = generation_model.split(":", 2)[1]
        verifier = next((route for route in _quick_routes()
                         if route.provider != generation_provider), None)
        if verifier is None:
            logger.warning("No independent provider available for direct section verification")
            return False
        user_content = (
            f"REQUESTED ACT: {record.act} ({record.code})\n"
            f"REQUESTED SECTION: {record.section}\n"
            f"EXACT STATUTORY TEXT:\n{record.exact_text}\n\n"
            f"PROPOSED EXPLANATION:\n{explanation}"
        )
        messages = [SystemMessage(content=_SECTION_VERIFIER_PROMPT), HumanMessage(content=user_content)]
        if verifier.provider == "google":
            llm, _, _ = _get_llm("quick", force_reinit=True, key_record=verifier)
            structured = llm.with_structured_output(_SectionVerification)
            result = await asyncio.wait_for(structured.ainvoke(messages), timeout=8.0)
            if isinstance(result, _SectionVerification):
                return result.supported
            if isinstance(result, dict) and type(result.get("supported")) is bool:
                return result["supported"]
            return False

        base_url = _provider_url(verifier)
        payload = {
            "model": verifier.model,
            "messages": [
                {"role": "system", "content": _SECTION_VERIFIER_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
            "max_tokens": 40,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {verifier.secret}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        if response.status_code >= 400:
            return False
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content")
        decoded = json.loads(content) if isinstance(content, str) else None
        return isinstance(decoded, dict) and type(decoded.get("supported")) is bool and decoded["supported"]
    except Exception as exc:
        logger.warning("Direct section verification failed closed: %s", exc)
        return False


def _direct_section_claims(analysis: StructuredAnalysis) -> str:
    """Collect all generated user-facing claims for the source auditor."""
    fields = (
        ("general_analysis", analysis.general_analysis),
        ("situation_meaning", analysis.situation_meaning),
        ("bail_status", analysis.bail_status),
        ("handling_authority", analysis.handling_authority),
    )
    parts = [f"{label}: {value}" for label, value in fields if value]
    for label in ("next_24_hours", "rights"):
        values = getattr(analysis, label)
        if values:
            parts.append(f"{label}: " + "; ".join(values))
    for law in analysis.applicable_laws:
        if law.explanation:
            parts.append(f"citation explanation: {law.explanation}")
    return "\n".join(parts)


def _use_verified_text_fallback(analysis: StructuredAnalysis, record) -> None:
    analysis.general_analysis = (
        "I couldn't verify an explanation against the requested provision. "
        "Here is the verified statutory text:\n\n" + record.exact_text
    )
    analysis.situation_meaning = ""
    analysis.bail_status = ""
    analysis.next_24_hours = []
    analysis.rights = []
    analysis.handling_authority = ""


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
    model_preference: Optional[str] = "quick",
    user_id: Optional[str] = None,
    ephemeral_context: Optional[str] = None,
    conversation_history: Optional[list[dict[str, str]]] = None,
    source_registry: LawSourceRegistry | None = None,
) -> AnalysisResponse:
    """Run direct model analysis and deterministic legal-source verification.

    ``document_filter``, ``top_k``, and ``user_id`` remain accepted for API
    compatibility with older callers, but normal chat does not use local RAG.
    ``ephemeral_context`` is still passed to the model as user-provided context.
    ``conversation_history`` contains bounded, already-compacted prior turns.
    """

    del document_filter, top_k, user_id, model_preference
    model_preference = "quick"

    start_time = time.time()
    registry = source_registry if source_registry is not None else get_registry()
    requested_law = _requested_law_record(query, registry)
    if model_preference == "quick" and is_quick_temporarily_unavailable() and not _quick_routes():
        raise QuickModelUnavailableError(
            "Quick Thinking is temporarily unavailable because all configured Quick Thinking providers are rate-limited or unavailable."
        )

    messages = _build_prompt_messages(
        query,
        ephemeral_context,
        conversation_history,
        requested_law=requested_law,
    )

    if model_preference == "quick":
        structured_analysis, actual_model_used = await _run_quick_provider_pipeline(
            messages,
            time.monotonic() + min(settings.analysis_deadline_seconds, 20.0),
        )
        if requested_law is not None and _DIRECT_SECTION_INTENT.search(query or ""):
            _enforce_direct_section_match(structured_analysis, requested_law, registry)
            if requested_law.code in {"BNS", "BNSS"} and not await _independent_section_verification(
                requested_law, _direct_section_claims(structured_analysis), actual_model_used
            ):
                _use_verified_text_fallback(structured_analysis, requested_law)
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

    if requested_law is not None and _DIRECT_SECTION_INTENT.search(query or ""):
        _enforce_direct_section_match(structured_analysis, requested_law, registry)
        if requested_law.code in {"BNS", "BNSS"} and not await _independent_section_verification(
            requested_law, _direct_section_claims(structured_analysis), actual_model_used
        ):
            _use_verified_text_fallback(structured_analysis, requested_law)
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


def _build_prompt_messages(
    query: str,
    ephemeral_context: Optional[str],
    conversation_history: Optional[list[dict[str, str]]],
    requested_law=None,
) -> list:
    """Build messages with prior turns before the newest user prompt."""

    if requested_law is not None and _DIRECT_SECTION_INTENT.search(query or ""):
        # A direct provision lookup is self-contained. Use a narrow system
        # instruction and omit chat history so a previous mistaken answer
        # cannot compete with the registry text for the model's attention.
        return [
            SystemMessage(content=_SECTION_SOURCE_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "Explain the provision requested below in plain language. "
                    "The verified record is the source of truth.\n\n"
                    f"USER QUERY:\n{query}\n\n"
                    f"VERIFIED ACT: {requested_law.act}\n"
                    f"VERIFIED CODE: {requested_law.code}\n"
                    f"VERIFIED SECTION: {requested_law.section}\n"
                    "VERIFIED STATUTORY TEXT:\n"
                    f"{requested_law.exact_text}"
                )
            ),
        ]

    prompt = DIRECT_ANALYSIS_PROMPT.format(
        question=query,
        ephemeral_context=ephemeral_context or "(No uploaded document was provided.)",
    )
    if requested_law is not None:
        prompt += (
            "\n\nEXACT REQUESTED STATUTE FROM THE VERIFIED SOURCE REGISTRY "
            "(this Act and section are the user's requested subject; do not "
            "substitute another code's same-numbered section):\n"
            f"Act/code: {requested_law.act} ({requested_law.code})\n"
            f"Section: {requested_law.section}\n"
            f"Text: {requested_law.exact_text}\n"
            "Explain only this provision. Do not describe another Act's "
            "section with the same number. Cite this exact Act and section."
        )
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    for item in conversation_history or []:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant":
            messages.append(AIMessage(content=content))
        elif role == "user":
            messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=prompt))
    return messages


def _requested_law_record(query: str, registry: LawSourceRegistry):
    """Resolve an explicitly named code and section before asking the model."""

    match = _EXPLICIT_LAW_SECTION.search(query or "")
    if not match:
        return None
    if match.group(1):
        code, section = match.group(1), match.group(2)
    else:
        section, code = match.group(3), match.group(4)
    return registry.lookup(code=code, section=section)


def _enforce_direct_section_match(
    analysis: StructuredAnalysis,
    record,
    registry: LawSourceRegistry,
) -> None:
    """Keep a mismatched generated section from being presented as verified."""

    from models.schemas import ApplicableLaw

    resolved_candidates = [
        registry.lookup(
            law.act,
            law.section,
            code=law.code,
            subsection=law.subsection,
        )
        for law in analysis.applicable_laws
    ]
    has_matching_citation = any(
        candidate is not None
        and (candidate.code, candidate.section) == (record.code, record.section)
        for candidate in resolved_candidates
    )
    has_conflicting_citation = not has_matching_citation or any(
        candidate is not None
        and (candidate.code, candidate.section) != (record.code, record.section)
        for candidate in resolved_candidates
    )

    if has_conflicting_citation:
        # Do not silently rewrite (and thereby "verify") a different model
        # answer as the section the user requested. Fail closed; the verified
        # statutory text is still attached as a source below.
        analysis.general_analysis = (
            "I couldn't reliably match the explanation to the section you "
            "asked about. Here is the verified statutory text:\n\n" + record.exact_text
        )
        analysis.situation_meaning = ""
        analysis.bail_status = ""
        analysis.next_24_hours = []
        analysis.rights = []
        analysis.handling_authority = ""

    matching_law = next(
        (
            law
            for law, candidate in zip(analysis.applicable_laws, resolved_candidates)
            if candidate is not None
            and (candidate.code, candidate.section) == (record.code, record.section)
        ),
        None,
    )
    analysis.applicable_laws = [
        matching_law
        or ApplicableLaw(act=record.act, code=record.code, section=record.section)
    ]
    analysis.requires_sources = True

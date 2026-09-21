"""Direct legal-analysis chain with deterministic source verification.

Normal chat no longer initializes or calls Chroma, BM25, or a reranker. The LLM
returns analysis plus candidate legal references. Exact statutory wording is
then populated only from :mod:`legal_sources.registry`.
"""

from __future__ import annotations

import time
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from config import settings
from key_manager import (
    QuickModelUnavailableError,
    clear_quick_temporarily_unavailable,
    get_active_key_count,
    get_current_key_record,
    is_quota_error,
    is_quick_temporarily_unavailable,
    mark_quick_temporarily_unavailable,
    record_provider_attempt,
    rotate_key,
)
from legal_sources.registry import LawSourceRegistry, get_registry
from llm.prompts import DIRECT_ANALYSIS_PROMPT, SYSTEM_PROMPT
from models.schemas import AnalysisResponse, SourceChunk, StructuredAnalysis
from utils.logger import get_logger

logger = get_logger(__name__)

_llms = {}


def _get_llm(model_preference: str = "deep", force_reinit: bool = False):
    """Lazily initialize the selected Google model for the active API key."""

    global _llms
    target_model = "gemini-2.5-flash" if model_preference == "quick" else settings.llm_model

    key_record = get_current_key_record()
    if key_record is None:
        raise RuntimeError("No active Gemini API keys are configured.")

    cache_key = (target_model, key_record.id)
    if cache_key in _llms and not force_reinit:
        return _llms[cache_key], target_model, key_record.id

    from langchain_google_genai import ChatGoogleGenerativeAI

    _llms[cache_key] = ChatGoogleGenerativeAI(
        model=target_model,
        temperature=settings.llm_temperature,
        google_api_key=key_record.secret,
        max_output_tokens=8192,
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

    return source_chunks


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

    if model_preference == "quick" and is_quick_temporarily_unavailable():
        raise QuickModelUnavailableError(
            "Quick Thinking is temporarily unavailable because Gemini Flash "
            "has reached the limit on all configured API keys."
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

    llm, actual_model_used, key_id = _get_llm(model_preference)
    quick_key_attempts = 0
    while True:
        try:
            structured_llm = llm.with_structured_output(StructuredAnalysis)
            response = await structured_llm.ainvoke(messages)
            structured_analysis = (
                response
                if isinstance(response, StructuredAnalysis)
                else StructuredAnalysis.model_validate(response)
            )
            record_provider_attempt(key_id, actual_model_used, "success")
            if model_preference == "quick":
                clear_quick_temporarily_unavailable()
            break
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
                if model_preference == "quick":
                    quick_key_attempts += 1
                    if quick_key_attempts >= max(1, get_active_key_count()):
                        mark_quick_temporarily_unavailable()
                        raise QuickModelUnavailableError(
                            "Quick Thinking is temporarily unavailable because Gemini Flash "
                            "has reached the limit on all configured API keys."
                        ) from exc
                if rotate_key():
                    llm, actual_model_used, key_id = _get_llm(
                        model_preference,
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

"""
LLM Chain for the Legal RAG Advisor.

Orchestrates the full retrieval-augmented generation pipeline:
  1. Hybrid retrieval (dense + BM25).
  2. Cross-encoder reranking (local).
  3. Context formatting with source attribution.
  4. LLM generation with Gemini API (Google AI Studio).

"""

from __future__ import annotations

import re
import time
from typing import Optional

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from config import settings
from llm.prompts import (
    build_retrieval_query,
    classify_query,
    extract_case_name,
    extract_case_lookup_terms,
    get_prompt,
    SYSTEM_PROMPT,
    format_context_from_chunks,
)
from models.schemas import AnalysisResponse, SourceChunk, StructuredAnalysis
from retrieval.hybrid_retriever import hybrid_retrieve, _is_junk_form
from retrieval.bm25_retriever import ensure_bm25_ready
from retrieval.reranker import filter_chunks_by_case, rerank
from utils.logger import get_logger
from key_manager import get_current_key, rotate_key

logger = get_logger(__name__)

def _clean_text(text: str | None) -> str:
    """Trim excessive form lines like '.....', '_____', or '-----'."""
    if not text:
        return ""
    # Replace 4 or more repeating form characters with a clean ellipsis
    return re.sub(r'[\.\-_]{4,}', '...', text).strip()

# ─── LLM cache ─────────────────────────────────────────────────────────────
_llms = {}

def _get_llm(model_preference: str = "deep", force_reinit: bool = False):
    """
    Lazily initialize and cache the LLM instances.

    Uses Google GenAI via the Gemini API.
    """
    global _llms
    
    if model_preference == "quick":
        target_model = "gemini-2.5-flash"
    else:
        target_model = settings.llm_model # defaults to gemma-4-31b-it

    if target_model in _llms and not force_reinit:
        return _llms[target_model], target_model

    from langchain_google_genai import ChatGoogleGenerativeAI

    current_key = get_current_key()
    _llms[target_model] = ChatGoogleGenerativeAI(
        model=target_model,
        temperature=settings.llm_temperature,
        google_api_key=current_key,
        max_output_tokens=8192,
    )
    logger.info(
        "LLM initialized: provider=google_genai, model=%s, temp=%.2f",
        target_model,
        settings.llm_temperature,
    )

    return _llms[target_model], target_model


async def run_analysis_pipeline(
    query: str,
    document_filter: Optional[str] = None,
    top_k: Optional[int] = None,
    model_preference: Optional[str] = "deep",
    user_id: Optional[str] = None,
    ephemeral_context: Optional[str] = None,
) -> AnalysisResponse:
    """
    Run the full RAG analysis pipeline for a legal query.

    Stages: hybrid retrieval → reranking → context assembly → LLM generation.
    """
    start_time = time.time()

    query_type = classify_query(query)
    retrieval_query = build_retrieval_query(query, query_type)
    prompt_template = get_prompt(query_type)

    # ── Stage 1: Hybrid Retrieval ───────────────────────────────────────
    logger.info(
        "Pipeline started — type=%s, query='%.80s…', retrieval='%.80s…'",
        query_type,
        query,
        retrieval_query,
    )

    if query_type == "CONVERSATIONAL":
        raw_results = []
    else:
        try:
            raw_results = hybrid_retrieve(
                query=retrieval_query,
                k=top_k or settings.retrieval_top_k,
                document_filter=document_filter,
                user_id=user_id,
            )
        except Exception as exc:
            logger.error("Hybrid retrieval failed: %s", exc)
            raise RuntimeError(f"Retrieval failed: {exc}") from exc

    if not raw_results and query_type != "CONVERSATIONAL":
        logger.warning("No documents retrieved for query.")
        return AnalysisResponse(
            query=query,
            analysis=StructuredAnalysis(
                is_conversational=False,
                summary="⚠️ **Information not found in the provided documents.**",
                detailed_analysis="No relevant document chunks were retrieved for your query. Please ensure the relevant documents have been uploaded and ingested, then try again."
            ),
            sources=[],
            model_used=settings.llm_model,
            processing_time_seconds=round(time.time() - start_time, 2),
        )

    # ── Stage 2: Reranking ──────────────────────────────────────────────
    try:
        rerank_candidates = raw_results
        case_name = None
        case_terms: list[str] | None = None
        if query_type == "CASE_LOOKUP":
            case_name = extract_case_name(query)
            case_terms = extract_case_lookup_terms(query)
            rerank_candidates = filter_chunks_by_case(raw_results, case_name, case_terms)

            if rerank_candidates:
                logger.info(
                    "Case lookup prefilter kept %d / %d candidates for '%s'.",
                    len(rerank_candidates),
                    len(raw_results),
                    case_name,
                )

        reranked = rerank(
            query=query,
            documents=rerank_candidates,
            top_n=settings.rerank_top_n,
            case_name=case_name,
            case_terms=case_terms,
        )
    except Exception as exc:
        logger.error("Reranking failed: %s", exc)
        # Graceful degradation: use the raw results without reranking.
        reranked = [(doc, 0.0) for doc in raw_results[: settings.rerank_top_n]]

    # ── Stage 3: Context Assembly ───────────────────────────────────────
    context_str = format_context_from_chunks(reranked)

    if ephemeral_context:
        context_str = f"--- UPLOADED EPHEMERAL DOCUMENT ---\n{ephemeral_context}\n\n--- RAG DATABASE RESULTS ---\n" + context_str

    # Build the prompt for the selected branch with context + question injected.
    full_prompt = prompt_template.format(
        context=context_str,
        question=query,
    )

    # ── Stage 4: LLM Generation ────────────────────────────────────────
    llm, actual_model_used = _get_llm(model_preference)

    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    if model_preference == "deep" and query_type != "CONVERSATIONAL":
        messages.append(SystemMessage(
            content="CRITICAL INSTRUCTION: The user has selected the Deep Thinking model. You MUST provide an exceptionally detailed, extensive, and comprehensive reply. Break down every aspect of the law, potential scenarios, and step-by-step guidance. Write a long, thorough analysis. Do not be brief."
        ))

    messages.append(HumanMessage(content=full_prompt))

    while True:
        try:
            structured_llm = llm.with_structured_output(StructuredAnalysis)
            response = await structured_llm.ainvoke(messages)
            structured_analysis = response
            break
        except Exception as exc:
            err_str = str(exc).lower()
            if "429" in err_str or "quota" in err_str or "exhausted" in err_str or "rate limit" in err_str:
                logger.warning("Rate limit hit during LLM generation. Attempting key rotation...")
                if rotate_key():
                    llm, actual_model_used = _get_llm(model_preference, force_reinit=True)
                    continue
            logger.error("LLM generation failed: %s", exc)
            raise RuntimeError(f"LLM generation failed: {exc}") from exc

    # ── Post-Processing: Fix "(not in context)" sections ────────────
    original_reranked_len = len(reranked)
    
    if structured_analysis.applicable_laws:
        valid_laws = []
        for law in structured_analysis.applicable_laws:
            # Check if LLM flagged it as not in context
            if law.quote and "(not in context)" in law.quote.lower():
                sec_query = f"{law.code} {law.section}"
                logger.info("Attempting post-generation BM25 rescue for section: %s", sec_query)
                try:
                    bm25_retriever = ensure_bm25_ready(k=3)
                    bm25_res = bm25_retriever.invoke(sec_query)
                    
                    found_doc = None
                    for doc in bm25_res:
                        # Skip if it is a junk form
                        if _is_junk_form(doc.page_content):
                            continue
                        # Ensure the chunk actually mentions the section number
                        if law.section.lower() in doc.page_content.lower():
                            found_doc = doc
                            break
                    
                    if found_doc:
                        reranked.append((found_doc, 1.0)) # Append to source chunks so user can read it
                        logger.info("Successfully rescued section %s via BM25 to sources", sec_query)
                except Exception as e:
                    logger.error("Post-processing BM25 search failed: %s", e)
                
                # Always keep the law, just clear the quote so it doesn't show up in the UI
                law.quote = ""
                valid_laws.append(law)
            else:
                if law.quote:
                    law.quote = _clean_text(law.quote)
                valid_laws.append(law)
        
        structured_analysis.applicable_laws = valid_laws

    # ── Stage 5: Response Packaging ─────────────────────────────────────
    reranked_to_use = []
    if structured_analysis.relevant_source_indices:
        for idx, (doc, score) in enumerate(reranked, start=1):
            if idx > original_reranked_len or idx in structured_analysis.relevant_source_indices:
                reranked_to_use.append((doc, score))
        if not reranked_to_use:
            reranked_to_use = reranked
    else:
        reranked_to_use = reranked

    source_chunks = [
        SourceChunk(
            content=_clean_text(doc.page_content),  # Pass full text for frontend to expand
            document_name=doc.metadata.get("document_name", "Unknown"),
            section=doc.metadata.get("section", "General"),
            relevance_score=round(score, 4),
            page_number=doc.metadata.get("page_number"),
        )
        for doc, score in reranked_to_use
    ]

    elapsed = round(time.time() - start_time, 2)

    logger.info(
        "Pipeline complete — %d sources, %.2fs elapsed.",
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

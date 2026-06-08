"""
Hybrid (Ensemble) Retriever for the Legal RAG Advisor.

Combines dense vector search (ChromaDB) with sparse keyword search (BM25)
using Reciprocal Rank Fusion (RRF).  This hybrid approach is the gold
standard for legal retrieval because:

- **Dense search** captures *semantic* similarity — it understands that
  "termination for cause" and "breach-based cancellation" are related.
- **BM25** captures *lexical* matches — it precisely finds "Force Majeure"
  or "Section 7.2(a)" even when the embedding model doesn't place them
  close together in vector space.

The weighting is configurable via ``settings.bm25_weight`` and
``settings.dense_weight`` and defaults to 60/40 favoring dense.
"""

import re
from langchain_core.documents import Document

from config import settings
from retrieval.bm25_retriever import ensure_bm25_ready
from retrieval.vector_store import get_retriever as get_dense_retriever
from utils.logger import get_logger

logger = get_logger(__name__)


def _is_junk_form(text: str) -> bool:
    """Check if the text is a boilerplate form or template."""
    upper_text = text.upper()
    if "FORM NO." in upper_text:
        return True
    if "..........." in text:
        return True
    if "WHEREAS" in upper_text and "...." in text:
        return True
    return False

def _reciprocal_rank_fusion(
    result_lists: list[list[Document]],
    weights: list[float],
    k: int = 60,
) -> list[Document]:
    """
    Merge multiple ranked result lists using weighted Reciprocal Rank Fusion.

    For each document, the RRF score is:
        score = sum(weight_i / (k + rank_i))

    Args:
        result_lists: List of document lists from each retriever.
        weights: Weight for each retriever's contribution.
        k: RRF constant (default 60, standard value from the RRF paper).

    Returns:
        Merged and re-ranked list of Documents.
    """
    doc_scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}

    for results, weight in zip(result_lists, weights):
        for rank, doc in enumerate(results):
            # Use first 500 chars as a dedup key
            doc_key = doc.page_content[:500]
            if doc_key not in doc_map:
                doc_map[doc_key] = doc
                doc_scores[doc_key] = 0.0
            doc_scores[doc_key] += weight / (k + rank + 1)

    # Sort by fused score descending
    sorted_keys = sorted(doc_scores, key=doc_scores.get, reverse=True)
    return [doc_map[key] for key in sorted_keys]


def hybrid_retrieve(
    query: str,
    k: int | None = None,
    document_filter: str | None = None,
    user_id: str | None = None,
) -> list[Document]:
    """
    Execute a hybrid retrieval and return merged results.

    This is the primary retrieval entry point used by the analysis pipeline.

    Args:
        query: The user's legal question.
        k: Number of results (before reranking).
        document_filter: Optional document name scope.

    Returns:
        Deduplicated, RRF-merged list of ``Document`` objects.
    """
    k = k or settings.retrieval_top_k

    # ── Dense retriever ─────────────────────────────────────────────────
    filter_dict = {}
    if document_filter:
        filter_dict["document_name"] = document_filter
    if user_id:
        filter_dict["$or"] = [{"user_id": user_id}, {"user_id": {"$exists": False}}]
    
    if not filter_dict:
        filter_dict = None

    dense_results: list[Document] = []
    try:
        dense_retriever = get_dense_retriever(k=k, filter_dict=filter_dict)
        dense_results = dense_retriever.invoke(query)
    except Exception as exc:
        logger.error(
            "Dense retrieval failed; falling back to BM25 only for this query: %s",
            exc,
        )

    # ── BM25 retriever ──────────────────────────────────────────────────
    bm25_results: list[Document] = []
    try:
        bm25_retriever = ensure_bm25_ready(k=k * 3) # Fetch more to account for filtering
        raw_bm25 = bm25_retriever.invoke(query)
        if user_id:
            bm25_results = [doc for doc in raw_bm25 if doc.metadata.get("user_id") in [user_id, None]][:k]
        else:
            bm25_results = raw_bm25[:k]
    except Exception as exc:
        logger.error("BM25 retrieval failed: %s", exc)

    if not dense_results and not bm25_results:
        raise RuntimeError("Both dense retrieval and BM25 retrieval failed.")

    # ── Filter out junk forms ───────────────────────────────────────────
    dense_results = [doc for doc in dense_results if not _is_junk_form(doc.page_content)]
    bm25_results = [doc for doc in bm25_results if not _is_junk_form(doc.page_content)]

    # ── Secondary Section Search ────────────────────────────────────────
    section_bm25_results: list[Document] = []
    section_matches = re.findall(r"[Ss]ection\s*\d+|BNS\s*\d+|BNSS\s*\d+", query)
    if section_matches:
        try:
            sec_query = " ".join(section_matches)
            logger.info("Running secondary BM25 search for extracted sections: %s", sec_query)
            bm25_retriever = ensure_bm25_ready(k=k * 3)
            raw_sec_bm25 = bm25_retriever.invoke(sec_query)
            if user_id:
                section_bm25_results = [doc for doc in raw_sec_bm25 if doc.metadata.get("user_id") in [user_id, None]][:k]
            else:
                section_bm25_results = raw_sec_bm25[:k]
            section_bm25_results = [doc for doc in section_bm25_results if not _is_junk_form(doc.page_content)]
        except Exception as exc:
            logger.error("Secondary BM25 search failed: %s", exc)

    # ── Fuse with RRF ───────────────────────────────────────────────────
    merged = _reciprocal_rank_fusion(
        result_lists=[dense_results, bm25_results, section_bm25_results],
        weights=[settings.dense_weight, settings.bm25_weight, settings.bm25_weight],
    )

    logger.info(
        "Hybrid retrieval returned %d results (dense=%d, bm25=%d, sec_bm25=%d) for: '%.60s…'",
        len(merged),
        len(dense_results),
        len(bm25_results),
        len(section_bm25_results),
        query,
    )
    return merged


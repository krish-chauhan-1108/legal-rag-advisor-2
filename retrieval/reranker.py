"""
Re-ranking module for the Legal RAG Advisor.

After the hybrid retriever surfaces ~20 candidate chunks, this module
narrows them to the top 5 most relevant using a *cross-encoder* reranker.

Primary backend: **Local cross-encoder** (``cross-encoder/ms-marco-MiniLM-L-6-v2``)
from HuggingFace sentence-transformers — runs entirely on your machine with
no API keys required.

Fallback: A simple TF-IDF cosine similarity reranker if the cross-encoder
model fails to load (useful for minimal environments).

Why reranking matters for legal RAG
-----------------------------------
- Initial retrieval casts a wide net (high recall, moderate precision).
- A cross-encoder reranker jointly encodes the *query + passage pair*,
  yielding far more accurate relevance judgments than bi-encoder similarity.
- For legal queries this difference is dramatic: "What are the seller's
  obligations upon a Material Adverse Change?" requires understanding the
  *relationship* between query and passage, not just keyword overlap.
"""

from __future__ import annotations

import re

from langchain_core.documents import Document

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


def filter_chunks_by_case(
    documents: list[Document],
    case_name: str | None,
    extra_terms: list[str] | None = None,
) -> list[Document]:
    """Prefer chunks that most strongly match the named case before reranking."""
    if not case_name:
        return documents

    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", case_name.lower())
        if token not in {"v", "vs", "versus", "the", "case"}
    ]

    if not tokens:
        return documents

    scored_docs: list[tuple[int, Document]] = []
    extra_tokens = [term.lower() for term in (extra_terms or []) if term]
    for doc in documents:
        haystack = f"{doc.page_content} {doc.metadata.get('document_name', '')}".lower()
        score = sum(haystack.count(token) for token in set(tokens))
        score += sum(haystack.count(token) for token in set(extra_tokens))
        if score > 0:
            scored_docs.append((score, doc))

    if scored_docs:
        scored_docs.sort(key=lambda item: item[0], reverse=True)
        best_score = scored_docs[0][0]
        filtered = [doc for score, doc in scored_docs if score >= max(1, best_score - 1)]
        logger.info(
            "Case filter reduced rerank candidates from %d to %d for '%s' (best_token_hits=%d).",
            len(documents),
            len(filtered),
            case_name,
            best_score,
        )
        return filtered

    logger.info(
        "Case filter found no exact mentions for '%s'; using original candidates.",
        case_name,
    )
    return documents


def _normalize_scores(scores):
    """Normalize raw reranker scores into 0..1 range without changing rank order."""
    import torch

    return torch.sigmoid(torch.tensor(scores)).tolist()


def _case_alignment_bonus(
    document: Document,
    case_name: str | None = None,
    extra_terms: list[str] | None = None,
) -> float:
    """Compute a small lexical bonus for case-lookup candidates."""
    if not case_name:
        return 0.0

    haystack = f"{document.page_content} {document.metadata.get('document_name', '')}".lower()
    case_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", case_name.lower())
        if token not in {"v", "vs", "versus", "the", "case"}
    ]
    bonus = 0.0

    if case_tokens:
        bonus += min(0.4, 0.1 * sum(haystack.count(token) for token in set(case_tokens)))

    if extra_terms:
        bonus += min(0.3, 0.08 * sum(haystack.count(term.lower()) for term in set(extra_terms)))

    return bonus


def rank_case_lookup_candidates(
    documents: list[Document],
    case_name: str | None,
    case_terms: list[str] | None = None,
    top_n: int | None = None,
) -> list[tuple[Document, float]]:
    """Deterministically rank named-case candidates using lexical overlap only."""
    top_n = top_n or settings.rerank_top_n

    if not documents:
        return []

    if not case_name:
        return [(doc, 0.0) for doc in documents[:top_n]]

    query_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", case_name.lower())
        if token not in {"v", "vs", "versus", "the", "case"}
    ]
    extra_tokens = [term.lower() for term in (case_terms or []) if term]

    scored: list[tuple[float, Document]] = []
    normalized_case = case_name.lower()

    for doc in documents:
        haystack = f"{doc.page_content} {doc.metadata.get('document_name', '')}".lower()
        score = 0.0

        if normalized_case in haystack:
            score += 10.0

        if query_tokens:
            score += 2.0 * sum(haystack.count(token) for token in set(query_tokens))

        if extra_tokens:
            score += 1.5 * sum(haystack.count(token) for token in set(extra_tokens))

        # Prefer documents whose metadata or text mention the exact citation.
        if re.search(r"\b20\d{2}\b", haystack):
            score += 0.5

        if score > 0:
            scored.append((score, doc))

    if not scored:
        return [(doc, 0.0) for doc in documents[:top_n]]

    scored.sort(key=lambda item: item[0], reverse=True)
    ranked = [(doc, score) for score, doc in scored[:top_n]]

    logger.info(
        "Case lookup ranked %d candidates down to %d for '%s'.",
        len(documents),
        len(ranked),
        case_name,
    )
    return ranked

# Cache the cross-encoder model after first load.
_cross_encoder = None


def _get_cross_encoder():
    """
    Lazily load and cache the local cross-encoder model.

    Uses sentence-transformers CrossEncoder — downloads the model on
    first run (~80 MB), then runs locally on CPU.
    """
    global _cross_encoder
    if _cross_encoder is not None:
        return _cross_encoder

    from sentence_transformers import CrossEncoder

    _cross_encoder = CrossEncoder(settings.rerank_model)
    logger.info("Loaded local cross-encoder model: %s", settings.rerank_model)
    return _cross_encoder


def rerank_with_cross_encoder(
    query: str,
    documents: list[Document],
    top_n: int | None = None,
    case_name: str | None = None,
    case_terms: list[str] | None = None,
) -> list[tuple[Document, float]]:
    """
    Rerank *documents* using a local cross-encoder model.

    Args:
        query: The user's legal question.
        documents: Candidate documents from the hybrid retriever.
        top_n: Number of top results to keep (defaults to
               ``settings.rerank_top_n``).

    Returns:
        A list of ``(Document, relevance_score)`` tuples sorted by
        descending relevance.
    """
    import numpy as np

    top_n = top_n or settings.rerank_top_n

    if not documents:
        logger.warning("Reranker received an empty document list.")
        return []

    model = _get_cross_encoder()

    # Cross-encoder expects (query, passage) pairs.
    pairs = [(query, doc.page_content) for doc in documents]
    scores = model.predict(pairs)
    normalized_scores = _normalize_scores(scores)

    combined_scores = [
        float(normalized_scores[i]) + _case_alignment_bonus(documents[i], case_name, case_terms)
        for i in range(len(documents))
    ]

    # Sort by descending score and take top_n.
    top_indices = np.argsort(combined_scores)[::-1][:top_n]

    ranked = [
        (documents[i], float(combined_scores[i]))
        for i in top_indices
    ]

    logger.info(
        "Cross-encoder reranked %d → %d documents for: '%.60s…'",
        len(documents),
        len(ranked),
        query,
    )
    return ranked


def rerank_with_tfidf_fallback(
    query: str,
    documents: list[Document],
    top_n: int | None = None,
    case_name: str | None = None,
    case_terms: list[str] | None = None,
) -> list[tuple[Document, float]]:
    """
    Lightweight fallback reranker using TF-IDF cosine similarity.

    This does **not** require any external model download and is suitable
    when the cross-encoder model is unavailable.

    Args:
        query: The user's legal question.
        documents: Candidate documents.
        top_n: Number of top results.

    Returns:
        ``(Document, score)`` tuples sorted descending.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np

    top_n = top_n or settings.rerank_top_n

    if not documents:
        return []

    corpus = [query] + [doc.page_content for doc in documents]
    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(corpus)

    # Cosine similarity between the query vector and all document vectors.
    query_vec = tfidf_matrix[0:1]
    doc_vecs = tfidf_matrix[1:]
    similarities = cosine_similarity(query_vec, doc_vecs).flatten()
    normalized_scores = similarities.tolist()

    combined_scores = [
        float(normalized_scores[i]) + _case_alignment_bonus(documents[i], case_name, case_terms)
        for i in range(len(documents))
    ]

    # Sort by descending similarity.
    top_indices = np.argsort(combined_scores)[::-1][:top_n]

    ranked = [
        (documents[i], float(combined_scores[i]))
        for i in top_indices
    ]

    logger.info(
        "TF-IDF fallback reranked %d → %d documents.",
        len(documents),
        len(ranked),
    )
    return ranked


def rerank(
    query: str,
    documents: list[Document],
    top_n: int | None = None,
    case_name: str | None = None,
    case_terms: list[str] | None = None,
) -> list[tuple[Document, float]]:
    """
    High-level reranking entry point with automatic backend selection.

    Strategy:
      1. Try the local cross-encoder model (primary).
      2. If it fails → fall back to TF-IDF cosine similarity.

    No API keys required for either path.

    Args:
        query: The user's legal question.
        documents: Candidate chunks from the hybrid retriever.
        top_n: How many to keep.

    Returns:
        Top-*n* ``(Document, relevance_score)`` tuples.
    """
    if case_name:
        return rank_case_lookup_candidates(
            documents,
            case_name,
            case_terms=case_terms,
            top_n=top_n,
        )

    # Render's free instance is intentionally configured for the lightweight
    # TF-IDF path. Avoid importing sentence-transformers/torch just to discover
    # that the configured model is the explicit fallback sentinel.
    if settings.rerank_model == "TF-IDF-FAST-FALLBACK":
        return rerank_with_tfidf_fallback(
            query,
            documents,
            top_n,
            case_name=case_name,
            case_terms=case_terms,
        )

    try:
        return rerank_with_cross_encoder(
            query,
            documents,
            top_n,
            case_name=case_name,
            case_terms=case_terms,
        )
    except Exception as exc:
        logger.error(
            "Cross-encoder rerank failed, falling back to TF-IDF: %s", exc
        )

    return rerank_with_tfidf_fallback(
        query,
        documents,
        top_n,
        case_name=case_name,
        case_terms=case_terms,
    )

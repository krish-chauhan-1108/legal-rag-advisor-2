"""
BM25 Keyword Retriever for the Legal RAG Advisor.

Provides a sparse retriever using the Okapi BM25 algorithm.  This is
*critical* for legal RAG because:

- Legal queries often contain precise defined terms (e.g., "Force Majeure",
  "Material Adverse Effect") that must be matched *lexically*, not just
  semantically.
- Dense embeddings may map synonyms to similar vectors but can miss exact
  terminology that carries specific legal weight.

The BM25 index is built in-memory from the same ``Document`` objects stored
in the vector store.  It is rebuilt on every ingestion cycle (fast for
corpora up to ~100k chunks).

Implementation
--------------
We wrap ``rank_bm25.BM25Okapi`` behind LangChain's ``BaseRetriever``
interface so it can be composed with the dense retriever via
``EnsembleRetriever``.
"""

from __future__ import annotations

import re
from threading import Lock
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field
from rank_bm25 import BM25Okapi

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# ─── Simple legal-aware tokenizer ──────────────────────────────────────────
# We keep hyphens and apostrophes inside words (e.g., "non-compete",
# "party's") and lowercase everything.
_TOKEN_RE = re.compile(r"[a-z0-9](?:[a-z0-9'\-]*[a-z0-9])?", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    """Tokenize *text* into lowercase word tokens for BM25."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _trim_text_for_bm25(text: str) -> str:
    """Trim long chunk text before BM25 indexing to reduce memory usage."""
    max_chars = max(256, int(settings.bm25_max_chars_per_doc))
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


class BM25Retriever(BaseRetriever):
    """
    LangChain-compatible retriever backed by an in-memory BM25 index.

    Attributes:
        documents: The corpus of ``Document`` objects.
        k: Number of results to return.
        bm25: The underlying ``BM25Okapi`` instance (built automatically).
        tokenized_corpus: Pre-tokenized version of the corpus.
    """

    documents: list[Document] = Field(default_factory=list)
    k: int = Field(default=20)
    bm25: Any = Field(default=None, exclude=True)
    tokenized_corpus: list[list[str]] = Field(default_factory=list, exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    def build_index(self) -> None:
        """
        (Re-)build the BM25 index from the current document corpus.

        This should be called after adding new documents.
        """
        if not settings.bm25_enabled:
            self.documents = []
            self.tokenized_corpus = []
            self.bm25 = None
            logger.info("BM25 indexing disabled by configuration.")
            return

        if not self.documents:
            logger.warning("BM25 index build skipped — no documents provided.")
            return

        total = len(self.documents)
        logger.info(
            "Tokenizing %d documents for BM25 (max_chars_per_doc=%d)…",
            total,
            settings.bm25_max_chars_per_doc,
        )
        self.tokenized_corpus = []
        log_interval = max(1, total // 5)  # Log ~5 progress updates
        for i, doc in enumerate(self.documents):
            self.tokenized_corpus.append(_tokenize(_trim_text_for_bm25(doc.page_content)))
            if (i + 1) % log_interval == 0 or (i + 1) == total:
                logger.info("  Tokenized %d / %d (%.0f%%)", i + 1, total, (i + 1) / total * 100)

        logger.info("Building BM25Okapi index…")
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        logger.info("BM25 index built over %d documents.", total)

    def add_documents(self, new_docs: list[Document]) -> None:
        """
        Append documents to the corpus and rebuild the index.

        Args:
            new_docs: New ``Document`` objects to add.
        """
        self.documents.extend(new_docs)
        self.build_index()

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        """
        Retrieve the top-*k* documents by BM25 score.

        Args:
            query: The user's search query.

        Returns:
            Ranked list of ``Document`` objects.
        """
        if self.bm25 is None or not self.documents:
            logger.warning("BM25 retriever called before index was built.")
            return []

        tokenized_query = _tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)

        # Pair each document with its score and sort descending.
        scored_docs = sorted(
            zip(scores, self.documents),
            key=lambda x: x[0],
            reverse=True,
        )

        top_docs = [doc for _, doc in scored_docs[: self.k]]
        logger.debug(
            "BM25 returned %d results for query: '%.60s…'",
            len(top_docs),
            query,
        )
        return top_docs


# ─── Module-level singleton ────────────────────────────────────────────────
_bm25_retriever: BM25Retriever | None = None
_bm25_build_lock = Lock()


def get_bm25_retriever(k: int = 20) -> BM25Retriever:
    """
    Return the singleton BM25 retriever, creating it if necessary.

    Args:
        k: Number of results to return per query.
    """
    global _bm25_retriever
    if _bm25_retriever is None:
        _bm25_retriever = BM25Retriever(k=k)
    else:
        _bm25_retriever.k = k
    return _bm25_retriever


def ensure_bm25_ready(k: int = 20) -> BM25Retriever:
    """Return a BM25 retriever and build it from Chroma if needed."""
    retriever = get_bm25_retriever(k=k)

    if retriever.bm25 is not None and retriever.documents:
        return retriever

    with _bm25_build_lock:
        retriever = get_bm25_retriever(k=k)
        if retriever.bm25 is not None and retriever.documents:
            return retriever

        logger.info("BM25 index is missing — rebuilding from vector store now.")
        return rebuild_bm25_from_vector_store()


def rebuild_bm25_from_vector_store() -> BM25Retriever:
    """
    Rebuild the BM25 index from all documents currently in the vector store.

    This is called after ingestion to synchronize the sparse index with the
    dense store.

    Returns:
        The rebuilt BM25 retriever.
    """
    from retrieval.vector_store import get_vector_store

    store = get_vector_store()
    collection = store._collection

    retriever = get_bm25_retriever()
    if not settings.bm25_enabled:
        retriever.documents = []
        retriever.build_index()
        return retriever

    total_expected = collection.count()
    max_docs = max(1, int(settings.bm25_max_docs))
    page_size = max(100, int(settings.bm25_page_size))
    start_offset = max(0, total_expected - max_docs)

    # Fetch documents from ChromaDB in pages so large collections do not
    # overflow SQLite's variable limit and to cap peak memory usage.
    documents = []
    offset = start_offset
    logger.info(
        "Fetching up to %d chunks from ChromaDB for BM25 rebuild (total=%d)…",
        max_docs,
        total_expected,
    )

    while True:
        batch = collection.get(
            include=["documents", "metadatas"],
            limit=page_size,
            offset=offset,
        )

        batch_documents = batch.get("documents") or []
        batch_metadatas = batch.get("metadatas") or []

        if not batch_documents:
            break

        for text, meta in zip(batch_documents, batch_metadatas):
            documents.append(
                Document(
                    page_content=_trim_text_for_bm25(text),
                    metadata=meta or {},
                )
            )

        offset += len(batch_documents)
        fetched = min(max_docs, max(0, offset - start_offset))
        logger.info(
            "  Fetched %d / %d chunks for BM25 window (%.0f%%)",
            fetched,
            max_docs,
            fetched / max(max_docs, 1) * 100,
        )

        if len(batch_documents) < page_size or len(documents) >= max_docs:
            break

    if len(documents) > max_docs:
        documents = documents[-max_docs:]

    retriever.documents = documents
    retriever.build_index()

    logger.info(
        "BM25 index rebuilt from vector store — indexed=%d, total_in_chroma=%d, max_docs=%d.",
        len(documents),
        total_expected,
        max_docs,
    )
    return retriever

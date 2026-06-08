"""
Vector Store management for the Legal RAG Advisor.

Wraps ChromaDB with LangChain's ``Chroma`` integration to provide:
  - Persistent local storage (survives server restarts).
  - Cloud embeddings via Google Gemini API.
  - Simple add/search/count/delete operations.

Why ChromaDB?
-------------
- Zero external infrastructure (no Docker, no managed service).
- Built-in persistence via SQLite + Parquet.
- Native metadata filtering — critical for scoping searches to a
  specific document or section.
"""

from langchain_core.documents import Document

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Module-level singletons — initialized lazily.
_embedding_function = None
_vector_store = None


def _get_embedding_function():
    """
    Build and cache the embedding function using Google Gemini.

    Uses the model specified in settings.embedding_model via API.

    Returns:
        A LangChain GoogleGenerativeAIEmbeddings instance.
    """
    global _embedding_function
    if _embedding_function is not None:
        return _embedding_function

    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    _embedding_function = GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.gemini_api_key,
    )
    logger.info(
        "Initialized Google Gemini embeddings: model=%s",
        settings.embedding_model,
    )

    return _embedding_function


API_KEYS = [
    "AQ.Ab8RN6KV0Q69xyi9xW3Vx4j-fSr4dXEeSKyMDHZUnkiFkf9jHA",
    "AQ.Ab8RN6IKHKIm28twQxKmGPpx_ZutYURxWZxA7jiVnOf1whcMPQ"
]
_current_key_idx = 0

def rotate_api_key() -> bool:
    """
    Swap the Gemini API key with the next fallback key and re-initialize the embedding function.
    Returns True if successfully rotated, False otherwise.
    """
    global _embedding_function, _vector_store, _current_key_idx
    
    _current_key_idx += 1
    exhausted = False
    if _current_key_idx >= len(API_KEYS):
        _current_key_idx = 0
        exhausted = True
        
    logger.info(f"Rotating API key to fallback #{_current_key_idx + 1} due to rate limits...")
    
    # Update the active key
    settings.gemini_api_key = API_KEYS[_current_key_idx]
    
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    
    # Re-initialize the embedding function with the new key
    _embedding_function = GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.gemini_api_key,
    )
    
    # If the vector store is already initialized, update its internal embedding function
    if _vector_store is not None:
        _vector_store._embedding_function = _embedding_function
        
    return not exhausted


def get_vector_store():
    """
    Return the singleton ChromaDB-backed vector store.

    Creates the underlying collection and persistence directory on first
    call.  Subsequent calls return the cached instance.

    Returns:
        A LangChain ``Chroma`` vector store.
    """
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    from langchain_chroma import Chroma

    settings.ensure_directories()
    embeddings = _get_embedding_function()

    _vector_store = Chroma(
        collection_name=settings.chroma_collection_name,
        embedding_function=embeddings,
        persist_directory=settings.chroma_persist_dir,
    )

    logger.info(
        "ChromaDB vector store ready — collection='%s', persist='%s'.",
        settings.chroma_collection_name,
        settings.chroma_persist_dir,
    )
    return _vector_store


def add_documents(documents: list[Document]) -> list[str]:
    """
    Embed and store a batch of documents in the vector store.

    Args:
        documents: LangChain ``Document`` objects (with metadata).

    Returns:
        The list of IDs assigned by ChromaDB.
    """
    store = get_vector_store()
    ids = store.add_documents(documents)
    logger.info("Added %d documents to the vector store.", len(ids))
    return ids


def similarity_search(
    query: str,
    k: int | None = None,
    filter_dict: dict | None = None,
) -> list[Document]:
    """
    Perform a dense vector similarity search.

    Args:
        query: Natural-language query string.
        k: Number of results to return (defaults to ``settings.retrieval_top_k``).
        filter_dict: Optional ChromaDB metadata filter
                     (e.g., ``{"document_name": "NDA_2024.pdf"}``).

    Returns:
        Ranked list of ``Document`` objects.
    """
    store = get_vector_store()
    k = k or settings.retrieval_top_k

    results = store.similarity_search(
        query=query,
        k=k,
        filter=filter_dict,
    )
    logger.debug("Dense search returned %d results for query: '%.60s…'", len(results), query)
    return results


def similarity_search_with_score(
    query: str,
    k: int | None = None,
    filter_dict: dict | None = None,
) -> list[tuple[Document, float]]:
    """
    Like :func:`similarity_search` but also returns distance scores.

    Lower scores indicate higher similarity (L2 distance by default in
    ChromaDB).
    """
    store = get_vector_store()
    k = k or settings.retrieval_top_k

    results = store.similarity_search_with_score(
        query=query,
        k=k,
        filter=filter_dict,
    )
    return results


def get_document_count() -> int:
    """Return the total number of chunks stored in the vector store."""
    store = get_vector_store()
    collection = store._collection  # ChromaDB internal — stable API
    return collection.count()


def delete_document(document_name: str) -> int:
    """
    Delete all chunks belonging to a specific document.

    Args:
        document_name: The ``document_name`` metadata value.

    Returns:
        Number of chunks deleted.
    """
    store = get_vector_store()
    collection = store._collection

    # Fetch and delete in batches to avoid SQLite variable limits
    total_deleted = 0
    limit = 500
    
    while True:
        results = collection.get(where={"document_name": document_name}, limit=limit)
        ids_to_delete = results["ids"]

        if not ids_to_delete:
            break

        collection.delete(ids=ids_to_delete)
        total_deleted += len(ids_to_delete)

    if total_deleted > 0:
        logger.info(
            "Deleted %d chunks for document '%s'.",
            total_deleted,
            document_name,
        )

    return total_deleted


def get_retriever(k: int | None = None, filter_dict: dict | None = None):
    """
    Return a LangChain ``VectorStoreRetriever`` for chain integration.

    Args:
        k: Number of results.
        filter_dict: Optional metadata filter.

    Returns:
        A LangChain retriever instance.
    """
    store = get_vector_store()
    search_kwargs = {"k": k or settings.retrieval_top_k}
    if filter_dict:
        search_kwargs["filter"] = filter_dict
    return store.as_retriever(search_kwargs=search_kwargs)

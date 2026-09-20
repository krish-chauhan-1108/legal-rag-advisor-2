"""
Configuration module for the Legal RAG Advisor.

Centralizes all application settings using pydantic-settings for type-safe
environment variable parsing with sensible defaults for local development.

Now updated to use the Google Gemini API (supporting Gemma and Gemini models).
"""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application-wide configuration.

    Values are loaded from environment variables and/or a .env file at the
    project root. Every field has a sane default so the app can start in
    development mode with minimal configuration.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM (via Gemini API) ────────────────────────────────────────────────
    # To use Gemma 4 26B via Gemini API, set to "gemma-4-26b-a4b-it".
    # Or use Gemini models like "gemini-2.5-flash".
    llm_model: str = "gemma-4-31b-it"
    llm_temperature: float = 0.25  # Increased slightly to prevent repetitive hallucination loops
    gemini_api_key: str = ""
    gemini_api_key_fallback: str = ""
    gemini_api_key_3: str = ""
    gemini_api_key_4: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # ── Embeddings (Google Gemini API)
    embedding_model: str = "models/gemini-embedding-2"
    embedding_dimensions: int = 768

    # ── Chunking ────────────────────────────────────────────────────────────
    # For highly precise legal retrieval, smaller chunks are better to capture specific clauses
    chunk_size_tokens: int = 400
    chunk_overlap_tokens: int = 100
    tiktoken_encoding: str = "cl100k_base"

    # ── Retrieval ───────────────────────────────────────────────────────────
    retrieval_top_k: int = 20         # Initial broad retrieval
    rerank_top_n: int = 8             # After reranking
    bm25_weight: float = 0.4          # Weight in ensemble (dense = 1 - this)
    dense_weight: float = 0.6
    bm25_enabled: bool = True
    bm25_max_docs: int = 50000
    bm25_max_chars_per_doc: int = 5000
    bm25_page_size: int = 1000

    # ── Re-ranking (local cross-encoder) ────────────────────────────────────
    # Setting an invalid model name forces the system to instantly fall back to the 
    # blazing fast TF-IDF local reranker instead of grinding the CPU.
    rerank_model: str = "TF-IDF-FAST-FALLBACK"

    # ── Storage ─────────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./data/chroma_db"
    chroma_collection_name: str = "legal_documents_multilingual_v2"
    upload_dir: str = "./data/uploads"

    # ── Logging ─────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Auth ────────────────────────────────────────────────────────────────
    google_client_id: str | None = None

    # ── Server ──────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    
    # ── Database ────────────────────────────────────────────────────────────
    # Keep the local SQLite database in the project directory by default. The
    # value can be overridden with DATABASE_URL on Render or another host.
    database_url: str = "sqlite:///./legal.db"
    seed_upload_token: str = ""

    # ── Helpers ─────────────────────────────────────────────────────────────
    def ensure_directories(self) -> None:
        """Create required data directories if they don't exist."""
        Path(self.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)


# Singleton instance — import this throughout the application.
settings = Settings()

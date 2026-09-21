"""
Configuration module for TRANA.

Centralizes all application settings using pydantic-settings for type-safe
environment variable parsing with sensible defaults for local development.

Now updated to use the Google Gemini API (supporting Gemma and Gemini models).
"""

from pathlib import Path

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
    deep_timeout_seconds: float = 8.0
    analysis_deadline_seconds: float = 20.0
    gemini_api_key: str = ""
    gemini_api_key_fallback: str = ""
    gemini_api_key_3: str = ""
    gemini_api_key_4: str = ""
    # Comma-separated verified Google email addresses allowed to use the
    # backend administration API.
    admin_emails: str = ""
    # Fernet key used to encrypt Gemini API keys persisted in the database.
    # Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    api_key_encryption_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # ── Embeddings (Google Gemini API)
    # Exact statutory text comes from legal_sources/corpus.json, not embeddings.

    # ── Chunking ────────────────────────────────────────────────────────────
    # For highly precise legal retrieval, smaller chunks are better to capture specific clauses

    # ── Retrieval ───────────────────────────────────────────────────────────

    # ── Re-ranking (local cross-encoder) ────────────────────────────────────
    # Setting an invalid model name forces the system to instantly fall back to the 
    # blazing fast TF-IDF local reranker instead of grinding the CPU.

    # ── Storage ─────────────────────────────────────────────────────────────
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

    # ── Helpers ─────────────────────────────────────────────────────────────
    def ensure_directories(self) -> None:
        """Create required data directories if they don't exist."""
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)


# Singleton instance — import this throughout the application.
settings = Settings()

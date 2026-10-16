from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, LargeBinary
from datetime import datetime
import uuid
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    google_id = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuthSession(Base):
    """Hashed, revocable TRANA sessions issued after Google sign-in."""

    __tablename__ = "auth_sessions"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    user_email = Column(String, index=True, nullable=False)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, index=True)
    user_email = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False) # 'user' or 'assistant'
    content = Column(String, nullable=False)
    structured_content = Column(String, nullable=True) # JSON string
    sources = Column(String, nullable=True) # JSON string
    model_used = Column(String, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatAttachment(Base):
    """User supplied document retained with its owning chat (database-backed)."""

    __tablename__ = "chat_attachments"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    content = Column(LargeBinary, nullable=False)
    extracted_text = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class GeminiAPIKey(Base):
    """Encrypted Gemini credentials managed by the admin console."""

    __tablename__ = "gemini_api_keys"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    label = Column(String(120), nullable=False)
    encrypted_key = Column(Text, nullable=False)
    fingerprint = Column(String(64), unique=True, index=True, nullable=False)
    masked_key = Column(String(32), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    rotation_order = Column(Integer, nullable=False, default=0, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    last_error_status = Column(String(32), nullable=True)
    last_error_at = Column(DateTime, nullable=True)


class GeminiAPIKeyUsage(Base):
    """Per-key/model counters in minute and IST-calendar-day buckets."""

    __tablename__ = "gemini_api_key_usage"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    api_key_id = Column(String, ForeignKey("gemini_api_keys.id"), nullable=False, index=True)
    model = Column(String(160), nullable=False, index=True)
    bucket_type = Column(String(16), nullable=False)
    bucket_start = Column(DateTime, nullable=False)
    total_requests = Column(Integer, nullable=False, default=0)
    successful_requests = Column(Integer, nullable=False, default=0)
    failed_requests = Column(Integer, nullable=False, default=0)
    quota_failures = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "api_key_id",
            "model",
            "bucket_type",
            "bucket_start",
            name="uq_gemini_key_usage_bucket",
        ),
        Index("ix_gemini_key_usage_lookup", "api_key_id", "model", "bucket_type", "bucket_start"),
    )


class ProviderAPIKey(Base):
    """Encrypted credentials for any model provider.

    This is an additive replacement for ``GeminiAPIKey``.  The legacy table is
    intentionally retained so old deployments and mixed-version processes can
    continue to read existing Gemini credentials during rollout.
    """

    __tablename__ = "provider_api_keys"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String(64), nullable=False, index=True)
    model = Column(String(160), nullable=False, index=True)
    mode = Column(String(16), nullable=False, default="quick", index=True)
    base_url = Column(String(255), nullable=True)
    label = Column(String(120), nullable=False)
    encrypted_key = Column(Text, nullable=False)
    fingerprint = Column(String(64), nullable=False, index=True)
    masked_key = Column(String(32), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    rotation_order = Column(Integer, nullable=False, default=0, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    last_error_status = Column(String(32), nullable=True)
    last_error_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "fingerprint",
            name="uq_provider_api_key_fingerprint",
        ),
        Index("ix_provider_api_key_pool", "provider", "model", "mode", "is_active", "rotation_order"),
    )


class ProviderAPIKeyUsage(Base):
    """Per-provider-key/model counters in minute and IST-calendar-day buckets."""

    __tablename__ = "provider_api_key_usage"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    provider_key_id = Column(String, ForeignKey("provider_api_keys.id"), nullable=False, index=True)
    provider = Column(String(64), nullable=False, index=True)
    model = Column(String(160), nullable=False, index=True)
    mode = Column(String(16), nullable=False, default="quick", index=True)
    bucket_type = Column(String(16), nullable=False)
    bucket_start = Column(DateTime, nullable=False)
    total_requests = Column(Integer, nullable=False, default=0)
    successful_requests = Column(Integer, nullable=False, default=0)
    failed_requests = Column(Integer, nullable=False, default=0)
    quota_failures = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "provider_key_id",
            "model",
            "mode",
            "bucket_type",
            "bucket_start",
            name="uq_provider_key_usage_bucket",
        ),
        Index(
            "ix_provider_key_usage_lookup",
            "provider_key_id",
            "provider",
            "model",
            "mode",
            "bucket_type",
            "bucket_start",
        ),
    )

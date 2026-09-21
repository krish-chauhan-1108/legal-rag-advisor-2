"""Database-backed Gemini API-key rotation and usage accounting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from threading import RLock
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.exc import IntegrityError

from config import settings
from database import SessionLocal
import models.db_models as db_models
from utils.logger import get_logger

logger = get_logger(__name__)

KEY_ENV_FIELDS = (
    ("GEMINI_API_KEY", "gemini_api_key"),
    ("GEMINI_API_KEY_FALLBACK", "gemini_api_key_fallback"),
    ("GEMINI_API_KEY_3", "gemini_api_key_3"),
    ("GEMINI_API_KEY_4", "gemini_api_key_4"),
)
IST = ZoneInfo("Asia/Kolkata")
QUICK_UNAVAILABLE_COOLDOWN_SECONDS = 300

_rotation_lock = RLock()
_current_key_idx = 0
_quick_unavailable_until = 0.0


class QuickModelUnavailableError(RuntimeError):
    """Raised when Gemini Flash is rate-limited on every active key."""


@dataclass(frozen=True)
class APIKeyRecord:
    id: str
    secret: str
    label: str
    fingerprint: str
    masked_key: str


def _env_key_values() -> list[tuple[str, str, str]]:
    """Return non-empty legacy keys as ``(env_name, label, secret)`` tuples."""
    result = []
    for index, (env_name, field_name) in enumerate(KEY_ENV_FIELDS, start=1):
        secret = str(getattr(settings, field_name, "") or "").strip()
        if secret:
            result.append((env_name, f"Environment key {index}", secret))
    return result


def encryption_is_configured() -> bool:
    return bool(str(settings.api_key_encryption_key or "").strip())


def _get_fernet() -> Fernet:
    raw_key = str(settings.api_key_encryption_key or "").strip()
    if not raw_key:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY is not configured.")
    try:
        return Fernet(raw_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def fingerprint_api_key(secret: str) -> str:
    return sha256(secret.encode("utf-8")).hexdigest()


def mask_api_key(secret: str) -> str:
    if len(secret) <= 8:
        return "••••••••"
    return f"{secret[:4]}…{secret[-4:]}"


def encrypt_api_key(secret: str) -> str:
    return _get_fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def _decrypt_api_key(encrypted_key: str) -> str:
    try:
        return _get_fernet().decrypt(encrypted_key.encode("utf-8")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RuntimeError("A stored Gemini API key could not be decrypted.") from exc


def initialize_key_store() -> int:
    """Create DB rows for legacy env keys without duplicating existing keys."""
    if not encryption_is_configured():
        logger.warning(
            "API_KEY_ENCRYPTION_KEY is not configured; using legacy environment "
            "keys and disabling persistent key management until it is supplied."
        )
        return 0

    imported = 0
    db = SessionLocal()
    try:
        for order, (_env_name, label, secret) in enumerate(_env_key_values()):
            fingerprint = fingerprint_api_key(secret)
            existing = (
                db.query(db_models.GeminiAPIKey)
                .filter(db_models.GeminiAPIKey.fingerprint == fingerprint)
                .first()
            )
            if existing is not None:
                continue
            db.add(
                db_models.GeminiAPIKey(
                    label=label,
                    encrypted_key=encrypt_api_key(secret),
                    fingerprint=fingerprint,
                    masked_key=mask_api_key(secret),
                    is_active=True,
                    rotation_order=order,
                )
            )
            imported += 1
        if imported:
            db.commit()
            logger.info("Imported %d legacy Gemini API key(s) into encrypted storage.", imported)
        return imported
    except Exception:
        db.rollback()
        logger.exception("Could not initialize encrypted Gemini API key storage.")
        return 0
    finally:
        db.close()


def _database_key_records() -> list[APIKeyRecord]:
    db = SessionLocal()
    try:
        rows = (
            db.query(db_models.GeminiAPIKey)
            .filter(db_models.GeminiAPIKey.is_active.is_(True))
            .order_by(db_models.GeminiAPIKey.rotation_order.asc(), db_models.GeminiAPIKey.created_at.asc())
            .all()
        )
        records = []
        for row in rows:
            try:
                secret = _decrypt_api_key(row.encrypted_key)
            except RuntimeError:
                logger.error("Skipping encrypted API key %s because it cannot be decrypted.", row.id)
                continue
            records.append(
                APIKeyRecord(
                    id=row.id,
                    secret=secret,
                    label=row.label,
                    fingerprint=row.fingerprint,
                    masked_key=row.masked_key,
                )
            )
        return records
    finally:
        db.close()


def get_active_key_records() -> list[APIKeyRecord]:
    """Load active keys in rotation order, with a local env fallback."""
    if encryption_is_configured():
        # An empty DB is intentional: the admin may have disabled every key.
        return _database_key_records()

    return [
        APIKeyRecord(
            id=f"env-{index}",
            secret=secret,
            label=label,
            fingerprint=fingerprint_api_key(secret),
            masked_key=mask_api_key(secret),
        )
        for index, (_env_name, label, secret) in enumerate(_env_key_values(), start=1)
    ]


def get_active_key_count() -> int:
    return len(get_active_key_records())


def get_current_key_record() -> APIKeyRecord | None:
    records = get_active_key_records()
    if not records:
        logger.error("No active Gemini API keys configured.")
        return None
    with _rotation_lock:
        global _current_key_idx
        _current_key_idx %= len(records)
        return records[_current_key_idx]


def get_current_key() -> str:
    record = get_current_key_record()
    return record.secret if record else ""


def rotate_key() -> bool:
    """Move to the next active key; return false after a full rotation."""
    records = get_active_key_records()
    if len(records) <= 1:
        return False
    with _rotation_lock:
        global _current_key_idx
        _current_key_idx += 1
        if _current_key_idx >= len(records):
            _current_key_idx = 0
            logger.error("All active Gemini API keys exhausted; wrapped to the first key.")
            return False
        logger.warning("Rotated Gemini API key to position #%d.", _current_key_idx + 1)
        return True


def _bucket_starts(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = (now or datetime.now(IST)).astimezone(IST)
    local_naive = current.replace(tzinfo=None)
    minute_start = local_naive.replace(second=0, microsecond=0)
    day_start = local_naive.replace(hour=0, minute=0, second=0, microsecond=0)
    return minute_start, day_start


def record_provider_attempt(
    key_id: str,
    model: str,
    outcome: str,
    error: Exception | str | None = None,
) -> None:
    """Record one provider attempt in both minute and IST-day buckets."""
    if not key_id or key_id.startswith("env-") or not encryption_is_configured():
        return
    if outcome not in {"success", "failure", "quota"}:
        raise ValueError(f"Unsupported provider outcome: {outcome}")

    minute_start, day_start = _bucket_starts()
    db = SessionLocal()
    try:
        key = db.query(db_models.GeminiAPIKey).filter(db_models.GeminiAPIKey.id == key_id).first()
        if key is None:
            return
        for bucket_type, bucket_start in (("minute", minute_start), ("day", day_start)):
            usage = (
                db.query(db_models.GeminiAPIKeyUsage)
                .filter(
                    db_models.GeminiAPIKeyUsage.api_key_id == key_id,
                    db_models.GeminiAPIKeyUsage.model == model,
                    db_models.GeminiAPIKeyUsage.bucket_type == bucket_type,
                    db_models.GeminiAPIKeyUsage.bucket_start == bucket_start,
                )
                .with_for_update()
                .first()
            )
            if usage is None:
                usage = db_models.GeminiAPIKeyUsage(
                    api_key_id=key_id,
                    model=model,
                    bucket_type=bucket_type,
                    bucket_start=bucket_start,
                    total_requests=0,
                    successful_requests=0,
                    failed_requests=0,
                    quota_failures=0,
                )
                db.add(usage)
            usage.total_requests += 1
            if outcome == "success":
                usage.successful_requests += 1
            else:
                usage.failed_requests += 1
            if outcome == "quota":
                usage.quota_failures += 1

        key.last_used_at = datetime.utcnow()
        key.last_error_status = None if outcome == "success" else outcome
        key.last_error_at = None if outcome == "success" else datetime.utcnow()
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning("Concurrent usage bucket update was skipped for key %s.", key_id)
    except Exception:
        db.rollback()
        logger.exception("Could not record Gemini usage for key %s.", key_id)
    finally:
        db.close()


def is_quota_error(error: Exception | str) -> bool:
    """Return whether an error indicates a provider quota or rate-limit failure."""
    error_text = str(error).lower()
    return any(marker in error_text for marker in (
        "429",
        "quota",
        "resource_exhausted",
        "exhausted",
        "rate limit",
    ))


def is_quick_temporarily_unavailable() -> bool:
    import time
    return time.monotonic() < _quick_unavailable_until


def mark_quick_temporarily_unavailable() -> None:
    import time
    global _quick_unavailable_until
    _quick_unavailable_until = time.monotonic() + QUICK_UNAVAILABLE_COOLDOWN_SECONDS
    logger.error(
        "Gemini Flash quota exhausted on all active keys. Quick Thinking unavailable for %ss.",
        QUICK_UNAVAILABLE_COOLDOWN_SECONDS,
    )


def clear_quick_temporarily_unavailable() -> None:
    global _quick_unavailable_until
    _quick_unavailable_until = 0.0

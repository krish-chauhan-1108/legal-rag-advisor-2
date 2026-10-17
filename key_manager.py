"""Database-backed provider key pools, rotation, and usage accounting.

The legacy Gemini helpers remain available for mixed-version compatibility.
Provider-neutral helpers use additive tables and keep a separate in-memory
rotation cursor for every ``(provider, model, mode)`` pool.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import os
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
PROVIDER_ENV_FIELDS = {
    "cerebras": (
        ("CEREBRAS_API_KEY", "Cerebras environment key 1"),
        ("CEREBRAS_API_KEY_2", "Cerebras environment key 2"),
        ("CEREBRAS_API_KEY_3", "Cerebras environment key 3"),
    ),
    "groq": (
        ("GROQ_API_KEY", "Groq environment key 1"),
        ("GROQ_API_KEY_2", "Groq environment key 2"),
        ("GROQ_API_KEY_3", "Groq environment key 3"),
    ),
}
PROVIDER_ENV_DEFAULT_MODELS = {
    "cerebras": "gpt-oss-120b",
    "groq": "openai/gpt-oss-120b",
}
IST = ZoneInfo("Asia/Kolkata")
QUICK_UNAVAILABLE_COOLDOWN_SECONDS = 300

_rotation_lock = RLock()
_current_key_idx = 0
_provider_key_indices: dict[tuple[str, str, str], int] = {}
_quick_unavailable_until = 0.0


class QuickModelUnavailableError(RuntimeError):
    """Raised when every active key in a Quick Thinking pool is unavailable."""


@dataclass(frozen=True)
class APIKeyRecord:
    id: str
    secret: str
    label: str
    fingerprint: str
    masked_key: str
    provider: str = "google"
    model: str = "gemini-2.5-flash"
    mode: str = "quick"
    rotation_order: int = 0
    base_url: str | None = None


# Provider-neutral name for callers that do not need the legacy Gemini term.
ProviderKeyRecord = APIKeyRecord


def _env_key_values() -> list[tuple[str, str, str]]:
    """Return non-empty legacy keys as ``(env_name, label, secret)`` tuples."""
    result = []
    for index, (env_name, field_name) in enumerate(KEY_ENV_FIELDS, start=1):
        secret = str(getattr(settings, field_name, "") or "").strip()
        if secret:
            result.append((env_name, f"Environment key {index}", secret))
    return result


def _provider_env_key_values(provider: str) -> list[tuple[str, str, str]]:
    """Return optional provider-specific environment keys.

    Google keeps using the existing settings-backed names.  Other providers
    are intentionally read by conventional environment names so this phase
    does not require provider SDKs or changes to the global Settings model.
    """

    normalized = normalize_provider(provider)
    if normalized == "google":
        return _env_key_values()

    result = []
    for env_name, label in PROVIDER_ENV_FIELDS.get(normalized, ()):
        secret = str(os.getenv(env_name, "") or "").strip()
        if secret:
            result.append((env_name, label, secret))
    return result


def normalize_provider(provider: str) -> str:
    normalized = str(provider or "").strip().lower()
    if not normalized:
        raise ValueError("Provider is required.")
    return normalized


def normalize_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized not in {"quick", "deep"}:
        raise ValueError("Mode must be 'quick' or 'deep'.")
    return normalized


def _pool_key(provider: str, model: str, mode: str) -> tuple[str, str, str]:
    return normalize_provider(provider), str(model or "").strip(), normalize_mode(mode)


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


def _database_provider_key_records(
    provider: str,
    model: str,
    mode: str,
) -> list[APIKeyRecord]:
    """Load active keys from the additive provider-neutral table."""

    provider, model, mode = _pool_key(provider, model, mode)
    db = SessionLocal()
    try:
        rows = (
            db.query(db_models.ProviderAPIKey)
            .filter(
                db_models.ProviderAPIKey.provider == provider,
                db_models.ProviderAPIKey.model == model,
                db_models.ProviderAPIKey.mode == mode,
                db_models.ProviderAPIKey.is_active.is_(True),
            )
            .order_by(
                db_models.ProviderAPIKey.rotation_order.asc(),
                db_models.ProviderAPIKey.created_at.asc(),
            )
            .all()
        )
        records = []
        for row in rows:
            try:
                secret = _decrypt_api_key(row.encrypted_key)
            except RuntimeError:
                logger.error("Skipping provider API key %s because it cannot be decrypted.", row.id)
                continue
            records.append(
                APIKeyRecord(
                    id=row.id,
                    secret=secret,
                    label=row.label,
                    fingerprint=row.fingerprint,
                    masked_key=row.masked_key,
                    provider=row.provider,
                    model=row.model,
                    mode=row.mode,
                    rotation_order=row.rotation_order,
                    base_url=getattr(row, "base_url", None),
                )
            )
        return records
    finally:
        db.close()


def _legacy_provider_key_records(
    provider: str,
    model: str,
    mode: str,
) -> list[APIKeyRecord]:
    """Expose legacy Gemini rows through the provider-neutral contract."""

    provider, model, mode = _pool_key(provider, model, mode)
    if provider != "google":
        return []
    if model != "gemini-2.5-flash" or mode != "quick":
        return []
    return [
        APIKeyRecord(
            id=record.id,
            secret=record.secret,
            label=record.label,
            fingerprint=record.fingerprint,
            masked_key=record.masked_key,
            provider=provider,
            model=model,
            mode=mode,
            rotation_order=index,
        )
        for index, record in enumerate(_database_key_records())
    ]


def get_active_provider_key_records(
    provider: str,
    model: str,
    mode: str = "quick",
) -> list[APIKeyRecord]:
    """Return the active keys for one provider/model/mode pool.

    New provider-neutral rows are combined with legacy Google rows during the
    migration window.  Fingerprint de-duplication prevents a key present in
    both tables from receiving duplicate attempts.
    """

    provider, model, mode = _pool_key(provider, model, mode)
    records: list[APIKeyRecord] = []
    seen_fingerprints: set[str] = set()

    if encryption_is_configured():
        candidates = _database_provider_key_records(provider, model, mode)
        if provider == "google":
            candidates.extend(_legacy_provider_key_records(provider, model, mode))
    else:
        candidates = [
            APIKeyRecord(
                id=f"env-{provider}-{index}",
                secret=secret,
                label=label,
                fingerprint=fingerprint_api_key(secret),
                masked_key=mask_api_key(secret),
                provider=provider,
                model=model,
                mode=mode,
                rotation_order=index,
            )
            for index, (_env_name, label, secret) in enumerate(
                _provider_env_key_values(provider),
                start=1,
            )
        ]

    for record in candidates:
        if record.fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(record.fingerprint)
        records.append(record)
    return sorted(records, key=lambda item: (item.rotation_order, item.label, item.id))


def get_active_provider_pools() -> dict[tuple[str, str, str], list[APIKeyRecord]]:
    """Return all configured active provider pools.

    This is read-only and intentionally does not infer providers from SDKs.
    It discovers provider-neutral rows plus legacy Google rows and groups them
    by their routing dimensions.
    """

    pools: dict[tuple[str, str, str], list[APIKeyRecord]] = {}
    db = SessionLocal()
    try:
        if encryption_is_configured():
            rows = db.query(db_models.ProviderAPIKey).filter(db_models.ProviderAPIKey.is_active.is_(True)).all()
            pool_keys = {(row.provider, row.model, row.mode) for row in rows}
        else:
            rows = []
            pool_keys = set()
    finally:
        db.close()

    for provider, model, mode in pool_keys:
        pools[(provider, model, mode)] = get_active_provider_key_records(provider, model, mode)

    if encryption_is_configured() and _database_key_records():
        legacy_pool = ("google", "gemini-2.5-flash", "quick")
        pools[legacy_pool] = get_active_provider_key_records(*legacy_pool)
    elif not encryption_is_configured():
        env_models = {
            "google": "gemini-2.5-flash",
            **PROVIDER_ENV_DEFAULT_MODELS,
        }
        for provider, model in env_models.items():
            if _provider_env_key_values(provider):
                pools[(provider, model, "quick")] = get_active_provider_key_records(
                    provider,
                    model,
                    "quick",
                )
    return pools


def initialize_provider_key_store(
    provider_models: dict[str, str] | None = None,
    mode: str = "quick",
) -> int:
    """Import provider-specific environment keys into additive storage.

    Existing rows are never updated or deleted.  Callers supply the model
    mapping because model identifiers belong to the integration layer, not to
    key storage.  This function is deliberately separate from
    ``initialize_key_store`` so the legacy startup path remains unchanged.
    """

    if not encryption_is_configured():
        logger.warning(
            "API_KEY_ENCRYPTION_KEY is not configured; provider environment "
            "keys will remain process-local."
        )
        return 0

    normalized_mode = normalize_mode(mode)
    provider_models = provider_models or {}
    imported = 0
    db = SessionLocal()
    try:
        for provider, model in provider_models.items():
            normalized_provider = normalize_provider(provider)
            normalized_model = str(model or "").strip()
            if not normalized_model:
                raise ValueError(f"A model is required for provider {normalized_provider}.")
            for order, (_env_name, label, secret) in enumerate(
                _provider_env_key_values(normalized_provider)
            ):
                fingerprint = fingerprint_api_key(secret)
                existing = (
                    db.query(db_models.ProviderAPIKey)
                    .filter(
                        db_models.ProviderAPIKey.provider == normalized_provider,
                        db_models.ProviderAPIKey.fingerprint == fingerprint,
                    )
                    .first()
                )
                if existing is not None:
                    continue
                db.add(
                    db_models.ProviderAPIKey(
                        provider=normalized_provider,
                        model=normalized_model,
                        mode=normalized_mode,
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
            logger.info("Imported %d provider API key(s) into encrypted storage.", imported)
        return imported
    except Exception:
        db.rollback()
        logger.exception("Could not initialize provider-neutral API key storage.")
        return 0
    finally:
        db.close()


def get_current_provider_key_record(
    provider: str,
    model: str,
    mode: str = "quick",
) -> APIKeyRecord | None:
    """Return the current key for one independent provider pool."""

    pool_key = _pool_key(provider, model, mode)
    records = get_active_provider_key_records(*pool_key)
    if not records:
        logger.error("No active %s provider keys configured for %s/%s.", *pool_key)
        return None
    with _rotation_lock:
        current_index = _provider_key_indices.get(pool_key, 0) % len(records)
        _provider_key_indices[pool_key] = current_index
        return records[current_index]


def rotate_provider_key(provider: str, model: str, mode: str = "quick") -> bool:
    """Advance one provider pool without affecting any other pool."""

    pool_key = _pool_key(provider, model, mode)
    records = get_active_provider_key_records(*pool_key)
    if len(records) <= 1:
        return False
    with _rotation_lock:
        current_index = _provider_key_indices.get(pool_key, 0) % len(records)
        next_index = current_index + 1
        if next_index >= len(records):
            _provider_key_indices[pool_key] = 0
            logger.warning("All active %s keys exhausted; wrapped to the first key.", pool_key[0])
            return False
        _provider_key_indices[pool_key] = next_index
        logger.info(
            "Rotated %s/%s/%s provider key to position #%d.",
            pool_key[0],
            pool_key[1],
            pool_key[2],
            next_index + 1,
        )
        return True


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


def record_provider_key_attempt(
    key_id: str,
    provider: str,
    model: str,
    mode: str,
    outcome: str,
    error: Exception | str | None = None,
) -> None:
    """Record one provider-neutral attempt in minute and IST-day buckets."""

    if not key_id or key_id.startswith("env-") or not encryption_is_configured():
        return
    if outcome not in {"success", "failure", "quota"}:
        raise ValueError(f"Unsupported provider outcome: {outcome}")

    provider, model, mode = _pool_key(provider, model, mode)
    minute_start, day_start = _bucket_starts()
    db = SessionLocal()
    try:
        key = db.query(db_models.ProviderAPIKey).filter(
            db_models.ProviderAPIKey.id == key_id,
            db_models.ProviderAPIKey.provider == provider,
            db_models.ProviderAPIKey.mode == mode,
        ).first()
        if key is None:
            # Legacy Gemini rows are exposed to routing as provider-neutral
            # Google records, but their usage belongs in the legacy table that
            # the admin usage endpoint also aggregates.
            if provider == "google" and mode == "quick":
                record_provider_attempt(key_id, model, outcome, error)
            return
        for bucket_type, bucket_start in (("minute", minute_start), ("day", day_start)):
            usage = (
                db.query(db_models.ProviderAPIKeyUsage)
                .filter(
                    db_models.ProviderAPIKeyUsage.provider_key_id == key_id,
                    db_models.ProviderAPIKeyUsage.provider == provider,
                    db_models.ProviderAPIKeyUsage.model == model,
                    db_models.ProviderAPIKeyUsage.mode == mode,
                    db_models.ProviderAPIKeyUsage.bucket_type == bucket_type,
                    db_models.ProviderAPIKeyUsage.bucket_start == bucket_start,
                )
                .with_for_update()
                .first()
            )
            if usage is None:
                usage = db_models.ProviderAPIKeyUsage(
                    provider_key_id=key_id,
                    provider=provider,
                    model=model,
                    mode=mode,
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
        logger.warning("Concurrent provider usage bucket update was skipped for key %s.", key_id)
    except Exception:
        db.rollback()
        logger.exception(
            "Could not record provider usage for %s/%s key %s.",
            provider,
            model,
            key_id,
        )
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
        "Quick Thinking quota exhausted on all active provider keys. "
        "Quick Thinking unavailable for %ss.",
        QUICK_UNAVAILABLE_COOLDOWN_SECONDS,
    )


def clear_quick_temporarily_unavailable() -> None:
    global _quick_unavailable_until
    _quick_unavailable_until = 0.0

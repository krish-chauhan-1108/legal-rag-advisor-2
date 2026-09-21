from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import key_manager
import models.db_models as db_models
from models.schemas import AdminAPIKeyCreate, AdminAPIKeyResponse, AdminAPIKeyUpdate, AdminUsageRow


@pytest.fixture()
def provider_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_models.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(key_manager, "SessionLocal", session_factory)
    monkeypatch.setattr(key_manager.settings, "api_key_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(key_manager, "_provider_key_indices", {})
    return session_factory


def _add_provider_key(session_factory, *, provider, model, mode, label, secret, order):
    db = session_factory()
    try:
        row = db_models.ProviderAPIKey(
            provider=provider,
            model=model,
            mode=mode,
            label=label,
            encrypted_key=key_manager.encrypt_api_key(secret),
            fingerprint=key_manager.fingerprint_api_key(secret),
            masked_key=key_manager.mask_api_key(secret),
            is_active=True,
            rotation_order=order,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def test_admin_schemas_add_provider_fields_without_breaking_legacy_payloads():
    created = AdminAPIKeyCreate(label="legacy", api_key="x" * 24)
    assert created.provider == "google"
    assert created.model == "gemini-2.5-flash"
    assert created.mode == "quick"

    updated = AdminAPIKeyUpdate(provider="cerebras", model="gpt-oss-120b", mode="quick")
    assert updated.provider == "cerebras"
    assert updated.model == "gpt-oss-120b"

    response = AdminAPIKeyResponse(
        id="key-1",
        label="legacy",
        fingerprint="f" * 64,
        masked_key="****1234",
        is_active=True,
        rotation_order=0,
        created_at="2026-09-22T00:00:00",
        updated_at="2026-09-22T00:00:00",
    )
    usage = AdminUsageRow(
        api_key_id="key-1",
        label="legacy",
        masked_key="****1234",
        model="gemini-2.5-flash",
        minute={"total_requests": 1},
        day={},
        all_time={},
    )
    assert response.provider == "google"
    assert usage.provider == "google"
    assert usage.mode == "quick"


def test_provider_pools_rotate_independently(provider_db):
    groq_first = _add_provider_key(
        provider_db,
        provider="groq",
        model="openai/gpt-oss-120b",
        mode="quick",
        label="Groq one",
        secret="g" * 32,
        order=0,
    )
    _add_provider_key(
        provider_db,
        provider="groq",
        model="openai/gpt-oss-120b",
        mode="quick",
        label="Groq two",
        secret="h" * 32,
        order=1,
    )
    _add_provider_key(
        provider_db,
        provider="cerebras",
        model="gpt-oss-120b",
        mode="quick",
        label="Cerebras one",
        secret="c" * 32,
        order=0,
    )

    first = key_manager.get_current_provider_key_record("groq", "openai/gpt-oss-120b", "quick")
    assert first is not None
    assert first.id == groq_first
    assert key_manager.rotate_provider_key("groq", "openai/gpt-oss-120b", "quick") is True
    second = key_manager.get_current_provider_key_record("groq", "openai/gpt-oss-120b", "quick")
    assert second is not None
    assert second.id != first.id

    # Rotating Groq does not move the Cerebras cursor.
    cerebras = key_manager.get_current_provider_key_record("cerebras", "gpt-oss-120b", "quick")
    assert cerebras is not None
    assert cerebras.label == "Cerebras one"


def test_legacy_gemini_rows_are_exposed_through_provider_contract(provider_db):
    db = provider_db()
    try:
        row = db_models.GeminiAPIKey(
            label="legacy Google",
            encrypted_key=key_manager.encrypt_api_key("k" * 32),
            fingerprint=key_manager.fingerprint_api_key("k" * 32),
            masked_key="kkkk...kkkk",
            is_active=True,
            rotation_order=0,
        )
        db.add(row)
        db.commit()
    finally:
        db.close()

    records = key_manager.get_active_provider_key_records(
        "google",
        "gemini-2.5-flash",
        "quick",
    )
    assert len(records) == 1
    assert records[0].provider == "google"
    assert records[0].mode == "quick"
    assert records[0].secret == "k" * 32


def test_provider_usage_records_minute_and_ist_day_buckets(provider_db, monkeypatch):
    key_id = _add_provider_key(
        provider_db,
        provider="groq",
        model="openai/gpt-oss-120b",
        mode="quick",
        label="Groq",
        secret="q" * 32,
        order=0,
    )
    minute_start = datetime(2026, 9, 22, 12, 34)
    day_start = datetime(2026, 9, 22)
    monkeypatch.setattr(key_manager, "_bucket_starts", lambda: (minute_start, day_start))

    key_manager.record_provider_key_attempt(
        key_id,
        "groq",
        "openai/gpt-oss-120b",
        "quick",
        "success",
    )
    key_manager.record_provider_key_attempt(
        key_id,
        "groq",
        "openai/gpt-oss-120b",
        "quick",
        "quota",
        error="HTTP 429",
    )

    db = provider_db()
    try:
        rows = db.query(db_models.ProviderAPIKeyUsage).order_by(
            db_models.ProviderAPIKeyUsage.bucket_type.asc()
        ).all()
        assert len(rows) == 2
        assert {row.bucket_type for row in rows} == {"minute", "day"}
        for row in rows:
            assert row.provider == "groq"
            assert row.model == "openai/gpt-oss-120b"
            assert row.mode == "quick"
            assert row.total_requests == 2
            assert row.successful_requests == 1
            assert row.failed_requests == 1
            assert row.quota_failures == 1
    finally:
        db.close()


def test_invalid_mode_is_rejected(provider_db):
    with pytest.raises(ValueError, match="Mode must be"):
        key_manager.get_active_provider_key_records("groq", "gpt-oss-120b", "sideways")

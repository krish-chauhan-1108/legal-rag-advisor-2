from datetime import datetime

import main
import models.db_models as db_models
from cryptography.fernet import Fernet
from models.schemas import AdminAPIKeyCreate, AdminAPIKeyUpdate
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _session(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_models.Base.metadata.create_all(engine)
    monkeypatch.setattr(main.settings, "api_key_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(main, "_require_encrypted_key_store", lambda: None)
    return sessionmaker(bind=engine)()


def test_admin_key_crud_uses_provider_table(monkeypatch):
    db = _session(monkeypatch)
    created = main.create_admin_key(
        AdminAPIKeyCreate(
            label="Groq",
            api_key="g" * 32,
            provider="Groq",
            model="openai/gpt-oss-120b",
            mode="quick",
        ),
        _admin_email="admin@example.com",
        db=db,
    )

    assert created["provider"] == "groq"
    assert created["model"] == "openai/gpt-oss-120b"
    assert created["mode"] == "quick"
    assert db.query(db_models.ProviderAPIKey).count() == 1
    assert db.query(db_models.GeminiAPIKey).count() == 0

    updated = main.update_admin_key(
        created["id"],
        AdminAPIKeyUpdate(label="Groq updated", mode="deep"),
        _admin_email="admin@example.com",
        db=db,
    )
    assert updated["label"] == "Groq updated"
    assert updated["mode"] == "deep"

    listed = main.list_admin_keys(_admin_email="admin@example.com", db=db)
    assert listed[0]["provider"] == "groq"

    main.delete_admin_key(created["id"], _admin_email="admin@example.com", db=db)
    assert db.query(db_models.ProviderAPIKey).count() == 0
    db.close()


def test_admin_usage_combines_provider_and_legacy_rows(monkeypatch):
    db = _session(monkeypatch)
    minute = datetime(2026, 9, 22, 12, 34)
    day = datetime(2026, 9, 22)
    monkeypatch.setattr(main, "_bucket_starts", lambda: (minute, day))

    provider = db_models.ProviderAPIKey(
        provider="groq",
        model="openai/gpt-oss-120b",
        mode="quick",
        label="Groq",
        encrypted_key="unused",
        fingerprint="p" * 64,
        masked_key="****prov",
        is_active=True,
        rotation_order=0,
    )
    legacy = db_models.GeminiAPIKey(
        label="Legacy",
        encrypted_key="unused",
        fingerprint="l" * 64,
        masked_key="****legacy",
        is_active=True,
        rotation_order=1,
    )
    db.add_all([provider, legacy])
    db.commit()
    db.add(db_models.ProviderAPIKeyUsage(
        provider_key_id=provider.id,
        provider="groq",
        model=provider.model,
        mode="quick",
        bucket_type="minute",
        bucket_start=minute,
        total_requests=2,
        successful_requests=1,
        failed_requests=1,
        quota_failures=1,
    ))
    db.add(db_models.GeminiAPIKeyUsage(
        api_key_id=legacy.id,
        model="gemini-2.5-flash",
        bucket_type="day",
        bucket_start=day,
        total_requests=3,
        successful_requests=3,
        failed_requests=0,
        quota_failures=0,
    ))
    db.commit()

    result = main.admin_usage(_admin_email="admin@example.com", db=db)
    provider_row = next(row for row in result["rows"] if row["api_key_id"] == provider.id)
    legacy_row = next(row for row in result["rows"] if row["api_key_id"] == legacy.id and row["model"] == "gemini-2.5-flash")
    assert provider_row["provider"] == "groq"
    assert provider_row["minute"]["total_requests"] == 2
    assert legacy_row["provider"] == "google"
    assert legacy_row["day"]["total_requests"] == 3
    db.close()

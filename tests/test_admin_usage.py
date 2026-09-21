from datetime import datetime
from types import SimpleNamespace

import main
import models.db_models as db_models


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows


class _Database:
    def __init__(self, keys, usage_rows):
        self.keys = keys
        self.usage_rows = usage_rows

    def query(self, model):
        if model is db_models.ProviderAPIKey:
            return _Query([])
        if model is db_models.ProviderAPIKeyUsage:
            return _Query([])
        if model is db_models.GeminiAPIKey:
            return _Query(self.keys)
        if model is db_models.GeminiAPIKeyUsage:
            return _Query(self.usage_rows)
        raise AssertionError(f"Unexpected query model: {model}")


def test_admin_usage_does_not_depend_on_removed_embedding_setting(monkeypatch) -> None:
    key = SimpleNamespace(
        id="key-1",
        label="Primary",
        masked_key="****1234",
    )
    minute_start = datetime(2026, 9, 22, 12, 34)
    day_start = datetime(2026, 9, 22)

    monkeypatch.setattr(main, "_require_encrypted_key_store", lambda: None)
    monkeypatch.setattr(main, "_bucket_starts", lambda: (minute_start, day_start))

    result = main.admin_usage(
        _admin_email="admin@example.com",
        db=_Database([key], []),
    )

    assert {row["model"] for row in result["rows"]} == {
        "gemini-2.5-flash",
        main.settings.llm_model,
    }

from datetime import datetime
from types import SimpleNamespace

import main
import models.db_models as db_models


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows


class _Database:
    def __init__(self, sessions):
        self.sessions = sessions

    def query(self, model):
        if model is db_models.ChatSession:
            return _Query(self.sessions)
        raise AssertionError("Chat summaries must not load message rows")


def test_chat_listing_returns_summaries_without_loading_messages() -> None:
    timestamp = datetime(2026, 9, 22, 12, 34)
    session = SimpleNamespace(
        id="chat-1",
        title="A saved question",
        user_email="admin@example.com",
        created_at=timestamp,
        updated_at=timestamp,
    )

    result = main.get_chats(user_email="admin@example.com", db=_Database([session]))

    assert result == [{
        "id": "chat-1",
        "title": "A saved question",
        "user_email": "admin@example.com",
        "created_at": timestamp.isoformat(),
        "updated_at": timestamp.isoformat(),
    }]

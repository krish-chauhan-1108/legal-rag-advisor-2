import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
import models.db_models as db_models
from llm import chain
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


def _row(role, index, *, content="", structured=None, sources=None, session_id="chat-1"):
    return SimpleNamespace(
        id=f"message-{index}",
        role=role,
        content=content,
        structured_content=json.dumps(structured) if structured is not None else None,
        sources=json.dumps(sources) if sources is not None else None,
        created_at=datetime(2026, 1, 1) + timedelta(minutes=index),
    )


def test_history_is_chronological_capped_and_excludes_statutory_quotes():
    rows = []
    for index in range(40):
        rows.append(_row("user" if index % 2 == 0 else "assistant", index, content=f"message {index}"))
    rows[-1] = _row(
        "assistant",
        39,
        structured={
            "general_analysis": "The answer is available.",
            "applicable_laws": [{
                "act": "Bharatiya Nyaya Sanhita, 2023",
                "code": "BNS",
                "section": "1",
                "quote": "VERIFIED STATUTORY QUOTE " * 100,
                "exact_text": "VERIFIED EXACT TEXT " * 100,
                "explanation": "Short explanation.",
            }],
        },
        sources=[{
            "act": "Bharatiya Nyaya Sanhita, 2023",
            "code": "BNS",
            "section": "1",
            "content": "LARGE SOURCE CONTENT " * 100,
            "exact_text": "LARGE EXACT TEXT " * 100,
        }],
    )

    history = main._build_conversation_history(rows)

    assert len(history) == 32
    assert [item["role"] for item in history[:2]] == ["user", "assistant"]
    assert history[0]["content"] == "message 8"
    serialized = json.dumps(history)
    assert "VERIFIED STATUTORY QUOTE" not in serialized
    assert "VERIFIED EXACT TEXT" not in serialized
    assert "LARGE SOURCE CONTENT" not in serialized
    assert "LARGE EXACT TEXT" not in serialized
    assert "Bharatiya Nyaya Sanhita, 2023" in serialized


def test_history_context_caps_each_message_and_total_context():
    rows = [
        _row("user", index, content="x" * 10_000)
        for index in range(40)
    ]

    history = main._build_conversation_history(rows)
    total_chars = sum(len(item["content"]) for item in history)

    assert len(history) <= 32
    assert all(len(item["content"]) <= main.HISTORY_MESSAGE_CHAR_LIMIT for item in history)
    assert total_chars <= main.HISTORY_CONTEXT_CHAR_LIMIT
    assert history[-1]["content"].startswith("x")


def test_history_requires_chat_ownership():
    engine = create_engine("sqlite:///:memory:")
    db_models.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    db.add_all([
        db_models.ChatSession(id="owned", user_email="owner@example.com", title="Owned"),
        db_models.ChatSession(id="other", user_email="other@example.com", title="Other"),
    ])
    db.add_all([
        db_models.ChatMessage(session_id="owned", role="user", content="owner context"),
        db_models.ChatMessage(session_id="other", role="user", content="private context"),
    ])
    db.commit()

    assert main._load_conversation_history(db, "owned", "owner@example.com")[0]["content"] == "owner context"
    assert main._load_conversation_history(db, "other", "owner@example.com") == []


def test_pipeline_message_construction_preserves_history_roles():
    messages = chain._build_prompt_messages(
        "newest question",
        None,
        [
            {"role": "user", "content": "earlier question"},
            {"role": "assistant", "content": "earlier answer"},
        ],
    )

    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert isinstance(messages[2], AIMessage)
    assert isinstance(messages[3], HumanMessage)
    assert messages[1].content == "earlier question"
    assert messages[2].content == "earlier answer"
    assert "newest question" in messages[3].content


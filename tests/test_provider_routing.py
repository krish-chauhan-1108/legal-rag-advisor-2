import asyncio
import json
from langchain_core.messages import HumanMessage, SystemMessage

from key_manager import APIKeyRecord
from llm import chain


def _record(identifier, provider, model, order=0):
    return APIKeyRecord(
        id=identifier,
        secret="s" * 32,
        label=identifier,
        fingerprint=identifier,
        masked_key="****",
        provider=provider,
        model=model,
        mode="quick",
        rotation_order=order,
    )


def test_quick_routes_prioritize_gpt_oss_then_llama(monkeypatch):
    monkeypatch.setattr(
        chain,
        "get_active_provider_pools",
        lambda: {
            ("cerebras", "llama3.1-8b", "quick"): [_record("llama", "cerebras", "llama3.1-8b")],
            ("groq", "openai/gpt-oss-120b", "quick"): [_record("oss", "groq", "openai/gpt-oss-120b")],
            ("nvidia", "nvidia/nemotron-3.5-lightning-30b-a3b", "quick"): [_record("nemotron", "nvidia", "nvidia/nemotron-3.5-lightning-30b-a3b")],
        },
    )

    assert [record.id for record in chain._quick_routes()] == ["oss", "nemotron", "llama"]


def test_groq_json_mode_handles_wrapped_structured_content(monkeypatch):
    record = _record("groq-key", "groq", "openai/gpt-oss-120b")
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            payload = {"is_conversational": False, "general_analysis": "A concise answer."}
            return {
                "choices": [{
                    "message": {
                        "content": "Here is the requested JSON:\n" + json.dumps(payload),
                    }
                }]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers, json):
            captured.update(json)
            return FakeResponse()

    monkeypatch.setattr(chain.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(chain._invoke_openai_compatible(
        record,
        [SystemMessage(content="Return valid JSON."), HumanMessage(content="Explain this.")],
        timeout=2,
    ))

    assert result.general_analysis == "A concise answer."
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["include_reasoning"] is False


def test_provider_payload_normalizes_nullable_law_fields(monkeypatch):
    record = _record("groq-key", "groq", "openai/gpt-oss-120b")

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "is_conversational": False,
                            "applicable_laws": [{
                                "act": "Bharatiya Nyaya Sanhita, 2023",
                                "code": "BNS",
                                "section": 1,
                                "quote": None,
                                "explanation": "Defines the short title and commencement.",
                                "verified": None,
                            }],
                        }),
                    }
                }]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(chain.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(chain._invoke_openai_compatible(
        record,
        [SystemMessage(content="Return valid JSON."), HumanMessage(content="Explain this.")],
        timeout=2,
    ))

    assert result.applicable_laws[0].section == "1"
    assert result.applicable_laws[0].quote == ""
    assert result.applicable_laws[0].verified is False

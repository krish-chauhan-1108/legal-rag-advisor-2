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

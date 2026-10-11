import asyncio
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, SystemMessage

from legal_sources import get_registry
from llm import chain
from models.schemas import ApplicableLaw, StructuredAnalysis


def test_direct_section_prompt_uses_verified_act_text_and_ignores_history():
    record = get_registry().lookup(code="BNS", section="77")

    messages = chain._build_prompt_messages(
        "explain bns 77",
        None,
        [{"role": "assistant", "content": "BNS 77 is about arrest without a warrant."}],
        requested_law=record,
    )

    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert "sole authority" in messages[0].content
    assert isinstance(messages[1], HumanMessage)
    assert "VERIFIED CODE: BNS" in messages[1].content
    assert "VERIFIED SECTION: 77" in messages[1].content
    assert record.exact_text in messages[1].content
    assert "arrest without a warrant" not in messages[1].content


def test_explicit_subsection_reference_is_resolved():
    record = chain._requested_law_record("explain BNS 1(1)", get_registry())

    assert record is not None
    assert record.code == "BNS"
    assert record.section == "1(1)"


def test_pipeline_rejects_cross_act_answer_instead_of_relabelling_it(monkeypatch):
    captured = {}

    async def fake_model(messages, deadline):
        captured["messages"] = messages
        return (
            StructuredAnalysis(
                general_analysis=(
                    "BNS Section 77 allows police to arrest without a warrant."
                ),
                applicable_laws=[
                    ApplicableLaw(
                        code="BNSS",
                        section="77",
                        explanation="A deliberately mismatched model citation.",
                    )
                ],
            ),
            "fake-provider:test-model",
        )

    monkeypatch.setattr(chain, "_run_quick_provider_pipeline", fake_model)

    response = asyncio.run(
        chain.run_analysis_pipeline(
            "explain bns 77",
            conversation_history=[
                {"role": "assistant", "content": "BNS 77 concerns arrest."}
            ],
        )
    )

    assert "VERIFIED CODE: BNS" in captured["messages"][1].content
    assert "couldn't reliably match" in response.analysis.general_analysis
    assert "arrest without a warrant" not in response.analysis.general_analysis
    assert [(law.code, law.section) for law in response.analysis.applicable_laws] == [
        ("BNS", "77")
    ]
    assert [(source.code, source.section) for source in response.sources] == [
        ("BNS", "77")
    ]
    assert get_registry().lookup(code="BNS", section="77").exact_text in response.analysis.general_analysis


def test_pipeline_fails_closed_on_unsupported_bns_163_medical_exam_claim(monkeypatch):
    async def fake_model(messages, deadline):
        return (
            StructuredAnalysis(
                general_analysis=(
                    "Section 163 BNS gives a person a right to a medical examination "
                    "after police suspect physical injury."
                ),
                applicable_laws=[ApplicableLaw(code="BNS", section="163")],
            ),
            "quick:groq:model-a",
        )

    async def reject_explanation(record, explanation, generation_model):
        assert record.code == "BNS" and record.section == "163"
        assert "medical examination" in explanation
        return False

    monkeypatch.setattr(chain, "_run_quick_provider_pipeline", fake_model)
    monkeypatch.setattr(chain, "_independent_section_verification", reject_explanation)
    response = asyncio.run(chain.run_analysis_pipeline("explain BNS 163"))

    exact_text = get_registry().lookup(code="BNS", section="163").exact_text
    assert response.analysis.general_analysis.endswith(exact_text)
    assert "medical examination" not in response.analysis.general_analysis
    assert response.sources[0].exact_text == exact_text


def test_pipeline_fails_closed_when_bnss_77_is_returned_for_bns_77(monkeypatch):
    async def fake_model(messages, deadline):
        return (
            StructuredAnalysis(
                general_analysis="BNSS Section 77 concerns a police procedure.",
                applicable_laws=[ApplicableLaw(code="BNSS", section="77")],
            ),
            "quick:groq:model-a",
        )

    async def accept_explanation(record, explanation, generation_model):
        return True

    monkeypatch.setattr(chain, "_run_quick_provider_pipeline", fake_model)
    monkeypatch.setattr(chain, "_independent_section_verification", accept_explanation)
    response = asyncio.run(chain.run_analysis_pipeline("explain BNS 77"))

    exact_text = get_registry().lookup(code="BNS", section="77").exact_text
    assert response.analysis.general_analysis.endswith(exact_text)
    assert "BNSS Section 77" not in response.analysis.general_analysis
    assert [(law.code, law.section) for law in response.analysis.applicable_laws] == [("BNS", "77")]


def test_section_verifier_accepts_only_strict_boolean_response(monkeypatch):
    async def invoke(_messages):
        return {"supported": True}

    class FakeLLM:
        def with_structured_output(self, _schema):
            return SimpleNamespace(ainvoke=invoke)

    monkeypatch.setattr(
        chain,
        "_quick_routes",
        lambda: [SimpleNamespace(provider="google", model="verifier", secret="key")],
    )
    monkeypatch.setattr(chain, "_get_llm", lambda *args, **kwargs: (FakeLLM(), "verifier", "key"))
    record = get_registry().lookup(code="BNS", section="163")

    assert asyncio.run(
        chain._independent_section_verification(record, "A supported explanation", "quick:groq:model")
    ) is True


def test_section_verifier_rejects_unsupported_and_malformed_responses(monkeypatch):
    outcomes = iter(({"supported": False}, {"supported": "yes"}))

    async def invoke(_messages):
        return next(outcomes)

    class FakeLLM:
        def with_structured_output(self, _schema):
            return SimpleNamespace(ainvoke=invoke)

    monkeypatch.setattr(
        chain,
        "_quick_routes",
        lambda: [SimpleNamespace(provider="google", model="verifier", secret="key")],
    )
    monkeypatch.setattr(chain, "_get_llm", lambda *args, **kwargs: (FakeLLM(), "verifier", "key"))
    record = get_registry().lookup(code="BNS", section="163")

    assert asyncio.run(
        chain._independent_section_verification(record, "Unsupported", "quick:groq:model")
    ) is False
    assert asyncio.run(
        chain._independent_section_verification(record, "Malformed", "quick:groq:model")
    ) is False


def test_section_verifier_fails_closed_on_timeout(monkeypatch):
    async def invoke(_messages):
        return {"supported": True}

    class FakeLLM:
        def with_structured_output(self, _schema):
            return SimpleNamespace(ainvoke=invoke)

    async def timed_out(awaitable, **_kwargs):
        awaitable.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(
        chain,
        "_quick_routes",
        lambda: [SimpleNamespace(provider="google", model="verifier", secret="key")],
    )
    monkeypatch.setattr(chain, "_get_llm", lambda *args, **kwargs: (FakeLLM(), "verifier", "key"))
    monkeypatch.setattr(chain.asyncio, "wait_for", timed_out)
    record = get_registry().lookup(code="BNS", section="163")

    assert asyncio.run(
        chain._independent_section_verification(record, "Any explanation", "quick:groq:model")
    ) is False


def test_direct_section_auditor_receives_all_user_facing_claim_fields():
    analysis = StructuredAnalysis(
        general_analysis="Statute says X.",
        rights=["Right Y"],
        next_24_hours=["Do Z"],
        applicable_laws=[ApplicableLaw(code="BNS", section="163", explanation="Procedure W.")],
    )

    claims = chain._direct_section_claims(analysis)

    assert "general_analysis: Statute says X." in claims
    assert "rights: Right Y" in claims
    assert "next_24_hours: Do Z" in claims
    assert "citation explanation: Procedure W." in claims

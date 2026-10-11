import asyncio

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


def test_bns_163_request_is_explained_from_its_verified_text(monkeypatch):
    captured = {}

    async def fake_model(messages, deadline):
        captured["messages"] = messages
        return (
            StructuredAnalysis(
                general_analysis="BNS Section 163 concerns abetting the desertion of a member of the armed forces.",
                applicable_laws=[ApplicableLaw(code="BNS", section="163")],
            ),
            "quick:groq:model-a",
        )

    monkeypatch.setattr(chain, "_run_quick_provider_pipeline", fake_model)
    response = asyncio.run(chain.run_analysis_pipeline("explain BNS 163"))

    exact_text = get_registry().lookup(code="BNS", section="163").exact_text
    assert exact_text in captured["messages"][1].content
    assert "abetting the desertion" in response.analysis.general_analysis
    assert response.sources[0].exact_text == exact_text


def test_pipeline_rejects_bnss_77_citation_for_bns_77_request(monkeypatch):
    async def fake_model(messages, deadline):
        return (
            StructuredAnalysis(
                general_analysis="BNSS Section 77 concerns a police procedure.",
                applicable_laws=[ApplicableLaw(code="BNSS", section="77")],
            ),
            "quick:groq:model-a",
        )

    monkeypatch.setattr(chain, "_run_quick_provider_pipeline", fake_model)
    response = asyncio.run(chain.run_analysis_pipeline("explain BNS 77"))

    exact_text = get_registry().lookup(code="BNS", section="77").exact_text
    assert response.analysis.general_analysis.endswith(exact_text)
    assert "BNSS Section 77" not in response.analysis.general_analysis
    assert [(law.code, law.section) for law in response.analysis.applicable_laws] == [("BNS", "77")]

from legal_sources import get_registry
from llm.chain import _sanitize_analysis, _verify_law_candidates
from models.schemas import ApplicableLaw, StructuredAnalysis


def test_full_supported_act_coverage_is_loaded() -> None:
    registry = get_registry()

    assert len(registry) == 1062
    assert registry.lookup("BNS", "358") is not None
    assert registry.lookup("BNSS", "531") is not None
    assert registry.lookup("BSA", "170") is not None


def test_registry_validates_and_resolves_subsection() -> None:
    registry = get_registry()
    record = registry.lookup("BNS", "1", subsection="1")

    assert record is not None
    assert record.code == "BNS"
    assert record.section == "1(1)"
    assert record.exact_text == "This Act may be called the Bharatiya Nyaya Sanhita, 2023."


def test_model_quote_is_discarded_and_registry_text_is_used() -> None:
    law = ApplicableLaw(
        act="BNS",
        section="1",
        subsection="1",
        quote="A fabricated quotation.",
        exact_text="Another fabricated quotation.",
    )
    analysis = StructuredAnalysis(applicable_laws=[law])

    sources = _verify_law_candidates(analysis, get_registry())

    assert law.verified is True
    assert law.quote_status == "backend_verified"
    assert law.exact_text == sources[0].exact_text
    assert law.quote != "A fabricated quotation."
    assert "Bharatiya Nyaya Sanhita" in law.quote


def test_unknown_citation_cannot_become_verified() -> None:
    law = ApplicableLaw(code="BNS", section="999", quote="Fabricated")
    analysis = StructuredAnalysis(applicable_laws=[law])

    sources = _verify_law_candidates(analysis, get_registry())

    assert sources == []
    assert analysis.applicable_laws == []


def test_model_repetition_is_compacted_before_display() -> None:
    analysis = StructuredAnalysis(
        situation_meaning="Same same same same same same.",
        next_24_hours=["Call a lawyer now now now.", "Call a lawyer now now now."],
    )

    cleaned = _sanitize_analysis(analysis)

    assert cleaned.situation_meaning == "Same."
    assert cleaned.next_24_hours == ["Call a lawyer now."]

from legal_sources import get_registry
from llm.chain import _verify_law_candidates
from models.schemas import ApplicableLaw, StructuredAnalysis


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
    assert law.verified is False
    assert law.quote_status == "unverified"
    assert law.quote == ""
    assert law.exact_text is None

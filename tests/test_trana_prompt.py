from main import NEW_CHAT_GREETING
from llm.prompts import DIRECT_ANALYSIS_PROMPT, SYSTEM_PROMPT


def test_new_chat_greeting_is_exact_utf8_text() -> None:
    assert "\ufffd" not in NEW_CHAT_GREETING
    assert "â" not in NEW_CHAT_GREETING
    assert "Ã" not in NEW_CHAT_GREETING
    assert NEW_CHAT_GREETING == "I'm TRANA\u2014your friendly legal assistant. How can I help you today?"


def test_system_prompt_contains_original_trana_modes_and_safety_rules() -> None:
    required_phrases = (
        "expert in Indian criminal law specialising in BNS",
        "ordinary Indian families",
        "same language as the user's latest message",
        "bail is available or not",
        "next 24 hours",
        "what rights they have",
        "which court or authority handles this",
        "LAWYER LOCATOR MODE",
        "Which city or district are you in?",
        "TRANA VERIFIED LAWYER DIRECTORY",
        "FIR ANALYSIS MODE",
        "List every BNS section in the FIR",
        "flag anything misapplied or exaggerated",
        "I'm only trained to help with criminal law situations under BNS, BNSS, and BSA",
        "Never claim to be a lawyer",
        "do not invent law, section numbers, quotations, URLs, or case facts",
        "verified legal-source registry",
        "Earlier user and assistant messages",
        "valid JSON object matching the requested schema",
    )

    normalized_prompt = " ".join(SYSTEM_PROMPT.casefold().split())
    for phrase in required_phrases:
        assert " ".join(phrase.casefold().split()) in normalized_prompt


def test_prompt_language_and_section_explanations_are_adaptive() -> None:
    normalized_prompt = " ".join(SYSTEM_PROMPT.casefold().split())
    assert "do not force the same fixed set of" in normalized_prompt
    assert "explain bns/bnss/bsa section" in normalized_prompt
    assert "leave `situation_meaning`, `bail_status`, `next_24_hours`, `rights`, and `handling_authority` empty unless one is genuinely relevant" in SYSTEM_PROMPT
    assert "same language as the user's latest message" in SYSTEM_PROMPT
    assert "Respond in English by default" not in SYSTEM_PROMPT
    assert "Respond in English by default" not in DIRECT_ANALYSIS_PROMPT

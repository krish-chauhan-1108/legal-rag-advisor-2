"""Versioned legal-source registry.

The registry is intentionally small and deterministic. LLM output may identify a
candidate Act and section, but only records loaded here can become authoritative
quotes in an API response.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


_DEFAULT_CORPUS_PATH = Path(__file__).with_name("corpus.json")
_SECTION_RE = re.compile(r"(?:section|sec\.?|s\.?|article)\s*", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class LawRecord:
    """One exact, versioned legal-text record."""

    act: str
    code: str
    section: str
    subsection: str | None
    heading: str
    exact_text: str
    source_url: str
    source_version: str
    source_hash: str
    jurisdiction: str = "India"

    @property
    def citation(self) -> str:
        return f"{self.code}, Section {self.section}"


def _normalize_code(value: str | None) -> str:
    lowered = _SPACE_RE.sub(" ", (value or "").strip().lower())
    aliases = {
        "bns": "BNS",
        "bharatiya nyaya sanhita": "BNS",
        "bharatiya nyaya sanhita, 2023": "BNS",
        "bnss": "BNSS",
        "bharatiya nagarik suraksha sanhita": "BNSS",
        "bharatiya nagarik suraksha sanhita, 2023": "BNSS",
        "bsa": "BSA",
        "bharatiya sakshya adhiniyam": "BSA",
        "bharatiya sakshya adhiniyam, 2023": "BSA",
        "ica": "ICA",
        "indian contract act": "ICA",
        "indian contract act, 1872": "ICA",
    }
    return aliases.get(lowered, value.strip().upper() if value else "")


def _normalize_section(value: str | None) -> tuple[str, str | None]:
    """Return canonical section and optional subsection, e.g. ``1(1)``."""

    cleaned = _SECTION_RE.sub("", value or "")
    cleaned = cleaned.strip().replace(" ", "")
    match = re.fullmatch(r"(\d+[A-Za-z]?)(?:\(([^()]*)\))?", cleaned)
    if not match:
        return cleaned, None
    section, subsection = match.groups()
    return f"{section}({subsection})" if subsection else section, subsection


def _record_from_payload(payload: dict[str, Any]) -> LawRecord:
    exact_text = str(payload["exact_text"])
    expected_hash = hashlib.sha256(exact_text.encode("utf-8")).hexdigest()
    source_hash = str(payload.get("source_hash") or expected_hash)
    if source_hash != expected_hash:
        raise ValueError(
            f"Source hash mismatch for {payload.get('code')} Section {payload.get('section')}"
        )

    section, parsed_subsection = _normalize_section(str(payload["section"]))
    subsection = payload.get("subsection") or parsed_subsection
    return LawRecord(
        act=str(payload["act"]),
        code=_normalize_code(str(payload["code"])),
        section=section,
        subsection=str(subsection) if subsection else None,
        heading=str(payload.get("heading", "")),
        exact_text=exact_text,
        source_url=str(payload["source_url"]),
        source_version=str(payload["source_version"]),
        source_hash=source_hash,
        jurisdiction=str(payload.get("jurisdiction", "India")),
    )


class LawSourceRegistry:
    """Read-only lookup over a validated JSON corpus."""

    def __init__(self, records: Iterable[LawRecord] = ()) -> None:
        self._records: dict[tuple[str, str], LawRecord] = {}
        for record in records:
            key = (_normalize_code(record.code), _normalize_section(record.section)[0])
            if key in self._records:
                raise ValueError(f"Duplicate legal source record: {key[0]} Section {key[1]}")
            self._records[key] = record

    @classmethod
    def from_json(cls, path: str | Path = _DEFAULT_CORPUS_PATH) -> "LawSourceRegistry":
        source_path = Path(path)
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "1.0":
            raise ValueError(f"Unsupported legal corpus schema: {payload.get('schema_version')}")
        supplemental_path = source_path.with_name("contract_corpus.json")
        supplemental_records = []
        if supplemental_path.is_file():
            supplemental = json.loads(supplemental_path.read_text(encoding="utf-8"))
            if supplemental.get("schema_version") != "1.0":
                raise ValueError(f"Unsupported supplemental corpus schema: {supplemental.get('schema_version')}")
            supplemental_records = supplemental.get("records", [])
        records = [
            _record_from_payload(item)
            for item in [*payload.get("records", []), *supplemental_records]
        ]
        return cls(records)

    def lookup(
        self,
        act: str | None = None,
        section: str | None = None,
        *,
        code: str | None = None,
        subsection: str | None = None,
    ) -> LawRecord | None:
        """Look up a section using either an Act name or a short code.

        ``act`` and ``code`` are both accepted for compatibility with model
        providers that use different field names. If both are supplied, each
        normalized value is tried without mutating the caller's data.
        """

        candidate_codes = []
        for candidate in (code, act):
            normalized = _normalize_code(candidate)
            if normalized and normalized not in candidate_codes:
                candidate_codes.append(normalized)
        section_value = str(section or "").strip()
        if subsection and "(" not in section_value:
            section_value = f"{section_value}({str(subsection).strip()})"
        normalized_section, _ = _normalize_section(section_value)
        for candidate_code in candidate_codes:
            record = self._records.get((candidate_code, normalized_section))
            if record is not None:
                return record
        return None

    def __len__(self) -> int:
        return len(self._records)

    def records(self) -> tuple[LawRecord, ...]:
        return tuple(self._records.values())


_registry: LawSourceRegistry | None = None


def get_registry() -> LawSourceRegistry:
    """Return the process-wide registry, loading and validating it once."""

    global _registry
    if _registry is None:
        _registry = LawSourceRegistry.from_json()
    return _registry

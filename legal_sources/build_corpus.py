"""Build the checked-in BNS/BNSS/BSA source corpus from official PDFs.

This is a one-time maintenance tool, not part of the API request path. It
deliberately fails if a numbered section is missing so an incomplete or
misaligned corpus cannot be generated silently.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SECTION_START = re.compile(r"^\s*(\d{1,3})\s*\.\s*(?=[(\w\"“])")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

SOURCES = (
    {
        "code": "BNS",
        "act": "Bharatiya Nyaya Sanhita, 2023",
        "filename": "250883_english_01042024.pdf",
        "max_section": 358,
        "source_url": "https://www.mha.gov.in/sites/default/files/2024-04/250883_english_01042024.pdf",
    },
    {
        "code": "BNSS",
        "act": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "filename": "250884_2_english_01042024.pdf",
        "max_section": 531,
        "source_url": "https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf",
    },
    {
        "code": "BSA",
        "act": "Bharatiya Sakshya Adhiniyam, 2023",
        "filename": "250882_english_01042024_0.pdf",
        "max_section": 170,
        "source_url": "https://www.mha.gov.in/sites/default/files/2024-04/250882_english_01042024_0.pdf",
    },
)

REVIEWED_SUBSECTIONS = (
    {
        "act": "Bharatiya Nyaya Sanhita, 2023",
        "code": "BNS",
        "section": "1(1)",
        "subsection": "1",
        "heading": "Short title, commencement and application",
        "exact_text": "This Act may be called the Bharatiya Nyaya Sanhita, 2023.",
        "source_url": "https://www.mha.gov.in/sites/default/files/2024-04/250883_english_01042024.pdf",
    },
    {
        "act": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "code": "BNSS",
        "section": "1(1)",
        "subsection": "1",
        "heading": "Short title, extent and commencement",
        "exact_text": "This Act may be called the Bharatiya Nagarik Suraksha Sanhita, 2023.",
        "source_url": "https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf",
    },
    {
        "act": "Bharatiya Sakshya Adhiniyam, 2023",
        "code": "BSA",
        "section": "1(1)",
        "subsection": "1",
        "heading": "Short title, application and commencement",
        "exact_text": "This Act may be called the Bharatiya Sakshya Adhiniyam, 2023.",
        "source_url": "https://www.mha.gov.in/sites/default/files/2024-04/250882_english_01042024_0.pdf",
    },
)


def clean_line(value: str) -> str:
    value = ANSI.sub("", value)
    value = "".join(char for char in value if char in "\t\n\r" or ord(char) >= 32)
    return " ".join(value.split())


def read_lines(path: Path) -> list[str]:
    reader = PdfReader(str(path))
    lines: list[str] = []
    for page in reader.pages:
        lines.extend(clean_line(line) for line in (page.extract_text() or "").splitlines())
    return lines


def section_ranges(lines: list[str], max_section: int) -> list[tuple[int, int, int]]:
    starts: list[tuple[int, int]] = []
    cursor = -1
    for section in range(1, max_section + 1):
        found = None
        for index in range(cursor + 1, len(lines)):
            match = SECTION_START.match(lines[index])
            if match and int(match.group(1)) == section:
                found = index
                break
        if found is None:
            raise RuntimeError(f"Could not locate section {section} after line {cursor}.")
        starts.append((section, found))
        cursor = found

    ranges: list[tuple[int, int, int]] = []
    for position, (section, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else len(lines)
        ranges.append((section, start, end))
    return ranges


def is_layout_noise(line: str) -> bool:
    if not line:
        return True
    if "THE GAZETTE OF INDIA" in line or line.startswith("[Part II"):
        return True
    if line.startswith("Sec. 1]") or set(line) == {"_"}:
        return True
    if re.fullmatch(r"\d{1,4}", line):
        return True
    if any(
        marker in line
        for marker in (
            "UPLOADED BY THE MANAGER",
            "AND PUBLISHED BY THE CONTROLLER",
            "Digitally signed by",
            "DN: c=IN,",
            "postalCode=",
            "serialNumber=",
            "ou=Deputy Manager",
            "Secretary & Legislative Counsel",
            "MGIPMRND",
            "Kshitiz",
            "2.5.4.20=",
            "pseudonym=",
            "Date: 2023.",
        )
    ):
        return True
    return False


def section_text(lines: list[str], start: int, end: int, code: str, section: int) -> str:
    section_lines = lines[start:end]
    terminal_markers = {
        ("BNS", 358): ("45 of 1860.",),
        ("BNSS", 531): ("2 of 1974.", "THE FIRST SCHEDULE"),
        ("BSA", 170): ("1 of 1872.", "THE SCHEDULE"),
    }.get((code, section), ())
    if terminal_markers:
        cutoff = next(
            (
                i
                for i, line in enumerate(section_lines)
                if any(line == marker for marker in terminal_markers)
            ),
            len(section_lines),
        )
        section_lines = section_lines[:cutoff]

    text = " ".join(line for line in section_lines if not is_layout_noise(line))
    text = re.sub(r"\s+", " ", text).strip()
    match = SECTION_START.match(text)
    if match:
        text = text[match.end() :].strip()
    return text


def build_records(source: dict[str, object]) -> list[dict[str, object]]:
    upload = ROOT / "data" / "uploads" / str(source["filename"])
    if not upload.is_file():
        raise FileNotFoundError(f"Missing official source PDF: {upload}")

    lines = read_lines(upload)
    ranges = section_ranges(lines, int(source["max_section"]))
    records: list[dict[str, object]] = []
    for section, start, end in ranges:
        exact = section_text(lines, start, end, str(source["code"]), section)
        if len(exact) < 20:
            raise RuntimeError(f"Section {source['code']} {section} is unexpectedly short.")
        records.append(
            {
                "act": source["act"],
                "code": source["code"],
                "section": str(section),
                "subsection": None,
                "heading": "",
                "exact_text": exact,
                "source_url": source["source_url"],
                "source_version": "2023-12-25-gazette",
                "source_hash": hashlib.sha256(exact.encode("utf-8")).hexdigest(),
            }
        )
    return records


def main() -> None:
    records: list[dict[str, object]] = []
    for source in SOURCES:
        records.extend(build_records(source))
    for reviewed in REVIEWED_SUBSECTIONS:
        exact = str(reviewed["exact_text"])
        records.append(
            {
                **reviewed,
                "source_version": "2023-12-25-gazette",
                "source_hash": hashlib.sha256(exact.encode("utf-8")).hexdigest(),
            }
        )
    payload = {
        "schema_version": "1.0",
        "corpus_version": "2023-12-25-gazette-full-sections",
        "description": "Section-level exact text extracted from the official BNS, BNSS, and BSA gazette PDFs.",
        "records": records,
    }
    target = ROOT / "legal_sources" / "corpus.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} records to {target}")


if __name__ == "__main__":
    main()

"""
Hierarchical Legal Document Chunker for the Legal RAG Advisor.

This module implements a *structure-aware* chunking strategy tailored for
legal documents:

1.  **Section detection** — Regex patterns identify common legal headings
    (e.g., ``ARTICLE IV``, ``Section 3.2``, ``EXHIBIT A``).  When a heading
    is found the chunker avoids splitting mid-section whenever possible.

2.  **Recursive character splitting** — Within each section the text is
    split using LangChain's ``RecursiveCharacterTextSplitter`` configured
    with a *token-based* length function (via ``tiktoken``) so chunk sizes
    are measured in tokens, not characters.

3.  **Metadata enrichment** — Every resulting :class:`langchain_core.documents.Document`
    carries metadata including the originating document name, detected
    section heading, page number, chunk index, and ingestion timestamp.

Design rationale
----------------
Legal agreements rely heavily on defined terms and cross-references.  Naive
fixed-window chunking regularly breaks a clause in the middle, causing the
retriever to surface incomplete context.  By respecting section boundaries
we dramatically improve retrieval precision for clause-level questions.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings
from ingestion.parser import PageTextList
from utils.logger import get_logger

logger = get_logger(__name__)

# ─── Compile legal section heading patterns once at import time ─────────────
# These cover the vast majority of US/UK commercial agreement conventions.
SECTION_HEADING_PATTERNS: list[re.Pattern] = [
    # ARTICLE I / Article 1 / ARTICLE ONE
    re.compile(
        r"^(?:ARTICLE|Article)\s+(?:[IVXLCDM]+|\d+|[A-Z]+(?:\s+[A-Z]+)*)"
        r"(?:\s*[\.:\-–—]\s*.*)?$",
        re.MULTILINE,
    ),
    # Section 1.1 / SECTION 2 / § 3.2
    re.compile(
        r"^(?:SECTION|Section|§)\s+\d+(?:\.\d+)*"
        r"(?:\s*[\.:\-–—]\s*.*)?$",
        re.MULTILINE,
    ),
    # EXHIBIT A / Schedule 1 / Annex B
    re.compile(
        r"^(?:EXHIBIT|Exhibit|SCHEDULE|Schedule|ANNEX|Annex)\s+[A-Z0-9]+"
        r"(?:\s*[\.:\-–—]\s*.*)?$",
        re.MULTILINE,
    ),
    # RECITALS / WITNESSETH / DEFINITIONS / WHEREAS
    re.compile(
        r"^(?:RECITALS|WITNESSETH|DEFINITIONS|WHEREAS|PREAMBLE|BACKGROUND)"
        r"(?:\s*[\.:\-–—]\s*.*)?$",
        re.MULTILINE,
    ),
    # Numbered clauses: "1." / "1.1" / "(a)" / "(i)"
    re.compile(
        r"^\s*(?:\d+\.(?:\d+\.)*\s|(\([a-z]\)|\([ivx]+\))\s)",
        re.MULTILINE,
    ),
]


def _detect_section_heading(text: str) -> str:
    """
    Return the first legal section heading found in *text*, or ``"General"``.

    We return only the first match because a chunk may span multiple
    sub-clauses; the *outermost* heading is the most useful for filtering.
    """
    for pattern in SECTION_HEADING_PATTERNS:
        match = pattern.search(text)
        if match:
            heading = match.group(0).strip()
            # Truncate excessively long headings (some "WHEREAS" clauses
            # are entire paragraphs).
            return heading[:120] if len(heading) > 120 else heading
    return "General"


def _build_token_length_function() -> callable:
    """
    Return a function that counts GPT tokens in a string.

    Using ``tiktoken`` with the same encoding as the embedding model ensures
    our ``chunk_size_tokens`` setting translates directly to actual model
    token counts.
    """
    enc = tiktoken.get_encoding(settings.tiktoken_encoding)

    def _token_len(text: str) -> int:
        return len(enc.encode(text, disallowed_special=()))

    return _token_len


def _split_into_sections(full_text: str) -> list[tuple[str, str]]:
    """
    Split *full_text* into ``(heading, body)`` tuples by detecting legal
    section headings.

    If no headings are detected the entire text is returned as a single
    section with heading ``"General"``.
    """
    # Collect all heading match positions.
    heading_positions: list[tuple[int, int, str]] = []
    for pattern in SECTION_HEADING_PATTERNS:
        for match in pattern.finditer(full_text):
            heading_positions.append(
                (match.start(), match.end(), match.group(0).strip()[:120])
            )

    if not heading_positions:
        return [("General", full_text)]

    # Sort by position in document and deduplicate overlapping matches.
    heading_positions.sort(key=lambda x: x[0])
    deduped: list[tuple[int, int, str]] = []
    for start, end, heading in heading_positions:
        if deduped and start < deduped[-1][1]:
            continue  # Overlapping with previous — skip.
        deduped.append((start, end, heading))

    sections: list[tuple[str, str]] = []

    # Text before the first heading belongs to a preamble section.
    if deduped[0][0] > 0:
        preamble_text = full_text[: deduped[0][0]].strip()
        if preamble_text:
            sections.append(("Preamble", preamble_text))

    for i, (start, end, heading) in enumerate(deduped):
        next_start = deduped[i + 1][0] if i + 1 < len(deduped) else len(full_text)
        body = full_text[end:next_start].strip()
        if body:
            sections.append((heading, body))

    return sections if sections else [("General", full_text)]


def chunk_document(
    pages: PageTextList,
    document_name: str,
) -> list[Document]:
    """
    Convert parsed PDF pages into enriched LangChain ``Document`` chunks.

    Pipeline:
      1. Concatenate all page text (preserving page-break markers).
      2. Split into legal sections via regex heading detection.
      3. Within each section apply ``RecursiveCharacterTextSplitter`` using a
         token-based length function.
      4. Attach metadata to every chunk.

    Args:
        pages: Output of :func:`ingestion.parser.parse_pdf`.
        document_name: The originating filename.

    Returns:
        A list of LangChain ``Document`` objects ready for embedding.
    """
    token_len = _build_token_length_function()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size_tokens,
        chunk_overlap=settings.chunk_overlap_tokens,
        length_function=token_len,
        separators=[
            "\n\n\n",   # Major section break
            "\n\n",      # Paragraph break
            "\n",        # Line break
            ". ",        # Sentence boundary
            "; ",        # Clause boundary
            ", ",        # Subordinate clause
            " ",         # Word boundary (last resort)
        ],
        keep_separator=True,
    )

    # ── Step 1: Build a single text and a page-offset index ─────────────
    full_text_parts: list[str] = []
    # Maps character offset → page number for later attribution.
    page_offset_index: list[tuple[int, int]] = []  # (start_offset, page_num)

    offset = 0
    for page in pages:
        page_offset_index.append((offset, page["page_number"]))
        part = page["text"]
        full_text_parts.append(part)
        offset += len(part) + 1  # +1 for the join newline

    full_text = "\n".join(full_text_parts)

    if not full_text.strip():
        logger.warning("Document '%s' produced no extractable text.", document_name)
        return []

    # ── Step 2: Split into legal sections ───────────────────────────────
    sections = _split_into_sections(full_text)
    logger.info(
        "Detected %d sections in '%s'.",
        len(sections),
        document_name,
    )

    # ── Step 3 & 4: Chunk each section and attach metadata ──────────────
    all_chunks: list[Document] = []
    timestamp = datetime.now(timezone.utc).isoformat()
    global_chunk_idx = 0

    for section_heading, section_body in sections:
        sub_chunks = splitter.split_text(section_body)

        for chunk_text in sub_chunks:
            # Determine the most likely source page by finding where
            # the chunk text first appears in the full document.
            chunk_start = full_text.find(chunk_text[:200])
            page_num = _resolve_page_number(chunk_start, page_offset_index)

            doc = Document(
                page_content=chunk_text,
                metadata={
                    "document_name": document_name,
                    "section": section_heading,
                    "timestamp": timestamp,
                    "page_number": page_num,
                    "chunk_index": global_chunk_idx,
                },
            )
            all_chunks.append(doc)
            global_chunk_idx += 1

    logger.info(
        "Chunked '%s' into %d chunks across %d sections.",
        document_name,
        len(all_chunks),
        len(sections),
    )
    return all_chunks


def _resolve_page_number(
    char_offset: int,
    page_offset_index: list[tuple[int, int]],
) -> int:
    """
    Given a character offset into the concatenated text, return the
    originating page number.
    """
    if char_offset < 0:
        return 1

    resolved_page = 1
    for start_offset, page_num in page_offset_index:
        if start_offset <= char_offset:
            resolved_page = page_num
        else:
            break

    return resolved_page

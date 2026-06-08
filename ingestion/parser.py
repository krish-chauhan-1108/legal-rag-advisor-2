"""
PDF Document Parser for the Legal RAG Advisor.

Extracts clean text from uploaded PDF documents using PyPDF as the primary
engine, with automatic fallback to the ``unstructured`` library for scanned
or complex-layout PDFs.

Design decisions
----------------
- PyPDF is fast and reliable for digitally-born PDFs (the vast majority of
  modern legal agreements).
- ``unstructured`` handles OCR-heavy or multi-column layouts but is slower
  and has heavier dependencies, so it's used only as a fallback.
- Page boundaries are preserved so downstream chunking can attach page
  numbers to each chunk.
"""

from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)


# ─── Type alias for parsed output ───────────────────────────────────────────
# Each element is a dict: {"page_number": int, "text": str}
PageTextList = list[dict]


def parse_pdf_with_pypdf(file_path: Path) -> PageTextList:
    """
    Parse a PDF using PyPDF and return per-page text.

    Args:
        file_path: Absolute or relative path to the PDF file.

    Returns:
        A list of dicts, each containing ``page_number`` (1-indexed) and
        the extracted ``text`` for that page.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        RuntimeError: If PyPDF fails to open or parse the file.
    """
    from pypdf import PdfReader

    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    logger.info("Parsing PDF with PyPDF: %s", file_path.name)

    try:
        reader = PdfReader(str(file_path))
    except Exception as exc:
        raise RuntimeError(f"PyPDF could not open '{file_path.name}': {exc}") from exc

    pages: PageTextList = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        # Normalize whitespace but preserve paragraph breaks.
        cleaned = "\n".join(
            line.strip() for line in text.splitlines() if line.strip()
        )
        pages.append({"page_number": idx, "text": cleaned})

    logger.info(
        "PyPDF extracted %d pages from '%s'.",
        len(pages),
        file_path.name,
    )
    return pages


def parse_pdf_with_unstructured(file_path: Path) -> PageTextList:
    """
    Fallback parser using the ``unstructured`` library.

    This handles scanned PDFs and complex multi-column layouts by leveraging
    layout detection and optional OCR.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Same format as :func:`parse_pdf_with_pypdf`.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        RuntimeError: If ``unstructured`` fails.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    logger.info("Parsing PDF with unstructured (fallback): %s", file_path.name)

    try:
        from unstructured.partition.pdf import partition_pdf

        elements = partition_pdf(str(file_path))
    except Exception as exc:
        raise RuntimeError(
            f"unstructured could not parse '{file_path.name}': {exc}"
        ) from exc

    # Group elements by page.
    page_map: dict[int, list[str]] = {}
    for el in elements:
        page_num = getattr(el.metadata, "page_number", 1) or 1
        page_map.setdefault(page_num, []).append(str(el))

    pages: PageTextList = [
        {"page_number": pn, "text": "\n".join(texts)}
        for pn, texts in sorted(page_map.items())
    ]

    logger.info(
        "unstructured extracted %d pages from '%s'.",
        len(pages),
        file_path.name,
    )
    return pages


def parse_pdf(file_path: Path) -> PageTextList:
    """
    High-level parsing entry point with automatic fallback.

    Strategy:
      1. Try PyPDF first (fast, lightweight).
      2. If PyPDF produces very little text (< 100 chars total), assume the
         PDF is scanned/complex and fall back to ``unstructured``.

    Args:
        file_path: Path to the PDF document.

    Returns:
        Per-page extracted text.
    """
    pages = parse_pdf_with_pypdf(file_path)

    total_chars = sum(len(p["text"]) for p in pages)
    if total_chars < 100:
        logger.warning(
            "PyPDF extracted only %d chars from '%s'; falling back to unstructured.",
            total_chars,
            file_path.name,
        )
        try:
            pages = parse_pdf_with_unstructured(file_path)
        except Exception as exc:
            logger.error("Fallback parser also failed: %s", exc)
            # Return whatever PyPDF managed to get.

    return pages

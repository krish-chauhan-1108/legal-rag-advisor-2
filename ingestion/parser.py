"""
PDF Document Parser for the Legal RAG Advisor.

Extracts clean text from uploaded PDF documents using the lightweight PyPDF
engine. Uploaded documents are ephemeral context only; they are not indexed.

Design decisions
----------------
- PyPDF is fast and reliable for digitally-born PDFs (the vast majority of
  modern legal agreements).
- OCR and vector indexing are intentionally outside this service's runtime
  path so the Render deployment stays small and predictable.
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


def parse_pdf(file_path: Path) -> PageTextList:
    """
    High-level lightweight parsing entry point.

    Scanned PDFs may produce little or no text and should be uploaded only
    after OCR has been performed elsewhere. Keeping OCR out of the API avoids
    loading a large document-processing stack for every chat worker.

    Args:
        file_path: Path to the PDF document.

    Returns:
        Per-page extracted text.
    """
    return parse_pdf_with_pypdf(file_path)

import docx
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)

def parse_docx(file_path: Path) -> list[dict]:
    """
    Parse a DOCX file and return per-paragraph text wrapped in page-like structs.
    Word documents don't have strict page boundaries without rendering, so we
    treat the entire document as 'page 1' or chunk by paragraphs.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"DOCX not found: {file_path}")

    logger.info("Parsing DOCX: %s", file_path.name)
    
    try:
        doc = docx.Document(file_path)
    except Exception as exc:
        raise RuntimeError(f"python-docx could not open '{file_path.name}': {exc}") from exc

    full_text = []
    for para in doc.paragraphs:
        if para.text.strip():
            full_text.append(para.text.strip())

    return [{"page_number": 1, "text": "\n".join(full_text)}]

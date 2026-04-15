import io
import logging

try:
    import pymupdf
    def _open_pdf(content: bytes):
        return pymupdf.open(stream=content, filetype="pdf")
except ImportError:
    import fitz as pymupdf
    def _open_pdf(content: bytes):
        return pymupdf.open(stream=content, filetype="pdf")

from docx import Document

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

def extract_text_from_pdf(content: bytes) -> str | None:
    try:
        doc = _open_pdf(content)
        text = "\n\n".join(page.get_text() for page in doc)
        return text if text.strip() else None
    except Exception as e:
        log.warning("PDF parse failed: %s — skipping", e)
        return None

def extract_text_from_docx(content: bytes) -> str | None:
    try:
        doc = Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs) if paragraphs else None
    except Exception as e:
        log.warning("DOCX parse failed: %s — skipping", e)
        return None

def extract_text(content: bytes, filename: str) -> str | None:
    """Returns extracted text or None if extraction failed. Logs WARN on failure."""
    if len(content) > MAX_FILE_SIZE:
        log.warning("%s exceeds 20MB limit — skipping", filename)
        return None
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        log.warning("Unsupported file type .%s in %s — skipping", ext, filename)
        return None
    if ext == "pdf":
        return extract_text_from_pdf(content)
    elif ext == "docx":
        return extract_text_from_docx(content)
    elif ext == "txt":
        try:
            return content.decode("utf-8", errors="replace")
        except Exception as e:
            log.warning("TXT decode failed for %s: %s — skipping", filename, e)
            return None
    return None

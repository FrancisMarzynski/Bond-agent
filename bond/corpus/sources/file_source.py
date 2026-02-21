import io

try:
    import pymupdf
    def _open_pdf(content: bytes):
        return pymupdf.open(stream=content, filetype="pdf")
except ImportError:
    import fitz as pymupdf
    def _open_pdf(content: bytes):
        return pymupdf.open(stream=content, filetype="pdf")

from docx import Document

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

def extract_text_from_pdf(content: bytes) -> str | None:
    try:
        doc = _open_pdf(content)
        text = "\n\n".join(page.get_text() for page in doc)
        return text if text.strip() else None
    except Exception as e:
        print(f"WARN: PDF parse failed: {e} — skipping")
        return None

def extract_text_from_docx(content: bytes) -> str | None:
    try:
        doc = Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs) if paragraphs else None
    except Exception as e:
        print(f"WARN: DOCX parse failed: {e} — skipping")
        return None

def extract_text(content: bytes, filename: str) -> str | None:
    """Returns extracted text or None if extraction failed. Prints WARN on failure."""
    if len(content) > MAX_FILE_SIZE:
        print(f"WARN: {filename} exceeds 20MB limit — skipping")
        return None
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        print(f"WARN: Unsupported file type .{ext} in {filename} — skipping")
        return None
    if ext == "pdf":
        return extract_text_from_pdf(content)
    elif ext == "docx":
        return extract_text_from_docx(content)
    elif ext == "txt":
        try:
            return content.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"WARN: TXT decode failed for {filename}: {e} — skipping")
            return None
    return None

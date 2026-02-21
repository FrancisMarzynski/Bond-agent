from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1875 chars ≈ 500 tokens for Polish text (~3.75 chars/token average)
# 10% overlap for context continuity
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1875,
    chunk_overlap=190,
    separators=["\n\n", "\n", " ", ""],
)

def chunk_article(text: str) -> list[str]:
    """Split article text into style-corpus chunks. Filters empty chunks."""
    chunks = _splitter.split_text(text)
    return [c for c in chunks if len(c.strip()) > 50]

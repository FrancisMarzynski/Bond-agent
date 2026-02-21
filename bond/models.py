from enum import Enum
from pydantic import BaseModel

class SourceType(str, Enum):
    OWN_TEXT = "own"
    EXTERNAL_BLOGGER = "external"

class IngestTextRequest(BaseModel):
    text: str
    title: str = "Untitled"
    source_type: SourceType

class IngestResult(BaseModel):
    article_id: str
    title: str
    chunks_added: int
    source_type: str
    warnings: list[str] = []

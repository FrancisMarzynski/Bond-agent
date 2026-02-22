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


class IngestUrlRequest(BaseModel):
    url: str
    source_type: SourceType


class IngestDriveRequest(BaseModel):
    folder_id: str
    source_type: SourceType


class BatchIngestResult(BaseModel):
    articles_ingested: int
    total_chunks: int
    source_type: str
    warnings: list[str] = []

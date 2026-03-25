from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from bond.models import (
    IngestTextRequest,
    IngestResult,
    SourceType,
    IngestUrlRequest,
    IngestDriveRequest,
    BatchIngestResult,
    DriveFileInfo,
    DriveIngestResult,
)
from bond.corpus.sources.text_source import ingest_text
from bond.corpus.sources.file_source import extract_text
from bond.corpus.ingestor import CorpusIngestor
from bond.corpus.sources.url_source import ingest_blog
from bond.corpus.sources.drive_source import (
    build_drive_service,
    ingest_drive_folder,
    list_folder_files,
)
from bond.store.article_log import get_article_count, get_chunk_count, get_articles
from bond.corpus.smoke_test import run_smoke_test, DEFAULT_QUERY
from bond.config import settings

router = APIRouter(prefix="/api/corpus", tags=["corpus"])


class DocumentInfo(BaseModel):
    article_id: str
    title: str
    source_type: str
    source_url: str
    chunk_count: int
    ingested_at: str | None = None


class CorpusStatus(BaseModel):
    article_count: int
    chunk_count: int
    low_corpus_warning: str | None = None
    documents: list[DocumentInfo] = []


class SmokeTestResult(BaseModel):
    query: str
    results: list[dict]
    result_count: int


@router.post("/ingest/text", response_model=IngestResult)
async def ingest_text_endpoint(request: IngestTextRequest):
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    result = ingest_text(
        text=request.text,
        source_type=request.source_type.value,
        title=request.title,
    )
    return IngestResult(
        article_id=result["article_id"],
        title=request.title,
        chunks_added=result["chunks_added"],
        source_type=request.source_type.value,
        warnings=[],
    )


@router.post("/ingest/file", response_model=IngestResult)
async def ingest_file_endpoint(
    file: UploadFile = File(...),
    source_type: str = Form(...),
    title: str = Form(default=""),
):
    # Validate source_type
    try:
        st = SourceType(source_type)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"source_type must be 'own' or 'external', got: {source_type}",
        )

    content = await file.read()
    filename = file.filename or "upload"
    effective_title = title or filename

    text = extract_text(content, filename)
    warnings = []
    if text is None:
        warnings.append(f"Could not parse {filename} — file skipped")
        return IngestResult(
            article_id="",
            title=effective_title,
            chunks_added=0,
            source_type=st.value,
            warnings=warnings,
        )

    ingestor = CorpusIngestor()
    result = ingestor.ingest(
        text=text,
        title=effective_title,
        source_type=st.value,
        source_url="",
    )
    return IngestResult(
        article_id=result["article_id"],
        title=effective_title,
        chunks_added=result["chunks_added"],
        source_type=st.value,
        warnings=warnings,
    )


@router.post("/ingest/url", response_model=BatchIngestResult)
async def ingest_url_endpoint(request: IngestUrlRequest):
    if not request.url.strip():
        raise HTTPException(status_code=422, detail="url must not be empty")
    result = ingest_blog(url=request.url, source_type=request.source_type.value)
    return BatchIngestResult(
        articles_ingested=result["articles_ingested"],
        total_chunks=result["total_chunks"],
        source_type=request.source_type.value,
        warnings=result.get("warnings", []),
    )


@router.post("/ingest/drive", response_model=BatchIngestResult)
async def ingest_drive_endpoint(request: IngestDriveRequest):
    if not request.folder_id.strip():
        raise HTTPException(status_code=422, detail="folder_id must not be empty")
    result = ingest_drive_folder(
        folder_id=request.folder_id,
        source_type=request.source_type.value,
    )
    return BatchIngestResult(
        articles_ingested=result["articles_ingested"],
        total_chunks=result["total_chunks"],
        source_type=request.source_type.value,
        warnings=result.get("warnings", []),
    )


@router.post("/drive-ingest", response_model=DriveIngestResult)
async def drive_ingest_endpoint(request: IngestDriveRequest):
    """
    List files in a Google Drive folder, then ingest all supported documents.
    Returns a combined result: file listing + ingestion summary.
    Triggered by the MCP bond-drive server or directly by the frontend.
    """
    if not request.folder_id.strip():
        raise HTTPException(status_code=422, detail="folder_id must not be empty")

    # List files first so the response includes what was found
    try:
        service = build_drive_service()
        raw_files = list_folder_files(service, request.folder_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Drive auth failed: {e}")

    files_info = [
        DriveFileInfo(id=f["id"], name=f["name"], mime_type=f["mimeType"])
        for f in raw_files
    ]

    result = ingest_drive_folder(
        folder_id=request.folder_id,
        source_type=request.source_type.value,
    )

    return DriveIngestResult(
        files_found=len(raw_files),
        articles_ingested=result["articles_ingested"],
        total_chunks=result["total_chunks"],
        source_type=request.source_type.value,
        files=files_info,
        warnings=result.get("warnings", []),
    )


@router.get("/status", response_model=CorpusStatus)
async def corpus_status_endpoint():
    """
    CORP-06: Return article count and chunk count.
    CORP-07: Include low_corpus_warning when article count < LOW_CORPUS_THRESHOLD.
    """
    article_count = get_article_count()
    chunk_count = get_chunk_count()

    warning = None
    if article_count < settings.low_corpus_threshold:
        warning = (
            f"Corpus contains only {article_count} article(s). "
            f"Recommend at least {settings.low_corpus_threshold} articles for reliable style retrieval."
        )

    documents = [DocumentInfo(**doc) for doc in get_articles()]

    return CorpusStatus(
        article_count=article_count,
        chunk_count=chunk_count,
        low_corpus_warning=warning,
        documents=documents,
    )


@router.get("/smoke-test", response_model=SmokeTestResult)
async def smoke_test_endpoint(
    query: str = DEFAULT_QUERY,
    n: int = 5,
):
    """
    Run retrieval smoke test against the corpus.
    Returns top-N fragments with cosine similarity scores and source metadata.
    """
    results = run_smoke_test(query=query, n_results=n)
    return SmokeTestResult(
        query=query,
        results=results,
        result_count=len(results),
    )

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from bond.models import (
    IngestTextRequest,
    IngestResult,
    SourceType,
    IngestUrlRequest,
    IngestDriveRequest,
    BatchIngestResult,
)
from bond.corpus.sources.text_source import ingest_text
from bond.corpus.sources.file_source import extract_text
from bond.corpus.ingestor import CorpusIngestor
from bond.corpus.sources.url_source import ingest_blog
from bond.corpus.sources.drive_source import ingest_drive_folder

router = APIRouter(prefix="/api/corpus", tags=["corpus"])


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

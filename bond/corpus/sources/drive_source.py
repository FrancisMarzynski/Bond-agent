"""Google Drive folder downloader using google-api-python-client v3."""

import io
from bond.config import settings
from bond.corpus.sources.file_source import extract_text
from bond.corpus.ingestor import CorpusIngestor

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SUPPORTED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "application/vnd.google-apps.document": ".txt",  # export as plain text
}


def build_drive_service():
    """Build Google Drive API service. Supports oauth and service_account auth methods."""
    from googleapiclient.discovery import build

    method = settings.google_auth_method
    creds_path = settings.google_credentials_path

    if method == "service_account":
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=SCOPES
        )
        return build("drive", "v3", credentials=creds)
    else:
        # OAuth installed-app flow (default)
        import os
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request

        token_path = creds_path.replace("credentials.json", "token.json")
        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        return build("drive", "v3", credentials=creds)


def list_folder_files(service, folder_id: str) -> list[dict]:
    """List supported files in a Drive folder. Handles pagination up to 500 files."""
    query = f"'{folder_id}' in parents and trashed=false"
    files = []
    page_token = None
    while True:
        params = {
            "q": query,
            "fields": "nextPageToken, files(id, name, mimeType)",
            "pageSize": 100,
        }
        if page_token:
            params["pageToken"] = page_token
        response = service.files().list(**params).execute()
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return [f for f in files if f["mimeType"] in SUPPORTED_MIME_TYPES]


def download_file(service, file_id: str, mime_type: str) -> bytes | None:
    """Download file content as bytes. Exports Google Docs as plain text."""
    from googleapiclient.http import MediaIoBaseDownload

    try:
        if mime_type == "application/vnd.google-apps.document":
            request = service.files().export_media(
                fileId=file_id, mimeType="text/plain"
            )
        else:
            request = service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()
    except Exception as e:
        print(f"WARN: Download failed for file {file_id}: {e} — skipping")
        return None


def ingest_drive_folder(folder_id: str, source_type: str) -> dict:
    """
    Download and ingest all supported files from a Drive folder.
    Returns summary dict with articles_ingested, total_chunks, warnings.
    """
    try:
        service = build_drive_service()
    except Exception as e:
        return {
            "articles_ingested": 0,
            "total_chunks": 0,
            "warnings": [f"Drive auth failed: {e}"],
        }

    files = list_folder_files(service, folder_id)

    if not files:
        # Per RESEARCH.md pitfall 4: show service account email for troubleshooting
        warning_msg = (
            f"No supported files found in folder {folder_id}. "
            "If using service_account auth, ensure the folder is shared with the service account email. "
            "Check GOOGLE_CREDENTIALS_PATH for the service account email address."
        )
        print(f"WARN: {warning_msg}")
        return {"articles_ingested": 0, "total_chunks": 0, "warnings": [warning_msg]}

    print(f"INFO: Found {len(files)} supported files in Drive folder {folder_id}")

    ingestor = CorpusIngestor()
    total_chunks = 0
    ingested_count = 0
    warnings = []

    for f in files:
        content = download_file(service, f["id"], f["mimeType"])
        if content is None:
            warnings.append(f"Could not download {f['name']} — skipped")
            continue

        # Determine effective extension for file_source dispatch
        ext = SUPPORTED_MIME_TYPES[f["mimeType"]].lstrip(".")
        effective_name = f["name"] if "." in f["name"] else f"{f['name']}.{ext}"

        text = extract_text(content, effective_name)
        if text is None:
            warnings.append(f"Could not parse {f['name']} — skipped")
            continue

        result = ingestor.ingest(
            text=text,
            title=f["name"],
            source_type=source_type,
            source_url=f"https://drive.google.com/file/d/{f['id']}",
        )
        if result["chunks_added"] > 0:
            total_chunks += result["chunks_added"]
            ingested_count += 1
        else:
            warnings.append(f"{f['name']} too short to produce chunks — skipped")

    return {
        "articles_ingested": ingested_count,
        "total_chunks": total_chunks,
        "warnings": warnings,
    }

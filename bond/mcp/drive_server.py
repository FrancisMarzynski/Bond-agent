"""Google Drive MCP server.

Exposes two tools to Claude Code / LangGraph agents:
- list_drive_folder  — list supported files in a Drive folder
- drive_ingest       — download and ingest a folder into the corpus
"""

from mcp.server.fastmcp import FastMCP

from bond.corpus.sources.drive_source import (
    build_drive_service,
    ingest_drive_folder,
    list_folder_files,
)

mcp = FastMCP("bond-drive")


@mcp.tool()
def list_drive_folder(folder_id: str) -> list[dict]:
    """List all supported files (PDF, DOCX, TXT, Google Docs) in a Google Drive folder.

    Args:
        folder_id: The Google Drive folder ID (from the folder URL).

    Returns:
        List of dicts with keys: id, name, mimeType.
    """
    service = build_drive_service()
    return list_folder_files(service, folder_id)


@mcp.tool()
def drive_ingest(folder_id: str, source_type: str = "own") -> dict:
    """Download and ingest all supported files from a Google Drive folder into the corpus.

    Args:
        folder_id:   The Google Drive folder ID (from the folder URL).
        source_type: 'own' for the author's own articles, 'external' for reference texts.

    Returns:
        Dict with articles_ingested, total_chunks, and warnings list.
    """
    if source_type not in ("own", "external"):
        return {
            "articles_ingested": 0,
            "total_chunks": 0,
            "warnings": [f"Invalid source_type '{source_type}'. Use 'own' or 'external'."],
        }
    return ingest_drive_folder(folder_id=folder_id, source_type=source_type)


if __name__ == "__main__":
    mcp.run()

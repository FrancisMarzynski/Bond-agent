"""Google Drive MCP server.

Exposes two tools to Claude Code / LangGraph agents:
- list_drive_folder  — list supported files in a Drive folder
- drive_ingest       — download and ingest a folder into the corpus
"""

import asyncio

from mcp.server.fastmcp import FastMCP

from bond.corpus.sources.drive_source import (
    build_drive_service,
    ingest_drive_folder,
    list_folder_files,
)
from bond.models import DriveFileInfo, SourceType

mcp = FastMCP("bond-drive")


@mcp.tool()
async def list_drive_folder(folder_id: str) -> list[DriveFileInfo]:
    """List all supported files (PDF, DOCX, TXT, Google Docs) in a Google Drive folder.

    Args:
        folder_id: The Google Drive folder ID (from the folder URL).

    Returns:
        List of DriveFileInfo with fields: id, name, mime_type.
    """
    service = await asyncio.to_thread(build_drive_service)
    return await asyncio.to_thread(list_folder_files, service, folder_id)


@mcp.tool()
async def drive_ingest(
    folder_id: str, source_type: SourceType = SourceType.OWN_TEXT
) -> dict:
    """Download and ingest all supported files from a Google Drive folder into the corpus.

    Args:
        folder_id:   The Google Drive folder ID (from the folder URL).
        source_type: 'own' for the author's own articles, 'external' for reference texts.

    Returns:
        Dict with articles_ingested, total_chunks, and warnings list.
    """
    return await asyncio.to_thread(
        ingest_drive_folder, folder_id=folder_id, source_type=source_type.value
    )


if __name__ == "__main__":
    mcp.run()

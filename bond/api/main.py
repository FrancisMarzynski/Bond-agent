import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from bond.config import settings
from bond.api.routes.corpus import router as corpus_router
from bond.api.routes.chat import router as chat_router
from bond.graph.graph import compile_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with compile_graph() as graph:
        app.state.graph = graph
        yield

app = FastAPI(title="Bond — Agent Redakcyjny", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(corpus_router)
app.include_router(chat_router, prefix="/api/chat")


async def _check_sqlite(path: str) -> str:
    try:
        async with aiosqlite.connect(path) as conn:
            await conn.execute("SELECT 1")
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


def _check_chroma_sync() -> str:
    try:
        from bond.store.chroma import get_chroma_client
        get_chroma_client().heartbeat()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


@app.get("/health")
async def health(request: Request):
    checkpoint_status, metadata_status, articles_status = await asyncio.gather(
        _check_sqlite(settings.checkpoint_db_path),
        _check_sqlite(settings.metadata_db_path),
        _check_sqlite(settings.article_db_path),
    )

    loop = asyncio.get_event_loop()
    chroma_status = await loop.run_in_executor(None, _check_chroma_sync)

    graph_status = "ok" if getattr(request.app.state, "graph", None) is not None else "not_ready"

    checks = {
        "graph": graph_status,
        "checkpoint_db": checkpoint_status,
        "metadata_db": metadata_status,
        "articles_db": articles_status,
        "chroma": chroma_status,
    }

    return {
        "status": "ok" if all(v == "ok" for v in checks.values()) else "degraded",
        "version": app.version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }

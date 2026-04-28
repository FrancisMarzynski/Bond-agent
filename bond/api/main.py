import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from bond.api.runtime import CommandRuntime
from bond.api.routes.chat import router as chat_router
from bond.api.routes.corpus import router as corpus_router
from bond.api.security import (
    INTERNAL_PROXY_TOKEN_HEADER,
    REQUEST_ID_HEADER,
    has_valid_internal_proxy_token,
    is_internal_auth_protected_path,
)
from bond.config import settings
from bond.graph.graph import compile_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = CommandRuntime()
    app.state.runtime = runtime
    async with compile_graph() as graph:
        app.state.graph = graph
        yield
    await runtime.shutdown()


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


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _build_readiness_payload(request: Request) -> dict[str, object]:
    checkpoint_status, metadata_status, articles_status = await asyncio.gather(
        _check_sqlite(settings.checkpoint_db_path),
        _check_sqlite(settings.metadata_db_path),
        _check_sqlite(settings.article_db_path),
    )

    loop = asyncio.get_running_loop()
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
        "version": request.app.version,
        "timestamp": _utc_timestamp(),
        "checks": checks,
    }


def _readiness_status_code(payload: dict[str, object]) -> int:
    return 200 if payload["status"] == "ok" else 503


class InternalSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        started_at = perf_counter()

        if (
            settings.internal_auth_enabled
            and is_internal_auth_protected_path(request.url.path)
            and not has_valid_internal_proxy_token(
                request.headers.get(INTERNAL_PROXY_TOKEN_HEADER),
                settings.internal_proxy_token,
            )
        ):
            response = JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        "Bezpośredni dostęp do backendu jest zablokowany "
                        "w trybie wdrożenia wewnętrznego."
                    )
                },
            )
        else:
            response = await call_next(request)

        request.state.request_duration_ms = round((perf_counter() - started_at) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def create_app(*, lifespan_handler=lifespan) -> FastAPI:
    app = FastAPI(
        title="Bond — Agent Redakcyjny",
        version="0.1.0",
        lifespan=lifespan_handler,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Bond-Thread-Id", REQUEST_ID_HEADER],
    )
    app.add_middleware(InternalSecurityMiddleware)

    app.include_router(corpus_router)
    app.include_router(chat_router, prefix="/api/chat")

    @app.get("/health")
    async def health(request: Request):
        payload = await _build_readiness_payload(request)
        return JSONResponse(status_code=_readiness_status_code(payload), content=payload)

    @app.get("/health/ready")
    async def health_ready(request: Request):
        payload = await _build_readiness_payload(request)
        return JSONResponse(status_code=_readiness_status_code(payload), content=payload)

    @app.get("/health/live")
    async def health_live(request: Request):
        return {
            "status": "ok",
            "version": request.app.version,
            "timestamp": _utc_timestamp(),
        }

    return app


app = create_app()

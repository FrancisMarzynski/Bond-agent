from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
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


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": app.version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

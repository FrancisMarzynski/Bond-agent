from fastapi import FastAPI
from bond.api.routes.corpus import router as corpus_router

app = FastAPI(title="Bond — Agent Redakcyjny", version="0.1.0")
app.include_router(corpus_router)

@app.get("/health")
async def health():
    return {"status": "ok"}

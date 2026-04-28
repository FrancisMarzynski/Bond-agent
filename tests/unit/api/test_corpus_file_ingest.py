from fastapi import FastAPI
from fastapi.testclient import TestClient

from bond.api.routes.corpus import router


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_ingest_file_returns_warning_payload_when_file_cannot_be_read(monkeypatch):
    client = _build_client()
    monkeypatch.setattr("bond.api.routes.corpus.extract_text", lambda content, filename: None)

    response = client.post(
        "/api/corpus/ingest/file",
        data={"source_type": "own", "title": "Uszkodzony plik"},
        files={"file": ("broken.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "article_id": "",
        "title": "Uszkodzony plik",
        "chunks_added": 0,
        "source_type": "own",
        "warnings": [
            "Nie udało się odczytać pliku broken.pdf — plik został pominięty."
        ],
    }


def test_ingest_file_returns_positive_chunks_when_ingest_succeeds(monkeypatch):
    client = _build_client()
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        "bond.api.routes.corpus.extract_text",
        lambda content, filename: "To jest poprawnie odczytany tekst.",
    )

    class DummyIngestor:
        def ingest(self, *, text: str, title: str, source_type: str, source_url: str) -> dict:
            captured["text"] = text
            captured["title"] = title
            captured["source_type"] = source_type
            captured["source_url"] = source_url
            return {
                "article_id": "article-123",
                "chunks_added": 3,
            }

    monkeypatch.setattr("bond.api.routes.corpus.CorpusIngestor", DummyIngestor)

    response = client.post(
        "/api/corpus/ingest/file",
        data={"source_type": "external", "title": "Raport kwartalny"},
        files={"file": ("report.txt", b"Zawartosc raportu", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "article_id": "article-123",
        "title": "Raport kwartalny",
        "chunks_added": 3,
        "source_type": "external",
        "warnings": [],
    }
    assert captured == {
        "text": "To jest poprawnie odczytany tekst.",
        "title": "Raport kwartalny",
        "source_type": "external",
        "source_url": "",
    }

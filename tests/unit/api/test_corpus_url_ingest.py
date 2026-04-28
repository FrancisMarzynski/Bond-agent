import json
import socket

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bond.api.routes.corpus import router
from bond.corpus.sources import url_source


@pytest.fixture(autouse=True)
def clear_resolution_cache():
    from bond.security import url_validation

    url_validation._RESOLUTION_CACHE.clear()
    yield
    url_validation._RESOLUTION_CACHE.clear()


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr("bond.api.routes.corpus.settings.allow_private_url_ingest", False)
    return TestClient(app)


def _install_fake_dns(monkeypatch, mapping: dict[str, list[str]]) -> None:
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host not in mapping:
            raise socket.gaierror(f"unknown host: {host}")

        results = []
        for address in mapping[host]:
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            sockaddr = (address, port or 0, 0, 0) if family == socket.AF_INET6 else (address, port or 0)
            results.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
        return results

    monkeypatch.setattr("bond.security.url_validation.socket.getaddrinfo", fake_getaddrinfo)


def test_ingest_url_rejects_loopback_address(client, monkeypatch):
    monkeypatch.setattr(
        "bond.api.routes.corpus.ingest_blog",
        lambda *args, **kwargs: pytest.fail("ingest_blog should not be called for unsafe URLs"),
    )

    response = client.post(
        "/api/corpus/ingest/url",
        json={"url": "http://127.0.0.1/internal", "source_type": "external"},
    )

    assert response.status_code == 422
    assert "non-public address" in response.json()["detail"]


def test_ingest_url_rejects_localhost(client, monkeypatch):
    _install_fake_dns(monkeypatch, {"localhost": ["127.0.0.1", "::1"]})
    monkeypatch.setattr(
        "bond.api.routes.corpus.ingest_blog",
        lambda *args, **kwargs: pytest.fail("ingest_blog should not be called for unsafe URLs"),
    )

    response = client.post(
        "/api/corpus/ingest/url",
        json={"url": "http://localhost/internal", "source_type": "external"},
    )

    assert response.status_code == 422
    assert "non-public address" in response.json()["detail"]


def test_ingest_url_rejects_private_metadata_address(client, monkeypatch):
    monkeypatch.setattr(
        "bond.api.routes.corpus.ingest_blog",
        lambda *args, **kwargs: pytest.fail("ingest_blog should not be called for unsafe URLs"),
    )

    response = client.post(
        "/api/corpus/ingest/url",
        json={"url": "http://169.254.169.254/latest/meta-data", "source_type": "external"},
    )

    assert response.status_code == 422
    assert "non-public address" in response.json()["detail"]


def test_ingest_url_rejects_non_http_scheme(client, monkeypatch):
    monkeypatch.setattr(
        "bond.api.routes.corpus.ingest_blog",
        lambda *args, **kwargs: pytest.fail("ingest_blog should not be called for unsafe URLs"),
    )

    response = client.post(
        "/api/corpus/ingest/url",
        json={"url": "ftp://public.example/posts.xml", "source_type": "external"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "url must use http or https"


def test_ingest_url_allows_public_https_url(client, monkeypatch):
    _install_fake_dns(monkeypatch, {"public.example": ["8.8.8.8"]})
    captured: dict[str, str] = {}

    def fake_ingest_blog(url: str, source_type: str) -> dict:
        captured["url"] = url
        captured["source_type"] = source_type
        return {
            "articles_ingested": 2,
            "total_chunks": 14,
            "warnings": ["one article skipped"],
        }

    monkeypatch.setattr("bond.api.routes.corpus.ingest_blog", fake_ingest_blog)

    response = client.post(
        "/api/corpus/ingest/url",
        json={"url": "https://public.example/posts", "source_type": "external"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "articles_ingested": 2,
        "total_chunks": 14,
        "source_type": "external",
        "warnings": ["one article skipped"],
    }
    assert captured == {
        "url": "https://public.example/posts",
        "source_type": "external",
    }


def test_scrape_blog_skips_discovered_unsafe_urls(monkeypatch):
    _install_fake_dns(monkeypatch, {"public.example": ["8.8.8.8"]})
    monkeypatch.setattr("bond.corpus.sources.url_source.settings.allow_private_url_ingest", False)
    monkeypatch.setattr("bond.corpus.sources.url_source.settings.max_blog_posts", 10)
    monkeypatch.setattr(
        url_source,
        "sitemap_search",
        lambda url: [
            "https://public.example/post-1",
            "http://127.0.0.1/admin",
            "https://public.example/post-2",
        ],
    )

    fetched: list[str] = []

    def fake_fetch_url(url: str):
        fetched.append(url)
        return {"url": url}

    def fake_extract(downloaded, output_format: str = "json"):
        assert output_format == "json"
        return json.dumps(
            {
                "title": f"Tytul {downloaded['url']}",
                "text": "To jest dluzszy tekst artykulu do testu.",
            }
        )

    monkeypatch.setattr(url_source.trafilatura, "fetch_url", fake_fetch_url)
    monkeypatch.setattr(url_source.trafilatura, "extract", fake_extract)

    articles = url_source.scrape_blog("https://public.example")

    assert fetched == [
        "https://public.example/post-1",
        "https://public.example/post-2",
    ]
    assert [article["url"] for article in articles] == fetched

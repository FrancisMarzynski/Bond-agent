from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from bond.api.main import create_app
from bond.api.runtime import CommandRuntime
from bond.api.security import INTERNAL_PROXY_TOKEN_HEADER, REQUEST_ID_HEADER
from bond.config import settings


class MockStateSnapshot:
    def __init__(self, values, next_nodes):
        self.values = values
        self.next = next_nodes
        self.tasks = []


@asynccontextmanager
async def noop_lifespan(_app):
    yield


@pytest.fixture
def client(monkeypatch):
    app = create_app(lifespan_handler=noop_lifespan)
    mock_graph = AsyncMock()
    mock_graph.aget_state.return_value = MockStateSnapshot(
        values={
            "messages": [{"role": "user", "content": "Temat"}],
            "draft": "Finalny draft",
            "metadata_saved": True,
            "mode": "author",
        },
        next_nodes=[],
    )
    app.state.graph = mock_graph
    app.state.runtime = CommandRuntime()

    async def fake_check_sqlite(_path: str) -> str:
        return "ok"

    monkeypatch.setattr("bond.api.main._check_sqlite", fake_check_sqlite)
    monkeypatch.setattr("bond.api.main._check_chroma_sync", lambda: "ok")
    return TestClient(app)


def test_protected_route_rejects_without_trusted_header_when_internal_auth_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "internal_auth_enabled", True)
    monkeypatch.setattr(settings, "internal_proxy_token", "sekretny-token")

    response = client.get("/api/chat/history/thread-secure")

    assert response.status_code == 401
    assert "zablokowany" in response.json()["detail"]
    assert response.headers[REQUEST_ID_HEADER]


def test_protected_route_allows_valid_trusted_header_when_internal_auth_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "internal_auth_enabled", True)
    monkeypatch.setattr(settings, "internal_proxy_token", "sekretny-token")

    response = client.get(
        "/api/chat/history/thread-secure",
        headers={INTERNAL_PROXY_TOKEN_HEADER: "sekretny-token"},
    )

    assert response.status_code == 200
    assert response.json()["session_status"] == "completed"
    assert response.headers[REQUEST_ID_HEADER]


@pytest.mark.parametrize("path", ["/health", "/health/live", "/health/ready"])
def test_health_routes_bypass_internal_auth(path, client, monkeypatch):
    monkeypatch.setattr(settings, "internal_auth_enabled", True)
    monkeypatch.setattr(settings, "internal_proxy_token", "sekretny-token")

    response = client.get(path)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers[REQUEST_ID_HEADER]


def test_protected_route_remains_open_when_internal_auth_is_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "internal_auth_enabled", False)
    monkeypatch.setattr(settings, "internal_proxy_token", "")

    response = client.get("/api/chat/history/thread-open")

    assert response.status_code == 200
    assert response.json()["session_status"] == "completed"
    assert response.headers[REQUEST_ID_HEADER]


def test_cors_exposes_request_id_without_regressing_thread_header(client, monkeypatch):
    monkeypatch.setattr(settings, "internal_auth_enabled", False)

    response = client.get(
        "/health/live",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    exposed_headers = {
        header.strip() for header in response.headers["access-control-expose-headers"].split(",")
    }
    assert REQUEST_ID_HEADER in exposed_headers
    assert "X-Bond-Thread-Id" in exposed_headers

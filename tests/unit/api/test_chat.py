import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bond.api.routes.chat import router
from bond.api.routes.chat import ChatRequest


# Fake LangChain AIMessageChunk with content
class FakeChunk:
    def __init__(self, content):
        self.content = content


# Fake event stream simulating LangGraph
async def fake_astream_events(*args, **kwargs):
    yield {"event": "on_chain_start", "metadata": {"langgraph_node": "researcher"}}
    yield {"event": "on_chat_model_stream", "data": {"chunk": FakeChunk("Hel")}}
    yield {"event": "on_chat_model_stream", "data": {"chunk": FakeChunk("lo")}}


@pytest.fixture
def app():
    app = FastAPI()
    
    # Mock LangGraph compile graph and inject
    mock_graph = AsyncMock()
    mock_graph.astream_events = fake_astream_events
    
    app.state.graph = mock_graph
    app.include_router(router, prefix="/api/chat")
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_chat_stream_returns_sse(client):
    req_data = {"message": "Hello Bond", "mode": "author"}
    
    # With TestClient, we can read the streaming response
    with client.stream("POST", "/api/chat/stream", json=req_data) as response:
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["connection"] == "keep-alive"
        
        # Parse the SSE output
        content = response.iter_lines()
        lines = [line for line in content if line.strip()]
        
        # Verify the chunks from fake_astream_events
        assert 'data: {"type": "node", "data": "researcher"}' in lines[0]
        assert 'data: {"type": "token", "data": "Hel"}' in lines[1]
        assert 'data: {"type": "token", "data": "lo"}' in lines[2]

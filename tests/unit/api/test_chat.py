import json
import pytest
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bond.api.routes.chat import router
from bond.api.runtime import CommandRuntime


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
    captured = {}

    async def capturing_astream_events(input_or_command, *args, **kwargs):
        captured["input"] = input_or_command
        async for event in fake_astream_events(*args, **kwargs):
            yield event

    mock_graph = AsyncMock()
    mock_graph.astream_events = capturing_astream_events

    class MockState:
        values = {"messages": []}
        next = []

    mock_graph.aget_state.return_value = MockState()

    app.state.graph = mock_graph
    app.state.runtime = CommandRuntime()
    app.state.captured_stream_input = captured
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
        # lines[0] is now thread_id
        assert 'data: {"type":"thread_id"' in lines[0]
        # lines[1] is node_start (JSON payload with node + label)
        assert '"type":"node_start"' in lines[1]
        node_start_event = json.loads(lines[1].removeprefix("data: "))
        node_start_data = json.loads(node_start_event["data"])
        assert node_start_data["node"] == "researcher"
        assert "label" in node_start_data
        # lines[2] is stage (added in stream.py, includes label)
        assert '"type":"stage"' in lines[2]
        stage_event = json.loads(lines[2].removeprefix("data: "))
        stage_data = json.loads(stage_event["data"])
        assert stage_data["stage"] == "research"
        assert stage_data["status"] == "running"
        assert "label" in stage_data
        # lines[3] is token
        assert 'data: {"type":"token","data":"Hel"}' in lines[3]
        # lines[4] is token
        assert 'data: {"type":"token","data":"lo"}' in lines[4]


def test_chat_stream_injects_thread_id_into_initial_state(app, client):
    thread_id = "thread-123"

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "Hello Bond", "mode": "author", "thread_id": thread_id},
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    initial_state = app.state.captured_stream_input["input"]
    assert initial_state["thread_id"] == thread_id
    assert initial_state["topic"] == "Hello Bond"
    assert initial_state["mode"] == "author"


def test_chat_stream_normalizes_structured_author_brief_into_initial_state(app, client):
    brief = (
        "Temat: AI w marketingu B2B\n"
        "Słowa kluczowe: AI marketing, lead generation; AI marketing\n"
        "Wymagania: Ton ekspercki.\n"
        "Dodaj case study z Polski."
    )

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": brief, "mode": "author"},
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    initial_state = app.state.captured_stream_input["input"]
    assert initial_state["topic"] == "AI w marketingu B2B"
    assert initial_state["keywords"] == ["AI marketing", "lead generation"]
    assert initial_state["context_dynamic"] == "Ton ekspercki.\nDodaj case study z Polski."
    assert initial_state["messages"] == [{"role": "user", "content": brief}]

import json
import pytest
from typing import AsyncIterator, Any

from bond.api.stream import parse_stream_events


async def mock_event_stream(events: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    for event in events:
        yield event


@pytest.mark.asyncio
async def test_parse_stream_events_on_chain_start_with_langgraph_node():
    events = [
        {
            "event": "on_chain_start",
            "metadata": {"langgraph_node": "researcher"},
            "name": "ignored"
        }
    ]
    
    stream = mock_event_stream(events)
    results = [json.loads(r) async for r in parse_stream_events(stream)]
    
    assert len(results) == 1
    assert results[0] == {"type": "node_start", "data": "researcher"}


@pytest.mark.asyncio
async def test_parse_stream_events_on_chain_start_fallback_name():
    events = [
        {
            "event": "on_chain_start",
            "metadata": {},
            "name": "writer"
        }
    ]
    
    stream = mock_event_stream(events)
    results = [json.loads(r) async for r in parse_stream_events(stream)]
    
    assert len(results) == 1
    assert results[0] == {"type": "node_start", "data": "writer"}


@pytest.mark.asyncio
async def test_parse_stream_events_on_chain_start_ignored_name():
    events = [
        {
            "event": "on_chain_start",
            "metadata": {},
            "name": "some_internal_chain"
        }
    ]
    
    stream = mock_event_stream(events)
    results = [json.loads(r) async for r in parse_stream_events(stream)]
    
    assert len(results) == 0


class MockAIMessageChunk:
    def __init__(self, content):
        self.content = content


@pytest.mark.asyncio
async def test_parse_stream_events_on_chat_model_stream_string_content():
    events = [
        {
            "event": "on_chat_model_stream",
            "data": {
                "chunk": MockAIMessageChunk(content="Hello")
            }
        },
        {
            "event": "on_chat_model_stream",
            "data": {
                "chunk": MockAIMessageChunk(content=" world")
            }
        }
    ]
    
    stream = mock_event_stream(events)
    results = [json.loads(r) async for r in parse_stream_events(stream)]
    
    assert len(results) == 2
    assert results[0] == {"type": "token", "data": "Hello"}
    assert results[1] == {"type": "token", "data": " world"}


@pytest.mark.asyncio
async def test_parse_stream_events_on_chat_model_stream_dict_content():
    # Simulate some models that return dicts
    events = [
        {
            "event": "on_chat_model_stream",
            "data": {
                "chunk": {"content": "Test dic"}
            }
        }
    ]
    
    stream = mock_event_stream(events)
    results = [json.loads(r) async for r in parse_stream_events(stream)]
    
    assert len(results) == 1
    assert results[0] == {"type": "token", "data": "Test dic"}


@pytest.mark.asyncio
async def test_parse_stream_events_on_chat_model_stream_list_content():
    # Simulate Anthropic-like structure where content is a list of blocks
    events = [
        {
            "event": "on_chat_model_stream",
            "data": {
                "chunk": MockAIMessageChunk(content=[
                    {"type": "text", "text": "Block 1 "},
                    {"type": "text", "text": "Block 2"}
                ])
            }
        }
    ]
    
    stream = mock_event_stream(events)
    results = [json.loads(r) async for r in parse_stream_events(stream)]
    
    assert len(results) == 2
    assert results[0] == {"type": "token", "data": "Block 1 "}
    assert results[1] == {"type": "token", "data": "Block 2"}


@pytest.mark.asyncio
async def test_parse_stream_events_ignores_other_events():
    events = [
        {
            "event": "on_tool_start",
            "data": {}
        },
        {
            "event": "on_chat_model_stream",
            "data": {
                "chunk": MockAIMessageChunk(content="Valid")
            }
        },
        {
            "event": "on_chain_end",
            "data": {}
        }
    ]
    
    stream = mock_event_stream(events)
    results = [json.loads(r) async for r in parse_stream_events(stream)]
    
    assert len(results) == 1
    assert results[0] == {"type": "token", "data": "Valid"}

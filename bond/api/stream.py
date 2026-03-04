import json
from typing import AsyncIterator, Any

from bond.schemas import StreamEvent


async def parse_stream_events(events: AsyncIterator[Any]) -> AsyncIterator[str]:
    """
    Asynchronously parses LangGraph stream events and yields formatted JSON strings.
    
    Args:
        events: An asynchronous iterator of LangGraph events (from astream_events).
        
    Yields:
        JSON formatted strings representing the parsed events.
        Format: {"type": "node", "data": "<node_name>"} or {"type": "token", "data": "<text_chunk>"}
    """
    async for event in events:
        kind = event.get("event")
        
        # Handle start of a new node (chain)
        if kind == "on_chain_start":
            metadata = event.get("metadata", {})
            # Look for the LangGraph node name. The exact structure might vary,
            # but usually graph nodes have a specific 'langgraph_node' metadata or 
            # we can use the 'name' field if it matches our known nodes.
            # Assuming 'langgraph_node' is present for standard LangGraph nodes.
            node_name = metadata.get("langgraph_node")
            
            # If for some reason langgraph_node is missing, fallback to 'name'
            if not node_name:
                 name = event.get("name")
                 # Check if it's one of our target nodes
                 if name in ["duplicate_check", "researcher", "structure", "writer", "save_metadata", "__start__", "__end__"]:
                      node_name = name
                      
            if node_name:
                yield StreamEvent(type="node", data=node_name).model_dump_json()
                
        # Handle streaming of chat model tokens
        elif kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk:
                # Extract text from the chunk. Depending on the model, it might be in .content
                # or similar. Assuming standard LangChain AIMessageChunk.
                if hasattr(chunk, "content"):
                    text = chunk.content
                    if isinstance(text, str):
                        yield StreamEvent(type="token", data=text).model_dump_json()
                    elif isinstance(text, list):
                        # Some models return list of content blocks
                        for block in text:
                            if isinstance(block, dict) and block.get("type") == "text":
                                yield StreamEvent(type="token", data=block.get("text")).model_dump_json()
                elif isinstance(chunk, dict) and "content" in chunk:
                     content = chunk["content"]
                     if isinstance(content, str):
                         yield StreamEvent(type="token", data=content).model_dump_json()

    # Optional: emit an end event when the stream finishes
    # yield json.dumps({"type": "end", "data": "done"})

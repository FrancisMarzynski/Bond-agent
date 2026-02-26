import os
from contextlib import asynccontextmanager
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from bond.graph.state import AuthorState
from bond.config import settings
from bond.graph.nodes.duplicate_check import duplicate_check_node as _duplicate_check_node
from bond.graph.nodes.researcher import researcher_node as _researcher_node
from bond.graph.nodes.structure import structure_node as _structure_node
from bond.graph.nodes.checkpoint_1 import checkpoint_1_node as _checkpoint_1_node
from bond.graph.nodes.writer import writer_node as _writer_node
from bond.graph.nodes.checkpoint_2 import checkpoint_2_node as _checkpoint_2_node
from bond.graph.nodes.save_metadata import save_metadata_node as _save_metadata_node


# ---------------------------------------------------------------------------
# Dynamic node loader — all 7 real implementations
# ---------------------------------------------------------------------------

_node_registry: dict = {
    "duplicate_check": _duplicate_check_node,
    "researcher": _researcher_node,
    "structure": _structure_node,
    "checkpoint_1": _checkpoint_1_node,
    "writer": _writer_node,
    "checkpoint_2": _checkpoint_2_node,
    "save_metadata": _save_metadata_node,
}


def register_node(name: str, fn) -> None:
    """Called by each nodes/*.py module to replace its stub."""
    _node_registry[name] = fn


# ---------------------------------------------------------------------------
# Routing functions (routing logic is stable — do not change in later plans)
# ---------------------------------------------------------------------------

def _route_after_duplicate_check(state: AuthorState) -> str:
    """Route to researcher unless user explicitly aborted the duplicate warning."""
    if state.get("duplicate_override") is False:
        return END
    return "researcher"


def _route_after_cp1(state: AuthorState) -> str:
    """Loop back to structure node on rejection; advance to writer on approval."""
    if state.get("cp1_approved"):
        return "writer"
    return "structure"


def _route_after_cp2(state: AuthorState) -> str:
    """Loop back to writer on rejection (soft cap enforced inside checkpoint_2 node);
    advance to save_metadata on approval."""
    if state.get("cp2_approved"):
        return "save_metadata"
    return "writer"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_author_graph() -> StateGraph:
    builder = StateGraph(AuthorState)

    # Register nodes (uses current registry — stubs until Plans 02-04 run)
    for name, fn in _node_registry.items():
        builder.add_node(name, fn)

    # Edges
    builder.add_edge(START, "duplicate_check")
    builder.add_conditional_edges(
        "duplicate_check",
        _route_after_duplicate_check,
        {"researcher": "researcher", END: END},
    )
    builder.add_edge("researcher", "structure")
    builder.add_edge("structure", "checkpoint_1")
    builder.add_conditional_edges(
        "checkpoint_1",
        _route_after_cp1,
        {"writer": "writer", "structure": "structure", END: END},
    )
    builder.add_edge("writer", "checkpoint_2")
    builder.add_conditional_edges(
        "checkpoint_2",
        _route_after_cp2,
        {"save_metadata": "save_metadata", "writer": "writer", END: END},
    )
    builder.add_edge("save_metadata", END)

    return builder


@asynccontextmanager
async def compile_graph():
    """Async context manager — yields a compiled graph with AsyncSqliteSaver.

    Usage:
        async with compile_graph() as graph:
            result = await graph.ainvoke(...)
    """
    os.makedirs(os.path.dirname(os.path.abspath(settings.checkpoint_db_path)), exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(settings.checkpoint_db_path) as checkpointer:
        builder = build_author_graph()
        yield builder.compile(checkpointer=checkpointer)

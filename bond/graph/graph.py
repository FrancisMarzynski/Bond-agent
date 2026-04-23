import os
from contextlib import asynccontextmanager
from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from bond.graph.state import BondState
from bond.config import settings
from bond.graph.nodes.duplicate_check import duplicate_check_node as _duplicate_check_node
from bond.graph.nodes.researcher import researcher_node as _researcher_node
from bond.graph.nodes.structure import structure_node as _structure_node
from bond.graph.nodes.checkpoint_1 import checkpoint_1_node as _checkpoint_1_node, HARD_CAP_ITERATIONS as _CP1_HARD_CAP
from bond.graph.nodes.writer import writer_node as _writer_node
from bond.graph.nodes.checkpoint_2 import checkpoint_2_node as _checkpoint_2_node, HARD_CAP_ITERATIONS as _CP2_HARD_CAP
from bond.graph.nodes.save_metadata import save_metadata_node as _save_metadata_node
from bond.graph.nodes.shadow_analyze import shadow_analyze_node as _shadow_analyze_node
from bond.graph.nodes.shadow_annotate import shadow_annotate_node as _shadow_annotate_node
from bond.graph.nodes.shadow_checkpoint import shadow_checkpoint_node as _shadow_checkpoint_node, HARD_CAP_ITERATIONS as _SHADOW_HARD_CAP


# ---------------------------------------------------------------------------
# Dynamic node loader — author mode nodes (7) + shadow mode nodes (2)
# ---------------------------------------------------------------------------

_node_registry: dict = {
    "duplicate_check": _duplicate_check_node,
    "researcher": _researcher_node,
    "structure": _structure_node,
    "checkpoint_1": _checkpoint_1_node,
    "writer": _writer_node,
    "checkpoint_2": _checkpoint_2_node,
    "save_metadata": _save_metadata_node,
    "shadow_analyze": _shadow_analyze_node,
    "shadow_annotate": _shadow_annotate_node,
    "shadow_checkpoint": _shadow_checkpoint_node,
}


def register_node(name: str, fn) -> None:
    """Called by each nodes/*.py module to replace its stub."""
    _node_registry[name] = fn


# ---------------------------------------------------------------------------
# Routing functions (routing logic is stable — do not change in later plans)
# ---------------------------------------------------------------------------

def route_mode(state: BondState) -> Literal["duplicate_check", "shadow_analyze"]:
    """Route to Author or Shadow branch based on the 'mode' field at START."""
    if state.get("mode") == "shadow":
        return "shadow_analyze"
    return "duplicate_check"


def _route_after_duplicate_check(state: BondState) -> str:
    """Route to researcher unless user explicitly aborted the duplicate warning."""
    if state.get("duplicate_override") is False:
        return END
    return "researcher"


def _route_after_cp1(state: BondState) -> str:
    """Loop back to structure node on rejection; advance to writer on approval.

    Safety cap: if cp1_iterations has reached the hard cap (defence-in-depth behind
    the node-level Command(goto=END)), route directly to END to prevent infinite loops.
    """
    if state.get("cp1_iterations", 0) >= _CP1_HARD_CAP:
        return END
    if state.get("cp1_approved"):
        return "writer"
    return "structure"


def _route_after_cp2(state: BondState) -> str:
    """Loop back to writer on rejection (soft cap enforced inside checkpoint_2 node);
    advance to save_metadata on approval.

    Safety cap: mirrors the node-level hard cap as a routing-layer backstop.
    """
    if state.get("cp2_iterations", 0) >= _CP2_HARD_CAP:
        return END
    if state.get("cp2_approved"):
        return "save_metadata"
    return "writer"


def _route_after_shadow_checkpoint(state: BondState) -> str:
    """Route to END on approval or hard-cap; loop back to shadow_annotate on rejection.

    Called only when the node returns a plain dict (approve case).
    For reject/abort/hard-cap the node returns Command(goto=...) which takes precedence.
    The path_map in add_conditional_edges also serves as the LangGraph declaration of all
    valid destinations — required for Command(goto="shadow_annotate") to compile correctly.
    """
    if state.get("shadow_approved"):
        return END
    if state.get("iteration_count", 0) >= _SHADOW_HARD_CAP:
        return END
    return "shadow_annotate"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_author_graph() -> StateGraph:
    builder = StateGraph(BondState)

    # Register nodes (uses current registry)
    for name, fn in _node_registry.items():
        builder.add_node(name, fn)

    # START → dual-branch routing (Author or Shadow)
    builder.add_conditional_edges(
        START,
        route_mode,
        {"duplicate_check": "duplicate_check", "shadow_analyze": "shadow_analyze"},
    )
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

    # Shadow branch: analyze → annotate → checkpoint (loops back to annotate on reject)
    builder.add_edge("shadow_analyze", "shadow_annotate")
    builder.add_edge("shadow_annotate", "shadow_checkpoint")
    builder.add_conditional_edges(
        "shadow_checkpoint",
        _route_after_shadow_checkpoint,
        {"shadow_annotate": "shadow_annotate", END: END},
    )

    return builder


# Backward-compat alias
build_bond_graph = build_author_graph


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

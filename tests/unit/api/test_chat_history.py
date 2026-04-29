from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bond.api.routes.chat import router
from bond.api.runtime import CommandRuntime, ActiveRun


class MockStateSnapshot:
    def __init__(self, values, next_nodes, tasks=None):
        self.values = values
        self.next = next_nodes
        self.tasks = tasks or []


def _draft_validation_details() -> dict:
    return {
        "passed": False,
        "checks": {
            "keyword_in_h1": False,
            "keyword_in_first_para": True,
            "meta_desc_length_ok": False,
            "word_count_ok": True,
            "no_forbidden_words": True,
        },
        "failure_codes": ["keyword_in_h1", "meta_desc_length_ok"],
        "failures": [
            {
                "code": "keyword_in_h1",
                "message": 'H1 musi zawierać główne słowo kluczowe "AI marketing".',
            },
            {
                "code": "meta_desc_length_ok",
                "message": "Meta-description musi mieć 150-160 znaków; obecnie ma 121.",
            },
        ],
        "primary_keyword": "AI marketing",
        "body_word_count": 920,
        "min_words": 800,
        "meta_description_length": 121,
        "meta_description_min_length": 150,
        "meta_description_max_length": 160,
        "forbidden_stems": [],
        "attempt_count": 3,
        "attempts": [
            {"attempt_number": 1, "passed": False, "failed_codes": ["keyword_in_h1"]},
            {"attempt_number": 2, "passed": False, "failed_codes": ["meta_desc_length_ok"]},
            {
                "attempt_number": 3,
                "passed": False,
                "failed_codes": ["keyword_in_h1", "meta_desc_length_ok"],
            },
        ],
    }


def _build_client(state_snapshot: MockStateSnapshot, runtime: CommandRuntime = None) -> TestClient:
    app = FastAPI()
    mock_graph = AsyncMock()
    mock_graph.aget_state.return_value = state_snapshot
    app.state.graph = mock_graph
    app.state.runtime = runtime or CommandRuntime()
    app.include_router(router, prefix="/api/chat")
    return TestClient(app)


def test_get_chat_history_returns_completed_author_session():
    client = _build_client(
        MockStateSnapshot(
            values={
                "messages": [{"role": "user", "content": "Temat"}],
                "draft": "Finalny draft",
                "metadata_saved": True,
            },
            next_nodes=[],
        )
    )

    response = client.get("/api/chat/history/thread-complete")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_status"] == "completed"
    assert payload["pending_node"] is None
    assert payload["can_resume"] is False
    assert payload["stage"] == "done"
    assert payload["stageStatus"] == {"done": "complete"}
    assert payload["draft"] == "Finalny draft"
    assert payload["hitlPause"] is None
    assert payload["mode"] == "author"


def test_get_chat_history_returns_paused_shadow_checkpoint_history():
    annotations = [
        {
            "id": "ann-1",
            "original_span": "Ala ma kota",
            "replacement": "Ala prowadzi narrację",
            "reason": "Lepszy rytm",
            "start_index": 0,
            "end_index": 12,
        }
    ]
    client = _build_client(
        MockStateSnapshot(
            values={
                "messages": [{"role": "user", "content": "Tekst"}],
                "original_text": "Tekst wejściowy",
                "annotations": annotations,
                "shadow_corrected_text": "Tekst poprawiony",
                "iteration_count": 1,
                "mode": "shadow",
            },
            next_nodes=["shadow_checkpoint"],
        )
    )

    response = client.get("/api/chat/history/thread-shadow")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_status"] == "paused"
    assert payload["pending_node"] == "shadow_checkpoint"
    assert payload["can_resume"] is True
    assert payload["draft"] == "Tekst poprawiony"
    assert payload["shadowCorrectedText"] == "Tekst poprawiony"
    assert payload["annotations"] == annotations
    assert payload["mode"] == "shadow"
    assert payload["hitlPause"] == {
        "checkpoint_id": "shadow_checkpoint",
        "type": "approve_reject",
        "annotations": annotations,
        "shadow_corrected_text": "Tekst poprawiony",
        "iteration_count": 1,
    }


def test_get_chat_history_surfaces_checkpoint_2_validation_details():
    validation_details = _draft_validation_details()
    client = _build_client(
        MockStateSnapshot(
            values={
                "messages": [{"role": "user", "content": "Temat"}],
                "draft": "Draft testowy",
                "draft_validated": False,
                "draft_validation_details": validation_details,
                "cp2_iterations": 2,
            },
            next_nodes=["checkpoint_2"],
        )
    )

    response = client.get("/api/chat/history/thread-cp2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_status"] == "paused"
    assert payload["pending_node"] == "checkpoint_2"
    assert payload["can_resume"] is True
    assert payload["hitlPause"]["checkpoint_id"] == "checkpoint_2"
    assert payload["hitlPause"]["draft_validated"] is False
    assert payload["hitlPause"]["iterations_remaining"] == 1
    assert payload["hitlPause"]["validation_warning"].startswith("Draft nie spełnia")
    assert payload["hitlPause"]["draft_validation_details"] == validation_details


def test_get_chat_history_does_not_fabricate_hitl_pause_for_running_session():
    client = _build_client(
        MockStateSnapshot(
            values={
                "messages": [{"role": "user", "content": "Temat"}],
                "topic": "Temat",
            },
            next_nodes=["writer"],
        )
    )

    response = client.get("/api/chat/history/thread-running")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_status"] == "running"
    assert payload["pending_node"] == "writer"
    assert payload["can_resume"] is False
    assert payload["hitlPause"] is None
    assert payload["stage"] == "writing"
    assert payload["stageStatus"] == {"writing": "running"}


# ---------------------------------------------------------------------------
# Shadow stage alignment tests
# ---------------------------------------------------------------------------

def test_get_chat_history_returns_shadow_analysis_for_running_shadow_analyze():
    client = _build_client(
        MockStateSnapshot(
            values={
                "messages": [{"role": "user", "content": "Tekst"}],
                "original_text": "Tekst wejściowy",
                "mode": "shadow",
            },
            next_nodes=["shadow_analyze"],
        )
    )

    response = client.get("/api/chat/history/thread-shadow-analyze")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_status"] == "running"
    assert payload["stage"] == "shadow_analysis"
    assert payload["stageStatus"] == {"shadow_analysis": "running"}
    assert payload["hitlPause"] is None


def test_get_chat_history_returns_shadow_annotation_for_running_shadow_annotate():
    client = _build_client(
        MockStateSnapshot(
            values={
                "messages": [{"role": "user", "content": "Tekst"}],
                "original_text": "Tekst wejściowy",
                "mode": "shadow",
            },
            next_nodes=["shadow_annotate"],
        )
    )

    response = client.get("/api/chat/history/thread-shadow-annotate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_status"] == "running"
    assert payload["stage"] == "shadow_annotation"
    assert payload["stageStatus"] == {"shadow_annotation": "running"}


def test_get_chat_history_returns_shadow_annotation_for_paused_checkpoint():
    annotations = [
        {
            "id": "ann-1",
            "original_span": "Ala ma kota",
            "replacement": "Ala prowadzi narrację",
            "reason": "Lepszy rytm",
            "start_index": 0,
            "end_index": 12,
        }
    ]
    client = _build_client(
        MockStateSnapshot(
            values={
                "messages": [{"role": "user", "content": "Tekst"}],
                "original_text": "Tekst wejściowy",
                "annotations": annotations,
                "shadow_corrected_text": "Tekst poprawiony",
                "iteration_count": 1,
            },
            next_nodes=["shadow_checkpoint"],
        )
    )

    response = client.get("/api/chat/history/thread-shadow-cp")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_status"] == "paused"
    assert payload["stage"] == "shadow_annotation"


# ---------------------------------------------------------------------------
# Runtime overlay tests
# ---------------------------------------------------------------------------

def test_get_chat_history_surfaces_active_command_from_runtime():
    runtime = CommandRuntime()

    mock_run = MagicMock(spec=ActiveRun)
    mock_run.active_command = "resume"
    mock_run.task = MagicMock()
    mock_run.task.done.return_value = False
    mock_run.finished_cleanly = False
    mock_run.terminal_error = None
    runtime._runs["thread-active"] = mock_run

    client = _build_client(
        MockStateSnapshot(
            values={"messages": [], "topic": "Temat"},
            next_nodes=["writer"],
        ),
        runtime=runtime,
    )

    response = client.get("/api/chat/history/thread-active")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_command"] == "resume"
    assert payload["session_status"] == "running"


def test_get_chat_history_surfaces_error_message_from_failed_run():
    runtime = CommandRuntime()

    mock_run = MagicMock(spec=ActiveRun)
    mock_run.active_command = "stream"
    mock_run.task = MagicMock()
    mock_run.task.done.return_value = True
    mock_run.finished_cleanly = False
    mock_run.terminal_error = "OpenAI API error"
    runtime._runs["thread-error"] = mock_run

    client = _build_client(
        MockStateSnapshot(
            values={"messages": []},
            next_nodes=[],  # No pending node → would normally be "completed"
        ),
        runtime=runtime,
    )

    response = client.get("/api/chat/history/thread-error")

    assert response.status_code == 200
    payload = response.json()
    assert payload["error_message"] == "OpenAI API error"
    assert payload["session_status"] == "error"


def test_get_chat_history_includes_null_active_command_when_no_runtime():
    client = _build_client(
        MockStateSnapshot(
            values={"messages": [], "metadata_saved": True},
            next_nodes=[],
        )
    )

    response = client.get("/api/chat/history/thread-complete")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_command"] is None
    assert payload["error_message"] is None
    assert payload["mode"] == "author"

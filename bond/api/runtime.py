"""
Detached command runtime.

Each POST /api/chat/stream and POST /api/chat/resume starts a background
asyncio.Task that owns the LangGraph execution. The SSE response generator
subscribes to an event queue on that task. When the client disconnects
(before the task finishes), the consumer is detached and future events are
dropped — but the graph continues running until the next durable state.

GET /api/chat/history/{thread_id} then reports the real recovery state
without the client replaying a committed POST.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

log = logging.getLogger(__name__)

_SENTINEL = object()

ActiveCommand = Literal["stream", "resume"]


class ActiveRun:
    """Tracks one background graph execution for a single thread."""

    __slots__ = (
        "thread_id",
        "active_command",
        "task",
        "_queue",
        "_consumer_active",
        "finished_cleanly",
        "terminal_error",
        "detached_at",
        "completed_at",
    )

    def __init__(self, thread_id: str, active_command: ActiveCommand) -> None:
        self.thread_id = thread_id
        self.active_command: ActiveCommand = active_command
        self.task: Optional[asyncio.Task] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._consumer_active: bool = True
        self.finished_cleanly: bool = False
        self.terminal_error: Optional[str] = None
        self.detached_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

    def publish(self, event: str) -> None:
        """Enqueue an SSE event string. Silently discarded after the consumer detaches."""
        if self._consumer_active:
            self._queue.put_nowait(event)

    def signal_done(self) -> None:
        """Called by the producer when it finishes — wakes any waiting consumer."""
        self.completed_at = datetime.now(timezone.utc)
        if self._consumer_active:
            try:
                self._queue.put_nowait(_SENTINEL)
            except Exception:
                pass

    def detach_subscriber(self) -> None:
        """
        Detach the SSE consumer.

        Future publish() calls are discarded. The background producer task
        continues running until the graph reaches a durable state.
        """
        if not self._consumer_active:
            return
        self._consumer_active = False
        self.detached_at = datetime.now(timezone.utc)
        try:
            self._queue.put_nowait(_SENTINEL)
        except Exception:
            pass
        log.info(
            "SSE consumer detached from thread %s — producer continues in background",
            self.thread_id,
        )

    async def consume_next(self, timeout: float = 0.5) -> "tuple[bool, Optional[str]]":
        """
        Try to read the next queued event.

        Returns:
            (True, None)      — done sentinel; consumer should stop.
            (False, None)     — timeout; caller should check disconnect and retry.
            (False, event)    — a normal event string ready to yield.
        """
        try:
            item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return False, None
        if item is _SENTINEL:
            return True, None
        return False, item


class CommandRuntime:
    """
    App-scoped detached command runtime.

    Initialised during FastAPI lifespan and stored on ``app.state.runtime``.
    """

    def __init__(self) -> None:
        self._runs: dict[str, ActiveRun] = {}

    def get_run(self, thread_id: str) -> Optional[ActiveRun]:
        """Return the most recent ActiveRun for a thread, or None."""
        return self._runs.get(thread_id)

    def is_running(self, thread_id: str) -> bool:
        """True if a background task for this thread is still alive."""
        run = self._runs.get(thread_id)
        return run is not None and run.task is not None and not run.task.done()

    async def start_run(
        self,
        thread_id: str,
        active_command: ActiveCommand,
        producer,
    ) -> ActiveRun:
        """
        Start a detached background producer task and return the ActiveRun immediately.

        ``producer`` is a coroutine function that accepts the ActiveRun and calls
        ``run.publish(event_str)`` for each SSE event it produces. Exceptions are
        caught, stored on the run, and never propagated to the SSE generator.
        """
        run = ActiveRun(thread_id=thread_id, active_command=active_command)

        async def _wrapper() -> None:
            try:
                await producer(run)
                run.finished_cleanly = True
            except Exception as exc:
                log.error(
                    "Background run failed for thread %s: %s",
                    thread_id,
                    exc,
                    exc_info=True,
                )
                run.terminal_error = str(exc)
            finally:
                run.signal_done()

        run.task = asyncio.create_task(_wrapper())
        self._runs[thread_id] = run
        return run

    async def shutdown(self) -> None:
        """Cancel all active background tasks during app shutdown."""
        for thread_id, run in list(self._runs.items()):
            if run.task and not run.task.done():
                log.info("Shutdown: cancelling background run for thread %s", thread_id)
                run.task.cancel()
                try:
                    await run.task
                except (asyncio.CancelledError, Exception):
                    pass
        self._runs.clear()

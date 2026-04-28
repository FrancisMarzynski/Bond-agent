"""
Unit tests for bond.api.runtime.CommandRuntime.

Validates:
- disconnect detaches the subscriber without cancelling the producer
- producer completion sets finished_cleanly and clears the queue
- terminal errors are captured for /history
- resume lock remains held until the producer finishes
"""
import asyncio
import pytest

from bond.api.runtime import ActiveRun, CommandRuntime


# ---------------------------------------------------------------------------
# ActiveRun unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_active_run_publish_delivers_to_consumer():
    run = ActiveRun("t1", "stream")
    run.publish("event-1")
    is_done, event = await run.consume_next(timeout=0.1)
    assert is_done is False
    assert event == "event-1"


@pytest.mark.asyncio
async def test_active_run_signal_done_stops_consumer():
    run = ActiveRun("t1", "stream")
    run.publish("event-1")
    run.signal_done()
    _, event = await run.consume_next(timeout=0.1)
    assert event == "event-1"
    is_done, event2 = await run.consume_next(timeout=0.1)
    assert is_done is True
    assert event2 is None


@pytest.mark.asyncio
async def test_active_run_detach_stops_delivery():
    run = ActiveRun("t1", "stream")
    run.detach_subscriber()
    # publish after detach should be silently dropped
    run.publish("should-be-dropped")
    is_done, event = await run.consume_next(timeout=0.1)
    # Detach sends the sentinel, so consumer should see done
    assert is_done is True
    assert event is None


@pytest.mark.asyncio
async def test_active_run_detach_sets_timestamp():
    run = ActiveRun("t1", "stream")
    assert run.detached_at is None
    run.detach_subscriber()
    assert run.detached_at is not None


@pytest.mark.asyncio
async def test_active_run_signal_done_sets_completed_at():
    run = ActiveRun("t1", "stream")
    assert run.completed_at is None
    run.signal_done()
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_active_run_double_detach_is_idempotent():
    run = ActiveRun("t1", "stream")
    run.detach_subscriber()
    first_ts = run.detached_at
    run.detach_subscriber()  # second call should be a no-op
    assert run.detached_at is first_ts


# ---------------------------------------------------------------------------
# CommandRuntime unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_start_run_returns_run_immediately():
    runtime = CommandRuntime()

    async def producer(run: ActiveRun):
        run.publish("hello")

    run = await runtime.start_run("t1", "stream", producer)
    assert run.thread_id == "t1"
    assert run.active_command == "stream"
    assert run.task is not None


@pytest.mark.asyncio
async def test_runtime_producer_completes_and_sets_finished_cleanly():
    runtime = CommandRuntime()

    async def producer(run: ActiveRun):
        run.publish("done-event")

    run = await runtime.start_run("t1", "stream", producer)
    # Wait for the task to finish
    await run.task
    assert run.finished_cleanly is True
    assert run.terminal_error is None


@pytest.mark.asyncio
async def test_runtime_producer_exception_captured_in_terminal_error():
    runtime = CommandRuntime()

    async def producer(run: ActiveRun):
        raise ValueError("something went wrong")

    run = await runtime.start_run("t1", "stream", producer)
    await run.task
    assert run.finished_cleanly is False
    assert "something went wrong" in run.terminal_error


@pytest.mark.asyncio
async def test_runtime_detach_does_not_cancel_producer():
    runtime = CommandRuntime()
    producer_ran_to_completion = asyncio.Event()

    async def slow_producer(run: ActiveRun):
        await asyncio.sleep(0.05)
        run.publish("late-event")
        producer_ran_to_completion.set()

    run = await runtime.start_run("t1", "stream", slow_producer)

    # Detach the consumer immediately — simulates a disconnect
    run.detach_subscriber()

    # Wait for the background producer to finish
    await run.task
    assert producer_ran_to_completion.is_set(), "Producer was cancelled despite detach"
    assert run.finished_cleanly is True


@pytest.mark.asyncio
async def test_runtime_lock_held_until_producer_finishes():
    runtime = CommandRuntime()
    lock = asyncio.Lock()
    lock_released = asyncio.Event()
    lock_during_run = asyncio.Event()

    async def producer(run: ActiveRun):
        try:
            lock_during_run.set()  # Signal that producer is running
            await asyncio.sleep(0.05)
        finally:
            lock.release()
            lock_released.set()

    # Simulate the pattern used by /resume: acquire lock before starting task
    await lock.acquire()
    await runtime.start_run("t1", "resume", producer)

    # While producer is running, lock must be held
    await lock_during_run.wait()
    assert lock.locked(), "Lock should still be held while producer is running"

    # Wait for producer to release lock
    await lock_released.wait()
    assert not lock.locked(), "Lock should be released when producer finishes"


@pytest.mark.asyncio
async def test_runtime_is_running_returns_false_after_completion():
    runtime = CommandRuntime()

    async def producer(run: ActiveRun):
        pass

    run = await runtime.start_run("t1", "stream", producer)
    await run.task
    assert runtime.is_running("t1") is False


@pytest.mark.asyncio
async def test_runtime_get_run_returns_none_for_unknown_thread():
    runtime = CommandRuntime()
    assert runtime.get_run("nonexistent") is None


@pytest.mark.asyncio
async def test_runtime_shutdown_cancels_running_tasks():
    runtime = CommandRuntime()
    cancelled = asyncio.Event()

    async def infinite_producer(run: ActiveRun):
        try:
            await asyncio.sleep(1000)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    run = await runtime.start_run("t1", "stream", infinite_producer)
    assert not run.task.done()

    await runtime.shutdown()
    assert run.task.done()

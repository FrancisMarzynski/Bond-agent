#!/usr/bin/env python3
"""Browser E2E for detached runtime recovery in Shadow and Author modes.

Requires Python Playwright to be installed in the active interpreter:

    python3 scripts/playwright_detached_runtime_journey.py

Optional flags:

    --frontend-url http://localhost:3000
    --api-url http://127.0.0.1:8000
    --output-dir /tmp/bond-playwright-detached-runtime
    --headed
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Page, Response, TimeoutError as PlaywrightTimeoutError, sync_playwright


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def now_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def fetch_json(url: str, timeout: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_history(
    api_url: str,
    thread_id: str,
    *,
    timeout_seconds: float,
    expected_status: str | None = None,
    expected_stage: str | None = None,
    expected_pending_node: str | None = None,
    expected_can_resume: bool | None = None,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    history_url = f"{api_url}/api/chat/history/{thread_id}"
    last_payload: dict[str, Any] | None = None

    while time.time() < deadline:
        try:
            payload = fetch_json(history_url)
        except urllib.error.URLError:
            time.sleep(0.5)
            continue

        last_payload = payload
        matches = True

        if expected_status is not None:
            matches = matches and payload.get("session_status") == expected_status
        if expected_stage is not None:
            matches = matches and payload.get("stage") == expected_stage
        if expected_pending_node is not None:
            matches = matches and payload.get("pending_node") == expected_pending_node
        if expected_can_resume is not None:
            matches = matches and payload.get("can_resume") is expected_can_resume

        if matches:
            return payload

        time.sleep(1.0)

    raise TimeoutError(
        f"Timed out waiting for history for {thread_id}. Last payload: "
        f"{json.dumps(last_payload, ensure_ascii=False, indent=2)}"
    )


@dataclass
class NetworkEvent:
    method: str
    path: str
    status: int | None = None
    thread_header: str | None = None
    body: str | None = None


class NetworkTracker:
    def __init__(self, page: Page, api_url: str) -> None:
        self.page = page
        self.requests: list[NetworkEvent] = []
        self.responses: list[NetworkEvent] = []
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def _normalize(self, url: str) -> str:
        split = urlsplit(url)
        path = split.path
        if split.query:
            path = f"{path}?{split.query}"
        return path

    def _is_api_chat(self, url: str) -> bool:
        return "/api/chat/" in urlsplit(url).path

    def _on_request(self, request) -> None:
        if not self._is_api_chat(request.url):
            return
        self.requests.append(
            NetworkEvent(
                method=request.method,
                path=self._normalize(request.url),
                body=request.post_data,
            )
        )

    def _on_response(self, response: Response) -> None:
        request = response.request
        if not self._is_api_chat(request.url):
            return
        headers = response.headers
        self.responses.append(
            NetworkEvent(
                method=request.method,
                path=self._normalize(response.url),
                status=response.status,
                thread_header=headers.get("x-bond-thread-id"),
            )
        )

    def count_requests(self, method: str, path_prefix: str) -> int:
        return sum(
            1
            for event in self.requests
            if event.method == method and event.path.startswith(path_prefix)
        )

    def count_responses(self, method: str, path_prefix: str) -> int:
        return sum(
            1
            for event in self.responses
            if event.method == method and event.path.startswith(path_prefix)
        )

    def first_thread_header(self, method: str, path_prefix: str) -> str | None:
        for event in self.responses:
            if event.method == method and event.path.startswith(path_prefix):
                return event.thread_header
        return None

    def wait_for_request_count(
        self,
        method: str,
        path_prefix: str,
        expected_count: int,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.count_requests(method, path_prefix) >= expected_count:
                return
            self.page.wait_for_timeout(100)
        raise TimeoutError(
            f"Timed out waiting for {method} {path_prefix} count {expected_count}. "
            f"Current count: {self.count_requests(method, path_prefix)}"
        )

    def wait_for_response_count(
        self,
        method: str,
        path_prefix: str,
        expected_count: int,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.count_responses(method, path_prefix) >= expected_count:
                return
            self.page.wait_for_timeout(100)
        raise TimeoutError(
            f"Timed out waiting for {method} {path_prefix} response count {expected_count}. "
            f"Current count: {self.count_responses(method, path_prefix)}"
        )


def wait_for_session_thread_id(page: Page, timeout_ms: int = 10_000) -> str:
    page.wait_for_function(
        "() => Boolean(window.sessionStorage.getItem('bond_thread_id'))",
        timeout=timeout_ms,
    )
    thread_id = page.evaluate("() => window.sessionStorage.getItem('bond_thread_id')")
    assert_true(isinstance(thread_id, str) and len(thread_id) > 0, "Missing bond_thread_id in sessionStorage")
    return thread_id


def wait_for_text(page: Page, text: str, timeout_ms: int = 120_000) -> None:
    page.get_by_text(text, exact=False).wait_for(timeout=timeout_ms)


def screenshot(page: Page, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)


def run_shadow(frontend_url: str, api_url: str, output_dir: Path, *, headed: bool) -> dict[str, Any]:
    shadow_text = (
        "Nasza firma wdraża agentów AI, ale teksty marketingowe nadal brzmią zbyt generycznie. "
        "Potrzebujemy wersji bardziej konkretnej, technicznej i wiarygodnej dla odbiorcy B2B."
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        context = browser.new_context(viewport={"width": 1440, "height": 1024})
        page = context.new_page()
        tracker = NetworkTracker(page, api_url)

        try:
            page.goto(f"{frontend_url}/shadow", wait_until="domcontentloaded")
            page.get_by_placeholder("Wklej tekst do analizy...").fill(shadow_text)
            page.get_by_role("button", name="Analizuj styl").click()

            tracker.wait_for_request_count("POST", "/api/chat/stream", 1, timeout_seconds=10)
            tracker.wait_for_response_count("POST", "/api/chat/stream", 1, timeout_seconds=10)
            thread_id = wait_for_session_thread_id(page, timeout_ms=15_000)
            assert_true(
                tracker.first_thread_header("POST", "/api/chat/stream") == thread_id,
                "Shadow stream response missing matching X-Bond-Thread-Id header",
            )

            wait_for_history(
                api_url,
                thread_id,
                timeout_seconds=90,
                expected_status="paused",
                expected_pending_node="shadow_checkpoint",
                expected_can_resume=True,
            )
            wait_for_text(page, "Zatwierdzasz adnotacje?", timeout_ms=120_000)
            screenshot(page, output_dir / "shadow-01-checkpoint.png")

            history_before_reload = tracker.count_requests("GET", f"/api/chat/history/{thread_id}")
            page.reload(wait_until="domcontentloaded")

            tracker.wait_for_request_count(
                "GET",
                f"/api/chat/history/{thread_id}",
                history_before_reload + 1,
                timeout_seconds=10,
            )
            wait_for_text(page, "Zatwierdzasz adnotacje?", timeout_ms=20_000)

            corrected_value = page.locator(
                "textarea[placeholder='Poprawiona wersja pojawi się tutaj...']"
            ).input_value()
            mark_count = page.locator("mark").count()
            assert_true(mark_count > 0, "Shadow reload did not restore annotation highlights")
            assert_true(corrected_value.strip() != "", "Shadow reload did not restore corrected text")
            assert_true(
                tracker.count_requests("POST", "/api/chat/stream") == 1,
                "Shadow reload replayed POST /api/chat/stream",
            )
            screenshot(page, output_dir / "shadow-02-restored.png")

            page.get_by_role("button", name="Zatwierdź").click()
            tracker.wait_for_request_count("POST", "/api/chat/resume", 1, timeout_seconds=10)
            tracker.wait_for_response_count("POST", "/api/chat/resume", 1, timeout_seconds=10)
            assert_true(
                tracker.first_thread_header("POST", "/api/chat/resume") == thread_id,
                "Shadow resume response missing matching X-Bond-Thread-Id header",
            )

            page.reload(wait_until="domcontentloaded")
            final_history = wait_for_history(
                api_url,
                thread_id,
                timeout_seconds=60,
                expected_status="completed",
                expected_stage="done",
                expected_can_resume=False,
            )
            page.wait_for_timeout(1000)
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == 1,
                "Shadow reload replayed POST /api/chat/resume",
            )
            screenshot(page, output_dir / "shadow-03-final.png")

            return {
                "thread_id": thread_id,
                "stream_posts": tracker.count_requests("POST", "/api/chat/stream"),
                "resume_posts": tracker.count_requests("POST", "/api/chat/resume"),
                "history_gets": tracker.count_requests("GET", f"/api/chat/history/{thread_id}"),
                "final_history": {
                    "session_status": final_history["session_status"],
                    "stage": final_history["stage"],
                    "can_resume": final_history["can_resume"],
                },
            }
        finally:
            context.close()
            browser.close()


def run_author(frontend_url: str, api_url: str, output_dir: Path, *, headed: bool) -> dict[str, Any]:
    topic = f"Procedura walidacji runtime {uuid.uuid4()}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        context = browser.new_context(viewport={"width": 1440, "height": 1024})
        page = context.new_page()
        tracker = NetworkTracker(page, api_url)

        try:
            page.goto(frontend_url, wait_until="domcontentloaded")
            page.get_by_placeholder("Wpisz temat i wymagania...").fill(topic)
            page.get_by_role("button", name="Wyślij").click()

            tracker.wait_for_request_count("POST", "/api/chat/stream", 1, timeout_seconds=10)
            tracker.wait_for_response_count("POST", "/api/chat/stream", 1, timeout_seconds=10)
            thread_id = wait_for_session_thread_id(page, timeout_ms=15_000)
            assert_true(
                tracker.first_thread_header("POST", "/api/chat/stream") == thread_id,
                "Author stream response missing matching X-Bond-Thread-Id header",
            )

            page.wait_for_timeout(1000)
            page.reload(wait_until="domcontentloaded")

            tracker.wait_for_request_count("GET", f"/api/chat/history/{thread_id}", 1, timeout_seconds=10)
            assert_true(
                tracker.count_requests("POST", "/api/chat/stream") == 1,
                "Author reload replayed POST /api/chat/stream",
            )

            wait_for_history(
                api_url,
                thread_id,
                timeout_seconds=180,
                expected_status="paused",
                expected_pending_node="checkpoint_1",
                expected_can_resume=True,
            )
            page.get_by_role("button", name="Zatwierdź").wait_for(timeout=180_000)
            screenshot(page, output_dir / "author-01-checkpoint-1.png")

            page.get_by_role("button", name="Zatwierdź").click()
            tracker.wait_for_request_count("POST", "/api/chat/resume", 1, timeout_seconds=10)
            tracker.wait_for_response_count("POST", "/api/chat/resume", 1, timeout_seconds=10)
            assert_true(
                tracker.first_thread_header("POST", "/api/chat/resume") == thread_id,
                "Author resume response missing matching X-Bond-Thread-Id header",
            )

            page.wait_for_timeout(1000)
            page.reload(wait_until="domcontentloaded")
            tracker.wait_for_request_count("GET", f"/api/chat/history/{thread_id}", 2, timeout_seconds=10)
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == 1,
                "Author reload replayed POST /api/chat/resume after checkpoint_1",
            )

            wait_for_history(
                api_url,
                thread_id,
                timeout_seconds=240,
                expected_status="paused",
                expected_pending_node="checkpoint_2",
                expected_can_resume=True,
            )
            page.get_by_role("button", name="Zapisz do bazy").wait_for(timeout=240_000)
            screenshot(page, output_dir / "author-02-checkpoint-2.png")

            page.get_by_role("button", name="Zapisz do bazy").click()
            tracker.wait_for_request_count("POST", "/api/chat/resume", 2, timeout_seconds=10)
            tracker.wait_for_response_count("POST", "/api/chat/resume", 2, timeout_seconds=10)
            final_history = wait_for_history(
                api_url,
                thread_id,
                timeout_seconds=60,
                expected_status="completed",
                expected_stage="done",
                expected_can_resume=False,
            )
            screenshot(page, output_dir / "author-03-final.png")

            assert_true(
                tracker.count_requests("POST", "/api/chat/stream") == 1,
                "Author flow sent more than one POST /api/chat/stream",
            )
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == 2,
                "Author flow sent unexpected number of POST /api/chat/resume calls",
            )

            return {
                "thread_id": thread_id,
                "topic": topic,
                "stream_posts": tracker.count_requests("POST", "/api/chat/stream"),
                "resume_posts": tracker.count_requests("POST", "/api/chat/resume"),
                "history_gets": tracker.count_requests("GET", f"/api/chat/history/{thread_id}"),
                "final_history": {
                    "session_status": final_history["session_status"],
                    "stage": final_history["stage"],
                    "can_resume": final_history["can_resume"],
                },
            }
        finally:
            context.close()
            browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument(
        "--output-dir",
        default=f"/tmp/bond-playwright-detached-runtime-{now_slug()}",
    )
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "run_started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "frontend_url": args.frontend_url,
        "api_url": args.api_url,
        "output_dir": str(output_dir),
    }

    try:
        summary["shadow"] = run_shadow(
            args.frontend_url,
            args.api_url,
            output_dir,
            headed=args.headed,
        )
        summary["author"] = run_author(
            args.frontend_url,
            args.api_url,
            output_dir,
            headed=args.headed,
        )
        summary["status"] = "passed"
    except (AssertionError, PlaywrightTimeoutError, TimeoutError, urllib.error.URLError) as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

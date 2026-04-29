#!/usr/bin/env python3
"""Browser regression proof for reload + reject recovery in Shadow and Author."""

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

AUTHOR_EDITOR_SELECTOR = "[data-testid='author-draft-editor'] textarea"


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
    def __init__(self, page: Page) -> None:
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
        self.responses.append(
            NetworkEvent(
                method=request.method,
                path=self._normalize(response.url),
                status=response.status,
                thread_header=response.headers.get("x-bond-thread-id"),
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


def _expect_resume_response(page: Page):
    return page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith("/api/chat/resume")
    )


def _expect_stream_response(page: Page):
    return page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith("/api/chat/stream")
    )


def _author_input(page: Page):
    return page.locator("textarea").first


def _author_editor_value(page: Page) -> str:
    return page.locator(AUTHOR_EDITOR_SELECTOR).first.input_value()


def _wait_for_author_checkpoint(
    page: Page,
    api_url: str,
    thread_id: str,
    *,
    checkpoint_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    history_url = f"{api_url}/api/chat/history/{thread_id}"
    last_payload: dict[str, Any] | None = None

    while time.time() < deadline:
        payload = fetch_json(history_url)
        last_payload = payload
        hitl_pause = payload.get("hitlPause") or {}
        current_checkpoint_id = hitl_pause.get("checkpoint_id")

        if (
            payload.get("session_status") == "paused"
            and current_checkpoint_id == checkpoint_id
        ):
            return payload

        if (
            payload.get("session_status") == "paused"
            and current_checkpoint_id in {"duplicate_check", "low_corpus"}
        ):
            button_name = (
                "Kontynuuj mimo to"
                if current_checkpoint_id == "duplicate_check"
                else "Kontynuuj mimo ryzyka"
            )
            page.get_by_role("button", name=button_name).click()
            page.wait_for_timeout(500)
            continue

        time.sleep(1.0)

    raise TimeoutError(
        f"Timed out waiting for checkpoint {checkpoint_id} for {thread_id}. "
        f"Last payload: {json.dumps(last_payload, ensure_ascii=False, indent=2)}"
    )


def run_shadow_regression(
    frontend_url: str,
    api_url: str,
    output_dir: Path,
    *,
    headed: bool,
) -> dict[str, Any]:
    shadow_text = (
        "Nasza firma wdraża agentów AI, ale teksty marketingowe nadal brzmią zbyt generycznie. "
        "Potrzebujemy wersji bardziej konkretnej, technicznej i wiarygodnej dla odbiorcy B2B."
    )
    reject_feedback = "Zachowaj techniczny ton, ale skróć wstęp i dodaj bardziej konkretne przykłady B2B."

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        context = browser.new_context(viewport={"width": 1440, "height": 1024})
        page = context.new_page()
        tracker = NetworkTracker(page)

        try:
            page.goto(f"{frontend_url}/shadow", wait_until="domcontentloaded")
            page.get_by_placeholder("Wklej tekst do analizy...").fill(shadow_text)
            with _expect_stream_response(page) as stream_info:
                page.get_by_role("button", name="Analizuj styl").click()
            stream_response = stream_info.value
            assert_true(stream_response.ok, "Shadow stream request failed")

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
            screenshot(page, output_dir / "shadow-01-initial-checkpoint.png")

            history_gets_before_reload = tracker.count_requests("GET", f"/api/chat/history/{thread_id}")
            page.reload(wait_until="domcontentloaded")
            tracker.wait_for_request_count(
                "GET",
                f"/api/chat/history/{thread_id}",
                history_gets_before_reload + 1,
                timeout_seconds=10,
            )
            wait_for_history(
                api_url,
                thread_id,
                timeout_seconds=30,
                expected_status="paused",
                expected_pending_node="shadow_checkpoint",
                expected_can_resume=True,
            )
            assert_true(
                tracker.count_requests("POST", "/api/chat/stream") == 1,
                "Shadow reload replayed POST /api/chat/stream",
            )

            page.get_by_placeholder("Napisz co poprawić (wymagane do odrzucenia)...").fill(reject_feedback)
            with _expect_resume_response(page) as reject_info:
                page.get_by_role("button", name="Odrzuć").click()
            reject_response = reject_info.value
            assert_true(reject_response.ok, "Shadow reject resume request failed")
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == 1,
                "Shadow reject should produce exactly one resume request before reload",
            )

            history_gets_before_recovery_reload = tracker.count_requests("GET", f"/api/chat/history/{thread_id}")
            page.reload(wait_until="domcontentloaded")
            tracker.wait_for_request_count(
                "GET",
                f"/api/chat/history/{thread_id}",
                history_gets_before_recovery_reload + 1,
                timeout_seconds=10,
            )
            recovered_history = wait_for_history(
                api_url,
                thread_id,
                timeout_seconds=120,
                expected_status="paused",
                expected_pending_node="shadow_checkpoint",
                expected_can_resume=True,
            )
            assert_true(
                recovered_history["hitlPause"]["iteration_count"] == 1,
                "Shadow reject recovery did not increment iteration_count",
            )
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == 1,
                "Shadow reload replayed POST /api/chat/resume after reject",
            )
            screenshot(page, output_dir / "shadow-02-recovered-after-reject.png")

            history_gets_before_second_reload = tracker.count_requests("GET", f"/api/chat/history/{thread_id}")
            page.reload(wait_until="domcontentloaded")
            tracker.wait_for_request_count(
                "GET",
                f"/api/chat/history/{thread_id}",
                history_gets_before_second_reload + 1,
                timeout_seconds=10,
            )
            wait_for_history(
                api_url,
                thread_id,
                timeout_seconds=30,
                expected_status="paused",
                expected_pending_node="shadow_checkpoint",
                expected_can_resume=True,
            )
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == 1,
                "Second Shadow reload replayed POST /api/chat/resume",
            )

            with _expect_resume_response(page) as approve_info:
                page.get_by_role("button", name="Zatwierdź").click()
            approve_response = approve_info.value
            assert_true(approve_response.ok, "Shadow approve resume request failed")
            final_history = wait_for_history(
                api_url,
                thread_id,
                timeout_seconds=60,
                expected_status="completed",
                expected_stage="done",
                expected_can_resume=False,
            )
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == 2,
                "Shadow flow produced unexpected number of resume requests",
            )
            screenshot(page, output_dir / "shadow-03-final.png")

            return {
                "thread_id": thread_id,
                "stream_posts": tracker.count_requests("POST", "/api/chat/stream"),
                "resume_posts": tracker.count_requests("POST", "/api/chat/resume"),
                "final_history": {
                    "session_status": final_history["session_status"],
                    "stage": final_history["stage"],
                    "can_resume": final_history["can_resume"],
                },
            }
        finally:
            context.close()
            browser.close()


def run_author_checkpoint_1_regression(
    frontend_url: str,
    api_url: str,
    output_dir: Path,
    *,
    headed: bool,
) -> dict[str, Any]:
    nonce = uuid.uuid4().hex[:8]
    brief = (
        f"Temat: ROI AI w marketingu producentów armatury przemysłowej {nonce}\n"
        "Słowa kluczowe: AI w marketingu B2B, lead generation, automatyzacja marketingu\n"
        "Wymagania: Ton ekspercki.\n"
        "Dodaj sekcję o ROI i case study z Polski."
    )
    reject_note = "Dodaj osobną sekcję H2 o ROI wdrożenia i konkretny case study z polskiego rynku."

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        context = browser.new_context(viewport={"width": 1440, "height": 1024})
        page = context.new_page()
        tracker = NetworkTracker(page)

        try:
            page.goto(frontend_url, wait_until="domcontentloaded")
            _author_input(page).fill(brief)
            with _expect_stream_response(page) as stream_info:
                page.get_by_role("button", name="Wyślij").click()
            stream_response = stream_info.value
            assert_true(stream_response.ok, "Author cp1 stream request failed")

            thread_id = wait_for_session_thread_id(page, timeout_ms=15_000)
            assert_true(
                tracker.first_thread_header("POST", "/api/chat/stream") == thread_id,
                "Author cp1 stream response missing matching X-Bond-Thread-Id header",
            )

            _wait_for_author_checkpoint(
                page,
                api_url,
                thread_id,
                checkpoint_id="checkpoint_1",
                timeout_seconds=180,
            )
            page.get_by_role("button", name="Zatwierdź").wait_for(timeout=180_000)
            resume_posts_before_cp1 = tracker.count_requests("POST", "/api/chat/resume")
            screenshot(page, output_dir / "author-cp1-01-initial-checkpoint.png")

            history_gets_before_reload = tracker.count_requests("GET", f"/api/chat/history/{thread_id}")
            page.reload(wait_until="domcontentloaded")
            tracker.wait_for_request_count(
                "GET",
                f"/api/chat/history/{thread_id}",
                history_gets_before_reload + 1,
                timeout_seconds=10,
            )
            _wait_for_author_checkpoint(
                page,
                api_url,
                thread_id,
                checkpoint_id="checkpoint_1",
                timeout_seconds=30,
            )
            assert_true(
                tracker.count_requests("POST", "/api/chat/stream") == 1,
                "Author cp1 reload replayed POST /api/chat/stream",
            )

            page.get_by_role("button", name="Odrzuć").click()
            page.get_by_placeholder(
                "Np. Sekcja wstępna jest zbyt ogólna, dodaj konkretne przykłady..."
            ).fill(reject_note)
            with _expect_resume_response(page) as reject_info:
                page.get_by_role("button", name="Wyślij poprawki").click()
            reject_response = reject_info.value
            assert_true(reject_response.ok, "Author cp1 reject resume request failed")
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == resume_posts_before_cp1 + 1,
                "Author cp1 reject should produce exactly one resume request before reload",
            )

            history_gets_before_recovery_reload = tracker.count_requests("GET", f"/api/chat/history/{thread_id}")
            page.reload(wait_until="domcontentloaded")
            tracker.wait_for_request_count(
                "GET",
                f"/api/chat/history/{thread_id}",
                history_gets_before_recovery_reload + 1,
                timeout_seconds=10,
            )
            recovered_history = _wait_for_author_checkpoint(
                page,
                api_url,
                thread_id,
                checkpoint_id="checkpoint_1",
                timeout_seconds=180,
            )
            recovered_pause = recovered_history.get("hitlPause") or {}
            assert_true(
                recovered_pause.get("cp1_iterations") == 1,
                "Author cp1 reject recovery did not increment cp1_iterations",
            )
            assert_true(
                bool(recovered_pause.get("heading_structure")),
                "Author cp1 reject recovery did not restore heading_structure",
            )
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == resume_posts_before_cp1 + 1,
                "Author cp1 reload replayed POST /api/chat/resume after reject",
            )
            screenshot(page, output_dir / "author-cp1-02-recovered-after-reject.png")

            with _expect_resume_response(page) as approve_info:
                page.get_by_role("button", name="Zatwierdź").click()
            approve_response = approve_info.value
            assert_true(approve_response.ok, "Author cp1 approve resume request failed")
            checkpoint_2_history = _wait_for_author_checkpoint(
                page,
                api_url,
                thread_id,
                checkpoint_id="checkpoint_2",
                timeout_seconds=240,
            )
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == resume_posts_before_cp1 + 2,
                "Author cp1 flow produced unexpected number of resume requests",
            )
            screenshot(page, output_dir / "author-cp1-03-next-checkpoint.png")

            return {
                "thread_id": thread_id,
                "stream_posts": tracker.count_requests("POST", "/api/chat/stream"),
                "resume_posts_total": tracker.count_requests("POST", "/api/chat/resume"),
                "resume_posts_during_cp1_flow": (
                    tracker.count_requests("POST", "/api/chat/resume") - resume_posts_before_cp1
                ),
                "cp1_iterations_after_reject": recovered_pause.get("cp1_iterations"),
                "next_checkpoint": checkpoint_2_history.get("pending_node"),
            }
        finally:
            context.close()
            browser.close()


def run_author_checkpoint_2_regression(
    frontend_url: str,
    api_url: str,
    output_dir: Path,
    *,
    headed: bool,
) -> dict[str, Any]:
    nonce = uuid.uuid4().hex[:8]
    brief = (
        f"Temat: Governance AI w biurach projektowych dla inwestycji mostowych {nonce}\n"
        "Słowa kluczowe: AI w firmie projektowej, governance AI\n"
        "Wymagania: Ton krytyczny, bez obietnic sprzedażowych.\n"
        "Pokaż ryzyka, proces wdrożenia i checklistę decyzyjną."
    )
    reject_feedback = "Dodaj więcej konkretów o procesie wdrożenia, ryzykach i kryteriach decyzyjnych."

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        context = browser.new_context(viewport={"width": 1440, "height": 1024})
        page = context.new_page()
        tracker = NetworkTracker(page)

        try:
            page.goto(frontend_url, wait_until="domcontentloaded")
            _author_input(page).fill(brief)
            with _expect_stream_response(page) as stream_info:
                page.get_by_role("button", name="Wyślij").click()
            stream_response = stream_info.value
            assert_true(stream_response.ok, "Author cp2 stream request failed")

            thread_id = wait_for_session_thread_id(page, timeout_ms=15_000)
            assert_true(
                tracker.first_thread_header("POST", "/api/chat/stream") == thread_id,
                "Author cp2 stream response missing matching X-Bond-Thread-Id header",
            )

            _wait_for_author_checkpoint(
                page,
                api_url,
                thread_id,
                checkpoint_id="checkpoint_1",
                timeout_seconds=180,
            )
            resume_posts_before_cp2 = tracker.count_requests("POST", "/api/chat/resume")
            with _expect_resume_response(page) as approve_cp1_info:
                page.get_by_role("button", name="Zatwierdź").click()
            approve_cp1_response = approve_cp1_info.value
            assert_true(approve_cp1_response.ok, "Author cp1 approve request failed in cp2 flow")

            checkpoint_2_history = _wait_for_author_checkpoint(
                page,
                api_url,
                thread_id,
                checkpoint_id="checkpoint_2",
                timeout_seconds=240,
            )
            page.get_by_role("button", name="Zapisz do bazy").wait_for(timeout=240_000)
            draft_before_reject = checkpoint_2_history.get("draft", "")
            assert_true(
                bool(draft_before_reject or _author_editor_value(page)),
                "Author cp2 initial draft is empty",
            )
            screenshot(page, output_dir / "author-cp2-01-initial-checkpoint.png")

            history_gets_before_reload = tracker.count_requests("GET", f"/api/chat/history/{thread_id}")
            page.reload(wait_until="domcontentloaded")
            tracker.wait_for_request_count(
                "GET",
                f"/api/chat/history/{thread_id}",
                history_gets_before_reload + 1,
                timeout_seconds=10,
            )
            _wait_for_author_checkpoint(
                page,
                api_url,
                thread_id,
                checkpoint_id="checkpoint_2",
                timeout_seconds=30,
            )
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == resume_posts_before_cp2 + 1,
                "Author cp2 reload replayed prior POST /api/chat/resume",
            )

            page.get_by_role("button", name="Odrzuć").click()
            page.get_by_placeholder(
                "Np. Sekcja wstępna jest zbyt ogólna, dodaj konkretne przykłady..."
            ).fill(reject_feedback)
            with _expect_resume_response(page) as reject_info:
                page.get_by_role("button", name="Wyślij poprawki").click()
            reject_response = reject_info.value
            assert_true(reject_response.ok, "Author cp2 reject resume request failed")
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == resume_posts_before_cp2 + 2,
                "Author cp2 reject should produce exactly one additional resume request before reload",
            )

            history_gets_before_recovery_reload = tracker.count_requests("GET", f"/api/chat/history/{thread_id}")
            page.reload(wait_until="domcontentloaded")
            tracker.wait_for_request_count(
                "GET",
                f"/api/chat/history/{thread_id}",
                history_gets_before_recovery_reload + 1,
                timeout_seconds=10,
            )
            recovered_history = _wait_for_author_checkpoint(
                page,
                api_url,
                thread_id,
                checkpoint_id="checkpoint_2",
                timeout_seconds=240,
            )
            recovered_pause = recovered_history.get("hitlPause") or {}
            assert_true(
                recovered_pause.get("cp2_iterations") == 1,
                "Author cp2 reject recovery did not increment cp2_iterations",
            )
            assert_true(
                bool(recovered_history.get("draft") or _author_editor_value(page)),
                "Author cp2 reject recovery did not restore regenerated draft",
            )
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == resume_posts_before_cp2 + 2,
                "Author cp2 reload replayed POST /api/chat/resume after reject",
            )
            screenshot(page, output_dir / "author-cp2-02-recovered-after-reject.png")

            with _expect_resume_response(page) as approve_cp2_info:
                page.get_by_role("button", name="Zapisz do bazy").click()
            approve_cp2_response = approve_cp2_info.value
            assert_true(approve_cp2_response.ok, "Author cp2 approve/save request failed")
            final_history = wait_for_history(
                api_url,
                thread_id,
                timeout_seconds=60,
                expected_status="completed",
                expected_stage="done",
                expected_can_resume=False,
            )
            assert_true(
                tracker.count_requests("POST", "/api/chat/resume") == resume_posts_before_cp2 + 3,
                "Author cp2 flow produced unexpected number of resume requests",
            )
            screenshot(page, output_dir / "author-cp2-03-final.png")

            return {
                "thread_id": thread_id,
                "stream_posts": tracker.count_requests("POST", "/api/chat/stream"),
                "resume_posts_total": tracker.count_requests("POST", "/api/chat/resume"),
                "resume_posts_during_cp2_flow": (
                    tracker.count_requests("POST", "/api/chat/resume") - resume_posts_before_cp2
                ),
                "cp2_iterations_after_reject": recovered_pause.get("cp2_iterations"),
                "initial_draft_length": len(draft_before_reject),
                "recovered_draft_length": len(recovered_history.get("draft", "")),
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
        default=f"/tmp/bond-playwright-checkpoint-recovery-{now_slug()}",
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
        summary["shadow"] = run_shadow_regression(
            args.frontend_url,
            args.api_url,
            output_dir,
            headed=args.headed,
        )
        summary["author_checkpoint_1"] = run_author_checkpoint_1_regression(
            args.frontend_url,
            args.api_url,
            output_dir,
            headed=args.headed,
        )
        summary["author_checkpoint_2"] = run_author_checkpoint_2_regression(
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

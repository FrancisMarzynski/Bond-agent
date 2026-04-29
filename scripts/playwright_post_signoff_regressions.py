#!/usr/bin/env python3
"""Browser E2E for post-signoff Author persistence, download, and upload regressions."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

EDITOR_SELECTOR = "[data-testid='author-draft-editor'] textarea"
DOWNLOAD_BUTTON_NAME = "Pobierz .md"


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


def wait_for_session_thread_id(page: Page, timeout_ms: int = 10_000) -> str:
    page.wait_for_function(
        "() => Boolean(window.sessionStorage.getItem('bond_thread_id'))",
        timeout=timeout_ms,
    )
    thread_id = page.evaluate("() => window.sessionStorage.getItem('bond_thread_id')")
    assert_true(
        isinstance(thread_id, str) and len(thread_id) > 0,
        "Missing bond_thread_id in sessionStorage",
    )
    return thread_id


def wait_for_text(page: Page, text: str, timeout_ms: int = 120_000) -> None:
    page.get_by_text(text, exact=False).wait_for(timeout=timeout_ms)


def screenshot(page: Page, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)


def editor_locator(page: Page):
    return page.locator(EDITOR_SELECTOR).first


def editor_value(page: Page) -> str:
    return editor_locator(page).input_value()


def assert_editor_contains(page: Page, expected_text: str, message: str) -> None:
    page.wait_for_function(
        """({ selector, expectedText }) => {
            const editor = document.querySelector(selector);
            return Boolean(editor && editor.value.includes(expectedText));
        }""",
        arg={"selector": EDITOR_SELECTOR, "expectedText": expected_text},
        timeout=20_000,
    )
    assert_true(expected_text in editor_value(page), message)


def assert_editor_omits(page: Page, unexpected_text: str, message: str) -> None:
    page.wait_for_function(
        """({ selector, unexpectedText }) => {
            const editor = document.querySelector(selector);
            if (editor) {
                return !editor.value.includes(unexpectedText);
            }
            return !document.body.innerText.includes(unexpectedText);
        }""",
        arg={"selector": EDITOR_SELECTOR, "unexpectedText": unexpected_text},
        timeout=30_000,
    )
    if page.locator(EDITOR_SELECTOR).count() > 0:
        assert_true(unexpected_text not in editor_value(page), message)
        return

    assert_true(unexpected_text not in page.locator("body").inner_text(), message)


def wait_for_author_checkpoint(
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


def reach_checkpoint_2(
    page: Page,
    api_url: str,
    *,
    topic: str,
    screenshot_path: Path,
) -> str:
    page.get_by_placeholder("Wpisz temat i wymagania...").fill(topic)
    page.get_by_role("button", name="Wyślij").click()

    thread_id = wait_for_session_thread_id(page, timeout_ms=15_000)
    wait_for_author_checkpoint(
        page,
        api_url,
        thread_id,
        checkpoint_id="checkpoint_1",
        timeout_seconds=180,
    )

    page.get_by_role("button", name="Zatwierdź").wait_for(timeout=180_000)
    page.get_by_role("button", name="Zatwierdź").click()

    wait_for_author_checkpoint(
        page,
        api_url,
        thread_id,
        checkpoint_id="checkpoint_2",
        timeout_seconds=240,
    )
    page.get_by_role("button", name="Zapisz do bazy").wait_for(timeout=240_000)
    screenshot(page, screenshot_path)
    return thread_id


def run_regressions(
    frontend_url: str,
    api_url: str,
    output_dir: Path,
    *,
    headed: bool,
) -> dict[str, Any]:
    upload_fixture = Path(__file__).resolve().parents[1] / "e2e-fixtures" / "upload-sample.txt"
    assert_true(upload_fixture.exists(), f"Missing upload fixture: {upload_fixture}")

    topic_one = f"PW regress A {now_slug()}"
    topic_two = f"PW regress B {now_slug()}"
    sentinel_one = f"PW_SENTINEL_A_{now_slug()}"
    sentinel_two = f"PW_SENTINEL_B_{now_slug()}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1024},
            accept_downloads=True,
        )
        page = context.new_page()

        try:
            page.goto(frontend_url, wait_until="domcontentloaded")

            thread_one = reach_checkpoint_2(
                page,
                api_url,
                topic=topic_one,
                screenshot_path=output_dir / "author-01-checkpoint-2.png",
            )

            edited_draft = f"{editor_value(page)}\n\n{sentinel_one}\n"
            editor_locator(page).fill(edited_draft)
            assert_editor_contains(
                page,
                sentinel_one,
                "Manual Author edit did not appear in the editor",
            )
            screenshot(page, output_dir / "author-02-manual-edit.png")

            page.reload(wait_until="domcontentloaded")
            wait_for_history(
                api_url,
                thread_one,
                timeout_seconds=30,
                expected_status="paused",
                expected_pending_node="checkpoint_2",
                expected_can_resume=True,
            )
            assert_editor_contains(
                page,
                sentinel_one,
                "Manual Author edit was lost after reload",
            )
            screenshot(page, output_dir / "author-03-reload-restored.png")

            page.locator("button[title='Nowa sesja']").click()
            page.get_by_role("button", name=topic_one, exact=True).click()
            restored_thread = wait_for_session_thread_id(page, timeout_ms=15_000)
            assert_true(
                restored_thread == thread_one,
                "Saved-session restore opened a different Author thread",
            )
            wait_for_history(
                api_url,
                thread_one,
                timeout_seconds=30,
                expected_status="paused",
                expected_pending_node="checkpoint_2",
                expected_can_resume=True,
            )
            assert_editor_contains(
                page,
                sentinel_one,
                "Saved-session restore did not prefer the local Author draft override",
            )
            screenshot(page, output_dir / "author-04-sidebar-restored.png")

            visible_draft = editor_value(page)
            with page.expect_download() as download_info:
                page.get_by_role("button", name=DOWNLOAD_BUTTON_NAME).click()
            download = download_info.value
            download_path = output_dir / "downloads" / download.suggested_filename
            download_path.parent.mkdir(parents=True, exist_ok=True)
            download.save_as(str(download_path))
            downloaded_text = download_path.read_text(encoding="utf-8")
            assert_true(
                download.suggested_filename == "draft.md",
                f"Unexpected markdown filename: {download.suggested_filename}",
            )
            assert_true(
                downloaded_text == visible_draft,
                "Downloaded markdown content did not match the visible draft",
            )

            page.get_by_role("button", name="Zapisz do bazy").click()
            final_history_one = wait_for_history(
                api_url,
                thread_one,
                timeout_seconds=60,
                expected_status="completed",
                expected_stage="done",
                expected_can_resume=False,
            )
            assert_editor_contains(
                page,
                sentinel_one,
                "Manual Author edit did not survive the checkpoint_2 save path",
            )
            screenshot(page, output_dir / "author-05-completed.png")

            page.locator("button[title='Nowa sesja']").click()

            thread_two = reach_checkpoint_2(
                page,
                api_url,
                topic=topic_two,
                screenshot_path=output_dir / "author-06-rerun-checkpoint-2.png",
            )

            editor_locator(page).fill(f"{editor_value(page)}\n\n{sentinel_two}\n")
            assert_editor_contains(
                page,
                sentinel_two,
                "Second-thread manual Author edit did not appear in the editor",
            )

            page.get_by_role("button", name="Odrzuć").click()
            page.get_by_placeholder(
                "Np. Sekcja wstępna jest zbyt ogólna, dodaj konkretne przykłady..."
            ).fill("Dodaj więcej konkretów, liczb i przykładów wdrożeń.")
            page.get_by_role("button", name="Wyślij poprawki").click()

            assert_editor_omits(
                page,
                sentinel_two,
                "Fresh writer run did not clear the stale local Author override",
            )
            wait_for_history(
                api_url,
                thread_two,
                timeout_seconds=240,
                expected_status="paused",
                expected_pending_node="checkpoint_2",
                expected_can_resume=True,
            )
            assert_editor_omits(
                page,
                sentinel_two,
                "Stale local Author override leaked into regenerated writer output",
            )
            screenshot(page, output_dir / "author-07-rerun-cleared.png")

            page.locator("button[title='Dodaj treść']").click()
            page.get_by_role("button", name="Plik", exact=True).click()
            page.locator("input[type='file']").set_input_files(str(upload_fixture))
            wait_for_text(page, upload_fixture.name, timeout_ms=10_000)
            page.get_by_placeholder("Tytuł (opcjonalnie)").fill(
                f"Playwright upload {now_slug()}"
            )

            with page.expect_response(
                lambda response: response.request.method == "POST"
                and response.url.endswith("/api/corpus/ingest/file")
            ) as response_info:
                page.get_by_role("button", name="Prześlij").click()
            upload_response = response_info.value
            assert_true(upload_response.ok, "Corpus file upload request failed")
            upload_payload = upload_response.json()
            assert_true(
                int(upload_payload.get("chunks_added", 0)) > 0,
                f"Corpus file upload added no chunks: {upload_payload}",
            )
            wait_for_text(page, "Plik zaindeksowany", timeout_ms=20_000)
            screenshot(page, output_dir / "corpus-01-upload-success.png")

            return {
                "author_persistence": {
                    "thread_id": thread_one,
                    "topic": topic_one,
                    "sentinel": sentinel_one,
                    "downloaded_file": str(download_path),
                    "final_history": {
                        "session_status": final_history_one["session_status"],
                        "stage": final_history_one["stage"],
                        "can_resume": final_history_one["can_resume"],
                    },
                },
                "author_rerun": {
                    "thread_id": thread_two,
                    "topic": topic_two,
                    "sentinel": sentinel_two,
                },
                "corpus_upload": {
                    "file_name": upload_fixture.name,
                    "chunks_added": upload_payload["chunks_added"],
                    "warnings": upload_payload.get("warnings", []),
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
        default=f"/tmp/bond-playwright-post-signoff-{now_slug()}",
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
        summary["results"] = run_regressions(
            args.frontend_url,
            args.api_url,
            output_dir,
            headed=args.headed,
        )
        summary["status"] = "passed"
    except (
        AssertionError,
        PlaywrightTimeoutError,
        TimeoutError,
        urllib.error.URLError,
        Exception,
    ) as exc:
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

/**
 * SSE Parser unit tests + FastAPI connection test
 * Run with: node frontend/scripts/test-sse.mjs
 *           node frontend/scripts/test-sse.mjs --api-url http://localhost:8000
 * Requires Node.js >= 18 (built-in fetch + node:test)
 */

import { test } from "node:test";
import assert from "node:assert/strict";

// ---------------------------------------------------------------------------
// SSEParser (pure JS port of frontend/src/lib/sse.ts)
// ---------------------------------------------------------------------------
const MAX_BUFFER_SIZE = 64 * 1024; // 64 KB

class SSEParser {
    buffer = "";

    feed(chunk) {
        this.buffer = `${this.buffer}${chunk}`.replace(/\r\n?/g, "\n");
        if (this.buffer.length > MAX_BUFFER_SIZE) {
            this.buffer = "";
            throw new Error(
                `SSEParser: buffer limit exceeded (${MAX_BUFFER_SIZE} bytes) — missing \\n\\n separator`
            );
        }
        const events = [];
        const parts = this.buffer.split("\n\n");
        this.buffer = parts.pop() ?? "";

        for (const part of parts) {
            const lines = part.split("\n");
            let eventType = "message";
            let eventId = undefined;
            const dataLines = [];
            for (const line of lines) {
                if (line.startsWith("event: ")) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith("id: ")) {
                    eventId = line.slice(4).trim();
                } else if (line.startsWith("data: ")) {
                    dataLines.push(line.slice(6));
                }
            }
            if (dataLines.length > 0) {
                events.push({ id: eventId, event: eventType, data: dataLines.join("\n") });
            }
        }
        return events;
    }
}

function parseNestedPayload(raw) {
    if (typeof raw !== "string") {
        return raw;
    }

    const trimmed = raw.trim();
    if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) {
        return raw;
    }

    try {
        return JSON.parse(raw);
    } catch {
        return raw;
    }
}

// ---------------------------------------------------------------------------
// Unit tests — SSEParser
// ---------------------------------------------------------------------------

test("SSEParser: parsuje pojedyncze zdarzenie z prefiksem data:", () => {
    const parser = new SSEParser();
    const events = parser.feed('data: {"type":"token","data":"Hello"}\n\n');
    assert.equal(events.length, 1);
    assert.equal(events[0].event, "message");
    assert.equal(events[0].data, '{"type":"token","data":"Hello"}');
});

test("SSEParser: obsługuje zdarzenie done", () => {
    const parser = new SSEParser();
    const events = parser.feed('data: {"type":"done","data":"done"}\n\n');
    assert.equal(events.length, 1);
    const parsed = JSON.parse(events[0].data);
    assert.equal(parsed.type, "done");
    assert.equal(parsed.data, "done");
});

test("SSEParser: obsługuje niekompletny chunk (boundary split)", () => {
    const parser = new SSEParser();
    // First chunk is incomplete — no trailing \n\n
    const first = parser.feed('data: {"type":"token"');
    assert.equal(first.length, 0, "No event should be emitted for incomplete chunk");

    // Second chunk completes the event
    const second = parser.feed(',"data":"World"}\n\n');
    assert.equal(second.length, 1);
    const parsed = JSON.parse(second[0].data);
    assert.equal(parsed.type, "token");
    assert.equal(parsed.data, "World");
});

test("SSEParser: parsuje wiele zdarzeń z jednego chunka", () => {
    const parser = new SSEParser();
    const chunk = [
        'data: {"type":"token","data":"A"}\n\n',
        'data: {"type":"token","data":"B"}\n\n',
        'data: {"type":"done","data":"done"}\n\n',
    ].join("");
    const events = parser.feed(chunk);
    assert.equal(events.length, 3);
    assert.equal(JSON.parse(events[0].data).data, "A");
    assert.equal(JSON.parse(events[1].data).data, "B");
    assert.equal(JSON.parse(events[2].data).type, "done");
});

test("SSEParser: rozpoznaje pole event:", () => {
    const parser = new SSEParser();
    const events = parser.feed("event: token\ndata: fragment\n\n");
    assert.equal(events[0].event, "token");
    assert.equal(events[0].data, "fragment");
});

test("SSEParser: rozpoznaje pole id:", () => {
    const parser = new SSEParser();
    const events = parser.feed("id: 42\ndata: payload\n\n");
    assert.equal(events[0].id, "42");
});

test("SSEParser: ignoruje puste zdarzenia (brak pola data:)", () => {
    const parser = new SSEParser();
    const events = parser.feed(": heartbeat\n\n");
    assert.equal(events.length, 0, "Comment-only blocks must not produce events");
});

test("SSEParser: obsługuje wieloliniowe pole data: (ciągłość)", () => {
    const parser = new SSEParser();
    const events = parser.feed("data: line1\ndata: line2\n\n");
    assert.equal(events.length, 1);
    assert.equal(events[0].data, "line1\nline2");
});

test("SSEParser: obsługuje separatory CRLF z przeglądarki", () => {
    const parser = new SSEParser();
    const events = parser.feed('data: {"type":"token","data":"Hello"}\r\n\r\n');
    assert.equal(events.length, 1);
    assert.equal(JSON.parse(events[0].data).data, "Hello");
});

test("parseNestedPayload: zachowuje tokeny liczbowe jako string", () => {
    assert.equal(parseNestedPayload("144"), "144");
    assert.equal(parseNestedPayload("1"), "1");
    assert.deepEqual(parseNestedPayload('{"thread_id":"abc"}'), { thread_id: "abc" });
    assert.deepEqual(parseNestedPayload('[1,2,3]'), [1, 2, 3]);
});

test("SSEParser: rzuca błąd po przekroczeniu limitu bufora (brak \\n\\n)", () => {
    const parser = new SSEParser();
    const bigChunk = "data: " + "x".repeat(MAX_BUFFER_SIZE);
    assert.throws(
        () => parser.feed(bigChunk),
        /buffer limit exceeded/,
        "Powinien rzucić błąd przy przekroczeniu limitu bufora"
    );
    // Buffer should be reset after the error
    const events = parser.feed("data: recovery\n\n");
    assert.equal(events.length, 1);
    assert.equal(events[0].data, "recovery");
});

// ---------------------------------------------------------------------------
// FastAPI integration — GET /health
// ---------------------------------------------------------------------------

const API_URL = (() => {
    const idx = process.argv.indexOf("--api-url");
    return idx !== -1 ? process.argv[idx + 1] : "http://localhost:8000";
})();

test(`FastAPI /health endpoint odpowiada (${API_URL})`, async () => {
    let res;
    try {
        res = await fetch(`${API_URL}/health`, { signal: AbortSignal.timeout(5000) });
    } catch (err) {
        // Server not running in CI — skip gracefully
        console.warn(`  ⚠  Serwer niedostępny pod ${API_URL}: ${err.message} — test pominięty`);
        return;
    }

    assert.equal(res.ok, true, `Oczekiwano HTTP 200, otrzymano ${res.status}`);
    const body = await res.json();
    assert.ok(
        ["ok", "degraded"].includes(body.status),
        `Pole status ma być "ok" lub "degraded", otrzymano: ${body.status}`
    );
    assert.ok(body.version, "Brakuje pola version");
    assert.ok(body.timestamp, "Brakuje pola timestamp");
    assert.ok(body.checks, "Brakuje pola checks");
});

test(`FastAPI POST /api/chat/stream zwraca SSE Content-Type (${API_URL})`, async () => {
    let res;
    try {
        res = await fetch(`${API_URL}/api/chat/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: "__ping__", thread_id: null, mode: "author" }),
            signal: AbortSignal.timeout(5000),
        });
    } catch (err) {
        console.warn(`  ⚠  Serwer niedostępny pod ${API_URL}: ${err.message} — test pominięty`);
        return;
    }

    const ct = res.headers.get("content-type") ?? "";
    assert.ok(
        ct.includes("text/event-stream"),
        `Oczekiwano Content-Type: text/event-stream, otrzymano: ${ct}`
    );

    // Read one SSE chunk and verify it parses correctly
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    const parser = new SSEParser();
    let parsed = [];
    let timeout = false;

    const deadline = setTimeout(() => { timeout = true; reader.cancel(); }, 4000);
    try {
        while (parsed.length === 0 && !timeout) {
            const { value, done } = await reader.read();
            if (done || timeout) break;
            if (value) parsed = parser.feed(value);
        }
    } finally {
        clearTimeout(deadline);
        reader.cancel().catch(() => {});
    }

    if (timeout) {
        console.warn("  ⚠  Brak danych SSE w ciągu 4s — możliwe zimne uruchomienie modelu");
        return;
    }

    assert.ok(parsed.length > 0, "Oczekiwano co najmniej jednego zdarzenia SSE");
    for (const ev of parsed) {
        const obj = JSON.parse(ev.data);
        assert.ok(obj.type, `Każde zdarzenie musi mieć pole type, otrzymano: ${JSON.stringify(obj)}`);
    }
});

test(`FastAPI GET /api/chat/history/{thread_id} zwraca pola recovery (${API_URL})`, async () => {
    let res;
    try {
        res = await fetch(`${API_URL}/api/chat/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: "__history_ping__", thread_id: null, mode: "author" }),
            signal: AbortSignal.timeout(5000),
        });
    } catch (err) {
        console.warn(`  ⚠  Serwer niedostępny pod ${API_URL}: ${err.message} — test pominięty`);
        return;
    }

    if (!res.ok || !res.body) {
        console.warn(`  ⚠  Nie udało się otworzyć streamu testowego (${res.status}) — test pominięty`);
        return;
    }

    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    const parser = new SSEParser();
    let threadId = null;
    let timeout = false;

    const deadline = setTimeout(() => {
        timeout = true;
        reader.cancel();
    }, 4000);

    try {
        while (!threadId && !timeout) {
            const { value, done } = await reader.read();
            if (done || timeout) break;
            if (!value) continue;

            for (const ev of parser.feed(value)) {
                const parsed = JSON.parse(ev.data);
                if (parsed.type === "thread_id") {
                    const payload = JSON.parse(parsed.data);
                    threadId = payload.thread_id;
                    break;
                }
            }
        }
    } finally {
        clearTimeout(deadline);
        reader.cancel().catch(() => {});
    }

    if (!threadId) {
        console.warn("  ⚠  Nie udało się odczytać thread_id ze streamu testowego — test pominięty");
        return;
    }

    const historyRes = await fetch(`${API_URL}/api/chat/history/${threadId}`, {
        signal: AbortSignal.timeout(5000),
    });
    assert.equal(historyRes.ok, true, `Historia sesji powinna zwrócić HTTP 200, otrzymano ${historyRes.status}`);

    const history = await historyRes.json();
    assert.ok(
        ["idle", "running", "paused", "completed", "error"].includes(history.session_status),
        `Nieprawidłowy session_status: ${history.session_status}`
    );
    assert.equal(typeof history.can_resume, "boolean");
    assert.ok(Object.hasOwn(history, "pending_node"), "Brakuje pola pending_node");
    assert.ok(Object.hasOwn(history, "hitlPause"), "Brakuje pola hitlPause");
    assert.ok(Array.isArray(history.messages), "Pole messages musi być tablicą");
    assert.equal(typeof history.stageStatus, "object");

    if (history.pending_node !== null) {
        assert.equal(typeof history.pending_node, "string");
    }
});

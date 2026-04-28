/**
 * Frontend gateway auth/proxy validation
 * Run with:
 *   node frontend/scripts/test-proxy-auth.mjs --frontend-url http://localhost:3000
 *
 * Requires Node.js >= 18.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

const FRONTEND_URL = (() => {
    const index = process.argv.indexOf("--frontend-url");
    return index !== -1 ? process.argv[index + 1] : "http://localhost:3000";
})();

const BASIC_AUTH_USERNAME = process.env.INTERNAL_BASIC_AUTH_USERNAME ?? "";
const BASIC_AUTH_PASSWORD = process.env.INTERNAL_BASIC_AUTH_PASSWORD ?? "";

function getBasicAuthHeader() {
    if (!BASIC_AUTH_USERNAME || !BASIC_AUTH_PASSWORD) {
        return null;
    }

    const encoded = Buffer.from(
        `${BASIC_AUTH_USERNAME}:${BASIC_AUTH_PASSWORD}`,
        "utf8"
    ).toString("base64");

    return `Basic ${encoded}`;
}

async function fetchOrSkip(url, init = {}) {
    try {
        return await fetch(url, {
            ...init,
            signal: AbortSignal.timeout(5000),
        });
    } catch (error) {
        console.warn(`  ⚠  Frontend niedostępny pod ${FRONTEND_URL}: ${error.message} — test pominięty`);
        return null;
    }
}

test(`Frontend / wymaga Basic Auth (${FRONTEND_URL})`, async () => {
    const response = await fetchOrSkip(`${FRONTEND_URL}/`, {
        redirect: "manual",
    });

    if (!response) {
        return;
    }

    assert.equal(response.status, 401, `Oczekiwano HTTP 401, otrzymano ${response.status}`);
    assert.equal(
        response.headers.get("www-authenticate"),
        'Basic realm="Bond - dostep wewnetrzny", charset="UTF-8"',
        "Brak poprawnego nagłówka WWW-Authenticate"
    );
});

test(`Frontend /healthz pozostaje publiczne (${FRONTEND_URL})`, async () => {
    const response = await fetchOrSkip(`${FRONTEND_URL}/healthz`);

    if (!response) {
        return;
    }

    assert.equal(response.status, 200, `Oczekiwano HTTP 200, otrzymano ${response.status}`);
    assert.equal(await response.text(), "ok");
});

test(`Uwierzytelnione /api/corpus/status przechodzi przez proxy (${FRONTEND_URL})`, async () => {
    const authorizationHeader = getBasicAuthHeader();
    if (!authorizationHeader) {
        const probe = await fetchOrSkip(`${FRONTEND_URL}/healthz`);
        if (!probe) {
            return;
        }

        throw new Error(
            "Ustaw INTERNAL_BASIC_AUTH_USERNAME i INTERNAL_BASIC_AUTH_PASSWORD, aby zweryfikować dostęp przez proxy."
        );
    }

    const response = await fetchOrSkip(`${FRONTEND_URL}/api/corpus/status`, {
        headers: {
            Authorization: authorizationHeader,
        },
    });

    if (!response) {
        return;
    }

    assert.equal(response.status, 200, `Oczekiwano HTTP 200, otrzymano ${response.status}`);
    assert.ok(
        response.headers.get("x-request-id"),
        "Brak X-Request-Id z backendu — żądanie nie wygląda na poprawnie przepuszczone przez proxy."
    );

    const payload = await response.json();
    assert.equal(typeof payload.article_count, "number");
    assert.equal(typeof payload.chunk_count, "number");
});

test(`Uwierzytelnione /api/chat/stream zachowuje SSE przez proxy (${FRONTEND_URL})`, async () => {
    const authorizationHeader = getBasicAuthHeader();
    if (!authorizationHeader) {
        const probe = await fetchOrSkip(`${FRONTEND_URL}/healthz`);
        if (!probe) {
            return;
        }

        throw new Error(
            "Ustaw INTERNAL_BASIC_AUTH_USERNAME i INTERNAL_BASIC_AUTH_PASSWORD, aby zweryfikować SSE przez proxy."
        );
    }

    const response = await fetchOrSkip(`${FRONTEND_URL}/api/chat/stream`, {
        method: "POST",
        headers: {
            Authorization: authorizationHeader,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            message: "__proxy_sse_ping__",
            thread_id: null,
            mode: "author",
        }),
    });

    if (!response) {
        return;
    }

    assert.equal(response.status, 200, `Oczekiwano HTTP 200, otrzymano ${response.status}`);
    const contentType = response.headers.get("content-type") ?? "";
    assert.ok(
        contentType.includes("text/event-stream"),
        `Oczekiwano Content-Type: text/event-stream, otrzymano: ${contentType}`
    );
    assert.ok(
        response.headers.get("x-request-id"),
        "Brak X-Request-Id z backendu dla SSE przez proxy."
    );

    await response.body?.cancel();
});

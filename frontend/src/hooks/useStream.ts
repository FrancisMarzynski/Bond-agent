"use client";
import { useChatStore } from "@/store/chatStore";
import { SSEParser } from "@/lib/sse";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAX_RETRIES = 3;
const RETRY_DELAY = 3000;

let activeController: AbortController | null = null;

export function stopStream() {
    if (activeController) {
        activeController.abort();
        activeController = null;
    }
    useChatStore.getState().setStreaming(false);
}

async function consumeStream(
    response: Response,
    onThreadId: (id: string) => void
): Promise<void> {
    const store = useChatStore.getState();
    const parser = new SSEParser();
    const reader = response.body!
        .pipeThrough(new TextDecoderStream())
        .getReader();

    try {
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            if (!value) continue;

            const events = parser.feed(value);
            for (const { event, data } of events) {
                try {
                    const parsed = JSON.parse(data);
                    if (!parsed || typeof parsed !== "object") {
                        throw new Error("Invalid JSON structure");
                    }
                    switch (event) {
                        case "thread_id":
                            onThreadId(parsed.thread_id);
                            break;
                        case "token":
                            store.appendDraftToken(parsed.token);
                            break;
                        case "stage":
                            store.setStage(parsed.stage, parsed.status);
                            break;
                        case "message":
                            store.addMessage({ role: "assistant", content: parsed.content });
                            break;
                        case "hitl_pause":
                            store.setHitlPause({
                                checkpoint_id: parsed.checkpoint_id,
                                type: parsed.type,
                                iterations_remaining: parsed.iterations_remaining,
                            });
                            store.setStreaming(false);
                            return; // Stream ends at HITL pause
                        case "error":
                            const currentStage = store.stage !== "idle" && store.stage !== "done" ? store.stage : "error";
                            store.setStage(currentStage, "error");
                            store.addMessage({ role: "assistant", content: `Error: ${parsed.message}` });
                            store.setStreaming(false);
                            return;
                        case "done":
                            store.setStage("done", "complete");
                            store.setStreaming(false);
                            return;
                    }
                } catch (err) {
                    // Skip malformed JSON — log in development
                    if (process.env.NODE_ENV === "development") {
                        console.warn("SSE parse error or invalid format:", data, err);
                    }
                }
            }
        }
    } finally {
        reader.releaseLock(); // Always release to avoid memory leak
    }
}

export async function startStream(
    message: string,
    threadId: string | null,
    mode: "author" | "shadow",
    onThreadId: (id: string) => void
): Promise<void> {
    const store = useChatStore.getState();
    if (store.isStreaming) {
        console.warn("Stream is already active. Blocking startStream.");
        return;
    }

    store.setStreaming(true);
    store.addMessage({ role: "user", content: message });

    if (activeController) {
        activeController.abort();
    }
    activeController = new AbortController();

    let attempt = 0;

    while (attempt <= MAX_RETRIES) {
        try {
            const response = await fetch(`${API_URL}/api/chat/stream`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message, thread_id: threadId, mode }),
                signal: activeController.signal,
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            await consumeStream(response, onThreadId);
            return; // Stream consumed successfully or ended gracefully
        } catch (e: unknown) {
            if (e instanceof Error && e.name === "AbortError") {
                return; // Gracefully exit if stream was intentionally aborted
            }
            attempt++;
            if (attempt <= MAX_RETRIES) {
                store.addMessage({
                    role: "assistant",
                    content: `Połączenie zerwane. Próbuję ponownie (${attempt}/${MAX_RETRIES})...`
                });
                await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY));
            } else {
                store.addMessage({
                    role: "assistant",
                    content: `[Błąd krytyczny]: Nie udało się nawiązać stabilnego połączenia po ${MAX_RETRIES} próbach. Odśwież stronę.`
                });
                store.setStreaming(false);
                const currentStage = store.stage !== "idle" && store.stage !== "done" ? store.stage : "error";
                store.setStage(currentStage, "error");
            }
        }
    }
}

export async function resumeStream(
    threadId: string,
    action: "approve" | "approve_save" | "reject",
    feedback: string | null,
    onThreadId: (id: string) => void
): Promise<void> {
    const store = useChatStore.getState();
    if (store.isStreaming) {
        console.warn("Stream is already active. Blocking resumeStream.");
        return;
    }

    store.setHitlPause(null);
    store.setStreaming(true);

    if (activeController) {
        activeController.abort();
    }
    activeController = new AbortController();

    let attempt = 0;

    while (attempt <= MAX_RETRIES) {
        try {
            const response = await fetch(`${API_URL}/api/chat/resume`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ thread_id: threadId, action, feedback }),
                signal: activeController.signal,
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            await consumeStream(response, onThreadId);
            return;
        } catch (e: unknown) {
            if (e instanceof Error && e.name === "AbortError") {
                return; // Gracefully exit if stream was intentionally aborted
            }
            attempt++;
            if (attempt <= MAX_RETRIES) {
                store.addMessage({
                    role: "assistant",
                    content: `Połączenie zerwane. Wznawianie sesji (${attempt}/${MAX_RETRIES})...`
                });
                await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY));
            } else {
                store.addMessage({
                    role: "assistant",
                    content: `[Błąd krytyczny]: Nie udało się wznowić odpowiedzi po ${MAX_RETRIES} próbach. Odśwież stronę.`
                });
                store.setStreaming(false);
                const currentStage = store.stage !== "idle" && store.stage !== "done" ? store.stage : "error";
                store.setStage(currentStage, "error");
            }
        }
    }
}

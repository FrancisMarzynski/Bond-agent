"use client";
import { useChatStore } from "@/store/chatStore";
import { SSEParser } from "@/lib/sse";
import { z } from "zod";

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
            for (const { id, event, data } of events) {
                if (id) {
                    store.setLastEventId(id);
                }
                try {
                    const parsed = JSON.parse(data);

                    switch (event) {
                        case "thread_id": {
                            const schema = z.object({ thread_id: z.string() });
                            const result = schema.safeParse(parsed);
                            if (!result.success) throw new Error("Invalid thread_id event data");
                            onThreadId(result.data.thread_id);
                            break;
                        }
                        case "token": {
                            const schema = z.object({ token: z.string() });
                            const result = schema.safeParse(parsed);
                            if (!result.success) throw new Error("Invalid token event data");
                            store.appendDraftToken(result.data.token);
                            break;
                        }
                        case "stage": {
                            const schema = z.object({ stage: z.string(), status: z.string() });
                            const result = schema.safeParse(parsed);
                            if (!result.success) throw new Error("Invalid stage event data");
                            store.setStage(result.data.stage as any, result.data.status as any);
                            break;
                        }
                        case "message": {
                            const schema = z.object({ content: z.string() });
                            const result = schema.safeParse(parsed);
                            if (!result.success) throw new Error("Invalid message event data");
                            store.addMessage({ role: "assistant", content: result.data.content });
                            break;
                        }
                        case "hitl_pause": {
                            const schema = z.object({
                                checkpoint_id: z.string(),
                                type: z.string(),
                                iterations_remaining: z.number().optional()
                            });
                            const result = schema.safeParse(parsed);
                            if (!result.success) throw new Error("Invalid hitl_pause event data");
                            store.setHitlPause({
                                checkpoint_id: result.data.checkpoint_id,
                                type: result.data.type,
                                iterations_remaining: result.data.iterations_remaining,
                            });
                            store.setStreaming(false);
                            return; // Stream ends at HITL pause
                        }
                        case "error": {
                            const schema = z.object({ message: z.string() });
                            const result = schema.safeParse(parsed);
                            if (!result.success) throw new Error("Invalid error event data");
                            const currentStage = store.stage !== "idle" && store.stage !== "done" ? store.stage : "error";
                            store.setStage(currentStage, "error");
                            store.addMessage({ role: "assistant", content: `Error: ${result.data.message}` });
                            store.setStreaming(false);
                            return;
                        }
                        case "node_start": {
                            const schema = z.object({ data: z.string().optional() }).catchall(z.any());
                            schema.safeParse(parsed);
                            // Możliwa integracja statusu konkretnego węzła z Zustand tutaj
                            break;
                        }
                        case "node_end": {
                            const schema = z.object({ data: z.string().optional() }).catchall(z.any());
                            schema.safeParse(parsed);
                            break;
                        }
                        case "heartbeat": {
                            // Cichy Ping - podtrzymuje otwarte procesy proxy zapobiegając Gateway Timeout
                            if (process.env.NODE_ENV === "development") {
                                console.log("[SSE] Otrzymano Heartbeat (ping) z serwera by podtrzymać strumień...");
                            }
                            break;
                        }
                        case "done":
                            store.setStage("done", "complete");
                            store.setStreaming(false);
                            return;
                        default:
                            if (process.env.NODE_ENV === "development") {
                                console.warn(`Unhandled SSE event type: ${event}`);
                            }
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
            const headers: Record<string, string> = {
                "Content-Type": "application/json",
            };
            if (store.lastEventId) {
                headers["Last-Event-ID"] = store.lastEventId;
            }

            const response = await fetch(`${API_URL}/api/chat/stream`, {
                method: "POST",
                headers,
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
                store.setSystemAlert(`Połączenie zerwane. Próbuję ponownie (${attempt}/${MAX_RETRIES})...`);
                await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY));
            } else {
                store.setSystemAlert(`[Błąd krytyczny]: Nie udało się nawiązać stabilnego połączenia po ${MAX_RETRIES} próbach. Odśwież stronę.`);
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
            const headers: Record<string, string> = {
                "Content-Type": "application/json",
            };
            if (store.lastEventId) {
                headers["Last-Event-ID"] = store.lastEventId;
            }

            const response = await fetch(`${API_URL}/api/chat/resume`, {
                method: "POST",
                headers,
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
                store.setSystemAlert(`Połączenie zerwane. Wznawianie sesji (${attempt}/${MAX_RETRIES})...`);
                await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY));
            } else {
                store.setSystemAlert(`[Błąd krytyczny]: Nie udało się wznowić odpowiedzi po ${MAX_RETRIES} próbach. Odśwież stronę.`);
                store.setStreaming(false);
                const currentStage = store.stage !== "idle" && store.stage !== "done" ? store.stage : "error";
                store.setStage(currentStage, "error");
            }
        }
    }
}

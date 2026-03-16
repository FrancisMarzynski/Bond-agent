"use client";
import { useEffect, useCallback } from "react";
import { useChatStore } from "@/store/chatStore";
import { SSEParser } from "@/lib/sse";
import { z } from "zod";
import { API_URL } from "@/config";
const MAX_RETRIES = 3;
const RETRY_DELAY = 3000;

// ---------------------------------------------------------------------------
// Zod schemas — defined once at module scope, not re-created on every event.
// ---------------------------------------------------------------------------
const ThreadIdSchema = z.object({ thread_id: z.string() });
const TokenSchema = z.object({ token: z.string() });
const StageSchema = z.object({ stage: z.string(), status: z.string() });
const MessageSchema = z.object({ content: z.string() });
const HitlPauseSchema = z.object({
    checkpoint_id: z.string(),
    type: z.string(),
    iterations_remaining: z.number().optional(),
});
const ErrorSchema = z.object({ message: z.string() });

// ---------------------------------------------------------------------------
// Internal stream consumer
// ---------------------------------------------------------------------------
async function consumeStream(
    response: Response,
    signal: AbortSignal,
    onThreadId: (id: string) => void
): Promise<void> {
    const store = useChatStore.getState();
    const parser = new SSEParser();
    const reader = response.body!
        .pipeThrough(new TextDecoderStream())
        .getReader();

    try {
        while (true) {
            if (signal.aborted) break;
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

                    // The backend emits events in the format: data: {"type": "<event_type>", "data": "<payload_string>"}
                    // Therefore, the SSE `event` header is missing, defaulting to "message".
                    // We must determine the true event type from `parsed.type`.
                    const eventType = parsed.type || event;

                    // Extract payload. If parsed.data is a string that looks like JSON, parse it.
                    let payload: any;
                    if (typeof parsed.data === "string") {
                        try {
                            payload = JSON.parse(parsed.data);
                        } catch (e) {
                            payload = parsed.data; // e.g. plain text for 'token', 'done', 'heartbeat'
                        }
                    } else {
                        payload = parsed.data;
                    }

                    switch (eventType) {
                        case "thread_id": {
                            const result = ThreadIdSchema.safeParse(payload);
                            if (!result.success) throw new Error("Invalid thread_id event data");
                            onThreadId(result.data.thread_id);
                            break;
                        }
                        case "token": {
                            // Backend may send plain string for token data
                            const tokenContent = typeof payload === "string" ? payload : (payload.token || "");
                            if (!tokenContent) throw new Error("Invalid token event data");
                            store.appendDraftToken(tokenContent);
                            break;
                        }
                        case "stage": {
                            const result = StageSchema.safeParse(payload);
                            if (!result.success) throw new Error("Invalid stage event data");
                            store.setStage(result.data.stage as any, result.data.status as any);
                            break;
                        }
                        case "message": { // Keeping this just in case backend ever sends direct message
                            const result = MessageSchema.safeParse(payload);
                            if (!result.success) throw new Error("Invalid message event data");
                            store.addMessage({ role: "assistant", content: result.data.content });
                            break;
                        }
                        case "hitl_pause": {
                            const result = HitlPauseSchema.safeParse(payload);
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
                            // Payload could be a string or JSON depending on backend formatting
                            const errorMessage = typeof payload === "string" ? payload : (payload.message || payload.data || "Unknown error");
                            const currentStage =
                                store.stage !== "idle" && store.stage !== "done"
                                    ? store.stage
                                    : "error";
                            store.setStage(currentStage, "error");
                            store.addMessage({
                                role: "assistant",
                                content: `Error: ${errorMessage}`,
                            });
                            store.setStreaming(false);
                            return;
                        }
                        case "node_start":
                        case "node_end":
                            // Informational lifecycle events — no store integration yet.
                            break;
                        case "heartbeat":
                            // Silent ping — keeps proxy connections alive during long generation pauses.
                            if (process.env.NODE_ENV === "development") {
                                console.log(
                                    "[SSE] Otrzymano Heartbeat (ping) z serwera by podtrzymać strumień..."
                                );
                            }
                            break;
                        case "done":
                            store.setStage("done", "complete");
                            store.setStreaming(false);
                            return;
                        default:
                            if (process.env.NODE_ENV === "development") {
                                console.warn(`Unhandled SSE event type: ${eventType}`, parsed);
                            }
                    }
                } catch (err) {
                    // Skip malformed JSON — log in development only
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

// ---------------------------------------------------------------------------
// Retry loop helper
// ---------------------------------------------------------------------------
async function fetchWithRetry(
    url: string,
    body: string,
    signal: AbortSignal,
    onThreadId: (id: string) => void
): Promise<void> {
    const store = useChatStore.getState();
    let attempt = 0;

    while (attempt <= MAX_RETRIES) {
        try {
            const headers: Record<string, string> = {
                "Content-Type": "application/json",
            };
            if (store.lastEventId) {
                headers["Last-Event-ID"] = store.lastEventId;
            }

            const response = await fetch(url, {
                method: "POST",
                headers,
                body,
                signal,
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            await consumeStream(response, signal, onThreadId);
            return; // Success — exit retry loop
        } catch (e: unknown) {
            if (e instanceof Error && e.name === "AbortError") {
                return; // Intentional abort — exit cleanly
            }
            attempt++;
            if (attempt <= MAX_RETRIES) {
                store.setSystemAlert(
                    `Połączenie zerwane. Próbuję ponownie (${attempt}/${MAX_RETRIES})...`
                );
                await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY));
            } else {
                store.setSystemAlert(
                    `[Błąd krytyczny]: Nie udało się nawiązać stabilnego połączenia po ${MAX_RETRIES} próbach. Odśwież stronę.`
                );
                store.setStreaming(false);
                const currentStage =
                    store.stage !== "idle" && store.stage !== "done" ? store.stage : "error";
                store.setStage(currentStage, "error");
            }
        }
    }
}

// ---------------------------------------------------------------------------
// React hook — the single public export.
//
// Encapsulates AbortController lifecycle: the controller lives in Zustand
// (isolated per-store instance) and is automatically aborted when the
// consuming component unmounts via useEffect cleanup.
// ---------------------------------------------------------------------------
export function useStream() {
    const { createController, abortController } = useChatStore();

    // Automatically stop any in-flight stream when the component unmounts.
    useEffect(() => {
        return () => {
            abortController();
        };
    }, [abortController]);

    const startStream = useCallback(
        async (
            message: string,
            threadId: string | null,
            mode: "author" | "shadow",
            onThreadId: (id: string) => void
        ): Promise<void> => {
            const store = useChatStore.getState();
            if (store.isStreaming) {
                console.warn("Stream is already active. Blocking startStream.");
                return;
            }

            store.setStreaming(true);
            store.addMessage({ role: "user", content: message });

            const signal = createController();
            await fetchWithRetry(
                `${API_URL}/api/chat/stream`,
                JSON.stringify({ message, thread_id: threadId, mode }),
                signal,
                onThreadId
            );
        },
        [createController]
    );

    const resumeStream = useCallback(
        async (
            threadId: string,
            action: "approve" | "approve_save" | "reject",
            feedback: string | null,
            onThreadId: (id: string) => void
        ): Promise<void> => {
            const store = useChatStore.getState();
            if (store.isStreaming) {
                console.warn("Stream is already active. Blocking resumeStream.");
                return;
            }

            store.setHitlPause(null);
            store.setStreaming(true);

            const signal = createController();
            await fetchWithRetry(
                `${API_URL}/api/chat/resume`,
                JSON.stringify({ thread_id: threadId, action, feedback }),
                signal,
                onThreadId
            );
        },
        [createController]
    );

    const stopStream = useCallback(() => {
        abortController();
    }, [abortController]);

    return { startStream, resumeStream, stopStream };
}

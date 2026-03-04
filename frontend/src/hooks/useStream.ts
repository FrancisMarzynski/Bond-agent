"use client";
import { useChatStore } from "@/store/chatStore";
import { SSEParser } from "@/lib/sse";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
                            store.setStage("error", "running");
                            store.addMessage({ role: "assistant", content: `Error: ${parsed.message}` });
                            store.setStreaming(false);
                            return;
                        case "done":
                            store.setStage("done", "complete");
                            store.setStreaming(false);
                            return;
                    }
                } catch {
                    // Skip malformed JSON — log in development
                    if (process.env.NODE_ENV === "development") {
                        console.warn("SSE parse error:", data);
                    }
                }
            }
        }
    } finally {
        reader.releaseLock(); // Always release to avoid memory leak
    }
}

export async function startStream(message: string, threadId: string | null, mode: "author" | "shadow", onThreadId: (id: string) => void): Promise<void> {
    const store = useChatStore.getState();
    store.setStreaming(true);
    store.addMessage({ role: "user", content: message });

    const response = await fetch(`${API_URL}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, thread_id: threadId, mode }),
    });

    if (!response.ok) {
        store.addMessage({ role: "assistant", content: "Connection error. Please try again." });
        store.setStreaming(false);
        return;
    }

    await consumeStream(response, onThreadId);
}

export async function resumeStream(
    threadId: string,
    action: "approve" | "approve_save" | "reject",
    feedback: string | null,
    onThreadId: (id: string) => void
): Promise<void> {
    const store = useChatStore.getState();
    store.setHitlPause(null);
    store.setStreaming(true);

    const response = await fetch(`${API_URL}/api/chat/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: threadId, action, feedback }),
    });

    if (!response.ok) {
        store.addMessage({ role: "assistant", content: "Resume error. Please try again." });
        store.setStreaming(false);
        return;
    }

    await consumeStream(response, onThreadId);
}

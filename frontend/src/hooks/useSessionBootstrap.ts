"use client";
import { useEffect, useState } from "react";
import { useChatStore } from "@/store/chatStore";
import { useShadowStore } from "@/store/shadowStore";
import { loadSessionHistory, SessionHistoryNotFoundError } from "@/hooks/useSession";

const STORAGE_KEY = "bond_thread_id";
const MODE_KEY = "bond_mode";

const MAX_RECOVERY_POLLS = 20;
const RECOVERY_POLL_DELAY_MS = 1_500;

function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * One-time startup bootstrap hook.
 *
 * Reads sessionStorage once on mount, restores the thread ID + mode into the
 * store, fetches history for the most recent session, and — if the session is
 * still running because the backend is executing a committed command — polls
 * /history until it settles into a durable state.
 *
 * MUST be called from exactly one place: SessionProvider. Consumer components
 * (Sidebar, CheckpointPanel, etc.) call useSession() which no longer triggers
 * restore side effects on every mount.
 */
export function useSessionBootstrap(): { isRestoring: boolean } {
    const [isRestoring, setIsRestoring] = useState(true);

    useEffect(() => {
        let cancelled = false;

        async function bootstrap() {
            const storedThread = sessionStorage.getItem(STORAGE_KEY);
            const storedMode = sessionStorage.getItem(MODE_KEY);

            if (storedMode === "author" || storedMode === "shadow") {
                useChatStore.getState().setMode(storedMode);
            }

            if (!storedThread) {
                setIsRestoring(false);
                return;
            }

            useChatStore.getState().setThreadId(storedThread);

            try {
                const history = await loadSessionHistory(storedThread, { mode: "restore" });

                if (cancelled) return;
                setIsRestoring(false);

                // If the backend is still executing a committed command, poll
                // until the session reaches a durable state.
                if (history.session_status === "running") {
                    await pollUntilSettled(storedThread, cancelled);
                }
            } catch (err) {
                if (cancelled) return;
                setIsRestoring(false);

                if (err instanceof SessionHistoryNotFoundError) {
                    sessionStorage.removeItem(STORAGE_KEY);
                    useChatStore.getState().setThreadId(null);
                    useShadowStore.getState().resetShadow();
                } else {
                    console.error("Session bootstrap error:", err);
                }
            }
        }

        bootstrap();

        return () => {
            cancelled = true;
        };
    }, []); // Intentionally empty — runs exactly once on mount

    return { isRestoring };
}

async function pollUntilSettled(threadId: string, cancelled: boolean): Promise<void> {
    const store = useChatStore.getState();
    store.setRecoveringSession(true);

    try {
        for (let i = 0; i < MAX_RECOVERY_POLLS; i++) {
            if (cancelled) return;
            await sleep(RECOVERY_POLL_DELAY_MS);
            if (cancelled) return;

            try {
                const history = await loadSessionHistory(threadId, { mode: "recovery" });
                if (history.session_status !== "running") {
                    return;
                }
            } catch {
                return;
            }
        }
    } finally {
        useChatStore.getState().setRecoveringSession(false);
    }
}

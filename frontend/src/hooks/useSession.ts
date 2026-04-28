"use client";
import { useEffect, useState, useCallback } from "react"; // useState still needed for sessions list
import { useChatStore, type ChatMessage } from "@/store/chatStore";
import { useShadowStore } from "@/store/shadowStore";
import { API_URL } from "@/config";
import {
    buildSessionHydration,
    type HydrationMode,
    type SessionHistoryResponse,
    type SessionHydrationSnapshot,
} from "@/lib/streamRecovery";

const STORAGE_KEY = "bond_thread_id";
const MODE_KEY = "bond_mode";
const SESSIONS_KEY = "bond_sessions";

export interface SessionMeta {
    id: string;
    title: string;
    updatedAt: number;
}

export class SessionHistoryNotFoundError extends Error {
    constructor(threadId: string) {
        super(`Sesja ${threadId} nie istnieje na serwerze.`);
        this.name = "SessionHistoryNotFoundError";
    }
}

function getSessionSnapshot(): SessionHydrationSnapshot {
    const chat = useChatStore.getState();
    const shadow = useShadowStore.getState();

    return {
        chat: {
            messages: chat.messages,
            draft: chat.draft,
            hitlPause: chat.hitlPause,
            stage: chat.stage,
            stageStatus: chat.stageStatus,
        },
        shadow: {
            originalText: shadow.originalText,
            annotations: shadow.annotations,
            shadowCorrectedText: shadow.shadowCorrectedText,
        },
    };
}

function hydrateSessionStores(
    history: SessionHistoryResponse,
    options: { mode?: HydrationMode; clearRecoveredPause?: boolean } = {}
): SessionHistoryResponse {
    const current = getSessionSnapshot();
    const hydration = buildSessionHydration(history, current, options);

    useChatStore.setState({
        messages: hydration.chat.messages,
        draft: hydration.chat.draft,
        hitlPause: hydration.chat.hitlPause,
        stage: hydration.chat.stage,
        stageStatus: {
            ...current.chat.stageStatus,
            ...hydration.chat.stageStatus,
        },
    });
    useShadowStore.setState({
        originalText: hydration.shadow.originalText,
        annotations: hydration.shadow.annotations,
        shadowCorrectedText: hydration.shadow.shadowCorrectedText,
    });

    return history;
}

export async function loadSessionHistory(
    id: string,
    options: { mode?: HydrationMode; clearRecoveredPause?: boolean } = {}
): Promise<SessionHistoryResponse> {
    const res = await fetch(`${API_URL}/api/chat/history/${id}`);

    if (!res.ok) {
        if (res.status === 404) {
            throw new SessionHistoryNotFoundError(id);
        }
        throw new Error(`Nie udało się pobrać historii sesji (${res.status}).`);
    }

    const data = (await res.json()) as SessionHistoryResponse;
    return hydrateSessionStores(data, options);
}

export function useSession() {
    const { threadId, setThreadId, mode, setMode, resetSession } = useChatStore();

    const [sessions, setSessions] = useState<SessionMeta[]>([]);

    useEffect(() => {
        const loadSessions = () => {
            const storedSessions = localStorage.getItem(SESSIONS_KEY);
            if (storedSessions) {
                try {
                    setSessions(JSON.parse(storedSessions));
                } catch (e) {
                    console.error("Failed to parse sessions", e);
                }
            }
        };

        loadSessions();

        const onStorage = (e: StorageEvent) => {
            if (e.key === SESSIONS_KEY) loadSessions();
        };
        const onLocal = () => loadSessions();

        window.addEventListener("storage", onStorage);
        window.addEventListener("bond_sessions_changed", onLocal);
        return () => {
            window.removeEventListener("storage", onStorage);
            window.removeEventListener("bond_sessions_changed", onLocal);
        };
    }, []);

    // Used by switchSession only — not called on every mount.
    const restoreSessionHistory = useCallback(async (id: string) => {
        try {
            await loadSessionHistory(id, { mode: "restore" });
        } catch (err) {
            console.error("Przywracanie sesji przerwane:", err);
            if (err instanceof SessionHistoryNotFoundError) {
                sessionStorage.removeItem(STORAGE_KEY);
                setThreadId(null);
            }
        }
    }, [setThreadId]);

    const saveSessionMeta = (id: string, messages: ChatMessage[]) => {
        const storedSessions = localStorage.getItem(SESSIONS_KEY);
        let updated: SessionMeta[] = [];
        try {
            if (storedSessions) updated = JSON.parse(storedSessions);
        } catch (e) {
            console.error("Failed to parse sessions", e);
        }

        const idx = updated.findIndex((s) => s.id === id);
        
        const userMsg = messages.find((m) => m.role === "user");
        let title = userMsg ? userMsg.content.slice(0, 30) : `Sesja ${id.slice(0, 8)}`;
        if (userMsg && userMsg.content.length >= 30) title += "...";

        if (idx > -1) {
            updated[idx].updatedAt = Date.now();
            updated[idx].title = title;
        } else {
            updated.unshift({ id, title, updatedAt: Date.now() });
        }
        
        const limited = updated.slice(0, 20); // Keep last 20
        localStorage.setItem(SESSIONS_KEY, JSON.stringify(limited));
        setSessions(limited);
        window.dispatchEvent(new Event("bond_sessions_changed"));
    };

    const persistThreadId = (id: string) => {
        sessionStorage.setItem(STORAGE_KEY, id);
        setThreadId(id);
        
        setTimeout(() => {
            const msgs = useChatStore.getState().messages;
            saveSessionMeta(id, msgs);
        }, 100);
    };

    const persistMode = (newMode: "author" | "shadow") => {
        sessionStorage.setItem(MODE_KEY, newMode);
        setMode(newMode);
    };

    const newSession = () => {
        sessionStorage.removeItem(STORAGE_KEY);
        useShadowStore.getState().resetShadow();
        resetSession();
    };

    const switchSession = (id: string) => {
        sessionStorage.setItem(STORAGE_KEY, id);
        useShadowStore.getState().resetShadow();
        resetSession();
        setThreadId(id);
        restoreSessionHistory(id);
    };

    return {
        threadId,
        mode,
        sessions,
        persistThreadId,
        persistMode,
        newSession,
        switchSession,
        loadSessionHistory: restoreSessionHistory,
    };
}

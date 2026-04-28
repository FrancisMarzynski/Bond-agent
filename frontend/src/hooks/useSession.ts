"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useChatStore, type ChatMessage } from "@/store/chatStore";
import { useShadowStore } from "@/store/shadowStore";
import { API_URL } from "@/config";
import {
    buildSessionHydration,
    type HydrationMode,
    normalizeSessionMode,
    sessionModeToPath,
    type SessionHistoryResponse,
    type SessionHydrationSnapshot,
    type SessionMode,
} from "@/lib/streamRecovery";

const STORAGE_KEY = "bond_thread_id";
const MODE_KEY = "bond_mode";
const SESSIONS_KEY = "bond_sessions";

export interface SessionMeta {
    id: string;
    title: string;
    updatedAt: number;
    mode?: SessionMode;
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

function readStoredSessions(): SessionMeta[] {
    const storedSessions = localStorage.getItem(SESSIONS_KEY);
    if (!storedSessions) {
        return [];
    }

    try {
        const parsed = JSON.parse(storedSessions) as unknown;
        if (!Array.isArray(parsed)) {
            return [];
        }

        return parsed.flatMap((entry) => {
            if (!entry || typeof entry !== "object") {
                return [];
            }

            const candidate = entry as Record<string, unknown>;
            const id = typeof candidate.id === "string" ? candidate.id : "";
            const title = typeof candidate.title === "string" ? candidate.title : "";
            const updatedAt =
                typeof candidate.updatedAt === "number" ? candidate.updatedAt : Date.now();
            const mode =
                candidate.mode === "author" || candidate.mode === "shadow"
                    ? candidate.mode
                    : undefined;

            if (!id || !title) {
                return [];
            }

            return [{ id, title, updatedAt, mode }];
        });
    } catch (error) {
        console.error("Failed to parse sessions", error);
        return [];
    }
}

function writeStoredSessions(sessions: SessionMeta[]): void {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
    window.dispatchEvent(new Event("bond_sessions_changed"));
}

function syncStoredSessionMode(threadId: string, mode: SessionMode): void {
    const sessions = readStoredSessions();
    const sessionIndex = sessions.findIndex((session) => session.id === threadId);
    if (sessionIndex === -1) {
        return;
    }

    if (sessions[sessionIndex].mode === mode) {
        return;
    }

    sessions[sessionIndex] = {
        ...sessions[sessionIndex],
        mode,
    };
    writeStoredSessions(sessions);
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

    const rawData = (await res.json()) as SessionHistoryResponse;
    const resolvedMode = normalizeSessionMode(rawData.mode);
    const data = {
        ...rawData,
        mode: resolvedMode,
    };
    useChatStore.getState().setMode(resolvedMode);
    syncStoredSessionMode(id, resolvedMode);
    return hydrateSessionStores(data, options);
}

export function useSession() {
    const { threadId, setThreadId, mode, setMode, resetSession } = useChatStore();
    const router = useRouter();

    const [sessions, setSessions] = useState<SessionMeta[]>([]);

    useEffect(() => {
        const loadSessions = () => {
            setSessions(readStoredSessions());
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
            return await loadSessionHistory(id, { mode: "restore" });
        } catch (err) {
            console.error("Przywracanie sesji przerwane:", err);
            if (err instanceof SessionHistoryNotFoundError) {
                sessionStorage.removeItem(STORAGE_KEY);
                setThreadId(null);
            }
            return null;
        }
    }, [setThreadId]);

    const saveSessionMeta = (id: string, messages: ChatMessage[], sessionMode: SessionMode) => {
        const updated = readStoredSessions();
        const idx = updated.findIndex((s) => s.id === id);
        
        const userMsg = messages.find((m) => m.role === "user");
        let title = userMsg ? userMsg.content.slice(0, 30) : `Sesja ${id.slice(0, 8)}`;
        if (userMsg && userMsg.content.length >= 30) title += "...";

        if (idx > -1) {
            updated[idx].updatedAt = Date.now();
            updated[idx].title = title;
            updated[idx].mode = sessionMode;
        } else {
            updated.unshift({ id, title, updatedAt: Date.now(), mode: sessionMode });
        }
        
        const limited = updated.slice(0, 20); // Keep last 20
        writeStoredSessions(limited);
        setSessions(limited);
    };

    const persistThreadId = (id: string) => {
        sessionStorage.setItem(STORAGE_KEY, id);
        setThreadId(id);
        
        setTimeout(() => {
            const msgs = useChatStore.getState().messages;
            const currentMode = useChatStore.getState().mode;
            saveSessionMeta(id, msgs, currentMode);
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

    const switchSession = (session: SessionMeta) => {
        sessionStorage.setItem(STORAGE_KEY, session.id);
        useShadowStore.getState().resetShadow();
        resetSession();
        setThreadId(session.id);

        if (session.mode) {
            persistMode(session.mode);
            router.replace(sessionModeToPath(session.mode));
        }

        void restoreSessionHistory(session.id).then((history) => {
            if (!history) {
                return;
            }

            const resolvedMode = normalizeSessionMode(history.mode);
            persistMode(resolvedMode);
            const targetPath = sessionModeToPath(resolvedMode);
            if (typeof window !== "undefined" && window.location.pathname !== targetPath) {
                router.replace(targetPath);
            }
        });
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

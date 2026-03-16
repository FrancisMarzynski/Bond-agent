"use client";
import { useEffect, useState, useCallback } from "react";
import { useChatStore } from "@/store/chatStore";
import { API_URL } from "@/config";

const STORAGE_KEY = "bond_thread_id";
const MODE_KEY = "bond_mode";
const SESSIONS_KEY = "bond_sessions";

export interface SessionMeta {
    id: string;
    title: string;
    updatedAt: number;
}

export function useSession() {
    const { threadId, setThreadId, mode, setMode, resetSession } = useChatStore();

    const [isRestoring, setIsRestoring] = useState(true);
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

    const loadSessionHistory = useCallback(async (id: string) => {
        setIsRestoring(true);
        try {
            const res = await fetch(`${API_URL}/api/chat/history/${id}`);
            if (!res.ok) throw new Error("Sesja nie znaleziona na serwerze");
            const data = await res.json();

            const store = useChatStore.getState();
            if (data.messages && Array.isArray(data.messages)) {
                useChatStore.setState({ messages: data.messages });
            }
            if (data.draft) {
                store.setDraft(data.draft);
            }
            if (data.hitlPause) {
                store.setHitlPause(data.hitlPause);
            }
            if (data.stage && data.stage !== "idle") {
                const status = data.stageStatus?.[data.stage] || "complete";
                store.setStage(data.stage, status);
            }
        } catch (err) {
            console.error("Przywracanie sesji przerwane:", err);
            sessionStorage.removeItem(STORAGE_KEY);
            setThreadId(null);
        } finally {
            setIsRestoring(false);
        }
    }, [setThreadId]);

    useEffect(() => {
        const storedThread = sessionStorage.getItem(STORAGE_KEY);
        const storedMode = sessionStorage.getItem(MODE_KEY);

        if (storedMode === "author" || storedMode === "shadow") {
            setMode(storedMode);
        }

        if (storedThread) {
            setThreadId(storedThread);
            loadSessionHistory(storedThread);
        } else {
            setIsRestoring(false);
        }
    }, [setThreadId, setMode, loadSessionHistory]);

    const saveSessionMeta = (id: string, messages: any[]) => {
        setSessions(prev => {
            const updated = [...prev];
            const idx = updated.findIndex((s) => s.id === id);
            
            const userMsg = messages.find((m) => m.role === "user");
            let title = userMsg ? userMsg.content.slice(0, 30) : `Sesja ${id.slice(0, 8)}`;
            if (title.length >= 30) title += "...";

            if (idx > -1) {
                updated[idx].updatedAt = Date.now();
                updated[idx].title = title;
            } else {
                updated.unshift({ id, title, updatedAt: Date.now() });
            }
            
            const limited = updated.slice(0, 20); // Keep last 20
            localStorage.setItem(SESSIONS_KEY, JSON.stringify(limited));
            window.dispatchEvent(new Event("bond_sessions_changed"));
            return limited;
        });
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
        resetSession();
    };

    const switchSession = (id: string) => {
        sessionStorage.setItem(STORAGE_KEY, id);
        resetSession();
        setThreadId(id);
        loadSessionHistory(id);
    };

    return { threadId, mode, sessions, persistThreadId, persistMode, newSession, switchSession, isRestoring };
}

"use client";
import { useEffect, useState } from "react";
import { useChatStore } from "@/store/chatStore";

const STORAGE_KEY = "bond_thread_id";
const MODE_KEY = "bond_mode";

export function useSession() {
    const { threadId, setThreadId, mode, setMode, resetSession } = useChatStore();

    const [isRestoring, setIsRestoring] = useState(true);

    useEffect(() => {
        const storedThread = sessionStorage.getItem(STORAGE_KEY);
        const storedMode = sessionStorage.getItem(MODE_KEY);

        if (storedMode === "author" || storedMode === "shadow") {
            setMode(storedMode);
        }

        if (storedThread) {
            setThreadId(storedThread);
            const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

            fetch(`${API_URL}/api/chat/history/${storedThread}`)
                .then((res) => {
                    if (!res.ok) throw new Error("Sesja nie znaleziona na serwerze");
                    return res.json();
                })
                .then((data) => {
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
                })
                .catch((err) => {
                    console.error("Przywracanie sesji przerwane:", err);
                    // Jeśli sesja wygasła w DB, czyścimy sessionStorage by uniknąć zapętlenia
                    sessionStorage.removeItem(STORAGE_KEY);
                    setThreadId(null);
                })
                .finally(() => setIsRestoring(false));
        } else {
            setIsRestoring(false);
        }
    }, [setThreadId, setMode]);

    const persistThreadId = (id: string) => {
        sessionStorage.setItem(STORAGE_KEY, id);
        setThreadId(id);
    };

    const persistMode = (newMode: "author" | "shadow") => {
        sessionStorage.setItem(MODE_KEY, newMode);
        setMode(newMode);
    };

    const newSession = () => {
        sessionStorage.removeItem(STORAGE_KEY);
        resetSession();
    };

    return { threadId, mode, persistThreadId, persistMode, newSession, isRestoring };
}

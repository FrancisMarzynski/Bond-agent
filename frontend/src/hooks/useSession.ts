"use client";
import { useEffect, useState } from "react";
import { useChatStore } from "@/store/chatStore";

const STORAGE_KEY = "bond_thread_id";

export function useSession() {
    const { threadId, setThreadId, resetSession } = useChatStore();

    const [isRestoring, setIsRestoring] = useState(true);

    useEffect(() => {
        const stored = sessionStorage.getItem(STORAGE_KEY);
        if (stored) {
            setThreadId(stored);
            const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

            fetch(`${API_URL}/api/chat/history/${stored}`)
                .then((res) => res.json())
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
                .catch((err) => console.error("Nie udało się pobrać historii:", err))
                .finally(() => setIsRestoring(false));
        } else {
            setIsRestoring(false);
        }
    }, [setThreadId]);

    const persistThreadId = (id: string) => {
        sessionStorage.setItem(STORAGE_KEY, id);
        setThreadId(id);
    };

    const newSession = () => {
        sessionStorage.removeItem(STORAGE_KEY);
        resetSession();
    };

    return { threadId, persistThreadId, newSession, isRestoring };
}

"use client";
import { useEffect } from "react";
import { useChatStore } from "@/store/chatStore";

const STORAGE_KEY = "bond_thread_id";

export function useSession() {
    const { threadId, setThreadId, resetSession } = useChatStore();

    useEffect(() => {
        const stored = sessionStorage.getItem(STORAGE_KEY);
        if (stored) setThreadId(stored);
    }, [setThreadId]);

    const persistThreadId = (id: string) => {
        sessionStorage.setItem(STORAGE_KEY, id);
        setThreadId(id);
    };

    const newSession = () => {
        sessionStorage.removeItem(STORAGE_KEY);
        resetSession();
    };

    return { threadId, persistThreadId, newSession };
}

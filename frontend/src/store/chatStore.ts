"use client";
import { create } from "zustand";

export type Stage = "idle" | "research" | "structure" | "writing" | "done" | "error";
export type StageStatus = "pending" | "running" | "complete" | "error";
export type HitlPause = {
    checkpoint_id: string;
    type: string;
    iterations_remaining?: number;
} | null;

export interface ChatMessage {
    role: "user" | "assistant";
    content: string;
}

interface ChatStore {
    mode: "author" | "shadow";
    threadId: string | null;
    stage: Stage;
    stageStatus: Record<Stage, StageStatus>;
    draft: string;
    messages: ChatMessage[];
    hitlPause: HitlPause;
    isStreaming: boolean;
    // Actions
    setMode: (mode: "author" | "shadow") => void;
    setThreadId: (id: string | null) => void;
    setStage: (stage: Stage, status: StageStatus) => void;
    appendDraftToken: (token: string) => void;
    setDraft: (draft: string) => void;
    setHitlPause: (pause: HitlPause) => void;
    setStreaming: (v: boolean) => void;
    addMessage: (msg: ChatMessage) => void;
    resetSession: () => void;
}

const initialStageStatus: Record<Stage, StageStatus> = {
    idle: "pending",
    research: "pending",
    structure: "pending",
    writing: "pending",
    done: "pending",
    error: "pending",
};

export const useChatStore = create<ChatStore>((set) => ({
    mode: "author",
    threadId: null,
    stage: "idle",
    stageStatus: { ...initialStageStatus },
    draft: "",
    messages: [],
    hitlPause: null,
    isStreaming: false,
    setMode: (mode) => set({ mode }),
    setThreadId: (threadId) => set({ threadId }),
    setStage: (stage, status) =>
        set((s) => ({ stage, stageStatus: { ...s.stageStatus, [stage]: status } })),
    appendDraftToken: (token) => set((s) => ({ draft: s.draft + token })),
    setDraft: (draft) => set({ draft }),
    setHitlPause: (hitlPause) => set({ hitlPause }),
    setStreaming: (isStreaming) => set({ isStreaming }),
    addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
    resetSession: () =>
        set({ threadId: null, stage: "idle", stageStatus: { ...initialStageStatus }, draft: "", messages: [], hitlPause: null, isStreaming: false }),
}));

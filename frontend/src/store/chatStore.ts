"use client";
import { create } from "zustand";

export type Stage = "idle" | "research" | "structure" | "writing" | "done" | "error";
export type StageStatus = "pending" | "running" | "complete" | "error";
export type HitlPause = {
    checkpoint_id: string;
    type: string;
    iterations_remaining?: number;
    // Checkpoint 1 fields
    research_report?: string;
    heading_structure?: string;
    // Duplicate check specific fields (checkpoint_id === "duplicate_check")
    warning?: string;
    existing_title?: string;
    existing_date?: string;
    similarity_score?: number;
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
    lastEventId?: string;
    systemAlert?: string;
    /** AbortController belonging to the current active stream. Stored here
     *  so that every hook/component instance has its own isolated reference
     *  instead of sharing a single module-level variable. */
    activeController: AbortController | null;
    // Actions
    setMode: (mode: "author" | "shadow") => void;
    setThreadId: (id: string | null) => void;
    setStage: (stage: Stage, status: StageStatus) => void;
    appendDraftToken: (token: string) => void;
    setDraft: (draft: string) => void;
    setHitlPause: (pause: HitlPause) => void;
    setStreaming: (v: boolean) => void;
    setLastEventId: (id: string | undefined) => void;
    setSystemAlert: (alert: string | undefined) => void;
    addMessage: (msg: ChatMessage) => void;
    resetSession: () => void;
    /** Creates a fresh AbortController, aborts any previous one, and stores
     *  the new instance in the store. Returns the new signal. */
    createController: () => AbortSignal;
    /** Aborts the current controller (if any) and clears it from the store. */
    abortController: () => void;
}

const initialStageStatus: Record<Stage, StageStatus> = {
    idle: "pending",
    research: "pending",
    structure: "pending",
    writing: "pending",
    done: "pending",
    error: "pending",
};

export const useChatStore = create<ChatStore>((set, get) => ({
    mode: "author",
    threadId: null,
    stage: "idle",
    stageStatus: { ...initialStageStatus },
    draft: "",
    messages: [],
    hitlPause: null,
    isStreaming: false,
    lastEventId: undefined,
    systemAlert: undefined,
    activeController: null,

    setMode: (mode) => set({ mode }),
    setThreadId: (threadId) => set({ threadId }),
    setStage: (stage, status) =>
        set((s) => ({ stage, stageStatus: { ...s.stageStatus, [stage]: status } })),
    appendDraftToken: (token) => set((s) => ({ draft: s.draft + token })),
    setDraft: (draft) => set({ draft }),
    setHitlPause: (hitlPause) => set({ hitlPause }),
    setStreaming: (isStreaming) => set({ isStreaming }),
    setLastEventId: (lastEventId) => set({ lastEventId }),
    setSystemAlert: (systemAlert) => set({ systemAlert }),
    addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
    resetSession: () =>
        set({
            threadId: null,
            stage: "idle",
            stageStatus: { ...initialStageStatus },
            draft: "",
            messages: [],
            hitlPause: null,
            isStreaming: false,
            lastEventId: undefined,
            systemAlert: undefined,
            activeController: null,
        }),

    createController: () => {
        const previous = get().activeController;
        if (previous) previous.abort();
        const controller = new AbortController();
        set({ activeController: controller });
        return controller.signal;
    },

    abortController: () => {
        const controller = get().activeController;
        if (controller) controller.abort();
        set({ activeController: null, isStreaming: false });
    },
}));

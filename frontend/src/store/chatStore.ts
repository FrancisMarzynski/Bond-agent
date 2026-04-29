"use client";
import { create } from "zustand";
import type { Annotation } from "@/store/shadowStore";

export type Stage =
  | "idle"
  | "checking"
  | "research"
  | "structure"
  | "writing"
  | "shadow_analysis"
  | "shadow_annotation"
  | "done"
  | "error";
export type StageStatus = "pending" | "running" | "complete" | "error";
export type PendingAction = "stream" | "resume" | null;
export type DraftValidationFailure = {
    code:
      | "keyword_in_h1"
      | "keyword_in_first_para"
      | "meta_desc_length_ok"
      | "word_count_ok"
      | "no_forbidden_words";
    message: string;
};
export type DraftValidationAttempt = {
    attempt_number: number;
    passed: boolean;
    failed_codes: string[];
};
export type DraftValidationDetails = {
    passed: boolean;
    checks: {
        keyword_in_h1: boolean;
        keyword_in_first_para: boolean;
        meta_desc_length_ok: boolean;
        word_count_ok: boolean;
        no_forbidden_words: boolean;
    };
    failure_codes: string[];
    failures: DraftValidationFailure[];
    primary_keyword: string;
    body_word_count: number;
    min_words: number;
    meta_description_length: number;
    meta_description_min_length: number;
    meta_description_max_length: number;
    forbidden_stems: string[];
    attempt_count: number;
    attempts: DraftValidationAttempt[];
};
export type HitlPause = {
    checkpoint_id: string;
    type: string;
    iterations_remaining?: number;
    // Checkpoint 1 fields
    research_report?: string;
    heading_structure?: string;
    cp1_iterations?: number;
    // Duplicate check specific fields (checkpoint_id === "duplicate_check")
    warning?: string;
    existing_title?: string;
    existing_date?: string;
    similarity_score?: number;
    // Writer / checkpoint_2 specific fields
    draft?: string;
    draft_validated?: boolean;
    cp2_iterations?: number;
    validation_warning?: string;
    draft_validation_details?: DraftValidationDetails;
    corpus_count?: number;
    threshold?: number;
    // Shadow mode fields
    annotations?: Annotation[];
    shadow_corrected_text?: string;
    iteration_count?: number;
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
    isReconnecting: boolean;
    isRecoveringSession: boolean;
    pendingAction: PendingAction;
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
    setReconnecting: (v: boolean) => void;
    setRecoveringSession: (v: boolean) => void;
    setPendingAction: (action: PendingAction) => void;
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
    checking: "pending",
    research: "pending",
    structure: "pending",
    writing: "pending",
    shadow_analysis: "pending",
    shadow_annotation: "pending",
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
    isReconnecting: false,
    isRecoveringSession: false,
    pendingAction: null,
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
    setReconnecting: (isReconnecting) => set({ isReconnecting }),
    setRecoveringSession: (isRecoveringSession) => set({ isRecoveringSession }),
    setPendingAction: (pendingAction) => set({ pendingAction }),
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
            isReconnecting: false,
            isRecoveringSession: false,
            pendingAction: null,
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
        set({
            activeController: null,
            isStreaming: false,
            isReconnecting: false,
            isRecoveringSession: false,
            pendingAction: null,
        });
    },
}));

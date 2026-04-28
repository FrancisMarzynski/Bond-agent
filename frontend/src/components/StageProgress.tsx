"use client";
import { useChatStore, type Stage } from "@/store/chatStore";
import { cn } from "@/lib/utils";
import { AlertTriangle, CheckCircle2, Circle, Loader2, RefreshCw, XCircle } from "lucide-react";

const AUTHOR_STEPS: { id: Stage; label: string }[] = [
    { id: "research", label: "Research" },
    { id: "structure", label: "Struktura" },
    { id: "writing", label: "Pisanie" },
];

const SHADOW_STEPS: { id: Stage; label: string }[] = [
    { id: "shadow_analysis", label: "Analiza" },
    { id: "shadow_annotation", label: "Adnotacje" },
];

function stepIndex(steps: { id: Stage; label: string }[], stage: Stage): number {
    return steps.findIndex((s) => s.id === stage);
}

export function StageProgress() {
    const {
        mode,
        stage,
        stageStatus,
        isStreaming,
        isReconnecting,
        isRecoveringSession,
        pendingAction,
        systemAlert,
        setSystemAlert,
    } = useChatStore();

    const STEPS = mode === "shadow" ? SHADOW_STEPS : AUTHOR_STEPS;

    // Always render when reconnecting or there's an alert so banners are visible.
    if (stage === "idle" && !isStreaming && !isReconnecting && !isRecoveringSession && !systemAlert) return null;

    let furthestIdx = -1;
    STEPS.forEach((step, idx) => {
        if (stageStatus[step.id] !== "pending") {
            furthestIdx = Math.max(furthestIdx, idx);
        }
    });

    const currentStageIdx = stepIndex(STEPS, stage);
    const activeIdx = currentStageIdx !== -1 ? currentStageIdx : furthestIdx;

    return (
        <div className="border-b bg-muted/20">
            {/* Reconnecting banner */}
            {isReconnecting && (
                <div className="flex items-center gap-2 px-4 py-1.5 text-xs text-amber-700 bg-amber-50 border-b border-amber-200">
                    <RefreshCw className="h-3 w-3 animate-spin shrink-0" />
                    <span>Ponawiam połączenie przed potwierdzeniem komendy...</span>
                </div>
            )}

            {isRecoveringSession && (
                <div className="flex items-center gap-2 px-4 py-1.5 text-xs text-sky-800 bg-sky-50 border-b border-sky-200">
                    <Loader2 className="h-3 w-3 animate-spin shrink-0" />
                    <span>
                        {pendingAction === "resume"
                            ? "Przywracam stan sesji z historii po wysłaniu decyzji HITL..."
                            : "Przywracam stan sesji z historii po przerwanym starcie streamu..."}
                    </span>
                </div>
            )}

            {/* System alert banner (hard-cap, critical errors) */}
            {systemAlert && !isReconnecting && !isRecoveringSession && (
                <div className="flex items-start gap-2 px-4 py-1.5 text-xs text-amber-800 bg-amber-50 border-b border-amber-200">
                    <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />
                    <span className="flex-1">{systemAlert}</span>
                    <button
                        onClick={() => setSystemAlert(undefined)}
                        className="shrink-0 text-amber-600 hover:text-amber-900 leading-none"
                        aria-label="Zamknij"
                    >
                        ×
                    </button>
                </div>
            )}

            <div className="px-4 py-3">
                <ol className="flex items-center gap-0">
                    {STEPS.map((step, idx) => {
                        const status = stageStatus[step.id];
                        const isActive = idx === activeIdx;
                        const isComplete = status === "complete" || stage === "done" || activeIdx > idx;
                        const isError = status === "error" || (isActive && (stage === "error" || stageStatus["error"] === "error"));
                        const isRunning = isActive && !isError && (status === "running" || isStreaming) && stage !== "done";

                        return (
                            <li key={step.id} className="flex items-center">
                                <span className="flex items-center gap-1.5">
                                    {isComplete ? (
                                        <CheckCircle2 className="h-4 w-4 text-primary" />
                                    ) : isError ? (
                                        <XCircle className="h-4 w-4 text-destructive" />
                                    ) : isRunning ? (
                                        <Loader2 className="h-4 w-4 text-primary animate-spin" />
                                    ) : (
                                        <Circle className={cn("h-4 w-4", isActive ? "text-primary" : "text-muted-foreground/50")} />
                                    )}
                                    <span className={cn(
                                        "text-xs font-medium",
                                        isActive && !isError ? "text-foreground" : isError ? "text-destructive" : isComplete ? "text-foreground/70" : "text-muted-foreground/50"
                                    )}>
                                        {step.label}
                                    </span>
                                </span>
                                {idx < STEPS.length - 1 && (
                                    <span className={cn(
                                        "mx-2 h-px w-8",
                                        isComplete ? "bg-primary" : "bg-muted-foreground/20"
                                    )} />
                                )}
                            </li>
                        );
                    })}
                </ol>
            </div>
        </div>
    );
}

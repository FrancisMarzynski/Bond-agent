"use client";
import { useChatStore, type Stage } from "@/store/chatStore";
import { cn } from "@/lib/utils";
import { AlertTriangle, CheckCircle2, Circle, Loader2, RefreshCw, XCircle } from "lucide-react";

const STEPS: { id: Stage; label: string }[] = [
    { id: "research", label: "Research" },
    { id: "structure", label: "Structure" },
    { id: "writing", label: "Writing" },
];

function stepIndex(stage: Stage): number {
    return STEPS.findIndex((s) => s.id === stage);
}

export function StageProgress() {
    const { stage, stageStatus, isStreaming, isReconnecting, systemAlert, setSystemAlert } = useChatStore();

    // Always render when reconnecting or there's an alert so banners are visible.
    if (stage === "idle" && !isStreaming && !isReconnecting && !systemAlert) return null;

    // Znajdź najdalszy krok, który został osiągnięty (nie jest "pending")
    let furthestIdx = -1;
    STEPS.forEach((step, idx) => {
        if (stageStatus[step.id] !== "pending") {
            furthestIdx = Math.max(furthestIdx, idx);
        }
    });

    const currentStageIdx = stepIndex(stage);
    const activeIdx = currentStageIdx !== -1 ? currentStageIdx : furthestIdx;

    return (
        <div className="border-b bg-muted/20">
            {/* Reconnecting banner */}
            {isReconnecting && (
                <div className="flex items-center gap-2 px-4 py-1.5 text-xs text-amber-700 bg-amber-50 border-b border-amber-200">
                    <RefreshCw className="h-3 w-3 animate-spin shrink-0" />
                    <span>Wznawianie połączenia SSE...</span>
                </div>
            )}

            {/* System alert banner (hard-cap, critical errors) */}
            {systemAlert && !isReconnecting && (
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

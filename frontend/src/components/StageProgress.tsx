"use client";
import { useChatStore, type Stage } from "@/store/chatStore";
import { cn } from "@/lib/utils";
import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";

const STEPS: { id: Stage; label: string }[] = [
    { id: "research", label: "Research" },
    { id: "structure", label: "Structure" },
    { id: "writing", label: "Writing" },
];

function stepIndex(stage: Stage): number {
    return STEPS.findIndex((s) => s.id === stage);
}

export function StageProgress() {
    const { stage, stageStatus, isStreaming } = useChatStore();

    // Only show stepper when a session is active.
    // Ensure we don't hide the stepper if we crashed at any stage other than idle.
    if (stage === "idle" && !isStreaming) return null;

    const currentIdx = stepIndex(stage);

    return (
        <div className="border-b px-4 py-3 bg-muted/20">
            <ol className="flex items-center gap-0">
                {STEPS.map((step, idx) => {
                    const status = stageStatus[step.id];
                    const isActive = step.id === stage;
                    const isComplete = status === "complete" || (currentIdx > idx && stage !== "error");
                    const isRunning = isActive && status === "running";
                    const isError = isActive && status === "error";

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
    );
}

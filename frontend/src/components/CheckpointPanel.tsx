"use client";
import { useChatStore } from "@/store/chatStore";
import { useSession } from "@/hooks/useSession";
import { useStream } from "@/hooks/useStream";
import { Button } from "@/components/ui/button";
import { CheckCircle2, XCircle, SaveAll } from "lucide-react";

export function CheckpointPanel() {
  const { hitlPause, isStreaming } = useChatStore();
  const { threadId, persistThreadId } = useSession();
  const { resumeStream } = useStream();

  if (!hitlPause || isStreaming) return null;

  const isCheckpoint2 = hitlPause.checkpoint_id === "cp2" ||
    hitlPause.checkpoint_id === "checkpoint_2";
  const iterationsRemaining = hitlPause.iterations_remaining;

  const handleApprove = async () => {
    if (!threadId) return;
    await resumeStream(threadId, "approve", null, persistThreadId);
  };

  const handleApproveSave = async () => {
    if (!threadId) return;
    await resumeStream(threadId, "approve_save", null, persistThreadId);
  };

  const handleReject = async () => {
    if (!threadId) return;
    // Chat-style reject: send reject action, agent responds asking what to change,
    // user replies in the normal chat input (locked UX decision from CONTEXT.md)
    await resumeStream(threadId, "reject", null, persistThreadId);
  };

  return (
    <div className="border rounded-lg p-3 bg-muted/30 mx-4 mt-3 mb-3 flex items-center gap-2 flex-wrap shrink-0">
      <span className="text-xs text-muted-foreground mr-auto">
        {isCheckpoint2 ? "Przejrzyj końcowy draft" : "Przejrzyj i zatwierdź, by kontynuować"}
      </span>

      <Button
        variant="default"
        size="sm"
        onClick={handleApprove}
        disabled={isStreaming}
        className="gap-1.5"
      >
        <CheckCircle2 className="h-3.5 w-3.5" />
        Zatwierdź
      </Button>

      {isCheckpoint2 && (
        <Button
          variant="default"
          size="sm"
          onClick={handleApproveSave}
          disabled={isStreaming}
          className="gap-1.5 bg-green-600 hover:bg-green-700"
        >
          <SaveAll className="h-3.5 w-3.5" />
          Zatwierdź i Zapisz
        </Button>
      )}

      <div className="flex items-center gap-1.5">
        <Button
          variant="outline"
          size="sm"
          onClick={handleReject}
          disabled={isStreaming}
          className="gap-1.5 text-destructive border-destructive/40 hover:bg-destructive/10"
        >
          <XCircle className="h-3.5 w-3.5" />
          Odrzuć
        </Button>
        {isCheckpoint2 && iterationsRemaining !== undefined && (
          <span className="text-xs text-muted-foreground">
            Pozostało {iterationsRemaining} z 3 prób poprawek
          </span>
        )}
      </div>
    </div>
  );
}

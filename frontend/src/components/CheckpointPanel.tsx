"use client";
import { useState } from "react";
import { useChatStore } from "@/store/chatStore";
import { useSession } from "@/hooks/useSession";
import { useStream } from "@/hooks/useStream";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { CheckCircle2, XCircle, Database, X } from "lucide-react";

export function CheckpointPanel() {
  const { hitlPause, isStreaming } = useChatStore();
  const { threadId, persistThreadId } = useSession();
  const { resumeStream } = useStream();

  const [showFeedbackField, setShowFeedbackField] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");

  if (!hitlPause || isStreaming) return null;

  const isCheckpoint2 = hitlPause.checkpoint_id === "cp2" ||
    hitlPause.checkpoint_id === "checkpoint_2";
  const iterationsRemaining = hitlPause.iterations_remaining;

  const handleApprove = async () => {
    if (!threadId) return;
    setShowFeedbackField(false);
    setFeedbackText("");
    await resumeStream(threadId, "approve", null, persistThreadId);
  };

  const handleRejectClick = () => {
    setShowFeedbackField(true);
  };

  const handleRejectCancel = () => {
    setShowFeedbackField(false);
    setFeedbackText("");
  };

  const handleRejectSubmit = async () => {
    if (!threadId) return;
    const feedback = feedbackText.trim() || null;
    setShowFeedbackField(false);
    setFeedbackText("");
    await resumeStream(threadId, "reject", feedback, persistThreadId);
  };

  return (
    <div className="border rounded-lg p-3 bg-muted/30 mx-4 mt-3 mb-3 flex flex-col gap-3 shrink-0">
      {/* Header row */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-muted-foreground mr-auto">
          {isCheckpoint2
            ? "Wygenerowano finalną wersję — zapisz do bazy lub odrzuć z poprawkami"
            : "Przejrzyj i zatwierdź, by kontynuować"}
        </span>

        {/* Approve button — checkpoint_1: "Zatwierdź", checkpoint_2: "Zapisz do bazy" */}
        {isCheckpoint2 ? (
          <Button
            variant="default"
            size="sm"
            onClick={handleApprove}
            disabled={isStreaming}
            className="gap-1.5 bg-green-600 hover:bg-green-700"
          >
            <Database className="h-3.5 w-3.5" />
            Zapisz do bazy
          </Button>
        ) : (
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
        )}

        {/* Reject button (or cancel when feedback field is open) */}
        <div className="flex items-center gap-1.5">
          {showFeedbackField ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRejectCancel}
              disabled={isStreaming}
              className="gap-1.5 text-muted-foreground"
            >
              <X className="h-3.5 w-3.5" />
              Anuluj
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={handleRejectClick}
              disabled={isStreaming}
              className="gap-1.5 text-destructive border-destructive/40 hover:bg-destructive/10"
            >
              <XCircle className="h-3.5 w-3.5" />
              Odrzuć
            </Button>
          )}
          {isCheckpoint2 && iterationsRemaining !== undefined && (
            <span className="text-xs text-muted-foreground">
              Pozostało {iterationsRemaining} z 3 prób poprawek
            </span>
          )}
        </div>
      </div>

      {/* Inline feedback field — visible only after clicking "Odrzuć" */}
      {showFeedbackField && (
        <div className="flex flex-col gap-2">
          <label className="text-xs text-muted-foreground font-medium">
            Opisz, co należy poprawić:
          </label>
          <Textarea
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            placeholder="Np. Sekcja wstępna jest zbyt ogólna, dodaj konkretne przykłady..."
            className="text-sm min-h-[80px] resize-none"
            disabled={isStreaming}
            autoFocus
          />
          <div className="flex justify-end">
            <Button
              variant="destructive"
              size="sm"
              onClick={handleRejectSubmit}
              disabled={isStreaming}
              className="gap-1.5"
            >
              <XCircle className="h-3.5 w-3.5" />
              Wyślij poprawki
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

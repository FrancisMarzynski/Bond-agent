"use client";
import { useState } from "react";
import { useChatStore } from "@/store/chatStore";
import { useSession } from "@/hooks/useSession";
import { useStream } from "@/hooks/useStream";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { CheckCircle2, XCircle, Database, X, AlertTriangle, ChevronDown, ChevronRight, ScrollText } from "lucide-react";

export function CheckpointPanel() {
  const { hitlPause, isStreaming, isRecoveringSession, pendingAction } = useChatStore();
  const { threadId, persistThreadId } = useSession();
  const { resumeStream } = useStream();

  const [showFeedbackField, setShowFeedbackField] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [researchOpen, setResearchOpen] = useState(true);
  const [structureOpen, setStructureOpen] = useState(true);

  if (!hitlPause || isStreaming) return null;

  const isDuplicateCheck = hitlPause.checkpoint_id === "duplicate_check";
  const isLowCorpus = hitlPause.checkpoint_id === "low_corpus";
  const isCheckpoint1 = hitlPause.checkpoint_id === "checkpoint_1";
  const isCheckpoint2 = hitlPause.checkpoint_id === "cp2" ||
    hitlPause.checkpoint_id === "checkpoint_2";
  const iterationsRemaining = hitlPause.iterations_remaining;
  const controlsDisabled = isStreaming || (isRecoveringSession && pendingAction === "resume");

  // --- Duplicate check handlers ---
  const handleDuplicateContinue = async () => {
    if (!threadId) return;
    await resumeStream(threadId, "approve", null, persistThreadId);
  };

  const handleDuplicateAbort = async () => {
    if (!threadId) return;
    await resumeStream(threadId, "reject", null, persistThreadId);
  };

  // --- Standard checkpoint handlers ---
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
    if (isCheckpoint1) {
      await resumeStream(threadId, "reject", null, persistThreadId, {
        note: feedback,
      });
      return;
    }
    await resumeStream(threadId, "reject", feedback, persistThreadId);
  };

  // --- Warning checkpoints UI ---
  if (isDuplicateCheck || isLowCorpus) {
    const warningTitle = isDuplicateCheck
      ? "Wykryto podobny temat"
      : "Niski stan korpusu";

    return (
      <div className="mx-3 mb-3 mt-3 flex shrink-0 flex-col gap-3 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 sm:mx-4">
        <div className="flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
          <div className="flex flex-col gap-1 flex-1 min-w-0">
            <span className="text-xs font-medium text-amber-600 dark:text-amber-400">
              {warningTitle}
            </span>
            {hitlPause.warning && (
              <span className="text-xs text-muted-foreground">
                {hitlPause.warning}
              </span>
            )}
            {isDuplicateCheck && hitlPause.existing_title && (
              <span className="text-xs text-muted-foreground">
                <span className="font-medium">Istniejący artykuł:</span>{" "}
                {hitlPause.existing_title}
              </span>
            )}
            {isDuplicateCheck && hitlPause.existing_date && (
              <span className="text-xs text-muted-foreground">
                <span className="font-medium">Data publikacji:</span>{" "}
                {hitlPause.existing_date}
              </span>
            )}
            {isDuplicateCheck && hitlPause.similarity_score !== undefined && (
              <span className="text-xs text-muted-foreground">
                <span className="font-medium">Podobieństwo:</span>{" "}
                {Math.round(hitlPause.similarity_score * 100)}%
              </span>
            )}
            {isLowCorpus && hitlPause.corpus_count !== undefined && (
              <span className="text-xs text-muted-foreground">
                <span className="font-medium">Artykułów w korpusie:</span>{" "}
                {hitlPause.corpus_count}
                {hitlPause.threshold !== undefined && ` / próg ${hitlPause.threshold}`}
              </span>
            )}
            {isRecoveringSession && pendingAction === "resume" && (
              <span className="text-xs text-muted-foreground">
                Przywracanie stanu po wysłaniu decyzji...
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDuplicateAbort}
            disabled={controlsDisabled}
            className="w-full gap-1.5 border-destructive/40 text-destructive hover:bg-destructive/10 sm:w-auto"
          >
            <XCircle className="h-3.5 w-3.5" />
            {isLowCorpus ? "Przerwij" : "Anuluj"}
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={handleDuplicateContinue}
            disabled={controlsDisabled}
            className="w-full gap-1.5 bg-amber-600 hover:bg-amber-700 sm:w-auto"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            {isLowCorpus ? "Kontynuuj mimo ryzyka" : "Kontynuuj mimo to"}
          </Button>
        </div>
      </div>
    );
  }

  const researchReport = hitlPause.research_report;
  const headingStructure = hitlPause.heading_structure;
  const validationWarning = hitlPause.validation_warning;

  // --- Standard checkpoint UI (cp1 / cp2) ---
  return (
    <div className="mx-3 mb-3 mt-3 flex shrink-0 flex-col gap-3 rounded-lg border bg-muted/30 p-3 sm:mx-4">
      {/* Collapsible research report — shown only at checkpoint_1 */}
      {isCheckpoint1 && researchReport && (
        <div className="flex flex-col gap-1.5">
          <button
            type="button"
            onClick={() => setResearchOpen((o) => !o)}
            className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors w-full text-left"
          >
            {researchOpen ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0" />
            )}
            <ScrollText className="h-3.5 w-3.5 shrink-0" />
            Raport Badawczy
          </button>
          {researchOpen && (
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap break-words font-sans leading-relaxed max-h-60 overflow-y-auto rounded border border-border/50 bg-background/60 p-2.5">
              {researchReport}
            </pre>
          )}
        </div>
      )}

      {isCheckpoint1 && headingStructure && (
        <div className="flex flex-col gap-1.5">
          <button
            type="button"
            onClick={() => setStructureOpen((o) => !o)}
            className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors w-full text-left"
          >
            {structureOpen ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0" />
            )}
            <ScrollText className="h-3.5 w-3.5 shrink-0" />
            Proponowana struktura
          </button>
          {structureOpen && (
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap break-words font-sans leading-relaxed max-h-60 overflow-y-auto rounded border border-border/50 bg-background/60 p-2.5">
              {headingStructure}
            </pre>
          )}
        </div>
      )}

      {isCheckpoint2 && validationWarning && (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <div className="min-w-0 text-xs text-muted-foreground whitespace-pre-wrap">
            {validationWarning}
          </div>
        </div>
      )}

      {/* Header row */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <span className="text-xs text-muted-foreground lg:mr-auto">
          {isCheckpoint2
            ? "Wygenerowano finalną wersję — zapisz do bazy lub odrzuć z poprawkami"
            : "Przejrzyj i zatwierdź, by kontynuować"}
        </span>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap lg:justify-end">
          {isCheckpoint2 ? (
            <Button
              variant="default"
              size="sm"
              onClick={handleApprove}
              disabled={controlsDisabled}
              className="w-full gap-1.5 bg-green-600 hover:bg-green-700 sm:w-auto"
            >
              <Database className="h-3.5 w-3.5" />
              Zapisz do bazy
            </Button>
          ) : (
            <Button
              variant="default"
              size="sm"
              onClick={handleApprove}
              disabled={controlsDisabled}
              className="w-full gap-1.5 sm:w-auto"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Zatwierdź
            </Button>
          )}
          {showFeedbackField ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRejectCancel}
              disabled={controlsDisabled}
              className="w-full gap-1.5 text-muted-foreground sm:w-auto"
            >
              <X className="h-3.5 w-3.5" />
              Anuluj
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={handleRejectClick}
              disabled={controlsDisabled}
              className="w-full gap-1.5 border-destructive/40 text-destructive hover:bg-destructive/10 sm:w-auto"
            >
              <XCircle className="h-3.5 w-3.5" />
              Odrzuć
            </Button>
          )}
          {isCheckpoint2 && iterationsRemaining !== undefined && (
            <span className="self-start text-xs text-muted-foreground sm:self-center">
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
            disabled={controlsDisabled}
            autoFocus
          />
          <div className="flex justify-stretch sm:justify-end">
            <Button
              variant="destructive"
              size="sm"
              onClick={handleRejectSubmit}
              disabled={controlsDisabled}
              className="w-full gap-1.5 sm:w-auto"
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

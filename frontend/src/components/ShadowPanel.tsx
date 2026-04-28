"use client";
import { useState, useCallback, useRef, useMemo } from "react";
import { useShadowStore, type Annotation } from "@/store/shadowStore";
import { useChatStore } from "@/store/chatStore";
import { useSession } from "@/hooks/useSession";
import { useStream } from "@/hooks/useStream";
import { AnnotationList } from "@/components/AnnotationList";
import { ShadowAnnotationsSection } from "@/components/ShadowAnnotationsSection";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, RotateCcw, FileText, Pencil } from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type Segment =
  | { type: "text"; content: string }
  | { type: "annotation"; annotation: Annotation; content: string };

/**
 * Split `text` into plain-text and annotation segments ordered by position.
 * Non-overlapping annotations only — overlapping spans are skipped.
 */
function buildSegments(text: string, annotations: Annotation[]): Segment[] {
  const sorted = [...annotations].sort((a, b) => a.start_index - b.start_index);
  const segments: Segment[] = [];
  let cursor = 0;

  for (const ann of sorted) {
    if (ann.start_index < cursor) continue; // skip overlapping
    if (ann.start_index > cursor) {
      segments.push({ type: "text", content: text.slice(cursor, ann.start_index) });
    }
    segments.push({
      type: "annotation",
      annotation: ann,
      content: text.slice(ann.start_index, ann.end_index),
    });
    cursor = ann.end_index;
  }

  if (cursor < text.length) {
    segments.push({ type: "text", content: text.slice(cursor) });
  }

  return segments;
}

// ---------------------------------------------------------------------------
// ShadowPanel — two-phase UI:
//   1. Input view  — user submits text for style analysis
//   2. Comparison  — responsive annotations + original (highlighted) + corrected (editable)
// ---------------------------------------------------------------------------
export function ShadowPanel() {
  const [inputText, setInputText] = useState("");
  const [activeAnnotationId, setActiveAnnotationId] = useState<string | null>(null);
  const [feedbackText, setFeedbackText] = useState("");

  // Refs to annotation <mark> elements in the original text pane
  const spanRefs = useRef<Record<string, HTMLElement | null>>({});

  const { originalText, setOriginalText, resetShadow, annotations, shadowCorrectedText } =
    useShadowStore();
  const { threadId, persistThreadId } = useSession();
  const {
    draft,
    setDraft,
    isStreaming,
    isReconnecting,
    isRecoveringSession,
    pendingAction,
    resetSession,
    hitlPause,
  } =
    useChatStore();
  const { startStream, resumeStream } = useStream();
  const isResumeRecovery = isRecoveringSession && pendingAction === "resume";

  const handleSubmit = useCallback(async () => {
    const trimmed = inputText.trim();
    if (!trimmed || isStreaming) return;
    resetSession();
    setOriginalText(trimmed);
    spanRefs.current = {};
    setActiveAnnotationId(null);
    setFeedbackText("");
    await startStream(trimmed, threadId, "shadow", persistThreadId);
  }, [inputText, isStreaming, persistThreadId, resetSession, setOriginalText, startStream, threadId]);

  const handleReset = useCallback(() => {
    resetSession();
    resetShadow();
    setInputText("");
    setActiveAnnotationId(null);
    setFeedbackText("");
    spanRefs.current = {};
  }, [resetSession, resetShadow]);

  /** Scroll original-text pane to the annotation's highlighted span. */
  const handleAnnotationClick = useCallback((ann: Annotation) => {
    setActiveAnnotationId(ann.id);
    const el = spanRefs.current[ann.id];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, []);

  /** Restore the full AI-corrected text (overwrite any manual edits). */
  const handleApplyAll = useCallback(() => {
    const target = shadowCorrectedText || draft;
    if (target) setDraft(target);
  }, [shadowCorrectedText, draft, setDraft]);

  const handleApprove = useCallback(async () => {
    if (!threadId) return;
    setFeedbackText("");
    await resumeStream(threadId, "approve", null, persistThreadId);
  }, [persistThreadId, resumeStream, threadId]);

  const handleReject = useCallback(async () => {
    const feedback = feedbackText.trim();
    if (!threadId || !feedback) return;
    await resumeStream(threadId, "reject", feedback, persistThreadId);
    setFeedbackText("");
  }, [feedbackText, persistThreadId, resumeStream, threadId]);

  // Memoize segments — recalculate only when originalText or annotations change,
  // not on every streaming draft update.
  const segments = useMemo(
    () => buildSegments(originalText, annotations),
    [originalText, annotations]
  );

  // ── Comparison view ──────────────────────────────────────────────────────
  if (originalText) {
    const showHitlPanel =
      hitlPause?.checkpoint_id === "shadow_checkpoint" &&
      !isStreaming &&
      !isReconnecting &&
      threadId;

    return (
      <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
        <div className="shrink-0 border-b bg-muted/20">
          <div className="flex min-h-10 flex-wrap items-center gap-2 px-3 py-2 sm:px-4">
            {isStreaming ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                <span className="text-xs text-muted-foreground">Analizuję tekst...</span>
              </>
            ) : isReconnecting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                <span className="text-xs text-muted-foreground">Ponawiam połączenie...</span>
              </>
            ) : isResumeRecovery ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                <span className="text-xs text-muted-foreground">
                  Przywracam stan sesji po wysłaniu decyzji...
                </span>
              </>
            ) : isRecoveringSession ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                <span className="text-xs text-muted-foreground">
                  Trwa przetwarzanie — oczekuję na wynik...
                </span>
              </>
            ) : (
              <span className="text-xs text-muted-foreground">
                Analiza zakończona
                {annotations.length > 0 && ` · ${annotations.length} adnotacji`}
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={handleReset}
              disabled={isStreaming}
              className="h-7 gap-1.5 text-xs sm:ml-auto"
            >
              <RotateCcw className="h-3 w-3" />
              Nowy tekst
            </Button>
          </div>

          {showHitlPanel && (
            <div className="space-y-3 border-t bg-background px-3 py-3 sm:px-4">
              <p className="text-xs font-medium text-foreground">
                Zatwierdzasz adnotacje?
                {hitlPause?.iteration_count !== undefined &&
                  ` Iteracja ${hitlPause.iteration_count + 1}/3`}
              </p>
              {isResumeRecovery && (
                <p className="text-xs text-muted-foreground">
                  Decyzja została już wysłana. Panel pozostaje widoczny do czasu odzyskania stanu z historii.
                </p>
              )}
              <div className="flex flex-col gap-2 sm:flex-row">
                <Button
                  size="sm"
                  onClick={handleApprove}
                  disabled={isResumeRecovery}
                  className="w-full sm:w-auto"
                >
                  Zatwierdź
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleReject}
                  disabled={!feedbackText.trim() || isResumeRecovery}
                  className="w-full sm:w-auto"
                >
                  Odrzuć
                </Button>
              </div>
              <Textarea
                value={feedbackText}
                onChange={(e) => setFeedbackText(e.target.value)}
                placeholder="Napisz co poprawić (wymagane do odrzucenia)..."
                className="text-xs min-h-[60px] resize-none"
                disabled={isResumeRecovery}
              />
            </div>
          )}
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="lg:hidden">
            <ShadowAnnotationsSection
              annotations={annotations}
              activeId={activeAnnotationId}
              onAnnotationClick={handleAnnotationClick}
              onApplyAll={handleApplyAll}
              isStreaming={isStreaming}
            />
          </div>

          <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
            <AnnotationList
              annotations={annotations}
              activeId={activeAnnotationId}
              onAnnotationClick={handleAnnotationClick}
              onApplyAll={handleApplyAll}
              isStreaming={isStreaming}
              className="hidden lg:flex"
            />

            <div className="flex min-h-[16rem] min-w-0 flex-1 flex-col overflow-hidden border-b lg:min-h-0 lg:border-b-0 lg:border-r">
              <div className="shrink-0 border-b bg-muted/10 px-3 py-2 sm:px-4">
                <div className="flex items-center gap-2">
                  <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Tekst oryginalny
                  </span>
                </div>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-4">
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                  {annotations.length > 0
                    ? segments.map((seg, i) => {
                        if (seg.type === "text") {
                          return <span key={i}>{seg.content}</span>;
                        }
                        const isActive = activeAnnotationId === seg.annotation.id;
                        return (
                          <mark
                            key={i}
                            ref={(el) => {
                              spanRefs.current[seg.annotation.id] = el;
                            }}
                            onClick={() => handleAnnotationClick(seg.annotation)}
                            title={seg.annotation.reason}
                            className={[
                              "cursor-pointer rounded transition-colors duration-150",
                              isActive
                                ? "bg-amber-300 dark:bg-amber-600"
                                : "bg-amber-100 hover:bg-amber-200 dark:bg-amber-900/40 dark:hover:bg-amber-800/60",
                            ].join(" ")}
                          >
                            {seg.content}
                          </mark>
                        );
                      })
                    : originalText}
                </p>
              </div>
            </div>

            <div className="flex min-h-[16rem] min-w-0 flex-1 flex-col overflow-hidden bg-muted/10 lg:min-h-0">
              <div className="shrink-0 border-b bg-muted/10 px-3 py-2 sm:px-4">
                <div className="flex items-center gap-2">
                  <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Wersja poprawiona
                  </span>
                  {isStreaming && (
                    <span className="ml-auto text-xs italic text-muted-foreground">
                      Trwa generowanie...
                    </span>
                  )}
                </div>
              </div>
              <div className="flex-1 overflow-hidden p-4">
                {isStreaming && !draft ? (
                  <div className="space-y-2.5">
                    <div className="h-3.5 w-3/4 animate-pulse rounded bg-muted/50" />
                    <div className="h-3.5 w-full animate-pulse rounded bg-muted/50" />
                    <div className="h-3.5 w-5/6 animate-pulse rounded bg-muted/50" />
                    <div className="h-3.5 w-2/3 animate-pulse rounded bg-muted/50" />
                  </div>
                ) : (
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    readOnly={isStreaming}
                    className="h-full min-h-[12rem] w-full resize-none bg-transparent text-sm leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none lg:min-h-0"
                    placeholder={isStreaming ? "" : "Poprawiona wersja pojawi się tutaj..."}
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Input view (initial state) ───────────────────────────────────────────
  return (
    <div className="flex h-full items-center justify-center overflow-hidden bg-background p-4 sm:p-8">
      <div className="w-full max-w-2xl space-y-4">
        <div className="space-y-1.5">
          <h2 className="text-lg font-semibold text-foreground">Tryb Cień</h2>
          <p className="text-sm text-muted-foreground">
            Wklej dowolny tekst, a AI przepisze go tak, żeby brzmiał jak Twój.
          </p>
        </div>
        <Textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Wklej tekst do analizy..."
          className="min-h-[200px] resize-none text-sm"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit();
          }}
        />
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-xs text-muted-foreground">⌘+Enter aby wysłać</span>
          <Button
            onClick={handleSubmit}
            disabled={!inputText.trim() || isStreaming}
            size="sm"
            className="w-full sm:w-auto"
          >
            {isStreaming ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Analizuję...
              </>
            ) : (
              "Analizuj styl"
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

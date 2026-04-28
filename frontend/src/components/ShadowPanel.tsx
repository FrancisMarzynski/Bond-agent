"use client";
import { useState, useCallback, useRef, useMemo } from "react";
import { useShadowStore, type Annotation } from "@/store/shadowStore";
import { useChatStore } from "@/store/chatStore";
import { useSession } from "@/hooks/useSession";
import { useStream } from "@/hooks/useStream";
import { AnnotationList } from "@/components/AnnotationList";
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
//   2. Comparison  — annotation sidebar | original (highlighted) | corrected (editable)
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
      <div className="flex flex-col h-full bg-background overflow-hidden">
        {/* Status bar */}
        <div className="border-b shrink-0 bg-muted/20">
          <div className="h-10 flex items-center px-4 gap-2">
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
              className="ml-auto h-7 text-xs gap-1.5"
            >
              <RotateCcw className="h-3 w-3" />
              Nowy tekst
            </Button>
          </div>

          {showHitlPanel && (
            <div className="border-t px-4 py-3 space-y-2 bg-background">
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
              <div className="flex gap-2">
                <Button size="sm" onClick={handleApprove} disabled={isResumeRecovery}>
                  Zatwierdź
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleReject}
                  disabled={!feedbackText.trim() || isResumeRecovery}
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

        {/* Three-column layout */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* Column 1: Annotation list sidebar */}
          <AnnotationList
            annotations={annotations}
            activeId={activeAnnotationId}
            onAnnotationClick={handleAnnotationClick}
            onApplyAll={handleApplyAll}
            isStreaming={isStreaming}
          />

          {/* Column 2: Original text with highlighted annotation spans */}
          <div className="flex-1 flex flex-col border-r overflow-hidden min-w-0">
            <div className="flex items-center gap-2 px-4 py-2 border-b bg-muted/10 shrink-0">
              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Tekst oryginalny
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
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
                            "rounded cursor-pointer transition-colors duration-150",
                            isActive
                              ? "bg-amber-300 dark:bg-amber-600"
                              : "bg-amber-100 dark:bg-amber-900/40 hover:bg-amber-200 dark:hover:bg-amber-800/60",
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

          {/* Column 3: Corrected text — editable after streaming */}
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-muted/10">
            <div className="flex items-center gap-2 px-4 py-2 border-b bg-muted/10 shrink-0">
              <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Wersja poprawiona
              </span>
              {isStreaming && (
                <span className="ml-auto text-xs text-muted-foreground italic">
                  Trwa generowanie...
                </span>
              )}
            </div>
            <div className="flex-1 overflow-hidden p-4">
              {isStreaming && !draft ? (
                /* Skeleton while waiting for corrected text */
                <div className="space-y-2.5">
                  <div className="h-3.5 bg-muted/50 rounded animate-pulse w-3/4" />
                  <div className="h-3.5 bg-muted/50 rounded animate-pulse w-full" />
                  <div className="h-3.5 bg-muted/50 rounded animate-pulse w-5/6" />
                  <div className="h-3.5 bg-muted/50 rounded animate-pulse w-2/3" />
                </div>
              ) : (
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  readOnly={isStreaming}
                  className="w-full h-full resize-none bg-transparent text-sm text-foreground leading-relaxed focus:outline-none placeholder:text-muted-foreground"
                  placeholder={isStreaming ? "" : "Poprawiona wersja pojawi się tutaj..."}
                />
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Input view (initial state) ───────────────────────────────────────────
  return (
    <div className="flex flex-col h-full bg-background overflow-hidden items-center justify-center p-8">
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
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">⌘+Enter aby wysłać</span>
          <Button
            onClick={handleSubmit}
            disabled={!inputText.trim() || isStreaming}
            size="sm"
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

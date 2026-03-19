"use client";
import { useState, useCallback } from "react";
import { useShadowStore } from "@/store/shadowStore";
import { useChatStore } from "@/store/chatStore";
import { useStream } from "@/hooks/useStream";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, RotateCcw, FileText, Pencil } from "lucide-react";

// ---------------------------------------------------------------------------
// ShadowPanel — two-phase UI:
//   1. Input view  — user submits text for style analysis
//   2. Comparison  — original (read-only) left / corrected (editable) right
// ---------------------------------------------------------------------------
export function ShadowPanel() {
  const [inputText, setInputText] = useState("");

  const { originalText, setOriginalText, resetShadow } = useShadowStore();
  const { draft, setDraft, isStreaming, threadId, setThreadId, resetSession } = useChatStore();
  const { startStream } = useStream();

  const handleSubmit = useCallback(async () => {
    const trimmed = inputText.trim();
    if (!trimmed || isStreaming) return;
    resetSession();
    setOriginalText(trimmed);
    await startStream(trimmed, threadId, "shadow", (id) => setThreadId(id));
  }, [inputText, isStreaming, resetSession, setOriginalText, startStream, threadId, setThreadId]);

  const handleReset = useCallback(() => {
    resetSession();
    resetShadow();
    setInputText("");
  }, [resetSession, resetShadow]);

  // ── Comparison view ──────────────────────────────────────────────────────
  if (originalText) {
    return (
      <div className="flex flex-col h-full bg-background overflow-hidden">
        {/* Status bar */}
        <div className="h-10 border-b flex items-center px-4 gap-2 shrink-0 bg-muted/20">
          {isStreaming ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Analizuję tekst...</span>
            </>
          ) : (
            <span className="text-xs text-muted-foreground">Analiza zakończona</span>
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

        {/* Two-column layout */}
        <div className="flex flex-1 min-h-0 overflow-hidden flex-col md:flex-row">
          {/* Left: Original text — read-only */}
          <div className="w-full md:w-1/2 flex flex-col border-r overflow-hidden shrink-0">
            <div className="flex items-center gap-2 px-4 py-2 border-b bg-muted/10 shrink-0">
              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Tekst oryginalny
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                {originalText}
              </p>
            </div>
          </div>

          {/* Right: Corrected text — editable after streaming */}
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
                /* Skeleton while waiting for first tokens */
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
            Wklej tekst, który chcesz dopasować do stylu swojego korpusu.
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

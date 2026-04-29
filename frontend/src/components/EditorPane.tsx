"use client";
import { useRef, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import "@uiw/react-md-editor/markdown-editor.css";
import { useChatStore } from "@/store/chatStore";
import { Button } from "@/components/ui/button";
import { writeAuthorDraftOverride } from "@/lib/draftPersistence";

// Dynamic import required — @uiw/react-md-editor uses browser APIs (no SSR)
const MDEditor = dynamic(() => import("@uiw/react-md-editor"), { ssr: false });

export function EditorPane() {
  const { draft, setDraft, isStreaming, threadId, mode } = useChatStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const persistTimerRef = useRef<number | null>(null);
  const pendingThreadIdRef = useRef<string | null>(null);
  const pendingDraftRef = useRef<string | null>(null);
  const [copyLabel, setCopyLabel] = useState("Kopiuj MD");

  // Automatyczne przewijanie edytora do najnowszych fragmentów tekstu
  useEffect(() => {
    if (isStreaming && containerRef.current) {
      const previewContainer = containerRef.current.querySelector<HTMLElement>(".w-md-editor-preview");
      if (previewContainer) {
        previewContainer.scrollTop = previewContainer.scrollHeight;
      } else {
        containerRef.current.scrollTop = containerRef.current.scrollHeight;
      }
    }
  }, [draft, isStreaming]);

  function flushPendingDraftPersist() {
    if (persistTimerRef.current !== null) {
      window.clearTimeout(persistTimerRef.current);
      persistTimerRef.current = null;
    }

    const pendingThreadId = pendingThreadIdRef.current;
    const pendingDraft = pendingDraftRef.current;
    if (pendingThreadId !== null && pendingDraft !== null) {
      writeAuthorDraftOverride(pendingThreadId, pendingDraft);
    }

    pendingThreadIdRef.current = null;
    pendingDraftRef.current = null;
  }

  useEffect(() => {
    return () => {
      flushPendingDraftPersist();
    };
  }, []);

  useEffect(() => {
    if (isStreaming) {
      flushPendingDraftPersist();
    }
  }, [isStreaming]);

  useEffect(() => {
    if (
      pendingThreadIdRef.current !== null &&
      pendingThreadIdRef.current !== threadId
    ) {
      flushPendingDraftPersist();
    }
  }, [threadId]);

  function handleCopyMd() {
    navigator.clipboard.writeText(draft).then(() => {
      setCopyLabel("Skopiowano!");
      setTimeout(() => setCopyLabel("Kopiuj MD"), 2000);
    });
  }

  function handleDownloadMd() {
    const blob = new Blob([draft], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "draft.md";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.setTimeout(() => {
      URL.revokeObjectURL(url);
    }, 0);
  }

  function handleDraftChange(value: string) {
    setDraft(value);

    if (mode !== "author" || isStreaming || !threadId) {
      return;
    }

    pendingThreadIdRef.current = threadId;
    pendingDraftRef.current = value;

    if (persistTimerRef.current !== null) {
      window.clearTimeout(persistTimerRef.current);
    }

    persistTimerRef.current = window.setTimeout(() => {
      flushPendingDraftPersist();
    }, 200);
  }

  if (!draft && !isStreaming) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm p-8">
        Wersja robocza pojawi się tutaj podczas generowania.
      </div>
    );
  }

  return (
    <div className="flex flex-1 min-h-0 flex-col overflow-hidden">
      {draft && !isStreaming && (
        <div className="shrink-0 border-b bg-background px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleCopyMd}>
              {copyLabel}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadMd}
              data-testid="download-markdown"
            >
              Pobierz .md
            </Button>
          </div>
        </div>
      )}
      <div
        ref={containerRef}
        className="flex min-h-0 flex-1 flex-col overflow-hidden"
        data-color-mode="light"
        data-testid="author-draft-editor"
      >
        <MDEditor
          value={draft}
          onChange={(val) => handleDraftChange(val ?? "")}
          height="100%"
          preview={isStreaming ? "preview" : "live"}
          hideToolbar={isStreaming}
          style={{ flex: 1, overflow: "hidden" }}
        />
      </div>
    </div>
  );
}

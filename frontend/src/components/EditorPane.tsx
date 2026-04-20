"use client";
import React, { useRef, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import "@uiw/react-md-editor/markdown-editor.css";
import { useChatStore } from "@/store/chatStore";
import { Button } from "@/components/ui/button";

// Dynamic import required — @uiw/react-md-editor uses browser APIs (no SSR)
const MDEditor = dynamic(() => import("@uiw/react-md-editor"), { ssr: false });

export function EditorPane() {
  const { draft, setDraft, isStreaming } = useChatStore();
  const containerRef = useRef<HTMLDivElement>(null);
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
    URL.revokeObjectURL(url);
  }

  if (!draft && !isStreaming) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm p-8">
        Wersja robocza pojawi się tutaj podczas generowania.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      {draft && !isStreaming && (
        <div className="flex items-center gap-2 px-3 py-2 border-b bg-background shrink-0">
          <Button variant="outline" size="sm" onClick={handleCopyMd}>
            {copyLabel}
          </Button>
          <Button variant="outline" size="sm" onClick={handleDownloadMd}>
            Pobierz .md
          </Button>
        </div>
      )}
      <div ref={containerRef} className="flex-1 overflow-hidden flex flex-col" data-color-mode="light">
        <MDEditor
          value={draft}
          onChange={(val) => setDraft(val ?? "")}
          height="100%"
          preview={isStreaming ? "preview" : "live"}
          hideToolbar={isStreaming}
          style={{ flex: 1, overflow: "hidden" }}
        />
      </div>
    </div>
  );
}

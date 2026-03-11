"use client";
import React, { useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import "@uiw/react-md-editor/markdown-editor.css";
import { useChatStore } from "@/store/chatStore";

// Dynamic import required — @uiw/react-md-editor uses browser APIs (no SSR)
const MDEditor = dynamic(() => import("@uiw/react-md-editor"), { ssr: false });

export function EditorPane() {
  const { draft, setDraft, isStreaming } = useChatStore();
  const containerRef = useRef<HTMLDivElement>(null);

  // Automatyczne przewijanie edytora do najnowszych fragmentów tekstu
  useEffect(() => {
    if (isStreaming && containerRef.current) {
      // Find the preview container inside the editor and scroll it to bottom
      const previewContainer = containerRef.current.querySelector(".w-md-editor-preview");
      if (previewContainer) {
        previewContainer.scrollTop = previewContainer.scrollHeight;
      }
    }
  }, [draft, isStreaming]);

  if (!draft && !isStreaming) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm p-8">
        Draft will appear here as it is generated.
      </div>
    );
  }

  return (
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
  );
}

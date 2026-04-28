"use client";
import { useRef, useEffect, useState } from "react";
import { useChatStore } from "@/store/chatStore";
import { useSession } from "@/hooks/useSession";
import { useStream } from "@/hooks/useStream";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Send } from "lucide-react";
import { cn } from "@/lib/utils";

export function ChatInterface() {
  const { messages, isStreaming, mode } = useChatStore();
  const { threadId, persistThreadId } = useSession();
  const { startStream } = useStream();
  const [input, setInput] = useState("");
  const [lastMessage, setLastMessage] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (msg?: string) => {
    const text = (msg ?? input).trim();
    if (!text || isStreaming) return;
    setLastMessage(text);
    setInput("");
    await startStream(text, threadId, mode, persistThreadId);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-4 space-y-3">
        {messages.length === 0 && (
          <p className="text-center text-muted-foreground text-sm mt-8">
            Wprowadź temat oraz słowa kluczowe, by zacząć.
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
            <div className={cn(
              "max-w-[92%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap sm:max-w-[88%] lg:max-w-[85%]",
              msg.role === "user"
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-foreground"
            )}>
              {msg.content}
              {msg.role === "assistant" && msg.content.startsWith("Error:") && (
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-2 text-xs"
                  onClick={() => handleSend(lastMessage)}
                  disabled={isStreaming}
                >
                  Spróbuj ponownie
                </Button>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="shrink-0 border-t p-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Wpisz temat i wymagania..."
          rows={2}
          disabled={isStreaming}
          className="min-h-[88px] flex-1 resize-none bg-background text-sm sm:min-h-[72px]"
        />
          <div className="flex justify-end sm:shrink-0">
            <Button
              onClick={() => handleSend()}
              disabled={!input.trim() || isStreaming}
              size="icon"
              aria-label="Send"
            >
              {isStreaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

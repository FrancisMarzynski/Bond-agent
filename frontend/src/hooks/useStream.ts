"use client";
import { useEffect, useCallback } from "react";
import { z } from "zod";

import { API_URL } from "@/config";
import { loadSessionHistory, SessionHistoryNotFoundError } from "@/hooks/useSession";
import { SSEParser } from "@/lib/sse";
import {
  classifyDisconnect,
  getRecoveryDisposition,
} from "@/lib/streamRecovery";
import {
  useChatStore,
  type PendingAction,
  type Stage,
  type StageStatus,
} from "@/store/chatStore";
import { useShadowStore } from "@/store/shadowStore";

const MAX_RETRIES = 5;
const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;
const RECOVERY_POLL_DELAY_MS = 1_500;
const MAX_RECOVERY_DURATION_MS = 10 * 60 * 1_000;

function backoffDelay(attempt: number): number {
  const exponential = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
  return exponential + Math.random() * 500;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseNestedPayload(raw: unknown): unknown {
  if (typeof raw !== "string") {
    return raw;
  }

  const trimmed = raw.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) {
    return raw;
  }

  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return raw;
  }
}

// ---------------------------------------------------------------------------
// Zod schemas — defined once at module scope, not re-created on every event.
// ---------------------------------------------------------------------------
const ThreadIdSchema = z.object({ thread_id: z.string() });
const TokenSchema = z.object({ token: z.string() });
const StageSchema = z.object({ stage: z.string(), status: z.string() });
const MessageSchema = z.object({ content: z.string() });
const AnnotationSchema = z.object({
  id: z.string(),
  original_span: z.string(),
  replacement: z.string(),
  reason: z.string(),
  start_index: z.number(),
  end_index: z.number(),
});
const HitlPauseSchema = z.object({
  checkpoint_id: z.string(),
  type: z.string(),
  iterations_remaining: z.number().optional(),
  research_report: z.string().optional(),
  heading_structure: z.string().optional(),
  cp1_iterations: z.number().optional(),
  warning: z.string().optional(),
  existing_title: z.string().optional(),
  existing_date: z.string().optional(),
  similarity_score: z.number().optional(),
  draft: z.string().optional(),
  draft_validated: z.boolean().optional(),
  cp2_iterations: z.number().optional(),
  validation_warning: z.string().optional(),
  corpus_count: z.number().optional(),
  threshold: z.number().optional(),
  annotations: z.array(AnnotationSchema).optional(),
  shadow_corrected_text: z.string().optional(),
  iteration_count: z.number().optional(),
});
const ErrorSchema = z.object({
  message: z.string().optional(),
  data: z.string().optional(),
});
const TextPayloadSchema = z.object({
  text: z.string().optional(),
  message: z.string().optional(),
  data: z.string().optional(),
});

function setTerminalError(message: string): void {
  const store = useChatStore.getState();
  store.setStreaming(false);
  store.setReconnecting(false);
  store.setRecoveringSession(false);
  store.setPendingAction(null);
  store.setSystemAlert(message);

  const currentStage = useChatStore.getState().stage;
  const stageToMark =
    currentStage !== "idle" && currentStage !== "done" ? currentStage : "error";
  store.setStage(stageToMark, "error");
}

function clearResumePauseOnProgress(enabled: boolean, hasCleared: boolean): boolean {
  if (!enabled || hasCleared) {
    return hasCleared;
  }
  useChatStore.getState().setHitlPause(null);
  return true;
}

// ---------------------------------------------------------------------------
// Internal stream consumer
// Returns true when the stream ended cleanly (via 'done', 'hitl_pause', or 'error' event).
// Returns false if the stream was cut unexpectedly (connection drop, server crash, etc.).
// ---------------------------------------------------------------------------
async function consumeStream(
  response: Response,
  signal: AbortSignal,
  onThreadId: (id: string) => void,
  options: { clearPauseOnProgress?: boolean } = {}
): Promise<boolean> {
  if (!response.body) {
    throw new Error("Serwer nie zwrócił strumienia SSE.");
  }

  const parser = new SSEParser();
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let endedCleanly = false;
  let pauseCleared = false;

  try {
    while (true) {
      if (signal.aborted) {
        endedCleanly = true;
        break;
      }

      const { value, done } = await reader.read();
      if (done) break;
      if (!value) continue;

      const events = parser.feed(value);
      for (const { event, data } of events) {
        try {
          const parsed = JSON.parse(data) as { type?: string; data?: unknown };
          const eventType = parsed.type || event;

          const payload = parseNestedPayload(parsed.data);

          switch (eventType) {
            case "thread_id": {
              const result = ThreadIdSchema.safeParse(payload);
              if (!result.success) throw new Error("Invalid thread_id event data");
              onThreadId(result.data.thread_id);
              break;
            }
            case "token": {
              pauseCleared = clearResumePauseOnProgress(
                options.clearPauseOnProgress === true,
                pauseCleared
              );
              const tokenResult = TokenSchema.safeParse(payload);
              const tokenContent =
                typeof payload === "string"
                  ? payload
                  : tokenResult.success
                    ? tokenResult.data.token
                    : "";
              if (!tokenContent) throw new Error("Invalid token event data");
              useChatStore.getState().appendDraftToken(tokenContent);
              break;
            }
            case "stage": {
              pauseCleared = clearResumePauseOnProgress(
                options.clearPauseOnProgress === true,
                pauseCleared
              );
              const result = StageSchema.safeParse(payload);
              if (!result.success) throw new Error("Invalid stage event data");
              useChatStore
                .getState()
                .setStage(result.data.stage as Stage, result.data.status as StageStatus);
              break;
            }
            case "message": {
              const result = MessageSchema.safeParse(payload);
              if (!result.success) throw new Error("Invalid message event data");
              useChatStore
                .getState()
                .addMessage({ role: "assistant", content: result.data.content });
              break;
            }
            case "hitl_pause": {
              const result = HitlPauseSchema.safeParse(payload);
              if (!result.success) throw new Error("Invalid hitl_pause event data");
              const store = useChatStore.getState();
              store.setHitlPause({
                checkpoint_id: result.data.checkpoint_id,
                type: result.data.type,
                iterations_remaining: result.data.iterations_remaining,
                research_report: result.data.research_report,
                heading_structure: result.data.heading_structure,
                cp1_iterations: result.data.cp1_iterations,
                warning: result.data.warning,
                existing_title: result.data.existing_title,
                existing_date: result.data.existing_date,
                similarity_score: result.data.similarity_score,
                draft: result.data.draft,
                draft_validated: result.data.draft_validated,
                cp2_iterations: result.data.cp2_iterations,
                validation_warning: result.data.validation_warning,
                corpus_count: result.data.corpus_count,
                threshold: result.data.threshold,
                annotations: result.data.annotations,
                shadow_corrected_text: result.data.shadow_corrected_text,
                iteration_count: result.data.iteration_count,
              });
              if (result.data.checkpoint_id === "shadow_checkpoint") {
                const shadowState = useShadowStore.getState();
                shadowState.setAnnotations(result.data.annotations ?? []);
                shadowState.setShadowCorrectedText(
                  result.data.shadow_corrected_text ?? ""
                );
                store.setDraft(result.data.shadow_corrected_text ?? "");
              }
              store.setStreaming(false);
              store.setRecoveringSession(false);
              store.setPendingAction(null);
              endedCleanly = true;
              return endedCleanly;
            }
            case "error": {
              const errorResult = ErrorSchema.safeParse(payload);
              const errorMessage =
                typeof payload === "string"
                  ? payload
                  : errorResult.success
                    ? errorResult.data.message ||
                      errorResult.data.data ||
                      "Unknown error"
                    : "Unknown error";
              const store = useChatStore.getState();
              const currentStage =
                store.stage !== "idle" && store.stage !== "done"
                  ? store.stage
                  : "error";
              store.setStage(currentStage, "error");
              store.addMessage({
                role: "assistant",
                content: `Error: ${errorMessage}`,
              });
              store.setStreaming(false);
              store.setRecoveringSession(false);
              store.setPendingAction(null);
              endedCleanly = true;
              return endedCleanly;
            }
            case "shadow_corrected_text": {
              pauseCleared = clearResumePauseOnProgress(
                options.clearPauseOnProgress === true,
                pauseCleared
              );
              const textResult = TextPayloadSchema.safeParse(payload);
              const text =
                typeof payload === "string"
                  ? payload
                  : textResult.success
                    ? textResult.data.text || ""
                    : "";
              if (text) {
                useChatStore.getState().setDraft(text);
                useShadowStore.getState().setShadowCorrectedText(text);
              }
              break;
            }
            case "annotations": {
              pauseCleared = clearResumePauseOnProgress(
                options.clearPauseOnProgress === true,
                pauseCleared
              );
              const annotationsResult = z.array(AnnotationSchema).safeParse(payload);
              const annotations = annotationsResult.success ? annotationsResult.data : [];
              useShadowStore.getState().setAnnotations(annotations);
              break;
            }
            case "system_alert": {
              const alertResult = TextPayloadSchema.safeParse(payload);
              const alertMessage =
                typeof payload === "string"
                  ? payload
                  : alertResult.success
                    ? alertResult.data.message || alertResult.data.data || ""
                    : "";
              if (alertMessage) {
                useChatStore.getState().setSystemAlert(alertMessage);
              }
              break;
            }
            case "node_start":
            case "node_end":
              pauseCleared = clearResumePauseOnProgress(
                options.clearPauseOnProgress === true,
                pauseCleared
              );
              break;
            case "heartbeat":
              if (process.env.NODE_ENV === "development") {
                console.log("[SSE] Otrzymano heartbeat z serwera.");
              }
              break;
            case "done": {
              pauseCleared = clearResumePauseOnProgress(
                options.clearPauseOnProgress === true,
                pauseCleared
              );
              const store = useChatStore.getState();
              store.setHitlPause(null);
              store.setStage("done", "complete");
              store.setStreaming(false);
              store.setRecoveringSession(false);
              store.setPendingAction(null);
              endedCleanly = true;
              return endedCleanly;
            }
            default:
              if (process.env.NODE_ENV === "development") {
                console.warn(`Unhandled SSE event type: ${eventType}`, parsed);
              }
          }
        } catch (err) {
          if (process.env.NODE_ENV === "development") {
            console.warn("SSE parse error or invalid format:", data, err);
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  return endedCleanly;
}

async function openCommandStream(
  url: string,
  body: string,
  signal: AbortSignal
): Promise<Response | null> {
  const store = useChatStore.getState();
  let attempt = 0;

  while (attempt <= MAX_RETRIES) {
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal,
      });
      store.setReconnecting(false);
      return response;
    } catch (error: unknown) {
      if (error instanceof Error && error.name === "AbortError") {
        store.setReconnecting(false);
        return null;
      }

      attempt += 1;
      if (attempt <= MAX_RETRIES) {
        store.setReconnecting(true);
        await sleep(backoffDelay(attempt - 1));
        continue;
      }

      throw error;
    }
  }

  return null;
}

async function recoverCommittedSession(
  threadId: string,
  pendingAction: PendingAction,
  signal: AbortSignal
): Promise<void> {
  const store = useChatStore.getState();
  store.setStreaming(false);
  store.setReconnecting(false);
  store.setRecoveringSession(true);
  store.setPendingAction(pendingAction);

  const deadline = Date.now() + MAX_RECOVERY_DURATION_MS;
  let errorAttempts = 0;

  while (Date.now() < deadline) {
    if (signal.aborted) {
      return;
    }

    try {
      const history = await loadSessionHistory(threadId, {
        mode: "recovery",
        clearRecoveredPause: pendingAction === "resume",
      });
      const disposition = getRecoveryDisposition(history, pendingAction);

      if (disposition === "poll") {
        await sleep(RECOVERY_POLL_DELAY_MS);
        continue;
      }

      store.setRecoveringSession(false);
      store.setPendingAction(null);
      store.setStreaming(false);
      return;
    } catch (error: unknown) {
      if (error instanceof Error && error.name === "AbortError") {
        return;
      }

      if (error instanceof SessionHistoryNotFoundError) {
        setTerminalError("Nie udało się odnaleźć sesji podczas przywracania stanu.");
        return;
      }

      errorAttempts += 1;

      if (Date.now() < deadline) {
        await sleep(backoffDelay(errorAttempts - 1));
        continue;
      }

      setTerminalError(
        "[Błąd krytyczny]: Nie udało się przywrócić stanu sesji z historii."
      );
      return;
    }
  }

  setTerminalError(
    "[Błąd krytyczny]: Sesja nadal przetwarza zadanie, ale stan nie został odzyskany w oczekiwanym czasie."
  );
}

async function readErrorResponse(response: Response): Promise<string> {
  try {
    const text = await response.text();
    return text || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

async function runCommandStream(
  url: string,
  body: string,
  signal: AbortSignal,
  pendingAction: PendingAction,
  initialThreadId: string | null,
  onThreadId: (id: string) => void
): Promise<void> {
  let activeThreadId = initialThreadId;
  const handleThreadId = (id: string) => {
    activeThreadId = id;
    onThreadId(id);
  };

  const response = await openCommandStream(url, body, signal);
  if (!response) {
    return;
  }

  if (!response.ok) {
    const message = await readErrorResponse(response);
    if (classifyDisconnect(true) === "recover" && activeThreadId) {
      await recoverCommittedSession(activeThreadId, pendingAction, signal);
      return;
    }
    setTerminalError(`[Błąd krytyczny]: ${message}`);
    return;
  }

  // Read thread ID from response header immediately — before consuming the body.
  // This ensures same-tab recovery works even when the body drops before the
  // first thread_id SSE event is parsed.
  const headerThreadId = response.headers.get("X-Bond-Thread-Id");
  if (headerThreadId) {
    handleThreadId(headerThreadId);
  }

  const endedCleanly = await consumeStream(response, signal, handleThreadId, {
    clearPauseOnProgress: pendingAction === "resume",
  });

  if (endedCleanly || signal.aborted) {
    useChatStore.getState().setReconnecting(false);
    return;
  }

  if (classifyDisconnect(true) === "recover" && activeThreadId) {
    await recoverCommittedSession(activeThreadId, pendingAction, signal);
    return;
  }

  setTerminalError(
    "[Błąd krytyczny]: Połączenie zostało zerwane po rozpoczęciu przetwarzania, ale brak thread_id uniemożliwia odzyskanie sesji."
  );
}

// ---------------------------------------------------------------------------
// React hook — the single public export.
// ---------------------------------------------------------------------------
export function useStream() {
  const { createController, abortController } = useChatStore();

  useEffect(() => {
    return () => {
      abortController();
    };
  }, [abortController]);

  const startStream = useCallback(
    async (
      message: string,
      threadId: string | null,
      mode: "author" | "shadow",
      onThreadId: (id: string) => void
    ): Promise<void> => {
      const store = useChatStore.getState();
      if (store.isStreaming || store.isRecoveringSession) {
        console.warn("Stream is already active or recovering. Blocking startStream.");
        return;
      }

      store.setStreaming(true);
      store.setReconnecting(false);
      store.setRecoveringSession(false);
      store.setPendingAction("stream");
      store.addMessage({ role: "user", content: message });

      const signal = createController();

      try {
        await runCommandStream(
          `${API_URL}/api/chat/stream`,
          JSON.stringify({ message, thread_id: threadId, mode }),
          signal,
          "stream",
          threadId,
          onThreadId
        );
      } catch {
        setTerminalError(
          `[Błąd krytyczny]: Nie udało się nawiązać stabilnego połączenia po ${MAX_RETRIES} próbach.`
        );
      } finally {
        const latest = useChatStore.getState();
        if (!latest.isRecoveringSession) {
          latest.setReconnecting(false);
        }
        if (!latest.isStreaming && !latest.isRecoveringSession) {
          latest.setPendingAction(null);
        }
      }
    },
    [createController]
  );

  const resumeStream = useCallback(
    async (
      threadId: string,
      action: "approve" | "approve_save" | "reject",
      feedback: string | null,
      onThreadId: (id: string) => void
    ): Promise<void> => {
      const store = useChatStore.getState();
      if (store.isStreaming || store.isRecoveringSession) {
        console.warn("Stream is already active or recovering. Blocking resumeStream.");
        return;
      }

      store.setStreaming(true);
      store.setReconnecting(false);
      store.setRecoveringSession(false);
      store.setPendingAction("resume");

      const signal = createController();
      const normalizedAction = action === "approve_save" ? "approve" : action;

      try {
        await runCommandStream(
          `${API_URL}/api/chat/resume`,
          JSON.stringify({
            thread_id: threadId,
            action: normalizedAction,
            feedback,
          }),
          signal,
          "resume",
          threadId,
          onThreadId
        );
      } catch {
        setTerminalError(
          `[Błąd krytyczny]: Nie udało się nawiązać stabilnego połączenia po ${MAX_RETRIES} próbach.`
        );
      } finally {
        const latest = useChatStore.getState();
        if (!latest.isRecoveringSession) {
          latest.setReconnecting(false);
        }
        if (!latest.isStreaming && !latest.isRecoveringSession) {
          latest.setPendingAction(null);
        }
      }
    },
    [createController]
  );

  const stopStream = useCallback(() => {
    abortController();
  }, [abortController]);

  return { startStream, resumeStream, stopStream };
}

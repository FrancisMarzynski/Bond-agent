import type {
  ChatMessage,
  HitlPause,
  PendingAction,
  Stage,
  StageStatus,
} from "@/store/chatStore";
import type { Annotation } from "@/store/shadowStore";

export type SessionStatus = "idle" | "running" | "paused" | "completed" | "error";
export type DisconnectDisposition = "retry" | "recover";
export type RecoveryDisposition = "resume" | "stop" | "poll";
export type HydrationMode = "restore" | "recovery";

export interface SessionHistoryResponse {
  messages: ChatMessage[];
  stage: Stage;
  draft: string;
  hitlPause: HitlPause;
  stageStatus: Partial<Record<Stage, StageStatus>>;
  session_status: SessionStatus;
  pending_node: string | null;
  can_resume: boolean;
  originalText: string;
  annotations: Annotation[];
  shadowCorrectedText: string;
  active_command: "stream" | "resume" | null;
  error_message: string | null;
}

export interface SessionHydrationSnapshot {
  chat: {
    messages: ChatMessage[];
    draft: string;
    hitlPause: HitlPause;
    stage: Stage;
    stageStatus: Record<Stage, StageStatus>;
  };
  shadow: {
    originalText: string;
    annotations: Annotation[];
    shadowCorrectedText: string;
  };
}

interface BuildSessionHydrationOptions {
  mode?: HydrationMode;
  clearRecoveredPause?: boolean;
}

export interface SessionHydrationResult {
  chat: {
    messages: ChatMessage[];
    draft: string;
    hitlPause: HitlPause;
    stage: Stage;
    stageStatus: Partial<Record<Stage, StageStatus>>;
  };
  shadow: {
    originalText: string;
    annotations: Annotation[];
    shadowCorrectedText: string;
  };
}

export function classifyDisconnect(hasCommittedResponse: boolean): DisconnectDisposition {
  return hasCommittedResponse ? "recover" : "retry";
}

export function getRecoveryDisposition(
  history: SessionHistoryResponse,
  pendingAction: PendingAction
): RecoveryDisposition {
  // Terminal error — stop polling immediately.
  if (history.session_status === "error" || history.error_message) {
    return "stop";
  }
  if (history.session_status === "running") {
    return "poll";
  }
  if (history.session_status === "paused" && history.can_resume) {
    return "resume";
  }
  if (pendingAction === "resume" && history.can_resume) {
    return "resume";
  }
  return "stop";
}

export function buildSessionHydration(
  history: SessionHistoryResponse,
  current: SessionHydrationSnapshot,
  options: BuildSessionHydrationOptions = {}
): SessionHydrationResult {
  const mode = options.mode ?? "restore";
  const preserveVisibleContent = mode === "recovery";
  // Use the history stage unless it is "idle" in a live recovery scenario where
  // a non-idle current stage is more informative.
  const shouldPreferCurrentStage =
    mode === "recovery" &&
    history.session_status === "running" &&
    !history.can_resume &&
    history.stage === "idle" &&
    current.chat.stage !== "idle";
  const stage = shouldPreferCurrentStage ? current.chat.stage : history.stage;

  const stageStatus =
    history.stageStatus && Object.keys(history.stageStatus).length > 0
      ? history.stageStatus
      : current.chat.stageStatus;

  let hitlPause: HitlPause = history.hitlPause ?? null;
  if (
    preserveVisibleContent &&
    history.session_status === "running" &&
    !options.clearRecoveredPause
  ) {
    hitlPause = current.chat.hitlPause;
  }

  return {
    chat: {
      messages: Array.isArray(history.messages) ? history.messages : current.chat.messages,
      draft:
        history.draft || !preserveVisibleContent ? history.draft : current.chat.draft,
      hitlPause,
      stage,
      stageStatus,
    },
    shadow: {
      originalText:
        history.originalText || !preserveVisibleContent
          ? history.originalText
          : current.shadow.originalText,
      annotations:
        history.annotations.length > 0 || !preserveVisibleContent
          ? history.annotations
          : current.shadow.annotations,
      shadowCorrectedText:
        history.shadowCorrectedText || !preserveVisibleContent
          ? history.shadowCorrectedText
          : current.shadow.shadowCorrectedText,
    },
  };
}

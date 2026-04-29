const AUTHOR_DRAFT_OVERRIDE_PREFIX = "bond_author_draft_override:";
const AUTHOR_DRAFT_OVERRIDE_KIND = "author_manual_draft_override";

export interface AuthorDraftOverride {
  kind: typeof AUTHOR_DRAFT_OVERRIDE_KIND;
  threadId: string;
  draft: string;
  updatedAt: number;
}

function getSessionStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function getOverrideKey(threadId: string): string | null {
  const trimmedThreadId = threadId.trim();
  if (!trimmedThreadId) {
    return null;
  }

  return `${AUTHOR_DRAFT_OVERRIDE_PREFIX}${trimmedThreadId}`;
}

export function readAuthorDraftOverride(threadId: string): AuthorDraftOverride | null {
  const storage = getSessionStorage();
  const key = getOverrideKey(threadId);
  if (!storage || !key) {
    return null;
  }

  const raw = storage.getItem(key);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") {
      storage.removeItem(key);
      return null;
    }

    const candidate = parsed as Record<string, unknown>;
    const kind = candidate.kind;
    const storedThreadId = candidate.threadId;
    const draft = candidate.draft;
    const updatedAt = candidate.updatedAt;

    if (
      kind !== AUTHOR_DRAFT_OVERRIDE_KIND ||
      typeof storedThreadId !== "string" ||
      storedThreadId !== threadId ||
      typeof draft !== "string" ||
      typeof updatedAt !== "number"
    ) {
      storage.removeItem(key);
      return null;
    }

    return {
      kind,
      threadId: storedThreadId,
      draft,
      updatedAt,
    };
  } catch {
    storage.removeItem(key);
    return null;
  }
}

export function writeAuthorDraftOverride(threadId: string, draft: string): void {
  const storage = getSessionStorage();
  const key = getOverrideKey(threadId);
  if (!storage || !key) {
    return;
  }

  const payload: AuthorDraftOverride = {
    kind: AUTHOR_DRAFT_OVERRIDE_KIND,
    threadId,
    draft,
    updatedAt: Date.now(),
  };
  storage.setItem(key, JSON.stringify(payload));
}

export function clearAuthorDraftOverride(threadId: string): void {
  const storage = getSessionStorage();
  const key = getOverrideKey(threadId);
  if (!storage || !key) {
    return;
  }

  storage.removeItem(key);
}

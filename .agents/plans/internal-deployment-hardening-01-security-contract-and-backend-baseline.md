# Plan 01: Internal Deployment Hardening — Security Contract And Backend Baseline

## Goal

Define and implement the backend-side contract that all later deployment hardening depends on:

- internal auth settings
- trusted proxy header semantics
- protected vs bypassed paths
- request ID / timing middleware
- explicit liveness and readiness endpoints

This plan is the contract gate for the rest of the workstream.

## Scope

In scope:

- `bond/config.py`
- `.env.example`
- `bond/api/security.py`
- `bond/api/main.py`
- `tests/unit/api/test_internal_security.py`

Out of scope:

- `frontend/src/proxy.ts`
- frontend Basic Auth prompt behavior
- Docker / Compose topology
- README deployment instructions

## Read First

- `bond/api/main.py`
- `bond/api/routes/chat.py`
- `bond/api/routes/corpus.py`
- `bond/api/runtime.py`
- `bond/config.py`
- `bond/schemas.py`
- `tests/unit/api/test_chat.py`
- `tests/unit/api/test_chat_history.py`
- `tests/unit/api/test_corpus_url_ingest.py`
- `frontend/src/config.ts`

## Required Decisions

Lock these decisions in code before any frontend or deployment work:

1. Env contract:
   - `internal_auth_enabled`
   - `internal_proxy_token`
   - `internal_basic_auth_username`
   - `internal_basic_auth_password`
2. Protected paths:
   - protect app/API surfaces in internal mode
   - explicitly bypass backend health routes
3. Header contract:
   - use a single internal trusted header constant
   - validate it with constant-time comparison
4. Health contract:
   - keep `/health` stable as readiness alias unless there is a compelling compatibility issue
   - add `/health/live`
   - add `/health/ready`

## Implementation Tasks

### 1. Update `bond/config.py`

- Add settings for internal auth enablement and secrets.
- Keep auth disabled by default.
- Preserve singleton access via `from bond.config import settings`.

### 2. Update `.env.example`

- Document the new internal auth and proxy-token variables.
- Make it clear that they are optional in local dev and required for internal deployment mode.

### 3. Create `bond/api/security.py`

- Add shared helpers/constants for:
  - trusted header name
  - protected/bypass path decisions
  - header validation
- Keep this module backend-only. Do not leak the token into browser-facing code or examples.

### 4. Update `bond/api/main.py`

- Install one request middleware that:
  - assigns request ID
  - enforces proxy-token auth on protected routes when internal auth is enabled
  - bypasses health routes
  - measures request duration
  - attaches `X-Request-Id` to all responses, including auth failures
- Extend `CORSMiddleware.expose_headers` to include `X-Request-Id` without regressing `X-Bond-Thread-Id`.
- Add `/health/live` and `/health/ready`.
- Keep `/health` compatible.

### 5. Create `tests/unit/api/test_internal_security.py`

- Cover:
  - 401 on protected route without trusted header when internal auth is enabled
  - success with valid trusted header
  - bypass for `/health`, `/health/live`, `/health/ready`
  - `X-Request-Id` present on success and rejection paths
- Ensure existing tests stay green when auth is disabled by default.

## Validation

Run:

- `uv run python - <<'PY'\nfrom bond.config import settings\nprint(settings.internal_auth_enabled)\nPY`
- `uv run pytest tests/unit/api/test_internal_security.py`
- `uv run pytest tests/unit/api/test_chat.py tests/unit/api/test_chat_history.py tests/unit/api/test_corpus_url_ingest.py`
- `uv run pytest tests/unit/api/test_runtime.py`
- `uv run ruff check .`

## Done Criteria

- Backend contract exists and is tested.
- Direct protected backend access fails closed in internal mode.
- Health endpoints remain probe-friendly.
- Response headers consistently include `X-Request-Id`.
- No frontend or deployment file was required to fake or compensate for a missing backend contract.

## Handoff To Plan 02

Before starting Plan 02, confirm:

- trusted header name is final
- bypass list is final enough for frontend proxy matching
- `/health`, `/health/live`, `/health/ready` behavior is stable

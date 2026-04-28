# Feature: Internal Deployment Hardening

## Status

This file is now the **umbrella plan** for internal deployment hardening.
Do **not** implement this file as one monolithic pass.
Execute the child plans below in order.

## Why This Was Split

The original single plan mixed three different change surfaces with different rollback and validation needs:

1. backend trust contract and observability
2. frontend gateway/auth behavior
3. container topology, operator docs, and deployment validation

That coupling made the plan hard to execute safely in one pass. The split keeps one shared security contract while reducing blast radius and keeping each rollout independently testable.

## Goal

Harden Bond so 1–2 trusted internal operators can run it on a private server with:

- browser access gated by simple operator auth
- backend routes reject direct access when internal mode is enabled
- health and request-correlation surfaces suitable for probes and debugging
- deployment defaults that do not casually expose the backend
- docs that describe the real supported internal topology

## Execution Order

Run these child plans sequentially:

1. [internal-deployment-hardening-01-security-contract-and-backend-baseline.md](</Users/franciszekmarzynski/Downloads/Projects/Bond-agent/.agents/plans/internal-deployment-hardening-01-security-contract-and-backend-baseline.md>)
2. [internal-deployment-hardening-02-frontend-gateway-and-auth.md](</Users/franciszekmarzynski/Downloads/Projects/Bond-agent/.agents/plans/internal-deployment-hardening-02-frontend-gateway-and-auth.md>)
3. [internal-deployment-hardening-03-deployment-hardening-and-docs.md](</Users/franciszekmarzynski/Downloads/Projects/Bond-agent/.agents/plans/internal-deployment-hardening-03-deployment-hardening-and-docs.md>)

## Dependency Rules

- Plan 01 defines the contract for env vars, bypass paths, proxy-token header semantics, and request ID behavior.
- Plan 02 must consume the Plan 01 contract rather than inventing its own header names or bypass list.
- Plan 03 assumes Plans 01 and 02 are complete enough to validate the full internal deployment shape.

## Shared Invariants

- Do not change SSE event kinds or HITL payload shapes.
- Do not change LangGraph routing function bodies or `add_conditional_edges` wiring.
- Keep local dev ergonomics intact: the current direct-to-FastAPI SSE path in development remains allowed unless explicitly reworked and revalidated.
- Do not treat Next.js Proxy as sufficient on its own; backend enforcement remains required.
- Do not introduce repo-owned user accounts, JWT auth, or RBAC in this workstream.

## Deliverables Across The Split

- repo-owned internal auth contract in backend config/settings
- backend middleware for trusted-proxy enforcement, request timing, and `X-Request-Id`
- frontend proxy with HTTP Basic Auth and `/api/*` rewriting
- unauthenticated probe endpoints
- non-root backend container and internal compose override
- root planning docs, README, and operator docs aligned to the chosen rollout

## Overall Acceptance Criteria

- Internal deployment mode requires authenticated frontend access.
- FastAPI rejects protected direct requests without the trusted proxy header when internal mode is enabled.
- `/health`, `/health/live`, `/health/ready`, and frontend `/healthz` remain probeable where intended.
- `X-Request-Id` is returned on normal and rejected responses.
- Existing Author, Shadow, corpus, and recovery flows keep working.
- Backend container no longer runs as root for the internal deployment profile.
- Internal deployment no longer depends on publishing backend port `8000` publicly.
- Root docs describe the active post-v1 workstream and the actual deployment story.

## Documentation Note

Root planning docs and mirrored operator docs were updated together when this split was introduced so the active post-v1 focus no longer points at the older threshold-sampling follow-up as the immediate next task.

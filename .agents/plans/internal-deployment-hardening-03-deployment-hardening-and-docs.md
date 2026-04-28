# Plan 03: Internal Deployment Hardening — Deployment Hardening And Docs

## Goal

Package the backend/frontend contract into a deployable internal topology and document the supported operator workflow.

This plan is where container posture, compose topology, README instructions, and final planning-doc state are brought into sync with the implemented behavior.

## Scope

In scope:

- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.internal.yml`
- `README.md`
- `.planning/STATE.md`
- `.planning/PROJECT.md`
- `.planning/ROADMAP.md`
- mirrored operator docs if the current-state summary changes (`AGENTS.md`, `CLAUDE.md`)

Out of scope:

- changing the auth contract from Plans 01–02
- building SaaS auth, user management, or RBAC

## Dependency

Start after Plans 01 and 02 are complete enough to validate a real internal deployment shape.

## Read First

- `Dockerfile`
- `frontend/Dockerfile`
- `docker-compose.yml`
- `README.md`
- `.planning/STATE.md`
- `.planning/PROJECT.md`
- `.planning/ROADMAP.md`
- `AGENTS.md`
- `CLAUDE.md`
- Plans 01 and 02

## Required Outcomes

- backend container no longer runs as root
- compose files expose probeable services
- internal deployment profile keeps backend off the public host interface
- docs explain dev vs internal deployment behavior clearly
- root planning docs describe the actual active post-v1 work and stop implying older follow-ups are the immediate next task

## Implementation Tasks

### 1. Update `Dockerfile`

- Add a non-root backend user/group.
- Switch runtime to that user.
- Add an image-level healthcheck only if it improves clarity and does not fight the compose-level checks.

### 2. Update `docker-compose.yml`

- Add healthchecks for backend and frontend.
- Add `init: true` if adopted.
- Preserve local developer ergonomics; do not hide backend port in the base compose file if that breaks standard dev workflows.

### 3. Create `docker-compose.internal.yml`

- Keep frontend public.
- Avoid publishing backend `8000:8000` publicly.
- Add env hooks needed for internal auth and proxy-token configuration.

### 4. Update `README.md`

- Add a concise internal deployment section covering:
  - required env vars
  - compose command for internal deployment
  - public vs internal surfaces
  - probe endpoints
  - dev-vs-internal traffic differences

### 5. Update root and mirrored docs

- After implementation and validation, sync:
  - `.planning/STATE.md`
  - `.planning/PROJECT.md`
  - `.planning/ROADMAP.md`
  - `AGENTS.md`
  - `CLAUDE.md`
- Remove stale references to previous immediate follow-ups once internal hardening is the active or completed workstream.

## Validation

Run:

- `docker compose -f docker-compose.yml -f docker-compose.internal.yml config`
- `uv run ruff check .`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`

Manual validation:

1. `docker compose -f docker-compose.yml -f docker-compose.internal.yml up --build`
2. `curl -i http://localhost:3000/` returns `401`
3. `curl -i http://localhost:3000/healthz` returns `200`
4. Direct `http://localhost:8000` protected access is blocked or unavailable in the internal profile
5. Backend health endpoints return `200` from inside the compose network
6. One Author flow, one Shadow flow, and one corpus ingest succeed through the authenticated frontend

## Done Criteria

- Internal deployment topology is documented and reproducible.
- Backend is not casually exposed in the internal profile.
- Root planning docs reflect the actual repo state after validation.
- Operator docs no longer require tribal knowledge to understand the supported internal deployment shape.

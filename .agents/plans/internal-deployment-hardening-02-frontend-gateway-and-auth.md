# Plan 02: Internal Deployment Hardening — Frontend Gateway And Auth

## Goal

Add a single frontend gateway layer that:

- challenges operators with HTTP Basic Auth
- rewrites `/api/*` traffic to FastAPI
- injects the trusted backend header from Plan 01
- leaves static assets and probe paths reachable where intended

This plan must consume the backend contract from Plan 01 and must not redefine it.

## Scope

In scope:

- `frontend/src/proxy.ts`
- `frontend/src/app/healthz/route.ts`
- `frontend/next.config.ts`
- `frontend/scripts/test-proxy-auth.mjs`

Out of scope:

- backend auth contract changes except narrowly required bug fixes
- Docker / Compose rollout
- README and planning-doc finalization

## Dependency

Do not start implementation until Plan 01 has locked:

- trusted header constant
- internal env names
- backend bypass routes
- request/health behavior

## Read First

- `frontend/next.config.ts`
- `frontend/src/config.ts`
- `frontend/src/hooks/useStream.ts`
- `frontend/src/hooks/useSession.ts`
- `frontend/src/components/CorpusAddForm.tsx`
- `frontend/src/components/CorpusStatusPanel.tsx`
- `frontend/scripts/test-sse.mjs`
- Plan 01 output files

## Required Behavior

- Protected app routes and proxied API routes require Basic Auth in internal deployment mode.
- Static assets and framework internals remain accessible:
  - `/_next/*`
  - metadata/static files
  - `favicon.ico`
- Frontend health route `/healthz` must remain unauthenticated for probes.
- Proxied `/api/*` requests must add the trusted backend header expected by Plan 01.
- The gateway must preserve current request shapes for JSON, SSE, and `FormData`.

## Implementation Tasks

### 1. Update `frontend/next.config.ts`

- Remove or minimize any static `/api/:path*` rewrite that would compete with `src/proxy.ts`.
- Preserve existing standalone build behavior.

### 2. Create `frontend/src/proxy.ts`

- Implement Basic Auth challenge with `WWW-Authenticate: Basic`.
- Use constant-time comparison for username and password checks.
- Rewrite `/api/:path*` to `process.env.API_URL`.
- Inject the trusted backend header from Plan 01 only on proxied API traffic.
- Keep matcher / route selection centralized in this file.

### 3. Create `frontend/src/app/healthz/route.ts`

- Return a minimal 200 response without auth.
- Keep the path explicitly excluded from proxy auth.

### 4. Create `frontend/scripts/test-proxy-auth.mjs`

- Add a lightweight validation script that:
  - expects `401` + `WWW-Authenticate` on unauthenticated `/`
  - expects `200` on unauthenticated `/healthz`
  - verifies authenticated access can reach a proxied API route
- Mirror the skip-friendly behavior of `frontend/scripts/test-sse.mjs`.

## Validation

Run:

- `cd frontend && npm run build`
- `cd frontend && npm run lint`
- `node frontend/scripts/test-proxy-auth.mjs --frontend-url http://localhost:3000`

Manual checks:

1. `curl -i http://localhost:3000/` returns `401` with `WWW-Authenticate: Basic`
2. `curl -i http://localhost:3000/healthz` returns `200`
3. Browser login prompt appears at `/`
4. Author and Shadow mode still load after authentication
5. Corpus uploads still work through same-origin `/api/*`

## Done Criteria

- One gateway file owns auth and `/api/*` rewriting.
- Frontend auth uses the Plan 01 contract instead of inventing new backend assumptions.
- Session restore and SSE entry points still use the expected same-origin routes.
- Health and static paths are not accidentally challenged.

## Handoff To Plan 03

Before starting Plan 03, confirm:

- internal deployment can be exercised through the frontend
- authenticated proxying reaches backend routes successfully
- there is a stable manual validation flow worth documenting

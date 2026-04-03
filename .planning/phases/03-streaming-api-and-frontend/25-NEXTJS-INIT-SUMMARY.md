# 25-NEXTJS-INIT Podsumowanie: Inicjalizacja Next.js i konteneryzacja frontendu

**Data ukończenia:** 2026-04-01  
**Poprawki code review:** 2026-04-03  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 25 — Next.js Initialization & Frontend Docker  
**Status:** ✅ Zakończone

---

## Cel

Potwierdzenie gotowości bazy Next.js (App Router, Tailwind CSS, TypeScript) oraz przygotowanie obrazu Docker dla frontendu. Integracja z istniejącym `docker-compose.yml`.

---

## Stan wyjściowy

Frontend był już w pełni rozwinięty z wcześniejszych faz:

| Element | Stan |
|---------|------|
| Next.js 15 (App Router) | ✅ `src/app/` z layout + pages |
| TypeScript | ✅ `tsconfig.json` ze `strict: true` |
| Tailwind CSS v4 | ✅ `@import "tailwindcss"` w `globals.css` |
| `src/components/` | ✅ 16 komponentów (ChatInterface, EditorPane, itp.) |
| `src/hooks/` | ✅ `useSession.ts`, `useStream.ts` |
| `src/store/` | ✅ `chatStore.ts`, `shadowStore.ts` (Zustand) |
| Dockerfile frontendu | ❌ Brakowało |
| `output: "standalone"` | ❌ Brakowało |
| Serwis w docker-compose | ❌ Brakowało |

---

## Architektura obrazu Docker

```
node:20-alpine (deps)
│  npm ci → node_modules
│
node:20-alpine (builder)
│  COPY node_modules + source
│  npm run build → .next/standalone/
│
node:20-alpine (runner)   ← obraz finalny: 298 MB
│  COPY standalone/ + static/
│  USER nextjs (uid 1001, nie root)
│  PORT 3000
│  CMD node server.js
```

Trzy etapy eliminują `node_modules` z obrazu finalnego — Next.js standalone bundle zawiera tylko wymagane zależności runtime.

---

## Architektura URL API

Wszystkie wywołania API z przeglądarki używają **względnych ścieżek** (`/api/...`). Next.js serwer przekierowuje je do backendu przez mechanizm `rewrites` skonfigurowany w `next.config.ts`.

```
Przeglądarka → /api/chat/stream
                    ↓ (rewrite, serwer Next.js)
              http://bond-api:8000/api/chat/stream
```

Zalety:
- Brak zmiennych `NEXT_PUBLIC_` — żaden URL backendu nie trafia do przeglądarki
- Działa lokalnie (`API_URL` domyślnie `http://localhost:8000`) i w Dockerze (`http://bond-api:8000`)
- Bez zmian kodu frontendu przy zmianie środowiska

---

## Nowe/zmodyfikowane pliki

### `frontend/Dockerfile`

```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
```

### `frontend/.dockerignore`

```
node_modules
.next
.git
.DS_Store
*.tsbuildinfo
npm-debug.log*
.env*
Dockerfile
.dockerignore
```

### `frontend/next.config.ts`

```ts
import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
```

- `output: "standalone"` — wymagane do budowania minimalnego bundle dla Dockera
- `rewrites()` — proxy wszystkich wywołań `/api/*` do backendu; czyta `API_URL` z env w czasie startu serwera

### `frontend/src/config.ts`

```ts
// Empty string = relative URL. All /api/* calls are proxied server-side
// via next.config.ts rewrites (using the API_URL env var, not exposed to browser).
export const API_URL = "";

/** Maximum allowed file upload size in bytes (50 MB). */
export const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;
```

### `docker-compose.yml` — serwis `bond-frontend`

```yaml
bond-frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile
  ports:
    - "3000:3000"
  environment:
    - API_URL=http://bond-api:8000
  depends_on:
    - bond-api
  networks:
    - bond-public
  restart: unless-stopped
```

`API_URL` wskazuje na wewnętrzną nazwę serwisu Docker — czytana przez Next.js serwer w czasie startu (nie przez przeglądarkę).

---

## Wynik budowania

```
docker build -t bond-frontend:local ./frontend/
```

```
[deps]    npm ci             → 846 packages in 10s   ✅
[builder] npm run build      → compiled in 6.0s      ✅
[runner]  standalone export  → 298 MB image          ✅
```

```
REPOSITORY      TAG     IMAGE ID       SIZE
bond-frontend   local   ebd2dcbf34c7   298MB
```

Smoke test:
```bash
docker run --rm -p 3000:3000 bond-frontend:local
curl http://localhost:3000  # → HTTP 200 ✅
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Next.js 15 (App Router), Tailwind CSS v4, TypeScript | ✅ Wszystkie aktywne od wcześniejszych faz |
| Struktura `src/components`, `src/hooks`, `src/store` | ✅ 16 komponentów, 2 hooks, 2 stores (Zustand) |
| Pomyślny deployment na Dockerze (HTTP 200) | ✅ `bond-frontend:local` — 298MB, serwer odpowiada HTTP 200 |

---

## Uruchomienie

```bash
# Tylko frontend
docker build -t bond-frontend:local ./frontend/
docker run --rm -p 3000:3000 bond-frontend:local

# Pełne środowisko (API + ChromaDB + Frontend)
docker compose --env-file .env.docker up --build
```

Aplikacja dostępna pod: `http://localhost:3000`

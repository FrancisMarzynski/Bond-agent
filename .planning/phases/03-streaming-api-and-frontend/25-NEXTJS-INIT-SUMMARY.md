# 25-NEXTJS-INIT Podsumowanie: Inicjalizacja Next.js i konteneryzacja frontendu

**Data ukończenia:** 2026-04-01
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
| Next.js 16 (App Router) | ✅ `src/app/` z layout + pages |
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

## Nowe pliki

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

---

## Zmodyfikowane pliki

### `frontend/next.config.ts`

Dodano `output: "standalone"` — wymagane do budowania minimalnego bundle dla Dockera:

```ts
const nextConfig: NextConfig = {
  output: "standalone",
};
```

### `docker-compose.yml`

Dodano serwis `bond-frontend`:

```yaml
bond-frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile
  ports:
    - "3000:3000"
  environment:
    - NEXT_PUBLIC_API_URL=http://localhost:8000
  depends_on:
    - bond-api
  networks:
    - bond-public
  restart: unless-stopped
```

`NEXT_PUBLIC_API_URL` wskazuje na `bond-api` eksponowane na hoście pod portem 8000.

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
| Next.js 16 (App Router), Tailwind CSS v4, TypeScript | ✅ Wszystkie aktywne od wcześniejszych faz |
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

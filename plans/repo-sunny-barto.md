# STEP 010 — Next.js Frontend Skeleton + Backend API Integration

## Context

STEP 009까지 backend는 수집(RSS) → raw_events → LangGraph 처리 → event_cards 영속화 → Milvus 의미검색 → OpenSearch 키워드검색 → admin 운영 보조 (reconcile/requeue/reindex)까지 완성. 9개 Docker 컨테이너가 동시에 healthy 상태이고 22개 REST endpoint가 노출되어 있다. 그러나 **사용자가 직접 데이터를 확인할 UI가 0%**다. 이번 STEP은 Next.js frontend skeleton을 scratch에서 만들어 이벤트 목록/상세/검색/필터/admin 상태를 브라우저에서 보고 조작할 수 있게 만든다.

### 직접 확인한 현재 상태

**Frontend** — 완전 부재. `frontend/` 디렉터리 없음, package.json/lock/config/Dockerfile 전부 없음. `.gitignore`는 이미 `node_modules`, `.next`, `out`, `dist`, `build` 차단 (line 38-43).

**Backend API** (`backend/app/main.py`):
- 22개 endpoint, 모두 동작 중
- `GET /health`, `GET /api/events` (pagination 없음, 전체), `GET /api/events/{id}`, `GET /api/events/search?q=...`, `GET /api/themes`, `GET /api/sectors`, `GET /api/themes/{id}/events`, `GET /api/sectors/{id}/events`, comments/ai-replies
- Admin (X-Admin-Token 헤더): jobs, raw-events CRUD, reconcile-stuck, requeue, search/reindex, collect-rss-once, upsert-event, internal/search-similar
- **CORS 미설정** — `Grep CORS|CORSMiddleware` 0건. 브라우저에서 localhost:8000 호출 시 차단됨. **추가 필수**.
- ADMIN_API_TOKEN 빈값 → dev 모드에서 모든 admin endpoint 통과 (startup WARNING). 정책 유지.
- 스키마: `FinalEventCard{id,title,summary,theme,sectors[],entities[],impact_path,evidence[],confidence_score,status,created_at}`, `EventSearchResponse{total, hits[EventSearchHit]}` 등 확정

**Docker** (`docker-compose.dev.yml`):
- 9개 서비스, named network 없음 → `event-intelligence-dev_default` bridge 자동 생성
- backend host port `8000:8000`, 컨테이너 내부 DNS `backend:8000`
- 모든 앱 서비스(backend/worker/agent-worker)가 `env_file: .env` 사용 → ADMIN_API_TOKEN 자동 주입
- `/health` healthcheck 15s 간격

### 사용자 결정 (확정)

| 항목 | 결정 |
|---|---|
| Admin token UI 전략 | **Next Route Handler proxy** — ADMIN_API_TOKEN은 frontend 컨테이너 서버측 env에만, 브라우저는 `/api/admin/*` proxy만 호출 |
| Package manager | **npm** — lock file 없음, Node 20 LTS 기본 동봉, Dockerfile `npm ci` 단순 |
| Next.js / React | Next 15.0.x stable + React 19.0.x stable, App Router, TypeScript strict |
| Tailwind | v3.4.x 안정 (v4 alpha 회피) |
| UI 라이브러리 | shadcn/radix 도입하지 않음. 자체 컴포넌트 7개로 skeleton |
| Output mode | `next.config.mjs output: "standalone"` (이미지 크기 절감) |
| Fetch caching | 모든 server fetch에 `cache: "no-store"` 명시 |

---

## 핵심 설계

### 1. Frontend 디렉터리 구조

```
frontend/
├── Dockerfile
├── .dockerignore
├── .gitignore
├── .eslintrc.json
├── README.md
├── package.json
├── tsconfig.json
├── next.config.mjs
├── next-env.d.ts
├── postcss.config.mjs
├── tailwind.config.ts
├── public/favicon.ico
└── src/
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx                       # / (홈, 안내 + 최근 이벤트 link)
    │   ├── globals.css
    │   ├── loading.tsx
    │   ├── error.tsx
    │   ├── not-found.tsx
    │   ├── api/
    │   │   ├── health/route.ts            # frontend self-health (Docker healthcheck용)
    │   │   └── admin/
    │   │       ├── reindex/route.ts       # POST proxy
    │   │       ├── reconcile/route.ts     # POST proxy
    │   │       └── requeue/[id]/route.ts  # POST proxy
    │   ├── events/
    │   │   ├── page.tsx                   # 이벤트 목록
    │   │   └── [eventId]/page.tsx         # 상세
    │   ├── search/page.tsx                # ?q=...
    │   ├── themes/
    │   │   ├── page.tsx                   # 테마 인덱스
    │   │   └── [themeId]/page.tsx
    │   ├── sectors/
    │   │   ├── page.tsx
    │   │   └── [sectorId]/page.tsx
    │   └── admin/page.tsx                 # 상태 + reindex/requeue 트리거
    ├── components/
    │   ├── EventCard.tsx
    │   ├── EventList.tsx
    │   ├── SearchBar.tsx                  # client
    │   ├── EventFilters.tsx               # client
    │   ├── HealthStatus.tsx
    │   ├── AdminPanel.tsx                 # client (proxy 호출)
    │   ├── EmptyState.tsx
    │   └── ErrorState.tsx
    └── lib/
        ├── api/
        │   ├── types.ts                   # backend pydantic 미러
        │   ├── client.ts                  # 브라우저용 fetch wrapper
        │   ├── server.ts                  # "server-only" + adminFetch
        │   └── __tests__/client.test.mjs  # node --test
        └── config.ts                      # env 파싱
```

### 2. API client 분할 (브라우저 ↔ 서버 격리)

**`src/lib/api/client.ts`** (브라우저 안전):
```ts
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { ...init, cache: "no-store" });
  if (!res.ok) throw new ApiError(res.status, await res.text().catch(() => ""));
  return res.json();
}
export class ApiError extends Error {
  constructor(public status: number, public body: string) { super(`API ${status}`); }
}
export const api = {
  listEvents, getEvent, search, listThemes, listSectors, themeEvents, sectorEvents, health,
};
```

**`src/lib/api/server.ts`** (server-only):
```ts
import "server-only";
const INTERNAL = process.env.INTERNAL_API_BASE_URL ?? "http://backend:8000";
const TOKEN = process.env.ADMIN_API_TOKEN ?? "";
export async function adminFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (TOKEN) headers.set("X-Admin-Token", TOKEN);
  const res = await fetch(`${INTERNAL}${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) throw new Error(`admin api ${res.status}: ${await res.text()}`);
  return res.json();
}
```

`import "server-only"`가 client component import 시 빌드 에러를 던져 token 누출을 컴파일 단계에서 차단.

### 3. Route Handler proxy (admin mutation)

`src/app/api/admin/reindex/route.ts`:
```ts
import { adminFetch } from "@/lib/api/server";
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const out = await adminFetch("/api/admin/search/reindex", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dry_run: !!body.dry_run, limit: body.limit ?? 1000 }),
  });
  return Response.json(out);
}
```

브라우저는 `/api/admin/reindex`만 호출 → ADMIN_API_TOKEN 노출 0. 동일 패턴으로 `reconcile`, `requeue/[id]` 추가.

### 4. Backend CORS 추가

**`backend/app/core/config.py`**:
```python
CORS_ALLOW_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
```
env 값이 `,`로 구분된 string으로 오면 validator로 list 변환.

**`backend/app/main.py`**:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token", "Accept"],
    max_age=600,
)
```

### 5. Dockerfile (multi-stage standalone)

```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=optional

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN addgroup -S app && adduser -S app -G app
COPY --from=builder --chown=app:app /app/public ./public
COPY --from=builder --chown=app:app /app/.next/standalone ./
COPY --from=builder --chown=app:app /app/.next/static ./.next/static
USER app
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD wget -qO- http://127.0.0.1:3000/api/health || exit 1
CMD ["node", "server.js"]
```

### 6. docker-compose.dev.yml frontend service (append)

```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: ei-frontend
    ports:
      - "3000:3000"
    environment:
      NODE_ENV: production
      NEXT_PUBLIC_API_BASE_URL: ${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8000}
      INTERNAL_API_BASE_URL: http://backend:8000
    env_file:
      - .env
    depends_on:
      backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:3000/api/health"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 30s
    restart: on-failure
```

주의: `backend.depends_on`에 frontend 추가 절대 금지 (역방향). `NEXT_PUBLIC_*`는 빌드 타임 inline → host=`localhost` (브라우저 기준). SSR/route handler는 `INTERNAL_API_BASE_URL=http://backend:8000` 사용.

### 7. Pages 요약

| Route | 컴포넌트 종류 | 호출 | 실패 처리 |
|---|---|---|---|
| `/` | Server | api.listEvents 일부 미리보기 | ErrorState |
| `/events` | Server | api.listEvents | EmptyState / ErrorState |
| `/events/[eventId]` | Server | api.getEvent | 404 → notFound() |
| `/search` | Server (searchParams Promise) | api.search 조건부 | 503 → "검색 서비스 일시 중단" |
| `/themes` `/themes/[id]` | Server | api.listThemes / api.themeEvents | EmptyState |
| `/sectors` `/sectors/[id]` | Server | api.listSectors / api.sectorEvents | EmptyState |
| `/admin` | Server + Client AdminPanel | adminFetch jobs/health + proxy mutation | ErrorState, dev 경고 배너 |

`SearchBar`, `EventFilters`, `AdminPanel`만 `"use client"`. 나머지 server.

---

## 신규 / 수정 파일

### 신규
| 경로 | 목적 |
|---|---|
| `frontend/**` (전체 트리) | Next.js skeleton + Dockerfile + API client + 페이지 + 컴포넌트 |
| `backend/tests/test_cors.py` | OPTIONS preflight 3 케이스 |
| `docs/FRONTEND_DESIGN.md` | route table, server/client 정책, admin token 격리 사유 |
| `docs/DEPLOYMENT.md` | 없으면 신규. frontend 빌드/실행 절차 |
| `plans/010_NEXTJS_FRONTEND_SKELETON_PLAN.md` | 본 plan 영구 사본 |
| `plans/010_NEXTJS_FRONTEND_SKELETON_REPORT.md` | 실행 보고 |

### 수정
| 경로 | 변경 |
|---|---|
| `docker-compose.dev.yml` | frontend service 추가 (9→10 컨테이너) |
| `backend/app/main.py` | CORSMiddleware 추가 |
| `backend/app/core/config.py` | CORS_ALLOW_ORIGINS 필드 + redacted_env_status fields |
| `.env.example` | NEXT_PUBLIC_API_BASE_URL, CORS_ALLOW_ORIGINS 섹션 |
| `docs/ARCHITECTURE.md` | frontend 노드 추가 (browser → frontend SSR/CSR → backend) |
| `docs/TRD.md` | STEP 010 컴포넌트/env var |
| `docs/API_CONTRACT.md` | CORS 정책 + `/api/internal/search-similar` 누락 보정 |
| `docs/COMPATIBILITY_NOTES.md` | STEP 010 TODO (RBAC, shadcn, NEXT_PUBLIC production 대체, hybrid UI, i18n) |

---

## 비범위 (절대 하지 않음)

- 로그인 / 회원가입 / RBAC / OAuth
- 댓글 커뮤니티 UI 고도화
- 실시간 WebSocket / SSE
- DART/SEC collector
- Hybrid search ranking (Milvus + OpenSearch rerank)
- Production deploy / domain / TLS / CDN
- 디자인 완성도 / 애니메이션 / 다크모드
- i18n
- shadcn/ui / radix 도입
- `retrieve_past_context` 노드 변경

## 절대 금지

- `Remove-Item`, `rm`, `del`, `git reset --hard`, `git clean -fdx`
- `git push` (모든 변형)
- `docker volume rm`, `docker compose down -v`
- `.env` 실값, ADMIN_API_TOKEN 실값 로그/응답/번들/문서 노출
- `NEXT_PUBLIC_ADMIN_*` 같은 변수 정의
- node_modules, .next, build 산출물 commit
- codex worktree 파일 직접 수정

---

## 테스트 전략

### Frontend
1. `npm run typecheck` (`tsc --noEmit`) → 0 errors
2. `npm run lint` → 0 errors
3. `npm run build` → 성공, `.next/standalone/server.js` 생성
4. `npm run test` (node --test) — `api.search()` URL builder 1 케이스, `ApiError` 1 케이스

### Backend
- `backend/tests/test_cors.py` (3 케이스):
  1. `OPTIONS /api/events` + `Origin: localhost:3000` → 200 + `access-control-allow-origin` echo
  2. `OPTIONS /api/admin/jobs` + `Access-Control-Request-Headers: x-admin-token` → 200, header allow
  3. `Origin: http://evil.example` → allow-origin 없음
- 기존 회귀: `pytest backend/tests agents/tests workers/tests -q` (127+ PASS 유지)

### Smoke
- Docker: `docker compose build frontend && up -d frontend && ps frontend healthy`
- HTTP:
  - `curl http://localhost:3000/api/health` → `{"status":"ok"}`
  - `curl -I http://localhost:3000/events` → 200
  - `curl -I "http://localhost:3000/search?q=test"` → 200
  - `curl -I http://localhost:3000/admin` → 200
- CORS:
  - `curl -i -X OPTIONS http://localhost:8000/api/events -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET"` → `access-control-allow-origin: http://localhost:3000`
- 기존 smoke 8종 회귀 (gate env 동일)

### 수동 브라우저 점검 (report에 기록)
1. `/events` 카드 목록 또는 EmptyState
2. 카드 클릭 → 상세
3. `/search` 폼 → 결과 or 503 ErrorState
4. `/themes/policy_korea` 등 5개 theme
5. `/admin` health 4-component + reindex 버튼 동작

---

## 실행 순서

### Phase 0 — Pre-flight
- `git status`, `docker compose ps`, `Test-Path frontend` 재확인
- working tree clean, 9 컨테이너 healthy, frontend 부재 확인

### Phase 1 — Scaffold
- `frontend/package.json`, `tsconfig.json`, `next.config.mjs`, `tailwind.config.ts`, `postcss.config.mjs`, `.eslintrc.json`, `.gitignore`, `.dockerignore`, `next-env.d.ts`
- `src/app/layout.tsx`, `page.tsx`, `globals.css`, `loading.tsx`, `error.tsx`, `not-found.tsx`
- `src/app/api/health/route.ts`
- `frontend/public/favicon.ico` placeholder

### Phase 2 — API client
- `src/lib/api/types.ts`, `client.ts`, `server.ts`, `config.ts`
- `src/lib/api/__tests__/client.test.mjs`

### Phase 3 — Events / Search 페이지
- `src/app/events/page.tsx`, `[eventId]/page.tsx`
- `src/app/search/page.tsx`
- `src/components/EventCard.tsx`, `EventList.tsx`, `SearchBar.tsx`, `EmptyState.tsx`, `ErrorState.tsx`

### Phase 4 — themes / sectors / admin + proxy
- `src/app/themes/{page,[themeId]/page}.tsx`, `sectors/{page,[sectorId]/page}.tsx`
- `src/components/EventFilters.tsx`, `HealthStatus.tsx`, `AdminPanel.tsx`
- `src/app/admin/page.tsx`
- `src/app/api/admin/{reindex,reconcile,requeue/[id]}/route.ts`

### Phase 5 — Dockerfile + compose
- `frontend/Dockerfile`, `.dockerignore`
- `docker-compose.dev.yml`에 frontend service append (10번째)
- `.env.example`에 NEXT_PUBLIC_API_BASE_URL, CORS_ALLOW_ORIGINS 섹션
- `docker compose -f docker-compose.dev.yml config --quiet`

### Phase 6 — Backend CORS + 회귀
- `backend/app/core/config.py` CORS_ALLOW_ORIGINS 필드 + validator + redacted_env_status
- `backend/app/main.py` CORSMiddleware 추가
- `backend/tests/test_cors.py` 3 케이스
- `pytest backend/tests agents/tests workers/tests -q` 회귀 PASS

### Phase 7 — Build + smoke
- `cd frontend; npm install; npm run typecheck; npm run lint; npm run build; npm run test`
- `docker compose -f docker-compose.dev.yml build frontend`
- `docker compose -f docker-compose.dev.yml up -d frontend`
- frontend healthcheck healthy 대기
- curl 5종 smoke pass
- CORS preflight smoke pass
- 10개 컨테이너 healthy
- 기존 smoke 8종 회귀

### Phase 8 — 문서
- `frontend/README.md`
- `docs/FRONTEND_DESIGN.md` 신규
- `docs/ARCHITECTURE.md` 업데이트 (frontend 노드)
- `docs/TRD.md` STEP 010
- `docs/API_CONTRACT.md` CORS + `/api/internal/search-similar` 보정
- `docs/DEPLOYMENT.md` (확인 후 신규/업데이트)
- `docs/COMPATIBILITY_NOTES.md` STEP 010 TODO
- `plans/010_NEXTJS_FRONTEND_SKELETON_PLAN.md` (본 plan 영구 사본)
- `plans/010_NEXTJS_FRONTEND_SKELETON_REPORT.md`

### Phase 9 — Commit
- Commit A: `feat(frontend): Next.js 15 App Router skeleton with API client and Docker integration`
  - `frontend/**`, `docker-compose.dev.yml` frontend service, `.env.example`, `frontend/README.md`, `docs/FRONTEND_DESIGN.md`
- Commit B: `feat(backend): CORS middleware for frontend; STEP 010 docs/plan/report`
  - `backend/app/main.py`, `backend/app/core/config.py`, `backend/tests/test_cors.py`, `docs/{ARCHITECTURE,TRD,API_CONTRACT,DEPLOYMENT,COMPATIBILITY_NOTES}.md`, `plans/010_*.md`
- `git add` 파일 단위 명시. `node_modules`/`.next`/`build`/`.env` 미포함 확인
- `git push` 미실행

### Phase 10 — Codex sync
- `git -C C:/Users/computer/Desktop/business/codex status --short` clean 확인
- clean이면 `git -C C:/Users/computer/Desktop/business/codex fetch && merge --no-ff main`
- 충돌 시 자동 해결 금지, 보고

---

## 검증 체크리스트

- [ ] `npm run typecheck` 0 errors
- [ ] `npm run lint` 0 errors
- [ ] `npm run build` 성공, `.next/standalone/server.js` 생성
- [ ] `npm run test` node 테스트 PASS
- [ ] `docker compose -f docker-compose.dev.yml config --quiet` PASS
- [ ] `docker compose build frontend` 성공
- [ ] `docker compose up -d frontend` healthy
- [ ] 10개 컨테이너 healthy (frontend 포함)
- [ ] `curl http://localhost:3000/api/health` 200
- [ ] `curl -I http://localhost:3000/events` 200
- [ ] `curl -I "http://localhost:3000/search?q=test"` 200
- [ ] `curl -I http://localhost:3000/admin` 200
- [ ] CORS preflight echo localhost:3000 PASS
- [ ] backend pytest 전체 + CORS 3 케이스 PASS
- [ ] 기존 smoke 8종 회귀 PASS
- [ ] `git status`에 node_modules/.next/build/.env 없음
- [ ] `git diff --stat`에 ADMIN_API_TOKEN 실값 0
- [ ] 문서 7종 + plan/report 작성
- [ ] Commit A/B 분리, push 미실행
- [ ] codex sync 완료 (clean 시)
- [ ] WARNING/BLOCKED/UNKNOWN 명시

---

## 위험 / UNKNOWN

| # | 항목 | 영향 | 완화 |
|---|---|---|---|
| R1 | Next 15 + React 19 build 호환성 | 중간 | next 15.0.x + react 19.0.x stable 핀. 실패 시 next 14.2 LTS + React 18 fallback (App Router 동일) |
| R2 | Tailwind v4 alpha 오인 설치 | 낮음 | `tailwindcss: "3.4.x"` 명시 핀 |
| R3 | standalone output + env 주입 | 낮음 | runtime env는 `process.env` 직접. `NEXT_PUBLIC_*`만 build-time inline. compose에 빌드 ARG 전달 |
| R4 | Next 15 fetch caching default 변화 | 낮음 | 모든 server fetch에 `cache: "no-store"` 명시 |
| R5 | Docker build 시간 | 낮음 | multi-stage deps 분리, `npm ci` 캐시 |
| R6 | OpenSearch down 시 search 페이지 500 | 중간 | 503 잡아서 ErrorState. Phase 7에서 `docker stop opensearch` 후 `/search?q=x` 200 + ErrorState 검증 |
| R7 | Backend CORS validator string→list | 낮음 | Pydantic field_validator로 분기. test로 검증 |
| R8 | Admin token 누출 | 높음 | `import "server-only"` 컴파일 차단. AdminPanel은 `/api/admin/*` proxy만 호출. `git diff` grep ADMIN_API_TOKEN 0 확인 |
| R9 | Windows file watcher / Docker bind mount | 낮음 | Docker는 build된 `next start`만 사용. bind mount 안 함. dev mode는 host npm run dev |
| R10 | depends_on 역방향 | 중간 | `backend.depends_on`에 frontend 절대 추가 금지. 단방향 확인 |
| U1 | RBAC / 사용자 권한 모델 | — | STEP 011+ |
| U2 | shadcn/ui 도입 | — | STEP 011+ |
| U3 | Production NEXT_PUBLIC_API_BASE_URL | — | deploy 단계에서 빌드 시 주입 |
| U4 | Hybrid search UI | — | STEP 012+ |
| U5 | i18n | — | STEP 011+ |
| U6 | WebSocket / 실시간 push | — | STEP 012+ |

---

## 다음 STEP 제안

1. **STEP 010.5** (선택) — Playwright e2e (events list, search, admin reindex 전체 path)
2. **STEP 011** — 디자인 시스템 도입 (shadcn/ui 또는 자체), 로그인 + RBAC, admin 권한 분리
3. **STEP 012** — Hybrid search UI, 검색 랭킹 튜닝, WebSocket 실시간 갱신
4. **STEP 013** — DART/SEC collector + 한국어 nori analyzer

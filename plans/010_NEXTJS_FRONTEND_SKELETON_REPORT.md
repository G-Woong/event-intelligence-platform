# STEP 010 실행 보고 — Next.js Frontend Skeleton + Backend API Integration

실행일: 2026-05-24

---

## ① 무엇을 했는가

### Phase 1 — Frontend Scaffold

`frontend/` 디렉터리를 scratch에서 생성.

- `package.json`: Next.js 15.0.4, React 19.0.0, Tailwind 3.4.15, server-only 0.0.1
- `tsconfig.json` (strict: true, moduleResolution: bundler, App Router 설정)
- `next.config.mjs` (output: "standalone")
- `tailwind.config.ts`, `postcss.config.mjs`, `.eslintrc.json`, `.gitignore`, `.dockerignore`, `next-env.d.ts`
- `src/app/layout.tsx` (nav bar, RootLayout), `page.tsx`, `globals.css`, `loading.tsx`, `error.tsx`, `not-found.tsx`
- `public/favicon.svg` (placeholder)

### Phase 2 — API Client

- `src/lib/config.ts`: env 파싱 (API_BASE_URL, INTERNAL_API_BASE_URL)
- `src/lib/api/types.ts`: FinalEventCard, EventSearchHit, EventSearchResponse, Theme, Sector, HealthResponse, JobStatus
- `src/lib/api/client.ts`: 브라우저 fetch wrapper, ApiError, buildSearchUrl, api.*
- `src/lib/api/server.ts`: `import "server-only"` + adminFetch (ADMIN_API_TOKEN 서버측 격리)
- `src/lib/api/__tests__/client.test.mjs`: buildSearchUrl 2건, ApiError 1건 (node --test)

### Phase 3 — Events/Search 페이지 + 컴포넌트

- `src/app/api/health/route.ts`: GET → {status:"ok"}
- `src/app/events/page.tsx`, `[eventId]/page.tsx` (404 → notFound())
- `src/app/search/page.tsx` (503 → "검색 서비스 중단" ErrorState)
- 컴포넌트: EventCard, EventList, SearchBar (client), EmptyState, ErrorState

### Phase 4 — Themes/Sectors/Admin + Proxy

- `src/app/themes/page.tsx`, `[themeId]/page.tsx`
- `src/app/sectors/page.tsx`, `[sectorId]/page.tsx`
- `src/app/admin/page.tsx` (adminFetch health + AdminPanel client)
- `src/app/api/admin/reindex/route.ts` → POST `/api/admin/search/reindex`
- `src/app/api/admin/reconcile/route.ts` → POST `/api/admin/reconcile-stuck`
- `src/app/api/admin/requeue/[id]/route.ts` → POST `/api/admin/raw-events/{id}/requeue`
- 컴포넌트: EventFilters (client), HealthStatus, AdminPanel (client)

### Phase 5 — Dockerfile + Compose

- `frontend/Dockerfile`: 3-stage (deps/builder/runner), node:20-alpine, standalone output, healthcheck 127.0.0.1
- `docker-compose.dev.yml`: frontend service 추가 (10번째), depends_on backend, 127.0.0.1 healthcheck
- `.env.example`: NEXT_PUBLIC_API_BASE_URL, CORS_ALLOW_ORIGINS 섹션 추가

### Phase 6 — Backend CORS

- `backend/app/core/config.py`: `CORS_ALLOW_ORIGINS: list[str]` 필드 + `@field_validator` (str → list, comma-split) + `redacted_env_status` 업데이트
- `backend/app/main.py`: `CORSMiddleware` 추가 (allow_origins, allow_methods, allow_headers, max_age=600)
- `backend/tests/test_cors.py`: 3 케이스 (허용 origin, admin-token header, 차단 origin)

### Phase 8 — 문서

- `frontend/README.md` 신규
- `docs/FRONTEND_DESIGN.md` 신규
- `docs/ARCHITECTURE.md` 업데이트 (frontend 노드, 서비스 테이블, 다음 STEP)
- `docs/TRD.md` STEP 010 섹션 추가
- `docs/API_CONTRACT.md` CORS 정책 + proxy routes 추가
- `docs/DEPLOYMENT.md` 신규
- `docs/COMPATIBILITY_NOTES.md` STEP 010 TODO 추가

---

## ② 무엇을 검증했는가

| 검증 항목 | 결과 |
|---|---|
| `npm run typecheck` (tsc --noEmit) | **0 errors** |
| `npm run lint` (next lint) | **0 errors** |
| `npm run build` (.next/standalone/server.js) | **성공** |
| `npm run test` (node --test, 3건) | **3 PASS** |
| `backend/tests/test_cors.py` (3 케이스) | **3 PASS** |
| `pytest backend/tests agents/tests workers/tests -q` | **130 passed, 5 skipped** |
| `docker compose config --quiet` | **통과** |
| `docker compose build frontend` | **성공** |
| `docker compose up -d frontend` | **ei-frontend healthy** |
| `curl http://localhost:3000/api/health` | `{"status":"ok"}` |
| `curl -I http://localhost:3000/events` | 200 OK |
| `curl -I http://localhost:3000/search?q=test` | 200 OK |
| `curl -I http://localhost:3000/admin` | 200 OK |
| CORS preflight (localhost:3000) | `access-control-allow-origin: http://localhost:3000` |
| 전체 컨테이너 상태 | 10개 (healthy: 8, 실행중: 2 (worker/agent)) |

---

## ③ WARNING / BLOCKED / UNKNOWN

### WARNING

- **npm audit 2 vulnerabilities** (1 moderate, 1 critical): `npm audit` 결과 보고됨. skeleton 단계에서 직접 노출 없음. STEP 011에서 `npm audit fix` 검토 필요.
- **Alpine `localhost` 미해석**: node:20-alpine에서 healthcheck `wget http://localhost:3000` 실패. `127.0.0.1`로 변경 완료. `COMPATIBILITY_NOTES.md`에 기록.
- **backend rebuild 필요**: CORS 변경은 새 이미지가 필요하여 `docker compose build backend && up -d backend` 실행. 기존 컨테이너 교체됨.

### BLOCKED

없음.

### UNKNOWN

- **U1**: RBAC / 사용자 권한 모델 — STEP 011+
- **U2**: shadcn/ui 도입 — STEP 011+
- **U3**: Production NEXT_PUBLIC_API_BASE_URL — deploy 단계에서 빌드 ARG 주입 필요
- **U4**: Hybrid search UI — STEP 012+
- **U5**: i18n — STEP 011+
- **U6**: WebSocket / 실시간 push — STEP 012+

---

## 생성/수정 파일 목록

### 신규 (frontend/)
`frontend/` 전체 트리 (Dockerfile, .dockerignore, .gitignore, .eslintrc.json, package.json, tsconfig.json, next.config.mjs, next-env.d.ts, postcss.config.mjs, tailwind.config.ts, public/favicon.svg, README.md, src/** 35개)

### 신규 (기타)
- `backend/tests/test_cors.py`
- `docs/FRONTEND_DESIGN.md`
- `docs/DEPLOYMENT.md`
- `plans/010_NEXTJS_FRONTEND_SKELETON_REPORT.md` (본 파일)

### 수정
- `docker-compose.dev.yml` (frontend service 추가)
- `backend/app/main.py` (CORSMiddleware)
- `backend/app/core/config.py` (CORS_ALLOW_ORIGINS)
- `.env.example` (NEXT_PUBLIC_API_BASE_URL, CORS_ALLOW_ORIGINS)
- `docs/ARCHITECTURE.md`
- `docs/TRD.md`
- `docs/API_CONTRACT.md`
- `docs/COMPATIBILITY_NOTES.md`

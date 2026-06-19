# Frontend Design — STEP 010

## 기술 스택

- **Next.js 15.0.x** App Router, TypeScript strict
- **React 19.0.x**
- **Tailwind CSS 3.4.x** (v4 alpha 회피)
- **npm** (lock file 관리)
- **Output**: `standalone` (Docker 이미지 최적화)

## 디렉터리 구조

```
frontend/src/
├── app/
│   ├── layout.tsx               # RootLayout — nav bar
│   ├── page.tsx                 # / 홈
│   ├── globals.css
│   ├── loading.tsx / error.tsx / not-found.tsx
│   ├── api/
│   │   ├── health/route.ts      # GET → {status:"ok"} (Docker healthcheck)
│   │   └── admin/
│   │       ├── reindex/route.ts     # POST proxy → backend /api/admin/search/reindex
│   │       ├── reconcile/route.ts   # POST proxy → backend /api/admin/reconcile-stuck
│   │       └── requeue/[id]/route.ts # POST proxy → backend /api/admin/raw-events/{id}/requeue
│   ├── events/page.tsx / [eventId]/page.tsx
│   ├── search/page.tsx
│   ├── themes/page.tsx / [themeId]/page.tsx
│   ├── sectors/page.tsx / [sectorId]/page.tsx
│   └── admin/page.tsx
├── components/
│   ├── EventCard.tsx    EventList.tsx   (server)
│   ├── SearchBar.tsx    EventFilters.tsx  AdminPanel.tsx  (client)
│   ├── HealthStatus.tsx  EmptyState.tsx  ErrorState.tsx  (server)
└── lib/
    ├── config.ts               # env 파싱
    └── api/
        ├── types.ts            # Pydantic 미러 타입
        ├── client.ts           # 브라우저 fetch wrapper
        ├── server.ts           # server-only + adminFetch
        └── __tests__/client.test.mjs
```

## Server/Client 분리 정책

| 레이어 | 파일 | 특징 |
|---|---|---|
| **Server** | `lib/api/server.ts` | `import "server-only"` — 클라이언트 번들 진입 시 빌드 에러 |
| **Browser** | `lib/api/client.ts` | `NEXT_PUBLIC_API_BASE_URL` 사용, 브라우저에서 backend 직접 호출 |
| **Proxy** | `app/api/admin/*/route.ts` | Route Handler — 브라우저에서 `/api/admin/*`만 호출, 서버가 token 주입 |

## Route Handler Proxy 테스트 전략 (STEP 011)

Route Handler (TypeScript + Next.js path aliases + `server-only`)는 `node --test`로 직접 import 불가.
대신 핵심 proxy 로직(URL 경로, body 직렬화, token 헤더)을 **JS inline 재구현** 후 `globalThis.fetch` stub으로 검증.

테스트 파일: `src/app/api/admin/__tests__/proxy.test.mjs`

| 테스트 케이스 | 검증 항목 |
|---|---|
| reconcile 경로 | `/api/admin/raw-events/reconcile-stuck` (old path 아님) |
| requeue body + Content-Type | `force` 필드 직렬화, `Content-Type: application/json` 헤더 |
| requeue force 기본값 | body 없을 때 `force: false` |
| token 존재 시 | `X-Admin-Token` 헤더 포함 |
| token 빈값 시 | `X-Admin-Token` 헤더 미포함 |

실행: `npm run test` (client.test.mjs와 함께 실행).

### STEP 012+ 후보

- Playwright e2e (UI 실제 렌더링 + 인터랙션)
- shadcn/ui + Radix 도입 후 컴포넌트 스냅샷 테스트
- MSW(Mock Service Worker) 기반 API stub (브라우저 환경 테스트)

## Admin Token 격리

```
브라우저 → /api/admin/reindex (proxy) → [서버: ADMIN_API_TOKEN 주입] → backend:8000
```

- `ADMIN_API_TOKEN`은 절대 `NEXT_PUBLIC_*`으로 노출하지 않는다.
- `import "server-only"`가 컴파일 단계에서 token 누출을 차단.
- Admin mutation은 브라우저에서 `/api/admin/*` proxy만 호출.

## CORS 정책

Backend `CORSMiddleware`:
- `allow_origins`: `settings.CORS_ALLOW_ORIGINS` (env: `CORS_ALLOW_ORIGINS`, 기본 `http://localhost:3000`)
- `allow_methods`: GET, POST, PATCH, OPTIONS
- `allow_headers`: Content-Type, X-Admin-Token, Accept
- `allow_credentials`: False
- `max_age`: 600

## 페이지별 렌더링 전략

| 경로 | 타입 | 데이터 소스 | 실패 처리 |
|---|---|---|---|
| `/` | Server | `api.listEvents()` 상위 6건 | ErrorState |
| `/events` | Server | `api.listEvents()` 전체 | ErrorState / EmptyState |
| `/events/[id]` | Server | `api.getEvent(id)` | 404 → notFound() |
| `/search` | Server | `api.search(q)` 조건부 | 503 → "검색 서비스 중단" ErrorState |
| `/themes` `/themes/[id]` | Server | `api.listThemes()` / `api.themeEvents()` | EmptyState |
| `/sectors` `/sectors/[id]` | Server | `api.listSectors()` / `api.sectorEvents()` | EmptyState |
| `/admin` | Server + Client | `adminFetch("/health")` + proxy | ErrorState + dev 경고 배너 |

## 환경 변수

| 변수 | 위치 | 설명 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | 브라우저 (빌드타임) | backend public URL |
| `INTERNAL_API_BASE_URL` | 서버 (런타임) | Docker 내부 backend URL |
| `ADMIN_API_TOKEN` | 서버 전용 (절대 PUBLIC 금지) | admin 인증 토큰 |

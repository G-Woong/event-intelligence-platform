# Frontend와 Admin UI

> Next.js App Router 구조, 11개 라우트, admin proxy 보안, token 격리를 설명합니다.

---

## 기술 스택

| 항목 | 버전 / 내용 |
|---|---|
| Next.js | 15.5.18 (App Router) |
| React | 19 |
| TypeScript | 5.x |
| 스타일링 | Tailwind CSS |
| 빌드 모드 | standalone (Docker 최적화) |
| Node.js | 20 (Alpine) |
| 컨테이너 | `ei-frontend`, 포트 3000 |

---

## App Router 라우트 구조

```
frontend/src/app/
├── page.tsx                        → / (홈)
├── layout.tsx                      → 전체 레이아웃
├── loading.tsx                     → 로딩 UI
├── error.tsx                       → 에러 바운더리
├── not-found.tsx                   → 404 페이지
├── globals.css
│
├── events/
│   ├── page.tsx                    → /events (이벤트 목록)
│   └── [id]/page.tsx               → /events/[id] (이벤트 상세)
│
├── themes/
│   ├── page.tsx                    → /themes (테마 목록)
│   └── [id]/page.tsx               → /themes/[id] (테마 상세)
│
├── sectors/
│   ├── page.tsx                    → /sectors (섹터 목록)
│   └── [id]/page.tsx               → /sectors/[id] (섹터 상세)
│
├── search/
│   └── page.tsx                    → /search (검색)
│
├── admin/
│   └── page.tsx                    → /admin (관리 패널)
│
└── api/                            ← Route Handler (서버 함수)
    ├── health/route.ts             → GET /api/health
    └── admin/
        ├── reindex/route.ts        → POST /api/admin/reindex
        ├── reconcile/route.ts      → POST /api/admin/reconcile
        └── requeue/[id]/route.ts   → POST /api/admin/requeue/[id]
```

---

## 11개 페이지 라우트 상세

| URL | 페이지 | 기능 | 상태 |
|---|---|---|---|
| `/` | 홈 | 최근 이벤트 카드 목록 | DONE |
| `/events` | 이벤트 목록 | 전체 이벤트 + 필터 | DONE |
| `/events/[id]` | 이벤트 상세 | 개별 카드 전체 내용 | DONE |
| `/themes` | 테마 목록 | 테마별 그룹 | DONE |
| `/themes/[id]` | 테마 상세 | 특정 테마 이벤트 | DONE |
| `/sectors` | 섹터 목록 | 섹터별 그룹 | DONE |
| `/sectors/[id]` | 섹터 상세 | 특정 섹터 이벤트 | DONE |
| `/search` | 검색 | 키워드 검색 결과 | DONE |
| `/admin` | Admin | 관리 패널 | DONE |

---

## 4개 API Route Handler (proxy)

| URL | Method | 역할 | 상태 |
|---|---|---|---|
| `/api/health` | GET | backend health 체크 전달 | DONE |
| `/api/admin/reindex` | POST | backend `/api/admin/search/reindex` 호출 | DONE |
| `/api/admin/reconcile` | POST | backend `/api/admin/raw-events/reconcile-stuck` 호출 | DONE |
| `/api/admin/requeue/[id]` | POST | backend `/api/admin/raw-events/{id}/requeue` 호출 | DONE |

---

## API 클라이언트 계층 (`frontend/src/lib/api/`)

### `types.ts` — 공유 타입 정의
```typescript
export interface FinalEventCard {
  event_id: string;
  title: string;
  headline: string;
  // ...
}
```

### `client.ts` — 브라우저 클라이언트
- `NEXT_PUBLIC_API_BASE_URL` 환경변수 사용
- 브라우저에서 직접 backend GET API 호출 (조회 전용)
- 테스트: `frontend/src/lib/__tests__/client.test.mjs` (3건)

### `server.ts` — 서버 전용 클라이언트
```typescript
import "server-only";  // 브라우저 번들에 포함되면 빌드 에러
```
- `INTERNAL_API_BASE_URL` 환경변수 사용 (컨테이너 내부 주소)
- `X-Admin-Token` 헤더를 **서버에서만** 추가
- Admin 조작 API 호출에 사용
- 테스트: `frontend/src/lib/__tests__/proxy.test.mjs` (5건)

### `config.ts` — 환경설정
```typescript
export const config = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  internalApiBaseUrl: process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000",
};
```

---

## Admin Token 보안 격리 흐름

```
브라우저
    │  POST /api/admin/reindex (토큰 없음)
    ▼
Next.js Route Handler (server.ts)
    │  INTERNAL_API_BASE_URL + X-Admin-Token 추가
    ▼
Backend FastAPI /api/admin/search/reindex
```

핵심 보안 원칙:
- `ADMIN_API_TOKEN`은 서버 환경변수 — 브라우저 JS에 노출 불가
- `NEXT_PUBLIC_*` 접두사 없음 → 브라우저 번들에 포함 안 됨
- `import "server-only"` 선언으로 실수로 client 컴포넌트에서 import 시 빌드 에러

---

## 컴포넌트 목록 (`frontend/src/components/`)

| 컴포넌트 | 역할 | 상태 |
|---|---|---|
| `EventCard.tsx` | 개별 이벤트 카드 표시 | DONE |
| `EventList.tsx` | 이벤트 카드 목록 렌더링 | DONE |
| `EventFilters.tsx` | theme·sector·status 필터 UI | DONE |
| `SearchBar.tsx` | 검색 입력창 | DONE |
| `HealthStatus.tsx` | 서비스 상태 표시 (중첩 + flat fallback) | DONE |
| `AdminPanel.tsx` | Admin 작업 버튼 (reindex·reconcile) | DONE |
| `EmptyState.tsx` | 데이터 없을 때 UI | DONE |
| `ErrorState.tsx` | 에러 발생 시 UI | DONE |

---

## Dockerfile 특징 (`frontend/Dockerfile`)

```dockerfile
# Phase 1 — 빌드
FROM node:20-alpine AS builder
RUN npm ci && npm run build

# Phase 2 — 실행 (최소 이미지)
FROM node:20-alpine AS runner
RUN adduser -D nextuser          # 비루트 사용자
USER nextuser
COPY --from=builder /app/.next/standalone ./
```

주요 보안 조치:
- 비루트 사용자(`nextuser`)로 실행
- standalone 빌드로 불필요한 파일 제외
- `wget /api/health` HEALTHCHECK

---

## 프론트엔드 테스트

| 파일 | 테스트 수 | 내용 |
|---|---|---|
| `src/lib/__tests__/client.test.mjs` | 3건 | API client 기본 동작 |
| `src/lib/__tests__/proxy.test.mjs` | 5건 | Route Handler proxy 동작, token 주입 확인 |

실행: `node --test src/lib/__tests__/*.test.mjs`

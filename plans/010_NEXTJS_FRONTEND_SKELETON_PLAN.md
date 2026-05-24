# STEP 010 PLAN — Next.js Frontend Skeleton (사후 회복)

> 이 문서는 STEP 010 실행 후 REPORT 기반으로 역설계한 사후 PLAN이다.
> 원본 PLAN 파일이 누락되어 STEP 011에서 회복 작성.

실행일: 2026-05-24  
작성일(사후): 2026-05-24

---

## 목적

STEP 009까지 완성된 backend(FastAPI+PostgreSQL+OpenSearch+Milvus) 위에 Next.js 15 App Router 기반 frontend skeleton을 올려 13단계 관통 흐름을 완성한다.

## 범위

- Next.js 15.0.x App Router + TypeScript strict + Tailwind CSS 3.4.x
- events / search / themes / sectors / admin 5개 페이지
- Admin proxy Route Handler (reindex / reconcile / requeue)
- Backend CORS middleware 추가
- Docker frontend 서비스 + healthcheck

## 비범위

- 실 사용자 인증 (RBAC/OAuth) — STEP 015+
- shadcn/ui 도입 — STEP 014+
- WebSocket/SSE — STEP 012+
- Production TLS/CDN — STEP 016+

## 구현 파일 (실행 결과 기준)

### 신규
| 경로 | 목적 |
|---|---|
| `frontend/` | Next.js 프로젝트 루트 |
| `frontend/src/app/layout.tsx` | RootLayout + nav bar |
| `frontend/src/app/page.tsx` | 홈 |
| `frontend/src/app/events/page.tsx` | 이벤트 목록 |
| `frontend/src/app/events/[eventId]/page.tsx` | 이벤트 상세 |
| `frontend/src/app/search/page.tsx` | 검색 결과 |
| `frontend/src/app/themes/page.tsx` | 테마 목록 |
| `frontend/src/app/themes/[themeId]/page.tsx` | 테마별 이벤트 |
| `frontend/src/app/sectors/page.tsx` | 섹터 목록 |
| `frontend/src/app/sectors/[sectorId]/page.tsx` | 섹터별 이벤트 |
| `frontend/src/app/admin/page.tsx` | 어드민 패널 |
| `frontend/src/app/api/health/route.ts` | Docker healthcheck용 |
| `frontend/src/app/api/admin/reindex/route.ts` | 재색인 proxy |
| `frontend/src/app/api/admin/reconcile/route.ts` | 복구 proxy |
| `frontend/src/app/api/admin/requeue/[id]/route.ts` | 재큐 proxy |
| `frontend/src/lib/config.ts` | env 파싱 |
| `frontend/src/lib/api/types.ts` | Pydantic 미러 타입 |
| `frontend/src/lib/api/client.ts` | 브라우저 fetch wrapper |
| `frontend/src/lib/api/server.ts` | server-only adminFetch |
| `frontend/src/lib/api/__tests__/client.test.mjs` | node --test 3건 |
| `frontend/src/components/` | EventCard, EventList, SearchBar, AdminPanel, HealthStatus, EmptyState, ErrorState |
| `frontend/Dockerfile` | standalone output 이미지 |

### 수정
| 경로 | 변경 |
|---|---|
| `backend/app/main.py` | CORSMiddleware 추가 |
| `backend/app/core/config.py` | CORS_ALLOW_ORIGINS 설정 |
| `docker-compose.dev.yml` | frontend 서비스 추가 |
| `.env.example` | NEXT_PUBLIC_API_BASE_URL, CORS_ALLOW_ORIGINS 추가 |

## 알려진 이슈 (STEP 011에서 수정)

| # | 이슈 | 수정 방법 |
|---|---|---|
| H1 | reconcile proxy 경로 오류 (`/api/admin/reconcile-stuck`) | → `/api/admin/raw-events/reconcile-stuck` |
| H2 | themes/sectors `name` 필드 누락 | backend 응답 name/description/event_count 추가 |
| H3 | EventSearchHit `id` alias 누락 | backend `id` = `card_id` alias 추가 |
| H4 | HealthStatus components 중첩 미지원 | backend components 중첩 + frontend flat fallback |
| H5 | Next.js 15.0.4 CVE-2025-29927 | → 15.5.18 업그레이드 |

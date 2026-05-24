# Event Intelligence — Frontend

Next.js 15 App Router + React 19 + TypeScript + Tailwind CSS skeleton.

## 개발 실행

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

## 검증

```bash
npm run typecheck  # tsc --noEmit
npm run lint       # next lint
npm run build      # .next/standalone/server.js 생성
npm run test       # node --test
```

## Docker

```bash
# 전체 스택 (backend 먼저)
docker compose -f docker-compose.dev.yml build frontend
docker compose -f docker-compose.dev.yml up -d frontend
```

## 환경 변수

| 변수 | 기본값 | 용도 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | 브라우저가 호출하는 backend URL (빌드타임 inline) |
| `INTERNAL_API_BASE_URL` | `http://localhost:8000` | SSR/Route Handler가 사용하는 내부 URL |
| `ADMIN_API_TOKEN` | `` | Admin proxy 토큰 (서버측 전용, 브라우저 노출 금지) |

## 페이지 목록

| 경로 | 설명 |
|---|---|
| `/` | 홈 — 최근 이벤트 미리보기 |
| `/events` | 전체 이벤트 목록 |
| `/events/[id]` | 이벤트 상세 |
| `/search?q=...` | OpenSearch 키워드 검색 |
| `/themes` | 테마 인덱스 |
| `/themes/[id]` | 테마별 이벤트 |
| `/sectors` | 섹터 인덱스 |
| `/sectors/[id]` | 섹터별 이벤트 |
| `/admin` | 시스템 상태 + reindex/reconcile 트리거 |
| `/api/health` | Docker healthcheck용 |
| `/api/admin/*` | Admin mutation proxy (ADMIN_API_TOKEN 격리) |

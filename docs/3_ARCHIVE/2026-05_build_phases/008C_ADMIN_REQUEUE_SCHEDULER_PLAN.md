# STEP 008C — Admin Auth + Re-enqueue + Scheduler Skeleton (PLAN)

날짜: 2026-05-24

## 목표

OpenSearch/Frontend 진입 전 backend 운영 골격의 최소 안전장치:
1. admin/internal endpoint에 최소 token 인증 부여
2. failed/stuck raw_event를 다시 Redis Stream에 안전하게 넣는 단일 requeue endpoint
3. reconciler를 1회 실행하는 script skeleton (cron/CI hook용)
4. `GET /api/admin/raw-events`에 source_type/offset/order 추가

## 사용자 결정 (확정)

| 항목 | 결정 |
|---|---|
| Dev-mode 정책 | ADMIN_API_TOKEN 비설정 → startup WARNING + 모든 admin 허용 |
| Requeue 대상 | failed/enqueued 기본 허용. processed는 force=true로만 |
| Scheduler 형태 | scripts/reconcile_stuck_once.py 1회 실행 |
| processing 상태 | 보류 (STEP 008D) |
| event_card_id FK | 보류 (STEP 008D) |
| admin token 방식 | X-Admin-Token 헤더, router-level dependency |
| auth 적용 범위 | /api/admin/* 전체 + /api/internal/search-similar |

## 신규 파일

- `backend/app/core/security.py` — require_admin_token dependency
- `scripts/__init__.py` — scripts 패키지 마커
- `scripts/reconcile_stuck_once.py` — scheduler skeleton
- `backend/tests/test_admin_auth.py` — 6 케이스
- `backend/tests/test_requeue_service.py` — 5 케이스
- `backend/tests/test_requeue_api.py` — 4 케이스
- `backend/tests/test_reconcile_script.py` — 3 케이스
- `tests/smoke/test_requeue.py` — 1 케이스

## 수정 파일

- `backend/app/core/config.py` — ADMIN_API_TOKEN 추가
- `backend/app/main.py` — router-level dependency + startup WARN
- `backend/app/api/admin.py` — requeue endpoint, list 확장
- `backend/app/schemas/raw_events.py` — RequeueRequest/Response
- `backend/app/services/raw_event_service.py` — requeue_raw_event(), list 확장
- `agents/agent_worker.py` — X-Admin-Token 헤더
- `workers/collectors/rss_collector.py` — X-Admin-Token 헤더
- `workers/pipelines/publish_pipeline.py` — X-Admin-Token 헤더
- 기존 테스트 4개 모듈 — dependency_overrides 추가
- `.env.example` — ADMIN_API_TOKEN, RECONCILER_* 추가
- 문서 5개 갱신

## 비범위

- OpenSearch / Next.js UI
- production-grade auth (RBAC/OAuth/JWT)
- processing 상태 도입
- event_card_id FK 제약
- bulk requeue / scheduler container

## 위험 (R1-R7, U1-U5)

R1: dev-mode allow → prod 무방비 위험 → startup WARN + docs prod checklist
R4: requeue 중복 event_card → force 가드 + requeue_count 추적
U1: processing 상태 — STEP 008D
U5: event_card_id FK — STEP 008D

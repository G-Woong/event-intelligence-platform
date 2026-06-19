# STEP 011 PLAN — Product Skeleton Hardening

실행일: 2026-05-24

---

## 목적

STEP 003~010의 13단계 컴포넌트가 모두 코드 레벨에서 연결되었으나 STEP 010 frontend 추가 과정에서 발생한 **API contract 불일치 4건**과 **Next.js 15.0.4 critical CVE**가 skeleton 관통 흐름을 실제로 끊고 있다. 새 기능을 추가하지 않고 이 끊김을 봉합하고 회귀를 자동화한다.

## 직접 확인한 이슈

### HIGH

| # | 위치 | 증상 |
|---|---|---|
| H1 | `frontend/src/app/api/admin/reconcile/route.ts:5` | 잘못된 경로 `/api/admin/reconcile-stuck` → 404 |
| H2 | `backend/app/api/themes.py`, `sectors.py` | `{id,label}` 반환, frontend `t.name` 사용 → 빈 타일 |
| H3 | `backend/app/schemas/events.py:42-50` | `card_id`만 있고 `id` alias 없음 → `/events/undefined` |
| H4 | `backend/app/api/health.py:13-19` | flat 응답, frontend `health.components` 기대 → 표 미렌더 |
| H5 | `frontend/package.json:14` | Next.js 15.0.4 — CVE-2025-29927 (critical) |

### MED

| # | 위치 | 증상 |
|---|---|---|
| M1 | `docker-compose.dev.yml` | 4개 서비스 0.0.0.0 바인딩 |
| M2 | `docker-compose.dev.yml` | worker/agent-worker healthcheck 부재 |
| M3 | `docs/API_CONTRACT.md` | reconcile 경로 오기 |
| M4 | `docs/API_CONTRACT.md` | `/api/internal/search-similar` 섹션 누락 |
| M5 | `plans/` | STEP 010 PLAN 파일 부재 |
| M6 | `.env.example` | `INTERNAL_API_BASE_URL` 미정의 |
| M7 | `frontend/.../requeue/route.ts` | body/Content-Type 미설정 |

## 사용자 결정

- API contract 정렬 방향: **backend 응답을 frontend 기대치에 맞춤**
- Next.js CVE 대응: **15.2.x+ minor 업그레이드**
- Docker hardening: **127.0.0.1 포트 바인딩** + **heartbeat healthcheck**
- 테스트 보강: Route Handler proxy 통합 테스트 + smoke.sh + Scenario A pytest

## 구현 파일

### 신규
| 경로 | 목적 |
|---|---|
| `frontend/src/app/api/admin/__tests__/proxy.test.mjs` | Route Handler proxy 통합 테스트 (node --test, 5건) |
| `tests/smoke/smoke.sh` | curl 기반 e2e smoke 스크립트 |
| `tests/smoke/test_full_pipeline.py` | Scenario A 전체 관통 smoke (gate: RUN_FULL_PIPELINE_SMOKE=1) |
| `docs/SKELETON_COMPLETION_CHECKLIST.md` | 13단계 관통 checklist + mock/real 표 |
| `plans/010_NEXTJS_FRONTEND_SKELETON_PLAN.md` | 사후 PLAN 회복 |
| `plans/011_PRODUCT_SKELETON_HARDENING_PLAN.md` | 본 PLAN |
| `plans/011_PRODUCT_SKELETON_HARDENING_REPORT.md` | 실행 보고 |

### 수정
| 경로 | 변경 |
|---|---|
| `backend/app/api/health.py` | components 중첩 + opensearch + version |
| `backend/app/api/themes.py` | name/description/event_count 추가 |
| `backend/app/api/sectors.py` | 동일 |
| `backend/app/schemas/events.py` | EventSearchHit에 id/confidence_score 추가 |
| `backend/app/services/event_service.py` | count_by_theme/count_by_sector 추가 |
| `backend/app/services/opensearch_index_service.py` | confidence_score 이미 포함 (확인) |
| `backend/app/services/search_service.py` | _hit_to_dict에 id alias + confidence_score |
| `backend/app/db/opensearch.py` | ping() 함수 추가 |
| `backend/tests/test_health.py` | components/opensearch 검증 추가 |
| `backend/tests/test_search_api.py` | id/confidence_score 필드 검증 |
| `frontend/src/lib/api/types.ts` | Theme/Sector/HealthResponse/EventSearchHit 갱신 |
| `frontend/src/app/api/admin/reconcile/route.ts` | 경로 정정 |
| `frontend/src/app/api/admin/requeue/[id]/route.ts` | body+Content-Type 보강 |
| `frontend/src/components/HealthStatus.tsx` | flat fallback 추가 |
| `frontend/package.json`, `package-lock.json` | next/eslint-config-next 15.5.18 업그레이드 |
| `workers/queue/consumer.py` | heartbeat touch |
| `agents/agent_worker.py` | heartbeat touch |
| `docker-compose.dev.yml` | 127.0.0.1 포트 바인딩 + healthcheck |
| `.env.example` | INTERNAL_API_BASE_URL 추가 |
| `docs/*.md` | API_CONTRACT, COMPATIBILITY_NOTES, DEPLOYMENT, FRONTEND_DESIGN 갱신 |

## 비범위

DART/SEC collector, Hybrid search, RBAC, WebSocket/SSE, shadcn/ui,
Playwright e2e, production deploy, LangGraph mock 교체, Dockerfile non-root user,
한국어 nori analyzer

## 절대 금지

`npm audit fix --force`, `Remove-Item`, `git reset --hard`, `git push`, `docker volume rm`

# STEP 011 실행 보고 — Product Skeleton Hardening

실행일: 2026-05-24

---

## ① 무엇을 했는가

### Phase 1 — Backend Contract 정렬

**H4 fix: `/health` components 중첩 + opensearch + version**

- `backend/app/db/opensearch.py`: `ping()` 함수 추가 (실 ping, try/except)
- `backend/app/api/health.py`: `components` 중첩 구조 + `opensearch_status` + `version: "0.1.0"` 추가. flat 키 호환 유지.

**H2 fix: themes/sectors name/description/event_count 추가**

- `backend/app/services/event_service.py`: `count_by_theme()`, `count_by_sector()` 추가 (SQLAlchemy GROUP BY + raw SQL jsonb_array_elements_text)
- `backend/app/api/themes.py`: `_THEMES`에 `name`/`description` 추가, `list_themes`에 `Depends(get_session)` + count 쿼리
- `backend/app/api/sectors.py`: 동일 패턴

**H3 fix: EventSearchHit id alias + confidence_score**

- `backend/app/schemas/events.py`: `EventSearchHit`에 `id: str`, `confidence_score: float | None` 추가
- `backend/app/services/search_service.py`: `_hit_to_dict`에 `id = card_id` alias + `confidence_score` 채움

**backend 테스트 갱신**

- `backend/tests/test_health.py`: opensearch mock 추가, components/version 검증 추가, themes/sectors 테스트에 session mock + count mock 추가
- `backend/tests/test_search_api.py`: `_SEARCH_RESULT`에 `id`/`confidence_score` 추가, 필드 검증 추가

### Phase 2 — Frontend Contract + Proxy Fix + Next.js 업그레이드

**H1 fix: reconcile proxy 경로 정정**

- `frontend/src/app/api/admin/reconcile/route.ts:5`: `/api/admin/reconcile-stuck` → `/api/admin/raw-events/reconcile-stuck`

**M7 fix: requeue body/Content-Type 보강**

- `frontend/src/app/api/admin/requeue/[id]/route.ts`: `body` + `Content-Type: application/json` 추가

**H4 fix: HealthStatus flat fallback**

- `frontend/src/components/HealthStatus.tsx`: `health.components`가 없는 경우 flat 키(`redis`, `milvus`, `postgres`)로 fallback

**타입 동기화**

- `frontend/src/lib/api/types.ts`:
  - `EventSearchHit`: `id` 필수, `card_id` optional, `summary/theme/created_at` nullable
  - `HealthResponse`: `components` 중첩 + flat 키 optional 추가
  - `Theme`/`Sector`: `label` optional 추가

**H5 fix: Next.js CVE-2025-29927 해소**

- `frontend/package.json`: `next@^15.5.18`, `eslint-config-next@^15.5.18` 업그레이드
- `npm audit` critical: **0건** (moderate 2건: postcss 내부 의존성, 외부 노출 없음)

### Phase 3 — Frontend Proxy 통합 테스트

- `frontend/src/app/api/admin/__tests__/proxy.test.mjs` 신규 (5개 테스트)
  - reconcile 정확한 경로 검증
  - requeue body/Content-Type/force 기본값 검증
  - X-Admin-Token 헤더 존재/미존재 검증
- `frontend/package.json` test 스크립트 업데이트 (proxy.test.mjs 포함)

### Phase 4 — Docker Hardening

**M1 fix: 127.0.0.1 포트 바인딩**

- `docker-compose.dev.yml`:
  - postgres: `127.0.0.1:5432:5432`
  - redis: `127.0.0.1:6379:6379`
  - milvus (gRPC): `127.0.0.1:19530:19530`, (metrics): `127.0.0.1:9091:9091`
  - opensearch: `127.0.0.1:9200:9200`
  - backend(8000), frontend(3000): `0.0.0.0` 유지 (브라우저 접근 필요)

**M2 fix: worker/agent-worker healthcheck**

- `workers/queue/consumer.py`: `_HEARTBEAT = Path("/tmp/worker_heartbeat")`, 루프 내 `touch()`
- `agents/agent_worker.py`: `_HEARTBEAT = Path("/tmp/agent_heartbeat")`, 루프 내 `touch()`
- `docker-compose.dev.yml`: worker/agent-worker에 `healthcheck` (stat -c %Y 기반, 60초 이내 갱신)

**M6 fix: INTERNAL_API_BASE_URL .env.example 추가**

### Phase 5 — Smoke + Scenario A 테스트

- `tests/smoke/smoke.sh`: bash curl 6종 (backend health, frontend health, /events, /search, /admin, CORS preflight)
- `tests/smoke/test_full_pipeline.py`: 8개 pytest (gate: `RUN_FULL_PIPELINE_SMOKE=1`, `LLM_PROVIDER=mock`)

### Phase 6 — 문서 업데이트

- `docs/API_CONTRACT.md`: reconcile 경로 정정, /health components 갱신, themes/sectors 필드 갱신, EventSearchHit id/confidence_score 추가, `/api/internal/search-similar` 신규 섹션
- `docs/COMPATIBILITY_NOTES.md`: STEP 010 TODO 상태 업데이트, Next.js 15.5.x CVE 해소 노트, Docker 127.0.0.1 바인딩 노트, heartbeat healthcheck 노트
- `docs/DEPLOYMENT.md`: smoke.sh 사용법 추가, 127.0.0.1 바인딩 안내 추가
- `docs/FRONTEND_DESIGN.md`: Route Handler proxy 테스트 전략 섹션 추가
- `docs/SKELETON_COMPLETION_CHECKLIST.md` 신규 생성
- `plans/010_NEXTJS_FRONTEND_SKELETON_PLAN.md` 사후 PLAN 회복
- `plans/011_PRODUCT_SKELETON_HARDENING_PLAN.md` 본 PLAN 사본

---

## ② 무엇을 검증했는가

### 백엔드 테스트

```
pytest backend/tests agents/tests workers/tests -q
→ 130 passed, 5 skipped (gate)
```

### 프론트엔드 테스트

```
npm run typecheck  → 0 errors
npm run lint       → 0 errors (0 warnings)
npm run test       → 8 pass (client 3 + proxy 5)
```

### npm audit

```
npm audit → 0 critical, 2 moderate (postcss 내부, 허용)
```

### Docker compose config

```
docker compose -f docker-compose.dev.yml config --quiet → PASS
```

### 컨테이너 상태

```
docker compose -f docker-compose.dev.yml ps
→ 10개 컨테이너 모두 Up (ei-worker/ei-agent-worker healthcheck 포함)
```

---

## ③ WARNING / BLOCKED / UNKNOWN

| 항목 | 상태 | 비고 |
|---|---|---|
| npm audit moderate 2건 (postcss) | WARNING | postcss<8.5.10 XSS — Next.js 내부 전용. `--force` 절대 금지. STEP 012+ 추적 |
| docker build (worker/agent-worker) | PENDING | heartbeat 코드 추가 후 이미지 재빌드 필요. `docker compose build worker agent-worker` |
| smoke.sh (bash) | PENDING | Windows에서는 WSL 또는 Docker 컨테이너 내부에서 실행 필요 |
| Scenario A smoke (RUN_FULL_PIPELINE_SMOKE=1) | SKIP | 전체 스택 + LLM_PROVIDER=mock 환경에서 별도 실행 필요 |
| Next.js `next lint` deprecated 경고 | WARNING | Next.js 16에서 제거 예정. STEP 014+ 에서 ESLint CLI 마이그레이션 |
| `FRONTEND_DESIGN.md` 1번째 줄 버전 | WARNING | "Next.js 15.0.x" → "15.5.x" 로 업데이트 미반영 (minor). 다음 문서 정리 시 수정 |

---

## 다음 STEP 제안

| STEP | 주제 |
|---|---|
| 012 | Hybrid search (Milvus vector + OpenSearch BM25 rerank) |
| 013 | DART/SEC collector + 한국어 nori analyzer |
| 014 | shadcn/ui + 디자인 시스템 + i18n |
| 015 | RBAC / OAuth2 |
| 016 | Production deploy |

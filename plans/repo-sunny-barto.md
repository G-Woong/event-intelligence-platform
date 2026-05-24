# STEP 011 — Product Skeleton Hardening (고도화 직전 관통 안정화)

## Context

STEP 003 ~ STEP 010까지 RSS 수집 → raw_events → Stream → LangGraph → event_cards → Milvus/OpenSearch → FastAPI → Next.js frontend → admin/reconcile/requeue/reindex의 13단계 컴포넌트가 모두 코드 레벨에서 연결되었고 10개 컨테이너가 동시에 healthy 상태다. 그러나 STEP 010 frontend 추가 과정에서 도입된 **API contract 불일치 4건**과 **Next.js 15.0.4의 critical CVE**가 skeleton 관통 흐름을 실제로 끊고 있다. 이번 STEP은 새 대형 기능을 추가하지 않고, 고도화 (DART/SEC, hybrid search, RBAC) 단계로 넘어가기 전에 이 끊김을 봉합하고 회귀를 자동화한다.

---

## 직접 확인한 현재 상태 (탐색 결과)

### HIGH 위험 — skeleton이 실제로 깨져있음

| # | 위치 | 증상 |
|---|---|---|
| H1 | `frontend/src/app/api/admin/reconcile/route.ts:5` | `/api/admin/reconcile-stuck` 호출하나 실제 backend는 `/api/admin/raw-events/reconcile-stuck` (admin.py:58) → **404** |
| H2 | `backend/app/api/themes.py:12-18`, `sectors.py:12-18` vs `frontend/src/app/themes/page.tsx:34`, `sectors/page.tsx:34` | backend 반환 `{id,label}`, frontend 사용 `t.name`/`t.description`/`t.event_count` → **모든 테마/섹터 타일이 빈 제목** |
| H3 | `backend/app/schemas/events.py:42-50` vs `frontend/src/lib/api/types.ts:15-24` | backend `card_id` + `score`, frontend `id` + `confidence_score` → `/events/undefined` 링크, `Math.round(undefined*100)` NaN badge |
| H4 | `backend/app/api/health.py:13-19` vs `frontend/src/components/HealthStatus.tsx:24-32` | backend flat `{status,redis,milvus,postgres}`, frontend `health.components` 중첩 가정 → **admin 페이지 컴포넌트 표 미렌더** |
| H5 | `frontend/package.json:14` | Next.js 15.0.4 — **CVE-2025-29927** (middleware auth bypass, critical). STEP 010 보고서 "1 critical" 정체. 15.2.3+ 필요 |

### MED 위험

| # | 위치 | 증상 |
|---|---|---|
| M1 | `docker-compose.dev.yml` | postgres:5432 / redis:6379 / milvus:19530 / opensearch:9200 모두 `0.0.0.0` 바인딩 — dev 호스트 외부 접근 가능 |
| M2 | `docker-compose.dev.yml` worker/agent-worker | healthcheck 부재 — `docker compose ps`에 status가 빈 상태로 표시, 장애 자동 감지 불가 |
| M3 | `docs/API_CONTRACT.md:26` | Proxy 표가 잘못된 `/api/admin/reconcile-stuck` 경로를 명시 (frontend proxy와 함께 틀린 상태) |
| M4 | `docs/API_CONTRACT.md` 전체 | `/api/internal/search-similar` 섹션 누락 (STEP 010 plan에서 보정 약속했으나 미반영) |
| M5 | `plans/` | STEP 010 PLAN 파일 부재 (REPORT만 존재) — 003~009는 모두 PLAN+REPORT 페어 |
| M6 | `.env.example` | `INTERNAL_API_BASE_URL` 미정의 (docker-compose.dev.yml:219, frontend/src/lib/config.ts:5에서 사용) |
| M7 | `frontend/src/app/api/admin/requeue/[id]/route.ts:8` | body 전송 없음 + `Content-Type` 미설정 |

### 정상 (이번 STEP에서 건드릴 필요 없음)

- Admin token 격리: `frontend/src/lib/api/server.ts:1`의 `import "server-only"`로 컴파일 차단. `NEXT_PUBLIC_ADMIN_*` 0건. SAFE.
- backend pytest 92건, agents 22건, workers 19건, smoke 11건, frontend 3건 = 총 147건 PASS 상태로 추정.
- LangGraph 6/11 mock 노드, MockLLMClient/MockEmbeddingClient default — 의도된 skeleton stub. STEP 012+ 도메인 모델 도입 시 교체.
- Milvus/OpenSearch 실 호출 wire-up 완료, `try_index_card` swallow 정책 일관.

---

## 사용자 결정 (확정)

| 항목 | 결정 |
|---|---|
| API contract 정렬 방향 | **Backend 응답을 frontend 기대치에 맞춤** — `/health`에 components 중첩 추가, themes/sectors에 name/description/event_count 추가, search hit에 id alias 추가 |
| Next.js CVE 대응 | **Next.js 15.2.x+ minor 업그레이드** — lockfile 재생성, build/typecheck/lint/test 재검증 |
| Docker hardening | **127.0.0.1 포트 바인딩** (postgres/redis/milvus/opensearch) + **worker/agent-worker healthcheck** (heartbeat 파일 기반). non-root user는 보류 |
| Test 보강 | **3가지 모두 추가**: Route Handler proxy 통합 테스트 (node --test) + `tests/smoke/smoke.sh` curl 스크립트 + Scenario A 전체 관통 smoke (pytest) |

---

## 핵심 설계

### 1. Contract 정렬 — Backend 응답 변경 (frontend 기대치에 맞춤)

#### 1.1 `/health` — components 중첩 추가
`backend/app/api/health.py`:
```python
return {
    "status": "ok",
    "version": settings.APP_VERSION if hasattr(settings, "APP_VERSION") else "0.1.0",
    "components": {
        "redis": redis_status,
        "milvus": milvus_status,
        "postgres": postgres_status,
        "opensearch": opensearch_status,  # 신규
    },
    # 기존 flat 키도 호환성 유지
    "redis": redis_status,
    "milvus": milvus_status,
    "postgres": postgres_status,
}
```
opensearch ping은 `backend/app/db/opensearch.py`의 `is_connected()` 재사용.

#### 1.2 themes/sectors — name/description/event_count 추가
`backend/app/api/themes.py`:
```python
_THEMES = [
    {"id": "geopolitics", "name": "Geopolitics", "label": "Geopolitics",
     "description": "국가/외교/안보 관련 이벤트"},
    ...
]

@router.get("/themes")
async def list_themes(db: AsyncSession = Depends(get_db)):
    counts = await event_service.count_by_theme(db)  # 신규 service
    return [{**t, "event_count": counts.get(t["id"], 0)} for t in _THEMES]
```
sectors도 동일 패턴. `count_by_theme`/`count_by_sector`는 `backend/app/services/event_service.py`에 신규 (PG `GROUP BY theme COUNT(*)`).

#### 1.3 EventSearchHit — id alias 추가
`backend/app/schemas/events.py`:
```python
class EventSearchHit(BaseModel):
    card_id: str
    id: str  # = card_id, frontend 호환
    title: str
    summary: str | None
    theme: str | None
    sectors: list[str] = []
    status: str | None
    score: float
    confidence_score: float | None = None  # event_cards 조회 시 채움
    created_at: datetime | None
```
`backend/app/services/search_service.py`의 hit 빌드에서 `id=hit["_source"]["card_id"]`, `confidence_score`는 OpenSearch doc에 포함하도록 `opensearch_index_service._card_to_doc`에 필드 추가.

#### 1.4 frontend types 동기화
`frontend/src/lib/api/types.ts`:
```ts
export interface HealthResponse {
  status: string;
  version?: string;
  components?: { redis?: string; milvus?: string; postgres?: string; opensearch?: string };
  redis?: string; milvus?: string; postgres?: string;  // legacy flat 호환
}
export interface Theme { id: string; name: string; label?: string; description?: string; event_count?: number; }
export interface Sector { id: string; name: string; label?: string; description?: string; event_count?: number; }
export interface EventSearchHit {
  id: string; card_id?: string; title: string; summary: string | null;
  theme: string | null; sectors: string[]; status?: string | null;
  confidence_score: number | null; score: number; created_at: string | null;
}
```

### 2. Reconcile proxy 경로 정정

`frontend/src/app/api/admin/reconcile/route.ts:5`:
```ts
- await adminFetch("/api/admin/reconcile-stuck", {
+ await adminFetch("/api/admin/raw-events/reconcile-stuck", {
```

`docs/API_CONTRACT.md:26` Proxy 표도 동일 경로로 수정.

### 3. Requeue proxy body/header 보강

`frontend/src/app/api/admin/requeue/[id]/route.ts`:
```ts
const body = await req.json().catch(() => ({ force: false }));
const out = await adminFetch(`/api/admin/raw-events/${id}/requeue`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ force: !!body.force }),
});
```

### 4. Next.js 15.2.x+ 업그레이드

```bash
cd frontend
npm install next@^15.2.3 eslint-config-next@^15.2.3
npm audit
npm run typecheck && npm run lint && npm run build && npm run test
```
package-lock.json 재생성. CVE-2025-29927 해소 확인.

### 5. Docker compose 127.0.0.1 바인딩

`docker-compose.dev.yml`의 postgres/redis/milvus/opensearch ports:
```yaml
ports:
  - "127.0.0.1:5432:5432"  # postgres
  - "127.0.0.1:6379:6379"  # redis
  - "127.0.0.1:19530:19530" # milvus
  - "127.0.0.1:9200:9200"  # opensearch
```
backend(8000), frontend(3000)은 사용자 브라우저 접근이 필요하므로 `0.0.0.0` 유지.

### 6. worker/agent-worker healthcheck (heartbeat 파일)

`workers/queue/consumer.py`의 메인 루프 안에:
```python
from pathlib import Path
HEARTBEAT = Path("/tmp/worker_heartbeat")
# 메시지 처리 후 또는 idle 타이머마다
HEARTBEAT.touch()
```

`agents/agent_worker.py` 동일 패턴 (`/tmp/agent_heartbeat`).

`docker-compose.dev.yml`:
```yaml
worker:
  healthcheck:
    test: ["CMD-SHELL", "test $(($(date +%s) - $(stat -c %Y /tmp/worker_heartbeat 2>/dev/null || echo 0))) -lt 60"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 30s
agent-worker:
  healthcheck:
    test: ["CMD-SHELL", "test $(($(date +%s) - $(stat -c %Y /tmp/agent_heartbeat 2>/dev/null || echo 0))) -lt 60"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 30s
```

### 7. 테스트 보강

#### 7.1 Frontend Route Handler proxy 통합 테스트
`frontend/src/app/api/admin/__tests__/proxy.test.mjs` (신규, node --test):
- `global.fetch`를 stub하여 reindex/reconcile/requeue route handler가 올바른 backend path + headers + body로 호출하는지 검증
- ADMIN_API_TOKEN env 설정 시 `X-Admin-Token` 헤더 포함, 빈값 시 미포함 확인

#### 7.2 `tests/smoke/smoke.sh` (신규)
```bash
#!/usr/bin/env bash
set -euo pipefail
echo "== Backend health"; curl -sf http://localhost:8000/health | head -c 200; echo
echo "== Frontend health"; curl -sf http://localhost:3000/api/health
echo "== Frontend /events"; curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:3000/events
echo "== Frontend /search?q=test"; curl -sf -o /dev/null -w "%{http_code}\n" "http://localhost:3000/search?q=test"
echo "== Frontend /admin"; curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:3000/admin
echo "== CORS preflight"
curl -si -X OPTIONS http://localhost:8000/api/events \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" | grep -i "access-control-allow-origin"
echo "OK"
```
docs/DEPLOYMENT.md에서 참조하도록 업데이트.

#### 7.3 Scenario A 전체 관통 smoke
`tests/smoke/test_full_pipeline.py` (신규):
- fixture RSS → raw_events insert
- 60s 폴링으로 processed 전환 확인
- GET /api/events에서 event_cards 발견
- frontend `/events`에 카드가 보이는지 (HTML 응답에 card title 포함 검증)
- frontend `/search?q=<title-token>`이 hit 표시
gate: full stack 실행 시 기본 활성, 외부 LLM 호출 회피 (LLM_PROVIDER=mock).

### 8. 문서 업데이트

- `docs/API_CONTRACT.md` — `/health` response 갱신, `/api/admin/raw-events/reconcile-stuck` 경로 정정, `/api/internal/search-similar` 섹션 신규 추가, EventSearchHit 필드 갱신
- `docs/ARCHITECTURE.md` — Mock/Real 컴포넌트 표 (STEP 011 시점) 갱신
- `docs/TRD.md` — STEP 011 섹션 추가 (contract fix + Next 15.2 + docker hardening + heartbeat healthcheck)
- `docs/FRONTEND_DESIGN.md` — Route Handler proxy 테스트 전략 섹션 추가
- `docs/DEPLOYMENT.md` — `tests/smoke/smoke.sh` 사용법, 127.0.0.1 포트 바인딩 안내
- `docs/COMPATIBILITY_NOTES.md` — STEP 010 TODO 정리 (해결된 항목 표시) + Next.js 15.2 업그레이드 노트
- `docs/SKELETON_COMPLETION_CHECKLIST.md` (신규) — 전체 13단계 관통 흐름 + 컴포넌트별 mock/real 표 + STEP 012+ 후보 목록
- `plans/010_NEXTJS_FRONTEND_SKELETON_PLAN.md` (신규, 사후 PLAN 회복) — STEP 010 REPORT 기반 역설계 plan
- `plans/011_PRODUCT_SKELETON_HARDENING_PLAN.md` (본 plan의 영구 사본)
- `plans/011_PRODUCT_SKELETON_HARDENING_REPORT.md`

---

## 신규 / 수정 파일

### 신규
| 경로 | 목적 |
|---|---|
| `frontend/src/app/api/admin/__tests__/proxy.test.mjs` | Route Handler proxy 통합 테스트 |
| `tests/smoke/smoke.sh` | curl 기반 e2e smoke 스크립트 |
| `tests/smoke/test_full_pipeline.py` | Scenario A 전체 관통 smoke |
| `docs/SKELETON_COMPLETION_CHECKLIST.md` | 13단계 관통 checklist + mock/real 표 |
| `plans/010_NEXTJS_FRONTEND_SKELETON_PLAN.md` | 사후 PLAN 회복 |
| `plans/011_PRODUCT_SKELETON_HARDENING_PLAN.md` | 본 plan 영구 사본 |
| `plans/011_PRODUCT_SKELETON_HARDENING_REPORT.md` | 실행 보고 |

### 수정
| 경로 | 변경 |
|---|---|
| `backend/app/api/health.py` | components 중첩 + opensearch 추가, legacy flat 호환 유지 |
| `backend/app/api/themes.py` | name/description/event_count 추가 |
| `backend/app/api/sectors.py` | 동일 |
| `backend/app/schemas/events.py` | EventSearchHit에 `id`/`confidence_score` 추가 |
| `backend/app/services/event_service.py` | count_by_theme / count_by_sector 신규 |
| `backend/app/services/opensearch_index_service.py` | `_card_to_doc`에 confidence_score 포함 |
| `backend/app/services/search_service.py` | hit 빌드 시 `id` alias 채움 |
| `backend/tests/test_health.py` | components 응답 검증 추가 |
| `backend/tests/test_search_api.py` | id/confidence_score 필드 검증 |
| `frontend/src/lib/api/types.ts` | Theme/Sector/HealthResponse/EventSearchHit 갱신 |
| `frontend/src/app/api/admin/reconcile/route.ts` | path 정정 |
| `frontend/src/app/api/admin/requeue/[id]/route.ts` | body+Content-Type 보강 |
| `frontend/package.json`, `package-lock.json` | next/eslint-config-next 15.2.x+ 업그레이드 |
| `workers/queue/consumer.py` | heartbeat touch |
| `agents/agent_worker.py` | heartbeat touch |
| `docker-compose.dev.yml` | 127.0.0.1 포트 바인딩 + worker/agent-worker healthcheck |
| `.env.example` | INTERNAL_API_BASE_URL 항목 추가 |
| `docs/*.md` (위 표 참조) | contract/skeleton 갱신 |

---

## 비범위 (절대 하지 않음)

- DART/SEC collector 추가
- Hybrid search ranking (Milvus + OpenSearch rerank)
- RBAC / OAuth / 로그인
- WebSocket / SSE 실시간 push
- shadcn/ui / radix 도입 (FRONTEND_DESIGN.md에 STEP 012+ 후보로만 기록)
- Playwright UI e2e 도입 (smoke.sh + node test로 대체)
- production deploy / domain / TLS / CDN
- LangGraph mock 노드 6개를 실제 모델로 교체
- 디자인 시스템 / 다크모드 / i18n
- backend 전체 refactor
- Dockerfile non-root user (이번 결정에서 보류)
- 한국어 nori analyzer

## 절대 금지

- `Remove-Item`, `rm`, `del`, `git reset --hard`, `git clean -fdx`
- `git push` (모든 변형)
- `docker volume rm`, `docker compose down -v`
- `.env` 실값, ADMIN_API_TOKEN/OPENAI_API_KEY/LANGSMITH_API_KEY 실값 노출
- `NEXT_PUBLIC_ADMIN_*` 변수 신규 정의
- `npm audit fix --force` (major upgrade 위험)
- node_modules, .next, build 산출물 commit
- codex worktree 파일 직접 수정

---

## 실행 순서

### Phase 0 — Pre-flight
- `git status`, `docker compose ps`, 10개 컨테이너 healthy 재확인
- `npm audit --json` 으로 현재 vulnerability 목록 캡처 (STEP 010 보고 1 moderate + 1 critical 매칭 확인)

### Phase 1 — Backend contract 정렬
1. `backend/app/services/event_service.py`에 `count_by_theme`/`count_by_sector` 추가
2. `backend/app/api/themes.py`, `sectors.py` — name/description/event_count 추가
3. `backend/app/api/health.py` — components 중첩 + opensearch 추가
4. `backend/app/schemas/events.py` — EventSearchHit id/confidence_score
5. `backend/app/services/opensearch_index_service.py` — `_card_to_doc`에 confidence_score
6. `backend/app/services/search_service.py` — hit `id` alias
7. backend tests 갱신 (test_health, test_search_api)
8. `pytest backend/tests agents/tests workers/tests -q` 회귀

### Phase 2 — Frontend contract + proxy fix + Next 업그레이드
1. `frontend/src/lib/api/types.ts` 갱신
2. `frontend/src/app/api/admin/reconcile/route.ts` 경로 수정
3. `frontend/src/app/api/admin/requeue/[id]/route.ts` body/header 보강
4. `frontend/src/components/HealthStatus.tsx` — components 우선, flat fallback
5. `frontend/src/app/themes/page.tsx`, `sectors/page.tsx` — name 표시
6. `npm install next@^15.2.3 eslint-config-next@^15.2.3`
7. `npm audit` 재실행 → critical 해소 확인
8. `npm run typecheck && npm run lint && npm run build && npm run test`

### Phase 3 — Frontend Route Handler proxy 통합 테스트
1. `frontend/src/app/api/admin/__tests__/proxy.test.mjs` 작성 (node --test)
2. `npm run test` 통과 확인 (총 4건 이상)

### Phase 4 — Docker hardening
1. `docker-compose.dev.yml` 포트 127.0.0.1 바인딩
2. `workers/queue/consumer.py`, `agents/agent_worker.py` heartbeat 추가
3. `docker-compose.dev.yml` worker/agent-worker healthcheck
4. `.env.example` INTERNAL_API_BASE_URL 추가
5. `docker compose config --quiet` 통과
6. `docker compose build worker agent-worker backend frontend` 빌드
7. `docker compose up -d` → 10개 컨테이너 healthy 확인

### Phase 5 — Smoke + Scenario A
1. `tests/smoke/smoke.sh` 작성 + 실행 (curl 6종)
2. `tests/smoke/test_full_pipeline.py` 작성
3. `pytest tests/smoke -q` (RUN_OPENSEARCH_INTEGRATION 등 gate 환경변수 확인)

### Phase 6 — 문서 업데이트
1. `docs/API_CONTRACT.md` — health/themes/sectors/search hit 갱신 + reconcile 경로 정정 + `/api/internal/search-similar` 신규 섹션
2. `docs/ARCHITECTURE.md` — Mock/Real 표 STEP 011 시점 갱신
3. `docs/TRD.md` — STEP 011 섹션
4. `docs/FRONTEND_DESIGN.md` — Route Handler proxy 테스트 전략
5. `docs/DEPLOYMENT.md` — smoke.sh 사용법 + 127.0.0.1 바인딩 안내
6. `docs/COMPATIBILITY_NOTES.md` — STEP 010 TODO 정리 + Next 15.2 노트
7. `docs/SKELETON_COMPLETION_CHECKLIST.md` 신규
8. `plans/010_NEXTJS_FRONTEND_SKELETON_PLAN.md` (사후 회복)
9. `plans/011_PRODUCT_SKELETON_HARDENING_PLAN.md` (본 plan 사본)
10. `plans/011_PRODUCT_SKELETON_HARDENING_REPORT.md`

### Phase 7 — 회귀 + Commit
1. `pytest backend/tests agents/tests workers/tests -q` 전체 PASS
2. `pytest tests/smoke -q` (gate 환경변수 분리)
3. `npm run typecheck && lint && build && test`
4. `docker compose ps` 10개 healthy
5. `bash tests/smoke/smoke.sh`
6. Commit A: `fix(step-011): align frontend/backend API contract for skeleton hardening`
   - `backend/app/api/health.py`, `themes.py`, `sectors.py`, `schemas/events.py`, `services/event_service.py`, `services/opensearch_index_service.py`, `services/search_service.py`, `backend/tests/test_health.py`, `test_search_api.py`
   - `frontend/src/lib/api/types.ts`, `app/api/admin/reconcile/route.ts`, `app/api/admin/requeue/[id]/route.ts`, `components/HealthStatus.tsx`, `app/themes/page.tsx`, `app/sectors/page.tsx`
7. Commit B: `chore(step-011): upgrade next.js 15.2 + docker hardening + tests/docs`
   - `frontend/package.json`, `package-lock.json`
   - `docker-compose.dev.yml`, `workers/queue/consumer.py`, `agents/agent_worker.py`, `.env.example`
   - `frontend/src/app/api/admin/__tests__/proxy.test.mjs`, `tests/smoke/smoke.sh`, `tests/smoke/test_full_pipeline.py`
   - `docs/*.md`, `plans/010_*.md`, `plans/011_*.md`

### Phase 8 — Codex sync
1. `git -C C:/Users/computer/Desktop/business/codex status --short` clean 확인
2. clean이면 main을 codex로 `merge --no-ff`
3. 충돌 시 자동 해결 금지, 보고

---

## 검증 체크리스트

### 빌드 & 회귀
- [ ] `pytest backend/tests agents/tests workers/tests -q` 전체 PASS (기존 ~140 + 신규 약 5)
- [ ] `npm run typecheck` 0 errors
- [ ] `npm run lint` 0 errors
- [ ] `npm run build` 성공
- [ ] `npm run test` (node) 6건+ PASS (기존 3 + proxy 3+)
- [ ] `npm audit` critical 0건 (moderate는 허용 시 COMPATIBILITY_NOTES 기록)
- [ ] `docker compose -f docker-compose.dev.yml config --quiet` PASS

### Container & smoke
- [ ] 10개 컨테이너 healthy (worker/agent-worker 포함, heartbeat healthcheck)
- [ ] `bash tests/smoke/smoke.sh` 6종 모두 200
- [ ] `pytest tests/smoke -q` 통과 (full stack 환경에서)
- [ ] curl OPTIONS preflight → `access-control-allow-origin: http://localhost:3000`

### Contract 검증 (수동)
- [ ] `/events` 카드 목록 표시
- [ ] `/events/[id]` 상세 표시
- [ ] `/search?q=Iran` 결과 표시 + 각 카드 link가 `/events/<uuid>` (undefined 아님)
- [ ] `/themes` 5개 타일에 이름/설명/카운트 표시
- [ ] `/sectors` 5개 타일에 이름/설명/카운트 표시
- [ ] `/admin` 4개 컴포넌트 표 (redis/milvus/postgres/opensearch) 표시
- [ ] `/admin` reconcile 버튼 클릭 시 200 응답 (404 아님)

### 보안 & policy
- [ ] postgres/redis/milvus/opensearch 외부 호스트(0.0.0.0)에서 connect 거부 (127.0.0.1만 허용)
- [ ] frontend bundle에 ADMIN_API_TOKEN 0건 (`grep -r ADMIN_API_TOKEN frontend/.next` empty)
- [ ] `git diff --stat`에 .env 실값 0
- [ ] node_modules / .next / build / volume / .venv 미커밋

### 문서
- [ ] API_CONTRACT.md의 reconcile 경로 정정
- [ ] API_CONTRACT.md에 `/api/internal/search-similar` 섹션 존재
- [ ] SKELETON_COMPLETION_CHECKLIST.md 신규 생성
- [ ] plans/010_PLAN.md, 011_PLAN.md, 011_REPORT.md 존재

### Commit
- [ ] Commit A/B 분리
- [ ] git push 미실행
- [ ] codex sync 완료 (clean 시)

---

## 위험 / UNKNOWN

| # | 항목 | 영향 | 완화 |
|---|---|---|---|
| R1 | Next 15.0.4 → 15.2.x minor 업그레이드로 빌드 깨짐 | 중간 | 같은 major. eslint-config-next 동일 버전 핀. 실패 시 lockfile 복원 후 15.1.x 시도 |
| R2 | OpenSearch ping이 health에서 timeout | 낮음 | 기존 `is_connected()` 재사용, 단발 호출. 실패 시 `"error"` 반환 (`milvus` 정책과 동일) |
| R3 | event_count COUNT(*) 성능 | 낮음 | event_cards 현재 row 수가 작음 (skeleton). GROUP BY theme 단발 쿼리. 향후 cache는 STEP 012+ |
| R4 | heartbeat 파일 / `stat -c %Y` Alpine BusyBox 호환성 | 낮음 | `stat -c` BusyBox 지원 확인 필요. 미지원 시 `find /tmp/heartbeat -mmin -1` fallback |
| R5 | 127.0.0.1 바인딩으로 codex worktree에서 외부 호스트 직접 접근 차단 | 낮음 | codex도 동일 호스트라 localhost로 접근. 영향 없음 |
| R6 | Scenario A smoke가 external LLM/OpenAI 호출 시 비용/시간 | 낮음 | LLM_PROVIDER=mock 강제. fixture RSS 사용 |
| R7 | EventSearchHit에 confidence_score 추가 → reindex 필요 | 중간 | reindex script 1회 실행 (`POST /api/admin/search/reindex`). plan 검증 단계에 포함 |
| U1 | shadcn/ui 도입 시점 | — | STEP 012+ FRONTEND_DESIGN.md TODO |
| U2 | Playwright UI e2e | — | smoke.sh + Route Handler test로 대체. STEP 012+ 검토 |
| U3 | LangGraph 6개 mock 노드 실모델 교체 | — | NER/분류기 도입 시 STEP 013+ |
| U4 | Dockerfile non-root user (backend/workers/agents) | — | STEP 012+ infra hardening |
| U5 | Production CORS 도메인 / TLS / CDN | — | deploy 단계 |
| U6 | RBAC / OAuth | — | STEP 011 이후 별도 트랙 |

---

## 다음 STEP 제안

| STEP | 주제 | 비고 |
|---|---|---|
| 012 | Hybrid search (Milvus vector + OpenSearch keyword rerank) | RAG_VECTOR_DESIGN.md TODO 해소 |
| 013 | DART/SEC collector + 한국어 nori analyzer | 신규 데이터 소스 |
| 014 | shadcn/ui 도입 + 디자인 시스템 + i18n | UX 고도화 |
| 015 | RBAC / OAuth / admin 권한 분리 | 보안 본격화 |
| 016 | Production deploy (CDN, TLS, prod CORS, secrets manager) | 운영 진입 |

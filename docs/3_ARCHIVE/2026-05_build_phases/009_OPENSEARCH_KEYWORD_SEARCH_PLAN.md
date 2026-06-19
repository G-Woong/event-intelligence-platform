# STEP 009 — OpenSearch Keyword Search Skeleton

## Context

STEP 008C까지 backend 운영 골격(admin token, requeue, scheduler script)이 정리됐다. 현재 검색 능력은 다음과 같다:
- **Milvus**: 의미 기반 유사 사건 검색 (`search_similar`, `retrieve_past_context`)
- **Postgres**: 단순 컬럼 필터 (`/api/events`, `/api/themes/{id}/events`, `/api/sectors/{id}/events`)
- **키워드 / 전문(full-text) 검색은 0%**. 사용자가 "title에 'Iran'이 들어간 사건" 같은 질의를 할 방법이 전혀 없다.

탐색 결과 OpenSearch 인프라는 완전 부재:
- `docker-compose.dev.yml`에 opensearch 서비스 없음 (현재 8개 컨테이너)
- `opensearch-py` 패키지 어디에도 없음
- `backend/app/db/opensearch.py` 없음
- `config.py` / `.env.example`에 `OPENSEARCH_*` 키 없음
- `docs/SEARCH_DESIGN.md` 없음

STEP 009 목표: **event_cards를 OpenSearch에 색인하고, 키워드로 검색할 수 있는 backend skeleton을 구축한다. Milvus는 의미 검색, OpenSearch는 키워드 검색으로 역할을 분리한다.**

## 사용자 결정 (확정)

| 항목 | 결정 |
|---|---|
| OpenSearch container | 이번 STEP에서 docker-compose.dev.yml에 추가 (8→9 컨테이너, single-node dev mode, security disabled) |
| 색인 대상 | **event_cards만**. raw_events는 STEP 010+에서 통합 검색 시 추가 |
| Search endpoint | **`/api/events/search`** — public, 무인증 (기존 events.py 패턴 유지) |
| Reindex | **admin endpoint + script 둘 다** — `POST /api/admin/search/reindex` (token 필요) + `scripts/reindex_opensearch_once.py` (cron/CI hook) |
| 색인 hook | `event_service.upsert_card` L96-100 직후 `opensearch_index_service.try_index_card(card)` (Milvus hook 옆) |
| 장애 정책 | OpenSearch 실패는 log warning, Postgres 저장은 보호. search endpoint는 503 반환 (fallback 없음 — TODO docs) |
| Analyzer | 기본(standard) analyzer만. 한국어 nori는 TODO로 SEARCH_DESIGN.md에 기록 |
| Hybrid retrieval | 이번 단계 X. `retrieve_past_context`는 Milvus만 유지 |

## 핵심 설계

### 1. OpenSearch Docker (`docker-compose.dev.yml`)

```yaml
opensearch:
  image: opensearchproject/opensearch:2.13.0
  environment:
    - discovery.type=single-node
    - plugins.security.disabled=true
    - OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m
    - DISABLE_INSTALL_DEMO_CONFIG=true
  ulimits:
    memlock: { soft: -1, hard: -1 }
    nofile: { soft: 65536, hard: 65536 }
  ports: ["9200:9200"]
  volumes:
    - opensearch_data:/usr/share/opensearch/data
  healthcheck:
    test: ["CMD-SHELL", "curl -sf http://localhost:9200/_cluster/health || exit 1"]
    interval: 10s
    timeout: 5s
    retries: 30
```

- `volumes:` 섹션에 `opensearch_data` 추가
- `backend`, `worker`, `agent-worker`의 `depends_on`에 `opensearch: { condition: service_healthy }` 추가 (backend만 필수, 나머지는 optional)
- 9 컨테이너 모두 healthy 검증

### 2. Config / Env (`backend/app/core/config.py`, `.env.example`)

```python
# config.py
OPENSEARCH_HOST: str = "opensearch"
OPENSEARCH_PORT: int = 9200
OPENSEARCH_EVENT_INDEX: str = "event_cards"
```

`.env.example`:
```
OPENSEARCH_HOST=opensearch
OPENSEARCH_PORT=9200
OPENSEARCH_EVENT_INDEX=event_cards
```

`redacted_env_status()`의 fields 리스트에 `OPENSEARCH_HOST/PORT/EVENT_INDEX` 추가.

### 3. OpenSearch Wrapper (`backend/app/db/opensearch.py` 신규)

`backend/app/db/milvus.py` 패턴 그대로:
- 모듈 전역 `_client`, `_connected` lazy 싱글톤
- `get_client()` → `OpenSearch(hosts=[{"host":..., "port":...}], use_ssl=False)`
- `connect() -> bool` → ping 시도, 성공 시 `_connected=True`
- `is_connected() -> bool`
- 실패는 try/except + logger.warning, non-fatal

### 4. Index Service (`backend/app/services/opensearch_index_service.py` 신규)

`vector_index_service.try_index_card` 패턴 그대로 복제:

```python
def try_index_card(card: FinalEventCard) -> None:
    try:
        client = opensearch_db.get_client()
        doc = _card_to_doc(card)
        client.index(
            index=settings.OPENSEARCH_EVENT_INDEX,
            id=str(card.id),
            body=doc,
            refresh=False,
        )
    except Exception as exc:
        logger.warning("opensearch index failed for card=%s: %s", card.id, exc)

def ensure_event_cards_index() -> None:
    # idempotent: HEAD index → create with mapping if not exists
    ...

def _card_to_doc(card: FinalEventCard) -> dict:
    text_all = " ".join(filter(None, [
        card.title, card.summary,
        " ".join(card.entities or []),
        " ".join(card.sectors or []),
    ]))
    return {
        "card_id": str(card.id),
        "title": card.title,
        "summary": card.summary,
        "theme": card.theme,
        "sectors": card.sectors or [],
        "entities": card.entities or [],
        "status": card.status,
        "confidence_score": card.confidence_score,
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "text_all": text_all,
    }
```

**Mapping** (standard analyzer):
- `title`: text + `keyword` subfield
- `summary`, `text_all`: text
- `theme`, `status`: keyword
- `sectors`, `entities`: keyword (array)
- `card_id`: keyword
- `confidence_score`: float
- `created_at`: date

### 5. Search Service (`backend/app/services/search_service.py` 신규)

```python
async def search_event_cards(
    q: str, theme: str | None = None, sector: str | None = None,
    status: str | None = None, limit: int = 20, offset: int = 0,
) -> dict:
    client = opensearch_db.get_client()
    must = [{"multi_match": {"query": q, "fields": ["title^2", "summary", "text_all"]}}]
    filter_clauses = []
    if theme:  filter_clauses.append({"term": {"theme": theme}})
    if sector: filter_clauses.append({"term": {"sectors": sector}})
    if status: filter_clauses.append({"term": {"status": status}})
    body = {
        "query": {"bool": {"must": must, "filter": filter_clauses}},
        "from": offset, "size": limit,
    }
    resp = client.search(index=settings.OPENSEARCH_EVENT_INDEX, body=body)
    return {
        "total": resp["hits"]["total"]["value"],
        "hits": [_hit_to_dict(h) for h in resp["hits"]["hits"]],
    }
```

### 6. Public Search Endpoint (`backend/app/api/events.py`)

`GET /api/events/{event_id}` (L18) **위에** static route 삽입 (순서 충돌 회피):

```python
@router.get("/search", response_model=EventSearchResponse)
async def search_events(
    q: str = Query(..., min_length=1, max_length=200),
    theme: str | None = None,
    sector: str | None = None,
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> EventSearchResponse:
    try:
        result = await search_service.search_event_cards(q, theme, sector, status, limit, offset)
        return EventSearchResponse(**result)
    except OpenSearchUnavailable:
        raise HTTPException(status_code=503, detail="search unavailable")
```

`q` 빈 값은 422 (Query min_length=1). 무인증 (기존 `/api/events` 패턴).

### 7. Indexing Hook (`backend/app/services/event_service.py`)

`upsert_card` L96-100 Milvus hook **직후**에 동일 패턴 추가:

```python
# 기존
try:
    vector_index_service.try_index_card(card)
except Exception as exc:
    logger.warning(...)
# 신규
try:
    opensearch_index_service.try_index_card(card)
except Exception as exc:
    logger.warning("opensearch hook failed: %s", exc)
```

Milvus hook과 OpenSearch hook은 **독립** — 하나 실패해도 다른 하나는 시도. 둘 다 실패해도 Postgres commit은 유지.

### 8. Admin Reindex (`backend/app/api/admin.py` + `scripts/reindex_opensearch_once.py`)

**Endpoint**: `POST /api/admin/search/reindex` (admin token 자동 적용 — router-level dependency)

```python
class ReindexRequest(BaseModel):
    limit: int = 1000
    dry_run: bool = False

class ReindexResponse(BaseModel):
    indexed: int
    dry_run: bool

@router.post("/search/reindex", response_model=ReindexResponse)
async def reindex_search(body: ReindexRequest, session=Depends(get_session)):
    cards = await event_service.list_events(session, limit=body.limit)  # 기존 함수 재사용
    if not body.dry_run:
        opensearch_index_service.ensure_event_cards_index()
        for card in cards:
            opensearch_index_service.try_index_card(card)
    return ReindexResponse(indexed=len(cards), dry_run=body.dry_run)
```

**Script** (`scripts/reindex_opensearch_once.py`): `scripts/reconcile_stuck_once.py` 패턴 복제 — env 기반 (`ADMIN_API_TOKEN`, `BACKEND_INTERNAL_URL`, `REINDEX_LIMIT`, `REINDEX_DRY_RUN`) 1회 HTTP 호출, exit 0/1.

### 9. Schemas (`backend/app/schemas/events.py`)

```python
class EventSearchHit(BaseModel):
    card_id: str
    title: str
    summary: str | None = None
    theme: str | None = None
    sectors: list[str] = []
    status: str | None = None
    score: float
    created_at: datetime | None = None

class EventSearchResponse(BaseModel):
    total: int
    hits: list[EventSearchHit]
```

### 10. Lifespan / Ensure Index (`backend/app/main.py`)

`lifespan` startup에 `redis_db.ping()` / `milvus_db.connect()` 라인 다음에:
```python
try:
    if opensearch_db.connect():
        opensearch_index_service.ensure_event_cards_index()
        logger.info("opensearch connected and index ensured")
    else:
        logger.warning("opensearch unavailable at startup")
except Exception as exc:
    logger.warning("opensearch startup error: %s", exc)
```

Non-fatal — backend는 OpenSearch 없이도 부팅 가능.

---

## 신규 / 수정 파일

### 신규

| 경로 | 목적 |
|---|---|
| `backend/app/db/opensearch.py` | OpenSearch client wrapper (milvus.py 패턴) |
| `backend/app/services/opensearch_index_service.py` | try_index_card, ensure_event_cards_index |
| `backend/app/services/search_service.py` | search_event_cards (multi_match + filters) |
| `scripts/reindex_opensearch_once.py` | env 기반 reindex 1회 호출 |
| `backend/tests/test_opensearch_wrapper.py` | wrapper 3 케이스 (connect ok / connect fail / ping) |
| `backend/tests/test_opensearch_index_service.py` | index/ensure/document shape 4 케이스 |
| `backend/tests/test_search_service.py` | search query body / response shape 3 케이스 |
| `backend/tests/test_search_api.py` | `/api/events/search` 4 케이스 (200 hits / q 누락 422 / 503 unavailable / filter) |
| `backend/tests/test_reindex_api.py` | `/api/admin/search/reindex` 3 케이스 (200 / dry_run / auth) |
| `backend/tests/test_reindex_script.py` | script 3 케이스 (happy / fail exit 1 / env override) |
| `tests/smoke/test_opensearch_search.py` | RUN_OPENSEARCH_INTEGRATION=1 게이트, upsert→search→hit |
| `docs/SEARCH_DESIGN.md` | OpenSearch 역할, mapping, Milvus와의 분리, TODO |
| `plans/009_OPENSEARCH_KEYWORD_SEARCH_PLAN.md` | 본 plan 영구 사본 |
| `plans/009_OPENSEARCH_KEYWORD_SEARCH_REPORT.md` | 실행 보고 |

### 수정

| 경로 | 변경 |
|---|---|
| `docker-compose.dev.yml` | opensearch service + opensearch_data volume + backend depends_on |
| `requirements/serve.txt` | `opensearch-py` 핀 추가 |
| `backend/app/core/config.py` | `OPENSEARCH_HOST/PORT/EVENT_INDEX` + redacted_env_status fields |
| `.env.example` | OPENSEARCH 섹션 추가 |
| `backend/app/main.py` | lifespan에 opensearch connect + ensure_event_cards_index |
| `backend/app/services/event_service.py` | upsert_card에 OpenSearch hook 추가 (Milvus hook 옆) |
| `backend/app/api/events.py` | `GET /search` 추가 (dynamic `/{event_id}` 위) |
| `backend/app/api/admin.py` | `POST /search/reindex` 추가 |
| `backend/app/schemas/events.py` | `EventSearchHit`, `EventSearchResponse`, `ReindexRequest/Response` |
| `backend/tests/test_event_service.py` (있다면) | OpenSearch hook 호출 검증 1 케이스 추가 (mock) |
| `docs/ARCHITECTURE.md` | OpenSearch 컴포넌트 + 색인 흐름 다이어그램, L189 갱신 |
| `docs/TRD.md` | STEP 009 컴포넌트/env var |
| `docs/API_CONTRACT.md` | `/api/events/search`, `/api/admin/search/reindex` 섹션 |
| `docs/EVENT_SCHEMA.md` | OpenSearch document schema 섹션 |
| `docs/COMPATIBILITY_NOTES.md` | STEP 009 추가 (한국어 nori TODO, hybrid TODO) |
| `docs/OBSERVABILITY.md` | OpenSearch index/reindex 로그 패턴 |
| `docs/COLLECTOR_DESIGN.md` | (선택) 검색 대상 정책 한 줄 |

---

## 비범위 (절대 하지 않음)

- Next.js / Frontend 검색 UI
- raw_events / comments 색인 (STEP 010+)
- 한국어 nori / 다국어 analyzer 고도화
- Hybrid search (Milvus + OpenSearch reranking)
- BM25 튜닝 / boost 튜닝 / synonym filter
- OpenSearch cluster / sharding / replica
- Search analytics / click tracking
- DART/SEC collector
- production auth/RBAC
- `retrieve_past_context` node 수정

## 절대 금지

- `Remove-Item`, `rm`, `del`, `git reset --hard`, `git clean -fdx`
- `git push` (모든 변형)
- `docker volume rm`, `docker compose down -v`
- `.env` 실제 값 (ADMIN_API_TOKEN 포함) 로그/응답/문서 노출
- OpenSearch data volume commit
- codex worktree 파일을 claude에서 직접 수정

---

## 테스트 전략

### Unit — `test_opensearch_wrapper.py` (3)
1. `connect()` → mock OpenSearch.ping=True → return True, `_connected=True`
2. `connect()` → mock ping 예외 → return False, warning
3. `get_client()` → 동일 인스턴스 재사용

### Unit — `test_opensearch_index_service.py` (4)
1. `try_index_card(card)` → mock client.index 호출 검증 (index name, id=str(card.id), body shape)
2. `try_index_card` → client.index 예외 → warning만, 예외 미전파
3. `ensure_event_cards_index()` → client.indices.exists=False → create 호출
4. `_card_to_doc(card)` → text_all 통합 필드 검증

### Unit — `test_search_service.py` (3)
1. `search_event_cards("Iran")` → mock client.search → body의 multi_match 쿼리 검증
2. filter (theme, sector, status) → bool filter clauses 검증
3. response shape: `{total, hits: [{card_id, title, score, ...}]}`

### Unit — `test_search_api.py` (4)
1. `GET /api/events/search?q=Iran` → 200, hits 반환 (service mock)
2. `GET /api/events/search` (q 누락) → 422
3. service가 OpenSearchUnavailable 발생 → 503
4. theme/sector/limit 파라미터 전달 검증

### Unit — `test_reindex_api.py` (3)
1. `POST /api/admin/search/reindex` (token 없음 + ADMIN_API_TOKEN 설정) → 401
2. dependency_override + 정상 → 200, `indexed=N`
3. dry_run=true → ensure_index/try_index 미호출 (count만 반환)

### Unit — `test_reindex_script.py` (3)
1. httpx.post mock 200 → exit 0, stdout JSON
2. httpx.post mock 500 → exit 1, stderr
3. env override (`REINDEX_LIMIT=50`, `REINDEX_DRY_RUN=true`) → payload 검증

### Unit — 기존 admin/internal 테스트 영향
- `test_admin_auth.py`에 `/api/admin/search/reindex` 보호 케이스 1개 추가 (선택)
- 기존 dependency_override 패턴 자동 적용 → 영향 0

### Smoke — `tests/smoke/test_opensearch_search.py` (RUN_OPENSEARCH_INTEGRATION=1)
1. ensure index (HEAD)
2. upsert FinalEventCard (title="STEP009_smoke_token_<uuid>", summary, theme)
3. wait refresh (`client.indices.refresh` 또는 short sleep)
4. `GET /api/events/search?q=STEP009_smoke_token_<uuid>` → hits에 card_id 포함

### 회귀 게이트 (필수 PASS)
- `pytest backend/tests agents/tests workers/tests -v`
- `pytest tests/smoke/test_pipeline.py test_persistence.py test_raw_event_lifecycle.py test_rss_collector_fixture.py test_reconciler.py test_requeue.py -v` (기존 7종)
- `RUN_OPENSEARCH_INTEGRATION=1 pytest tests/smoke/test_opensearch_search.py -v`
- 9 컨테이너 Up/healthy
- OpenSearch 컨테이너 down 상태에서도 `POST /api/admin/upsert-event` 성공 (Postgres만)

---

## 실행 순서

### Phase 0 — 정적 점검
- `git status; git log --oneline -8; docker compose -f docker-compose.dev.yml ps`

### Phase 1 — Docker / Infra
1. `docker-compose.dev.yml`에 opensearch service + volume 추가
2. `requirements/serve.txt`에 opensearch-py 추가
3. `docker compose -f docker-compose.dev.yml config --quiet`
4. `.env.example` OPENSEARCH 섹션 추가

### Phase 2 — Wrapper / Config
1. `backend/app/core/config.py` OPENSEARCH 필드 + redacted fields
2. `backend/app/db/opensearch.py` 신규 (milvus.py 패턴)
3. `backend/tests/test_opensearch_wrapper.py` 3 케이스 → PASS

### Phase 3 — Index service / Mapping
1. `backend/app/services/opensearch_index_service.py` 신규 (try_index_card, ensure_event_cards_index, _card_to_doc)
2. `backend/tests/test_opensearch_index_service.py` 4 케이스 → PASS

### Phase 4 — Hook 부착
1. `backend/app/services/event_service.py` upsert_card에 OpenSearch hook 추가
2. 기존 `test_event_service.py` 또는 신규 mock 검증
3. Milvus hook과 독립성 검증 (둘 중 하나 실패해도 다른 하나 호출)

### Phase 5 — Search service / API
1. `backend/app/services/search_service.py` 신규
2. `backend/app/schemas/events.py` EventSearchHit/Response 추가
3. `backend/app/api/events.py` GET /search 추가 (dynamic 위)
4. `backend/tests/test_search_service.py` 3 케이스 → PASS
5. `backend/tests/test_search_api.py` 4 케이스 → PASS

### Phase 6 — Reindex
1. `backend/app/api/admin.py` POST /search/reindex 추가
2. `backend/app/schemas/events.py` ReindexRequest/Response
3. `backend/tests/test_reindex_api.py` 3 케이스 → PASS
4. `scripts/reindex_opensearch_once.py` 신규
5. `backend/tests/test_reindex_script.py` 3 케이스 → PASS

### Phase 7 — main.py lifespan
1. opensearch connect + ensure_event_cards_index 호출 추가
2. `backend/tests/test_health.py` 회귀 → PASS

### Phase 8 — Rebuild + Smoke
1. `docker compose -f docker-compose.dev.yml build backend worker agent-worker`
2. `docker compose -f docker-compose.dev.yml up -d` (9 컨테이너)
3. 9 컨테이너 healthy 확인 (opensearch healthcheck 60s 대기 가능)
4. `RUN_OPENSEARCH_INTEGRATION=1 pytest tests/smoke/test_opensearch_search.py -v`
5. 기존 smoke 7종 회귀 → PASS
6. **장애 테스트**: `docker compose stop opensearch` → upsert 호출 → Postgres 200 + 로그에 OpenSearch warning 확인 → `docker compose start opensearch`

### Phase 9 — 문서
1. `docs/SEARCH_DESIGN.md` 신규 (역할 분리, mapping, TODO)
2. `docs/ARCHITECTURE.md` L189 갱신 + 색인 흐름 추가
3. `docs/API_CONTRACT.md` /api/events/search, /api/admin/search/reindex 섹션
4. `docs/EVENT_SCHEMA.md` OpenSearch document schema 섹션
5. `docs/TRD.md` STEP 009 env vars / 컴포넌트
6. `docs/OBSERVABILITY.md` index/reindex 로그 패턴
7. `docs/COMPATIBILITY_NOTES.md` STEP 009 (한국어 nori TODO, hybrid TODO)
8. `plans/009_OPENSEARCH_KEYWORD_SEARCH_PLAN.md` + `_REPORT.md`

### Phase 10 — Commit
- Commit A: `feat(step-009): add opensearch keyword search skeleton`
  - docker-compose, requirements, config, wrapper, index/search service, api endpoints, schemas, hook
- Commit B: `chore(step-009): reindex script + docs/plan/report`
  - script, SEARCH_DESIGN.md, 문서 6종 갱신, plan/report
- `git push` **미실행**

### Phase 11 — Codex sync
- `git -C C:/Users/computer/Desktop/business/codex status --short`
- clean이면 `git -C C:/Users/computer/Desktop/business/codex fetch && git -C ... merge --no-ff main`
- 충돌 시 자동 해결 금지 → 보고

---

## 검증 체크리스트

- [ ] `docker compose -f docker-compose.dev.yml config --quiet` PASS
- [ ] 9 컨테이너 Up/healthy (opensearch 포함)
- [ ] `curl http://localhost:9200/_cluster/health` status=green|yellow
- [ ] `backend/app/db/opensearch.py` 신규 + lifespan connect
- [ ] `OPENSEARCH_HOST/PORT/EVENT_INDEX` config + .env.example
- [ ] `event_service.upsert_card` Milvus + OpenSearch 양쪽 hook
- [ ] OpenSearch 다운 상태에서도 upsert 200 (Postgres 보호)
- [ ] `GET /api/events/search?q=` 422
- [ ] `GET /api/events/search?q=foo` 200 (mock or live)
- [ ] OpenSearchUnavailable → 503
- [ ] `POST /api/admin/search/reindex` 200 (token 적용) / 401 (token 누락 + 설정)
- [ ] reindex dry_run → indexed count만, 실제 index X
- [ ] `scripts/reindex_opensearch_once.py` happy/fail/env override 3 케이스
- [ ] smoke `test_opensearch_search.py` PASS (RUN_OPENSEARCH_INTEGRATION=1)
- [ ] 기존 smoke 7종 회귀 0
- [ ] `pytest backend/tests agents/tests workers/tests -v` 전체 PASS
- [ ] docs 7개 + SEARCH_DESIGN 신규 + plan/report
- [ ] 한국어 nori / hybrid / raw_events 색인 모두 TODO로 문서화
- [ ] Commit A/B, `.env`/.venv/opensearch_data 미포함
- [ ] `git push` 미실행
- [ ] codex sync 완료 (clean 시)
- [ ] WARNING/BLOCKED/UNKNOWN 명시

---

## 위험 / UNKNOWN

| # | 항목 | 영향 | 완화 |
|---|---|---|---|
| R1 | OpenSearch 1.5GB+ 메모리 → 로컬 Docker Desktop 자원 압박 | 중간 | `Xms512m -Xmx512m` 고정. healthcheck 60s 대기 허용. 문제 시 사용자 보고 후 profile 분리 검토 |
| R2 | opensearch container 부팅 늦음 → backend depends_on healthy 시 시작 지연 | 낮음 | healthcheck retries 30. backend lifespan은 connect 실패 시 warning만 (non-fatal). 정상 부팅 후 reindex로 복구 |
| R3 | OpenSearch index 실패가 Milvus hook으로 전파 | 중간 | 두 hook 각각 독립 try/except. test로 검증 |
| R4 | event_cards 색인 + Postgres update race → eventually consistent | 낮음 | source of truth = Postgres. reindex로 보정. 문서화 |
| R5 | `/search` route가 `/{event_id}` 보다 뒤에 등록되면 UUID 파싱 실패 | 중간 | static `/search`를 dynamic `/{event_id}` 위에 명시 배치 + 테스트 |
| R6 | 한국어 검색 품질 낮음 (standard analyzer는 어절 단위) | 낮음 | SEARCH_DESIGN.md에 nori TODO. 영문 키워드는 작동 |
| R7 | reindex 대량 처리 시 메모리 / 타임아웃 | 낮음 | limit 기본 1000. bulk API 미사용 (skeleton). 문서에 TODO |
| R8 | OpenSearch 응답 timestamp 포맷 mismatch | 낮음 | mapping에 date format 명시. `created_at`만 isoformat |
| U1 | 한국어 nori / 다국어 analyzer | — | STEP 010+ |
| U2 | raw_events / comments 색인 통합 | — | STEP 010+ |
| U3 | Hybrid search (BM25 + Milvus rerank) | — | STEP 011+ |
| U4 | OpenSearch 인증 (security plugin) | — | prod 진입 시 |
| U5 | bulk reindex 최적화 | — | 대량 진입 시 |

---

## 다음 STEP 제안

1. **STEP 009.5** — (선택) raw_events 색인 + source-aware search, `retrieve_past_context` hybrid (Milvus + OpenSearch)
2. **STEP 010** — Next.js `/events` UI + `/search?q=` UI + `/raw-events` admin UI
3. **STEP 011** — DART/SEC collector + 한국어 nori analyzer + 검색 랭킹 튜닝

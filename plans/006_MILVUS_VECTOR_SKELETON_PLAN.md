# STEP 006 — Milvus Embedding Insert/Search Skeleton

## Context

STEP 003~005.5에서 LangGraph + LLMClient + Postgres + Docker e2e 흐름이 완성됐지만,
Milvus는 여전히 stub 상태(`backend/app/db/milvus.py:33-42` 모든 함수가 `pass`/`return []`).
`retrieve_past_context` 노드는 `["[mock-context-1]"]`만 반환하고
(`agents/nodes/retrieve_context.py:6-7`), `deduplicate_event`는 sha256 hash pass-through만 수행
(`agents/nodes/deduplicate.py:6-9`).

본 STEP 006의 목표는 **Milvus 기반 Dense Vector RAG의 minimal end-to-end 경로**를 뚫는 것이다:

```
FinalEventCard
  → backend upsert_card
  → EmbeddingClient.embed_text(title + summary)
  → Milvus insert (collection: event_embeddings, dim=1536)
  → /api/internal/search-similar  (신규 endpoint)
  → agent-worker retrieve_past_context → state.past_context/retrieved_context
  → LangGraph 후속 노드(impact/fact_check/final_writer)에 context 입력
```

고도화(KG-RAG, hybrid search, reranker, chunking, threshold 튜닝)는 본 단계 범위 밖.
deduplicate는 hook/stub 연결까지만 허용.

---

## 사용자 확정 결정 (Phase 3 질의응답)

| 결정 항목 | 선택 |
|---|---|
| Search 경로 | **Backend API 경유**: `POST /api/internal/search-similar` 신설. agent-worker는 httpx로 호출. vector store 진입점을 backend로 단일화. agents/Dockerfile 무수정. |
| Embedding 차원 | **1536 단일 통일**. EMBEDDING_DIM=1536 고정. Mock/OpenAI 모두 1536-dim 반환. Milvus collection 단일. |
| EventState 키 | **둘 다 유지 (별칭)**. 기존 `past_context: List[str]`은 유지(하위호환), 신규 `retrieved_context: List[dict]` 추가. |

---

## 비범위 (절대 하지 않음)

- crawler (STEP 007)
- KG-RAG / hybrid search / reranker / chunking 고도화
- deduplicate threshold 튜닝 알고리즘 (hook만)
- OpenSearch, sparse retrieval 본격 도입
- Next.js frontend (STEP 009)
- agent-worker async 전환 (STEP 008)
- LangSmith tracing 실연결
- production-grade Milvus schema 최적화 (partition, dynamic field 등)
- pymilvus/Milvus 메이저 업그레이드
- 새 LLM provider
- agent-worker에 pymilvus 추가 (backend 경유로 회피)

---

## 절대 금지 (CLAUDE.md 준수)

- `Remove-Item`, `rm`, `del`, `git reset --hard`, `git clean -fdx`
- `git push`
- `docker volume rm`, `docker system prune -af`
- `.env` 실값 출력. `OPENAI_API_KEY` 길이만 logger.debug
- OpenAI 실호출 (`RUN_OPENAI_EMBED_SMOKE=1` 없으면 금지)
- codex worktree 안의 파일을 claude에서 직접 수정

---

## 변경/생성 파일

### 신규 파일

| 경로 | 목적 |
|---|---|
| `backend/app/services/embedding_client.py` | BaseEmbeddingClient + MockEmbeddingClient + OpenAIEmbeddingClient + factory + cache (LLMClient 패턴 미러) |
| `backend/app/services/vector_index_service.py` | upsert_card 직후 호출되는 thin orchestrator (embed → Milvus insert). 실패해도 Postgres write 안 깨지게 try/except. |
| `backend/app/api/internal.py` | router. `POST /api/internal/search-similar` (query_text 받아 embed + Milvus search → 결과 반환) |
| `backend/app/schemas/vector.py` | `SimilarEventQuery`/`SimilarEventHit` pydantic schema (event_id/card_id/score/title/summary 등) |
| `backend/tests/test_embedding_client.py` | Mock deterministic + OpenAI 키 누락 시 ValueError + 키 비노출 |
| `backend/tests/test_milvus_wrapper.py` | ensure_collection / insert / search 단위 (Milvus 컨테이너 가정, fixture로 collection 격리) |
| `backend/tests/test_vector_index_service.py` | upsert_card → insert 호출 검증, Milvus 실패 시 PG write 유지 |
| `backend/tests/test_internal_api.py` | `/api/internal/search-similar` 응답 schema |
| `agents/tools/vector_search.py` | retrieve_past_context가 사용하는 thin httpx wrapper (backend internal API 호출) |
| `agents/tests/test_retrieve_context.py` | mock vector_search 주입 → state.past_context/retrieved_context 검증, 실패 fallback |
| `tests/smoke/test_vector_search.py` | Docker e2e: upsert → insert → search → top1 == upserted id 확인 |
| `docs/RAG_VECTOR_DESIGN.md` | collection schema, embedding 정책, insert/search 흐름, dedup TODO |
| `plans/006_MILVUS_VECTOR_SKELETON_PLAN.md` | 본 plan의 영구 사본 |
| `plans/006_MILVUS_VECTOR_SKELETON_REPORT.md` | STEP 006 실행 보고 |

### 수정 파일

| 경로 | 변경 |
|---|---|
| `backend/app/db/milvus.py` | `ensure_event_embeddings_collection(dim)`, `insert_event_embedding(...)`, `search_similar_events(...)` 실구현. `is_connected()`를 `utility.get_server_version()` 기반 ping으로 교체 (W4 해소). 기존 module 플래그는 lazy connect 캐시로만 사용. |
| `backend/app/api/health.py` | milvus 판정을 try/except + `utility.get_server_version()` 또는 `connections.has_connection` 기반으로 교체. |
| `backend/app/core/config.py` | `EMBEDDING_PROVIDER: Literal["mock","openai"]="mock"`, `EMBEDDING_MODEL: str = "text-embedding-3-small"`, `EMBEDDING_DIM: int = 1536`, `EMBEDDING_TIMEOUT_SEC: float = 30.0`, `MILVUS_COLLECTION: str = "event_embeddings"` 추가. `redacted_env_status()` 갱신. |
| `.env.example` | 위 5개 키 빈값 추가. |
| `docker-compose.dev.yml` | `worker`/`agent-worker` environment에 MILVUS_HOST/PORT 명시(기본값 fallback). `backend` env에 EMBEDDING_*, BACKEND_INTERNAL_URL 추가. |
| `backend/app/services/event_service.py` | `upsert_card` 마지막에 `vector_index_service.try_index_card(card)` 호출 (await 또는 동기, 실패 swallow + logger.warning). |
| `backend/app/api/router.py` (또는 main.py include) | `internal` router 등록 (prefix `/api/internal`). |
| `agents/state/event_state.py` | `retrieved_context: List[dict]` 추가 (past_context는 유지). |
| `agents/nodes/retrieve_context.py` | `vector_search.search_similar(text, top_k=5)` 호출 → 결과를 `past_context`(요약 str 리스트)와 `retrieved_context`(dict 리스트) 양쪽에 채움. 실패 시 mock fallback + `llm_errors`에 기록. |
| `agents/nodes/deduplicate.py` | TODO 주석으로 vector-based dedup hook 자리 표시(기존 hash 로직 유지). 본 STEP에선 동작 변경 없음. |
| `agents/Dockerfile` | **수정 없음** (backend 경유로 pymilvus 회피). |
| `docs/ARCHITECTURE.md` | Milvus 경로 추가 (insert/search 흐름도). |
| `docs/TRD.md` | EmbeddingClient + vector_index_service + /api/internal/search-similar 명세. |
| `docs/EVENT_SCHEMA.md` (없으면 신규) | Milvus collection 필드 정의. |
| `docs/LLM_AGENT_DESIGN.md` | retrieve_past_context 연결 방식 추가. |
| `docs/COMPATIBILITY_NOTES.md` | STEP 006 섹션 + W4 해소 기록 + pymilvus 2.4.4 API 사용 노트. |

---

## Milvus Collection 설계

**collection name**: `event_embeddings` (환경변수 `MILVUS_COLLECTION`).

**dim**: 1536 (`EMBEDDING_DIM`).

**fields** (pymilvus 2.4.4 호환):

| 필드 | 타입 | 비고 |
|---|---|---|
| `pk` | INT64, auto_id=True, is_primary=True | Milvus 내부 PK |
| `event_id` | VARCHAR(64) | FinalEventCard.id (UUID 문자열) |
| `card_id` | VARCHAR(64) | 동일 (현재 schema에선 event_id == card_id, 향후 분리 대비) |
| `text_hash` | VARCHAR(64) | sha256(title+summary)[:32], 중복 insert 방지용 |
| `theme` | VARCHAR(64) | 단일 string |
| `source_type` | VARCHAR(32) | 향후 확장용 (현재는 "agent") |
| `created_at` | INT64 | unix timestamp |
| `metadata_json` | VARCHAR(2048) | sectors/entities 등 JSON 직렬화 (filter 본격 도입은 후속 STEP) |
| `embedding` | FLOAT_VECTOR(dim=1536) | |

**index**: `IVF_FLAT`, `metric_type=COSINE`, `nlist=128` (skeleton 기본값).

**search params**: `metric_type=COSINE`, `params={"nprobe": 8}`, `limit=5`.

**선택 이유**: JSON 필드는 pymilvus 2.4.4에서 가능하지만 dynamic field 의존성이 있어 skeleton에선 VARCHAR JSON으로 단순화. 후속 STEP에서 JSON 필드 + partition으로 migration TODO를 docs에 명시.

---

## EmbeddingClient 설계 (LLMClient 미러)

```
BaseEmbeddingClient(ABC):
  embed_text(text: str) -> list[float]
  embed_texts(texts: list[str]) -> list[list[float]]

MockEmbeddingClient:
  # deterministic: sha256(text)를 seed로 numpy.random.default_rng → dim float 정규화
  # 같은 text → 같은 vector. dim 일치 (EMBEDDING_DIM).

OpenAIEmbeddingClient:
  __init__: OPENAI_API_KEY 없으면 ValueError("OPENAI_API_KEY is not set (len=0)")
  embed_text/embed_texts: openai.embeddings.create(model=..., input=...)
  tenacity retry: 2회, RateLimitError/APITimeoutError만

create_embedding_client(provider, model) -> BaseEmbeddingClient
get_embedding_client() -> singleton
reset_embedding_client_cache()
```

**Mock deterministic 구현 (참고)**:
```python
import hashlib, numpy as np
seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
rng = np.random.default_rng(seed)
v = rng.normal(0, 1, dim).astype(np.float32)
v /= (np.linalg.norm(v) + 1e-12)  # normalize → cosine 친화
return v.tolist()
```

numpy가 base.txt에 없을 경우 hash bytes를 직접 float로 변환하는 stdlib-only 구현으로 대체.

---

## API: `/api/internal/search-similar`

```
POST /api/internal/search-similar
Body: { "query_text": str, "top_k": int = 5, "exclude_event_id": str | None }
Response: {
  "hits": [
    { "event_id": str, "card_id": str, "score": float, "title": str, "summary": str, "theme": str }
  ]
}
```

- backend가 embed → Milvus search → 결과의 event_id로 Postgres `event_cards` lookup하여 title/summary 채움
- `exclude_event_id`로 본인 카드 제외 (retrieve 호출 시 자기 자신 회수 방지)
- 인증은 STEP 006 범위 밖: prefix `/api/internal`만 사용, 향후 internal-only middleware 도입 TODO

---

## Insert 시점

`backend/app/services/event_service.py:upsert_card`의 마지막 `await session.commit()` 직후:

```python
try:
    await vector_index_service.try_index_card(card)
except Exception as exc:
    logger.warning("vector index failed for card=%s: %s", card.id, exc)
    # PG write는 유지, /health는 milvus error로 자연 노출
```

- `vector_index_service.try_index_card`는 backend 내부 함수 (HTTP 호출 아님)
- `text_hash`로 동일 텍스트 재upsert 시 무시(또는 같은 PK upsert) — pymilvus 2.4.4에서 auto_id 사용 시 deletion 후 insert 패턴 사용. skeleton에선 매번 새 insert 허용 + 중복 허용으로 단순화. 중복 정책은 docs TODO.

---

## retrieve_past_context 연결

```python
# agents/nodes/retrieve_context.py
def retrieve_past_context(state: EventState) -> EventState:
    normalized = state.get("normalized")
    if not normalized:
        return {**state, "past_context": [], "retrieved_context": []}

    text = f"{normalized.title}\n{normalized.body[:500]}"
    try:
        hits = vector_search.search_similar(
            text, top_k=5, exclude_event_id=normalized.id
        )
        past = [f"{h['title']}: {h['summary'][:200]}" for h in hits]
        return {**state, "past_context": past, "retrieved_context": hits}
    except Exception as exc:
        errors = list(state.get("llm_errors") or [])
        errors.append(f"retrieve_past_context: {exc}")
        return {
            **state,
            "past_context": ["[fallback-context]"],
            "retrieved_context": [],
            "llm_errors": errors,
        }
```

`vector_search.search_similar`은 `agents/tools/vector_search.py`에 정의된 thin httpx 함수 — `os.getenv("BACKEND_INTERNAL_URL", "http://backend:8000")` 기준 POST `/api/internal/search-similar` 호출.

---

## 실행 순서

### Phase 1 — 정적 점검

```powershell
docker compose -f docker-compose.dev.yml config --quiet
git status
git log --oneline -5
git worktree list
```

### Phase 2 — Config/.env/Compose 변경

1. `backend/app/core/config.py`에 EMBEDDING_*, MILVUS_COLLECTION 추가
2. `.env.example`에 5개 키 추가
3. `docker-compose.dev.yml`의 worker/agent-worker env에 MILVUS_HOST/PORT, BACKEND_INTERNAL_URL 추가
4. `docker compose config --quiet` 재확인

### Phase 3 — EmbeddingClient 구현

1. `backend/app/services/embedding_client.py` 작성 (Mock + OpenAI)
2. `backend/tests/test_embedding_client.py` 작성
3. `$env:PYTHONPATH=...; pytest backend/tests/test_embedding_client.py -q` PASS

### Phase 4 — Milvus wrapper 실구현 + W4 해소

1. `backend/app/db/milvus.py` 확장 (ensure/insert/search + 실 ping)
2. `backend/app/api/health.py` milvus 판정 교체
3. `backend/tests/test_milvus_wrapper.py` 작성 (Milvus 컨테이너 가정 — 환경변수 `RUN_MILVUS_INTEGRATION=1`일 때만 실행하도록 skip)

### Phase 5 — vector_index_service + internal API

1. `backend/app/services/vector_index_service.py` 신규
2. `backend/app/api/internal.py` 신규
3. `backend/app/schemas/vector.py` 신규
4. `event_service.upsert_card`에 hook 삽입
5. router include
6. `backend/tests/test_vector_index_service.py`, `test_internal_api.py` 작성

### Phase 6 — Agent 노드 연결

1. `agents/state/event_state.py`에 `retrieved_context` 추가
2. `agents/tools/vector_search.py` 신규
3. `agents/nodes/retrieve_context.py` 교체
4. `agents/nodes/deduplicate.py`에 TODO 주석만 추가 (동작 무변경)
5. `agents/tests/test_retrieve_context.py` 작성 (mock httpx 주입)

### Phase 7 — Docker 재빌드 + 회귀 게이트

```powershell
docker compose -f docker-compose.dev.yml build backend worker agent-worker
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml ps
curl -s http://localhost:8000/health
```

```powershell
$env:PYTHONPATH = "C:\Users\computer\Desktop\business\claude"
pytest backend/tests -q
pytest agents/tests -q
pytest tests/smoke/test_pipeline.py tests/smoke/test_persistence.py -q
```

기대: 기존 smoke 2 + 신규 unit 모두 PASS.

### Phase 8 — Milvus integration smoke

```powershell
$env:RUN_MILVUS_INTEGRATION = "1"
pytest backend/tests/test_milvus_wrapper.py -q
pytest tests/smoke/test_vector_search.py -q
```

smoke 흐름: enqueue raw_event → sleep 15s → `GET /api/events` → 최근 카드 id 추출 → `POST /api/internal/search-similar { query_text: ..., exclude_event_id: <other>}` → top1.event_id == 추출 id 확인.

### Phase 9 — OpenAI embedding opt-in (미실행)

```powershell
# 사용자 명시 시에만:
$env:RUN_OPENAI_EMBED_SMOKE = "1"
pytest backend/tests/test_embedding_client.py::test_openai_smoke -q
```

응답 길이/차원/모델명만 보고. 키 값 출력 금지.

### Phase 10 — 문서 + Commit

1. `docs/RAG_VECTOR_DESIGN.md` 신규
2. `docs/ARCHITECTURE.md`, `docs/TRD.md`, `docs/EVENT_SCHEMA.md`, `docs/LLM_AGENT_DESIGN.md`, `docs/COMPATIBILITY_NOTES.md` 갱신
3. `plans/006_MILVUS_VECTOR_SKELETON_PLAN.md` 영구 사본
4. `plans/006_MILVUS_VECTOR_SKELETON_REPORT.md` 실행 보고

**Commit A**: `feat(step-006): add milvus vector skeleton for event retrieval`
**Commit B**: `docs(step-006): rag vector design + plan/report snapshot`

`git push` 미실행.

### Phase 11 — Codex Sync

```powershell
git -C C:/Users/computer/Desktop/business/codex status --short
git -C C:/Users/computer/Desktop/business/codex fetch
git -C C:/Users/computer/Desktop/business/codex merge --ff-only main
# 실패 시 --no-ff merge (충돌 없을 때만)
```

---

## 검증 체크리스트

- [ ] `docker compose config --quiet` PASS
- [ ] config.py EMBEDDING_*, MILVUS_COLLECTION 5필드 추가
- [ ] `.env.example` 5키 추가
- [ ] EmbeddingClient Mock deterministic test PASS
- [ ] OpenAI 키 누락 시 ValueError + 키 비노출 test PASS
- [ ] Milvus wrapper ensure/insert/search 실구현 + integration test PASS (RUN_MILVUS_INTEGRATION=1)
- [ ] `/health`의 milvus 판정이 실 ping 기반으로 교체됨 (W4 해소)
- [ ] `POST /api/internal/search-similar` 응답 schema test PASS
- [ ] upsert_card → Milvus insert hook 동작, 실패 시 PG write 유지
- [ ] retrieve_past_context가 backend API 경유로 search → past_context + retrieved_context 채움
- [ ] retrieve 실패 시 fallback + llm_errors 누적
- [ ] `pytest backend/tests -q` 전체 PASS
- [ ] `pytest agents/tests -q` 전체 PASS (+ OpenAI smoke SKIP)
- [ ] `pytest tests/smoke/test_pipeline.py test_persistence.py -q` 기존 e2e 회귀 PASS
- [ ] `pytest tests/smoke/test_vector_search.py -q` 신규 vector smoke PASS
- [ ] 7개 컨테이너 모두 Up/healthy
- [ ] docs 6개 갱신 + RAG_VECTOR_DESIGN.md 신규
- [ ] Commit A/B 성공, `.env`/`.venv` 미포함
- [ ] `git push` 미실행
- [ ] codex sync 완료 (ff-only 또는 --no-ff)
- [ ] WARNING/BLOCKED/UNKNOWN 명시
- [ ] STEP 007 제안 포함

---

## 위험 / UNKNOWN

| # | 항목 | 영향 | 완화 |
|---|---|---|---|
| R1 | pymilvus 2.4.4 + Milvus 2.4.10 API 시그니처 (CollectionSchema/FieldSchema/Collection.create_index/load 흐름) | 중간 | 실 호출로 검증. 실패 시 docs/COMPATIBILITY_NOTES.md에 기록 후 최소 우회 |
| R2 | Milvus collection 첫 생성 시 health timing — backend 기동 직후 ensure_collection이 너무 일찍 호출되면 실패 | 중간 | `ensure_event_embeddings_collection`을 lazy(첫 insert/search 시) 호출 + retry 2회 |
| R3 | upsert_card → Milvus insert 동기 호출이 응답 시간을 늘림 | 낮음 | mock 환경에선 무시 가능. 실 OpenAI embedding 시 응답 영향 가능 → background task로 빼는 안은 STEP 008로 미룸 |
| R4 | retrieve_past_context HTTP hop latency | 낮음 | skeleton 단계 허용. 후속 STEP에서 internal RPC 또는 in-proc 호출 검토 |
| R5 | text_hash 충돌(다른 카드인데 같은 hash) | 매우 낮음 | sha256[:32]로 충돌 확률 무시 가능. 충돌 시 insert 중복으로 처리 |
| R6 | Milvus 재시작 시 collection 유실 | 낮음 | volume 마운트 확인 (compose에서 milvus volume). 첫 호출 시 ensure로 재생성 |
| R7 | OpenAI embedding 비용 | 낮음 | 기본 mock 유지, opt-in만 |
| R8 | numpy 의존 (Mock에서 사용 시) | 낮음 | `requirements/base.txt`에 이미 있는지 확인. 없으면 hash 기반 deterministic으로 numpy 없이 구현 가능 |
| U1 | dedup vector threshold 정책 — 본 STEP에선 미결 | 명시적으로 STEP 010 이후로 연기, docs TODO |

---

## 다음 STEP 순서

1. **STEP 007** — RSS crawler 1종 + `raw_events` 테이블 + Alembic migration.
2. **STEP 008** — agent-worker async 전환 + Milvus insert를 background task로 분리 + LangSmith tracing 실연결.
3. **STEP 009** — Next.js `/events` 목록 UI + 검색 UI (vector search 결과 노출).
4. **STEP 010** — `entity_linking`/`theme_sector_mapping`/`evidence_check` LLM 전환 + vector dedup threshold 정책.
5. **STEP 011** — KG-RAG / hybrid search (sparse + dense) 도입.

# STEP 006 실행 보고 — Milvus Vector Skeleton

날짜: 2026-05-23

---

## ① 무엇을 했는가

### Phase 2 — Config / .env.example / Compose
- `backend/app/core/config.py`: `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `EMBEDDING_TIMEOUT_SEC`, `MILVUS_COLLECTION`, `BACKEND_INTERNAL_URL` 6개 필드 추가. `redacted_env_status()` 갱신.
- `.env.example`: STEP 006 섹션 5키 추가.
- `docker-compose.dev.yml`: backend에 EMBEDDING_* 환경변수, worker/agent-worker에 MILVUS_HOST/PORT, agent-worker에 BACKEND_INTERNAL_URL 추가.

### Phase 3 — EmbeddingClient
- `backend/app/services/embedding_client.py` 신규: `BaseEmbeddingClient`, `MockEmbeddingClient` (stdlib-only 결정론 구현, sha256 seed → L2 정규화), `OpenAIEmbeddingClient` (tenacity 2회 retry), factory/singleton.
- `backend/tests/test_embedding_client.py` 신규: 9 tests PASS.

### Phase 4 — Milvus wrapper 실구현
- `backend/app/db/milvus.py`: `ensure_event_embeddings_collection(dim)`, `insert_event_embedding(...)`, `search_similar_events(...)` 실구현.
- `is_connected()`: `utility.get_server_version()` 실 ping 기반으로 교체 (W4 해소).
- `backend/app/api/health.py`: milvus 판정 주석 추가 (실 ping 기반 명시).
- `backend/tests/test_milvus_wrapper.py` 신규: 3 integration tests (RUN_MILVUS_INTEGRATION=1).
- **R1 해소**: pymilvus 2.4.4에서 `hit.entity.get(key)` 1인자 제한 확인 → `or ""` fallback 패턴으로 수정.

### Phase 5 — vector_index_service + internal API
- `backend/app/schemas/vector.py` 신규: `SimilarEventQuery`, `SimilarEventHit`, `SimilarEventResponse`.
- `backend/app/services/vector_index_service.py` 신규: `try_index_card(card)` — embed → insert, 실패 swallow.
- `backend/app/api/internal.py` 신규: `POST /api/internal/search-similar`.
- `backend/app/services/event_service.py`: `upsert_card` 마지막에 `try_index_card` hook 삽입 (try/except로 보호).
- `backend/app/main.py`: `internal.router` 등록 (prefix `/api/internal`).
- `backend/tests/test_vector_index_service.py`, `test_internal_api.py` 신규.

### Phase 6 — Agent 노드 연결
- `agents/state/event_state.py`: `retrieved_context: list[dict]` 추가 (past_context 유지).
- `agents/tools/vector_search.py` 신규: `search_similar(text, top_k, exclude_event_id)` thin httpx wrapper.
- `agents/nodes/retrieve_context.py`: backend API 경유 vector search 연결. 실패 시 fallback + llm_errors.
- `agents/nodes/deduplicate.py`: vector dedup TODO 주석 추가 (동작 무변경).
- `agents/tests/test_retrieve_context.py` 신규: 5 tests PASS.

### Phase 7/8 — Docker + smoke
- backend/worker/agent-worker 재빌드 PASS.
- 7개 컨테이너 모두 Up/healthy.
- `/health` → `{"status":"ok","redis":"ok","milvus":"ok","postgres":"ok"}`.
- `tests/smoke/test_vector_search.py` 신규: upsert → Milvus insert → search → card_id 확인 PASS.

### Phase 10 — 문서
- `docs/RAG_VECTOR_DESIGN.md` 신규.
- `docs/ARCHITECTURE.md`: Milvus insert/search 흐름도 추가.
- `docs/TRD.md`: STEP 006 컴포넌트/환경변수 추가.
- `docs/EVENT_SCHEMA.md`: Milvus Vector Schema 섹션 추가.
- `docs/LLM_AGENT_DESIGN.md`: retrieve_past_context 연결 방식 섹션 추가.
- `docs/COMPATIBILITY_NOTES.md`: STEP 006 섹션 + W4 해소 + pymilvus 2.4.4 API 노트.

---

## ② 무엇을 검증했는가

| 검증 항목 | 결과 |
|---|---|
| `docker compose config --quiet` | PASS |
| config.py EMBEDDING_* 6개 필드 | 추가 완료 |
| `.env.example` 5키 추가 | 완료 |
| `pytest backend/tests -q` | **26 PASS, 4 SKIP** |
| `pytest agents/tests -q` | **15 PASS, 1 SKIP** |
| `pytest tests/smoke/test_pipeline.py test_persistence.py -q` | **2 PASS** (회귀 없음) |
| Milvus integration (RUN_MILVUS_INTEGRATION=1) | **3 PASS** |
| vector search e2e smoke (RUN_MILVUS_INTEGRATION=1) | **1 PASS** |
| `/health` milvus 실 ping | "ok" 확인 |
| upsert_card → Milvus insert | 동작 확인 |
| retrieve_past_context → backend API → search → past_context/retrieved_context | 동작 확인 |
| retrieve 실패 → fallback + llm_errors | 테스트 PASS |
| OpenAI embedding smoke | SKIP (RUN_OPENAI_EMBED_SMOKE 미설정) |
| 7개 컨테이너 Up/healthy | 확인 |
| `.env` 실값 미출력 | 준수 |
| `git push` 미실행 | 준수 |

---

## ③ WARNING / BLOCKED / UNKNOWN

### WARNING
- **W4 해소 완료**: `is_connected()`가 `utility.get_server_version()` 실 ping 기반으로 교체됨.
- **pymilvus 2.4.4 hit.entity.get() 제한**: default 인자 없음 확인. `or ""` fallback으로 수정 완료. `docs/COMPATIBILITY_NOTES.md`에 기록.
- **OpenAI embedding 미검증**: `RUN_OPENAI_EMBED_SMOKE=1` 미설정으로 skip. Mock만 검증됨.

### BLOCKED
- 없음.

### UNKNOWN
- **U1 dedup threshold 정책**: STEP 010+ 이후로 명시 연기. `deduplicate.py` TODO 주석 추가.

---

## 다음 STEP 제안

1. **STEP 007**: RSS crawler 1종 + `raw_events` 테이블 + Alembic migration.
2. **STEP 008**: agent-worker async 전환 + Milvus insert background task + LangSmith tracing 실연결.
3. **STEP 009**: Next.js `/events` 목록 UI + 검색 UI.

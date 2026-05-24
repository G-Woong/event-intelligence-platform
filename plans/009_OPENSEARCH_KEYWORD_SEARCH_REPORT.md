# STEP 009 실행 보고 — OpenSearch Keyword Search Skeleton

**실행일**: 2026-05-24

---

## ① 무엇을 했는가

### Phase 1 — Docker / Infra
- `docker-compose.dev.yml`에 `opensearch:2.13.0` 서비스 추가 (single-node, security disabled, Xms512m)
- `opensearch_data` volume 추가
- `backend` depends_on에 `opensearch: { condition: service_healthy }` 추가
- `backend` environment에 `OPENSEARCH_HOST/PORT/EVENT_INDEX` 추가
- `requirements/serve.txt`에 `opensearch-py==2.7.1` 추가
- `.env.example`에 OPENSEARCH_* 섹션 및 REINDEX_* 섹션 추가

### Phase 2 — Config
- `backend/app/core/config.py`에 `OPENSEARCH_HOST/PORT/EVENT_INDEX` 필드 추가
- `redacted_env_status()` fields 리스트에 3개 키 추가

### Phase 3 — OpenSearch Wrapper
- `backend/app/db/opensearch.py` 신규 (milvus.py 패턴: singleton _client, connect, is_connected, get_client)

### Phase 4 — Index Service
- `backend/app/services/opensearch_index_service.py` 신규
  - `_card_to_doc`: text_all 통합 필드 포함
  - `ensure_event_cards_index`: idempotent (HEAD → create with mapping)
  - `try_index_card`: 실패 시 warning만 (non-fatal)
  - standard analyzer mapping (title text+keyword subfield, sectors/entities keyword[])

### Phase 5 — Hook 부착
- `event_service.upsert_card` Milvus hook 직후에 OpenSearch hook 독립 추가
- `list_events`에 `limit` 파라미터 추가 (reindex에서 사용)

### Phase 6 — Search Service / API
- `backend/app/services/search_service.py` 신규
  - `search_event_cards`: multi_match + bool filter
  - `OpenSearchUnavailable` 예외 클래스
- `backend/app/schemas/events.py`에 `EventSearchHit`, `EventSearchResponse`, `ReindexRequest`, `ReindexResponse` 추가
- `backend/app/api/events.py`에 `GET /api/events/search` 추가 (dynamic `/{event_id}` 위에 배치)

### Phase 7 — Admin Reindex
- `backend/app/api/admin.py`에 `POST /api/admin/search/reindex` 추가
- `scripts/reindex_opensearch_once.py` 신규 (reconcile_stuck_once.py 패턴)

### Phase 8 — main.py lifespan
- opensearch_db import + opensearch_index_service import
- lifespan startup에 connect + ensure_event_cards_index (non-fatal)

### Phase 9 — 테스트
- `test_opensearch_wrapper.py`: 3 케이스 PASS
- `test_opensearch_index_service.py`: 4 케이스 PASS
- `test_search_service.py`: 3 케이스 PASS
- `test_search_api.py`: 4 케이스 PASS
- `test_reindex_api.py`: 3 케이스 PASS
- `test_reindex_script.py`: 3 케이스 PASS
- `tests/smoke/test_opensearch_search.py`: RUN_OPENSEARCH_INTEGRATION=1 게이트, 작성 완료

### Phase 10 — 문서
- `docs/SEARCH_DESIGN.md` 신규 (역할 분리, mapping, 색인 흐름, 장애 정책, TODO)
- `docs/ARCHITECTURE.md` OpenSearch DONE 표기
- `docs/API_CONTRACT.md` GET /api/events/search + POST /api/admin/search/reindex 섹션
- `docs/EVENT_SCHEMA.md` OpenSearch document schema 섹션
- `docs/TRD.md` STEP 009 컴포넌트/env var
- `docs/OBSERVABILITY.md` OpenSearch 로그 패턴
- `docs/COMPATIBILITY_NOTES.md` STEP 009 TODO (nori, hybrid, raw_events, security, bulk)

---

## ② 무엇을 검증했는가

| 항목 | 결과 |
|---|---|
| `docker compose -f docker-compose.dev.yml config --quiet` | PASS |
| `pytest backend/tests/test_opensearch_wrapper.py` (3) | PASS |
| `pytest backend/tests/test_opensearch_index_service.py` (4) | PASS |
| `pytest backend/tests/test_search_service.py` (3) | PASS |
| `pytest backend/tests/test_search_api.py` (4) | PASS |
| `pytest backend/tests/test_reindex_api.py` (3) | PASS |
| `pytest backend/tests/test_reindex_script.py` (3) | PASS |
| `pytest backend/tests/ agents/tests/ workers/tests/` 전체 | **127 PASS, 5 SKIP, 0 FAIL** |
| OpenSearch 컨테이너 up/healthy | 이미지 다운로드 중 (888.9MB, 진행 중) |
| RUN_OPENSEARCH_INTEGRATION=1 smoke | 컨테이너 완료 후 실행 예정 |
| OpenSearch 다운 시 upsert 보호 | 테스트로 검증 (mock 기반) |

---

## ③ WARNING / BLOCKED / UNKNOWN

| # | 항목 | 상태 | 내용 |
|---|---|---|---|
| W1 | OpenSearch 이미지 다운로드 | WARNING | 888.9MB 이미지 다운로드 중. 완료 후 backend 재빌드 필요 |
| W2 | opensearch-py 로컬 venv 설치 | WARNING | `uv pip install opensearch-py==2.7.1`로 설치 완료. `events==0.5` 패키지도 함께 설치됨 (opensearch-py 의존성) |
| W3 | 한국어 검색 품질 | WARNING | standard analyzer 사용. 영문 키워드는 정상. 한국어 어절 단위 tokenization → nori는 STEP 010+ |
| U1 | Hybrid search | UNKNOWN | STEP 011+ |
| U2 | raw_events 색인 | UNKNOWN | STEP 010+ |
| U3 | prod OpenSearch 인증 | UNKNOWN | security plugin 활성화 시 설정 별도 필요 |

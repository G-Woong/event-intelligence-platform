# LLM + LangGraph + RAG + 검색 파이프라인

> LLMClient 추상화, LangGraph 11 노드, Milvus(벡터), OpenSearch(키워드) 구조를 설명합니다.

---

## LLM / Embedding 클라이언트 추상화

### 왜 추상화했나

개발·테스트 시 OpenAI API를 호출하면 비용이 발생하고 테스트가 결정론적이지 않음.  
→ Mock 클라이언트와 실 클라이언트를 동일 인터페이스로 교체 가능하게 설계.

```
환경변수           사용되는 클라이언트
LLM_PROVIDER=mock  → MockLLMClient  (기본값 — 비용 0, 결정론적)
LLM_PROVIDER=openai → OpenAIClient  (실 LLM 연결)

EMBEDDING_PROVIDER=mock  → MockEmbeddingClient (SHA256 기반 가짜 벡터)
EMBEDDING_PROVIDER=openai → OpenAIEmbeddingClient (실 임베딩 모델)
```

### MockLLMClient 동작 (`backend/app/services/llm_client.py`)
- "impact" 키워드 포함 시 → "supply disruption risk" 반환
- "fact_check" 키워드 포함 시 → `{"status": "pass"}` JSON 반환
- "summary/headline" 키워드 포함 시 → "[mock] summary" 반환
- 테스트에서 항상 동일 결과 → 회귀 테스트 안정성 보장

### MockEmbeddingClient 동작 (`backend/app/services/embedding_client.py`)
- 입력 텍스트의 SHA256 해시를 시드로 1536차원 float 배열 생성
- NaN/Inf 값 방지 처리 포함
- 의미적 유사도는 없음 — Milvus에 저장은 되지만 검색 품질은 의미 없음

---

## LangGraph 11 노드 파이프라인

### 전체 구조 (`agents/graphs/event_processing_graph.py`)

```
EventState 초기화
    │
    ▼
① source_parse       ← agents/nodes/parse_source.py       [REAL]
    │
    ▼
② normalize_event    ← agents/nodes/normalize_event.py    [REAL]
    │
    ▼
③ deduplicate_event  ← agents/nodes/deduplicate.py        [PARTIAL — mock 흔적]
    │
    ▼
④ entity_linking     ← agents/nodes/entity_linking.py     [MOCK]
    │
    ▼
⑤ theme_sector_mapping ← agents/nodes/sector_mapping.py  [MOCK]
    │
    ▼
⑥ retrieve_past_context ← agents/nodes/retrieve_context.py [REAL — Milvus 호출]
    │
    ▼
⑦ impact_analysis    ← agents/nodes/impact_analysis.py   [MOCK]
    │
    ▼
⑧ evidence_check     ← agents/nodes/evidence_check.py    [MOCK]
    │
    ▼
⑨ run_fact_check     ← agents/nodes/fact_check.py        [MOCK]
    │
    ▼
⑩ final_card_writer  ← agents/nodes/final_writer.py      [MOCK]
    │
    ▼
⑪ publish_or_hold    ← agents/nodes/publish_or_hold.py   [REAL]
    │
    ▼
FinalEventCard 반환
```

### 노드별 상세

| # | 노드명 | 함수명 | 상태 | 동작 |
|---|---|---|---|---|
| 1 | source_parse | `source_parse` | **REAL** | raw_event의 source_type·URL 파싱, 소스 메타데이터 추출 |
| 2 | normalize_event | `normalize_event` | **REAL** | 텍스트 정규화, 언어 감지, NormalizedEvent 생성 |
| 3 | deduplicate_event | `deduplicate_event` | **PARTIAL** | dedupe_key 생성. 벡터 유사도 기준 미구현 |
| 4 | entity_linking | `entity_linking` | **MOCK** | `["[mock-entity-1]", "[mock-entity-2]"]` 고정 반환 |
| 5 | theme_sector_mapping | `theme_sector_mapping` | **MOCK** | 키워드 매칭으로 단순 theme/sector 분류 |
| 6 | retrieve_past_context | `retrieve_past_context` | **REAL** | Milvus top-k 검색으로 과거 유사 사건 반환 |
| 7 | impact_analysis | `impact_analysis` | **MOCK** | LLMClient.complete() 호출 (MockLLMClient 사용 시 템플릿 반환) |
| 8 | evidence_check | `evidence_check` | **MOCK** | 근거 URL 목록 반환 (현재 빈 목록) |
| 9 | run_fact_check | `fact_check` | **MOCK** | LLMClient.complete_json() 호출 → "pass" 고정 |
| 10 | final_card_writer | `final_card_writer` | **MOCK** | FinalEventCard 구성 (headline·summary mock 값) |
| 11 | publish_or_hold | `publish_or_hold` | **REAL** | fact_check 결과에 따라 status="published" 또는 "held" 결정 |

### EventState 구조 (`agents/state/event_state.py`)
```python
class EventState(TypedDict):
    raw: RawEvent
    raw_event_id: str
    normalized: NormalizedEvent | None
    dedupe_key: str | None
    entities: list[str]
    theme: str
    sectors: list[str]
    past_context: list[dict]
    impact: str
    evidence: list[str]
    fact_check: str
    final_card: FinalEventCard | None
    status: str
    llm_provider: str
    llm_errors: list[str]
    prompt_versions: dict[str, str]
    model_used: str | None
```

---

## Agents Tools

### `agents/tools/vector_search.py`
- Milvus 컬렉션에서 top-k 유사 벡터 검색
- `retrieve_past_context` 노드에서 호출
- 현재 MockEmbeddingClient 사용 → 검색 결과의 의미적 정확도 없음

### `agents/tools/llm.py`
- LLMClient 인스턴스 관리 (싱글톤 패턴)
- 노드들이 공유하는 LLM 호출 도구

---

## Prompt 자산 (`agents/prompts/`)

현재 상태: Python 패키지(`__init__.py`)와 초안 템플릿 파일 존재.

| 파일 | 용도 | 코드 통합 상태 |
|---|---|---|
| `impact_analysis.md` | 영향 분석 프롬프트 초안 | 미통합 (STEP 014 예정) |
| `fact_check.md` | 팩트체크 프롬프트 초안 | 미통합 |
| `summarize_event.md` | 사건 요약 프롬프트 초안 | 미통합 |
| `final_card_writer.md` | 최종 카드 작성 프롬프트 초안 | 미통합 |

→ 프롬프트 자산 코드 통합: STEP 014 예정

---

## Milvus vs OpenSearch — 왜 둘 다 필요한가

| 특성 | Milvus | OpenSearch |
|---|---|---|
| 검색 방식 | 벡터 유사도 (코사인·L2) | 키워드 BM25 |
| 강점 | "의미적으로 비슷한" 사건 찾기 | 정확한 단어 포함 검색 |
| 약점 | 정확한 단어 매칭 불가 | 동의어·유사표현 놓침 |
| 현재 상태 | REAL (mock 임베딩) | REAL (실동작) |
| 검색 기능 | agents의 RAG 컨텍스트 검색 | FastAPI /api/events/search |
| 사용 경로 | `agents/tools/vector_search.py` | `backend/app/services/search_service.py` |

### try_index_card swallow 정책
색인 실패가 `event_cards` 저장을 방해하지 않도록:
```python
def try_index_card(card: FinalEventCard) -> None:
    try:
        _index_card(card)
    except Exception as e:
        logger.warning("index failed: %s", e)  # 삼키고 계속
```

---

## 현재 검색 흐름 (GET /api/events/search)

```
q="러시아 원유" (키워드 검색)
    │
    ▼
search_service.search_event_cards()
    │
    ▼
OpenSearch multi_match 쿼리
  fields: [title, headline, summary, entities, theme, sectors]
  + bool filter: theme, sector, status
    │
    ▼
EventSearchResponse (hits + total)
```

Hybrid search(OpenSearch BM25 + Milvus rerank) → STEP 012 예정.

---

## LangSmith 관측 (`backend/app/core/observability.py`)

```python
# LANGSMITH_TRACING=true 설정 시
# LangGraph 각 노드의 입출력·토큰 사용량·오류가 LangSmith에 자동 기록됨
```

`.env`에 `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` 설정 필요.  
미설정 시 trace 없이 정상 실행됨.

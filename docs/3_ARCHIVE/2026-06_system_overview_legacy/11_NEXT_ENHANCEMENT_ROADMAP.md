> **Status: SUPERSEDED (부분)**
> Canonical replacement: `docs/_CANONICAL/07_ENHANCEMENT_BACKLOG.md`, `docs/_CANONICAL/03_SOURCE_STATUS.md`
> Reason: Axis B(소스 확장)·Axis C(본문 추출)는 `ingestion/` 엔진이 이미 구현(06 C-3). Axis A/D만 유효 → 07로 이관.

# 다음 단계 고도화 로드맵

> 4대 고도화 축이 현재 코드 구조 어디에 붙는지 파일 경로 단위로 설명합니다.

---

## 4대 고도화 축 개요

| 축 | 주제 | 핵심 목표 | 예상 STEP |
|---|---|---|---|
| A | Dense / Graph / KG-RAG | 과거 사건 의미 검색 + 관계망 기반 맥락 | STEP 012~ |
| B | 다수 API 수집 확장 | DART·SEC·정부 OpenAPI 등 소스 추가 | STEP 013 |
| C | 웹 본문 전처리 | RSS summary → 실제 기사 본문 추출 | STEP 013 |
| D | Agent Framework Loop 고도화 | LangGraph 선형 → 조건 분기·sub-graph·재처리 | STEP 014 |

---

## 축 A — Dense / Graph / KG-RAG

### 현재 상태
```
agents/tools/vector_search.py  → Milvus top-k 단순 검색
agents/nodes/retrieve_context.py → top-k 결과를 EventState.past_context에 저장
backend/app/services/vector_index_service.py → MockEmbeddingClient (가짜 벡터)
backend/app/services/embedding_client.py → MockEmbeddingClient (기본값)
```

### Dense RAG 강화 (다음 1단계)

**Step A-1**: 실 임베딩 모델 연결
```
파일: backend/app/services/embedding_client.py
변경: MockEmbeddingClient → OpenAIEmbeddingClient
트리거: EMBEDDING_PROVIDER=openai 환경변수
```

**Step A-2**: retrieve_context에 reranker 추가
```
파일: agents/nodes/retrieve_context.py
변경: top-k 반환 후 cross-encoder reranker로 재정렬
신규: agents/tools/reranker.py
```

**Step A-3**: Hybrid search 통합
```
파일: backend/app/services/search_service.py
변경: OpenSearch keyword 결과 + Milvus vector 결과 병합 (RRF 또는 linear combination)
참고: docs/RAG_VECTOR_DESIGN.md
```

### Graph / KG-RAG (다음 3단계)

```
신규 모듈: agents/graph_store/
  ├── entity_graph.py    ← 엔티티 간 관계(인수·제재·협력) 저장
  ├── event_timeline.py  ← 시간축 기반 사건 연결
  └── kg_search.py       ← 엔티티 관계 그래프 탐색
```

연결 지점:
- `agents/nodes/entity_linking.py` → 엔티티 추출 후 graph_store에 관계 저장
- `agents/nodes/retrieve_context.py` → Milvus top-k + KG traversal 결합

과거 사건 연결 근거: `event_cards.created_at` + `event_cards.entities` JSONB overlap 기반

---

## 축 B — 다수 API 수집 확장

### 현재 상태
```
workers/collectors/sources.py  → DEFAULT_SOURCES (RSS 3개)
workers/collectors/rss_collector.py → RSS 전용 수집기
```

### 신규 Collector 추가 방법 (다음 1단계)

모든 수집기의 **출구는 동일**: `raw_event_service.create_raw_event()` → `stream:raw_events`

```
workers/collectors/
├── rss_collector.py        ← REAL (기존)
├── dart_collector.py       ← TODO: 한국 DART 공시 API
├── sec_collector.py        ← TODO: 미국 SEC EDGAR API
└── gov_collector.py        ← TODO: 정부 OpenAPI
```

각 신규 collector 구현 체크리스트:
1. `sources.py`에 새 소스 타입 추가
2. `{name}_collector.py` 작성 — `run()` 함수, `RawEventCreate` 반환
3. `raw_event_service.create_raw_event()` 호출 (공통 입구)
4. `queue/producer.py`로 `stream:raw_events` 발행 (자동)
5. 하위 파이프라인(ingest, agent, publish) 변경 불필요

한국어 공시 처리 시 추가 작업:
- OpenSearch nori analyzer 설정 (`opensearch_index_service.py` 인덱스 매핑 변경)
- `alembic/versions/0005_dart_source_meta.py` 마이그레이션 (source 메타 컬럼 추가)

---

## 축 C — 웹 본문 전처리

### 현재 상태
```
workers/pipelines/ingest_pipeline.py → RSS summary 텍스트만 사용 (본문 URL만 저장)
raw_events.raw_text → RSS <description> 또는 <summary> (수백 자 수준)
```

### 본문 전처리 추가 (다음 1단계)

**연결 위치**: `workers/pipelines/ingest_pipeline.py` — normalize() 함수에 본문 추출 단계 삽입

```python
# ingest_pipeline.py 수정 예시
from trafilatura import fetch_url, extract

def normalize(raw_event: RawEventRecord) -> NormalizedEvent:
    body_text = None
    if raw_event.source_url:
        html = fetch_url(raw_event.source_url)
        body_text = extract(html)  # 광고·메뉴 제거, 본문만 추출
    return NormalizedEvent(..., body_text=body_text or raw_event.raw_text)
```

**DB 변경**: `raw_events.body_text` 컬럼 추가
```
backend/alembic/versions/0004_body_text.py  (신규)
```

**저작권 경계**: `docs/DATA_POLICY.md` 정책 준수 필수
- 전문 저장 금지 소스 목록 관리
- 요약·인용 범위 제한

---

## 축 D — Agent Framework Loop 고도화

### 현재 상태
```
agents/graphs/event_processing_graph.py  → 선형 11 노드, 조건 분기 없음
agents/nodes/                            → 11개 노드 (mock 6 포함)
agents/tools/                            → llm.py, vector_search.py
```

### LangGraph 구조 고도화 (다음 1단계)

**조건 분기 추가**:
```python
# event_processing_graph.py 수정 예시
g.add_conditional_edges(
    "deduplicate_event",
    lambda state: "skip" if state["is_duplicate"] else "continue",
    {"skip": "publish_or_hold", "continue": "entity_linking"}
)
```

**실패 재처리 loop** (다음 2단계):
- 현재: 실패 시 `reconciler_service.py`에서 외부 API로 재처리
- 고도화: LangGraph 내부에 retry/fallback 엣지 추가

```python
g.add_conditional_edges(
    "impact_analysis",
    lambda s: "retry" if s["llm_errors"] else "next",
    {"retry": "impact_analysis", "next": "evidence_check"}
)
```

**Sub-graph 분해** (다음 3단계):
```
agents/graphs/
├── event_processing_graph.py  ← 최상위 오케스트레이터
├── collection_subgraph.py     ← 수집·정제 그룹
├── validation_subgraph.py     ← 검증·팩트체크 그룹
├── writing_subgraph.py        ← 분석·카드 작성 그룹
└── search_subgraph.py         ← RAG·컨텍스트 검색 그룹
```

**LangSmith trace 활용**:
- `observability.py`에서 이미 연결됨
- mock 노드 교체 시 노드별 실패율·응답시간·토큰 비용 추적 가능

**신규 tools 추가**:
```
agents/tools/
├── llm.py              ← 기존 (REAL)
├── vector_search.py    ← 기존 (REAL)
├── reranker.py         ← 신규 (축 A)
├── web_search.py       ← 신규 — 팩트체크용 외부 검색
└── knowledge_graph.py  ← 신규 (축 A KG-RAG)
```

---

## STEP별 예상 일정

| STEP | 내용 | 축 | 우선순위 |
|---|---|---|---|
| 012 | Hybrid search (Milvus + OpenSearch BM25 rerank) | A | HIGH |
| 013 | DART/SEC collector + 한국어 nori analyzer + 웹 본문 전처리 | B, C | HIGH |
| 014 | LangGraph mock 노드 → 실모델 + shadcn/ui + prompts 통합 | D | MED |
| 015 | RBAC / OAuth2 + 내장 scheduler + prod deploy | — | MED |

---

## 각 축별 "지금 어디까지 / 다음 1단계 / 다음 3단계"

### 축 A (Dense/Graph RAG)
- **지금**: Milvus 인프라 연결, mock 벡터로 형식만 갖춤
- **다음 1단계**: `EMBEDDING_PROVIDER=openai` 설정으로 실 임베딩 연결 (코드 변경 0)
- **다음 3단계**: reranker → hybrid search → KG-RAG

### 축 B (수집 확장)
- **지금**: RSS 3개 소스, 공통 출구 파이프라인 완성
- **다음 1단계**: `dart_collector.py` 작성 (300줄 이내, 기존 패턴 동일)
- **다음 3단계**: DART → SEC → 정부 OpenAPI → 소셜 API

### 축 C (본문 전처리)
- **지금**: RSS summary만 저장
- **다음 1단계**: `ingest_pipeline.py`에 trafilatura 5줄 추가 + 0004 마이그레이션
- **다음 3단계**: 본문 저장 → 언어 감지 → NLP 전처리 → 임베딩 품질 향상

### 축 D (Agent Loop)
- **지금**: 선형 11 노드, 실패 시 외부 reconcile
- **다음 1단계**: 조건 분기 엣지 + impact_analysis에 실 LLM 연결
- **다음 3단계**: sub-graph 분해 → 병렬 실행 → 자가 수복 loop

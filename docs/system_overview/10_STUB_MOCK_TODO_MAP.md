> **Status: SUPERSEDED**
> Canonical replacement: `docs/_CANONICAL/04_OPEN_TASKS_BY_FOLDER.md`, `docs/_CANONICAL/06_CONFLICTS_AND_SUPERSEDED.md` (C-3)
> Reason: DART/SEC/trafilatura를 TODO로 표기하나 `ingestion/sources/opendart.py`·`sec_edgar.py`·`tools/trafilatura_extractor.py`로 이미 구현됨. 다운스트림 mock 항목은 04·08 참조.

# Mock·Stub·TODO 집계표

> 시스템 내 모든 임시(mock/stub/partial/empty) 구현 및 미구현(TODO) 항목을 한 곳에 정리합니다.

---

## Mock / Stub 목록

| 위치 | 분류 | 왜 mock인가 | 교체 방법 / 예정 STEP |
|---|---|---|---|
| `backend/app/services/llm_client.py:MockLLMClient` | **mock** | 외부 API 비용 회피, 결정론적 테스트 보장 | `.env`에 `LLM_PROVIDER=openai` + `OPENAI_API_KEY` 설정 시 자동 전환 |
| `backend/app/services/embedding_client.py:MockEmbeddingClient` | **mock** | 동일 이유 | `.env`에 `EMBEDDING_PROVIDER=openai` 설정 시 전환 |
| `agents/nodes/entity_linking.py` | **mock** | NER 도메인 모델 미도입 | STEP 013 — NER 모델 통합 |
| `agents/nodes/sector_mapping.py` | **mock** | 분류기 모델 미도입, 키워드 매칭 수준 | STEP 013 — 분류 모델 통합 |
| `agents/nodes/impact_analysis.py` | **mock** | LLM 프롬프트 통합 미완 | STEP 014 — prompts/ 자산 코드 통합 |
| `agents/nodes/evidence_check.py` | **mock** | 외부 검증 소스 미통합 | STEP 014 |
| `agents/nodes/fact_check.py` | **mock** | 동일 이유, 항상 "pass" 반환 | STEP 014 |
| `agents/nodes/final_writer.py` | **mock** | headline·summary 프롬프트 미완 | STEP 014 |
| `agents/nodes/deduplicate.py` | **partial** | dedupe_key 생성됨, 벡터 유사도 기준 미정 | STEP 012 — 유사도 임계값 결정 |

---

## 미완성 (PARTIAL) 목록

| 위치 | 분류 | 현재 상태 | 교체/완성 조건 |
|---|---|---|---|
| `agents/prompts/` | **partial** | `__init__.py` + 4개 .md 초안 존재, 코드에 미통합 | STEP 014 — 노드 코드에 프롬프트 자산 연결 |
| `workers/collectors/` | **partial** | RSS 3개 소스만 실동작. DART·SEC 없음 | STEP 013 — dart_collector.py, sec_collector.py 추가 |
| `backend/app/api/themes.py` | **partial** | 스켈레톤 자료 반환 | STEP 012+ — 실제 theme 집계 로직 |
| `backend/app/api/sectors.py` | **partial** | 스켈레톤 자료 반환 | STEP 012+ |
| `backend/app/api/comments.py` | **partial** | 미완성 CRUD | 미정 |
| `backend/app/api/ai_replies.py` | **partial** | 미완성 | 미정 |

---

## 미구현 (TODO) 목록

| 항목 | 현재 대안 | 예정 STEP | 연결 파일 |
|---|---|---|---|
| DART 공시 collector | RSS만 실동작 | STEP 013 | `workers/collectors/dart_collector.py` (신규 예정) |
| SEC EDGAR collector | RSS만 실동작 | STEP 013 | `workers/collectors/sec_collector.py` (신규 예정) |
| 웹 본문 전처리 (trafilatura) | RSS summary 텍스트만 사용 | STEP 013 (축 C) | `workers/pipelines/ingest_pipeline.py`에 삽입 예정 |
| Hybrid search (BM25 + Vector rerank) | OpenSearch keyword only | STEP 012 (축 A) | `backend/app/services/search_service.py` |
| Dense RAG reranker | top-k 반환만 | STEP 012 (축 A) | `agents/nodes/retrieve_context.py` |
| KG-RAG / Graph RAG | 없음 | 미정 (축 A) | 신규 `agents/graph_store/` 모듈 필요 |
| 내장 Scheduler daemon | 외부 cron / 수동 스크립트 | STEP 015 | `scripts/` → 내장 스케줄러로 변환 |
| Admin 인증 (RBAC) | bypass (빈 token = 허용) | STEP 015 | `backend/app/core/security.py` |
| OAuth2 로그인 | 없음 | STEP 015 | 신규 auth 모듈 필요 |
| 한국어 nori analyzer (OpenSearch) | 기본 분석기 | STEP 013 | `opensearch_index_service.py` 인덱스 설정 변경 |
| shadcn/ui 디자인 시스템 | 기본 Tailwind | STEP 014 | `frontend/src/components/` 전면 개편 |
| i18n (국제화) | 없음 | 미정 | frontend 전체 |
| Playwright e2e | node --test 8건 | 미정 | 신규 `e2e/` 디렉터리 |
| Production Docker 설정 | dev 설정 사용 | STEP 015 | 신규 `docker-compose.prod.yml` |
| TLS / CDN | 없음 | STEP 015+ | 운영 환경 |
| body_text 컬럼 (웹 본문 저장) | raw_text에 RSS summary만 | 축 C 시 | `alembic/versions/0004_body_text.py` (신규 예정) |
| LangGraph sub-graph 분해 | 단일 선형 11 노드 | 축 D 시 | `agents/graphs/event_processing_graph.py` 재설계 |

---

## 환경변수 교체로 즉시 전환 가능한 항목

mock → real 전환이 코드 변경 없이 환경변수만으로 가능한 항목:

| 환경변수 | 기본값 | real 전환값 | 전환 시 동작 |
|---|---|---|---|
| `LLM_PROVIDER` | `mock` | `openai` | MockLLMClient → OpenAIClient 자동 전환 |
| `EMBEDDING_PROVIDER` | `mock` | `openai` | MockEmbeddingClient → 실 임베딩 모델 자동 전환 |
| `LANGSMITH_TRACING` | (미설정) | `true` | LangGraph 실행 trace가 LangSmith에 기록됨 |
| `ADMIN_API_TOKEN` | `` (빈값) | `<토큰값>` | Admin API bypass 해제, token 검사 활성화 |

---

## agents/prompts/ 상태 상세

```
agents/prompts/
├── __init__.py             ← Python 패키지 선언
├── impact_analysis.md      ← 영향 분석 프롬프트 초안 (코드 미연결)
├── fact_check.md           ← 팩트체크 프롬프트 초안 (코드 미연결)
├── summarize_event.md      ← 요약 프롬프트 초안 (코드 미연결)
└── final_card_writer.md    ← 최종 카드 작성 프롬프트 초안 (코드 미연결)
```

→ STEP 014에서 노드 코드가 이 .md 파일을 로드해 LLMClient에 전달하도록 통합 예정

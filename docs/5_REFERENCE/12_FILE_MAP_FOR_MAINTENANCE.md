# 파일 경로 인덱스 (역할별)

> "X를 고치려면 어느 파일?"에 즉답할 수 있도록 모든 핵심 파일을 역할별로 정리합니다.

---

## 데이터 수집 레이어

| 파일 경로 | 역할 | 관련 STEP |
|---|---|---|
| `workers/collectors/rss_collector.py` | RSS 피드 수집, feedparser, content_hash 중복 제거 | STEP 003 |
| `workers/collectors/sources.py` | 수집 소스 목록 정의 (BBC, Reuters, YNA) | STEP 003 |
| `workers/collectors/__main__.py` | collector 독립 실행 진입점 | STEP 003 |
| `workers/collectors/__init__.py` | 패키지 선언 | — |

---

## 큐 레이어 (Redis Stream)

| 파일 경로 | 역할 | 관련 STEP |
|---|---|---|
| `workers/queue/producer.py` | XADD — raw_event ID를 stream:raw_events에 발행 | STEP 005 |
| `workers/queue/consumer.py` | XREADGROUP — stream 소비, heartbeat 내장 | STEP 007 |
| `workers/queue/__init__.py` | 패키지 선언 | — |

---

## 파이프라인 레이어

| 파일 경로 | 역할 | 관련 STEP |
|---|---|---|
| `workers/pipelines/ingest_pipeline.py` | raw_event 정규화, stream:to_agent 발행 | STEP 006 |
| `workers/pipelines/publish_pipeline.py` | FinalEventCard를 backend API에 POST | STEP 008 |
| `workers/pipelines/__init__.py` | 패키지 선언 | — |

---

## 에이전트 레이어 (LangGraph)

| 파일 경로 | 역할 | 상태 |
|---|---|---|
| `agents/agent_worker.py` | stream:to_agent 소비, LangGraph 실행, heartbeat | REAL |
| `agents/graphs/event_processing_graph.py` | 11 노드 StateGraph 정의 + run() | REAL |
| `agents/state/event_state.py` | EventState TypedDict 정의 | REAL |
| `agents/tools/llm.py` | LLMClient 싱글톤 관리 | REAL |
| `agents/tools/vector_search.py` | Milvus top-k 검색 | REAL |

### 에이전트 노드

| 파일 경로 | 노드명 | 상태 |
|---|---|---|
| `agents/nodes/parse_source.py` | source_parse | REAL |
| `agents/nodes/normalize_event.py` | normalize_event | REAL |
| `agents/nodes/deduplicate.py` | deduplicate_event | PARTIAL |
| `agents/nodes/entity_linking.py` | entity_linking | MOCK |
| `agents/nodes/sector_mapping.py` | theme_sector_mapping | MOCK |
| `agents/nodes/retrieve_context.py` | retrieve_past_context | REAL |
| `agents/nodes/impact_analysis.py` | impact_analysis | MOCK |
| `agents/nodes/evidence_check.py` | evidence_check | MOCK |
| `agents/nodes/fact_check.py` | run_fact_check | MOCK |
| `agents/nodes/final_writer.py` | final_card_writer | MOCK |
| `agents/nodes/publish_or_hold.py` | publish_or_hold | REAL |

### 프롬프트 자산

| 파일 경로 | 역할 | 상태 |
|---|---|---|
| `agents/prompts/__init__.py` | 패키지 선언 | — |
| `agents/prompts/impact_analysis.md` | 영향 분석 프롬프트 초안 | 코드 미통합 |
| `agents/prompts/fact_check.md` | 팩트체크 프롬프트 초안 | 코드 미통합 |
| `agents/prompts/summarize_event.md` | 요약 프롬프트 초안 | 코드 미통합 |
| `agents/prompts/final_card_writer.md` | 최종 카드 작성 프롬프트 초안 | 코드 미통합 |

---

## 백엔드 API 레이어

| 파일 경로 | 역할 | 상태 |
|---|---|---|
| `backend/app/main.py` | FastAPI 앱 생성, CORS, lifespan | REAL |
| `backend/app/api/health.py` | GET /health | REAL |
| `backend/app/api/events.py` | GET /api/events, /search, /{id} | REAL |
| `backend/app/api/admin.py` | POST/GET /api/admin/** (10개 엔드포인트) | REAL |
| `backend/app/api/internal.py` | 내부 서비스 전용 API | REAL |
| `backend/app/api/themes.py` | GET /api/themes (스켈레톤) | PARTIAL |
| `backend/app/api/sectors.py` | GET /api/sectors (스켈레톤) | PARTIAL |
| `backend/app/api/comments.py` | 댓글 CRUD | PARTIAL |
| `backend/app/api/ai_replies.py` | AI 댓글 답변 | PARTIAL |

---

## 백엔드 서비스 레이어

| 파일 경로 | 역할 | 상태 |
|---|---|---|
| `backend/app/services/event_service.py` | event_cards CRUD, upsert_card | REAL |
| `backend/app/services/raw_event_service.py` | raw_events CRUD, requeue, status update | REAL |
| `backend/app/services/search_service.py` | OpenSearch multi_match 검색 | REAL |
| `backend/app/services/vector_index_service.py` | Milvus 색인 (try_index_card) | REAL |
| `backend/app/services/opensearch_index_service.py` | OpenSearch 색인 (try_index_card) | REAL |
| `backend/app/services/reconciler_service.py` | stuck raw_events 정리 | REAL |
| `backend/app/services/llm_client.py` | LLM 추상화 (MockLLMClient 기본값) | REAL (mock) |
| `backend/app/services/embedding_client.py` | 임베딩 추상화 (MockEmbeddingClient 기본값) | REAL (mock) |
| `backend/app/services/comment_service.py` | 댓글 서비스 | PARTIAL |

---

## 데이터베이스 레이어

| 파일 경로 | 역할 | 연결 DB |
|---|---|---|
| `backend/app/db/postgres.py` | PostgreSQL AsyncSession 팩토리 | PostgreSQL |
| `backend/app/db/redis.py` | Redis 연결, get_redis() | Redis |
| `backend/app/db/milvus.py` | Milvus 연결, 컬렉션 관리 | Milvus |
| `backend/app/db/opensearch.py` | OpenSearch 클라이언트 | OpenSearch |

---

## 모델 / 스키마 레이어

| 파일 경로 | 역할 |
|---|---|
| `backend/app/models/raw_event.py` | raw_events SQLAlchemy 모델 |
| `backend/app/models/event.py` | event_cards SQLAlchemy 모델 |
| `backend/app/models/comment.py` | comments SQLAlchemy 모델 |
| `backend/app/models/base.py` | 공통 Base 클래스 |
| `backend/app/schemas/events.py` | RawEvent, FinalEventCard, EventSearchResponse Pydantic 스키마 |
| `backend/app/schemas/raw_events.py` | RawEventCreate, RawEventRecord 등 |
| `backend/app/schemas/comments.py` | 댓글 스키마 |
| `backend/app/schemas/vector.py` | 벡터 관련 스키마 |

---

## Core / 설정 레이어

| 파일 경로 | 역할 |
|---|---|
| `backend/app/core/config.py` | pydantic-settings 기반 환경변수 파싱 |
| `backend/app/core/security.py` | Admin token 검사 |
| `backend/app/core/observability.py` | LangSmith 연결 |
| `backend/app/core/logging.py` | structlog 설정 |

---

## Alembic 마이그레이션

| 파일 경로 | 내용 |
|---|---|
| `backend/alembic/versions/0001_initial.py` | event_cards 테이블 생성 |
| `backend/alembic/versions/0002_raw_events.py` | raw_events 테이블 추가 |
| `backend/alembic/versions/0003_raw_events_event_card_link.py` | raw_events.event_card_id FK 추가 |

---

## 프론트엔드 레이어

| 파일 경로 | 역할 |
|---|---|
| `frontend/src/app/layout.tsx` | 전체 레이아웃 |
| `frontend/src/app/page.tsx` | 홈 페이지 |
| `frontend/src/app/events/page.tsx` | 이벤트 목록 |
| `frontend/src/app/events/[id]/page.tsx` | 이벤트 상세 |
| `frontend/src/app/search/page.tsx` | 검색 |
| `frontend/src/app/admin/page.tsx` | Admin 패널 |
| `frontend/src/app/api/health/route.ts` | 헬스 체크 proxy |
| `frontend/src/app/api/admin/reindex/route.ts` | 재색인 proxy |
| `frontend/src/app/api/admin/reconcile/route.ts` | reconcile proxy |
| `frontend/src/app/api/admin/requeue/[id]/route.ts` | requeue proxy |
| `frontend/src/components/EventCard.tsx` | 이벤트 카드 컴포넌트 |
| `frontend/src/components/EventList.tsx` | 이벤트 목록 컴포넌트 |
| `frontend/src/components/AdminPanel.tsx` | 관리 패널 컴포넌트 |
| `frontend/src/lib/config.ts` | 프론트엔드 환경설정 |
| `frontend/src/lib/api/types.ts` | 공유 타입 정의 |
| `frontend/src/lib/api/client.ts` | 브라우저 API 클라이언트 |
| `frontend/src/lib/api/server.ts` | 서버 전용 API 클라이언트 (server-only) |

---

## 인프라 / 운영 파일

| 파일 경로 | 역할 |
|---|---|
| `docker-compose.dev.yml` | 10개 서비스 정의 (개발 환경) |
| `backend/Dockerfile` | backend 이미지 빌드 |
| `backend/entrypoint.sh` | alembic upgrade head → uvicorn 시작 |
| `workers/Dockerfile` | worker 이미지 빌드 |
| `agents/Dockerfile` | agent-worker 이미지 빌드 |
| `frontend/Dockerfile` | Next.js standalone 멀티스테이지 빌드 |
| `.env` | 환경변수 (실값, 비커밋) |
| `.env.example` | 환경변수 템플릿 (커밋 가능) |

---

## 운영 스크립트

| 파일 경로 | 역할 |
|---|---|
| `scripts/reconcile_stuck_once.py` | stuck raw_events 1회 정리 (외부 cron에서 호출) |
| `scripts/reindex_opensearch_once.py` | OpenSearch 전체 재색인 1회 |

---

## 테스트 파일

| 경로 | 내용 | 수량 |
|---|---|---|
| `backend/tests/` | FastAPI 엔드포인트·서비스·DB 단위 테스트 | ~50건 |
| `agents/tests/` | LangGraph 노드·그래프 테스트 | ~22건 |
| `workers/tests/test_rss_collector.py` | RSS 수집기 테스트 | — |
| `workers/tests/test_stream_payload_compat.py` | Stream 메시지 호환성 테스트 | — |
| `frontend/src/lib/__tests__/client.test.mjs` | API client 테스트 | 3건 |
| `frontend/src/lib/__tests__/proxy.test.mjs` | Route Handler proxy 테스트 | 5건 |
| `tests/smoke/` | 전체 파이프라인 연동 smoke 테스트 | 8건 |

---

## 기존 설계 문서 (`docs/`)

| 파일 경로 | 내용 |
|---|---|
| `docs/ARCHITECTURE.md` | 전체 아키텍처 설계 |
| `docs/API_CONTRACT.md` | API 계약 명세 |
| `docs/TRD.md` | 기술 요구사항 문서 |
| `docs/EVENT_SCHEMA.md` | 이벤트 데이터 스키마 |
| `docs/COLLECTOR_DESIGN.md` | 수집기 설계 |
| `docs/LLM_AGENT_DESIGN.md` | LLM 에이전트 설계 |
| `docs/AGENT_WORKFLOW.md` | 에이전트 워크플로우 |
| `docs/RAG_VECTOR_DESIGN.md` | RAG·벡터 검색 설계 |
| `docs/SEARCH_DESIGN.md` | 검색 설계 |
| `docs/FRONTEND_DESIGN.md` | 프론트엔드 설계 |
| `docs/DEPLOYMENT.md` | 배포 절차 |
| `docs/OBSERVABILITY.md` | 관측성 설계 |
| `docs/DATA_POLICY.md` | 데이터 저작권 정책 |
| `docs/COMPLIANCE_BOUNDARY.md` | 컴플라이언스 경계 |
| `docs/COMPATIBILITY_NOTES.md` | 호환성 메모 |
| `docs/PROMPT_EXPERIMENT_GUIDE.md` | 프롬프트 실험 가이드 |
| `docs/SKELETON_COMPLETION_CHECKLIST.md` | 스켈레톤 완료 체크리스트 |
| `docs/system_overview/` | **이 문서 묶음** — 전체 통합 명세서 |

# 핵심 용어 사전 (60+ 항목)

> 모든 항목은 **한 줄 설명 → 왜 필요한가 → 비유 → 현재 repo에서의 역할 → 관련 파일 → 아직 부족한 점** 순서로 설명합니다.

---

## 카테고리 1 — 서비스/제품 개념

### Event Intelligence (이벤트 인텔리전스)
**한 줄 설명**: 전세계 뉴스·공시 등에서 사건 정보를 자동 수집·분석해 제공하는 서비스  
**왜 필요한가**: 수동으로 전 세계 소스를 모니터링하기 불가능하므로, 자동화된 수집·분석 파이프라인이 필요  
**비유**: 전 세계 기자 수천 명의 기사를 실시간으로 받아서 편집부가 요약해주는 글로벌 뉴스룸  
**현재 repo에서의 역할**: 이 프로젝트 전체의 목적  
**관련 파일**: `docker-compose.dev.yml`, `backend/app/main.py`  
**아직 부족한 점**: RSS 3개 소스만 실동작. DART·SEC·SNS 미구현

---

### raw_event (원시 이벤트)
**한 줄 설명**: 수집 직후 아직 AI 분석이 되지 않은 원본 데이터 단위  
**왜 필요한가**: 분석 전/후를 분리해서 재처리(retry)가 가능하게 하기 위해  
**비유**: 편집부에 도착한 원고 — 아직 교열·검토 전  
**현재 repo에서의 역할**: `raw_events` PostgreSQL 테이블에 저장, `status` 컬럼으로 처리 상태 추적  
**관련 파일**: `backend/app/models/raw_event.py`, `backend/app/services/raw_event_service.py`  
**아직 부족한 점**: 본문(body_text) 전문 저장 미구현 — 현재 RSS summary만

---

### event_card (사건 카드 / FinalEventCard)
**한 줄 설명**: AI 분석을 마치고 화면에 표시 가능한 최종 사건 정보 객체  
**왜 필요한가**: 사용자에게 보여줄 수 있는 구조화된 형태로 정제된 정보  
**비유**: 편집·교열·팩트체크가 완료된 최종 인쇄 기사  
**현재 repo에서의 역할**: `event_cards` PostgreSQL 테이블 + Milvus 벡터 + OpenSearch 문서  
**관련 파일**: `backend/app/schemas/events.py`, `backend/app/services/event_service.py`  
**아직 부족한 점**: AI 분석 필드(impact, headline) 대부분이 mock 값

---

### Ingest Pipeline (수집 파이프라인)
**한 줄 설명**: raw_event를 읽어 정규화한 뒤 agent에게 전달하는 처리 흐름  
**왜 필요한가**: 다양한 소스 형식을 통일된 스키마로 변환해야 함  
**비유**: 외국 통신사 기사를 한국어로 번역·표준화하는 번역팀  
**현재 repo에서의 역할**: `workers/pipelines/ingest_pipeline.py`에서 정규화 수행  
**관련 파일**: `workers/pipelines/ingest_pipeline.py`  
**아직 부족한 점**: 웹 본문 전처리(trafilatura) 미연결

---

### Publish Pipeline (발행 파이프라인)
**한 줄 설명**: LangGraph가 완성한 FinalEventCard를 backend API에 저장 요청하는 흐름  
**왜 필요한가**: agent-worker와 backend를 HTTP로 분리해 독립 확장 가능하게  
**비유**: 기자가 완성 기사를 편집시스템에 제출하는 행위  
**현재 repo에서의 역할**: `workers/pipelines/publish_pipeline.py` → POST `/api/admin/upsert-event`  
**관련 파일**: `workers/pipelines/publish_pipeline.py`  
**아직 부족한 점**: 발행 실패 시 재시도 큐 부재

---

## 카테고리 2 — 백엔드

### FastAPI
**한 줄 설명**: Python으로 REST API를 빠르게 만들 수 있는 웹 프레임워크  
**왜 필요한가**: 빠른 개발 속도, 자동 문서화(Swagger), 비동기 처리 지원  
**비유**: 식당의 주방 창구 — 손님(프론트엔드) 주문을 받아 주방(서비스 레이어)에 전달  
**현재 repo에서의 역할**: 모든 API 엔드포인트 제공, 포트 8000  
**관련 파일**: `backend/app/main.py`, `backend/app/api/`  
**아직 부족한 점**: 인증(auth) 미완성 — Admin token 검사가 dev 모드 bypass 상태

---

### SQLAlchemy (ORM)
**한 줄 설명**: Python 객체와 PostgreSQL 테이블을 연결해주는 라이브러리  
**왜 필요한가**: SQL 직접 작성 없이 Python 코드로 DB 조작 가능  
**비유**: 창고 관리 시스템 — 실제 창고(DB) 구조를 몰라도 물건 입출고 가능  
**현재 repo에서의 역할**: `backend/app/models/`에서 테이블 정의, 비동기(async) 모드  
**관련 파일**: `backend/app/models/`, `backend/app/db/postgres.py`  
**아직 부족한 점**: -

---

### Alembic (DB 마이그레이션)
**한 줄 설명**: DB 스키마 변경 이력을 버전으로 관리하는 도구  
**왜 필요한가**: 팀원 모두가 동일한 DB 구조를 유지하고 롤백도 가능하게  
**비유**: 건물 설계 도면 개정 이력 관리 — v1.0 → v1.1 → v2.0  
**현재 repo에서의 역할**: 컨테이너 시작 시 `entrypoint.sh`에서 `alembic upgrade head` 자동 실행  
**관련 파일**: `backend/alembic/versions/0001_initial.py`, `0002_raw_events.py`, `0003_raw_events_event_card_link.py`  
**아직 부족한 점**: 3개 마이그레이션만 존재. body_text 컬럼 추가 시 0004 필요

---

### Pydantic
**한 줄 설명**: Python 데이터 유효성 검사 라이브러리  
**왜 필요한가**: API 요청/응답 스키마를 선언적으로 정의하고 자동 검증  
**비유**: 주문서 양식 — 빠진 항목이 있으면 즉시 오류 반환  
**현재 repo에서의 역할**: `backend/app/schemas/`에서 모든 API 데이터 모델 정의  
**관련 파일**: `backend/app/schemas/events.py`, `schemas/raw_events.py`  
**아직 부족한 점**: -

---

### CORS (Cross-Origin Resource Sharing)
**한 줄 설명**: 다른 도메인/포트에서 오는 HTTP 요청을 허용하는 보안 정책  
**왜 필요한가**: 프론트엔드(3000)가 백엔드(8000)를 호출할 때 브라우저가 차단하지 않도록  
**비유**: 건물 출입증 — "3000번 건물 직원이 8000번 건물에 방문해도 됩니다"  
**현재 repo에서의 역할**: `backend/app/main.py`에서 `CORS_ALLOW_ORIGINS` 환경변수로 설정  
**관련 파일**: `backend/app/main.py`, `backend/app/core/config.py`  
**아직 부족한 점**: 운영 환경에서 정확한 도메인 화이트리스트 설정 필요

---

### X-Admin-Token (관리자 인증 토큰)
**한 줄 설명**: Admin API 엔드포인트 접근에 사용하는 HTTP 헤더 기반 인증 값  
**왜 필요한가**: 관리 기능(재색인·재처리 등)에 인가되지 않은 접근 차단  
**비유**: 편집장 사무실 열쇠 — 일반 직원은 들어갈 수 없음  
**현재 repo에서의 역할**: `backend/app/core/security.py`에 검사 로직. **현재 dev 모드에서 bypass**  
**관련 파일**: `backend/app/core/security.py`, `frontend/src/lib/api/server.ts`  
**아직 부족한 점**: 운영 모드에서 `ADMIN_API_TOKEN` 필수 설정 필요. RBAC 미구현

---

### healthcheck (헬스체크)
**한 줄 설명**: 컨테이너가 정상 동작 중인지 주기적으로 확인하는 메커니즘  
**왜 필요한가**: 비정상 컨테이너를 자동 감지하고 의존 서비스 시작을 안전하게 조율  
**비유**: 직원 출근 확인 — 매 N분마다 "살아있나요?" 확인  
**현재 repo에서의 역할**: `docker-compose.dev.yml`의 모든 10개 서비스에 정의됨  
**관련 파일**: `docker-compose.dev.yml`  
**아직 부족한 점**: worker/agent-worker는 heartbeat 파일 방식 (프로세스 직접 체크 아님)

---

### Admin auth (관리자 인증)
**한 줄 설명**: Admin API 및 관리 화면 접근을 제한하는 인증·인가 체계  
**왜 필요한가**: 재색인·강제 발행 등 파괴적 작업에 무단 접근 방지  
**비유**: 서버실 출입 카드 시스템  
**현재 repo에서의 역할**: **bypass 상태** — `ADMIN_API_TOKEN` 빈값이면 모든 Admin API 허용  
**관련 파일**: `backend/app/core/security.py`, `frontend/src/app/api/admin/`  
**아직 부족한 점**: RBAC·OAuth 미구현 (STEP 015 예정)

---

## 카테고리 3 — 큐/작업 처리

### Redis
**한 줄 설명**: 메모리에서 동작하는 초고속 키-값 저장소 (캐시 + 메시지 큐)  
**왜 필요한가**: 수집된 이벤트를 순서대로 처리하기 위한 대기열(queue) + 빠른 임시 저장  
**비유**: 번호표 발급기 + 대기실 — 번호표를 뽑고 차례가 될 때까지 기다림  
**현재 repo에서의 역할**: Redis Stream 두 개(`stream:raw_events`, `stream:to_agent`)로 워커 간 메시지 전달  
**관련 파일**: `backend/app/db/redis.py`, `workers/queue/producer.py`, `workers/queue/consumer.py`  
**아직 부족한 점**: 키 만료·메모리 상한 정책 미설정

---

### Redis Stream
**한 줄 설명**: Redis의 로그 스트림 자료구조 — 순서가 보장된 메시지 큐  
**왜 필요한가**: 메시지 유실 없이 워커들이 순서대로 안전하게 처리할 수 있게  
**비유**: 조립 라인의 컨베이어 벨트 — 부품이 순서대로 흘러감  
**현재 repo에서의 역할**: `stream:raw_events`(수집→워커), `stream:to_agent`(워커→에이전트) 두 채널  
**관련 파일**: `workers/queue/producer.py` (XADD), `workers/queue/consumer.py` (XREADGROUP)  
**아직 부족한 점**: 스트림 최대 길이(MAXLEN) 정책 미설정

---

### XADD / XREADGROUP / ACK
**한 줄 설명**: Redis Stream의 핵심 명령어 — 메시지 추가 / 그룹 소비 / 처리 완료 확인  
**왜 필요한가**: 메시지가 처리됐다는 확인(ACK) 없으면 재전달됨 → 유실 방지  
**비유**: 택배 수령 서명 — 서명 전까지는 "미배달" 상태 유지  
**현재 repo에서의 역할**: producer.py에서 XADD, consumer.py에서 XREADGROUP + XACK  
**관련 파일**: `workers/queue/producer.py`, `workers/queue/consumer.py`  
**아직 부족한 점**: -

---

### PEL (Pending Entry List)
**한 줄 설명**: Redis Stream에서 소비됐지만 ACK가 오지 않은 메시지 목록  
**왜 필요한가**: 처리 중 크래시 발생 시 재처리할 메시지를 추적하기 위해  
**비유**: 택배기사가 배달 시도했지만 수령 확인이 안 된 목록  
**현재 repo에서의 역할**: `consumer.py`에서 주기적으로 PEL 확인 및 재처리  
**관련 파일**: `workers/queue/consumer.py`  
**아직 부족한 점**: 재처리 최대 횟수(max_delivery) 정책 미구현

---

### Consumer Group (컨슈머 그룹)
**한 줄 설명**: Redis Stream에서 여러 소비자가 메시지를 분산 처리하는 그룹 구조  
**왜 필요한가**: 워커를 여러 개 띄울 때 같은 메시지를 중복 처리하지 않도록  
**비유**: 콜센터 상담사 여러 명이 하나의 대기열을 나눠 처리  
**현재 repo에서의 역할**: `consumer.py`에서 `XREADGROUP GROUP worker_group` 사용  
**관련 파일**: `workers/queue/consumer.py`  
**아직 부족한 점**: 현재 단일 워커만 실행 — 수평 확장 시 그룹명 관리 필요

---

### worker (워커 컨테이너)
**한 줄 설명**: RSS 수집과 ingest pipeline 실행을 담당하는 백그라운드 프로세스  
**왜 필요한가**: API 서버와 분리해 수집·처리 부하가 API 응답에 영향 안 주도록  
**비유**: 신문사의 인쇄소 — 편집부(API)와 분리된 생산 설비  
**현재 repo에서의 역할**: `ei-worker` 컨테이너, `workers/collectors/` + `workers/queue/consumer.py`  
**관련 파일**: `workers/Dockerfile`, `workers/collectors/rss_collector.py`, `workers/queue/consumer.py`  
**아직 부족한 점**: DART·SEC collector 미구현

---

### agent-worker (에이전트 워커 컨테이너)
**한 줄 설명**: LangGraph AI 파이프라인을 실행하는 전용 백그라운드 프로세스  
**왜 필요한가**: LLM 호출 등 느린 AI 처리를 API·수집과 완전히 분리  
**비유**: 신문사의 편집팀 — 원고 받아서 AI가 분석하고 기사 완성  
**현재 repo에서의 역할**: `ei-agent-worker` 컨테이너, `agents/agent_worker.py` 실행  
**관련 파일**: `agents/Dockerfile`, `agents/agent_worker.py`  
**아직 부족한 점**: LangGraph mock 6노드 — 실 LLM 미연결

---

### heartbeat (하트비트)
**한 줄 설명**: 프로세스가 살아있음을 주기적으로 파일에 기록하는 건강 신호  
**왜 필요한가**: 컨테이너 healthcheck가 "파일 최근 수정 시각"을 체크  
**비유**: 맥박 모니터 — 1분 이상 신호가 없으면 이상 감지  
**현재 repo에서의 역할**: `/tmp/worker_heartbeat`, `/tmp/agent_heartbeat` 파일 60초 이내 갱신  
**관련 파일**: `workers/queue/consumer.py`, `agents/agent_worker.py`, `docker-compose.dev.yml`  
**아직 부족한 점**: -

---

### reconciler (조정자)
**한 줄 설명**: 오랫동안 처리되지 않고 stuck 상태인 raw_event를 failed로 정리하는 서비스  
**왜 필요한가**: 처리 중 크래시로 영원히 pending/processing 상태가 되는 데이터 방지  
**비유**: 미결 서류함 정리 담당자 — N일 이상 방치된 서류는 반려 처리  
**현재 repo에서의 역할**: `backend/app/services/reconciler_service.py` + Admin API `/raw-events/reconcile-stuck`  
**관련 파일**: `backend/app/services/reconciler_service.py`, `scripts/reconcile_stuck_once.py`  
**아직 부족한 점**: 자동 주기 실행 없음 — 외부 cron 또는 수동 API 호출 필요

---

### scheduler (스케줄러)
**한 줄 설명**: 정해진 시간 간격으로 작업(수집·reconcile 등)을 자동 실행하는 데몬  
**왜 필요한가**: 사람이 직접 매번 API 호출 없이 자동으로 주기 작업 실행  
**비유**: 알람 시계 — 매 5분마다 RSS 체크, 매 시간마다 reconcile  
**현재 repo에서의 역할**: **별도 daemon 미구현** — 외부 cron 또는 k8s CronJob 가정  
**관련 파일**: `scripts/reconcile_stuck_once.py`, `scripts/reindex_opensearch_once.py`  
**아직 부족한 점**: 내장 스케줄러 없음 (STEP 015 운영 진입 시 예정)

---

### producer (프로듀서)
**한 줄 설명**: Redis Stream에 메시지를 발행(추가)하는 역할  
**왜 필요한가**: 처리할 이벤트를 대기열에 넣는 첫 번째 단계  
**현재 repo에서의 역할**: `workers/queue/producer.py`, `raw_event_service.create_raw_event()` 내부에서 호출  
**관련 파일**: `workers/queue/producer.py`  
**아직 부족한 점**: -

---

### consumer (컨슈머)
**한 줄 설명**: Redis Stream에서 메시지를 읽어 실제 처리를 수행하는 역할  
**왜 필요한가**: 대기열에서 순서대로 꺼내 처리  
**현재 repo에서의 역할**: `workers/queue/consumer.py` — 두 개 Stream에서 메시지 소비  
**관련 파일**: `workers/queue/consumer.py`  
**아직 부족한 점**: -

---

## 카테고리 4 — AI / Agent

### LangGraph
**한 줄 설명**: LLM 기반 AI 작업 흐름을 상태 그래프로 정의하는 Python 프레임워크  
**왜 필요한가**: 복잡한 다단계 AI 처리(11 노드)를 명확한 흐름으로 관리  
**비유**: 공장 조립 라인 도면 — 각 작업 스테이션을 어떤 순서로 거치는지 정의  
**현재 repo에서의 역할**: `agents/graphs/event_processing_graph.py`에서 11 노드 선형 그래프 정의  
**관련 파일**: `agents/graphs/event_processing_graph.py`  
**아직 부족한 점**: 선형 순서 고정 — 조건 분기·loop·sub-graph 없음

---

### StateGraph / EventState
**한 줄 설명**: LangGraph의 상태(State) 객체 — 노드들이 공유하는 데이터 컨테이너  
**왜 필요한가**: 11개 노드가 차례로 상태를 읽고 업데이트하며 최종 결과 도출  
**비유**: 기사 초안 파일 — 각 편집자가 자신의 항목을 채워넣음  
**현재 repo에서의 역할**: `agents/state/event_state.py`에서 TypedDict로 정의  
**관련 파일**: `agents/state/event_state.py`  
**아직 부족한 점**: -

---

### LLMClient / MockLLMClient / OpenAIClient
**한 줄 설명**: LLM(대규모 언어 모델) 호출 추상화 — 실제 OpenAI 또는 mock 선택 가능  
**왜 필요한가**: 개발·테스트 시 비용 없이 결정론적 응답, 운영 시 실 LLM 교체  
**비유**: 번역가 고용 계약 — 같은 인터페이스로 아르바이트(mock)↔전문가(OpenAI) 교체  
**현재 repo에서의 역할**: `LLM_PROVIDER=mock` 환경변수가 기본 → `MockLLMClient` 사용  
**관련 파일**: `backend/app/services/llm_client.py`  
**아직 부족한 점**: `LLM_PROVIDER=openai` 설정 + `OPENAI_API_KEY` 주입 시 실 LLM 연결

---

### EmbeddingClient / MockEmbeddingClient
**한 줄 설명**: 텍스트를 숫자 벡터로 변환하는 임베딩 모델 호출 추상화  
**왜 필요한가**: 텍스트 의미를 숫자로 표현해야 벡터 유사도 검색 가능  
**비유**: 단어의 "좌표" 계산기 — 비슷한 의미의 단어는 좌표가 가까움  
**현재 repo에서의 역할**: `EMBEDDING_PROVIDER=mock`이 기본 → SHA256 기반 결정론적 가짜 벡터 반환  
**관련 파일**: `backend/app/services/embedding_client.py`  
**아직 부족한 점**: `EMBEDDING_PROVIDER=openai` 설정 시 실 임베딩 모델 연결

---

### LangSmith
**한 줄 설명**: LangGraph 실행 추적(trace) 및 디버깅을 위한 Anthropic/LangChain 관측 서비스  
**왜 필요한가**: AI 노드별로 어떤 프롬프트가 입력되고 어떤 출력이 나왔는지 추적  
**비유**: 항공기 블랙박스 — 무슨 일이 있었는지 나중에 정확히 확인 가능  
**현재 repo에서의 역할**: `backend/app/core/observability.py`에서 `LANGSMITH_TRACING=true` 시 활성화  
**관련 파일**: `backend/app/core/observability.py`  
**아직 부족한 점**: API 키 미설정 시 trace 없음

---

### prompt (프롬프트)
**한 줄 설명**: LLM에게 주는 지시문 — "이렇게 분석해주세요"  
**왜 필요한가**: LLM의 출력 품질은 프롬프트 품질에 직접적으로 의존  
**비유**: 업무 지시서 — 애매하면 결과가 엉터리  
**현재 repo에서의 역할**: `agents/prompts/` 아래 .md 파일로 초안 존재 (impact_analysis.md, fact_check.md, summarize_event.md, final_card_writer.md) — 코드에 완전 통합 미완  
**관련 파일**: `agents/prompts/`  
**아직 부족한 점**: 프롬프트 자산 코드 통합 미완 (STEP 014 예정)

---

### entity linking (엔티티 링킹)
**한 줄 설명**: 텍스트에서 인물·기관·국가 등 고유 개체를 식별하고 연결하는 AI 기능  
**왜 필요한가**: "애플 CEO 팀 쿡"을 사람으로 인식해야 관련 사건 연결 가능  
**비유**: 기사에서 "박 대통령"을 "박근혜 대통령"으로 특정하는 작업  
**현재 repo에서의 역할**: `agents/nodes/entity_linking.py` — **mock**, `["[mock-entity-1]", "[mock-entity-2]"]` 반환  
**관련 파일**: `agents/nodes/entity_linking.py`  
**아직 부족한 점**: NER 모델 미도입 (STEP 013 예정)

---

### NER (Named Entity Recognition, 개체명 인식)
**한 줄 설명**: 텍스트에서 이름·장소·조직 등을 자동으로 찾아내는 AI 기술  
**왜 필요한가**: entity linking의 전제 — 먼저 "이게 기업명이다"를 알아야 연결 가능  
**비유**: 텍스트에서 고유명사에 형광펜 치는 작업  
**현재 repo에서의 역할**: 미구현 (entity_linking 노드에서 mock으로 대체)  
**관련 파일**: `agents/nodes/entity_linking.py`  
**아직 부족한 점**: 도메인 특화 NER 모델 필요 (STEP 013)

---

### sector mapping (섹터 매핑)
**한 줄 설명**: 사건을 에너지·금융·기술 등 산업 섹터로 자동 분류하는 기능  
**왜 필요한가**: 사용자가 "에너지 섹터 이벤트만 보기" 같은 필터링 가능하게  
**비유**: 도서관 서가 분류 — "이 책은 경제학 섹션"  
**현재 repo에서의 역할**: `agents/nodes/sector_mapping.py` — **mock**, 키워드 기반 단순 분류  
**관련 파일**: `agents/nodes/sector_mapping.py`  
**아직 부족한 점**: 실 분류 모델 미도입 (STEP 013 예정)

---

### impact analysis (영향 분석)
**한 줄 설명**: 사건이 시장·산업·사회에 미치는 영향을 LLM이 추론하는 기능  
**왜 필요한가**: 단순 뉴스 요약을 넘어 "이 사건이 왜 중요한가" 설명  
**비유**: 기업 리포트의 "영향 분석" 섹션  
**현재 repo에서의 역할**: `agents/nodes/impact_analysis.py` — **mock**, 템플릿 문자열 반환  
**관련 파일**: `agents/nodes/impact_analysis.py`, `agents/prompts/impact_analysis.md`  
**아직 부족한 점**: LLM 프롬프트 통합 미완 (STEP 014 예정)

---

### fact check (팩트체크)
**한 줄 설명**: 사건 정보의 사실 여부를 외부 소스로 검증하는 기능  
**왜 필요한가**: 오보·루머 차단, 정보 신뢰도 제고  
**비유**: 기사 게재 전 편집장 최종 검토  
**현재 repo에서의 역할**: `agents/nodes/fact_check.py` + `agents/nodes/evidence_check.py` — **mock**, 항상 "pass" 반환  
**관련 파일**: `agents/nodes/fact_check.py`, `agents/nodes/evidence_check.py`  
**아직 부족한 점**: 외부 검증 API 미통합 (STEP 014 예정)

---

## 카테고리 5 — RAG / Search

### RAG (Retrieval-Augmented Generation)
**한 줄 설명**: LLM이 답변 생성 시 관련 문서를 먼저 검색해 맥락으로 활용하는 기법  
**왜 필요한가**: LLM의 학습 데이터에 없는 최신·특수 정보를 검색으로 보완  
**비유**: 오픈북 시험 — 모든 걸 외울 필요 없이 자료집 참고 허용  
**현재 repo에서의 역할**: `agents/nodes/retrieve_context.py`에서 Milvus top-k 검색으로 과거 유사 사건 참조  
**관련 파일**: `agents/nodes/retrieve_context.py`, `agents/tools/vector_search.py`  
**아직 부족한 점**: 단순 top-k 벡터 검색만. Dense rerank·Graph RAG 미구현

---

### Dense RAG
**한 줄 설명**: 텍스트를 고밀도 벡터로 임베딩한 후 의미 유사도로 검색하는 RAG 방식  
**왜 필요한가**: "비슷한 의미"의 문서를 정확히 찾아야 좋은 맥락 제공 가능  
**비유**: 도서관에서 "비슷한 주제의 책" 추천 시스템  
**현재 repo에서의 역할**: 기반 인프라(Milvus) 존재하나 실 임베딩 모델 미연결 (MockEmbeddingClient 사용 중)  
**관련 파일**: `backend/app/services/vector_index_service.py`, `agents/tools/vector_search.py`  
**아직 부족한 점**: 실 임베딩 모델 + reranker 미구현

---

### Hybrid Search (하이브리드 검색)
**한 줄 설명**: 벡터 유사도 검색(Milvus)과 키워드 검색(OpenSearch)을 결합한 검색 방식  
**왜 필요한가**: 각각의 약점 보완 — 키워드 검색은 의미적 유사도 파악 불가, 벡터 검색은 정확한 단어 매칭 불가  
**비유**: "의미 추천 + 키워드 일치" 두 결과를 합쳐 최종 순위 결정  
**현재 repo에서의 역할**: **미구현** — 현재 OpenSearch keyword only  
**관련 파일**: `docs/RAG_VECTOR_DESIGN.md`  
**아직 부족한 점**: STEP 012 예정

---

### KG-RAG (Knowledge Graph RAG)
**한 줄 설명**: 엔티티 간 관계 그래프를 구축해 더 정확한 맥락 검색을 수행하는 고급 RAG  
**왜 필요한가**: "A 기업이 B 기업을 인수했고 B는 C의 경쟁사" 같은 관계적 맥락 파악  
**비유**: 가계도 — 단순 이름 검색이 아니라 관계를 따라 연결된 정보 탐색  
**현재 repo에서의 역할**: **미구현** — 4대 고도화 축 A  
**관련 파일**: `docs/RAG_VECTOR_DESIGN.md`  
**아직 부족한 점**: entity graph store 모듈 신규 필요

---

### Graph RAG
**한 줄 설명**: KG-RAG의 일종 — 문서들의 관계를 그래프로 모델링해 검색  
**왜 필요한가**: 시간축을 따라 연결된 사건들의 인과관계 파악 가능  
**비유**: 타임라인 + 관계망 — "이번 사건은 3개월 전 A 사건의 후속"  
**현재 repo에서의 역할**: 미구현 (4대 고도화 축 A)  
**아직 부족한 점**: -

---

### Milvus
**한 줄 설명**: 고성능 오픈소스 벡터 데이터베이스 — 수백만 개의 임베딩 벡터 검색  
**왜 필요한가**: 텍스트 의미 유사도 기반 검색을 빠르게 수행하기 위해  
**비유**: "의미적으로 비슷한 좌표" 검색에 특화된 지도 시스템  
**현재 repo에서의 역할**: `ei-milvus` 컨테이너, `event_embeddings` 컬렉션에 FinalEventCard 벡터 저장  
**관련 파일**: `backend/app/db/milvus.py`, `backend/app/services/vector_index_service.py`  
**아직 부족한 점**: 실 임베딩 미사용 (mock 벡터) — 의미 검색 품질 낮음

---

### OpenSearch
**한 줄 설명**: Elasticsearch 기반 오픈소스 검색 엔진 — 키워드·전문검색에 특화  
**왜 필요한가**: "러시아 원유"처럼 특정 단어가 포함된 문서를 빠르게 찾기 위해  
**비유**: 도서관 색인 카드 — 제목·본문에서 단어 검색  
**현재 repo에서의 역할**: `ei-opensearch` 컨테이너, `event_cards` 인덱스에 FinalEventCard 문서 저장  
**관련 파일**: `backend/app/db/opensearch.py`, `backend/app/services/opensearch_index_service.py`  
**아직 부족한 점**: 한국어 nori analyzer 미설정

---

### vector (벡터)
**한 줄 설명**: 텍스트나 이미지를 숫자 배열로 표현한 것 — 의미를 수학적으로 인코딩  
**왜 필요한가**: 컴퓨터가 텍스트의 "의미"를 비교할 수 있게 하기 위해  
**비유**: 지도 좌표 — 비슷한 의미의 단어는 비슷한 좌표에 위치  
**현재 repo에서의 역할**: `MockEmbeddingClient`가 1536차원 SHA256 기반 가짜 벡터 생성  
**관련 파일**: `backend/app/services/embedding_client.py`  
**아직 부족한 점**: 실 임베딩 모델 교체 필요

---

### embedding (임베딩)
**한 줄 설명**: 텍스트를 벡터로 변환하는 과정 또는 그 결과물  
**왜 필요한가**: 벡터 유사도 검색의 핵심 전처리 단계  
**현재 repo에서의 역할**: `EmbeddingClient.embed_text()` 호출 → Milvus에 저장  
**관련 파일**: `backend/app/services/embedding_client.py`, `backend/app/services/vector_index_service.py`  
**아직 부족한 점**: 실 임베딩 모델(text-embedding-3-small 등) 미연결

---

### index (색인)
**한 줄 설명**: 검색이 빠르게 되도록 문서 데이터를 정리해 저장하는 구조  
**왜 필요한가**: 인덱스 없이는 모든 문서를 순차 스캔해야 해서 느림  
**비유**: 책의 찾아보기(index) 페이지  
**현재 repo에서의 역할**: OpenSearch `event_cards` 인덱스 + Milvus `event_embeddings` 컬렉션  
**관련 파일**: `backend/app/services/opensearch_index_service.py`, `backend/app/services/vector_index_service.py`  
**아직 부족한 점**: -

---

### keyword search (키워드 검색)
**한 줄 설명**: 입력한 단어가 문서에 포함된 것을 찾는 전통적인 검색 방식  
**왜 필요한가**: 정확한 단어 매칭에 빠르고 직관적  
**현재 repo에서의 역할**: OpenSearch `multi_match` + `bool filter`로 구현  
**관련 파일**: `backend/app/services/search_service.py`  
**아직 부족한 점**: 한국어 형태소 분석 미지원

---

### vector search (벡터 검색)
**한 줄 설명**: 의미적으로 유사한 문서를 벡터 거리로 찾는 검색 방식  
**왜 필요한가**: "원유 가격 상승" 검색 시 "석유 비용 증가" 문서도 찾을 수 있음  
**현재 repo에서의 역할**: `agents/tools/vector_search.py`에서 Milvus top-k 검색 구현  
**관련 파일**: `agents/tools/vector_search.py`, `backend/app/db/milvus.py`  
**아직 부족한 점**: 실 임베딩 미사용으로 검색 품질 의미 없음

---

### BM25
**한 줄 설명**: OpenSearch/Elasticsearch의 기본 키워드 랭킹 알고리즘  
**왜 필요한가**: 단순 키워드 존재 여부가 아닌 빈도·문서 길이를 고려한 관련도 점수  
**현재 repo에서의 역할**: OpenSearch 기본 설정으로 자동 적용  
**관련 파일**: `backend/app/services/opensearch_index_service.py`  
**아직 부족한 점**: -

---

### rerank (재랭킹)
**한 줄 설명**: 1차 검색 결과를 더 정교한 모델로 재순위화하는 과정  
**왜 필요한가**: 초기 검색 결과의 순서가 정확하지 않을 때 보정  
**현재 repo에서의 역할**: 미구현 (STEP 012 hybrid search 시 도입 예정)  
**아직 부족한 점**: -

---

### similarity search (유사도 검색)
**한 줄 설명**: 벡터 거리(코사인·L2 등)로 가장 비슷한 문서를 찾는 검색  
**왜 필요한가**: 의미 기반 검색의 핵심 메커니즘  
**현재 repo에서의 역할**: Milvus에서 L2 또는 IP(Inner Product) 기반 top-k 반환  
**관련 파일**: `agents/tools/vector_search.py`  
**아직 부족한 점**: 실 임베딩 미적용으로 의미 있는 유사도 결과 없음

---

## 카테고리 6 — Frontend

### Next.js
**한 줄 설명**: React 기반 풀스택 웹 프레임워크 — 서버·클라이언트 렌더링 모두 지원  
**왜 필요한가**: SEO 친화적 서버사이드 렌더링 + React 컴포넌트 재사용성  
**비유**: 잡지 인쇄소이자 배포소 — 서버에서 내용을 채워 독자에게 전달  
**현재 repo에서의 역할**: `ei-frontend` 컨테이너, 포트 3000, Next.js 15.5.18  
**관련 파일**: `frontend/src/app/`, `frontend/package.json`  
**아직 부족한 점**: shadcn/ui·디자인 시스템·i18n 미구현

---

### App Router (앱 라우터)
**한 줄 설명**: Next.js 13+의 파일시스템 기반 라우팅 — `app/` 디렉터리 구조 = URL 구조  
**왜 필요한가**: 폴더 구조만으로 페이지 라우팅 자동화, 서버 컴포넌트 지원  
**비유**: 파일 탐색기 — 폴더 이름이 곧 주소  
**현재 repo에서의 역할**: `frontend/src/app/` 아래 11개 라우트 정의  
**관련 파일**: `frontend/src/app/`  
**아직 부족한 점**: -

---

### Server Component vs Client Component
**한 줄 설명**: Next.js에서 서버에서 렌더링되는 컴포넌트(default)와 브라우저에서 실행되는 컴포넌트(`"use client"`) 구분  
**왜 필요한가**: 민감한 API 키·토큰이 브라우저에 노출되지 않도록 서버에서만 처리  
**비유**: 주방(서버)에서 조리한 음식 vs 테이블(클라이언트)에서 직접 만드는 요리  
**현재 repo에서의 역할**: `frontend/src/lib/api/server.ts`는 `import "server-only"`, `X-Admin-Token` 서버에서만 주입  
**관련 파일**: `frontend/src/lib/api/server.ts`, `frontend/src/lib/api/client.ts`  
**아직 부족한 점**: -

---

### Route Handler (API Route)
**한 줄 설명**: Next.js App Router에서 백엔드 API처럼 동작하는 서버 함수  
**왜 필요한가**: 프론트엔드가 직접 백엔드 주소(포트 8000)를 노출 않고 admin token을 안전하게 전달  
**비유**: 회사 수위 — 외부 방문자를 내부로 직접 안내 안 하고 중간에서 중계  
**현재 repo에서의 역할**: `frontend/src/app/api/` 아래 health·reindex·reconcile·requeue 4개 proxy  
**관련 파일**: `frontend/src/app/api/`  
**아직 부족한 점**: -

---

### proxy (프록시)
**한 줄 설명**: 요청을 중간에서 대신 전달하는 중계 역할  
**왜 필요한가**: Admin token을 클라이언트 브라우저에 노출하지 않으면서 API 호출 가능  
**비유**: 비서 — "저 대신 전화해드리겠습니다"  
**현재 repo에서의 역할**: Next.js Route Handler가 `X-Admin-Token`을 서버에서 헤더에 추가하고 백엔드에 전달  
**관련 파일**: `frontend/src/lib/api/server.ts`, `frontend/src/app/api/admin/`  
**아직 부족한 점**: -

---

### server-only (서버 전용)
**한 줄 설명**: `import "server-only"` — 해당 모듈이 클라이언트 번들에 포함되면 빌드 에러 발생  
**왜 필요한가**: 실수로 비밀 키·내부 URL이 브라우저 JS 파일에 포함되는 것 방지  
**현재 repo에서의 역할**: `frontend/src/lib/api/server.ts` 최상단에 선언  
**관련 파일**: `frontend/src/lib/api/server.ts`  
**아직 부족한 점**: -

---

### NEXT_PUBLIC
**한 줄 설명**: Next.js에서 브라우저에 노출해도 되는 환경변수 접두사  
**왜 필요한가**: 서버 전용 변수와 명확히 구분 — `NEXT_PUBLIC_` 없는 변수는 서버에서만 접근 가능  
**현재 repo에서의 역할**: `NEXT_PUBLIC_API_BASE_URL`만 사용. Admin token 관련 변수에 `NEXT_PUBLIC_` 접두사 사용 금지  
**관련 파일**: `frontend/src/lib/config.ts`  
**아직 부족한 점**: -

---

## 카테고리 7 — Infra

### Docker
**한 줄 설명**: 애플리케이션을 컨테이너로 격리·실행하는 플랫폼  
**왜 필요한가**: "내 컴퓨터에선 됩니다" 문제 해결 — 어디서나 동일한 환경  
**비유**: 표준 규격 화물 컨테이너 — 내용물이 뭐든 크레인으로 어디든 옮길 수 있음  
**현재 repo에서의 역할**: 10개 서비스 모두 컨테이너로 실행  
**관련 파일**: `docker-compose.dev.yml`, `backend/Dockerfile`, `workers/Dockerfile`, `agents/Dockerfile`, `frontend/Dockerfile`  
**아직 부족한 점**: prod 전용 Dockerfile 미구현

---

### Docker Compose
**한 줄 설명**: 여러 Docker 컨테이너를 한 파일로 정의하고 한 번에 실행하는 도구  
**왜 필요한가**: 10개 서비스를 매번 수동으로 실행하는 것은 불가능  
**비유**: 악보 — 오케스트라 단원 10명이 무엇을, 언제, 어떻게 연주할지 한 곳에 정의  
**현재 repo에서의 역할**: `docker-compose.dev.yml`, compose project명 `event-intelligence-dev`  
**관련 파일**: `docker-compose.dev.yml`  
**아직 부족한 점**: prod 전용 compose 없음

---

### container (컨테이너)
**한 줄 설명**: Docker가 격리된 환경에서 실행하는 프로세스 단위  
**왜 필요한가**: 서비스 간 의존성 충돌 없이 각자 독립 실행  
**현재 repo에서의 역할**: 10개 컨테이너 (milvus-etcd, milvus-minio, milvus-standalone, redis, postgres, opensearch, backend, worker, agent-worker, frontend)  
**관련 파일**: `docker-compose.dev.yml`  
**아직 부족한 점**: -

---

### volume (볼륨)
**한 줄 설명**: 컨테이너가 재시작되어도 데이터가 유지되는 영속 저장소  
**왜 필요한가**: 컨테이너는 기본적으로 stateless — 데이터 유지를 위해 볼륨 필요  
**비유**: USB 드라이브 — 컴퓨터(컨테이너)를 교체해도 데이터는 USB에 남음  
**현재 repo에서의 역할**: etcd_data, minio_data, milvus_data, redis_data, pg_data, opensearch_data 6개 볼륨  
**관련 파일**: `docker-compose.dev.yml` (volumes 섹션)  
**아직 부족한 점**: 볼륨 백업 정책 미수립

---

### 127.0.0.1 binding (루프백 바인딩)
**한 줄 설명**: 서비스 포트를 같은 서버 내에서만 접근 가능하도록 제한  
**왜 필요한가**: DB·인프라 포트가 외부 네트워크에 노출되면 보안 위험  
**비유**: 사무실 내부망 — 외부에서 직접 접근 불가  
**현재 repo에서의 역할**: Milvus(19530), Redis(6379), PostgreSQL(5432), OpenSearch(9200) 모두 `127.0.0.1:` 바인딩  
**관련 파일**: `docker-compose.dev.yml`  
**아직 부족한 점**: -

---

### multi-stage build (멀티스테이지 빌드)
**한 줄 설명**: Dockerfile에서 빌드 단계와 실행 단계를 분리해 최종 이미지를 최소화  
**왜 필요한가**: 빌드 도구(npm, compiler)가 실행 이미지에 포함되면 크기·보안 문제  
**현재 repo에서의 역할**: `frontend/Dockerfile` — node:20-alpine 빌드 → 최소 실행 이미지, 비루트 user  
**관련 파일**: `frontend/Dockerfile`  
**아직 부족한 점**: -

---

## 카테고리 8 — 보안 / 운영

### environment variable (환경변수)
**한 줄 설명**: 프로그램 실행 시 외부에서 주입하는 설정값 — 코드에 하드코딩 금지  
**왜 필요한가**: API 키·비밀번호를 코드에 직접 쓰면 깃허브 유출 위험  
**비유**: 금고 비밀번호를 메모장에 쓰지 않고 머릿속에만 기억  
**현재 repo에서의 역할**: `.env` 파일로 관리, `pydantic-settings`/`os.getenv`로만 읽음  
**관련 파일**: `.env` (실값 비커밋), `backend/app/core/config.py`  
**아직 부족한 점**: 운영환경 secrets manager 미연결

---

### content_hash (컨텐츠 해시)
**한 줄 설명**: 기사 내용을 SHA256으로 해시해 중복 여부 판단에 사용하는 값  
**왜 필요한가**: 같은 기사가 여러 번 수집될 때 중복 저장 방지  
**비유**: 책의 ISBN — 같은 책이면 ISBN이 같음  
**현재 repo에서의 역할**: `rss_collector.py`에서 제목+본문 hash → `raw_events.content_hash` UNIQUE 제약  
**관련 파일**: `workers/collectors/rss_collector.py`, `backend/alembic/versions/0002_raw_events.py`  
**아직 부족한 점**: -

---

### swallow 정책 (try_index_card swallow)
**한 줄 설명**: 색인 실패 시 에러를 삼키고 계속 진행하는 정책  
**왜 필요한가**: Milvus·OpenSearch 색인 실패가 event_cards 저장 자체를 막으면 안 됨  
**비유**: 부록 인쇄 실패해도 본문 책은 출판  
**현재 repo에서의 역할**: `vector_index_service.try_index_card()`, `opensearch_index_service.try_index_card()`  
**관련 파일**: `backend/app/services/vector_index_service.py`, `backend/app/services/opensearch_index_service.py`  
**아직 부족한 점**: swallow된 에러를 추적하는 알림 체계 없음

---

### RBAC (Role-Based Access Control)
**한 줄 설명**: 역할(관리자·편집자·뷰어 등)에 따라 접근 권한을 다르게 부여하는 체계  
**왜 필요한가**: 모든 사용자가 관리 기능에 접근하면 보안 위험  
**현재 repo에서의 역할**: **미구현** — dev 모드에서 Admin token bypass 상태  
**아직 부족한 점**: STEP 015 예정

---

### OAuth
**한 줄 설명**: 외부 서비스(Google·GitHub 등)로 로그인을 위임하는 인증 프로토콜  
**왜 필요한가**: 직접 비밀번호 저장 없이 신뢰할 수 있는 인증 제공  
**현재 repo에서의 역할**: **미구현**  
**아직 부족한 점**: STEP 015 예정

---

### UI/UX
**한 줄 설명**: 사용자 인터페이스(화면 디자인)와 사용자 경험(사용 편의성)  
**현재 repo에서의 역할**: 기본 Tailwind CSS 스타일만 적용. shadcn/ui 미도입  
**아직 부족한 점**: 디자인 시스템 · i18n(국제화) 미구현 (STEP 014 예정)

---

### observability (관측성)
**한 줄 설명**: 실행 중인 시스템의 내부 상태를 로그·메트릭·트레이스로 파악하는 능력  
**현재 repo에서의 역할**: `backend/app/core/observability.py` — LangSmith 연결, structlog 로깅  
**관련 파일**: `backend/app/core/observability.py`, `backend/app/core/logging.py`  
**아직 부족한 점**: Prometheus metrics·Grafana dashboard 미구현

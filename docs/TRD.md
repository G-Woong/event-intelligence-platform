# Technical Requirements Document — STEP 005

## 런타임 스택

| 항목 | 버전 | 비고 |
|---|---|---|
| Python | 3.11.x | `py -3.11` / uv venv |
| FastAPI | 0.115.14 | `requirements/serve.txt` |
| uvicorn | 0.35.0 | ASGI 서버 |
| pydantic | 2.11.7 | schema / settings |
| pydantic-settings | 2.7.1 | `.env` 로드 |
| SQLAlchemy | 2.0.36 | ORM + async core (`requirements/serve.txt`) |
| asyncpg | 0.30.0 | FastAPI async PG driver |
| alembic | 1.14.0 | DB migration |
| greenlet | 3.1.1 | SQLAlchemy async 의존 |
| psycopg[binary] | 3.2.3 | alembic sync 실행용 driver |
| redis | 5.0.0 | Stream I/O (`requirements/worker.txt`) |
| pymilvus | 2.4.4 | Vector store client (`requirements/vector.txt`) |
| langgraph | 0.2.76 | Event processing graph (`requirements/ai.txt`) |
| langchain-core | 0.2.43 | LangGraph 의존 |
| openai | 1.108.1 | LLM 호출 (`requirements/ai.txt`, agent-worker 한정) |
| tenacity | 8.5.0 | OpenAI retry (`requirements/base.txt`) |
| httpx | 0.28.1 | agent-worker → backend HTTP 호출 |

## 인프라

| 항목 | 버전 | 비고 |
|---|---|---|
| Redis | 7.4-alpine | Stream broker, in-memory KV |
| PostgreSQL | 17-alpine | 영속 스토리지 (event_cards, comments) |
| Milvus | v2.4.10 | Vector store (STEP 006: 실호출 활성화) |
| Docker Compose | v2 | `event-intelligence-dev` project |

## 환경 변수 (`.env` + compose override)

| 키 | 기본값 | 비고 |
|---|---|---|
| LANGSMITH_TRACING | "" | 비어있으면 WARNING |
| LANGSMITH_ENDPOINT | "" | |
| LANGSMITH_API_KEY | "" | 길이만 로그 |
| LANGSMITH_PROJECT | "" | |
| OPENAI_API_KEY | "" | mock provider에서는 미사용. openai provider 선택 시 필수 |
| MILVUS_HOST | localhost | compose: `milvus-standalone` |
| MILVUS_PORT | 19530 | |
| REDIS_URL | redis://localhost:6379/0 | compose: `redis://redis:6379/0` |
| DATABASE_URL | postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel | compose: host=`postgres` |
| LLM_PROVIDER | mock | `mock` 또는 `openai`. agent-worker 환경변수로 명시 |
| LLM_MODEL | gpt-4o-mini | openai provider 사용 시 모델명 |
| LLM_TIMEOUT_SEC | 30.0 | OpenAI API 요청 타임아웃 (초) |
| LLM_MAX_TOKENS | 1024 | 최대 응답 토큰 수 |
| LLM_TEMPERATURE | 0.2 | 생성 온도 (0.0~1.0) |

## Stream 구성

| Stream | Group | Consumer | 방향 |
|---|---|---|---|
| stream:raw_events | group:ingest | worker-1 | producer → worker |
| stream:to_agent | group:agent | agent-worker-1 | worker → agent-worker |

## DB 구성

| 테이블 | 역할 |
|---|---|
| event_cards | FinalEventCard 영속 저장 |
| comments | 사용자 댓글 |

Migration: `alembic upgrade head` (backend/entrypoint.sh에서 자동 실행).

## LLM 구성 (STEP 005)

| 컴포넌트 | 위치 | 역할 |
|---|---|---|
| BaseLLMClient | `backend/app/services/llm_client.py` | 공통 인터페이스 (ABC) |
| MockLLMClient | 동일 | 결정론적 mock 응답, 테스트용 |
| OpenAILLMClient | 동일 | openai SDK 동기 호출, tenacity retry 2회 |
| get_llm_client() | 동일 | lazy singleton (노드별 재생성 없음) |
| agents/tools/llm.py | `agents/tools/llm.py` | 노드-LLM 사이 thin wrapper (4개 헬퍼) |
| agents/prompts/*.md | `agents/prompts/` | 교체 가능한 프롬프트 템플릿 |

## 비기능 요구사항 (STEP 005 범위)

- LLM_PROVIDER=mock 기본 — 기존 e2e/smoke 회귀 0건
- OpenAI 실호출은 `RUN_OPENAI_SMOKE=1` opt-in 시에만
- backend Dockerfile에 ai.txt 미설치 (불필요한 의존성 비대화 방지)
- agent-worker Dockerfile에만 ai.txt (openai 패키지) 포함
- `.env` 실값 로그 금지 (`OPENAI_API_KEY` 부분 마스킹도 금지, 길이만 logger.debug)
- Pydantic 검증 실패 시 fallback 반환, pipeline 전체 차단 없음
- `restart: on-failure`로 비정상 종료 시 자동 재시작

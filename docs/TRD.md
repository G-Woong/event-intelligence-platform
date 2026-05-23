# Technical Requirements Document — STEP 003

## 런타임 스택

| 항목 | 버전 | 비고 |
|---|---|---|
| Python | 3.11.x | `py -3.11` / uv venv |
| FastAPI | 0.115.14 | `requirements/serve.txt` |
| uvicorn | 0.35.0 | ASGI 서버 |
| pydantic | 2.11.7 | schema / settings |
| pydantic-settings | 2.7.1 | `.env` 로드 |
| redis | 5.0.0 | Stream I/O (`requirements/worker.txt`) |
| pymilvus | 2.4.4 | Vector store client (`requirements/vector.txt`) |
| langgraph | 0.2.76 | Event processing graph (`requirements/ai.txt`) |
| langchain-core | 0.2.43 | LangGraph 의존 |
| httpx | 0.28.1 | agent-worker → backend HTTP 호출 |

## 인프라

| 항목 | 버전 | 비고 |
|---|---|---|
| Redis | 7.4-alpine | Stream broker, in-memory KV |
| Milvus | v2.4.10 | Vector store (STEP 003: connect stub) |
| Docker Compose | v2 | `event-intelligence-dev` project |

## 환경 변수 (`.env`)

| 키 | 기본값 | 비고 |
|---|---|---|
| LANGSMITH_TRACING | "" | 비어있으면 WARNING |
| LANGSMITH_ENDPOINT | "" | |
| LANGSMITH_API_KEY | "" | 길이만 로그 |
| LANGSMITH_PROJECT | "" | |
| OPENAI_API_KEY | "" | mock provider에서는 미사용 |
| MILVUS_HOST | localhost | compose: `milvus-standalone` |
| MILVUS_PORT | 19530 | |
| REDIS_URL | redis://localhost:6379/0 | compose: `redis://redis:6379/0` |

## Stream 구성

| Stream | Group | Consumer | 방향 |
|---|---|---|---|
| stream:raw_events | group:ingest | worker-1 | producer → worker |
| stream:to_agent | group:agent | agent-worker-1 | worker → agent-worker |

## 비기능 요구사항 (STEP 003 범위)

- LLM 호출 0회 (mock)
- 외부 API 호출 없음 (producer → Redis → worker → agent-worker → backend HTTP)
- 프로세스 비정상 종료 시 `restart: on-failure`로 자동 재시작
- `.env` 실값 로그 금지 (`SecretMaskingFilter`)
- Postgres 미설치 (placeholder)

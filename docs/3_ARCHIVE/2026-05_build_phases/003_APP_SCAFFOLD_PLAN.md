# STEP 003 — 앱 Scaffold 실행 계획
> **superseded by `plans/repo-sunny-barto.md` (STEP 003 expanded)**

## 목적

FastAPI + LangGraph + Celery Worker + Milvus client를 포함한 앱 scaffold를 구성하고,
docker-compose.dev.yml에 backend / worker / agent-worker 서비스를 추가해 통합 동작을 검증한다.

## 진입 조건

- STEP 002.5(본 정리 단계) 검증 항목 모두 PASS
- codex 브랜치 상태 정상 (deleted 미표시)
- 사용자 STEP 003 시작 승인

## 산출물

### backend/
| 파일 | 내용 |
|---|---|
| `backend/app/main.py` | FastAPI app 생성, lifespan, 라우터 등록 |
| `backend/app/api/health.py` | `GET /health` — Redis/Milvus 연결 상태 반환 |
| `backend/app/api/events.py` | `GET /events` (mock), `POST /events/ingest` (mock) |
| `backend/app/core/config.py` | pydantic-settings, `.env` 키 8개 로드 |
| `backend/app/db/redis.py` | Redis 연결 헬퍼 |
| `backend/app/db/milvus.py` | Milvus 연결 헬퍼, 컬렉션 init |
| `backend/Dockerfile` | Python 3.11, uv, requirements/serve.txt |

### agents/
| 파일 | 내용 |
|---|---|
| `agents/graphs/event_processing_graph.py` | LangGraph StateGraph (normalize → dedupe → rank → summarize) |
| `agents/nodes/normalize.py` | raw event → normalized schema |
| `agents/nodes/dedupe.py` | 중복 제거 (mock) |
| `agents/nodes/rank.py` | 랭킹 점수 부여 (mock) |
| `agents/nodes/summarize.py` | LLM 요약 (mock, 실제 호출 없음) |
| `agents/Dockerfile` | Python 3.11, uv, requirements/ai.txt |

### workers/
| 파일 | 내용 |
|---|---|
| `workers/queue/producer.py` | Redis queue enqueue |
| `workers/queue/consumer.py` | Celery worker, task 등록 |
| `workers/pipelines/raw_event_pipeline.py` | raw event → graph 실행 → 결과 저장 |
| `workers/Dockerfile` | Python 3.11, uv, requirements/worker.txt |

### 인프라/문서
| 파일 | 내용 |
|---|---|
| `docker-compose.dev.yml` | backend, worker, agent-worker 서비스 추가 |
| `docs/EVENT_SCHEMA.md` | raw/normalized/final event 스키마 초안 |
| `docs/API_CONTRACT.md` | `/health`, `/events` 엔드포인트 명세 초안 |
| `tests/smoke/test_health.py` | `GET /health` 응답 확인 |
| `tests/smoke/test_pipeline.py` | raw event enqueue → consume → final_card 조회 |

## 비범위 (STEP 003에서 하지 않음)

- Next.js 풀 UI 구현
- 실제 대규모 crawler / Playwright / Selenium
- torch / transformers / Gemma 로컬 서빙
- 실제 KG-RAG 고도화
- production deploy / 도메인 연결
- pymilvus 2.6.x 업그레이드 (별도 compatibility task)
- LanceDB 연동 (`graph_optional.txt` 범위)

## 검증 절차

```powershell
# 1. Compose config 유효성
docker compose -f docker-compose.dev.yml config

# 2. 서비스 이미지 빌드
docker compose -f docker-compose.dev.yml build backend worker agent-worker

# 3. 전체 스택 기동
docker compose -f docker-compose.dev.yml up -d

# 4. 헬스 엔드포인트
curl http://localhost:8000/health

# 5. Redis ping (app → Redis)
docker compose -f docker-compose.dev.yml exec backend python -c "import redis; r = redis.from_url('redis://ei-redis:6379'); print(r.ping())"

# 6. Milvus connect (app → Milvus)
docker compose -f docker-compose.dev.yml exec backend python -c "from pymilvus import connections; connections.connect(host='ei-milvus', port='19530'); print('ok')"

# 7. E2E smoke: raw event → worker → LangGraph mock → final_card 조회
python tests/smoke/test_pipeline.py
```

## 작업 분담

| 영역 | 담당 |
|---|---|
| PLAN / 리뷰 / 통합 | Claude (main worktree) |
| backend scaffold | Claude 또는 Codex 위임 |
| agents scaffold | Codex 위임 권장 (atomic) |
| workers scaffold | Codex 위임 권장 (atomic) |
| docker-compose 통합 | Claude |
| smoke test | Claude |

## 예상 소요

- scaffold + compose 통합: 1–2 세션
- 각 서비스 smoke 검증: 별도 세션

## commit 전략

- `feat(backend): add FastAPI scaffold with health endpoint`
- `feat(agents): add LangGraph event_processing_graph (mock)`
- `feat(workers): add Celery producer/consumer and raw_event_pipeline`
- `chore(docker): integrate backend/worker/agent-worker into compose dev`
- `test(smoke): add health and pipeline smoke tests`

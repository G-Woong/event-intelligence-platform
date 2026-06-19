# 백엔드 API와 데이터베이스

> FastAPI 구조, 모든 API 엔드포인트, PostgreSQL 스키마, Alembic 마이그레이션, 보안 정책을 설명합니다.

---

## FastAPI 아키텍처

```
HTTP 요청
    │
    ▼
backend/app/main.py  ← CORS middleware, lifespan 훅
    │
    ├── api/health.py       GET /health
    ├── api/events.py       GET /api/events, /api/events/search, /api/events/{id}
    ├── api/themes.py       GET /api/themes (partial)
    ├── api/sectors.py      GET /api/sectors (partial)
    ├── api/comments.py     (partial)
    ├── api/ai_replies.py   (partial)
    ├── api/admin.py        POST/GET /api/admin/**
    └── api/internal.py     내부 서비스 간 호출 전용
         │
         ▼
    services/  ← 비즈니스 로직
    (event_service, raw_event_service, search_service,
     vector_index_service, opensearch_index_service,
     reconciler_service, llm_client, embedding_client)
         │
         ▼
    db/  ← 데이터베이스 연결
    (postgres.py, redis.py, milvus.py, opensearch.py)
```

---

## API 엔드포인트 전체 목록

### Health

| Method | Path | 설명 | 상태 |
|---|---|---|---|
| GET | `/health` | 서비스 생존 확인 | DONE |

### Events

| Method | Path | 설명 | 상태 |
|---|---|---|---|
| GET | `/api/events` | event_cards 목록 반환 | DONE |
| GET | `/api/events/search` | OpenSearch 키워드 검색 (q, theme, sector, status 파라미터) | DONE |
| GET | `/api/events/{event_id}` | 특정 이벤트 카드 조회 | DONE |

### Themes / Sectors (partial)

| Method | Path | 설명 | 상태 |
|---|---|---|---|
| GET | `/api/themes` | 테마 목록 | PARTIAL (스켈레톤) |
| GET | `/api/sectors` | 섹터 목록 | PARTIAL (스켈레톤) |

### Admin

| Method | Path | 설명 | 상태 |
|---|---|---|---|
| GET | `/api/admin/jobs` | Redis Stream 상태 조회 | DONE |
| POST | `/api/admin/upsert-event` | FinalEventCard 저장·갱신 | DONE |
| POST | `/api/admin/raw-events` | raw_event 직접 생성 | DONE |
| GET | `/api/admin/raw-events` | raw_events 목록 조회 (필터 지원) | DONE |
| GET | `/api/admin/raw-events/{id}` | 특정 raw_event 조회 | DONE |
| POST | `/api/admin/raw-events/{id}/requeue` | 처리 실패 raw_event 재시도 | DONE |
| PATCH | `/api/admin/raw-events/{id}/status` | raw_event 상태 수동 변경 | DONE |
| POST | `/api/admin/raw-events/reconcile-stuck` | stuck 상태 raw_events 일괄 failed 처리 | DONE |
| POST | `/api/admin/search/reindex` | OpenSearch 색인 전체 재구축 | DONE |
| POST | `/api/admin/collect-rss-once` | RSS 수동 수집 트리거 | DONE |

> **경고**: Admin 엔드포인트는 현재 `ADMIN_API_TOKEN`이 빈값이면 인증 bypass 상태.

### Internal

| Method | Path | 설명 | 상태 |
|---|---|---|---|
| (내부 전용) | `/api/internal/**` | agent-worker·worker에서만 호출 | DONE |

---

## PostgreSQL 스키마

### raw_events 테이블
원시 수집 데이터 저장. AI 분석 전 단계.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `raw_event_id` | UUID (PK) | 고유 식별자 |
| `status` | VARCHAR | pending / processing / done / failed |
| `source_type` | VARCHAR | rss / dart / sec 등 |
| `source_name` | VARCHAR | 소스 이름 (예: Reuters Business) |
| `source_url` | TEXT | 원본 URL |
| `title` | TEXT | 기사 제목 |
| `raw_text` | TEXT | 기사 본문 (현재 RSS summary) |
| `content_hash` | VARCHAR | SHA256 해시 (UNIQUE 제약) |
| `published_at` | TIMESTAMP | 원본 발행 시각 |
| `created_at` | TIMESTAMP | DB 저장 시각 |
| `updated_at` | TIMESTAMP | 마지막 업데이트 |
| `error_reason` | TEXT | 처리 실패 시 에러 메시지 |
| `event_card_id` | UUID (FK) | 처리 완료 시 연결된 event_cards.event_id |
| `requeue_count` | INT | 재처리 횟수 |

관련 파일: `backend/app/models/raw_event.py`, `backend/alembic/versions/0002_raw_events.py`, `0003_raw_events_event_card_link.py`

### event_cards 테이블
AI 분석이 완료된 최종 사건 카드.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `event_id` | UUID (PK) | 고유 식별자 |
| `title` | TEXT | 사건 제목 |
| `headline` | TEXT | AI 생성 헤드라인 |
| `summary` | TEXT | AI 요약 |
| `theme` | VARCHAR | 테마 (geopolitics / macro / macro_kr 등) |
| `sectors` | JSONB | 섹터 목록 (["energy", "finance"]) |
| `entities` | JSONB | 엔티티 목록 |
| `impact` | TEXT | AI 영향 분석 |
| `fact_check_status` | VARCHAR | pass / fail / skip |
| `source_name` | VARCHAR | 출처 이름 |
| `source_url` | TEXT | 출처 URL |
| `published_at` | TIMESTAMP | 원본 발행 시각 |
| `status` | VARCHAR | published / held |
| `llm_provider` | VARCHAR | mock / openai |
| `model_used` | VARCHAR | gpt-4o-mini 등 (mock 시 null) |
| `created_at` | TIMESTAMP | 저장 시각 |

관련 파일: `backend/app/models/event.py`, `backend/alembic/versions/0001_initial.py`

### comments 테이블 (partial)
사건 카드에 대한 사용자 댓글 (스켈레톤 수준).

관련 파일: `backend/app/models/comment.py`, `backend/app/api/comments.py`

---

## Alembic 마이그레이션 이력

| 버전 | 파일 | 내용 |
|---|---|---|
| 0001 | `0001_initial.py` | `event_cards` 테이블 초기 생성 |
| 0002 | `0002_raw_events.py` | `raw_events` 테이블 추가 |
| 0003 | `0003_raw_events_event_card_link.py` | `raw_events.event_card_id` FK 컬럼 추가 |

실행 방식: 컨테이너 시작 시 `backend/entrypoint.sh`에서 `alembic upgrade head` 자동 실행.

---

## 서비스 레이어 요약

| 서비스 파일 | 역할 | 상태 |
|---|---|---|
| `event_service.py` | event_cards CRUD, upsert_card | DONE |
| `raw_event_service.py` | raw_events CRUD, requeue, status update | DONE |
| `search_service.py` | OpenSearch multi_match 검색 | DONE |
| `vector_index_service.py` | Milvus 벡터 색인 (try_index_card) | DONE |
| `opensearch_index_service.py` | OpenSearch 색인 (try_index_card) | DONE |
| `reconciler_service.py` | stuck raw_events 정리 | DONE |
| `llm_client.py` | LLM 호출 추상화 (MockLLMClient / OpenAIClient) | DONE (mock 기본) |
| `embedding_client.py` | 임베딩 추상화 (MockEmbeddingClient) | DONE (mock 기본) |
| `comment_service.py` | 댓글 CRUD | PARTIAL |

---

## CORS 설정

```python
# backend/app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # .env의 CORS_ORIGINS
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`CORS_ORIGINS` 환경변수 예시: `http://localhost:3000`

---

## Admin 인증 정책 (현재)

- `backend/app/core/security.py`에 `ADMIN_API_TOKEN` 검사 로직 존재
- **dev 모드**: `ADMIN_API_TOKEN`이 빈값이면 모든 Admin API 허용 (bypass)
- **운영 모드**: `.env`에 `ADMIN_API_TOKEN` 설정 필수
- Frontend → Backend 전달: `frontend/src/lib/api/server.ts`에서 `X-Admin-Token` 헤더 추가 (서버 측만)

→ 전체 인증 체계(RBAC·OAuth)는 STEP 015 예정

# Docker 인프라와 환경 설정

> 10개 서비스 구성, healthcheck 정책, 포트 바인딩 보안, .env 키 목록을 설명합니다.

---

## 10개 서비스 전체 표

| 서비스명 | 컨테이너 | 이미지 | 포트 | Healthcheck | 의존 서비스 |
|---|---|---|---|---|---|
| milvus-etcd | `ei-milvus-etcd` | coreos/etcd:v3.5.5 | (내부) | `etcdctl endpoint health` | — |
| milvus-minio | `ei-milvus-minio` | minio/minio | 9001 (콘솔) | `curl /minio/health/live` | — |
| milvus-standalone | `ei-milvus` | milvusdb/milvus:v2.4.10 | 127.0.0.1:19530, 127.0.0.1:9091 | `curl /healthz` | etcd, minio |
| redis | `ei-redis` | redis:7.4-alpine | 127.0.0.1:6379 | `redis-cli ping` | — |
| postgres | `ei-postgres` | postgres:17-alpine | 127.0.0.1:5432 | `pg_isready` | — |
| opensearch | `ei-opensearch` | opensearch:2.13.0 | 127.0.0.1:9200 | `curl /_cluster/health` | — |
| backend | `ei-backend` | (빌드) | **0.0.0.0:8000** | `curl /health` | redis, milvus, postgres, opensearch |
| worker | `ei-worker` | (빌드) | (없음) | heartbeat `/tmp/worker_heartbeat` | redis, backend |
| agent-worker | `ei-agent-worker` | (빌드) | (없음) | heartbeat `/tmp/agent_heartbeat` | redis, backend |
| frontend | `ei-frontend` | (빌드) | **0.0.0.0:3000** | `wget /api/health` | backend |

---

## 포트 바인딩 보안 정책

```
인프라 서비스 (DB·캐시):   127.0.0.1:<port> → 서버 내부에서만 접근 가능
사용자 접점 서비스:        0.0.0.0:<port>   → 외부 접근 허용
```

| 서비스 | 바인딩 | 이유 |
|---|---|---|
| Redis (6379) | 127.0.0.1 | DB — 외부 직접 접근 금지 |
| PostgreSQL (5432) | 127.0.0.1 | DB — 외부 직접 접근 금지 |
| Milvus (19530, 9091) | 127.0.0.1 | DB — 외부 직접 접근 금지 |
| OpenSearch (9200) | 127.0.0.1 | DB — 외부 직접 접근 금지 |
| Backend (8000) | 0.0.0.0 | 외부(브라우저·프론트) 접근 필요 |
| Frontend (3000) | 0.0.0.0 | 사용자 접점 |

---

## healthcheck 방식별 분류

### curl 방식 (HTTP 엔드포인트)
```yaml
test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
```
대상: backend, milvus-standalone, milvus-minio, opensearch

### pg_isready 방식
```yaml
test: ["CMD-SHELL", "pg_isready -U event_user -d event_intel"]
```
대상: postgres

### redis-cli 방식
```yaml
test: ["CMD", "redis-cli", "ping"]
```
대상: redis

### heartbeat 파일 방식
```yaml
test: ["CMD-SHELL", "test $(($(date +%s) - $(stat -c %Y /tmp/worker_heartbeat 2>/dev/null || echo 0))) -lt 60"]
```
대상: worker, agent-worker  
→ 프로세스가 60초 이내에 파일을 갱신하지 않으면 unhealthy

### wget 방식
```yaml
test: ["CMD", "wget", "-qO-", "http://127.0.0.1:3000/api/health"]
```
대상: frontend (wget이 curl보다 Alpine 이미지에 더 작음)

---

## 컨테이너 시작 순서 (depends_on 기반)

```
etcd ─┐
      ├→ milvus
minio─┘        ┐
redis ──────────┤
postgres ───────┤
opensearch ─────┴→ backend ─┬→ worker
                             ├→ agent-worker
                             └→ frontend
```

`condition: service_healthy` 사용 — 단순 시작 완료가 아닌 healthcheck 통과 후 다음 서비스 시작.

---

## 볼륨 구성

| 볼륨명 | 용도 | 서비스 |
|---|---|---|
| `etcd_data` | Milvus 메타데이터 | milvus-etcd |
| `minio_data` | Milvus 오브젝트 스토리지 | milvus-minio |
| `milvus_data` | Milvus 벡터 인덱스 | milvus-standalone |
| `redis_data` | Redis 영속 데이터 (AOF) | redis |
| `pg_data` | PostgreSQL 데이터 | postgres |
| `opensearch_data` | OpenSearch 인덱스 | opensearch |

→ `docker compose down` 시 볼륨은 유지됨 (데이터 보존)  
→ 볼륨 삭제: `docker compose down -v` (CLAUDE.md에서 사용자 명시 요청 전 금지)

---

## .env 키 목록 (실값 비포함)

> **경고**: 실제 API 키 값을 절대 커밋하지 마세요. 아래는 키 이름만 나열합니다.

### LangSmith 관측
```
LANGSMITH_TRACING=true/false
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=<LangSmith 발급 키>
LANGSMITH_PROJECT=<프로젝트명>
```

### OpenAI
```
OPENAI_API_KEY=<OpenAI 발급 키>
```

### Milvus 연결
```
MILVUS_HOST=milvus-standalone  (컨테이너 내부명)
MILVUS_PORT=19530
MILVUS_COLLECTION=event_embeddings
```

### Redis 연결
```
REDIS_URL=redis://redis:6379/0
```

### LLM / Embedding 프로바이더 선택
```
LLM_PROVIDER=mock          (mock | openai)
LLM_MODEL=gpt-4o-mini
EMBEDDING_PROVIDER=mock    (mock | openai)
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
```

### Admin 인증
```
ADMIN_API_TOKEN=<비밀 토큰>  (빈값이면 dev 모드 bypass)
```

### Frontend URL
```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
INTERNAL_API_BASE_URL=http://backend:8000
```

### Backend
```
DATABASE_URL=postgresql+asyncpg://event_user:event_pass@postgres:5432/event_intel
CORS_ORIGINS=http://localhost:3000
OPENSEARCH_HOST=opensearch
OPENSEARCH_PORT=9200
OPENSEARCH_EVENT_INDEX=event_cards
BACKEND_INTERNAL_URL=http://backend:8000
```

---

## 컨테이너 재기동 절차 요약

```powershell
# 전체 재시작
docker compose -f docker-compose.dev.yml restart

# 특정 서비스만 재시작
docker compose -f docker-compose.dev.yml restart backend

# 로그 확인
docker compose -f docker-compose.dev.yml logs -f backend

# 전체 상태 확인
docker compose -f docker-compose.dev.yml ps
```

상세 절차: `docs/DEPLOYMENT.md` 참고

---

## Compose 프로젝트명

```yaml
name: event-intelligence-dev
```

→ 컨테이너명 접두사: `ei-` (예: `ei-backend`, `ei-redis`)

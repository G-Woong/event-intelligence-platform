> **Status: SUPERSEDED (부분)**
> Canonical replacement: `docs/_CANONICAL/01_IMPLEMENTED_FLOW.md §B`, `docs/_CANONICAL/03_SOURCE_STATUS.md`
> Reason: `workers/` RSS 3소스(legacy 경로) 전용. 현재 주 수집 엔진은 `ingestion/`(57소스). 별개 서브시스템(06 C-1).

# Collector Design

## STEP 007: RSS Collector

### 아키텍처

```
RSS feed (feedparser)
  → workers/collectors/rss_collector.py  (one-shot run())
  → POST /api/admin/raw-events           (backend admin API)
     │  헤더: X-Admin-Token (ADMIN_API_TOKEN env, STEP 008C)
     ├─ raw_events 테이블 idempotent insert (content_hash UNIQUE)
     ├─ asyncio.to_thread(enqueue_raw_event(...))  → stream:raw_events
     │    payload에 raw_event_id 포함 (STEP 008A)
     └─ status: collected → enqueued
            │
            ├─ XADD 실패 → status="failed", error_reason="xadd_failed:..." (STEP 008A)
            │
  → worker consumer → ingest_pipeline → stream:to_agent
         raw_event_id forward (STEP 008A)
  → agent-worker → LangGraph (EventState.raw_event_id 주입)
       → FinalEventCard → Postgres + Milvus
       → PATCH /api/admin/raw-events/{id}/status
       │    헤더: X-Admin-Token (settings.ADMIN_API_TOKEN, STEP 008C)
            ├─ 성공: status="processed", event_card_id=card.id (STEP 008A)
            └─ 실패: status="failed", error_reason=<snippet> (STEP 008A)
```

### 모듈 구조

```
workers/collectors/
  __init__.py
  __main__.py       # python -m workers.collectors entry
  rss_collector.py  # run() one-shot, returns summary dict
  sources.py        # DEFAULT_SOURCES 하드코딩 + get_sources()
```

### DEFAULT_SOURCES (STEP 007)

| name | url | theme_hint |
|---|---|---|
| bbc_world | https://feeds.bbci.co.uk/news/world/rss.xml | geopolitics |
| reuters_business | https://feeds.reuters.com/reuters/businessNews | macro |
| yna_economy | https://www.yna.co.kr/rss/economy.xml | macro_kr |

### content_hash 계산

```
sha256(f"{source_type}|{source_name}|{external_id or url}|{title}|{raw_text}")
```

두 UNIQUE 제약이 dedup을 담당:
1. `UNIQUE (content_hash)` — 전역 컨텐츠 dedup
2. `UNIQUE (source_type, external_id) WHERE external_id IS NOT NULL` — partial unique

### error 처리

| 상황 | 동작 |
|---|---|
| 네트워크 timeout | 해당 source 스킵, 다음 진행 |
| feedparser bozo=1 | 가능한 entries 살리고 진행 |
| entry.link 없음 | entry 스킵 |
| backend 5xx | errors 카운트 증가 |
| XADD 실패 | status="failed", error_reason="xadd_failed:..." (STEP 008A) |

### CLI 사용

```bash
# one-shot 실행
docker compose run --rm worker python -m workers.collectors.rss_collector

# fixture 기반 (live 피드 없이)
RUN_RSS_LIVE_SMOKE=0 pytest workers/tests/test_rss_collector.py -v

# live smoke (외부 피드)
RUN_RSS_LIVE_SMOKE=1 pytest tests/smoke/test_rss_collector_live.py -v
```

---

## 향후 collector 확장 패턴 (STEP 008+)

### DB-backed sources (STEP 008+)

`collector_sources` 테이블을 추가하여 관리자가 UI에서 sources를 관리.

```sql
CREATE TABLE collector_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) UNIQUE NOT NULL,
    source_type VARCHAR(32) NOT NULL,  -- rss / dart / sec / web
    url TEXT NOT NULL,
    theme_hint VARCHAR(64),
    enabled BOOLEAN NOT NULL DEFAULT true,
    poll_interval_sec INTEGER NOT NULL DEFAULT 900,
    last_collected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`get_sources()` → DB에서 enabled=true 행들을 읽어 반환.

### 새 collector 추가 패턴

1. `workers/collectors/{type}_collector.py` 생성
2. `run(sources: list[SourceConfig]) -> dict` 인터페이스 준수
3. `workers/collectors/__main__.py`에 `--source-type` 파라미터 추가
4. `requirements/collector.txt`에 신규 의존성 추가

### DART API collector (STEP 010+)

```python
# workers/collectors/dart_collector.py (STEP 010+)
# DART Open API → disclosure feed → raw_events insert
# source_type="dart", external_id=rcpNo
```

### robots.txt / 저작권 경계

`docs/COMPLIANCE_BOUNDARY.md` 참조.

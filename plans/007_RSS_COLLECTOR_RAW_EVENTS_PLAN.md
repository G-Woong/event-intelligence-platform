# STEP 007 PLAN — RSS Collector + raw_events Persistence + Alembic Migration

날짜: 2026-05-23

## 목표

외부 정보 수집의 첫 입구를 RSS로 뚫는다. feedparser로 BBC/Reuters/YNA 피드를 수집하고,
`raw_events` 테이블에 idempotent insert + Redis Stream enqueue한다.

## 범위

### 포함
- `raw_events` 테이블 + Alembic migration 0002
- `workers/collectors/rss_collector.py` one-shot run()
- `POST /api/admin/raw-events` (RawEventCreate → idempotent insert + XADD)
- `POST /api/admin/collect-rss-once` (asyncio.to_thread 트리거)
- fixture XML 4개 + unit test 21개 + smoke test 3개

### 비포함
- DART/SEC/Web/Social collector
- Playwright/Selenium/본문 크롤링
- agent pipeline의 raw_events.status 업데이트 (STEP 008)
- DB-backed sources 테이블 (STEP 008+)
- raw_event_id stream linkage (STEP 008)

## 결정 사항

| 항목 | 결정 |
|---|---|
| raw_events status lifecycle | collector: collected→enqueued. agent pipeline: 미인지. |
| DEFAULT_SOURCES | BBC World, Reuters Business, YNA Economy 하드코딩 |
| 테스트 전략 | fixture-first (네트워크 0). live는 `RUN_RSS_LIVE_SMOKE=1` opt-in |
| `/collect-rss-once` | 포함. `asyncio.to_thread` 로 이벤트 루프 블록 방지 |
| XADD 동기 Redis | `asyncio.to_thread(enqueue_raw_event, ...)` 로 래핑 |

## 핵심 설계

### content_hash
```
sha256(f"{source_type}|{source_name}|{external_id or url}|{title}|{raw_text}")
```

### 두 UNIQUE 제약
1. `UNIQUE (content_hash)` — 전역 컨텐츠 dedup
2. `UNIQUE (source_type, external_id) WHERE external_id IS NOT NULL` — partial GUID dedup

### 저장 write path
```
rss_collector.run()
  → httpx.post(/api/admin/raw-events)
    → raw_event_service.create_raw_event()
      → pg_insert ON CONFLICT DO NOTHING
      → SELECT to check duplicate
      → if new: asyncio.to_thread(enqueue_raw_event)
      → UPDATE status='enqueued'
```

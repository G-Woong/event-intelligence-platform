# workers/

Redis Stream 기반 ingest worker.

## 구조

- `queue/producer.py` — `enqueue_raw_event(RawEvent)` → XADD `stream:raw_events`
- `queue/consumer.py` — XREADGROUP `stream:raw_events` group `group:ingest`
- `pipelines/ingest_pipeline.py` — 파싱 후 `stream:to_agent`로 forward
- `pipelines/publish_pipeline.py` — FinalEventCard를 backend `/api/admin/upsert-event`로 POST

## 실행

```bash
python -m workers.queue.consumer
```

환경변수 `REDIS_URL` 필요.

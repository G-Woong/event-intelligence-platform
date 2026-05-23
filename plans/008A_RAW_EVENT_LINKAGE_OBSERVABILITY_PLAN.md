# STEP 008A — RawEvent Processing Linkage + Status Lifecycle + Observability Skeleton

*Plan 원문은 구현 지시 메시지 참조 (2026-05-24)*

## 핵심 목표

raw_event_id를 stream payload → worker → agent-worker → LangGraph state → backend status update까지 최소 침습으로 전달하고,
processed/failed 전이를 채우며, LangSmith를 plug-in 가능한 skeleton 수준으로 정리한다.

## 주요 결정 사항

| 항목 | 결정 |
|---|---|
| status 라이프사이클 | `collected → enqueued → processed \| failed` (processing 중간 상태 없음) |
| raw_event_id 전송 | `RawEvent.raw_event_id: Optional[str] = None` + stream payload 키 추가 |
| status update 경로 | `PATCH /api/admin/raw-events/{id}/status` |
| status 조회 | `GET /api/admin/raw-events/{id}` |
| event_card linkage | `raw_events.event_card_id UUID NULL` 컬럼 (Alembic 0003) |
| agent-worker 통보 | 동기 `httpx.Client.patch()` + 실패 시 warn log only |
| LangSmith | `setup_langsmith()` startup wiring, `LANGSMITH_TRACING=true`이면 활성화 |

## 비범위

- OpenSearch / Next.js UI
- processing 중간 상태
- retry/DLQ 본격 구현
- admin endpoint 인증 (STEP 008C)
- GET /api/admin/raw-events 페이징 목록 (STEP 008B/009)

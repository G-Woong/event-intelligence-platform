from __future__ import annotations

"""Redis Stream 실패 복구: 재시도 + DLQ + PEL reaper (P0 하드닝, Phase 3).

설계 불변:
- silent drop 금지: 실패 메시지는 항상 원본을 ack로 정리하되, 재시도 사본 또는 DLQ로 보존한다.
- 무한 재시도 금지: `_retry_count`를 메시지 필드에 실어 max_retries 도달 시 DLQ로 격리(poison).
- worker가 `>`(신규)만 읽는 기존 루프와 호환: 재시도는 동일 스트림에 사본을 XADD하고 원본을 ack.
- PEL reaper: worker crash로 delivered-but-unacked 잔류한 메시지를 XAUTOCLAIM으로 회수해 동일 정책 적용.

client는 redis-py 호환 객체(`xadd(name, fields)`, `xack(name, group, *ids)`,
`xautoclaim(name, group, consumer, min_idle_time, start_id, count)`)면 된다(FakeRedis 테스트 가능).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

RETRY_FIELD = "_retry_count"
DLQ_REASON_FIELD = "_dlq_reason"
DLQ_ORIGINAL_ID_FIELD = "_original_msg_id"
DLQ_SOURCE_STREAM_FIELD = "_source_stream"

DEFAULT_MAX_RETRIES = 3


def _retry_count(fields: dict) -> int:
    try:
        return int(fields.get(RETRY_FIELD, 0))
    except (TypeError, ValueError):
        return 0


def route_failure(
    client: Any,
    stream: str,
    group: str,
    msg_id: str,
    fields: dict,
    reason: str,
    dlq_stream: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """실패 메시지를 재시도 또는 DLQ로 보낸 뒤 원본을 ack한다.

    반환: "retried" | "dead_lettered".
    """
    count = _retry_count(fields)
    if count < max_retries:
        retry_fields = {k: v for k, v in fields.items() if not str(k).startswith("_dlq")}
        retry_fields[RETRY_FIELD] = str(count + 1)
        client.xadd(stream, retry_fields)
        client.xack(stream, group, msg_id)
        logger.warning(
            "dlq.route_failure: retried stream=%s msg=%s attempt=%d reason=%s",
            stream, msg_id, count + 1, reason[:120],
        )
        return "retried"

    dlq_fields = dict(fields)
    dlq_fields[DLQ_REASON_FIELD] = reason[:480]
    dlq_fields[RETRY_FIELD] = str(count)
    dlq_fields[DLQ_ORIGINAL_ID_FIELD] = str(msg_id)
    dlq_fields[DLQ_SOURCE_STREAM_FIELD] = stream
    client.xadd(dlq_stream, dlq_fields)
    client.xack(stream, group, msg_id)
    logger.error(
        "dlq.route_failure: dead_lettered stream=%s msg=%s retries=%d dlq=%s reason=%s",
        stream, msg_id, count, dlq_stream, reason[:120],
    )
    return "dead_lettered"


def reap_pending(
    client: Any,
    stream: str,
    group: str,
    consumer: str,
    min_idle_ms: int,
    dlq_stream: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    count: int = 100,
) -> dict:
    """PEL에서 idle 초과(미ack) 메시지를 XAUTOCLAIM으로 회수해 retry/DLQ로 정리.

    반환: {"claimed": n, "retried": n, "dead_lettered": n}.
    """
    stats = {"claimed": 0, "retried": 0, "dead_lettered": 0}
    cursor = "0-0"
    # 무한루프 방지: 회수→재발행이 동일 스트림에 사본을 만드므로 cursor 종료조건으로만 순회.
    for _ in range(1000):
        result = client.xautoclaim(
            stream, group, consumer, min_idle_ms, start_id=cursor, count=count
        )
        if len(result) == 3:
            next_cursor, claimed, _deleted = result
        else:
            next_cursor, claimed = result

        for msg_id, fields in claimed:
            stats["claimed"] += 1
            outcome = route_failure(
                client,
                stream,
                group,
                msg_id,
                dict(fields or {}),
                reason="reaper: stale pending (worker crash / unacked)",
                dlq_stream=dlq_stream,
                max_retries=max_retries,
            )
            stats[outcome] += 1

        cursor = next_cursor
        if not claimed or str(cursor) in ("0-0", "0"):
            break
    return stats

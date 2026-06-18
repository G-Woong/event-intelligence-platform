from __future__ import annotations

import logging
import sys
from pathlib import Path

from backend.app.db import redis as redis_db
from workers.pipelines.ingest_pipeline import process
from workers.queue import dlq

logger = logging.getLogger(__name__)

_STREAM = "stream:raw_events"
_GROUP = "group:ingest"
_CONSUMER = "worker-1"
_DLQ_STREAM = "stream:raw_events:dlq"
_MAX_RETRIES = 3
_HEARTBEAT = Path("/tmp/worker_heartbeat")


def run_forever() -> None:
    redis_db.ensure_group(_STREAM, _GROUP)
    logger.info("worker consumer started: stream=%s group=%s", _STREAM, _GROUP)
    while True:
        messages = redis_db.xreadgroup(_STREAM, _GROUP, _CONSUMER)
        _HEARTBEAT.touch()
        for _stream_name, entries in messages:
            for msg_id, fields in entries:
                try:
                    process(msg_id, fields)
                    redis_db.xack(_STREAM, _GROUP, msg_id)
                except Exception as exc:
                    logger.error("worker consumer: unhandled error msg=%s err=%s", msg_id, exc)
                    # silent PEL leak 방지: 재시도(사본 재발행) 또는 DLQ로 격리 후 원본 ack.
                    try:
                        outcome = dlq.route_failure(
                            redis_db.get_redis(),
                            _STREAM,
                            _GROUP,
                            msg_id,
                            fields,
                            reason=f"{type(exc).__name__}: {exc}",
                            dlq_stream=_DLQ_STREAM,
                            max_retries=_MAX_RETRIES,
                        )
                        logger.warning("worker consumer: msg=%s routed=%s", msg_id, outcome)
                    except Exception as route_exc:
                        # 라우팅 자체 실패(예: redis 다운) → ack 보류, reaper가 후속 회수.
                        logger.error(
                            "worker consumer: failure routing failed msg=%s err=%s",
                            msg_id, route_exc,
                        )
                finally:
                    _HEARTBEAT.touch()


if __name__ == "__main__":
    from backend.app.core.logging import configure_logging
    configure_logging()
    run_forever()

from __future__ import annotations

import logging
import sys
from pathlib import Path

from backend.app.db import redis as redis_db
from workers.pipelines.ingest_pipeline import process

logger = logging.getLogger(__name__)

_STREAM = "stream:raw_events"
_GROUP = "group:ingest"
_CONSUMER = "worker-1"
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
                finally:
                    _HEARTBEAT.touch()


if __name__ == "__main__":
    from backend.app.core.logging import configure_logging
    configure_logging()
    run_forever()

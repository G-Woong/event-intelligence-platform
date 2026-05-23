from __future__ import annotations

import json
import logging
from datetime import datetime
from backend.app.db import redis as redis_db
from backend.app.schemas.events import RawEvent
from agents.graphs.event_processing_graph import run as graph_run
from workers.pipelines.publish_pipeline import publish_card

logger = logging.getLogger(__name__)

_STREAM = "stream:to_agent"
_GROUP = "group:agent"
_CONSUMER = "agent-worker-1"


def run_forever() -> None:
    redis_db.ensure_group(_STREAM, _GROUP)
    logger.info("agent-worker started: stream=%s group=%s", _STREAM, _GROUP)
    while True:
        messages = redis_db.xreadgroup(_STREAM, _GROUP, _CONSUMER)
        for _stream_name, entries in messages:
            for msg_id, fields in entries:
                try:
                    raw = RawEvent(
                        source=fields.get("source", "unknown"),
                        url=fields.get("url", ""),
                        fetched_at=datetime.fromisoformat(
                            fields.get("fetched_at", datetime.utcnow().isoformat())
                        ),
                        raw_text=fields.get("raw_text", ""),
                        raw_metadata=json.loads(fields.get("raw_metadata", "{}")),
                    )
                    card = graph_run(raw)
                    publish_card(card)
                    redis_db.xack(_STREAM, _GROUP, msg_id)
                except Exception as exc:
                    logger.error("agent-worker: error msg=%s err=%s", msg_id, exc)


if __name__ == "__main__":
    from backend.app.core.logging import configure_logging
    configure_logging()
    run_forever()

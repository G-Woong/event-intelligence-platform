from __future__ import annotations

import json
import logging
from datetime import datetime
from backend.app.db import redis as redis_db
from backend.app.schemas.events import RawEvent

logger = logging.getLogger(__name__)
_TO_AGENT_STREAM = "stream:to_agent"


def process(message_id: str, fields: dict) -> None:
    raw_event_id = fields.get("raw_event_id", "")
    try:
        raw = RawEvent(
            source=fields.get("source", "unknown"),
            url=fields.get("url", ""),
            fetched_at=datetime.fromisoformat(fields.get("fetched_at", datetime.utcnow().isoformat())),
            raw_text=fields.get("raw_text", ""),
            raw_metadata=json.loads(fields.get("raw_metadata", "{}")),
            raw_event_id=raw_event_id or None,
        )
    except Exception as exc:
        logger.error("ingest_pipeline: parse error msg=%s err=%s", message_id, exc)
        return

    payload = {
        "source": raw.source,
        "url": raw.url,
        "fetched_at": raw.fetched_at.isoformat(),
        "raw_text": raw.raw_text,
        "raw_metadata": json.dumps(raw.raw_metadata),
        "raw_event_id": raw.raw_event_id or "",
    }
    redis_db.xadd(_TO_AGENT_STREAM, payload)
    logger.info("ingest_pipeline: forwarded msg=%s to %s", message_id, _TO_AGENT_STREAM)

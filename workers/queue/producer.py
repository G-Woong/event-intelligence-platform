from __future__ import annotations

import json
from datetime import datetime
from backend.app.db import redis as redis_db
from backend.app.schemas.events import RawEvent

_STREAM = "stream:raw_events"


def enqueue_raw_event(raw_event: RawEvent) -> str:
    payload = {
        "source": raw_event.source,
        "url": raw_event.url,
        "fetched_at": raw_event.fetched_at.isoformat(),
        "raw_text": raw_event.raw_text,
        "raw_metadata": json.dumps(raw_event.raw_metadata),
    }
    msg_id = redis_db.xadd(_STREAM, payload)
    return msg_id

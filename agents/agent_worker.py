from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.app.core.config import settings
from backend.app.db import redis as redis_db
from backend.app.schemas.events import RawEvent
from agents.graphs.event_processing_graph import run as graph_run
from workers.pipelines.publish_pipeline import publish_card

logger = logging.getLogger(__name__)

_STREAM = "stream:to_agent"
_GROUP = "group:agent"
_CONSUMER = "agent-worker-1"


@retry(
    reraise=False,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=3),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
)
def _patch_status(url: str, payload: dict, headers: dict | None = None) -> None:
    resp = httpx.patch(url, json=payload, headers=headers or {}, timeout=10)
    resp.raise_for_status()


def _notify_status(
    raw_event_id: Optional[str],
    status: str,
    error_reason: Optional[str] = None,
    event_card_id: Optional[str] = None,
) -> None:
    if raw_event_id is None:
        logger.warning("raw_event_id absent — status update skipped status=%s", status)
        return
    url = f"{settings.BACKEND_INTERNAL_URL}/api/admin/raw-events/{raw_event_id}/status"
    payload = {"status": status, "error_reason": error_reason, "event_card_id": event_card_id}
    headers: dict[str, str] = {}
    if settings.ADMIN_API_TOKEN:
        headers["X-Admin-Token"] = settings.ADMIN_API_TOKEN
    try:
        _patch_status(url, payload, headers)
    except Exception as exc:
        logger.warning(
            "raw_event status update failed after retries id=%s reason=%s",
            raw_event_id,
            str(exc)[:200],
        )


def run_forever() -> None:
    redis_db.ensure_group(_STREAM, _GROUP)
    logger.info("agent-worker started: stream=%s group=%s", _STREAM, _GROUP)
    while True:
        messages = redis_db.xreadgroup(_STREAM, _GROUP, _CONSUMER)
        for _stream_name, entries in messages:
            for msg_id, fields in entries:
                raw_event_id = fields.get("raw_event_id") or None
                try:
                    raw = RawEvent(
                        source=fields.get("source", "unknown"),
                        url=fields.get("url", ""),
                        fetched_at=datetime.fromisoformat(
                            fields.get("fetched_at", datetime.utcnow().isoformat())
                        ),
                        raw_text=fields.get("raw_text", ""),
                        raw_metadata=json.loads(fields.get("raw_metadata", "{}")),
                        raw_event_id=raw_event_id,
                    )
                    card = graph_run(raw)
                    publish_card(card)
                    _notify_status(raw_event_id, "processed", event_card_id=str(card.id))
                except Exception as exc:
                    logger.exception("agent-worker: error msg=%s err=%s", msg_id, exc)
                    _notify_status(raw_event_id, "failed", error_reason=str(exc)[:500])
                finally:
                    redis_db.xack(_STREAM, _GROUP, msg_id)


if __name__ == "__main__":
    from backend.app.core.logging import configure_logging
    configure_logging()
    run_forever()

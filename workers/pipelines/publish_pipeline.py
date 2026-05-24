from __future__ import annotations

import logging
import os
import httpx
from backend.app.schemas.events import FinalEventCard

logger = logging.getLogger(__name__)
_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
_ADMIN_TOKEN = os.getenv("ADMIN_API_TOKEN", "")


def publish_card(card: FinalEventCard) -> bool:
    headers: dict[str, str] = {"X-Admin-Token": _ADMIN_TOKEN} if _ADMIN_TOKEN else {}
    try:
        resp = httpx.post(
            f"{_BACKEND_URL}/api/admin/upsert-event",
            json=card.model_dump(mode="json"),
            headers=headers,
            timeout=10.0,
        )
        resp.raise_for_status()
        logger.info("publish_pipeline: card=%s status=published", card.id)
        return True
    except Exception as exc:
        logger.error("publish_pipeline: failed card=%s err=%s", card.id, exc)
        return False

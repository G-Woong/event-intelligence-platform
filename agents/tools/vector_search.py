from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BACKEND_URL = os.getenv("BACKEND_INTERNAL_URL", "http://backend:8000")
_TIMEOUT = 10.0


def search_similar(
    text: str,
    top_k: int = 5,
    exclude_event_id: Optional[str] = None,
) -> list[dict]:
    url = f"{_BACKEND_URL}/api/internal/search-similar"
    payload: dict = {"query_text": text, "top_k": top_k}
    if exclude_event_id:
        payload["exclude_event_id"] = exclude_event_id
    resp = httpx.post(url, json=payload, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("hits", [])

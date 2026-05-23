from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import socket

import feedparser
import httpx

from workers.collectors.sources import get_sources

logger = logging.getLogger(__name__)

_BACKEND_URL = os.getenv("BACKEND_INTERNAL_URL", "http://localhost:8000")
_TIMEOUT_SEC = int(os.getenv("RSS_COLLECTOR_FETCH_TIMEOUT_SEC", "15"))
_USER_AGENT = os.getenv("RSS_COLLECTOR_USER_AGENT", "event-intelligence/0.7 (+ei)")
_MAX_URL_LEN = 2048

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def _content_hash(source_type: str, source_name: str, external_id: str | None, url: str, title: str, raw_text: str) -> str:
    key = f"{source_type}|{source_name}|{external_id or url}|{title}|{raw_text}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _parse_published(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed")
    if parsed is None:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except Exception:
        return None


def _process_source(source: dict, client: httpx.Client) -> dict:
    name: str = source["name"]
    url: str = source["url"]
    theme_hint: str = source.get("theme_hint", "")

    items_seen = 0
    items_enqueued = 0
    duplicates = 0
    errors = 0

    try:
        prev_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(_TIMEOUT_SEC)
        try:
            feed = feedparser.parse(url, agent=_USER_AGENT, request_headers={"User-Agent": _USER_AGENT})
        finally:
            socket.setdefaulttimeout(prev_timeout)
    except Exception as exc:
        logger.error("source=%s fetch error: %s", name, exc)
        return {"source": name, "items_seen": 0, "items_enqueued": 0, "duplicates": 0, "errors": 1}

    if feed.get("bozo"):
        logger.warning("source=%s bozo=1 (%s), processing available entries", name, feed.get("bozo_exception"))

    for entry in feed.get("entries", []):
        link: str | None = entry.get("link") or entry.get("url")
        if not link:
            logger.debug("source=%s entry missing link — skipping", name)
            continue

        if len(link) > _MAX_URL_LEN:
            logger.warning("source=%s url length %d > %d — truncating", name, len(link), _MAX_URL_LEN)
            link = link[:_MAX_URL_LEN]

        items_seen += 1
        external_id: str | None = entry.get("id") or entry.get("guidislink") and entry.get("link") or None
        if not external_id:
            external_id = entry.get("link")

        title: str = (entry.get("title") or "")[:1024]
        summary_raw: str = entry.get("summary") or ""
        raw_text: str = _strip_html(summary_raw)
        published_at: datetime | None = _parse_published(entry)

        feed_title: str = feed.feed.get("title", "")
        tags: list[str] = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]
        raw_metadata: dict = {
            "rss": {
                "feed_title": feed_title,
                "guid": external_id,
                "tags": tags,
            }
        }

        content_hash = _content_hash("rss", name, external_id, link, title, raw_text)

        payload: dict = {
            "source_type": "rss",
            "source_name": name,
            "external_id": external_id,
            "url": link,
            "title": title,
            "raw_text": raw_text,
            "published_at": published_at.isoformat() if published_at else None,
            "content_hash": content_hash,
            "theme_hint": theme_hint,
            "raw_metadata": raw_metadata,
        }

        try:
            resp = client.post(f"{_BACKEND_URL}/api/admin/raw-events", json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("is_duplicate"):
                duplicates += 1
            else:
                items_enqueued += 1
        except httpx.HTTPStatusError as exc:
            logger.error("source=%s backend 5xx url=%s status=%d", name, link, exc.response.status_code)
            errors += 1
        except Exception as exc:
            logger.error("source=%s backend call failed url=%s: %s", name, link, exc)
            errors += 1

    return {
        "source": name,
        "items_seen": items_seen,
        "items_enqueued": items_enqueued,
        "duplicates": duplicates,
        "errors": errors,
    }


def run() -> dict:
    sources = get_sources()
    total_seen = total_enqueued = total_duplicates = total_errors = 0
    per_source: list[dict] = []

    with httpx.Client(timeout=_TIMEOUT_SEC) as client:
        for source in sources:
            result = _process_source(source, client)
            per_source.append(result)
            total_seen += result["items_seen"]
            total_enqueued += result["items_enqueued"]
            total_duplicates += result["duplicates"]
            total_errors += result["errors"]

    summary = {
        "sources": len(sources),
        "items_seen": total_seen,
        "items_enqueued": total_enqueued,
        "duplicates": total_duplicates,
        "errors": total_errors,
        "per_source": per_source,
    }
    logger.info("rss_collector done: %s", summary)
    return summary

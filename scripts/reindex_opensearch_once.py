"""One-shot OpenSearch reindex caller for cron/CI hooks.

Env vars:
  BACKEND_INTERNAL_URL   default http://localhost:8000
  ADMIN_API_TOKEN        if set, sends X-Admin-Token header
  REINDEX_LIMIT          default 1000
  REINDEX_DRY_RUN        default true
"""
from __future__ import annotations

import json
import os
import sys

import httpx


def main() -> int:
    url = (
        f"{os.getenv('BACKEND_INTERNAL_URL', 'http://localhost:8000')}"
        "/api/admin/search/reindex"
    )
    headers: dict[str, str] = {}
    token = os.getenv("ADMIN_API_TOKEN", "")
    if token:
        headers["X-Admin-Token"] = token

    body = {
        "limit": int(os.getenv("REINDEX_LIMIT", "1000")),
        "dry_run": os.getenv("REINDEX_DRY_RUN", "true").lower() in ("1", "true", "yes"),
    }
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=60)
        resp.raise_for_status()
        print(json.dumps(resp.json(), default=str))
        return 0
    except Exception as exc:
        print(f"reindex_opensearch_once failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

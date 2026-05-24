"""One-shot reconcile-stuck caller for cron/CI hooks.

Env vars:
  BACKEND_INTERNAL_URL   default http://localhost:8000
  ADMIN_API_TOKEN        if set, sends X-Admin-Token header
  RECONCILER_BEFORE_SECONDS  default 600
  RECONCILER_LIMIT           default 100
  RECONCILER_DRY_RUN         default true
"""
from __future__ import annotations

import json
import os
import sys

import httpx


def main() -> int:
    url = (
        f"{os.getenv('BACKEND_INTERNAL_URL', 'http://localhost:8000')}"
        "/api/admin/raw-events/reconcile-stuck"
    )
    headers: dict[str, str] = {}
    token = os.getenv("ADMIN_API_TOKEN", "")
    if token:
        headers["X-Admin-Token"] = token

    body = {
        "before_seconds": int(os.getenv("RECONCILER_BEFORE_SECONDS", "600")),
        "limit": int(os.getenv("RECONCILER_LIMIT", "100")),
        "dry_run": os.getenv("RECONCILER_DRY_RUN", "true").lower() in ("1", "true", "yes"),
    }
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        print(json.dumps(resp.json(), default=str))
        return 0
    except Exception as exc:
        print(f"reconcile_stuck_once failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

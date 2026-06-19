#!/usr/bin/env python
"""Stop hook: non-blocking reminder to run a secret scan when files changed.

Emits an ``additionalContext`` reminder (never ``decision: block``) so the
turn always completes normally. Fail-open: any error exits 0 silently.
stdlib only.
"""
import json
import subprocess
import sys


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        payload = {}

    # Loop guard: if we are already inside a stop-hook continuation, emitting
    # additionalContext again would re-block the turn from ending and loop
    # (hit the block cap). Return success silently so the turn can end.
    if payload.get("stop_hook_active"):
        return 0

    cwd = payload.get("cwd") or None

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception:
        return 0  # git unavailable / not a repo -> stay silent

    changed = [ln for ln in result.stdout.splitlines() if ln.strip()]
    if not changed:
        return 0  # nothing changed -> no reminder

    msg = (
        f"[reminder] {len(changed)} file(s) changed since HEAD. "
        "Before committing, consider running the secret scan: "
        ".\\.venv\\Scripts\\python.exe -m ingestion.tools.scan_secrets "
        "--paths ingestion docs plans .claude"
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

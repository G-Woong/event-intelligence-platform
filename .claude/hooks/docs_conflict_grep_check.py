#!/usr/bin/env python
"""Stop hook: non-blocking reminder to check docs for status mis-labels.

When docs/**.md changed since HEAD, scans only those changed files for a few
high-risk status mis-labels and emits an ``additionalContext`` reminder
(never ``decision: block``). The authoritative, context-aware check lives in
docs-sync-skill; this hook is only a lightweight nudge.

Fail-open: any error exits 0 silently. stdlib only.
"""
import json
import os
import re
import subprocess
import sys

# A line is suspicious only if it asserts a wrong status. Lines that merely
# state the policy (e.g. "PASS 표기 금지", "must not mark PASS") are excluded.
_POLICY_WORDS = ("금지", "표기 금지", "오표기", "절대", "not ", "never", "must not",
                 "CONFIRMED_EXTERNAL_RATE_LIMIT", "do not")

_SUSPECT = [
    (re.compile(r"google_trends_explore", re.I), re.compile(r"\bPASS\b"),
     "google_trends_explore marked PASS?"),
    (re.compile(r"\bgdelt\b", re.I), re.compile(r"NOT_READY"),
     "gdelt marked NOT_READY? (it is PASS)"),
]


def _is_policy_line(line: str) -> bool:
    return any(w in line for w in _POLICY_WORDS)


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        payload = {}

    # Loop guard: don't re-emit additionalContext during a stop-hook
    # continuation (would re-block the turn and loop to the block cap).
    if payload.get("stop_hook_active"):
        return 0

    cwd = payload.get("cwd") or os.getcwd()

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=8,
        )
    except Exception:
        return 0

    changed_docs = [
        ln.strip() for ln in result.stdout.splitlines()
        if ln.strip().startswith("docs/") and ln.strip().endswith(".md")
    ]
    if not changed_docs:
        return 0

    hits = []
    for rel in changed_docs:
        path = os.path.join(cwd, rel.replace("/", os.sep))
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for i, line in enumerate(fh, 1):
                    if _is_policy_line(line):
                        continue
                    for subj, obj, label in _SUSPECT:
                        if subj.search(line) and obj.search(line):
                            hits.append(f"{rel}:{i} {label}")
        except OSError:
            continue

    parts = [f"[docs reminder] {len(changed_docs)} doc(s) changed; "
             "consider running /docs-sync-skill."]
    if hits:
        parts.append("Possible status mis-labels: " + "; ".join(hits[:10]))
    msg = " ".join(parts)

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

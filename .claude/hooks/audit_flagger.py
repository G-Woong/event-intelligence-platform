#!/usr/bin/env python
"""PostToolUse hook: raise per-change-type audit flags (SENSOR only).

Fires after file-modifying tools (matcher: Edit|Write|NotebookEdit). It is a
sensor: it NEVER blocks and writes NO stdout. It recomputes, from the current
uncommitted tree, which review types are required and writes them to
``.harness/audit_required.json``. The turn-closeout skill (the main agent) reads
this file and actually routes the subagents / code-review skill — the hook does
no semantic judgement itself.

Stateless: each run overwrites with the FULL classification of the current tree
(``_porcelain_paths`` returns the whole uncommitted set), so a clean tree yields
an empty flag list and nothing accumulates across turns.

Reuses the classifier in ``turn_state_snapshot.py`` (same dir) to stay DRY.
Fail-open: any error exits 0. stdlib only.
"""
import json
import os
import sys


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()

    here = os.path.dirname(os.path.abspath(__file__))
    try:
        if here not in sys.path:
            sys.path.insert(0, here)
        import turn_state_snapshot as ts  # reuse classifier (DRY)
        norm = ts._norm_set(ts._porcelain_paths(cwd))
        flags = ts.audit_types(norm)
    except Exception:
        return 0  # fail-open: classifier unavailable -> no flags this run

    harness = os.path.join(cwd, ".harness")
    try:
        os.makedirs(harness, exist_ok=True)
        with open(os.path.join(harness, "audit_required.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"session_id": payload.get("session_id"), "flags": flags},
                      fh, ensure_ascii=False, indent=2)
    except OSError:
        return 0  # fail-open

    return 0  # no stdout: PostToolUse sensor must stay silent


if __name__ == "__main__":
    sys.exit(main())

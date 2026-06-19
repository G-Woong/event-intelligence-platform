#!/usr/bin/env python
"""Print the canonical working-tree signature for the turn-closeout stamp.

The ``turn-closeout`` skill runs this at stamp time — AFTER writing its
PROJECT_STATUS / RISK / _DECISIONS edits — and copies the ``signature`` array
verbatim into ``.harness/closeout_stamp.json:working_tree_signature``.

Why a helper instead of copying ``machine_status.sig``: the Stop hook's
``machine_status.json`` was written at the END of the *previous* turn, so it
predates this turn's narration edits. Now that the signature includes CONTENT
hashes (R2 fix), copying the stale value would never match the hook's recompute
and the gate would never go current. This helper recomputes the signature from
the CURRENT tree using the very same ``compute_signature`` the Stop hook uses
(DRY), so a correct closeout converges while a later content-only edit diverges
and re-triggers review.

Assumption: run before committing this turn's work (the documented workflow —
stamp/report precede the local commit). stdlib only.

Usage:  python scripts/closeout_sig.py [repo_root]
"""
import json
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
_HOOKS = os.path.join(ROOT, ".claude", "hooks")
if _HOOKS not in sys.path:
    sys.path.insert(0, _HOOKS)

import turn_state_snapshot as ts  # noqa: E402  (path set above)


def _prev_head():
    """prev_head the Stop hook will use to compute the moved-files component =
    the head recorded in the last machine_status snapshot (NOT the current HEAD).
    Reading it here keeps closeout_sig.py's path set identical to the hook's even
    across a commit (architect REAL_BUG fix)."""
    try:
        ms = json.load(open(os.path.join(ROOT, ".harness", "machine_status.json"),
                            encoding="utf-8"))
        return ms.get("head")
    except (OSError, ValueError):
        return None


def main():
    try:  # Windows cp949 stdout would crash on non-ASCII; emit UTF-8 (R1)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    paths, _head, _incomplete = ts.collect_changed_paths(ROOT, _prev_head())
    sig = ts.compute_signature(ROOT, ts._norm_set(paths))
    print(json.dumps({"signature": sig, "count": len(sig)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

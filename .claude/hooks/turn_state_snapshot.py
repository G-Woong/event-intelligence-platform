#!/usr/bin/env python
"""Stop hook: deterministic turn-state snapshot.

Writes ONLY ``.harness/machine_status.json`` (the "fact" layer, hook-exclusive).
The agent's freshness signal lives in a SEPARATE file
``.harness/narrative_marker.json`` (agent-exclusive, written by turn-closeout).
PROJECT_STATUS.md is authored only by the agent. So no file has two writers —
the R1 race is removed for real (not merely moved).

Responsibilities (deterministic, no LLM):
- classify changed files via ``git status --porcelain -z`` (untracked included,
  NUL-delimited so Korean/space/quoted paths never corrupt parsing) plus files
  moved by HEAD advancing since the last snapshot (R2).
- per-session monotonic turn counter kept in a map (survives worktree/session
  switches; payload carries no turn id) (R1/R5).
- detect file-path audit triggers (semantic triggers are the skill's job) (R2/B3).
- read cached test result, flag staleness vs current HEAD (R8).
- count open risks (severity via word-boundary, current severity = last in a
  ``HIGH->MEDIUM->LOW`` chain) from docs/_RISK/RISK_REGISTER.md.
- decide narrative_fresh by comparing the agent's marker to the prior turn
  (NOT mtime) (R5).
- emit a soft additionalContext nudge when changes exist and narrative is stale.
  Never blocks; never combines block + additionalContext (R6).

Fail-open: any error exits 0 silently. stdlib only. Runs under ``py``.
"""
import fnmatch
import json
import os
import re
import subprocess
import sys

_DEFAULT_CFG = {
    "enforce": "soft",
    "audit_loc_threshold": 40,
    "audit_files_threshold": 5,
    "archive_retention_turns": 30,
    "loc_whitelist": ["*.lock", "requirements*.lock*", "ingestion/outputs/**"],
    "status_path": "PROJECT_STATUS.md",
}

_CODE_PREFIXES = ("ingestion/", "backend/", "agents/", "workers/")
_SEV_RE = re.compile(r"\b(HIGH|MEDIUM|LOW)\b")
_MAX_SESSIONS = 200  # bound the turn map so it can't grow unbounded


def _git(args, cwd):
    """Run git; return UTF-8 stdout or '' on any failure (fail-open).

    Decodes explicitly as UTF-8 (not the locale codepage) so non-ASCII paths on
    a Korean Windows shell are not mangled.
    """
    try:
        r = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, timeout=8
        )
        if r.returncode != 0:
            return ""
        return r.stdout.decode("utf-8", "replace")
    except Exception:
        return ""


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _porcelain_paths(cwd):
    """Parse ``git status --porcelain -z`` into a set of repo-relative paths.

    -z makes records NUL-delimited with NO C-quoting/escaping, so spaces,
    quotes and Korean characters survive intact. Rename/copy records carry the
    original path as an extra NUL field which we consume (we keep the
    destination path).
    """
    out = _git(["-c", "core.quotePath=false", "status", "--porcelain", "-z"], cwd)
    tokens = out.split("\0")
    paths = set()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok or len(tok) < 4:
            i += 1
            continue
        xy, path = tok[:2], tok[3:]
        if path:
            paths.add(path)
        # rename/copy: the next NUL field is the original path -> skip it
        if "R" in xy or "C" in xy:
            i += 2
        else:
            i += 1
    return paths


def _matches_any(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def _classify(paths, whitelist):
    buckets = {"code": [], "docs": [], "config": [], "outputs": [], "other": []}
    code_files = []
    for p in sorted(paths):
        norm = p.replace("\\", "/")
        if norm.startswith("ingestion/outputs/"):
            buckets["outputs"].append(norm)
        elif norm.startswith(_CODE_PREFIXES) and norm.endswith(".py"):
            buckets["code"].append(norm)
            if not _matches_any(norm, whitelist):
                code_files.append(norm)
        elif norm.startswith("docs/") and norm.endswith(".md"):
            buckets["docs"].append(norm)
        elif norm.endswith((".json", ".toml", ".yml", ".yaml")) or ".claude/" in norm:
            buckets["config"].append(norm)
        else:
            buckets["other"].append(norm)
    return buckets, code_files


def _code_py_loc(cwd, whitelist):
    """Added+removed LOC for *tracked* code .py files (whitelist excluded).

    Untracked new files are not counted here (numstat only covers tracked
    changes); they are caught by the file-count and new-source triggers
    instead.
    """
    total = 0
    out = _git(["diff", "--numstat", "HEAD"], cwd)
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, path = parts
        norm = path.replace("\\", "/")
        if not (norm.startswith(_CODE_PREFIXES) and norm.endswith(".py")):
            continue
        if _matches_any(norm, whitelist):
            continue
        try:
            total += int(added) + int(removed)
        except ValueError:
            continue  # binary files report '-'
    return total


def _norm_set(paths):
    return {p.replace("\\", "/") for p in paths}


def _touched(norm_paths, *needles):
    return any(any(n in p for n in needles) for p in norm_paths)


def _new_source(norm_paths):
    return any(p.startswith("ingestion/sources/") for p in norm_paths)


def _is_narration_output(norm):
    """The closeout's own outputs. Excluded from the change signature so that
    (a) running closeout doesn't re-trigger its own nudge, and (b) a static
    dirty tree doesn't nudge every turn — only *new non-narration* work does.
    gitignored files (.harness/**, docs/_TRASH/**) never appear in porcelain,
    so they need no explicit exclusion."""
    n = norm.lower()
    return (
        n == "project_status.md"
        or n.startswith("docs/_decisions/")
        or n.startswith("docs/_risk/")
        or n.startswith("docs/_archive_superseded/")
    )


def _count_risks(path):
    """Count risk headings + current severity in RISK_REGISTER.md.

    RISK_REGISTER.md holds only open/partial risks by design (closed risks move
    to RISK_CLOSED.md), so every ``### `` heading is an open item. Severity uses
    word-boundary matching (so MEDIA/FOLLOW/HIGHLIGHT don't false-trip) and
    takes the LAST severity token on the line, which is the *current* severity
    in a ``HIGH->MEDIUM->LOW`` downgrade chain.
    """
    counts = {"total": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if not line.startswith("### "):
                    continue
                counts["total"] += 1
                seg = line.split("Severity:", 1)[1] if "Severity:" in line else line
                found = _SEV_RE.findall(seg.upper())
                if found:
                    counts[found[-1]] += 1
    except OSError:
        pass
    return counts


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()
    sid = payload.get("session_id") or "nosession"
    # Loop guard: during a stop-hook continuation, still record the snapshot
    # (a file write does not block), but never emit the nudge (stdout output
    # would re-block the turn and loop to the block cap).
    stop_active = bool(payload.get("stop_hook_active"))

    harness = os.path.join(cwd, ".harness")
    cfg = _read_json(os.path.join(harness, "config.json"), dict(_DEFAULT_CFG))
    for k, v in _DEFAULT_CFG.items():
        cfg.setdefault(k, v)
    prev = _read_json(os.path.join(harness, "machine_status.json"), {})

    # (R1/R5) per-session monotonic turn counter in a bounded map. Surviving a
    # different session writing in between (e.g. shared .harness) no longer
    # resets this session's counter.
    turns = dict(prev.get("turns", {}))
    prev_turn = turns.get(sid)  # this session's last turn, or None on first run
    turn = (prev_turn or 0) + 1
    turns[sid] = turn
    if len(turns) > _MAX_SESSIONS:  # drop oldest insertion-ordered entries
        for stale in list(turns)[: len(turns) - _MAX_SESSIONS]:
            turns.pop(stale, None)

    # (R2) delta = uncommitted (porcelain incl. untracked) + files moved by HEAD
    head = _git(["rev-parse", "HEAD"], cwd).strip()
    paths = _porcelain_paths(cwd)
    delta_incomplete = False
    prev_head = prev.get("head")
    if prev_head and head and prev_head != head:
        # (R3-fix) only diff if prev_head is still a reachable commit; after a
        # rebase/reset it may be gone -> flag instead of silently undercounting.
        try:
            valid = subprocess.run(
                ["git", "cat-file", "-e", prev_head + "^{commit}"],
                cwd=cwd, capture_output=True, timeout=8
            ).returncode == 0
        except Exception:
            valid = False
        if valid:
            moved = _git(["diff", "--name-only", prev_head, head], cwd)
            paths |= {ln.strip() for ln in moved.splitlines() if ln.strip()}
        else:
            delta_incomplete = True

    norm_paths = _norm_set(paths)
    whitelist = cfg.get("loc_whitelist", [])
    buckets, code_files = _classify(paths, whitelist)
    code_loc = _code_py_loc(cwd, whitelist)

    # file-path audit triggers only (semantic triggers belong to the skill)
    audit_required = bool(
        code_loc >= cfg["audit_loc_threshold"]
        or len(code_files) >= cfg["audit_files_threshold"]
        or _touched(norm_paths, ".claude/settings", ".env", ".claude/hooks")
        or _new_source(norm_paths)
    )

    # (R8) test cache + staleness vs current HEAD
    tc = _read_json(os.path.join(harness, "last_test_result.json"), None)
    test_stale = bool(tc) and bool(head) and tc.get("as_of_commit") != head

    risk = _count_risks(os.path.join(cwd, "docs", "_RISK", "RISK_REGISTER.md"))

    # (R5, rev3) change signature = sorted non-narration uncommitted paths.
    # Nudge keys off THIS, not the raw dirty-tree state, so a static dirty tree
    # stops nagging every turn (adversarial M2 fix). Narrative is "fresh" iff
    # the agent's marker recorded exactly the current signature — i.e. nothing
    # new (besides narration outputs) changed since the last closeout.
    sig = sorted(p for p in norm_paths if not _is_narration_output(p))
    marker = _read_json(os.path.join(harness, "narrative_marker.json"), {})
    narrative_fresh = bool(
        marker.get("session_id") == sid and marker.get("narrated_sig") == sig
    )

    status = {
        "session_id": sid,
        "turn": turn,
        "turns": turns,
        "head": head,
        "delta_incomplete": delta_incomplete,
        "changed_total": len(paths),
        "buckets_count": {k: len(v) for k, v in buckets.items()},
        "code_files": code_files,
        "code_py_loc": code_loc,
        "audit_required": audit_required,
        "tests": tc,
        "test_stale": test_stale,
        "risk": risk,
        "sig": sig,
        "narrative_fresh": narrative_fresh,
        # enforce is reserved; this hook is ALWAYS soft (never blocks). "block"
        # is unsupported until the stop_hook_active loop guard is verified (R6).
        "enforce": cfg.get("enforce", "soft"),
    }

    try:
        os.makedirs(harness, exist_ok=True)
        with open(os.path.join(harness, "machine_status.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(status, fh, ensure_ascii=False, indent=2)
    except OSError:
        return 0  # fail-open

    # (R6) soft nudge only — never block, never combine with a block decision.
    # Keyed off sig (new non-narration work since last closeout), not the raw
    # dirty tree, so a static uncommitted tree does not nag every turn.
    if sig and not narrative_fresh and not stop_active:
        msg = ("[turn-closeout 권장] 비-서술 변경 {n}건·미마감. "
               "PROJECT_STATUS/risk/_DECISIONS 갱신을 위해 turn-closeout 실행을 "
               "권장합니다.").format(n=len(sig))
        out = {"hookSpecificOutput": {"hookEventName": "Stop",
                                      "additionalContext": msg}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

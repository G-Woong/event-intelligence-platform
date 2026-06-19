#!/usr/bin/env python
"""Stop hook: deterministic turn-state snapshot.

Writes ONLY ``.harness/machine_status.json`` (the "fact" layer, hook-exclusive).
The agent's closeout evidence lives in a SEPARATE file
``.harness/closeout_stamp.json`` (agent-exclusive, written by turn-closeout) —
this hook only READS it for the stamp gate. PROJECT_STATUS.md is authored only
by the agent. So no file has two writers — the R1 race is removed for real.
(The earlier ``narrative_marker.json`` is superseded by closeout_stamp.json.)

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
import hashlib
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

# (R-CloseoutTrust phase-2) important file groups whose *content* — not just
# path — must be captured in the working-tree signature. A path-only signature
# missed content-only edits to an already-dirty file (R2): claim/risk-evidence/
# config changes under an unchanged path set passed the gate silently. These
# include narration-important files (RISK register, PROJECT_STATUS) on purpose;
# a content-only risk-evidence edit MUST re-trigger review.
_IMPORTANT_CONTENT = (
    "project_status.md",
    "docs/_risk/",
    "docs/_decisions/",
    "docs/_canonical/",
    "docs/harness_construction/",
    ".claude/hooks/",
    ".claude/skills/",
    ".claude/settings.json",
    "scripts/",
    "configs/",
    "tests/",
    ".harness/config.json",
)
_IMPORTANT_EXT = (".py", ".md", ".json", ".yaml", ".yml", ".toml", ".csv", ".txt")


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


def audit_types(norm_paths):
    """Map changed paths -> required review flags for the closeout orchestrator.

    The hook is a SENSOR: it only raises flags. The turn-closeout skill (the
    main agent) consumes them and actually calls the subagents / code-review
    skill. Dead-code/refactor review is a judgment the skill/scanner adds, not
    derivable from path alone, so it is not raised here.
    """
    f = set()
    for p in norm_paths:
        if ".claude/hooks" in p or ".claude/settings" in p or p.endswith(".ps1"):
            f |= {"harness_runtime_review", "security_review", "adversarial_review"}
        if p == ".env" or p.startswith(".env/") or "/.env" in p:
            f |= {"security_review", "adversarial_review"}
        if p.startswith("ingestion/") and p.endswith(".py"):
            f |= {"code_review", "pipeline_review", "test_review"}
        if any(k in p for k in ("source_registry", "rate_limit", "publication_policy", "retry_policy")):
            f |= {"source_integrity_review", "data_quality_review"}
        if p.startswith("docs/_ARCHIVE") or p.startswith("docs/_TRASH"):
            f |= {"docs_lifecycle_review", "destructive_action_review", "safety_review"}
        if p.startswith("docs/_RISK"):
            f |= {"risk_closure_review", "evidence_review"}
        if (p.startswith(("backend/", "agents/", "workers/")) and p.endswith(".py")):
            f |= {"code_review", "architecture_review", "test_review"}
    return sorted(f)


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


def _is_important(norm):
    """True if this changed path belongs to a content-tracked important group.
    Restricted to known text extensions so binary/large generated files are not
    hashed. May overlap with narration files (intentional — see _IMPORTANT_CONTENT)."""
    n = norm.lower()
    if not n.endswith(_IMPORTANT_EXT):
        return False
    return any(n == pat or n.startswith(pat) for pat in _IMPORTANT_CONTENT)


_MAX_HASH_BYTES = 4 * 1024 * 1024  # cap per-file hashing so a huge fixture/CSV
#                                    can't blow the Stop-hook timeout (architect
#                                    CONCERN). Oversize files are summarized by
#                                    size, which still changes when they change.


def _file_hash(path):
    """sha256 (first 16 hex) of a file's bytes; ``'size:<n>'`` for files over the
    cap; ``''`` if unreadable/deleted (then it drops out of the content
    signature, itself a change the gate notices). Catches *any* exception so the
    hook keeps its fail-open contract (architect CONCERN: non-OSError errors must
    not crash the Stop hook)."""
    try:
        if os.path.getsize(path) > _MAX_HASH_BYTES:
            return "size:%d" % os.path.getsize(path)
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except Exception:
        return ""


def collect_changed_paths(cwd, prev_head):
    """The authoritative changed-path set for the signature: uncommitted
    (porcelain, incl. untracked) PLUS files moved by HEAD advancing since the
    last snapshot (``prev_head``). Returns ``(paths_set, head, delta_incomplete)``.

    Extracted so the Stop hook AND ``scripts/closeout_sig.py`` build the signature
    from the *identical* path set — otherwise (architect REAL_BUG) a stamp written
    from a porcelain-only set would never match the hook's porcelain+moved set
    once a commit lands, leaving the gate stuck off."""
    head = _git(["rev-parse", "HEAD"], cwd).strip()
    paths = _porcelain_paths(cwd)
    delta_incomplete = False
    if prev_head and head and prev_head != head:
        # only diff if prev_head is still reachable; after a rebase/reset it may
        # be gone -> flag instead of silently undercounting.
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
    return paths, head, delta_incomplete


def compute_signature(cwd, norm_paths):
    """Canonical working-tree signature.

    Two components, concatenated:
    - path component: sorted non-narration changed paths (the "real work" signal;
      narration outputs the agent rewrites every closeout are excluded so closeout
      does not re-trigger its own nudge and a static dirty tree stops nagging).
    - content component: ``content:<path>#<hash>`` for every *important* changed
      file (incl. narration-important ones like the RISK register / PROJECT_STATUS).

    The content component closes R2: content-only edits under an unchanged path
    set were invisible to a path-only signature. Both the Stop hook and
    ``scripts/closeout_sig.py`` (which the agent runs at stamp time, AFTER its
    narration edits) call THIS function, so a correct closeout converges
    (stamp == hook recompute) while a later content-only edit diverges and
    re-triggers review. Committed content is captured separately by ``head``."""
    path_sig = sorted(p for p in norm_paths if not _is_narration_output(p))
    content_sig = []
    for p in sorted(norm_paths):
        if _is_important(p):
            digest = _file_hash(os.path.join(cwd, p.replace("/", os.sep)))
            if digest:
                content_sig.append("content:%s#%s" % (p, digest))
    return path_sig + content_sig


def _nudge_message(n_dirty, a_types):
    """ASCII-safe Stop-hook feedback (R1). Windows stdout is cp949; keeping the
    string pure-ASCII + json.dumps(ensure_ascii=True) guarantees it never
    mojibakes in PowerShell or Claude Code feedback. Detail stays Korean in
    PROJECT_STATUS."""
    extra = (" Required audits: " + ", ".join(a_types)) if a_types else ""
    return ("[turn-closeout] closeout incomplete (stamp mismatch): "
            "{n} uncommitted change(s). Run /turn-closeout to update "
            "PROJECT_STATUS/risk/_DECISIONS and route audits.{e}").format(
                n=n_dirty, e=extra)


def should_nudge(dirty_work, closeout_current, stop_active):
    """Nudge only for UNCOMMITTED non-narration work (R2): a post-commit
    HEAD-only advance (clean tree -> dirty_work empty) is benign and silent;
    a dirty tree (incl. content-only edits, which show up in porcelain) nudges.
    Never during a stop-hook continuation (loop guard)."""
    return bool(dirty_work) and not closeout_current and not stop_active


def _audit_attested(audit_type, evidence_by_type, has_unresolved):
    """R-CloseoutTrust gate: a required audit counts as addressed only if the
    stamp carries a STRUCTURED evidence record for it — executed=true AND a
    non-empty verdict — not merely the type name in audit_types_addressed.
    Unaddressed blocking findings must be surfaced in unresolved_required_actions
    (else the audit is not considered closed). This raises the bar from "list a
    type" to "produce a per-audit record"; it still cannot prove an LLM *really*
    reasoned (honest, documented limit)."""
    for e in evidence_by_type.get(audit_type, ()):
        if e.get("executed") is True and str(e.get("verdict", "")).strip():
            try:
                blocking = int(e.get("blocking_findings_count", 0) or 0)
                addressed = int(e.get("addressed_findings_count", 0) or 0)
            except (TypeError, ValueError):
                blocking, addressed = 0, 0
            if blocking > addressed and not has_unresolved:
                continue  # open blocking findings not surfaced -> not closed
            return True
    return False


_REQUIRED_HOOKS = {
    "PreToolUse": {"forbidden_command_guard.py"},
    "PostToolUse": {"audit_flagger.py"},
    "Stop": {"secret_scan_reminder.py", "docs_conflict_grep_check.py",
             "turn_state_snapshot.py"},
}


def _settings_health(cwd):
    """Loop-safe self-check: is every required hook still registered in
    settings.json? (settings.json is gitignored, so on a fresh clone it is
    absent and the harness is inert — R-HarnessReproducibility.) Returns a small
    summary recorded into machine_status; emits NO stdout (no Stop loop). Full
    diagnosis: scripts/harness_doctor.py."""
    path = os.path.join(cwd, ".claude", "settings.json")
    try:
        settings = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "missing": ["settings.json"]}
    missing = []
    hooks = settings.get("hooks") or {}
    for event, required in _REQUIRED_HOOKS.items():
        seen = set()
        for g in hooks.get(event, []) or []:
            for h in g.get("hooks", []) or []:
                for a in h.get("args", []) or []:
                    if isinstance(a, str):
                        seen.add(os.path.basename(a))
        for r in required:
            if r not in seen:
                missing.append("%s/%s" % (event, r))
    return {"ok": not missing, "missing": sorted(missing)}


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

    # (R2) delta = uncommitted (porcelain incl. untracked) + files moved by HEAD.
    # Shared with scripts/closeout_sig.py so stamp & gate use the same path set.
    prev_head = prev.get("head")
    paths, head, delta_incomplete = collect_changed_paths(cwd, prev_head)
    # uncommitted-only set, kept separate so the NUDGE keys off real dirty work
    # (not files already committed since the last snapshot) — closes the
    # commit-time transient nudge (R2): a clean tree where only HEAD advanced
    # does not nag, while a dirty working tree still does.
    uncommitted = _norm_set(_porcelain_paths(cwd))

    norm_paths = _norm_set(paths)
    whitelist = cfg.get("loc_whitelist", [])
    buckets, code_files = _classify(paths, whitelist)
    code_loc = _code_py_loc(cwd, whitelist)

    # file-path audit triggers (semantic triggers belong to the skill). The
    # per-type flags below are the SENSOR output the closeout orchestrator
    # consumes to route subagents.
    a_types = audit_types(norm_paths)
    audit_required = bool(
        a_types
        or code_loc >= cfg["audit_loc_threshold"]
        or len(code_files) >= cfg["audit_files_threshold"]
        or _new_source(norm_paths)
    )

    # (R8) test cache + staleness vs current HEAD
    tc = _read_json(os.path.join(harness, "last_test_result.json"), None)
    test_stale = bool(tc) and bool(head) and tc.get("as_of_commit") != head

    risk = _count_risks(os.path.join(cwd, "docs", "_RISK", "RISK_REGISTER.md"))

    # (R5, rev3 + R-CloseoutTrust phase-2) change signature = non-narration
    # uncommitted paths PLUS content hashes of important changed files. Nudge
    # keys off THIS, not the raw dirty-tree state, so a static dirty tree stops
    # nagging every turn (adversarial M2 fix); content hashes additionally catch
    # content-only edits the path-only sig missed (R2).
    sig = compute_signature(cwd, norm_paths)

    # (Option C: stamp-gated) closeout is "current" iff the agent's
    # closeout_stamp recorded exactly this working-tree signature for this
    # session, left no unresolved required actions, AND addressed every audit
    # type the SENSOR (this hook) objectively requires. The required set
    # (a_types) is hook-computed, so the agent cannot hide a required audit by
    # omitting it from the stamp — a skipped audit leaves a_types ⊄ addressed
    # and the gate fails (closes the "self-report skips audit" gap raised by
    # the orchestrator/adversarial review). NOTE: the gate enforces COVERAGE of
    # required types; it still trusts the agent's claim that a listed audit was
    # actually performed (no hook can verify an LLM "really" reasoned). This is
    # an honest limit, documented in 05 / R-CloseoutTrust.
    stamp = _read_json(os.path.join(harness, "closeout_stamp.json"), {})
    addressed = set(stamp.get("audit_types_addressed", []))
    audit_covered = set(a_types).issubset(addressed)
    # (R-CloseoutTrust phase-1) coverage is necessary but no longer sufficient:
    # each required audit must also carry a STRUCTURED evidence record in the
    # stamp (executed=true + verdict). A bare audit_types_addressed list or a
    # self-reported code_review_completed=true no longer passes the gate.
    ev_list = stamp.get("audit_evidence", [])
    evidence_by_type = {}
    if isinstance(ev_list, list):
        for e in ev_list:
            if isinstance(e, dict) and e.get("audit_type"):
                evidence_by_type.setdefault(e["audit_type"], []).append(e)
    has_unresolved = bool(stamp.get("unresolved_required_actions"))
    audit_attested = all(
        _audit_attested(t, evidence_by_type, has_unresolved) for t in a_types
    )
    closeout_current = bool(
        stamp.get("session_id") == sid
        and stamp.get("working_tree_signature") == sig
        and not stamp.get("unresolved_required_actions")
        and audit_covered
        and audit_attested
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
        "audit_types": a_types,
        "tests": tc,
        "test_stale": test_stale,
        "risk": risk,
        "sig": sig,
        "audit_covered": audit_covered,
        "audit_attested": audit_attested,
        "settings_health": _settings_health(cwd),
        "closeout_current": closeout_current,
        "narrative_fresh": closeout_current,  # back-compat alias
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
    # (R2) keyed off UNCOMMITTED non-narration work, NOT the full sig: a
    # post-commit HEAD-only advance leaves a clean tree (uncommitted empty) and
    # must not nag, while a dirty tree (incl. content-only edits, which appear in
    # porcelain) still does. (R1) ASCII-safe English output — Windows stdout is
    # cp949, so ensure_ascii=True keeps the bytes pure-ASCII and the feedback
    # never mojibakes across PowerShell/Claude Code. Detail stays Korean in
    # PROJECT_STATUS. stop_hook_active=true is always silent (loop guard).
    dirty_work = [p for p in uncommitted if not _is_narration_output(p)]
    if should_nudge(dirty_work, closeout_current, stop_active):
        out = {"hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": _nudge_message(len(dirty_work), a_types)}}
        sys.stdout.write(json.dumps(out))  # ascii-safe (no ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())

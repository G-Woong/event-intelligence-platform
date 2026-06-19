#!/usr/bin/env python
"""Docs lifecycle audit (READ-ONLY, DRY-RUN — never moves, never writes a trash
manifest). Web-intelligence harness, Req 2 (docs lifecycle as a *tested* policy).

For every doc it answers: what role does it play, where in the lifecycle should it
flow (keep / overwrite / monthly_compact / archive / trash), is it PROTECTED from
moving, and what test invariant pins that down. The output
(``.harness/docs_lifecycle_audit.json``) is the source the lifecycle TESTS assert
against (``tests/test_docs_lifecycle.py``), so "where a doc flows after it is
written" is frozen as code, not prose.

Movement is opt-in and explicit: a non-protected doc becomes an archive/trash
*candidate* ONLY if it carries a machine marker ``<!-- LIFECYCLE: superseded -->``
/ ``<!-- LIFECYCLE: dead -->`` (or sits in the archive dir). Keyword heuristics are
deliberately NOT used (a doc mentioning "superseded" or carrying a *partial*
SUPERSEDED banner is still active). ``sweep_dry_run`` always reports
``moves_applied=0`` and ``manifests_created=0`` — applying moves is the
turn-closeout skill's job, gated by team audit + explicit confirm, never here.

stdlib only.  Usage:  python scripts/docs_lifecycle_audit.py [repo_root]
"""
import json
import os
import re
import sys

LIFECYCLE_MARKER_RE = re.compile(
    r"<!--\s*LIFECYCLE:\s*(superseded|dead|archive|trash)\s*-->", re.I)

# --- protection rules (move_allowed = not protected) ---
PROTECTED_EXACT = {
    "PROJECT_STATUS.md", "README.md", "CLAUDE.md",
    "docs/_RISK/RISK_REGISTER.md", "docs/_RISK/RISK_CLOSED.md",
    "docs/_ARCHIVE_SUPERSEDED/_INDEX.md",
    # immutable contract specs (02 §A.1: 계약 스펙 불변 문서는 lifecycle 대상 아님)
    "docs/API_CONTRACT.md", "docs/EVENT_SCHEMA.md",
    "docs/COMPLIANCE_BOUNDARY.md", "docs/DATA_POLICY.md",
    # source-registry / ingestion canonical specs (web-intelligence backbone)
    "docs/ingestion/INGESTION_FINAL.md", "docs/COLLECTOR_DESIGN.md",
    "ingestion/plans/06_SOURCE_REGISTRY_DESIGN.md",
    "docs/Orchestration_Construction/02_SOURCE_ROLE_AND_PURPOSE_ROUTING.md",
    "docs/Orchestration_Construction/03_COLLECTION_STRATEGY_ROUTER_DESIGN.md",
}
PROTECTED_PREFIX = ("docs/_RISK/", "docs/_CANONICAL/", "docs/_DECISIONS/")

SOURCE_REGISTRY_SPECS = {
    "docs/ingestion/INGESTION_FINAL.md", "docs/COLLECTOR_DESIGN.md",
    "ingestion/plans/06_SOURCE_REGISTRY_DESIGN.md",
    "docs/Orchestration_Construction/02_SOURCE_ROLE_AND_PURPOSE_ROUTING.md",
    "docs/Orchestration_Construction/03_COLLECTION_STRATEGY_ROUTER_DESIGN.md",
}
CONTRACT_SPECS = {
    "docs/API_CONTRACT.md", "docs/EVENT_SCHEMA.md",
    "docs/COMPLIANCE_BOUNDARY.md", "docs/DATA_POLICY.md",
}
IMPL_SPEC_PREFIX = (
    "docs/Harness_Construction/", "docs/Orchestration_Construction/",
    "docs/Implementation_Instructions/", "docs/system_overview/",
    "docs/Environment_setup/", "docs/ingestion/",
)


def _is_protected(rel):
    if rel in PROTECTED_EXACT:
        return True
    if rel == "README.md" or rel.endswith("/README.md"):
        return True  # entry-point READMEs are never auto-move candidates
    # authoritative area-detail docs (권위 ③): *_FINAL.md + the single artifact
    # manifest are never auto-move candidates (curator GAP).
    base = os.path.basename(rel).lower()
    if base.endswith("_final.md") or base == "artifact_manifest_final.md":
        return True
    return any(rel.startswith(p) for p in PROTECTED_PREFIX)


def _role(rel):
    if rel == "PROJECT_STATUS.md":
        return "report"
    if rel in ("docs/_RISK/RISK_REGISTER.md", "docs/_RISK/RISK_CLOSED.md"):
        return "risk_log"
    if rel.startswith("docs/_DECISIONS/"):
        return "decision_log"
    if rel == "docs/_ARCHIVE_SUPERSEDED/_INDEX.md":
        return "tombstone_index"
    if rel.startswith("docs/_ARCHIVE_SUPERSEDED/"):
        return "archived"
    if rel.startswith("docs/_TRASH/"):
        return "trashed"
    if rel.startswith("docs/_CANONICAL/"):
        return "canonical"
    if rel in CONTRACT_SPECS:
        return "contract_spec"
    if rel in SOURCE_REGISTRY_SPECS:
        return "source_registry_spec"
    if rel in ("README.md", "CLAUDE.md") or rel.endswith("/README.md"):
        return "canonical"
    if rel.startswith("docs/_IDEATION_WEB_INTELLIGENCE/"):
        return "ideation"
    if rel.startswith("plans/") or rel.startswith("ingestion/plans/"):
        return "plan_report"
    if rel.startswith(IMPL_SPEC_PREFIX):
        return "implementation_spec"
    return "active"


def _expected_lifecycle(role, marker):
    if marker in ("superseded", "archive"):
        return "archive"
    if marker in ("dead", "trash"):
        return "trash"
    return {
        "report": "overwrite",
        "risk_log": "keep",
        "decision_log": "monthly_compact",
        "canonical": "keep",
        "contract_spec": "keep",
        "source_registry_spec": "keep",
        "tombstone_index": "keep",
        "archived": "trash_candidate_after_retention",
        "trashed": "keep",
    }.get(role, "keep")


def classify(rel, content):
    role = _role(rel)
    protected = _is_protected(rel)
    m = LIFECYCLE_MARKER_RE.search(content or "")
    marker = m.group(1).lower() if m else None
    move_allowed = not protected
    expected = _expected_lifecycle(role, marker)
    is_archive_candidate = move_allowed and marker in ("superseded", "archive")
    is_trash_candidate = move_allowed and marker in ("dead", "trash")
    if protected:
        assertion = "PROTECTED: never an archive/trash candidate; move_allowed=False"
    elif role in ("implementation_spec", "ideation", "plan_report", "active"):
        assertion = "archive/trash only via explicit LIFECYCLE marker + team audit + confirm"
    elif role == "archived":
        assertion = "trash candidate only after retention + confirm; index keeps 1-line tombstone"
    else:
        assertion = "keep"
    return {
        "path": rel,
        "current_role": role,
        "expected_lifecycle": expected,
        "lifecycle_marker": marker,
        "protected": protected,
        "move_allowed": move_allowed,
        "is_archive_candidate": is_archive_candidate,
        "is_trash_candidate": is_trash_candidate,
        "trigger_condition": ("LIFECYCLE marker present" if marker else
                              "none (stays in place)"),
        "reason": "role=%s protected=%s marker=%s" % (role, protected, marker),
        "test_assertion": assertion,
    }


def _doc_paths(root):
    """Tracked-like doc set: every .md under docs/ plus root status/readme docs.
    Walk filesystem (stdlib only, no git dependency)."""
    out = []
    # documentation corpus: docs/ + ingestion (source-registry/pipeline specs) +
    # plans/ (plan-reports). .claude/ + agents/prompts are code-adjacent config,
    # not memory docs -> out of lifecycle scope.
    roots = [os.path.join(root, d) for d in ("docs", "ingestion", "plans")]
    for base in roots:
        if not os.path.isdir(base):
            continue
        for dp, dns, fns in os.walk(base):
            dns[:] = [d for d in dns if d not in
                      {".git", "__pycache__", "outputs", "logs", ".venv",
                       "node_modules"}]
            for fn in fns:
                if fn.endswith(".md"):
                    out.append(os.path.relpath(os.path.join(dp, fn), root)
                               .replace("\\", "/"))
    for top in ("PROJECT_STATUS.md", "README.md", "CLAUDE.md"):
        if os.path.isfile(os.path.join(root, top)):
            out.append(top)
    return sorted(set(out))


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def audit(root):
    docs = []
    for rel in _doc_paths(root):
        docs.append(classify(rel, _read(os.path.join(root, rel.replace("/", os.sep)))))
    totals = {}
    for d in docs:
        totals[d["current_role"]] = totals.get(d["current_role"], 0) + 1
    return {
        "schema_version": 1,
        "docs_count": len(docs),
        "totals_by_role": totals,
        "protected_count": sum(1 for d in docs if d["protected"]),
        "move_allowed_count": sum(1 for d in docs if d["move_allowed"]),
        "docs": docs,
    }


def sweep_dry_run(root):
    """What a sweep WOULD do — and proof it does nothing destructive. This
    function never moves a file and never writes a trash manifest; the counters
    are hard-zero by construction. ``conflicts`` lists protected docs that somehow
    carry a dead/superseded marker (a safety violation the tests must catch)."""
    a = audit(root)
    archive = [d["path"] for d in a["docs"] if d["is_archive_candidate"]]
    trash = [d["path"] for d in a["docs"] if d["is_trash_candidate"]]
    conflicts = [d["path"] for d in a["docs"]
                 if d["protected"] and d["lifecycle_marker"] in ("dead", "trash", "superseded", "archive")]
    return {
        "archive_candidates": sorted(archive),
        "trash_candidates": sorted(trash),
        "protected_count": a["protected_count"],
        "moves_applied": 0,         # this tool NEVER moves (apply is the skill's job)
        "manifests_created": 0,     # no manifest/restore/shard/index ever written
        "conflicts": sorted(conflicts),
    }


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    result = audit(root)
    result["sweep_dry_run"] = sweep_dry_run(root)
    out_dir = os.path.join(root, ".harness")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "docs_lifecycle_audit.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    s = result["sweep_dry_run"]
    print("docs_lifecycle_audit: %d docs, %d protected | dry-run archive=%d trash=%d "
          "moves=%d manifests=%d conflicts=%d -> %s"
          % (result["docs_count"], result["protected_count"],
             len(s["archive_candidates"]), len(s["trash_candidates"]),
             s["moves_applied"], s["manifests_created"], len(s["conflicts"]), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

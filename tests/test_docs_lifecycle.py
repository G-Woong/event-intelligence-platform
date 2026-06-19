"""Docs lifecycle audit-as-test (web-intelligence harness, Req 2).

Freezes "where a doc flows after it is written" as executable invariants instead
of prose: protected docs never become move candidates, movement is dry-run +
marker-gated, no trash manifest is ever written, the decision log stays a monthly
ledger, and stale-doc risk is registered. Backed by
``scripts/docs_lifecycle_audit.py`` (read-only classifier). Infra-free (no docker
/ no services), so it runs in the default ``pytest tests`` set.

SCOPE (honest, per adversarial review): these tests freeze the *classifier
contract* (role/protection/marker-gating) and real on-disk invariants (no trash
manifest on disk, decision log is a monthly ledger, stale-doc risk registered).
They do NOT test the turn-closeout *skill* that actually performs Move-Item — the
classifier never moves files (``moves_applied`` is 0 by construction). The skill's
move safety is gated separately by team audit + explicit confirm, not here.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import docs_lifecycle_audit as dla  # noqa: E402


@pytest.fixture(scope="module")
def report():
    return dla.audit(ROOT)


@pytest.fixture(scope="module")
def sweep():
    return dla.sweep_dry_run(ROOT)


def _by_path(report, path):
    for d in report["docs"]:
        if d["path"] == path:
            return d
    return None


# 1 — PROJECT_STATUS.md never archive/trash candidate, protected, immovable
def test_project_status_protected(report):
    d = _by_path(report, "PROJECT_STATUS.md")
    assert d is not None
    assert d["protected"] and not d["move_allowed"]
    assert not d["is_archive_candidate"] and not d["is_trash_candidate"]


# 2 — RISK register + closed log never archive/trash candidate
@pytest.mark.parametrize("path", ["docs/_RISK/RISK_REGISTER.md", "docs/_RISK/RISK_CLOSED.md"])
def test_risk_logs_protected(report, path):
    d = _by_path(report, path)
    assert d is not None, path
    assert d["protected"] and not d["move_allowed"]
    assert not d["is_archive_candidate"] and not d["is_trash_candidate"]


# 3 — README protected
def test_readme_protected(report):
    d = _by_path(report, "README.md")
    assert d is not None and d["protected"]


# 4 — canonical docs protected; no active/canonical doc is a live candidate
def test_canonical_protected_and_no_active_candidates(report):
    canon = [d for d in report["docs"] if d["current_role"] == "canonical"]
    assert canon, "expected canonical docs"
    assert all(d["protected"] for d in canon)
    for d in report["docs"]:
        if d["current_role"] in ("canonical", "active"):
            assert not d["is_archive_candidate"] and not d["is_trash_candidate"], d["path"]


# 5 — superseded docs become DRY-RUN archive candidates only (marker-gated)
def test_superseded_marker_makes_archive_candidate():
    c = dla.classify("docs/system_overview/99_OLD.md", "x\n<!-- LIFECYCLE: superseded -->\n")
    assert c["is_archive_candidate"] and not c["is_trash_candidate"]
    assert c["expected_lifecycle"] == "archive"
    # a protected doc with the SAME marker must NOT become a candidate (safety override)
    cp = dla.classify("docs/_RISK/RISK_REGISTER.md", "<!-- LIFECYCLE: superseded -->")
    assert not cp["is_archive_candidate"]


# 6 — dead docs become DRY-RUN trash candidates only (marker-gated)
def test_dead_marker_makes_trash_candidate():
    c = dla.classify("docs/system_overview/99_DEAD.md", "<!-- LIFECYCLE: dead -->")
    assert c["is_trash_candidate"] and not c["is_archive_candidate"]
    assert c["expected_lifecycle"] == "trash"


# 7 — apply/confirm absent => zero real moves
def test_sweep_applies_no_moves(sweep):
    assert sweep["moves_applied"] == 0


# 8 — no trash manifest/restore/shard/index ever created (counter + on-disk)
def test_no_trash_manifest(sweep):
    assert sweep["manifests_created"] == 0
    trash = os.path.join(ROOT, "docs", "_TRASH")
    if os.path.isdir(trash):
        for fn in os.listdir(trash):
            low = fn.lower()
            assert not any(k in low for k in ("manifest", "restore", "shard", "index")), fn


# 9 — decision log is a monthly ledger (no per-session md proliferation)
def test_decisions_monthly_ledger():
    dec = os.path.join(ROOT, "docs", "_DECISIONS")
    assert os.path.isdir(dec)
    mds = [f for f in os.listdir(dec) if f.endswith(".md")]
    assert mds, "expected at least one monthly ledger"
    for f in mds:
        assert re.fullmatch(r"\d{4}-\d{2}\.md", f), "non-monthly decision file: %s" % f


# 10 — audit/sweep conflict (protected doc carrying a move marker) is detected
def test_conflict_detection(monkeypatch):
    assert dla.sweep_dry_run(ROOT)["conflicts"] == []  # clean repo today
    # synthetic: a protected doc that wrongly carries a dead marker is a conflict.
    # Inject it into the audit so sweep_dry_run actually surfaces it in conflicts
    # (not just classify() in isolation) — exercises the non-empty path.
    real_audit = dla.audit

    def fake_audit(root):
        rep = real_audit(root)
        rep["docs"].append(dla.classify("docs/_RISK/RISK_REGISTER.md",
                                        "<!-- LIFECYCLE: dead -->"))
        return rep

    monkeypatch.setattr(dla, "audit", fake_audit)
    sweep = dla.sweep_dry_run(ROOT)
    assert "docs/_RISK/RISK_REGISTER.md" in sweep["conflicts"]
    assert sweep["trash_candidates"] == []  # protection still wins, no candidate
    assert sweep["moves_applied"] == 0


# 13 — immutable contract specs are protected & immovable
@pytest.mark.parametrize("path", [
    "docs/API_CONTRACT.md", "docs/EVENT_SCHEMA.md",
    "docs/DATA_POLICY.md", "docs/COMPLIANCE_BOUNDARY.md"])
def test_contract_specs_protected(report, path):
    d = _by_path(report, path)
    assert d is not None, path
    assert d["protected"] and not d["move_allowed"], path
    assert not d["is_archive_candidate"] and not d["is_trash_candidate"], path


# 14 — authoritative *_FINAL / artifact-manifest docs are protected (curator GAP)
def test_final_and_manifest_docs_protected(report):
    finals = [d for d in report["docs"]
              if d["path"].lower().endswith("_final.md")
              or os.path.basename(d["path"]).lower() == "artifact_manifest_final.md"]
    assert len(finals) >= 3, "expected several *_FINAL docs"
    for d in finals:
        assert d["protected"] and not d["move_allowed"], d["path"]


# 11 — stale-doc drift is registered as a risk (not silently left active)
def test_stale_docs_risk_registered():
    reg = os.path.join(ROOT, "docs", "_RISK", "RISK_REGISTER.md")
    txt = open(reg, encoding="utf-8", errors="ignore").read()
    assert "R-StaleDocs" in txt


# 12 — source-registry / ingestion-canonical docs are protected & immovable
def test_source_registry_specs_protected(report):
    specs = [d for d in report["docs"] if d["current_role"] == "source_registry_spec"]
    assert specs, "expected source_registry_spec docs"
    for d in specs:
        assert d["protected"] and not d["move_allowed"], d["path"]
        assert not d["is_archive_candidate"] and not d["is_trash_candidate"], d["path"]


# meta — every doc carries the full audit schema (so the manifest is test-usable)
def test_audit_schema_complete(report):
    required = {"path", "current_role", "expected_lifecycle", "protected",
               "move_allowed", "is_archive_candidate", "is_trash_candidate",
               "trigger_condition", "reason", "test_assertion"}
    assert report["docs"]
    for d in report["docs"]:
        assert required.issubset(d.keys()), d.get("path")

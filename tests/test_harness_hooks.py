"""Harness operational-stability tests (web-intelligence turn-closeout).

Freezes the operational invariants closed this cleanup phase:
- R1: Stop-hook feedback is ASCII-safe (never mojibakes on Windows cp949 stdout).
- R2: a post-commit HEAD-only advance (clean tree) does NOT nudge, while a dirty
  tree (incl. content-only edits) does.
- harness_doctor catches a missing/!registered hook.
- dead-code scan emits a deterministic, schema-stable artifact.
Infra-free (no docker/services).
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import turn_state_snapshot as ts  # noqa: E402
import harness_doctor as doc  # noqa: E402


# --- R2: nudge keys off uncommitted work, not committed/HEAD-advanced files ---
def test_nudge_suppressed_on_clean_tree():
    # HEAD-only advance leaves dirty_work empty -> benign, no nudge even if the
    # stamp gate is not "current" (closeout_current False).
    assert ts.should_nudge([], False, False) is False


def test_nudge_fires_on_dirty_work():
    assert ts.should_nudge(["ingestion/foo.py"], False, False) is True


def test_nudge_suppressed_when_current():
    assert ts.should_nudge(["ingestion/foo.py"], True, False) is False


def test_nudge_suppressed_under_loop_guard():
    assert ts.should_nudge(["ingestion/foo.py"], False, True) is False


# --- R1: feedback message is pure ASCII (no mojibake possible) ---
def test_nudge_message_is_ascii():
    msg = ts._nudge_message(3, ["code_review", "security_review"])
    msg.encode("ascii")  # raises if any non-ASCII slips in
    assert msg.startswith("[turn-closeout]")
    assert "3 uncommitted change(s)" in msg


def test_stop_hook_stdout_is_ascii(tmp_path):
    # drive the real hook with a dirty non-narration file; its stdout must decode
    # as strict ASCII (this is exactly what Claude Code / PowerShell consume).
    probe = os.path.join(ROOT, "scripts", "_zz_ascii_probe.py")
    open(probe, "w", encoding="utf-8").write("# ascii probe\n")
    try:
        r = subprocess.run([sys.executable, ts.__file__],
                           input=b'{"session_id":"ascii-test"}',
                           capture_output=True, cwd=ROOT)
        r.stdout.decode("ascii")  # strict: raises on any non-ASCII byte
        if r.stdout.strip():
            payload = json.loads(r.stdout.decode("ascii"))
            assert "turn-closeout" in payload["hookSpecificOutput"]["additionalContext"]
    finally:
        os.remove(probe)


def test_stop_hook_empty_input_failopen():
    r = subprocess.run([sys.executable, ts.__file__], input=b"",
                       capture_output=True, cwd=ROOT)
    assert r.returncode == 0


# --- harness_doctor catches a missing required hook ---
def test_doctor_flags_missing_hook(tmp_path):
    # build a settings.json missing the Stop turn_state_snapshot registration
    claude = tmp_path / ".claude"
    hooks = claude / "hooks"
    hooks.mkdir(parents=True)
    for name in doc.REQUIRED:  # create the hook files so only registration is missing
        (hooks / name).write_text("# stop_hook_active\n", encoding="utf-8")
    settings = {
        "hooks": {
            "PreToolUse": [{"hooks": [{"args": [str(hooks / "forbidden_command_guard.py")]}]}],
            # PostToolUse + Stop intentionally omitted -> doctor must FAIL
        }
    }
    (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    rc = doc.main.__wrapped__ if hasattr(doc.main, "__wrapped__") else None  # noqa
    # call main() with the temp root via argv
    out = subprocess.run([sys.executable, doc.__file__, str(tmp_path)],
                         capture_output=True, cwd=ROOT)
    assert out.returncode == 1  # missing registrations -> FAIL
    assert b"FAIL" in out.stdout


def test_doctor_missing_settings_fails(tmp_path):
    (tmp_path / ".claude").mkdir()
    out = subprocess.run([sys.executable, doc.__file__, str(tmp_path)],
                         capture_output=True, cwd=ROOT)
    assert out.returncode == 1
    assert b"MISSING .claude/settings.json" in out.stdout


def test_doctor_passes_on_real_repo():
    out = subprocess.run([sys.executable, doc.__file__, ROOT],
                         capture_output=True, cwd=ROOT)
    assert out.returncode == 0
    assert b"PASS" in out.stdout


# --- dead-code scan is deterministic + schema-stable ---
def test_dead_code_scan_deterministic():
    import dead_code_scan as dc
    r1 = dc.scan(ROOT)
    r2 = dc.scan(ROOT)
    assert r1["candidate_count"] == r2["candidate_count"]
    assert r1["candidates_by_category"] == r2["candidates_by_category"]
    for c in r1["candidates"]:
        assert {"path", "kind", "confidence", "category",
                "deletion_allowed"}.issubset(c.keys())
        assert c["deletion_allowed"] is False  # never auto-delete

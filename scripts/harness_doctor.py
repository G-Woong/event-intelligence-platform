#!/usr/bin/env python
"""Harness reproducibility doctor (R-HarnessReproducibility).

``.claude/settings.json`` is **gitignored** (``.gitignore`` ignores ``.claude/*``
and only re-includes ``agents/``, ``skills/``, ``hooks/``). So a fresh clone /
another machine / a codex worktree gets the hook *scripts* but NOT the
``settings.json`` that REGISTERS them — the turn-closeout harness then silently
does nothing (no Stop snapshot, no PostToolUse audit flags, no forbidden-command
guard) with no error. This doctor detects that drift and prints remediation.

Run manually (NEVER from a Stop hook — output there would loop):
    python scripts/harness_doctor.py

Exit 0 = all required wiring present; exit 1 = at least one FAIL. stdlib only.
"""
import json
import os
import sys

# required hook script -> the settings.json event it must be registered under
REQUIRED = {
    "forbidden_command_guard.py": "PreToolUse",
    "audit_flagger.py": "PostToolUse",
    "secret_scan_reminder.py": "Stop",
    "docs_conflict_grep_check.py": "Stop",
    "turn_state_snapshot.py": "Stop",
}
STOP_GUARD_REQUIRED = {  # Stop hooks that MUST carry the loop guard
    "secret_scan_reminder.py", "docs_conflict_grep_check.py", "turn_state_snapshot.py",
}


def _registered_hooks(settings):
    """Map event -> set(hook script basenames) registered in settings.json."""
    out = {}
    for event, groups in (settings.get("hooks") or {}).items():
        names = set()
        for g in groups or []:
            for h in g.get("hooks", []) or []:
                for a in h.get("args", []) or []:
                    if isinstance(a, str) and a.endswith(".py"):
                        names.add(os.path.basename(a))
        out[event] = names
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    fails, warns, oks = [], [], []
    hooks_dir = os.path.join(root, ".claude", "hooks")
    settings_path = os.path.join(root, ".claude", "settings.json")

    # 1) settings.json present (the gitignored single point of failure)
    if not os.path.isfile(settings_path):
        fails.append(
            "MISSING .claude/settings.json (gitignored — NOT restored by clone). "
            "The harness is INERT until it is recreated. Remediation: copy from a "
            "machine that has it, or recreate from docs/Harness_Construction/05 "
            "(hooks block) + README 'Harness setup'.")
        _report(fails, warns, oks)
        return 1
    try:
        settings = json.load(open(settings_path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        fails.append("settings.json unreadable/invalid JSON: %s" % e)
        _report(fails, warns, oks)
        return 1
    oks.append(".claude/settings.json present and valid JSON")

    reg = _registered_hooks(settings)

    # 2) every required hook registered under the right event + 3) file exists
    for script, event in REQUIRED.items():
        if script not in reg.get(event, set()):
            fails.append("hook NOT registered under %s: %s "
                         "(add it to settings.json hooks.%s)" % (event, script, event))
        else:
            oks.append("registered %s -> %s" % (event, script))
        if not os.path.isfile(os.path.join(hooks_dir, script)):
            fails.append("hook script file missing on disk: .claude/hooks/%s" % script)

    # 4) Stop hooks carry the stop_hook_active loop guard
    for script in STOP_GUARD_REQUIRED:
        p = os.path.join(hooks_dir, script)
        if os.path.isfile(p):
            txt = open(p, encoding="utf-8", errors="ignore").read()
            if "stop_hook_active" not in txt:
                fails.append("Stop hook %s lacks stop_hook_active loop guard "
                             "(infinite-loop risk)" % script)
            else:
                oks.append("loop guard present: %s" % script)

    # 5) tracked harness config present
    if os.path.isfile(os.path.join(root, ".harness", "config.json")):
        oks.append(".harness/config.json present")
    else:
        warns.append(".harness/config.json missing (defaults will be used)")

    # 6) helper used by the closeout stamp
    if not os.path.isfile(os.path.join(root, "scripts", "closeout_sig.py")):
        warns.append("scripts/closeout_sig.py missing (stamp signature helper)")

    rc = 1 if fails else 0
    _report(fails, warns, oks)
    return rc


def _report(fails, warns, oks):
    print("=== harness doctor ===")
    for o in oks:
        print("  OK   %s" % o)
    for w in warns:
        print("  WARN %s" % w)
    for f in fails:
        print("  FAIL %s" % f)
    print("verdict: %s (%d ok, %d warn, %d fail)"
          % ("PASS" if not fails else "FAIL", len(oks), len(warns), len(fails)))


if __name__ == "__main__":
    sys.exit(main())

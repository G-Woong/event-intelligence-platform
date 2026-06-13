#!/usr/bin/env python
"""PreToolUse hook: block destructive Bash/PowerShell commands.

Reads the Claude Code hook payload from stdin (JSON), inspects
``tool_input.command``, and denies execution of destructive patterns by
emitting a ``permissionDecision: "deny"`` decision on stdout (exit 0).

Design notes:
- Fail-OPEN: on any parse/IO error we exit 0 with no decision so that a
  malformed payload never blocks normal development (constraint: hooks must
  not block legitimate commands).
- Patterns mirror the repo's CLAUDE.md / settings.json deny policy. This hook
  is defense-in-depth on top of the permission deny list, not a replacement.
- stdlib only; runs under any Python 3.
"""
import json
import re
import sys

# Command-position prefix: start-of-string or immediately after a shell
# command separator (newline, ;, &, |). This is the key to avoiding false
# positives: a forbidden phrase that appears *inside a quoted argument*
# (e.g. a commit message "blocks git push", or `echo "rm -rf"`) is NOT at a
# command position and is therefore allowed. Only the actual command token
# being executed is matched.
_P = r"(?:^|[\n;&|]\s*)"

# (compiled pattern, human reason). Matched case-insensitively against the
# full command string. Patterns mirror CLAUDE.md / settings.json deny policy;
# this hook is defense-in-depth on top of the permission deny list.
_RULES = [
    (re.compile(_P + r"git\s+push\b", re.I), "git push is forbidden"),
    (re.compile(_P + r"git\s+reset\s+--hard\b", re.I), "git reset --hard is forbidden"),
    (re.compile(_P + r"git\s+clean\b", re.I), "git clean is forbidden"),
    (re.compile(_P + r"rm\s", re.I), "rm is forbidden"),
    (re.compile(_P + r"Remove-Item\b", re.I), "Remove-Item is forbidden"),
    (re.compile(_P + r"rmdir\b", re.I), "rmdir is forbidden"),
    (re.compile(_P + r"del\s", re.I), "del is forbidden"),
    (re.compile(_P + r"erase\s", re.I), "erase is forbidden"),
    # reading the real .env (allow .env.example / .env.* templates)
    (re.compile(_P + r"(?:type|cat|gc|Get-Content)\s+[^\n;&|]*\.env(?![.\w])", re.I),
     "reading .env contents is forbidden (.env values must not be printed)"),
    (re.compile(_P + r"docker\s+system\s+prune", re.I), "docker system prune is forbidden"),
    (re.compile(_P + r"docker\s+volume\s+(?:rm|prune)", re.I), "docker volume rm/prune is forbidden"),
]
# NOTE: "proxy rotation" is intentionally NOT matched here. It is a code/config
# policy concern (enforced by security/legal review), not a single shell
# command, and matching the phrase caused false positives on docs/commit text.


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0  # nothing to inspect -> allow
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        # malformed payload: fail open so normal work is never blocked
        return 0

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return 0  # no command string -> allow

    for pattern, reason in _RULES:
        if pattern.search(command):
            decision = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"FORBIDDEN_COMMAND_BLOCKED: {reason}",
                }
            }
            sys.stdout.write(json.dumps(decision))
            return 0  # exit 0 + JSON is the recommended block method

    return 0  # no match -> allow


if __name__ == "__main__":
    sys.exit(main())

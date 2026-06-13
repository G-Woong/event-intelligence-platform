from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional


def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in (p.parent, p.parent.parent, p.parent.parent.parent):
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return Path.cwd()


def _legacy_alias_map() -> dict[str, str]:
    """legacy alias 이름 → canonical 이름 (env_loader._ALIASES 전체에서 도출)."""
    from ingestion.core.env_loader import _ALIASES
    return {
        alias: canonical
        for canonical, aliases in _ALIASES.items()
        for alias in aliases
    }


def _extract_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=")[0].strip()
            if k:
                keys.add(k)
    return keys


def check_hygiene(
    env_path: Optional[Path] = None,
    example_path: Optional[Path] = None,
) -> list[dict]:
    """Scan .env for hygiene issues. Returns list of issue dicts — no values exposed.

    Issue types:
      MISSING_ENV_FILE      — .env does not exist
      SPACE_AROUND_EQUALS   — trailing space before '=' (e.g. CLIENT_ID = value)
      AMBIGUOUS_ALIAS       — legacy alias name in use (env_loader._ALIASES 전체)
      ALIAS_VALUE_MISMATCH  — canonical과 legacy 둘 다 있고 값이 다름 (값은 비노출)
      EMPTY_VALUE           — KEY= (값 없음)
      UNCOMMENTED_PROSE     — line without '#' that has no '=' (prose text)
      DUPLICATE_KEY         — same key appears more than once
      KEY_NOT_IN_EXAMPLE    — key in .env is absent from .env.example
    """
    if env_path is None:
        env_path = _find_repo_root() / ".env"
    if example_path is None:
        example_path = _find_repo_root() / ".env.example"

    if not env_path.exists():
        return [{"type": "MISSING_ENV_FILE", "file": str(env_path), "detail": ""}]

    legacy_map = _legacy_alias_map()
    issues: list[dict] = []
    lines = env_path.read_text(encoding="utf-8").splitlines()
    seen_keys: dict[str, int] = {}
    values: dict[str, str] = {}  # 메모리 내 비교 전용 — 절대 출력하지 않음

    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if "=" in raw:
            key_part = raw.split("=")[0]
            k = key_part.strip()
            v = raw.partition("=")[2].strip()
            if k and k not in values:
                values[k] = v

            if key_part != key_part.rstrip():
                issues.append({
                    "type": "SPACE_AROUND_EQUALS",
                    "line": lineno,
                    "key": k,
                    "detail": "trailing space before '=' - remove whitespace around '='",
                })

            if k in legacy_map:
                issues.append({
                    "type": "AMBIGUOUS_ALIAS",
                    "line": lineno,
                    "key": k,
                    "detail": (
                        f"legacy alias — use {legacy_map[k]} instead "
                        f"(기능에는 영향 없음: env_loader가 자동 해석)"
                    ),
                })

            if not v:
                issues.append({
                    "type": "EMPTY_VALUE",
                    "line": lineno,
                    "key": k,
                    "detail": "key has no value (KEY=) — fill it or remove the line",
                })

            if k in seen_keys:
                issues.append({
                    "type": "DUPLICATE_KEY",
                    "line": lineno,
                    "key": k,
                    "detail": f"first seen at line {seen_keys[k]}",
                })
            else:
                seen_keys[k] = lineno
        else:
            issues.append({
                "type": "UNCOMMENTED_PROSE",
                "line": lineno,
                "detail": "line has no '=' and no '#' prefix - add '#' if it is a comment",
            })

    # canonical과 legacy alias 둘 다 존재하고 값이 다르면 경고 (메모리 내 비교, 값 비노출)
    for alias, canonical in sorted(legacy_map.items()):
        alias_val = values.get(alias, "")
        canonical_val = values.get(canonical, "")
        if alias_val and canonical_val and alias_val != canonical_val:
            issues.append({
                "type": "ALIAS_VALUE_MISMATCH",
                "key": canonical,
                "detail": (
                    f"'{canonical}' and legacy '{alias}' both set with DIFFERENT values — "
                    f"canonical wins at runtime; remove or sync the legacy line"
                ),
            })

    if example_path.exists():
        example_keys = _extract_keys(example_path.read_text(encoding="utf-8"))
        for k in sorted(set(seen_keys) - example_keys):
            issues.append({
                "type": "KEY_NOT_IN_EXAMPLE",
                "key": k,
                "detail": f"'{k}' is in .env but missing from .env.example — add it",
            })

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Check .env file for hygiene issues.")
    parser.add_argument("--env-path", type=Path, default=None, help="Path to .env file")
    parser.add_argument("--example-path", type=Path, default=None, help="Path to .env.example file")
    args = parser.parse_args()
    issues = check_hygiene(env_path=args.env_path, example_path=args.example_path)
    if not issues:
        print("OK: no hygiene issues found")
        return
    for issue in issues:
        parts = [f"[{issue['type']}]"]
        if "line" in issue:
            parts.append(f"line {issue['line']}")
        if "key" in issue:
            parts.append(f"key={issue['key']}")
        if issue.get("detail"):
            parts.append(f"| {issue['detail']}")
        line = " ".join(parts)
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="replace").decode("ascii"))
    sys.exit(1)


if __name__ == "__main__":
    main()

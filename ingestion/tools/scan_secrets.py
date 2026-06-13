from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

# Exit codes
EXIT_PASS = 0
EXIT_WARNING = 1
EXIT_BLOCKED = 2

# Files we never scan (the .env itself is the secret source, not a leak target)
_EXCLUDED_NAMES = frozenset({".env"})
_MAX_FILE_BYTES = 5 * 1024 * 1024  # skip files larger than 5 MB
_SCAN_EXTENSIONS = frozenset({
    ".md", ".txt", ".json", ".yaml", ".yml", ".py", ".html", ".xml",
    ".csv", ".log", ".toml", ".ini", ".cfg", ".env.example",
})

# Layer 1: pattern detection → WARNING (token-shaped strings, 20+ chars)
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("openai_key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("google_api_key", re.compile(r"AIza[A-Za-z0-9_-]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("service_key_param", re.compile(r"serviceKey=[A-Za-z0-9%+/=]{20,}")),
    ("generic_api_key_assign", re.compile(
        r"(?i)(api[_-]?key|api[_-]?secret|access[_-]?token|client[_-]?secret)"
        r"\s*[=:]\s*['\"]?[A-Za-z0-9+/_-]{20,}"
    )),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

# Placeholder allowlist — a pattern hit containing one of these is NOT a finding
_PLACEHOLDER_MARKERS = (
    "YOUR_", "your_", "<", ">", "REDACTED", "example", "EXAMPLE",
    "placeholder", "PLACEHOLDER", "xxxx", "XXXX", "...",
)


def _is_placeholder(matched: str, line: str) -> bool:
    return any(m in matched or m in line for m in _PLACEHOLDER_MARKERS)


def _is_openai_url_slug_false_positive(matched: str) -> bool:
    """`sk-...` 매치가 OpenAI 키가 아니라 뉴스 기사 URL slug인지 판별.

    실제 OpenAI 키는 `sk-`(또는 `sk-proj-`/`sk-svcacct-` 등) 뒤에 하이픈 없는
    20자 이상 고엔트로피(영문+숫자 혼합) 토큰을 갖는다.
    공개 기사 URL slug는 'sk-if-iran-war-persists'(=…ri[sk]-if-…),
    'sk-spacex-tesla-ipo-…'(=mu[sk]-spacex-…)처럼 하이픈으로 끊긴 단어들의 나열이다.
    후자(고엔트로피 토큰이 하나도 없는 경우)만 false positive로 처리한다.
    전체 `sk-*`를 무시하지 않는다 — 키 형태(긴 혼합 토큰)는 그대로 WARNING으로 남긴다.
    """
    for seg in matched[3:].split("-"):  # 'sk-' 제거 후 하이픈 분할
        if len(seg) >= 20 and any(c.isdigit() for c in seg) and any(c.isalpha() for c in seg):
            return False  # 고엔트로피 토큰 존재 → 실제 키 가능성, FP 아님
    return True


# Only keys whose NAME indicates a credential are compared in layer 2.
# Infra config values (MILVUS_HOST=localhost, ports, URLs) are not secrets and
# would flood the report with false BLOCKED findings.
_SECRET_KEY_NAME_RE = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)", re.IGNORECASE)


def _load_env_values(env_path: Path) -> dict[str, str]:
    """Load .env key→value in memory only. Values are never written anywhere.

    Only credential-named keys (KEY/SECRET/TOKEN/PASSWORD/CREDENTIAL) with
    values of length >= 8 participate in exact-match detection.
    """
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        key, val = key.strip(), val.strip()
        if key and val and len(val) >= 8 and _SECRET_KEY_NAME_RE.search(key):
            values[key] = val
    return values


def _iter_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(f for f in sorted(p.rglob("*")) if f.is_file())
    return files


def _should_scan(path: Path) -> bool:
    if path.name in _EXCLUDED_NAMES:
        return False
    if path.suffix.lower() == ".png" or path.suffix.lower() in (
        ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".pyc", ".lock",
    ):
        return False
    if path.suffix.lower() not in _SCAN_EXTENSIONS and path.suffix != "":
        return False
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return False
    except OSError:
        return False
    return True


def scan_paths(
    paths: list[Path],
    env_path: Optional[Path] = None,
) -> dict:
    """Scan files under paths. Returns report dict — secret VALUES never included.

    Findings:
      severity=WARNING — token-shaped pattern hit (placeholders allowlisted)
      severity=BLOCKED — exact match against a real .env value (in-memory comparison)
    """
    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    env_values = _load_env_values(env_path)

    findings: list[dict] = []
    scanned = 0
    for f in _iter_files(paths):
        if not _should_scan(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), 1):
            # Layer 2: exact .env value match → BLOCKED (boolean check only)
            for key_name, value in env_values.items():
                if value in line:
                    findings.append({
                        "severity": "BLOCKED",
                        "type": "ENV_VALUE_LEAKED",
                        "env_key": key_name,
                        "file": str(f),
                        "line": lineno,
                    })
            # Layer 1: pattern hit → WARNING
            for pat_name, pattern in _SECRET_PATTERNS:
                m = pattern.search(line)
                if m and not _is_placeholder(m.group(0), line):
                    if pat_name == "openai_key":
                        # 'sk'가 단어 중간(mu[sk]-spacex…, ri[sk]-if…)이면 키가 아니라
                        # 기사 URL slug다. 실제 키는 단어 경계(공백/=/"/:)에서 시작한다.
                        prev = line[m.start() - 1] if m.start() > 0 else ""
                        if prev.isalnum() or _is_openai_url_slug_false_positive(m.group(0)):
                            continue
                    findings.append({
                        "severity": "WARNING",
                        "type": f"PATTERN_{pat_name.upper()}",
                        "file": str(f),
                        "line": lineno,
                    })

    blocked = [x for x in findings if x["severity"] == "BLOCKED"]
    warnings = [x for x in findings if x["severity"] == "WARNING"]
    if blocked:
        verdict, exit_code = "BLOCKED", EXIT_BLOCKED
    elif warnings:
        verdict, exit_code = "WARNING", EXIT_WARNING
    else:
        verdict, exit_code = "PASS", EXIT_PASS
    return {
        "verdict": verdict,
        "exit_code": exit_code,
        "files_scanned": scanned,
        "env_keys_loaded": len(env_values),
        "findings": findings,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan files for leaked secrets. Reports key NAMES only, never values."
    )
    parser.add_argument("--paths", nargs="+", required=True, help="Files/directories to scan")
    parser.add_argument("--env-path", type=Path, default=None, help="Path to .env (default: repo root)")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args(argv)

    report = scan_paths([Path(p) for p in args.paths], env_path=args.env_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"verdict={report['verdict']} files_scanned={report['files_scanned']}")
        for x in report["findings"]:
            loc = f"{x['file']}:{x['line']}"
            if x["severity"] == "BLOCKED":
                print(f"[BLOCKED] {x['type']} env_key={x['env_key']} at {loc}")
            else:
                print(f"[WARNING] {x['type']} at {loc}")
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())

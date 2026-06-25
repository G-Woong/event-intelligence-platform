from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_REDACTED = "***REDACTED***"

_ALIASES: dict[str, list[str]] = {
    "NAVER_CLIENT_ID": ["CLIENT_ID"],
    "NAVER_CLIENT_SECRET": ["CLIENT_SECRET"],
    "BOK_ECOS_API_KEY": ["ECOS_API_KEY"],
    "PRODUCT_HUNT_ACCESS_TOKEN": ["PRODUCT_HUNT_API_KEY"],
    "GOOGLE_CUSTOM_SEARCH_API_KEY": ["GOOGLE_API_KEY"],
    "GOOGLE_CUSTOM_SEARCH_CX": ["CSE_CX"],
    # culture.go.kr API: registry uses CULTURE_INFO_API_KEY; .env may use CULTURE_INFO_KEY
    "CULTURE_INFO_API_KEY": ["CULTURE_INFO_KEY"],
}


def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in (p.parent, p.parent.parent, p.parent.parent.parent):
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return Path.cwd()


def load_env(env_path: Optional[Path] = None) -> dict[str, str]:
    """Parse .env and populate os.environ via setdefault. Returns raw key→value dict.

    Values are never logged or returned to callers outside this module — use
    env_status() for safe present/missing reporting.
    """
    if env_path is None:
        env_path = _find_repo_root() / ".env"
    if not env_path.exists():
        return {}
    loaded: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        key = key.strip()
        val = val.strip()
        if key:
            loaded[key] = val
            os.environ.setdefault(key, val)
    return loaded


def redact_secret(value: str) -> str:  # noqa: ARG001
    """Always returns ***REDACTED***. Never exposes the value."""
    return _REDACTED


def env_status(
    keys: list[str],
    env_path: Optional[Path] = None,
) -> dict[str, str]:
    """Return 'present' or 'missing' for each key. No values are exposed.

    Alias resolution: NAVER_CLIENT_ID resolved from CLIENT_ID,
    NAVER_CLIENT_SECRET from CLIENT_SECRET, BOK_ECOS_API_KEY from ECOS_API_KEY.
    """
    loaded = load_env(env_path)
    result: dict[str, str] = {}
    for key in keys:
        if os.environ.get(key) or loaded.get(key):
            result[key] = "present"
            continue
        aliases = _ALIASES.get(key, [])
        if any(os.environ.get(a) or loaded.get(a) for a in aliases):
            result[key] = "present"
        else:
            result[key] = "missing"
    return result


def check_gcp_credentials() -> dict[str, str]:
    """Check GOOGLE_APPLICATION_CREDENTIALS path existence only. Never reads content."""
    path_val = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not path_val:
        return {"GOOGLE_APPLICATION_CREDENTIALS": "missing"}
    return {
        "GOOGLE_APPLICATION_CREDENTIALS": (
            "path_exists" if Path(path_val).exists() else "path_not_found"
        )
    }


def env_example_declares(var_name: str, example_path: Optional[Path] = None) -> bool:
    """`.env.example`(실값 없는 안전 템플릿)에 `var_name=` 선언이 있는지 — **이름만** 확인(값 미반환).

    `.env.example` 만 읽는다(`.env` 는 열지 않는다). 라인의 키 토큰이 정확히 일치할 때만 True.
    """
    if example_path is None:
        example_path = _find_repo_root() / ".env.example"
    if not example_path.exists():
        return False
    for line in example_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.partition("=")[0].strip() == var_name:
            return True
    return False


def probe_env_var(
    var_name: str,
    env_path: Optional[Path] = None,
    example_path: Optional[Path] = None,
) -> dict[str, object]:
    """단일 env var 의 secret-safe readiness probe. **boolean/present-missing 만** 반환 — 값 미반환·미로그.

    구분(§ADR#63): credential 부재 시 `.env` 파일 자체가 없으면(env_not_loaded) 와 파일은 있으나 키 미설정
    (missing_credentials) 을 분리하기 위한 신호를 제공한다. 모두 값 비열람:
      - credential_present: `env_status` (present/missing·값 0)
      - env_file_present:   `.env` 의 `Path.exists()` 만 (내용 미열람)
      - declared_in_example: `.env.example` 이름 선언만
    """
    root = _find_repo_root()
    if env_path is None:
        env_path = root / ".env"
    status = env_status([var_name], env_path=env_path).get(var_name, "missing")
    return {
        "var_name": var_name,
        "credential_present": status == "present",
        "env_file_present": env_path.exists(),
        "declared_in_example": env_example_declares(var_name, example_path=example_path),
    }

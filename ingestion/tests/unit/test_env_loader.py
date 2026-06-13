from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from ingestion.core.env_loader import (
    check_gcp_credentials,
    env_status,
    load_env,
    redact_secret,
)

_SECRET = "sk-supersecret-value-12345"


def _make_env(tmp_path: Path, content: str) -> Path:
    p = tmp_path / ".env"
    p.write_text(content, encoding="utf-8")
    return p


# ── redact_secret ──────────────────────────────────────────────────────────


def test_redact_never_leaks_value():
    result = redact_secret(_SECRET)
    assert _SECRET not in result
    assert result == "***REDACTED***"


def test_redact_empty_string():
    assert redact_secret("") == "***REDACTED***"


def test_redact_very_long_value():
    long_val = "x" * 10_000
    result = redact_secret(long_val)
    assert long_val not in result
    assert result == "***REDACTED***"


def test_redact_is_idempotent():
    first = redact_secret(_SECRET)
    second = redact_secret(first)
    assert first == second == "***REDACTED***"


# ── env_status: present / missing ─────────────────────────────────────────


def test_env_status_present(tmp_path):
    env = _make_env(tmp_path, "MY_KEY=somevalue\n")
    for k in ("MY_KEY",):
        os.environ.pop(k, None)
    status = env_status(["MY_KEY"], env_path=env)
    assert status["MY_KEY"] == "present"
    assert "somevalue" not in str(status)


def test_env_status_missing(tmp_path):
    env = _make_env(tmp_path, "OTHER_KEY=value\n")
    os.environ.pop("MISSING_KEY_XYZ_UNIQUE", None)
    status = env_status(["MISSING_KEY_XYZ_UNIQUE"], env_path=env)
    assert status["MISSING_KEY_XYZ_UNIQUE"] == "missing"


def test_no_value_in_status_output(tmp_path):
    env = _make_env(tmp_path, f"MY_API_KEY={_SECRET}\n")
    os.environ.pop("MY_API_KEY", None)
    status = env_status(["MY_API_KEY"], env_path=env)
    assert _SECRET not in str(status)


# ── alias resolution ───────────────────────────────────────────────────────


def test_naver_client_id_alias(tmp_path):
    env = _make_env(tmp_path, "CLIENT_ID=testclientid\n")
    for k in ("NAVER_CLIENT_ID", "CLIENT_ID"):
        os.environ.pop(k, None)
    status = env_status(["NAVER_CLIENT_ID"], env_path=env)
    assert status["NAVER_CLIENT_ID"] == "present", "CLIENT_ID alias should resolve NAVER_CLIENT_ID"


def test_naver_client_secret_alias(tmp_path):
    env = _make_env(tmp_path, "CLIENT_SECRET=testsecret\n")
    for k in ("NAVER_CLIENT_SECRET", "CLIENT_SECRET"):
        os.environ.pop(k, None)
    status = env_status(["NAVER_CLIENT_SECRET"], env_path=env)
    assert status["NAVER_CLIENT_SECRET"] == "present", "CLIENT_SECRET alias should resolve"


def test_bok_ecos_alias(tmp_path):
    env = _make_env(tmp_path, "ECOS_API_KEY=testecos123\n")
    for k in ("BOK_ECOS_API_KEY", "ECOS_API_KEY"):
        os.environ.pop(k, None)
    status = env_status(["BOK_ECOS_API_KEY"], env_path=env)
    assert status["BOK_ECOS_API_KEY"] == "present", "ECOS_API_KEY alias should resolve BOK_ECOS_API_KEY"


def test_canonical_key_takes_precedence(tmp_path):
    env = _make_env(tmp_path, "NAVER_CLIENT_ID=direct\nCLIENT_ID=alias\n")
    for k in ("NAVER_CLIENT_ID", "CLIENT_ID"):
        os.environ.pop(k, None)
    status = env_status(["NAVER_CLIENT_ID"], env_path=env)
    assert status["NAVER_CLIENT_ID"] == "present"


def test_product_hunt_access_token_direct(tmp_path):
    env = _make_env(tmp_path, "PRODUCT_HUNT_ACCESS_TOKEN=token123\n")
    for k in ("PRODUCT_HUNT_ACCESS_TOKEN", "PRODUCT_HUNT_API_KEY"):
        os.environ.pop(k, None)
    status = env_status(["PRODUCT_HUNT_ACCESS_TOKEN"], env_path=env)
    assert status["PRODUCT_HUNT_ACCESS_TOKEN"] == "present"


def test_product_hunt_api_key_alias(tmp_path):
    """Legacy PRODUCT_HUNT_API_KEY alias resolves PRODUCT_HUNT_ACCESS_TOKEN."""
    env = _make_env(tmp_path, "PRODUCT_HUNT_API_KEY=legacytoken\n")
    for k in ("PRODUCT_HUNT_ACCESS_TOKEN", "PRODUCT_HUNT_API_KEY"):
        os.environ.pop(k, None)
    status = env_status(["PRODUCT_HUNT_ACCESS_TOKEN"], env_path=env)
    assert status["PRODUCT_HUNT_ACCESS_TOKEN"] == "present"


# ── canonical rename: KOFIC_API_KEY / CULTURE_INFO_KEY ────────────────────

def test_kofic_api_key_canonical_name(tmp_path):
    """KOFIC_API_KEY must be recognised (canonical rename from KOBIS_API_KEY)."""
    env = _make_env(tmp_path, "KOFIC_API_KEY=testkofic\n")
    for k in ("KOFIC_API_KEY", "KOBIS_API_KEY"):
        os.environ.pop(k, None)
    status = env_status(["KOFIC_API_KEY"], env_path=env)
    assert status["KOFIC_API_KEY"] == "present"


def test_culture_info_key_canonical_name(tmp_path):
    """CULTURE_INFO_KEY must be recognised (canonical rename from CULTURE_INFO_API_KEY)."""
    env = _make_env(tmp_path, "CULTURE_INFO_KEY=testculture\n")
    for k in ("CULTURE_INFO_KEY", "CULTURE_INFO_API_KEY"):
        os.environ.pop(k, None)
    status = env_status(["CULTURE_INFO_KEY"], env_path=env)
    assert status["CULTURE_INFO_KEY"] == "present"


def test_culture_info_api_key_resolves_via_alias(tmp_path):
    """CULTURE_INFO_API_KEY (registry canonical) must resolve when .env has CULTURE_INFO_KEY."""
    env = _make_env(tmp_path, "CULTURE_INFO_KEY=testculture_alias\n")
    for k in ("CULTURE_INFO_KEY", "CULTURE_INFO_API_KEY"):
        os.environ.pop(k, None)
    status = env_status(["CULTURE_INFO_API_KEY"], env_path=env)
    assert status["CULTURE_INFO_API_KEY"] == "present", "CULTURE_INFO_KEY alias should resolve CULTURE_INFO_API_KEY"


# ── GCP credentials ────────────────────────────────────────────────────────


def test_gcp_credentials_missing():
    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    result = check_gcp_credentials()
    assert result["GOOGLE_APPLICATION_CREDENTIALS"] in ("missing", "path_not_found")


def test_gcp_credentials_path_exists(tmp_path):
    fake_key = tmp_path / "service-account.json"
    fake_key.write_text("{}", encoding="utf-8")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(fake_key)
    try:
        result = check_gcp_credentials()
        assert result["GOOGLE_APPLICATION_CREDENTIALS"] == "path_exists"
    finally:
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)


def test_gcp_credentials_path_not_found():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/nonexistent/path/key.json"
    try:
        result = check_gcp_credentials()
        assert result["GOOGLE_APPLICATION_CREDENTIALS"] == "path_not_found"
    finally:
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

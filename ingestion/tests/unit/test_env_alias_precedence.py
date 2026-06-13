from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.core.env_loader import _ALIASES, env_status
from ingestion.tools.check_env_hygiene import _legacy_alias_map, check_hygiene


def _write_env(tmp_path: Path, content: str) -> Path:
    env = tmp_path / ".env"
    env.write_text(content, encoding="utf-8")
    return env


def _write_example(tmp_path: Path, content: str = "") -> Path:
    ex = tmp_path / ".env.example"
    ex.write_text(content, encoding="utf-8")
    return ex


# ── canonical 우선 / legacy 단독 동작 ─────────────────────────────────────

def test_canonical_wins_over_legacy(monkeypatch):
    from ingestion.probes.api_probe import _resolve_key
    monkeypatch.setenv("NAVER_CLIENT_ID", "canonical_fake_value_1")
    monkeypatch.setenv("CLIENT_ID", "legacy_fake_value_2")
    assert _resolve_key("NAVER_CLIENT_ID") == "canonical_fake_value_1"


def test_legacy_alone_still_resolves(monkeypatch):
    from ingestion.probes.api_probe import _resolve_key
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.setenv("CLIENT_ID", "legacy_only_fake_value")
    assert _resolve_key("NAVER_CLIENT_ID") == "legacy_only_fake_value"


def test_env_status_resolves_via_alias(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOK_ECOS_API_KEY", raising=False)
    monkeypatch.delenv("ECOS_API_KEY", raising=False)
    env = _write_env(tmp_path, "ECOS_API_KEY=fake_alias_value_xyz\n")  # pragma: allowlist secret
    status = env_status(["BOK_ECOS_API_KEY"], env_path=env)
    assert status["BOK_ECOS_API_KEY"] == "present"


# ── _ALIASES 전체 커버 (하드코딩 CLIENT_ID/SECRET → 일반화) ───────────────

def test_legacy_alias_map_covers_all_aliases():
    legacy_map = _legacy_alias_map()
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            assert legacy_map[alias] == canonical


def test_every_legacy_alias_flagged_as_ambiguous(tmp_path: Path):
    all_aliases = [a for aliases in _ALIASES.values() for a in aliases]
    env = _write_env(
        tmp_path,
        "".join(f"{a}=some_value_{i}\n" for i, a in enumerate(all_aliases)),
    )
    _write_example(tmp_path, "".join(f"{a}=\n" for a in all_aliases))
    issues = check_hygiene(env_path=env, example_path=tmp_path / ".env.example")
    flagged = {x["key"] for x in issues if x["type"] == "AMBIGUOUS_ALIAS"}
    assert flagged == set(all_aliases)
    # legacy alias는 "기능에는 영향 없음"이 명시된다
    for x in issues:
        if x["type"] == "AMBIGUOUS_ALIAS":
            assert "기능에는 영향 없음" in x["detail"]


# ── ALIAS_VALUE_MISMATCH ──────────────────────────────────────────────────

def test_alias_value_mismatch_flagged_without_values(tmp_path: Path):
    env = _write_env(
        tmp_path,
        "NAVER_CLIENT_ID=fake_canonical_secret_aaa\n"
        "CLIENT_ID=fake_legacy_secret_bbb\n",
    )
    _write_example(tmp_path, "NAVER_CLIENT_ID=\nCLIENT_ID=\n")
    issues = check_hygiene(env_path=env, example_path=tmp_path / ".env.example")
    mismatches = [x for x in issues if x["type"] == "ALIAS_VALUE_MISMATCH"]
    assert len(mismatches) == 1
    assert mismatches[0]["key"] == "NAVER_CLIENT_ID"
    # 값이 리포트에 절대 섞이지 않는다 (boolean 비교)
    serialized = json.dumps(issues)
    assert ("fake_canonical_secret_aaa" in serialized) is False
    assert ("fake_legacy_secret_bbb" in serialized) is False


def test_no_mismatch_when_values_equal(tmp_path: Path):
    env = _write_env(
        tmp_path,
        "NAVER_CLIENT_ID=same_fake_value\nCLIENT_ID=same_fake_value\n",
    )
    _write_example(tmp_path, "NAVER_CLIENT_ID=\nCLIENT_ID=\n")
    issues = check_hygiene(env_path=env, example_path=tmp_path / ".env.example")
    assert [x for x in issues if x["type"] == "ALIAS_VALUE_MISMATCH"] == []


# ── EMPTY_VALUE ───────────────────────────────────────────────────────────

def test_empty_value_flagged(tmp_path: Path):
    env = _write_env(tmp_path, "SOME_KEY=\nFILLED_KEY=value123\n")
    _write_example(tmp_path, "SOME_KEY=\nFILLED_KEY=\n")
    issues = check_hygiene(env_path=env, example_path=tmp_path / ".env.example")
    empty = [x for x in issues if x["type"] == "EMPTY_VALUE"]
    assert len(empty) == 1
    assert empty[0]["key"] == "SOME_KEY"

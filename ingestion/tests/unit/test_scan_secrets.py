from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.tools.scan_secrets import (
    EXIT_BLOCKED,
    EXIT_PASS,
    EXIT_WARNING,
    main,
    scan_paths,
)

# Fixture secret values — fabricated, never real
_FAKE_ENV_VALUE = "fake_secret_value_abc123xyz789"


@pytest.fixture
def fake_env(tmp_path: Path) -> Path:
    env = tmp_path / "fake.env"
    env.write_text(
        f"MY_TEST_API_KEY={_FAKE_ENV_VALUE}\n"
        "EMPTY_KEY=\n"
        "SHORT=ab\n",
        encoding="utf-8",
    )
    return env


def test_clean_dir_passes(tmp_path: Path, fake_env: Path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "clean.md").write_text("# 깨끗한 문서\n내용만 있음.\n", encoding="utf-8")
    report = scan_paths([target], env_path=fake_env)
    assert report["verdict"] == "PASS"
    assert report["exit_code"] == EXIT_PASS
    assert report["findings"] == []


def test_env_value_leak_is_blocked(tmp_path: Path, fake_env: Path):
    target = tmp_path / "outputs"
    target.mkdir()
    (target / "leak.json").write_text(
        json.dumps({"resp": f"key echoed: {_FAKE_ENV_VALUE}"}), encoding="utf-8"
    )
    report = scan_paths([target], env_path=fake_env)
    assert report["verdict"] == "BLOCKED"
    assert report["exit_code"] == EXIT_BLOCKED
    finding = report["findings"][0]
    assert finding["env_key"] == "MY_TEST_API_KEY"
    assert finding["line"] == 1


def test_blocked_report_never_contains_value(tmp_path: Path, fake_env: Path):
    """리포트 직렬화 결과에 실값이 절대 섞이지 않는다 (boolean 비교)."""
    target = tmp_path / "outputs"
    target.mkdir()
    (target / "leak.txt").write_text(_FAKE_ENV_VALUE, encoding="utf-8")
    report = scan_paths([target], env_path=fake_env)
    serialized = json.dumps(report)
    assert (_FAKE_ENV_VALUE in serialized) is False


def test_pattern_hit_is_warning_not_blocked(tmp_path: Path, fake_env: Path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "doc.md").write_text(
        "token: sk-aaaabbbbccccddddeeeeffff1234\n", encoding="utf-8"  # pragma: allowlist secret
    )
    report = scan_paths([target], env_path=fake_env)
    assert report["verdict"] == "WARNING"
    assert report["exit_code"] == EXIT_WARNING
    assert all(x["severity"] == "WARNING" for x in report["findings"])


def test_placeholder_is_allowed(tmp_path: Path, fake_env: Path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "doc.md").write_text(
        "OPENAI_API_KEY=sk-YOUR_KEY_HERE_xxxxxxxxxxxxxxxx\n"
        "api_key: <your-api-key-goes-here-1234567890>\n"
        "token: ***REDACTED***\n",
        encoding="utf-8",
    )
    report = scan_paths([target], env_path=fake_env)
    assert report["verdict"] == "PASS"


def test_news_url_slug_is_not_openai_key_false_positive(tmp_path: Path, fake_env: Path):
    """기사 URL slug(`…risk-if-…`, `musk-spacex-…`)는 sk- 정규식에 걸려도 키가 아니다."""
    target = tmp_path / "outputs"
    target.mkdir()
    (target / "exa.json").write_text(
        '{"url":"https://example.com/oecd-cuts-growth-forecast-and-warns-of-'
        'recession-risk-if-iran-war-persists","title":"OECD"}\n'
        "source_url: https://apnews.com/article/"
        "musk-spacex-tesla-ipo-trillionaire-billionaire-worth-rockets-7723f82b\n",
        encoding="utf-8",
    )
    report = scan_paths([target], env_path=fake_env)
    assert report["verdict"] == "PASS"
    assert report["findings"] == []


def test_real_openai_key_shape_still_warns(tmp_path: Path, fake_env: Path):
    """하이픈 없는 고엔트로피 토큰을 가진 진짜 키 형태는 여전히 WARNING."""
    from ingestion.tools.scan_secrets import _is_openai_url_slug_false_positive
    assert _is_openai_url_slug_false_positive("sk-if-iran-war-persists") is True
    assert _is_openai_url_slug_false_positive("sk-spacex-tesla-ipo-trillionaire-billionaire-") is True
    assert _is_openai_url_slug_false_positive("sk-proj-Ab12Cd34Ef56Gh78Ij90Kl12Mn34") is False  # pragma: allowlist secret
    assert _is_openai_url_slug_false_positive("sk-aaaabbbbccccddddeeeeffff1234") is False  # pragma: allowlist secret
    target = tmp_path / "docs"
    target.mkdir()
    (target / "leak.md").write_text(
        "token: sk-proj-Ab12Cd34Ef56Gh78Ij90Kl12Mn34xyz\n", encoding="utf-8"  # pragma: allowlist secret
    )
    report = scan_paths([target], env_path=fake_env)
    assert report["verdict"] == "WARNING"


def test_env_file_itself_is_not_scanned(tmp_path: Path, fake_env: Path):
    """`.env` 파일 자체는 스캔 대상에서 제외된다."""
    env_in_target = tmp_path / ".env"
    env_in_target.write_text(f"K={_FAKE_ENV_VALUE}\n", encoding="utf-8")
    report = scan_paths([tmp_path], env_path=fake_env)
    blocked_files = [x["file"] for x in report["findings"] if x["severity"] == "BLOCKED"]
    assert str(env_in_target) not in blocked_files


def test_missing_env_file_no_exception(tmp_path: Path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "a.md").write_text("hello", encoding="utf-8")
    report = scan_paths([target], env_path=tmp_path / "nonexistent.env")
    assert report["verdict"] == "PASS"
    assert report["env_keys_loaded"] == 0


def test_main_exit_codes(tmp_path: Path, fake_env: Path, capsys):
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "a.md").write_text("clean", encoding="utf-8")
    assert main(["--paths", str(clean), "--env-path", str(fake_env)]) == EXIT_PASS

    leaky = tmp_path / "leaky"
    leaky.mkdir()
    (leaky / "b.md").write_text(_FAKE_ENV_VALUE, encoding="utf-8")
    code = main(["--paths", str(leaky), "--env-path", str(fake_env), "--json"])
    assert code == EXIT_BLOCKED
    out = capsys.readouterr().out
    assert (_FAKE_ENV_VALUE in out) is False
    assert "MY_TEST_API_KEY" in out


def test_code_reference_assignment_is_not_secret(tmp_path: Path, fake_env: Path):
    """`access_token = func(...)` 같은 함수 호출/식별자 참조는 secret이 아니다."""
    target = tmp_path / "src"
    target.mkdir()
    (target / "a.py").write_text(
        "access_token = _igdb_get_access_token(client_id, client_secret)\n",
        encoding="utf-8",
    )
    report = scan_paths([target], env_path=fake_env)
    assert report["verdict"] == "PASS"
    assert report["findings"] == []


def test_quoted_credential_literal_still_warns(tmp_path: Path, fake_env: Path):
    """따옴표 리터럴로 박힌 credential 값은 함수호출 FP와 무관하게 여전히 WARNING."""
    target = tmp_path / "src"
    target.mkdir()
    (target / "b.py").write_text(
        'access_token = "Ab12Cd34Ef56Gh78Ij90Kl12"\n', encoding="utf-8"  # pragma: allowlist secret
    )
    report = scan_paths([target], env_path=fake_env)
    assert report["verdict"] == "WARNING"


def test_allowlist_pragma_suppresses_pattern_warning(tmp_path: Path, fake_env: Path):
    """`# pragma: allowlist secret` 이 있는 라인의 Layer1 패턴 경고는 면제된다."""
    target = tmp_path / "docs"
    target.mkdir()
    (target / "f.md").write_text(
        "token: sk-aaaabbbbccccddddeeeeffff1234  # pragma: allowlist secret\n",
        encoding="utf-8",
    )
    report = scan_paths([target], env_path=fake_env)
    assert report["verdict"] == "PASS"
    assert report["findings"] == []


def test_allowlist_pragma_does_not_suppress_env_value_leak(tmp_path: Path, fake_env: Path):
    """pragma 가 있어도 실제 .env 값 누출(Layer2 BLOCKED)은 절대 면제되지 않는다."""
    target = tmp_path / "outputs"
    target.mkdir()
    (target / "leak.txt").write_text(
        f"echoed {_FAKE_ENV_VALUE}  # pragma: allowlist secret\n", encoding="utf-8"
    )
    report = scan_paths([target], env_path=fake_env)
    assert report["verdict"] == "BLOCKED"


# ── _sanitize_response 회귀 테스트 (api_probe) ─────────────────────────────

def test_sanitize_response_redacts_secret():
    from ingestion.probes.api_probe import _sanitize_response
    secret = "abcdef1234567890"
    body = f'{{"echo": "{secret}", "ok": true}}'
    out = _sanitize_response(body, [secret])
    assert (secret in out) is False
    assert "***REDACTED***" in out


def test_sanitize_response_ignores_short_or_empty_secrets():
    from ingestion.probes.api_probe import _sanitize_response
    body = "abcd is fine"
    assert _sanitize_response(body, ["", "abcd"]) == body


def test_sanitize_response_multiple_secrets():
    from ingestion.probes.api_probe import _sanitize_response
    s1, s2 = "secret_one_12345", "secret_two_67890"
    out = _sanitize_response(f"{s1} and {s2}", [s1, s2])
    assert (s1 in out) is False
    assert (s2 in out) is False

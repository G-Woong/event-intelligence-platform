"""ADR#54 — production activation preflight 정책 잠금(순수·DB 무관·결정론).

_build_preflight_report 의 게이트 조립 + classify_write_target 의 named 분류/불일치 + preflight_exit_code 를
DB 없이 검증한다(async DB gather 는 CLI 실행·live-PG 에 귀속). DATABASE_URL 원문 미로그(fingerprint 만)도 잠근다.
"""
from __future__ import annotations

from backend.app.tools.db_target import (
    UnsafeWriteTargetError,
    assert_safe_write_target,
    classify_write_target,
)
from backend.app.tools.production_activation_preflight import (
    _build_preflight_report,
    preflight_exit_code,
)

_DEV_URL = "postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel"
_PROD_URL = "postgresql+asyncpg://event_user:event_pass@dbhost:5432/event_intel_prod"
_SECRET_URL = "postgresql+asyncpg://admin:SuperSecretPw123@10.0.0.5:5432/event_intel"


def _readiness(*, ready=True, current="c9d0e1f2a3b4", head="c9d0e1f2a3b4",
               behind=0, destructive=False, missing=None):
    return {
        "ready_for_stage3": ready,
        "current_revision": current,
        "expected_head": head,
        "behind_count": behind,
        "destructive_risk": destructive,
        "missing_revisions": missing or [],
        "tables_present": {"events": True, "event_identity_adjudication": ready},
    }


def _safe(app_env, url, allow_non_dev):
    try:
        assert_safe_write_target(app_env=app_env, database_url=url, allow_non_dev=allow_non_dev)
        return True
    except UnsafeWriteTargetError:
        return False


def _report(*, app_env="dev", url=_DEV_URL, persist=False, allow_non_dev=False,
            allow_flag_off=False, ready=True, flag=False, destructive=False, pending=0):
    return _build_preflight_report(
        app_env=app_env, database_url=url, persist_requested=persist,
        allow_non_dev=allow_non_dev, allow_flag_off=allow_flag_off,
        scheduler_profile_enabled=None,
        readiness=_readiness(ready=ready, destructive=destructive),
        flag_enabled=flag, safe_target=_safe(app_env, url, allow_non_dev), pending_links=pending)


# ── classify_write_target: named 분류 + 불일치 ──────────────────────────────────────
def test_classify_dev_consistent():
    c = classify_write_target(app_env="dev", database_url=_DEV_URL)
    assert c["classification"] == "dev" and c["consistent"] and c["is_dev_target"]
    assert not c["is_production_target"]


def test_classify_test_env():
    c = classify_write_target(app_env="test", database_url=_DEV_URL)
    assert c["classification"] == "test" and c["is_dev_target"]


def test_classify_production_via_app_env():
    c = classify_write_target(app_env="production", database_url=_PROD_URL)
    assert c["classification"] == "production" and c["is_production_target"] and c["consistent"]


def test_classify_dev_env_prod_url_is_dangerous_mismatch():
    # APP_ENV=dev 인데 URL 이 prod-marker → 더 위험한 production 으로 분류·불일치(거짓 안심 차단).
    c = classify_write_target(app_env="dev", database_url=_PROD_URL)
    assert c["classification"] == "production" and c["is_production_target"]
    assert c["consistent"] is False


def test_classify_staging_env_unmarked_url_inconsistent():
    c = classify_write_target(app_env="staging", database_url=_DEV_URL)
    assert c["classification"] == "staging" and c["consistent"] is False


def test_classify_unknown_env():
    c = classify_write_target(app_env="weird", database_url=_DEV_URL)
    assert c["classification"] == "unknown" and c["env_class"] == "unknown"


_STAGING_URL = "postgresql+asyncpg://event_user:event_pass@dbhost:5432/event_intel_staging"


def test_classify_production_env_staging_url_inconsistent():
    # 운영 env 가 staging-marked DB → cross-tier 불일치(이전엔 consistent=True 로 놓치던 갭).
    c = classify_write_target(app_env="production", database_url=_STAGING_URL)
    assert c["classification"] == "production" and c["consistent"] is False


def test_classify_staging_env_prod_url_inconsistent():
    c = classify_write_target(app_env="staging", database_url=_PROD_URL)
    assert c["classification"] == "production" and c["consistent"] is False


def test_classify_unknown_env_prod_url_inconsistent():
    # env=unknown(오타) + prod URL → production 격상·불일치(거짓 안심 차단).
    c = classify_write_target(app_env="prdo", database_url=_PROD_URL)
    assert c["classification"] == "production" and c["is_production_target"] and c["consistent"] is False


def test_classify_staging_env_staging_url_consistent():
    c = classify_write_target(app_env="staging", database_url=_STAGING_URL)
    assert c["classification"] == "staging" and c["consistent"] is True


# ── _build_preflight_report: 게이트 조립 ────────────────────────────────────────────
def test_dev_dry_run_allowed():
    r = _report(persist=False, ready=True, flag=False)
    assert r["can_dry_run"] is True
    assert r["can_persist"] is False           # persist 미요청
    assert preflight_exit_code(r) == 0         # dry-run 평가는 green


def test_dev_persist_blocked_without_flag():
    r = _report(persist=True, ready=True, flag=False)
    assert r["can_persist"] is False
    assert "flag:semantic_adjudication_disabled" in r["block_reasons"]
    assert preflight_exit_code(r) == 1


def test_dev_persist_allowed_with_explicit_persist_and_flag():
    r = _report(persist=True, ready=True, flag=True)
    assert r["can_persist"] is True
    assert r["block_reasons"] == []
    assert preflight_exit_code(r) == 0


def test_dev_persist_allowed_with_allow_flag_off_override():
    r = _report(persist=True, ready=True, flag=False, allow_flag_off=True)
    assert r["can_persist"] is True


def test_production_target_persist_blocked_unless_allowed():
    # APP_ENV=production·flag on·persist 인데 allow_non_dev 없음 → safe_target 차단.
    r = _report(app_env="production", url=_PROD_URL, persist=True, ready=True, flag=True)
    assert r["safe_write_target"] is False
    assert r["can_persist"] is False
    assert "safe_target:non_dev_db_without_allow" in r["block_reasons"]


def test_production_target_persist_allowed_with_allow_non_dev():
    r = _report(app_env="production", url=_PROD_URL, persist=True, ready=True, flag=True,
                allow_non_dev=True)
    assert r["safe_write_target"] is True
    assert r["can_persist"] is True
    assert r["is_production_target"] is True


def test_app_env_url_mismatch_warns_and_blocks():
    # APP_ENV=dev 인데 prod-like URL → 불일치 경고 + boundary 차단(allow_non_dev 없음).
    r = _report(app_env="dev", url=_PROD_URL, persist=True, ready=True, flag=True)
    assert r["app_env_url_consistent"] is False
    assert "boundary:app_env_url_mismatch" in r["block_reasons"]
    assert any("app_env_url_mismatch" in w for w in r["warnings"])


def test_ready_false_blocks_persist_and_dry_run():
    r = _report(persist=True, ready=False, flag=True)
    assert r["can_dry_run"] is False
    assert r["can_persist"] is False
    assert "readiness:stage3_tables_absent" in r["block_reasons"]


def test_allow_non_dev_does_not_bypass_readiness():
    # --allow-non-dev-db 는 safe_target/boundary 만 우회 — readiness 는 못 우회.
    r = _report(app_env="production", url=_PROD_URL, persist=True, ready=False, flag=True,
                allow_non_dev=True)
    assert r["can_persist"] is False
    assert "readiness:stage3_tables_absent" in r["block_reasons"]


def test_allow_non_dev_does_not_bypass_flag():
    r = _report(app_env="production", url=_PROD_URL, persist=True, ready=True, flag=False,
                allow_non_dev=True)
    assert r["can_persist"] is False
    assert "flag:semantic_adjudication_disabled" in r["block_reasons"]


def test_destructive_pending_blocks_persist():
    r = _build_preflight_report(
        app_env="dev", database_url=_DEV_URL, persist_requested=True, allow_non_dev=False,
        allow_flag_off=True, scheduler_profile_enabled=None,
        readiness=_readiness(ready=True, destructive=True), flag_enabled=True,
        safe_target=True, pending_links=0)
    assert r["destructive_risk"] is True
    assert r["can_persist"] is False
    assert "migration:destructive_pending" in r["block_reasons"]


def test_database_url_secret_not_in_fingerprint():
    r = _report(url=_SECRET_URL)
    fp = r["database_url_fingerprint"]
    assert "SuperSecretPw123" not in fp
    assert "admin" not in fp
    assert fp == "10.0.0.5:5432/event_intel"   # host:port/dbname 만


def test_report_has_block_reasons_and_next_actions():
    r = _report(persist=True, ready=False, flag=False)
    assert isinstance(r["block_reasons"], list) and r["block_reasons"]
    assert isinstance(r["next_required_actions"], list) and r["next_required_actions"]


def test_auto_merge_always_disabled():
    assert _report(persist=True, ready=True, flag=True)["auto_merge_enabled"] is False


def test_dev_safe_target_noop_warning_surfaced():
    # MEDIUM-1: dev event_intel safe-target no-op 을 warning 으로 표면화(은폐 금지).
    r = _report(app_env="dev", url=_DEV_URL, persist=False, ready=True, flag=True)
    assert any("safe_target_noop_in_dev" in w for w in r["warnings"])


def test_production_env_staging_url_blocks_persist():
    # 운영 env + staging URL(allow_non_dev 없음) → boundary 불일치로 persist 차단.
    r = _report(app_env="production", url=_STAGING_URL, persist=True, ready=True, flag=True)
    assert r["app_env_url_consistent"] is False
    assert "boundary:app_env_url_mismatch" in r["block_reasons"]
    assert r["can_persist"] is False


def test_exit_code_persist_requested_blocked():
    assert preflight_exit_code(_report(persist=True, ready=False, flag=False)) == 1


def test_exit_code_dry_run_blocked_when_not_ready():
    assert preflight_exit_code(_report(persist=False, ready=False)) == 1

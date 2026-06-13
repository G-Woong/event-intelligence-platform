from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ingestion.core.retry_policy import RetryPolicy, load_retry_policy

_REPO_CONFIG = Path(__file__).parent.parent.parent / "configs" / "retry_policy.yaml"


# ── RetryPolicy.budget_for ─────────────────────────────────────────────────

def test_budget_for_unknown_source_falls_back_to_global():
    policy = RetryPolicy(max_strategies_per_url=3, per_source_budget={"krx_kind": 8})
    assert policy.budget_for("bbc") == 3


def test_budget_for_known_source_returns_override():
    policy = RetryPolicy(max_strategies_per_url=3, per_source_budget={"krx_kind": 8})
    assert policy.budget_for("krx_kind") == 8


def test_default_policy_has_empty_per_source_budget():
    policy = RetryPolicy()
    assert policy.per_source_budget == {}
    assert policy.budget_for("anything") == policy.max_strategies_per_url


# ── load_retry_policy parsing ──────────────────────────────────────────────

def test_load_retry_policy_parses_per_source(tmp_path):
    yaml_path = tmp_path / "retry_policy.yaml"
    yaml_path.write_text(
        "max_strategies_per_url: 3\n"
        "per_source:\n"
        "  site_a:\n"
        "    max_strategies_per_url: 7\n"
        "  site_b:\n"
        "    max_strategies_per_url: 5\n",
        encoding="utf-8",
    )
    policy = load_retry_policy(yaml_path)
    assert policy.budget_for("site_a") == 7
    assert policy.budget_for("site_b") == 5
    assert policy.budget_for("site_c") == 3


def test_load_retry_policy_without_per_source_section(tmp_path):
    yaml_path = tmp_path / "retry_policy.yaml"
    yaml_path.write_text("max_strategies_per_url: 3\n", encoding="utf-8")
    policy = load_retry_policy(yaml_path)
    assert policy.per_source_budget == {}
    assert policy.budget_for("any") == 3


def test_repo_config_global_default_unchanged():
    policy = load_retry_policy(_REPO_CONFIG)
    assert policy.max_strategies_per_url == 3


def test_repo_config_has_playwright_first_overrides():
    policy = load_retry_policy(_REPO_CONFIG)
    assert policy.budget_for("krx_kind") == 8
    assert policy.budget_for("eu_press_corner") == 8
    assert policy.budget_for("dcinside") == 6
    assert policy.budget_for("fmkorea") == 6


# ── strategy_runner integration: per-source budget applied ─────────────────

def _run_loop_with_empty_fetches(source_id: str):
    from ingestion.fetch_strategies.strategy_runner import run_fetch_strategy_loop

    with patch(
        "ingestion.agents.graph._fetch_with_strategy",
        return_value=("", None, None),
    ), patch(
        "ingestion.fetch_strategies.strategy_runner.time.sleep"
    ), patch(
        "ingestion.fetch_strategies.selenium_strategy.selenium_env_status",
        return_value={"ready": False},
    ):
        return run_fetch_strategy_loop(source_id, "https://example.com/page")


def test_runner_default_budget_caps_attempts_at_3():
    result = _run_loop_with_empty_fetches("some_unconfigured_source")
    assert result.status == "exhausted"
    assert len(result.attempts) <= 3


def test_runner_per_source_budget_allows_more_attempts():
    result = _run_loop_with_empty_fetches("krx_kind")
    assert result.status == "exhausted"
    # 기본 budget 3을 넘어 playwright 전략까지 도달해야 한다
    assert len(result.attempts) > 3
    assert any("playwright" in a.strategy for a in result.attempts)


def test_runner_explicit_strategy_budget_wins_over_per_source():
    from ingestion.fetch_strategies.strategy_runner import run_fetch_strategy_loop

    with patch(
        "ingestion.agents.graph._fetch_with_strategy",
        return_value=("", None, None),
    ), patch(
        "ingestion.fetch_strategies.strategy_runner.time.sleep"
    ), patch(
        "ingestion.fetch_strategies.selenium_strategy.selenium_env_status",
        return_value={"ready": False},
    ):
        result = run_fetch_strategy_loop(
            "krx_kind", "https://example.com/page", strategy_budget=2
        )
    assert len(result.attempts) <= 2

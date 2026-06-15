"""G2-12: SourceSupervisor — deterministic fallback + unsafe 전략 거부 + LLM 제안은 allowed 안에서만.
"""
from __future__ import annotations

from ingestion.orchestration.source_supervisor import decide


def test_deterministic_fallback_picks_first_allowed():
    d = decide(source_id="gdelt", observed_failure="provider 429 rate limit",
               blocking_layer="RATE_LIMIT")
    assert d.selected_strategy == "rate_limit_cooldown_resume"
    assert "provider_rate_limit" in d.root_cause_candidates
    assert d.confidence in ("high", "medium")


def test_unsafe_strategies_rejected_even_if_in_pool():
    d = decide(source_id="x", observed_failure="captcha challenge", blocking_layer="ROBOTS",
               candidate_strategies=("captcha_solver", "proxy_rotation", "use_robots_allowed_path"))
    assert "captcha_solver" not in d.allowed_strategies
    assert "proxy_rotation" not in d.allowed_strategies
    assert d.selected_strategy == "use_robots_allowed_path"
    assert "captcha_solver" in d.rejected_unsafe_strategies


def test_llm_proposal_only_accepted_within_allowed():
    # LLM이 우회를 제안해도 무시(allowed 밖) → deterministic 유지
    d = decide(source_id="x", observed_failure="rate limit", blocking_layer="RATE_LIMIT",
               llm_available=True, llm_propose=lambda f, allowed: "proxy_rotation")
    assert d.selected_strategy == "rate_limit_cooldown_resume"


def test_llm_proposal_accepted_when_in_allowed():
    d = decide(source_id="x", observed_failure="rate limit", blocking_layer="RATE_LIMIT",
               llm_available=True, llm_propose=lambda f, allowed: "query_simplification_spaced_probe")
    assert d.selected_strategy == "query_simplification_spaced_probe"
    assert d.confidence == "medium"


def test_policy_layer_yields_no_bypass_proof():
    d = decide(source_id="dcinside", observed_failure="robots policy block", blocking_layer="POLICY")
    assert d.selected_strategy == "policy_block_no_bypass_with_proof"
    assert "robots_ignore" in d.rejected_unsafe_strategies


def test_empty_allowed_returns_manual_review():
    d = decide(source_id="x", observed_failure="weird", blocking_layer="RATE_LIMIT",
               candidate_strategies=("proxy_rotation",))
    assert d.selected_strategy == "manual_operator_review" and d.confidence == "low"

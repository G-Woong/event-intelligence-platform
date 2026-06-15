"""Phase G2-12 SourceSupervisor — 실패 진단 + 정책 안전 전략 선택(LLM-ready, 결정적 fallback).

오케스트레이션은 deterministic이 기본이다. 이 모듈은 최소한의 LLM-ready supervisor
인터페이스를 제공한다: 실패 로그를 요약하고, root cause 후보를 만들고, **허용된 전략만**
선택하며, 우회(unsafe) 전략은 제거한다. LLM은 후보를 '판단'만 하고 실행하지 않는다 —
실행은 AllowedStrategyRegistry + deterministic ToolExecutor만 한다.

LLM provider가 설정되지 않으면(기본) deterministic fallback으로 동작한다.

stdlib만. 신규 설치 0. 네트워크 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# blocking layer → 정책 안전 전략 후보(우선순위 순)
_ALLOWED_BY_LAYER: dict[str, tuple[str, ...]] = {
    "POLICY": ("policy_block_no_bypass_with_proof",),
    "ROBOTS": ("use_robots_allowed_path", "policy_block_no_bypass_with_proof"),
    "RATE_LIMIT": ("rate_limit_cooldown_resume", "query_simplification_spaced_probe"),
    "API_CONTRACT": ("requires_official_api_or_contract",),
    "BODY_FETCH": ("static_fetch", "body_ladder_fetch"),
    "EVIDENCE_ANCHOR": ("source_adapter_anchor_fix",),
    "SOURCE_VALUE": ("disable_low_value",),
    "PARSER": ("fix_parser_selectors",),
}

# 절대 선택 금지(우회) — provider/LLM이 제안해도 제거한다
_UNSAFE_STRATEGIES = frozenset({
    "proxy_rotation", "captcha_solver", "captcha_bypass", "login_credential_inject",
    "robots_ignore", "anti_bot_evasion", "user_agent_spoof_to_evade", "tight_loop_retry",
    "paywall_bypass", "ignore_rate_limit",
})

# 항상 '검토 후 거부됨'으로 보고할 대표 우회 전략(투명성)
_BASELINE_REJECTED = ("proxy_rotation", "captcha_bypass", "robots_ignore", "ignore_rate_limit")


@dataclass(frozen=True)
class SourceSupervisorDecision:
    source_id: str
    observed_failure: str
    root_cause_candidates: tuple[str, ...]
    allowed_strategies: tuple[str, ...]
    rejected_unsafe_strategies: tuple[str, ...]
    selected_strategy: str
    confidence: str


def _root_causes(observed_failure: str) -> tuple[str, ...]:
    low = (observed_failure or "").lower()
    out: list[str] = []
    if "429" in low or "rate" in low or "limit" in low:
        out.append("provider_rate_limit")
    if "robots" in low:
        out.append("robots_policy")
    if "captcha" in low:
        out.append("captcha_challenge")
    if "login" in low:
        out.append("login_wall")
    if "api" in low or "contract" in low or "key" in low:
        out.append("missing_official_api_or_key")
    if "parse" in low or "selector" in low or "no_rows" in low:
        out.append("parser_or_selector")
    return tuple(out) or ("unclassified_failure",)


def decide(
    *,
    source_id: str,
    observed_failure: str,
    blocking_layer: str,
    candidate_strategies: Optional[tuple[str, ...]] = None,
    llm_propose: Optional[Callable[[str, tuple[str, ...]], str]] = None,
    llm_available: bool = False,
) -> SourceSupervisorDecision:
    """실패 → root cause 후보 + 허용 전략 선택. LLM 미설정이면 deterministic fallback.

    llm_propose(observed_failure, allowed) → 제안 전략. allowed에 없으면 무시(안전).
    """
    pool = candidate_strategies if candidate_strategies is not None else _ALLOWED_BY_LAYER.get(
        blocking_layer, ("manual_operator_review",))

    allowed = tuple(s for s in pool if s not in _UNSAFE_STRATEGIES)
    rejected_in_pool = tuple(s for s in pool if s in _UNSAFE_STRATEGIES)
    rejected = tuple(dict.fromkeys(rejected_in_pool + _BASELINE_REJECTED))  # 중복 제거, 순서 유지

    if not allowed:
        return SourceSupervisorDecision(
            source_id, observed_failure, _root_causes(observed_failure),
            (), rejected, "manual_operator_review", "low")

    selected = allowed[0]
    confidence = "high" if len(allowed) == 1 else "medium"
    if llm_available and llm_propose is not None:
        try:
            proposed = llm_propose(observed_failure, allowed)
        except Exception:
            proposed = None
        if proposed in allowed:        # 허용 집합 안에서만 채택(우회 제안 차단)
            selected = proposed
            confidence = "medium"
        # 허용 밖 제안은 조용히 무시 → deterministic fallback 유지

    return SourceSupervisorDecision(
        source_id, observed_failure, _root_causes(observed_failure),
        allowed, rejected, selected, confidence)

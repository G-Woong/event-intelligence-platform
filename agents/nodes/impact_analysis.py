from __future__ import annotations

from backend.app.core.config import settings
from agents.state.event_state import EventState
from agents.nodes.baselines import impact_baseline, contains_mock_sentinel
from agents.tools.llm import analyze_impact


def impact_analysis(state: EventState) -> EventState:
    """결정론적 impact baseline을 1차로 쓰고, LLM_PROVIDER="openai"일 때만 LLM으로 보강한다.

    mock provider(dev)에서는 LLM의 `[mock] ...` 출력을 카드에 노출하지 않고 정직한 baseline을 쓴다.
    """
    normalized = state.get("normalized")
    if not normalized:
        return {**state, "impact": "[skip] no normalized event"}

    sectors = state.get("sectors", [])
    source_type = getattr(normalized, "source", "") or ""

    if settings.LLM_PROVIDER == "openai":
        try:
            result = analyze_impact(
                title=normalized.title,
                body=normalized.body,
                theme=state.get("theme", "unknown"),
                sectors=sectors,
            )
            # LLM 파싱 실패 시 analyze_impact가 `[fallback] ...` 상수를 반환할 수 있다 →
            # 합성 상수를 카드에 넣지 않고 정직한 baseline으로 대체.
            if contains_mock_sentinel(result.impact):
                return {**state, "impact": impact_baseline(sectors, source_type)}
            return {**state, "impact": result.impact}
        except Exception as e:
            errors = list(state.get("llm_errors") or []) + [
                f"impact_analysis: {type(e).__name__}: {e}"
            ]
            return {**state, "impact": impact_baseline(sectors, source_type), "llm_errors": errors}

    return {**state, "impact": impact_baseline(sectors, source_type)}

from __future__ import annotations

from backend.app.core.config import settings
from agents.state.event_state import EventState
from agents.nodes.baselines import structural_fact_check
from agents.tools.llm import fact_check_claims


def fact_check(state: EventState) -> EventState:
    """fail-closed 구조적 근거 확인을 1차로 적용하고, openai일 때만 LLM이 추가로 downgrade한다.

    이전에는 LLM 실패 시 무조건 "pass"로 fail-open했다(빈본문/무근거도 통과). 이제는 본문 존재 +
    grounded evidence + 합성마커 없음일 때만 구조적 "pass"이고, mock provider에서는 가짜 LLM "pass"를
    만들지 않는다. LLM(openai)은 구조적 pass를 "hold"로 낮출 수만 있다(더 엄격하게).
    """
    normalized = state.get("normalized")
    body = getattr(normalized, "body", "") or "" if normalized else ""
    evidence = state.get("evidence", [])

    structural = structural_fact_check(body, evidence)

    if settings.LLM_PROVIDER == "openai" and structural == "pass" and normalized:
        try:
            result = fact_check_claims(
                title=normalized.title,
                body=normalized.body,
                evidence=evidence,
            )
            # LLM은 더 엄격해질 수만 있다(pass→hold). pass를 만들어내지 않는다.
            status = "hold" if result.status != "pass" else "pass"
            return {**state, "fact_check": status}
        except Exception as e:
            errors = list(state.get("llm_errors") or []) + [
                f"fact_check: {type(e).__name__}: {e}"
            ]
            return {**state, "fact_check": structural, "llm_errors": errors}

    return {**state, "fact_check": structural}

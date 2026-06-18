from __future__ import annotations

from agents.state.event_state import EventState
from agents.nodes.evidence_rules import is_valid_evidence_url


def evidence_check(state: EventState) -> EventState:
    """raw 이벤트의 실제 source URL을 근거로 채택한다.

    P0 하드닝 이전에는 ["[mock-source-1]", ...] 고정 mock을 반환했다. 이제는 수집 시점의
    실 source URL이 구조적으로 유효할 때만 근거로 인정하고, 합성/로컬/플레이스홀더면 비운다.
    근거가 비면 downstream publish_or_hold가 hold로 봉인한다(검증 안 된 카드 노출 차단).
    """
    raw = state.get("raw")
    url = getattr(raw, "url", "") or ""
    evidence: list[str] = [url] if is_valid_evidence_url(url) else []
    return {**state, "evidence": evidence}

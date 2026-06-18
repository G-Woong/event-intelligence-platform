from __future__ import annotations

from backend.app.core.config import settings
from agents.state.event_state import EventState
from agents.nodes.evidence_rules import is_valid_evidence_url
from agents.nodes.evidence_reachability import check_evidence_reachable


def evidence_check(state: EventState) -> EventState:
    """raw 이벤트의 실제 source URL을 근거로 채택한다.

    P0 하드닝 이전에는 ["[mock-source-1]", ...] 고정 mock을 반환했다. 이제는 수집 시점의
    실 source URL이 구조적으로 유효할 때만 근거로 인정하고, 합성/로컬/플레이스홀더면 비운다.

    T-AgtA(Phase 4): `settings.EVIDENCE_REACHABILITY_CHECK` 가 켜지면 구조검증을 통과한 URL을
    SSRF-safe 하게 실제 HTTP 도달성까지 확인하고, 도달 불가면 근거에서 제외한다.
    근거가 비면 downstream publish_or_hold가 hold로 봉인한다(검증 안 된 카드 노출 차단).
    """
    raw = state.get("raw")
    url = getattr(raw, "url", "") or ""

    if not is_valid_evidence_url(url):
        return {**state, "evidence": [], "evidence_status": "invalid"}

    if not settings.EVIDENCE_REACHABILITY_CHECK:
        return {**state, "evidence": [url], "evidence_status": "structural_ok"}

    result = check_evidence_reachable(
        url,
        timeout_sec=settings.EVIDENCE_REACHABILITY_TIMEOUT_SEC,
        max_redirects=settings.EVIDENCE_REACHABILITY_MAX_REDIRECTS,
    )
    if result.reachable:
        return {**state, "evidence": [url], "evidence_status": "reachable_ok"}
    return {**state, "evidence": [], "evidence_status": f"unreachable:{result.status}"}

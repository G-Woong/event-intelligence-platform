from __future__ import annotations

from agents.state.event_state import EventState
from agents.nodes.evidence_rules import has_grounded_evidence

# 익명 커뮤니티/미확인 신호는 외부 교차확인 전 publish 금지(§1 info-not-advice, G-4 게이트의
# B측 강제). ingestion CommunityCorroborationGate 의 publish_level 과 동일 의미.
# ingestion 패키지에 의존하지 않도록 상수만 인라인한다(agents 이미지 독립성).
_CORROBORATION_REQUIRED_POLICIES = frozenset(
    {"unconfirmed_until_corroborated", "internal_queue_only", "publish_blocked_until_corrob"}
)


def _requires_corroboration(state: EventState) -> bool:
    raw = state.get("raw")
    meta = getattr(raw, "raw_metadata", None) or {}
    if meta.get("confirmation_policy") in _CORROBORATION_REQUIRED_POLICIES:
        return True
    return meta.get("corroboration_required") is True


def _has_body(state: EventState) -> bool:
    normalized = state.get("normalized")
    body = getattr(normalized, "body", "") or ""
    return bool(body.strip())


def publish_or_hold(state: EventState) -> EventState:
    """published 승격은 fail-closed로 엄격 게이트한다(P0 하드닝).

    다음을 모두 만족할 때만 published:
      1) 외부확인 강제 신호가 아님(community/unconfirmed → 무조건 hold)
      2) fact_check == "pass"
      3) 유효한 근거 URL(http(s)+호스트, 합성/mock 마커 아님)이 1개 이상
      4) 본문이 비어있지 않음(빈본문 fact_check pass 차단)

    mock evidence_check/빈 근거/합성 URL은 (3)을 통과 못 하므로 mock 콘텐츠 카드는 published되지
    않고 hold로 봉인된다(05 R-MockCard). evidence_check가 실 URL/도달성 검증으로 강화되면 자동으로
    published 가능해진다.
    """
    card = state.get("final_card")

    if _requires_corroboration(state):
        if card:
            card.status = "hold"
        return {**state, "status": "hold"}

    publishable = (
        state.get("fact_check") == "pass"
        and has_grounded_evidence(state.get("evidence"))
        and _has_body(state)
    )

    status = "published" if publishable else "hold"
    if card:
        card.status = status
    return {**state, "status": status}

from __future__ import annotations

from agents.state.event_state import EventState

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


def publish_or_hold(state: EventState) -> EventState:
    card = state.get("final_card")
    if _requires_corroboration(state):
        # 외부확인 강제 신호 — fact_check 와 무관하게 hold(자동 publish 차단)
        if card:
            card.status = "hold"
        return {**state, "status": "hold"}
    if card and state.get("fact_check") == "pass":
        card.status = "published"
        status = "published"
    else:
        if card:
            card.status = "hold"
        status = "hold"
    return {**state, "status": status}

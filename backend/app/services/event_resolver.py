"""Event Resolution 라우팅 결정 (S2c, ADR#16 / SPEC §2.2 / doc 12 §2.1).

cross_source_dedup 클러스터(+ cluster_event_map 매핑 상태)를 받아 **APPEND / HOLD / CREATE** 를
결정하는 순수 함수(DB 미접근). 영속화는 event_timeline_service(S2d)가 이 결정을 적용한다.

clique 게이트(R-FalseMerge): 강신호여도 clique_ok=False(약신호로만 끌려온 멤버 존재)면 그 멤버를
자동 흡수하지 않고 분리 HOLD(event_links possible)한다. 강신호 core만 APPEND/CREATE.

ingestion 비의존: 클러스터 필드를 원시값으로 받는다(confidence 문자열은 cross_source_dedup 값 계약).
merge_score entity_overlap(S4)/domain_distance(거버넌스 ADR)는 미사용 — signal_strength+clique만.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# cross_source_dedup.CONF_DUPLICATE 값 계약(import 없이 문자열로 결합).
_CONF_DUPLICATE = "duplicate"

ACTION_APPEND = "APPEND"
ACTION_CREATE = "CREATE"
ACTION_HOLD = "HOLD"
ACTION_WITHHELD = "WITHHELD"    # source-type gate: 직접 발행 금지(미영속·미노출). R-SourceTypeFidelityGate.

# 직접 발행(Event primary) 가능 source_type. 나머지(community/search/signal 등)는 **단독 cross-source
# 클러스터로 발행하지 않는다**(설계 never_direct_publish / signal_only_not_article_card; ADR#33).
# 값 계약: event_ingest_pipeline._RECORD_TYPE_TO_SOURCE_TYPE 매핑 결과(official_record→"official",
# article_candidate→"article"). ingestion 비의존 — 원시 문자열로 받는다.
_PUBLISHABLE_SOURCE_TYPES = frozenset({"official", "article"})


def _has_publishable(member_source_types: tuple[str, ...]) -> bool:
    """클러스터에 직접 발행 가능한 멤버(official/article)가 하나라도 있으면 True."""
    return any(st in _PUBLISHABLE_SOURCE_TYPES for st in member_source_types)


@dataclass(frozen=True)
class EventRoutingDecision:
    cluster_id: str
    action: str                          # APPEND | CREATE | HOLD | WITHHELD
    event_id: Optional[str]              # APPEND/HOLD 대상(매핑된 event); CREATE/WITHHELD는 None
    reason: str
    held_members: tuple[str, ...] = ()   # event_links(possible)로 분리 보류할 멤버 키(자동병합 금지)


def resolve_routing(
    *,
    cluster_id: str,
    confidence: str,
    clique_ok: bool,
    member_keys: tuple[str, ...],
    weak_only_members: tuple[str, ...] = (),
    mapped_event_id: Optional[str] = None,
    member_source_types: tuple[str, ...] = (),
) -> EventRoutingDecision:
    """클러스터 1개 → 라우팅 결정.

    mapped_event_id = cluster_event_map.get(cluster_id) 결과(없으면 None = 미매핑).
    member_source_types = 멤버 source_type 목록(official/article/community/search/signal). **source-type
    publish gate**(ADR#33+#35): 미매핑 신규 발행(CREATE) 시 publishable(official/article)가 하나도 없으면
    WITHHELD(미발행) — pure community/search/structured 단독 cross-source 직접 발행 차단. **미제공/미지/빈값도
    fail-closed→WITHHELD**(ADR#35: source_type 모르면 발행 안전하지 않음 — 조용한 우회 금지). 매핑된 event 의
    APPEND/HOLD 는 게이트 미적용(community 는 corroborator).
    결정적(같은 입력 → 같은 결정) — 재실행/감사 가능.
    """
    is_strong = confidence == _CONF_DUPLICATE
    held = tuple(weak_only_members)

    if mapped_event_id is not None:
        # 이 cluster가 이미 어떤 Event로 라우팅됨.
        if is_strong and clique_ok:
            return EventRoutingDecision(
                cluster_id, ACTION_APPEND, mapped_event_id, "strong_clique_append", ()
            )
        if is_strong and not clique_ok:
            # 강신호 core는 APPEND, 약신호-only 멤버는 분리 HOLD(transitive 흡수 차단).
            return EventRoutingDecision(
                cluster_id, ACTION_APPEND, mapped_event_id, "strong_core_append_weak_hold", held
            )
        # 약신호 → 자동병합 금지, 전체를 possible_link 보류.
        return EventRoutingDecision(
            cluster_id, ACTION_HOLD, mapped_event_id, "weak_signal_possible_link", tuple(member_keys)
        )

    # source-type publish gate(ADR#33+#35, R-SourceTypeFidelityGate): 미매핑 신규 발행인데 publishable
    # (official/article)가 하나도 없으면(pure community/search/structured **또는 source_type 미제공/미지/빈값**)
    # **직접 발행 금지** → WITHHELD(미영속·public timeline 미노출; fail-closed — 모르면 보류). 설계
    # never_direct_publish / signal_only_not_article_card. 매핑된 event 의 APPEND 는 위에서 이미 처리
    # (community 가 기존 발행 event 에 corroborator 로 append). 빈/미지 member_source_types → _has_publishable
    # =False → WITHHELD(실 호출은 candidate.evidence 가 source_type 항상 제공; 누락 = 조용한 발행 차단, ADR#35).
    if not _has_publishable(member_source_types):
        return EventRoutingDecision(
            cluster_id, ACTION_WITHHELD, None, "non_publishable_source_type", tuple(member_keys)
        )

    # 미매핑 → 신규 Event 생성(FSD origin). clique 미달이면 약신호-only 멤버는 HOLD.
    if is_strong and clique_ok:
        return EventRoutingDecision(cluster_id, ACTION_CREATE, None, "new_event_strong_clique", ())
    if is_strong and not clique_ok:
        return EventRoutingDecision(
            cluster_id, ACTION_CREATE, None, "new_event_strong_core_weak_hold", held
        )
    return EventRoutingDecision(cluster_id, ACTION_CREATE, None, "new_event_low_confidence", held)

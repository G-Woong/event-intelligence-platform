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


def _homogeneous_publishable(member_source_types: tuple[str, ...]) -> bool:
    """약신호 cluster 발행 자격(ADR#37): 모든 멤버가 **동일한** publishable type(전부 official 또는 전부
    article)일 때만 True. 혼합(official+article·community 섞임)이나 비-publishable 단일 타입은 False.
    → 약신호 title-link 로만 묶인 cluster 에서 더 권위 높은 출처(예 official)가 다른 type 을 끌어와 Event
    대표로 발행되는 weak-primary 차단. 동일 타입 약신호(news+news)는 authority 상향 없이 저신뢰 발행."""
    return len(set(member_source_types)) == 1 and member_source_types[0] in _PUBLISHABLE_SOURCE_TYPES


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

    # 약신호(possible_duplicate) 추가 게이트(ADR#37, weak-primary 차단): 강신호 core 가 없는 약신호 cluster 는
    # **모든 멤버가 동일한 publishable type 일 때만**(news+news, official+official) 발행한다. 혼합(official+news)
    # 이나 비-publishable(community/search/market) 섞임은 WITHHELD — 약신호 title-link 로만 묶인 cluster 에서
    # 더 권위 높은 출처(예 official)가 다른 type 을 끌어와 Event 대표로 발행되는 weak-primary 차단(검증 안 된
    # 약신호 결합이 강한 Event 얼굴이 되지 않음). 동일 타입 약신호(news+news)는 authority 상향 없이 저신뢰 발행
    # (delta_summary "…같은 사건으로 추정됩니다" — ADR#29 흐름 보존). 강신호 cluster 는 core-policy(ADR#36) 처리.
    if not is_strong and not _homogeneous_publishable(member_source_types):
        return EventRoutingDecision(
            cluster_id, ACTION_WITHHELD, None, "weak_cluster_not_homogeneous_publishable", tuple(member_keys)
        )

    # 미매핑 → 신규 Event 생성(FSD origin). clique 미달이면 약신호-only 멤버는 HOLD.
    if is_strong and clique_ok:
        return EventRoutingDecision(cluster_id, ACTION_CREATE, None, "new_event_strong_clique", ())
    if is_strong and not clique_ok:
        return EventRoutingDecision(
            cluster_id, ACTION_CREATE, None, "new_event_strong_core_weak_hold", held
        )
    return EventRoutingDecision(cluster_id, ACTION_CREATE, None, "new_event_low_confidence", held)

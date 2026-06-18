"""Source role taxonomy — 기존 source_profiles 메타에서 source 의 **본질적 역할**을 파생한다.

이 모듈은 새 데이터를 만들지 않는다. source_profiles.yaml 의 source_group/purpose/
confirmation_policy/is_community 를 단일 출처로 두고, 그로부터 role/routing_mode/
publication_policy 를 결정론적으로 파생할 뿐이다(이중 하드코딩 금지).

설계 결정 — 역할 vs 운영 상태 분리:
  role(여기) = source 가 "무엇을 위한 것인가"(article body / expansion search / official record /
    structured signal / community early signal / enrichment / periodic event queue).
  final_action(run_orchestration_source_validation) = "이번 run 에서 무엇을 하는가"
    (POLICY_EXCLUDED / RATE_LIMITED_SCHEDULED / NEEDS_KEY / CALLABLE_NOT_PROBED / ...).
  POLICY_EXCLUDED·RATE_LIMITED 는 역할이 아니라 운영 상태다. excluded 된 reuters 도 본질은
  ARTICLE_BODY_SOURCE 이며 단지 final_action 이 SKIPPED 일 뿐이다. 둘을 합쳐야 전체 그림이 된다.

stdlib 만. 신규 설치 0. 네트워크 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ingestion.orchestration.source_profile import SourceProfile

# ── 본질적 역할 enum ──
ARTICLE_BODY = "ARTICLE_BODY_SOURCE"
EXPANSION_SEARCH = "EXPANSION_SEARCH_SOURCE"
OFFICIAL_RECORD = "OFFICIAL_RECORD_SOURCE"
STRUCTURED_SIGNAL = "STRUCTURED_SIGNAL_SOURCE"
COMMUNITY_EARLY_SIGNAL = "COMMUNITY_EARLY_SIGNAL_SOURCE"
ENRICHMENT_ONLY = "ENRICHMENT_ONLY_SOURCE"
PERIODIC_EVENT_QUEUE = "PERIODIC_EVENT_QUEUE_SOURCE"  # cross-cutting 보조 역할

ALL_ROLES = frozenset({
    ARTICLE_BODY, EXPANSION_SEARCH, OFFICIAL_RECORD, STRUCTURED_SIGNAL,
    COMMUNITY_EARLY_SIGNAL, ENRICHMENT_ONLY, PERIODIC_EVENT_QUEUE,
})


@dataclass(frozen=True)
class SourceRoleView:
    source_id: str
    primary_role: str
    roles: tuple[str, ...]
    routing_mode: str
    publication_policy: str
    body_policy: str
    source_group: str
    confirmation_policy: str


def derive_source_role(profile: SourceProfile) -> SourceRoleView:
    """SourceProfile → SourceRoleView. source_group(+is_community) 을 권위 기준으로 파생.

    precedence: community > search > official > market > news > trend/domain > fallback.
    is_community=true 는 source_group 과 무관하게 community 로 본다(naver_blog_search 처럼
    search group 이지만 blog 본문이 community 성격이고 profile 이 명시적으로 표기한 경우).
    """
    grp = (profile.source_group or "").lower()
    is_comm = bool(profile.is_community) or grp == "community"
    conf = profile.confirmation_policy or ""

    if is_comm:
        primary = COMMUNITY_EARLY_SIGNAL
        roles = (COMMUNITY_EARLY_SIGNAL,)
        routing = "hold_corroboration_required"
        pub = "hold_until_corroborated_never_direct_publish"
        body = "preview_only_no_body"
    elif grp == "search":
        primary = EXPANSION_SEARCH
        roles = (EXPANSION_SEARCH,)
        routing = "expansion_candidate_not_evidence"
        pub = "never_direct_publish_expansion_only"
        body = "snippet_only"
    elif grp == "official":
        primary = OFFICIAL_RECORD
        roles = (OFFICIAL_RECORD, PERIODIC_EVENT_QUEUE)
        routing = "backend_sink_evidence_required"
        pub = "published_if_evidence_complete_else_hold"
        body = "schema_record_not_article_body"
    elif grp == "market":
        primary = STRUCTURED_SIGNAL
        roles = (STRUCTURED_SIGNAL,)
        routing = "structured_signal_or_expansion_seed"
        pub = "signal_only_not_article_card"
        body = "numeric_payload_no_body"
    elif grp == "news":
        primary = ARTICLE_BODY
        roles = (ARTICLE_BODY, PERIODIC_EVENT_QUEUE)
        routing = "backend_sink_published_if_body_else_hold"
        pub = "published_if_body_and_evidence_else_hold"
        body = "body_or_snippet_hold"
    elif grp in ("trend", "domain"):
        primary = ENRICHMENT_ONLY
        roles = (ENRICHMENT_ONLY,)
        routing = "enrichment_no_bulk_event_queue"
        pub = "enrichment_no_direct_publish"
        body = "metadata_only"
    else:
        # source_group 미상 → 보수적으로 enrichment(직접 publish 금지) 처리.
        primary = ENRICHMENT_ONLY
        roles = (ENRICHMENT_ONLY,)
        routing = "enrichment_no_bulk_event_queue"
        pub = "enrichment_no_direct_publish"
        body = "metadata_only"

    return SourceRoleView(
        source_id=profile.source_id, primary_role=primary, roles=roles,
        routing_mode=routing, publication_policy=pub, body_policy=body,
        source_group=grp, confirmation_policy=conf,
    )


def derive_all_roles(profiles: Sequence[SourceProfile]) -> list[SourceRoleView]:
    return [derive_source_role(p) for p in profiles]


def roles_by_source(profiles: Sequence[SourceProfile]) -> dict[str, SourceRoleView]:
    return {v.source_id: v for v in derive_all_roles(profiles)}

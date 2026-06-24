"""S2e — dedup 클러스터 → resolver → apply_routing 통합 파이프라인 (deterministic).

cross_source_dedup 출력(클러스터)을 받아 **event_resolver 결정 → event_timeline_service 영속**까지
잇는 배선. 상용 Event Intelligence Pipeline 의 토대:

    source records → cross_source_dedup → [이 모듈] → events/event_updates/cluster_event_map/event_links

설계 경계(중요):
  - **ingestion 비의존:** 클러스터를 duck-typed 로 읽는다(`.cluster_id`/`.confidence`/`.clique_ok`/
    `.duplicate_group`/`.weak_only_members`). cross_source_dedup 의 `CrossSourceDedupResult` 를 그대로
    받지만 import 하지 않아 backend→ingestion 하드 의존을 만들지 않는다.
  - **후보 생성 분리:** 클러스터→`ResolvedCandidate` 매핑은 `candidate_for` 콜백으로 호출자가 제공한다
    (record 형태에 대한 결합을 호출자 측에 둔다).
  - **LLM 경계:** 현재 전 경로 결정론. LLM(중요도 판정·확장 수집 계획·요약·맥락화)은 이 결정론 토대
    **위에** 보조 레이어로 붙이며, raw truth(클러스터·라우팅 결정)를 덮어쓰지 않는다 — 이 모듈은 그
    경계만 열어둔다(현재 미배선).
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.services.event_resolver import ACTION_APPEND, resolve_routing
from backend.app.services.event_timeline_service import (
    ApplyResult,
    ResolvedCandidate,
    apply_routing,
    find_held_parents,
    get_cluster_event,
    map_cluster,
)

# held 승격 title 판정자 타입(ADR#38): (재등장 cluster 제목, parent Event 제목)→같은 사건인가.
# 호출자가 cross_source_dedup.titles_similar(약신호 결합과 동일 기준)를 주입. None=승격 비활성(레거시·하위호환).
TitleMatcher = Callable[[str, str], bool]


class _ClusterLike(Protocol):
    cluster_id: str
    confidence: str
    clique_ok: bool
    duplicate_group: tuple[str, ...]
    weak_only_members: tuple[str, ...]


async def resolve_and_apply_cluster(
    session: AsyncSession,
    cluster: _ClusterLike,
    *,
    candidate: ResolvedCandidate,
    title_matcher: Optional[TitleMatcher] = None,
) -> ApplyResult:
    """클러스터 1개 → 라우팅 결정 → 영속. 결정/영속의 단일 진입점.

    cluster_event_map 을 먼저 조회해 resolver 에 mapped_event_id 를 넘긴다(이미 매핑됐으면 APPEND/HOLD,
    미매핑이면 CREATE). apply_routing 이 CREATE 시 매핑을 재확인(동시성 가드)하므로, 조회→결정→적용
    사이의 race 는 apply_routing 에서 흡수된다.

    **held 승격(ADR#38):** cluster_id 미매핑이고 title_matcher 가 주어지면, 재등장 멤버의 held lineage
    (degenerate→possible→parent)를 조회해 **parent 제목과 재등장 cluster 제목이 같은 사건일 때만** parent 로
    라우팅(mapped_event_id=parent)한다 — 이전에 HOLD 되었던 근거가 나중에 강신호로 재등장할 때 새 중복 Event
    를 만들지 않고 기존 parent 에 APPEND(강신호)/HOLD(약신호)로 잇는다. 제목 불일치면 승격 안 함(독립 사건 →
    CREATE; false-merge 방어 — 무조건 병합 금지). 승격 시 cluster_id→parent 를 매핑해 재처리를 멱등화한다.
    """
    mapped = await get_cluster_event(session, cluster.cluster_id)
    promoted = False
    if mapped is None and title_matcher is not None:
        for parent_id, parent_title in await find_held_parents(
            session, member_keys=tuple(cluster.duplicate_group)
        ):
            if title_matcher(candidate.canonical_title, parent_title or ""):
                mapped = parent_id
                promoted = True
                break
    # source-type publish gate 입력(ADR#33/#36): 우선 candidate.core_source_types(강신호 core 멤버 source_type,
    # weak_only 제외 — candidate_from_cluster 가 채움)로 판정해 **weak_only publishable 로 발행되는 것을 차단**.
    # 미설정(레거시 candidate)이면 candidate.evidence 의 source_type 으로 fallback(하위호환).
    member_source_types = candidate.core_source_types or tuple(
        e["source_type"]
        for e in candidate.evidence
        if isinstance(e, dict) and e.get("source_type")
    )
    decision = resolve_routing(
        cluster_id=cluster.cluster_id,
        confidence=cluster.confidence,
        clique_ok=cluster.clique_ok,
        member_keys=tuple(cluster.duplicate_group),
        weak_only_members=tuple(cluster.weak_only_members),
        mapped_event_id=mapped,
        member_source_types=member_source_types,
    )
    result = await apply_routing(session, decision, candidate=candidate)
    if promoted and result.action == ACTION_APPEND and result.event_id is not None:
        # 재등장 cluster_id → parent 매핑(멱등): 같은 cluster_id 재처리 시 held 재조회 없이 바로 mapped APPEND.
        await map_cluster(session, cluster_id=cluster.cluster_id, event_id=result.event_id)
    return result


async def resolve_and_apply_clusters(
    session: AsyncSession,
    clusters: Iterable[_ClusterLike],
    *,
    candidate_for: Callable[[Any], ResolvedCandidate],
    title_matcher: Optional[TitleMatcher] = None,
) -> list[ApplyResult]:
    """클러스터 목록을 순차 처리. 각 클러스터를 독립 라우팅·영속(결정적·재현 가능).

    candidate_for(cluster) → ResolvedCandidate. 호출자가 record→candidate 매핑을 제공한다.
    title_matcher(재등장 제목, parent 제목)→bool: held 승격 판정자(ADR#38; None=비활성).

    **fail-fast 계약(현재):** 한 클러스터의 `candidate_for` 또는 영속이 예외를 던지면 배치가 중단된다
    (후보 단위 try/except 격리 미구현 — R-ExpansionPartialFailure 와 동형). 앞 클러스터는 각자 commit
    됐으므로 부분 영속 + 나머지 미처리로 끝난다. 후보 단위 격리(실패 클러스터 격리 + audit)는 production
    배선(S5+) 에서 에러 정책과 함께 결정 — 그 전까지 호출자가 격리를 책임진다.
    """
    results: list[ApplyResult] = []
    for cluster in clusters:
        results.append(
            await resolve_and_apply_cluster(
                session, cluster, candidate=candidate_for(cluster), title_matcher=title_matcher
            )
        )
    return results

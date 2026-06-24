"""Event 타임라인 CRUD 영속층 (S2d, ADR#16/#18/#19 / SPEC §21.1 / EVENT_SCHEMA Part 2).

event_resolver(S2c)의 순수 라우팅 결정(APPEND / HOLD / CREATE)을 **실제 DB 영속 동작**으로
연결하는 서비스 계층. decision layer는 수정하지 않는다(읽기만).

핵심 불변식:
  - event_updates 는 **append-only**(INSERT 만; UPDATE/DELETE 없음) → 가역성·감사. CREATE 의 첫 행은
    genesis update(생성 근거; candidate evidence/delta_summary), 이후 행은 변화분 — 둘 다 append-only
    관측 이력이다(ADR#31; 이전 "CREATE 는 update 0" 불변식을 의도적으로 개정).
  - cluster_event_map 은 cluster_id→event_id **단일 진실원천**(on_conflict_do_nothing = 최초 매핑 보존).
  - held_members 는 자동병합 금지 → degenerate held event + event_links(possible) 로 보류(ADR#19).
  - set_snapshot 은 events.snapshot_card_id ↔ event_cards.event_id **쌍방향 정합 강제**(is_snapshot_bidirectional).

방어(R-EventTimelineS2Hardening ②③④):
  - tz-naive datetime → UTC 부착(_ensure_aware).
  - UUID/str 경계(_coerce_uuid) — Pydantic(str)↔ORM(UUID) 혼용 견딤.
  - evidence/source_refs 는 allowlist 키만 영속(_sanitize_*) → 전문 본문/임의 PII 필드 저장 차단.

heat 재산정(§2.4 half-life)·merge_score entity/domain 축은 S2.5/S4 로 이월 — 본 계층은 미터치.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.app.models.event import EventCardORM
from backend.app.models.event_resolution import (
    ClusterEventMapORM,
    EventIdentityCandidateMapORM,
    EventIdentityMapORM,
    EventLinkORM,
)
from backend.app.models.event_timeline import (
    EventORM,
    EventUpdateORM,
    is_snapshot_bidirectional,
)
from backend.app.schemas.events import Event, EventUpdate
from backend.app.services.event_resolver import (
    ACTION_APPEND,
    ACTION_CREATE,
    ACTION_HOLD,
    ACTION_WITHHELD,
    EventRoutingDecision,
)

logger = logging.getLogger(__name__)

# evidence dict 에서 영속을 허용하는 키(EvidenceNode, EVENT_SCHEMA §EvidenceNode).
# allowlist 밖 키(body/raw_text/content/author 등)는 폐기 → 전문 미저장·임의 PII 필드 차단.
_EVIDENCE_ALLOWED_KEYS = frozenset(
    {"url", "source_type", "role", "confidence", "relation", "observed_at"}
)
# allowlist 키의 값은 scalar(또는 datetime)만 허용 — 중첩 dict/list 에 전문/PII 를 숨기는
# 경로 차단(adversarial A-6). bool 은 int 의 subclass 라 자동 포함.
_EVIDENCE_SCALAR_TYPES = (str, int, float, datetime)
_MAX_EVIDENCE_STR_LEN = 2048   # url/라벨 상한 — 본문 길이 텍스트는 거부(전문 저장 차단).
_MAX_SOURCE_REF_LEN = 256      # raw_events.id / cluster_id 식별자 상한.


# ── 입력 모델 ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ResolvedCandidate:
    """resolver 결정을 영속할 때 쓰는 사건 후보(create_event/append_update 공통 입력).

    create_event 는 제목/도메인/태그/엔티티/first_seen 을, append_update 는
    observed_at/delta_summary/evidence/added_domains/source_refs/heat_delta 를 사용한다.
    """

    canonical_title: str
    observed_at: datetime
    delta_summary: str = ""
    domains: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    primary_entity_ids: tuple[str, ...] = ()
    evidence: tuple[Any, ...] = ()
    added_domains: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    heat_delta: float = 0.0
    # primary-authority 가 선정한 대표 멤버 키(ADR#35). apply_routing 이 held_members 에서 이 키를
    # 제외해 **대표 record 가 held degenerate 로 이중 등장하는 것을 차단**(데이터 정합). None=미설정(레거시
    # candidate; 제외 없음 — 하위호환).
    primary_member_key: Optional[str] = None
    # source-type publish gate 입력(ADR#36): 강신호 core 멤버 source_type(weak_only 제외). resolve_and_apply_
    # cluster 가 이걸로 gate 판정 — 강신호 core 에 publishable 없으면 WITHHELD(weak_only publishable 로 발행 금지).
    # ()=미설정(레거시 candidate; resolution_pipeline 이 candidate.evidence 로 fallback — 하위호환).
    core_source_types: tuple[str, ...] = ()
    # cross-batch Event identity anchor(ADR#40, R-CrossBatchEventIdentity): 이 사건의 **강한 identity 키**
    # (publishable 멤버의 canonical_url/official_id 기반 record_key). CREATE/APPEND 시 event_identity_map 에
    # event_id 로 영속되고, 다음 배치의 미매핑 cluster 가 같은 anchor 를 가지면 그 Event 로 APPEND(분열 방지).
    # ()=미설정(레거시 candidate; cross-batch 승격 비활성 — 하위호환). community/market/catalog/약신호 제외(보수).
    identity_keys: tuple[str, ...] = ()
    # deterministic semantic cross-batch identity fingerprint(ADR#41, R-CrossBatchEventIdentity): publishable
    # core 제목의 normalized token-set + date bucket(`semantic_identity_fingerprint`). 공유 strong anchor 가
    # 없어도 같은 사건일 수 있는 후보를 결정론으로 식별한다. **확정 anchor(identity_keys)와 분리** — 매칭 시
    # 자동 병합하지 않고 event_links(possible) 로만 링크(false-merge 0). ()=미설정(후보 비활성 — 하위호환).
    semantic_fingerprints: tuple[str, ...] = ()


@dataclass
class ApplyResult:
    action: str
    event_id: Optional[str]
    held_event_ids: list[str] = field(default_factory=list)
    link_ids: list[str] = field(default_factory=list)


# ── 방어 헬퍼 ──────────────────────────────────────────────────────────────────
def _coerce_uuid(value: Any) -> uuid.UUID:
    """UUID/str 경계 방어 — uuid.UUID 또는 str 을 UUID 로. 잘못된 값은 ValueError."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _coerce_uuid_or_none(value: Any) -> Optional[uuid.UUID]:
    try:
        return _coerce_uuid(value)
    except (ValueError, AttributeError, TypeError):
        return None


def _ensure_aware(dt: datetime) -> datetime:
    """tz-naive datetime → UTC 부착(R-EventTimelineS2Hardening ②). aware 는 그대로."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _sanitize_evidence(items: Any) -> list[dict]:
    """evidence → allowlist 키만 보존(전문 본문/임의 PII 필드 차단, R-EventTimelineS2Hardening ④).

    - dict: allowlist 키만 유지, 과대 문자열 값(본문 길이) 폐기.
    - str(legacy degrade): url 로 간주하되 상한 초과면 폐기.
    """
    out: list[dict] = []
    for it in items or ():
        if isinstance(it, str):
            if it and len(it) <= _MAX_EVIDENCE_STR_LEN:
                out.append({"url": it})
            continue
        if not isinstance(it, dict):
            continue
        clean: dict = {}
        for k, v in it.items():
            if k not in _EVIDENCE_ALLOWED_KEYS:
                continue
            if not isinstance(v, _EVIDENCE_SCALAR_TYPES):
                continue  # 비-scalar(중첩 dict/list 등) 거부 — 본문/PII 은닉 차단(A-6).
            if isinstance(v, str) and len(v) > _MAX_EVIDENCE_STR_LEN:
                continue  # 본문 길이 문자열 거부(전문 미저장).
            clean[k] = v
        if clean:
            out.append(clean)
    return out


def _sanitize_source_refs(items: Any) -> list[str]:
    """source_refs → 짧은 식별자(raw_events.id/cluster_id)만. 과대 문자열(본문) 폐기."""
    out: list[str] = []
    for it in items or ():
        s = str(it)
        if s and len(s) <= _MAX_SOURCE_REF_LEN:
            out.append(s)
    return out


# ── ORM → Pydantic ─────────────────────────────────────────────────────────────
def _orm_to_event(row: EventORM) -> Event:
    return Event(
        id=str(row.id),
        canonical_title=row.canonical_title,
        status=row.status,
        first_seen_at=row.first_seen_at,
        last_update_at=row.last_update_at,
        heat=row.heat,
        domains=list(row.domains or []),
        tags=list(row.tags or []),
        primary_entity_ids=list(row.primary_entity_ids or []),
        snapshot_card_id=str(row.snapshot_card_id) if row.snapshot_card_id else None,
    )


def _orm_to_update(row: EventUpdateORM) -> EventUpdate:
    return EventUpdate(
        id=str(row.id),
        event_id=str(row.event_id),
        observed_at=row.observed_at,
        delta_summary=row.delta_summary,
        evidence=list(row.evidence or []),
        added_domains=list(row.added_domains or []),
        source_refs=list(row.source_refs or []),
        heat_delta=row.heat_delta,
    )


# ── CRUD ───────────────────────────────────────────────────────────────────────
async def create_event(
    session: AsyncSession, *, candidate: ResolvedCandidate, commit: bool = True
) -> str:
    """events INSERT(FSD: first_seen_at = candidate.observed_at). event_id(str) 반환.

    commit=False 면 트랜잭션을 닫지 않는다(apply_routing 단일 원자 커밋 합성용).
    """
    event_id = uuid.uuid4()
    observed = _ensure_aware(candidate.observed_at)
    stmt = pg_insert(EventORM).values(
        id=event_id,
        canonical_title=candidate.canonical_title,
        status="active",
        first_seen_at=observed,
        last_update_at=observed,
        heat=0.0,
        domains=list(candidate.domains),
        tags=list(candidate.tags),
        primary_entity_ids=list(candidate.primary_entity_ids),
    )
    await session.execute(stmt)
    if commit:
        await session.commit()
    return str(event_id)


async def append_update(
    session: AsyncSession, *, event_id: Any, candidate: ResolvedCandidate, commit: bool = True
) -> str:
    """event_updates INSERT(**append-only**) + events.last_update_at 갱신 + first_seen pull-earlier(FSD).

    기존 event_updates 행을 UPDATE/DELETE 하지 않는다(가역성·감사). heat 재산정은 S2.5 이월
    (events.heat 미터치; heat_delta 는 provenance 로 update 행에만 기록). commit=False 면 트랜잭션 미종료.
    """
    eid = _coerce_uuid(event_id)
    observed = _ensure_aware(candidate.observed_at)
    update_id = uuid.uuid4()

    ins = pg_insert(EventUpdateORM).values(
        id=update_id,
        event_id=eid,
        observed_at=observed,
        delta_summary=candidate.delta_summary,
        evidence=_sanitize_evidence(candidate.evidence),
        added_domains=list(candidate.added_domains),
        source_refs=_sanitize_source_refs(candidate.source_refs),
        heat_delta=candidate.heat_delta,
    )
    await session.execute(ins)

    # last_update_at 전진 + first_seen_at 은 과거로만 당김(FSD, §2.3) — LEAST 로 단조 보장.
    upd = (
        update(EventORM)
        .where(EventORM.id == eid)
        .values(
            last_update_at=func.greatest(EventORM.last_update_at, observed),
            first_seen_at=func.least(EventORM.first_seen_at, observed),
            updated_at=func.now(),
        )
    )
    await session.execute(upd)
    if commit:
        await session.commit()
    return str(update_id)


async def get_event(
    session: AsyncSession, event_id: Any
) -> Optional[tuple[Event, list[EventUpdate]]]:
    """Event 1건 + 그 event_updates(observed_at ASC) 조회. 없으면 None."""
    eid = _coerce_uuid_or_none(event_id)
    if eid is None:
        return None
    row = (
        await session.execute(select(EventORM).where(EventORM.id == eid))
    ).scalar_one_or_none()
    if row is None:
        return None
    updates = (
        await session.execute(
            select(EventUpdateORM)
            .where(EventUpdateORM.event_id == eid)
            .order_by(EventUpdateORM.observed_at.asc())
        )
    ).scalars()
    return _orm_to_event(row), [_orm_to_update(u) for u in updates]


async def get_public_event(
    session: AsyncSession, event_id: Any
) -> Optional[tuple[Event, list[EventUpdate]]]:
    """공개 단건 조회 — **매핑된 실 주제만**(held degenerate 단건 우회 차단).

    `get_event` 와 달리 cluster_event_map 매핑 게이트를 강제한다: 미매핑(held degenerate,
    canonical_title=raw member key)은 id 를 알아도 None(→404). 목록 필터(list_events)·event_cards
    단건(published 강제)과 대칭(R-MockCard — 목록 필터를 단건으로 우회하는 노출 차단).
    """
    eid = _coerce_uuid_or_none(event_id)
    if eid is None:
        return None
    mapped = (
        await session.execute(
            select(ClusterEventMapORM.event_id)
            .where(ClusterEventMapORM.event_id == eid)
            .limit(1)
        )
    ).scalar_one_or_none()
    if mapped is None:
        return None
    return await get_event(session, eid)


async def list_events(
    session: AsyncSession, *, limit: int = 20, offset: int = 0
) -> list[Event]:
    """매핑된 Event(실 주제)만 (last_update_at, id) desc 로 조회(공개 목록, read-only).

    **held degenerate event 제외**: HOLD 보류로 만들어진 degenerate event(canonical_title=raw
    member key)는 cluster_event_map 에 매핑되지 않는다 — `id IN (cluster_event_map.event_id)` 로
    매핑된 실 주제만 노출(공개 목록 품질·안전).

    정렬 = (last_update_at desc, **id desc**): last_update_at 동률(같은 배치의 다수 클러스터가 동일
    observed_at 으로 CREATE → first_seen==last_update 동일)에도 **결정적 순서** 보장 →
    offset 페이지네이션의 중복/누락 차단.
    """
    stmt = (
        select(EventORM)
        .where(EventORM.id.in_(select(ClusterEventMapORM.event_id)))
        .order_by(EventORM.last_update_at.desc(), EventORM.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_orm_to_event(r) for r in rows]


async def set_snapshot(
    session: AsyncSession, *, event_id: Any, card_id: Any, commit: bool = True
) -> None:
    """events.snapshot_card_id ↔ event_cards.event_id 쌍방향 정합 강제(is_snapshot_bidirectional).

    ① 카드가 이미 **다른** Event 에 연결돼 있으면 거부(카드 탈취 방지). ② 두 FK 를 같은 트랜잭션에서
    세팅. ③ **실제 영속값을 재조회**해 is_snapshot_bidirectional 로 검증한다(의도값끼리 비교하는
    형식적 단언이 아니라 — adversarial A-1). event 가 없어 UPDATE 가 0행이면 재조회가 None →
    불일치로 raise(존재하지 않는 event 에 스냅샷 세팅 차단). 위반 시 commit 안 함.
    """
    eid = _coerce_uuid(event_id)
    cid = _coerce_uuid(card_id)

    card_event_id = (
        await session.execute(
            select(EventCardORM.event_id).where(EventCardORM.id == cid)
        )
    ).scalar_one_or_none()
    if card_event_id is not None and str(card_event_id) != str(eid):
        raise ValueError(
            "set_snapshot refused: card already linked to a different event"
        )

    await session.execute(
        update(EventCardORM).where(EventCardORM.id == cid).values(event_id=eid)
    )
    await session.execute(
        update(EventORM)
        .where(EventORM.id == eid)
        .values(snapshot_card_id=cid, updated_at=func.now())
    )

    # 세팅 후 **실제 DB 상태**(read-your-writes)를 재조회해 양방향 정합 검증.
    actual_card_event_id = (
        await session.execute(
            select(EventCardORM.event_id).where(EventCardORM.id == cid)
        )
    ).scalar_one_or_none()
    actual_snapshot_card_id = (
        await session.execute(
            select(EventORM.snapshot_card_id).where(EventORM.id == eid)
        )
    ).scalar_one_or_none()
    if not is_snapshot_bidirectional(
        event_id=eid,
        snapshot_card_id=actual_snapshot_card_id,
        card_id=cid,
        card_event_id=actual_card_event_id,
    ):
        raise ValueError("set_snapshot invariant violated: not bidirectional after write")
    if commit:
        await session.commit()


async def get_cluster_event(session: AsyncSession, cluster_id: str) -> Optional[str]:
    """cluster_event_map.get(cluster_id) → event_id(str) 또는 None."""
    row = (
        await session.execute(
            select(ClusterEventMapORM.event_id).where(
                ClusterEventMapORM.cluster_id == cluster_id
            )
        )
    ).scalar_one_or_none()
    return str(row) if row is not None else None


async def map_cluster(
    session: AsyncSession, *, cluster_id: str, event_id: Any, commit: bool = True
) -> str:
    """cluster_id → event_id 영속(단일 진실원천). 이미 매핑돼 있으면 보존(on_conflict_do_nothing).

    반환 = 영속된 event_id(기존 매핑이 있으면 그 값 — 라우팅 단일출처 유지). commit=False 면 미종료.
    """
    eid = _coerce_uuid(event_id)
    stmt = (
        pg_insert(ClusterEventMapORM)
        .values(cluster_id=cluster_id, event_id=eid)
        .on_conflict_do_nothing(index_elements=["cluster_id"])
    )
    await session.execute(stmt)
    if commit:
        await session.commit()
    existing = await get_cluster_event(session, cluster_id)
    return existing if existing is not None else str(eid)


async def find_held_parents(
    session: AsyncSession, *, member_keys: tuple[str, ...]
) -> list[tuple[str, str]]:
    """재등장 멤버의 held lineage 조회(ADR#38 held 승격): degenerate held event(canonical_title==member_key)의
    possible 링크가 가리키는 **매핑된 parent Event** 목록 [(parent_event_id, parent_canonical_title)].

    - degenerate held event 는 canonical_title=record_key(member_key)로 영속됨(apply_routing held 루프).
    - event_links(status='possible') 가 held→parent. parent 는 cluster_event_map 에 매핑된 실 Event 만(공개 주제;
      degenerate 끼리의 링크·미매핑 우회 차단).
    - 결정적 순서(parent id asc)·중복 제거. 빈 입력/무매칭 → []. 호출자(resolve_and_apply_cluster)가 parent 제목과
      재등장 cluster 제목을 title_matcher 로 비교해 same 일 때만 승격(false-merge 방어).
    """
    keys = [str(k) for k in member_keys if k]
    if not keys:
        return []
    de = aliased(EventORM)  # degenerate held event(canonical_title=member_key)
    pe = aliased(EventORM)  # 매핑된 parent event
    stmt = (
        select(EventLinkORM.linked_event_id, pe.canonical_title)
        .select_from(EventLinkORM)
        .join(de, de.id == EventLinkORM.event_id)
        .join(pe, pe.id == EventLinkORM.linked_event_id)
        .where(de.canonical_title.in_(keys))
        .where(EventLinkORM.status == "possible")
        .where(EventLinkORM.linked_event_id.in_(select(ClusterEventMapORM.event_id)))
        .order_by(pe.id.asc())
    )
    rows = (await session.execute(stmt)).all()
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for parent_id, parent_title in rows:
        pid = str(parent_id)
        if pid not in seen:
            seen.add(pid)
            out.append((pid, parent_title))
    return out


async def find_events_by_identity(
    session: AsyncSession, *, identity_keys: tuple[str, ...]
) -> list[str]:
    """identity anchor 들이 가리키는 **기존 매핑 Event** 목록(cross-batch 동일성; ADR#40).

    event_identity_map(identity_key→event_id)에서 주어진 anchor 중 하나라도 매핑된 event_id 를 distinct 로
    반환(결정적 정렬 event_id asc). 보통 0 또는 1개 — 1개면 같은 사건 재등장(→APPEND), 0개면 신규(→CREATE).
    2개 이상이면 cluster 가 서로 다른 기존 Event 두 개의 anchor 를 동시에 가짐(모호) → 호출자가 보수적으로
    승격하지 않는다(잘못된 병합 금지). 빈 입력 → []."""
    keys = [str(k) for k in identity_keys if k]
    if not keys:
        return []
    stmt = (
        select(EventIdentityMapORM.event_id)
        .where(EventIdentityMapORM.identity_key.in_(keys))
        .distinct()
        .order_by(EventIdentityMapORM.event_id.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [str(r) for r in rows]


async def map_event_identities(
    session: AsyncSession, *, identity_keys: tuple[str, ...], event_id: Any, commit: bool = True
) -> None:
    """identity anchor 들 → event_id 영속(cross-batch 동일성 단일 출처; ADR#40).

    각 anchor 를 on_conflict_do_nothing(identity_key) 로 INSERT — **첫 매핑 보존**(안정 identity; 같은 anchor
    가 이미 다른 Event 에 있으면 덮어쓰지 않는다). CREATE/APPEND 시 호출돼 Event 가 자신의 strong anchor 를
    claim → 다음 배치의 같은 anchor cluster 가 이 Event 로 수렴. 빈 입력은 no-op. commit=False 면 미종료."""
    eid = _coerce_uuid(event_id)
    keys = [str(k) for k in identity_keys if k]
    for key in keys:
        stmt = (
            pg_insert(EventIdentityMapORM)
            .values(identity_key=key, event_id=eid)
            .on_conflict_do_nothing(index_elements=["identity_key"])
        )
        await session.execute(stmt)
    if commit:
        await session.commit()


async def find_event_candidates_by_fingerprint(
    session: AsyncSession, *, fingerprints: tuple[str, ...]
) -> list[str]:
    """semantic fingerprint 들이 가리키는 **기존 매핑 Event** 목록(cross-batch 동일성 후보; ADR#41).

    event_identity_candidate(candidate_key→event_id)에서 주어진 fingerprint 중 하나라도 매핑된 event_id 를
    distinct 로 반환(결정론 정렬 event_id asc). 0개=신규(→CREATE, 후보 없음), **정확히 1개**=같은 사건 후보
    (→event_links possible 링크; 자동 병합 아님), 2개 이상=서로 다른 기존 Event 후보 다수(모호)→호출자가
    링크하지 않는다(잘못된 연결 금지). event_identity_map(확정 anchor)과 별개 테이블 — 약한 신호. 빈 입력 → []."""
    keys = [str(k) for k in fingerprints if k]
    if not keys:
        return []
    stmt = (
        select(EventIdentityCandidateMapORM.event_id)
        .where(EventIdentityCandidateMapORM.candidate_key.in_(keys))
        .distinct()
        .order_by(EventIdentityCandidateMapORM.event_id.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [str(r) for r in rows]


async def map_event_candidate_fingerprints(
    session: AsyncSession, *, fingerprints: tuple[str, ...], event_id: Any, commit: bool = True
) -> None:
    """semantic fingerprint 들 → event_id 영속(cross-batch 동일성 후보 단일 출처; ADR#41).

    각 fingerprint 를 on_conflict_do_nothing(candidate_key) 로 INSERT — **첫 매핑 보존**(첫 Event 가 fingerprint
    hub). CREATE/APPEND 시 호출돼 발행 Event 가 자신의 semantic fingerprint 를 claim → 다음 배치의 같은
    fingerprint cluster 가 이 Event 를 후보로 발견(→ possible 링크). 빈 입력은 no-op. commit=False 면 미종료."""
    eid = _coerce_uuid(event_id)
    keys = [str(k) for k in fingerprints if k]
    for key in keys:
        stmt = (
            pg_insert(EventIdentityCandidateMapORM)
            .values(candidate_key=key, event_id=eid)
            .on_conflict_do_nothing(index_elements=["candidate_key"])
        )
        await session.execute(stmt)
    if commit:
        await session.commit()


async def hold_link(
    session: AsyncSession,
    *,
    event_id: Any,
    linked_event_id: Any,
    reason: Optional[str] = None,
    commit: bool = True,
) -> str:
    """event_links(status='possible') INSERT — 약신호/clique 미달 보류(자동병합 금지). link_id 반환.

    commit=False 면 트랜잭션 미종료(apply_routing 원자 합성용).
    """
    link_id = uuid.uuid4()
    stmt = pg_insert(EventLinkORM).values(
        id=link_id,
        event_id=_coerce_uuid(event_id),
        linked_event_id=_coerce_uuid(linked_event_id),
        status="possible",
        reason=reason,
    )
    await session.execute(stmt)
    if commit:
        await session.commit()
    return str(link_id)


# ── resolver 결정 → 영속 적용 ────────────────────────────────────────────────────
async def apply_routing(
    session: AsyncSession,
    decision: EventRoutingDecision,
    *,
    candidate: ResolvedCandidate,
    held_observed_at: Optional[datetime] = None,
) -> ApplyResult:
    """resolver 결정(APPEND/HOLD/CREATE)을 DB 영속으로 적용(ADR#19).

    **트랜잭션 소유 계약(중요):** apply_routing 은 **자신의 트랜잭션을 소유**한다 — 내부 CRUD 를 commit=False
    로 호출하고 정상 경로는 마지막 1회 commit(부분 영속 orphan 0). 단 **동시 CREATE 패배 경로는 전체
    `session.rollback()`** 을 친다(SAVEPOINT 아님). 따라서 호출자는 **보존해야 할 미커밋 작업을 가진 외부
    트랜잭션 안에서 apply_routing 을 호출하면 안 된다**(그 작업이 rollback 으로 함께 폐기됨). 배치
    처리(`event_resolution_pipeline.resolve_and_apply_clusters`)는 클러스터마다 apply_routing 이 자체 commit
    하므로 각 클러스터가 독립 tx → 앞 클러스터는 이미 commit 되어 안전. (배치를 단일 tx 로 묶으려면
    rollback 을 `begin_nested()` SAVEPOINT 로 격리해야 하며 — live-PG 하드닝 이월, adversarial A-1.)

    - CREATE: 먼저 cluster_event_map 조회 → 이미 매핑됐으면(재실행/동시) **orphan event 생성 회피**,
      기존 event 로 append degrade. 미매핑이면 events INSERT + cluster_event_map 기록(A-4) +
      **genesis update 1행**(생성 근거 — candidate 의 delta_summary/evidence 를 첫 타임라인 항목으로
      영속, ADR#31; 이전 "CREATE 는 update 0" 불변식을 의도적으로 개정 — CREATE-only Event 의 빈 상세 해소).
    - APPEND: 매핑된 event 에 event_updates append(자동병합은 강신호 clique 만 — resolver가 이미 판정).
    - HOLD:   append 0(오병합 금지). 매핑 event 유지.
    - held_members(공통): degenerate held event(title=member key) + event_links(possible→primary) 보류.
      동시 CREATE 패배 후에도 held 는 승자(mapped) 에 링크된다(rollback 이후 신규 tx 에서 생성).
      (rich held payload 는 S2e 통합에서 — 여기선 record key 만 보존, 가역.)

    동시성(S2e): cluster_event_map.cluster_id PK(unique) 가 매핑 멱등을 DB 레벨에서 보장한다. CREATE 는
    ① get-first 로 순차 재실행 orphan 회피, ② create→map 후 map 이 **다른** event 를 돌려주면(교차-tx
    동시 CREATE 패배) rollback 으로 우리 orphan event 폐기 + 승자 event 로 append degrade → orphan 0.
    (실 동시 세션·SAVEPOINT 격리 입증은 live Postgres 필요 — 본 로직은 단위로 race 를 시뮬레이션해 검증.)
    """
    if decision.action == ACTION_WITHHELD:
        # source-type publish gate(ADR#33): pure community/search/structured 단독 cross-source 는 직접
        # 발행하지 않는다 — DB 미접근(events/updates/map/links 0)·commit 없음·public timeline 미노출.
        # idempotent: 미매핑 유지라 재실행도 동일 WITHHELD(영속 0).
        return ApplyResult(action=ACTION_WITHHELD, event_id=None)

    result = ApplyResult(action=decision.action, event_id=decision.event_id)

    if decision.action == ACTION_CREATE:
        existing = await get_cluster_event(session, decision.cluster_id)
        if existing is not None:
            # 이미 매핑됨(순차 재실행) → orphan event 생성 회피, 기존 event 로 append degrade.
            await append_update(session, event_id=existing, candidate=candidate, commit=False)
            result.event_id = existing
        else:
            new_id = await create_event(session, candidate=candidate, commit=False)
            mapped = await map_cluster(
                session, cluster_id=decision.cluster_id, event_id=new_id, commit=False
            )
            if mapped != new_id:
                # 교차-tx 동시 CREATE 패배: 우리 event 는 매핑 못 받은 orphan → 전체 rollback 으로 폐기
                # (미커밋 orphan 만 — 호출 계약상 외부 보존 작업 없음) 후 승자(mapped) 로 append degrade.
                # rollback 이후 append/held 는 신규 tx 에서 진행, 함수 끝 1회 commit.
                # (승자는 자신의 tx 에서 genesis update 를 이미 영속 — 여기 degrade append 는 그 위에 누적.)
                await session.rollback()
                await append_update(session, event_id=mapped, candidate=candidate, commit=False)
            else:
                # genesis update(생성 근거, ADR#31): 신규 Event 의 **첫 타임라인 항목**으로 candidate 의
                # delta_summary/evidence/source_refs 를 영속한다. 이게 없으면 CREATE-only Event(실 수집의
                # 대다수)는 상세화면에서 evidence·변화설명이 비어 제품 북극성(증거·업데이트 가시화)을 못 채운다.
                # append-only·감사 불변식 보존(INSERT 만). observed_at==first_seen 이라 FSD GREATEST/LEAST
                # 는 no-op(timestamp 왜곡 0). create_event→map_cluster→genesis 는 함수 끝 1회 commit 으로 원자.
                await append_update(session, event_id=new_id, candidate=candidate, commit=False)
            result.event_id = mapped
    elif decision.action == ACTION_APPEND:
        if decision.event_id is None:
            raise ValueError("APPEND decision missing event_id")
        await append_update(session, event_id=decision.event_id, candidate=candidate, commit=False)
        result.event_id = decision.event_id
    elif decision.action == ACTION_HOLD:
        # 오병합 금지 — append 하지 않는다. held_members 만 보류 기록.
        result.event_id = decision.event_id
    else:  # pragma: no cover - resolver 계약상 도달 불가
        raise ValueError(f"unknown action: {decision.action!r}")

    primary_id = result.event_id
    if decision.held_members and primary_id is not None:
        held_obs = _ensure_aware(held_observed_at or candidate.observed_at)
        for member_key in decision.held_members:
            # primary-authority(ADR#35): candidate 대표로 선정된 멤버는 held degenerate 로 중복 영속하지
            # 않는다 — 같은 record 가 대표 evidence ↔ held degenerate 로 DB 이중 등장하는 것을 차단(데이터
            # 정합). 대표 외 약신호 corroborator 만 held(정당한 다른-출처 보류는 유지). 키 정확 일치만 제외.
            if candidate.primary_member_key is not None and member_key == candidate.primary_member_key:
                continue
            held_event_id = await create_event(
                session,
                candidate=ResolvedCandidate(
                    canonical_title=str(member_key), observed_at=held_obs
                ),
                commit=False,
            )
            link_id = await hold_link(
                session,
                event_id=held_event_id,
                linked_event_id=primary_id,
                reason=f"{decision.reason}:{member_key}",
                commit=False,
            )
            result.held_event_ids.append(held_event_id)
            result.link_ids.append(link_id)

    # cross-batch identity anchor 영속(ADR#40): 발행(CREATE/APPEND)된 Event 가 자신의 strong identity
    # anchor(candidate.identity_keys)를 claim → 다음 배치의 같은 anchor cluster 가 이 Event 로 수렴(분열 방지).
    # WITHHELD/HOLD(미발행)는 anchor 를 claim 하지 않는다(발행 안 된 사건에 identity 부여 금지). 첫 매핑 보존.
    if (
        candidate.identity_keys
        and primary_id is not None
        and decision.action in (ACTION_CREATE, ACTION_APPEND)
    ):
        await map_event_identities(
            session, identity_keys=candidate.identity_keys, event_id=primary_id, commit=False
        )

    # deterministic semantic fingerprint claim(ADR#41): 발행 Event 가 자신의 fingerprint 를 claim → 다음 배치의
    # 같은 fingerprint cluster 가 이 Event 를 cross-batch 동일성 **후보**로 발견(→ possible 링크; 자동 병합 아님).
    # event_identity_candidate(별도 테이블)에 영속 — 확정 anchor(event_identity_map)와 분리. CREATE/APPEND 만
    # (WITHHELD/HOLD 미발행은 claim 안 함). 첫 매핑 보존(첫 Event 가 hub). 실제 링크는 resolve_and_apply_cluster.
    if (
        candidate.semantic_fingerprints
        and primary_id is not None
        and decision.action in (ACTION_CREATE, ACTION_APPEND)
    ):
        await map_event_candidate_fingerprints(
            session, fingerprints=candidate.semantic_fingerprints, event_id=primary_id, commit=False
        )

    await session.commit()  # 단일 원자 커밋(부분 실패 orphan 차단).
    return result

"""Event 타임라인 CRUD 영속층 (S2d, ADR#16/#18/#19 / SPEC §21.1 / EVENT_SCHEMA Part 2).

event_resolver(S2c)의 순수 라우팅 결정(APPEND / HOLD / CREATE)을 **실제 DB 영속 동작**으로
연결하는 서비스 계층. decision layer는 수정하지 않는다(읽기만).

핵심 불변식:
  - event_updates 는 **append-only**(INSERT 만; UPDATE/DELETE 없음) → 가역성·감사.
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

from backend.app.models.event import EventCardORM
from backend.app.models.event_resolution import ClusterEventMapORM, EventLinkORM
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

    **단일 트랜잭션 원자 적용:** 내부 CRUD 를 모두 commit=False 로 호출하고 **마지막에 1회 commit**한다
    → 중간 실패 시 부분 영속(orphan held event/link, 매핑 없는 event) 없음(all-or-nothing, adversarial A-4b).

    - CREATE: 먼저 cluster_event_map 조회 → 이미 매핑됐으면(재실행/동시) **orphan event 생성 회피**,
      기존 event 로 append degrade. 미매핑이면 events INSERT + cluster_event_map 기록(A-4).
    - APPEND: 매핑된 event 에 event_updates append(자동병합은 강신호 clique 만 — resolver가 이미 판정).
    - HOLD:   append 0(오병합 금지). 매핑 event 유지.
    - held_members(공통): degenerate held event(title=member key) + event_links(possible→primary) 보류.
      (rich held payload 는 S2e 통합에서 — 여기선 record key 만 보존, 가역.)

    잔여(S2e): 교차-트랜잭션 동시 CREATE race(둘 다 미매핑 조회 후 각자 create)는 DB unique/lock
    이 필요 — get-first 가드는 순차 재실행 orphan 만 제거. 통합 E2E 에서 확정.
    """
    result = ApplyResult(action=decision.action, event_id=decision.event_id)

    if decision.action == ACTION_CREATE:
        existing = await get_cluster_event(session, decision.cluster_id)
        if existing is not None:
            # 이미 매핑됨(재실행/동시) → orphan event 생성 회피, 기존 event 로 append degrade.
            await append_update(session, event_id=existing, candidate=candidate, commit=False)
            result.event_id = existing
        else:
            new_id = await create_event(session, candidate=candidate, commit=False)
            result.event_id = await map_cluster(
                session, cluster_id=decision.cluster_id, event_id=new_id, commit=False
            )
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

    await session.commit()  # 단일 원자 커밋(부분 실패 orphan 차단).
    return result

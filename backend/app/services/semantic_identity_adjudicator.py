"""Semantic identity adjudicator — shadow/eval 계층 (ADR#42, R-SemanticIdentityAdjudicator).

ADR#41 의 `event_identity_candidate` 는 공유 anchor 없는 같은-사건 후보를 `event_links(possible,
reason='semantic_cross_batch_candidate')` 로 **표면화만** 했다(소비처 0). 이 모듈은 그 possible-link 를
소비하는 **첫 shadow/eval 계층**이다: deterministic feature(title 유사도·날짜 거리·source_type·언어·다중
후보 여부)로 status 를 산출해 `event_identity_adjudication` 에 누적한다.

**절대 불변(상용 안전 계약):**
  - **자동 병합/APPEND 0** — 이 status 로 Event 를 합치지 않는다. shadow/eval 전용. 중복 Event count 미감소.
  - **false-merge surface 0** — events/event_updates/cluster_event_map 를 쓰지 않는다(read-only + adjudication
    테이블만 write). 실제 병합은 labeled eval set + precision 입증 + adversarial 승인 전까지 금지(option C 금지).
  - **API 미노출** — adjudication 은 내부 shadow 테이블(public events API 가 읽지 않음).
  - **source role guard** — community/market/catalog-only·unknown 은 likely_same 후보 불가(insufficient/fail-closed).
  - **결정론** — LLM/embedding 미사용. `AdjudicationFeatures.semantic_score` 는 미래 embedding/LLM hook(현재 None).

분류 status(`ADJUDICATION_STATUSES`):
  likely_same_event · ambiguous · likely_different_event · insufficient_features
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.orchestration.cross_source_dedup import _MIN_SEMANTIC_TOKENS, _jaccard, _title_tokens

from backend.app.models.event_resolution import (
    EventIdentityAdjudicationORM,
    EventLinkORM,
)
from backend.app.models.event_timeline import EventORM, EventUpdateORM

# 분류 status (event_resolution.ADJUDICATION_STATUSES 와 동기 — CheckConstraint 잠금).
ADJ_LIKELY_SAME = "likely_same_event"
ADJ_AMBIGUOUS = "ambiguous"
ADJ_LIKELY_DIFFERENT = "likely_different_event"
ADJ_INSUFFICIENT = "insufficient_features"

# semantic 후보 link 의 reason 라벨(ADR#41 event_resolution_pipeline 이 hold_link 로 기록).
SEMANTIC_LINK_REASON = "semantic_cross_batch_candidate"

# deterministic 임계(테스트로 잠금 — 임의 threshold 금지). title token Jaccard·날짜 거리(일).
_TITLE_SIM_HIGH = 0.8
_DATE_NEAR_DAYS = 1
_DATE_FAR_DAYS = 7

_PUBLISHABLE_SOURCE_TYPES = frozenset({"official", "article"})
# adjudicator 가 인지하는 source_type(이외/빈값=unknown → fail-closed). 값 계약: event_ingest_pipeline
# ._RECORD_TYPE_TO_SOURCE_TYPE 의 치역 + 'catalog'.
_KNOWN_SOURCE_TYPES = frozenset({"official", "article", "signal", "search", "community", "catalog"})


@dataclass(frozen=True)
class EventView:
    """adjudication 입력으로 쓰는 Event 의 결정론 요약(본문/PII 비포함)."""

    event_id: str
    canonical_title: str
    first_seen_at: Optional[datetime]
    source_types: tuple[str, ...]   # 이 Event 의 evidence source_type 집합(event_updates 집계)


@dataclass(frozen=True)
class AdjudicationFeatures:
    candidate_event_id: str
    existing_event_id: str
    title_similarity: float            # token Jaccard(어순무관·stopword 제거)
    date_distance_days: Optional[int]  # |first_seen 차이| 일. None=시점 불명
    both_publishable: bool             # 양쪽 Event 가 publishable(official/article) evidence 보유
    source_type_compatible: bool       # 양쪽이 공통 publishable source_type 보유
    community_only: bool               # 한쪽이라도 evidence 가 community 뿐
    market_only: bool                  # 한쪽이라도 evidence 가 signal(market) 뿐
    catalog_only: bool                 # 한쪽이라도 evidence 가 catalog 뿐
    unknown_present: bool              # 미지/빈 source_type 존재(fail-closed)
    min_significant_tokens: int        # 두 제목 유의미 토큰 수의 최소(generic 가드; ADR#41 fingerprint 와 동기)
    multiple_candidates: bool          # candidate Event 가 서로 다른 기존 Event 다수와 link(모호)
    evidence_count: int                # 양쪽 evidence source_type 총수
    language_hint: str                 # 'ko' | 'latin' | 'mixed' | 'unknown'
    # 미래 embedding/LLM/KG adjudicator hook(현재 None — provider 미배선). 채워지면 classify 가 보조 활용.
    semantic_score: Optional[float] = None


@dataclass(frozen=True)
class AdjudicationResult:
    link_id: str
    status: str
    score: float
    reason: str
    features: AdjudicationFeatures


def _language_hint(*titles: str) -> str:
    has_hangul = any(any("가" <= ch <= "힣" for ch in (t or "")) for t in titles)
    has_latin = any(any(("a" <= ch.lower() <= "z") for ch in (t or "")) for t in titles)
    if has_hangul and has_latin:
        return "mixed"
    if has_hangul:
        return "ko"
    if has_latin:
        return "latin"
    return "unknown"


def _date_distance_days(a: Optional[datetime], b: Optional[datetime]) -> Optional[int]:
    if a is None or b is None:
        return None
    return abs((a.date() - b.date()).days)


def _has_publishable(types: tuple[str, ...]) -> bool:
    return any(t in _PUBLISHABLE_SOURCE_TYPES for t in types)


def _only(types: tuple[str, ...], kind: str) -> bool:
    """이 Event 의 evidence source_type 이 비어있지 않고 전부 kind 인가(예: community 뿐)."""
    return bool(types) and all(t == kind for t in types)


def build_adjudication_features(
    candidate: EventView,
    existing: EventView,
    *,
    multiple_candidates: bool,
    semantic_score: Optional[float] = None,
) -> AdjudicationFeatures:
    """두 Event(후보·기존) → 결정론 adjudication feature. 순수 함수(DB 미접근)."""
    a, b = candidate.source_types, existing.source_types
    tok_a, tok_b = _title_tokens(candidate.canonical_title), _title_tokens(existing.canonical_title)
    return AdjudicationFeatures(
        candidate_event_id=candidate.event_id,
        existing_event_id=existing.event_id,
        title_similarity=_jaccard(tok_a, tok_b),
        date_distance_days=_date_distance_days(candidate.first_seen_at, existing.first_seen_at),
        both_publishable=_has_publishable(a) and _has_publishable(b),
        source_type_compatible=_has_publishable(a) and _has_publishable(b),
        community_only=_only(a, "community") or _only(b, "community"),
        market_only=_only(a, "signal") or _only(b, "signal"),
        catalog_only=_only(a, "catalog") or _only(b, "catalog"),
        unknown_present=any((t not in _KNOWN_SOURCE_TYPES) for t in (a + b)) or not a or not b,
        min_significant_tokens=min(len(tok_a), len(tok_b)),
        multiple_candidates=multiple_candidates,
        evidence_count=len(a) + len(b),
        language_hint=_language_hint(candidate.canonical_title, existing.canonical_title),
        semantic_score=semantic_score,
    )


def classify_identity_candidate(f: AdjudicationFeatures) -> tuple[str, float, str]:
    """feature → (status, score, reason). 결정론·보수.

    우선순위(보수): fail-closed(unknown) → source role(non-publishable) → 신호 부족 → 모호(다중 후보·source
    불호환) → 시점(far) → likely_same(고유사·근접·publishable) → borderline(ambiguous). **어떤 status 도 자동
    병합을 의미하지 않는다**(shadow). score = title_similarity × date_factor(결정론 랭킹용·0..1)."""
    # 1) fail-closed: 미지/빈 source_type 은 판정 불가(안전).
    if f.unknown_present:
        return ADJ_INSUFFICIENT, 0.0, "unknown_source_type_fail_closed"
    # 2) source role guard: community/market/catalog-only 또는 publishable core 부재 → likely_same 후보 불가.
    if not f.both_publishable or f.community_only or f.market_only or f.catalog_only:
        return ADJ_INSUFFICIENT, 0.0, "non_publishable_role"
    # 3) 모호: candidate 가 서로 다른 기존 Event 다수와 link → 자동 판정 보류(잘못 합치지 않음). **title 신호보다
    #    먼저** — 다중 후보 모호성은 eval 에 가장 중요한 신호라 no_title_signal 에 가려지지 않게 한다(adversarial 3a).
    if f.multiple_candidates:
        return ADJ_AMBIGUOUS, 0.0, "multiple_candidate_links"
    # 4) 신호 부족: 제목 token 신호 0 또는 유의미 토큰 < 임계(generic) → 판정 불가(ADR#41 fingerprint 가드와 동기).
    if f.title_similarity <= 0.0:
        return ADJ_INSUFFICIENT, 0.0, "no_title_signal"
    if f.min_significant_tokens < _MIN_SEMANTIC_TOKENS:
        return ADJ_INSUFFICIENT, 0.0, "generic_title"
    # 5) 시점 불명/원거리 → 같은 사건 단정 금지.
    if f.date_distance_days is None:
        return ADJ_INSUFFICIENT, 0.0, "no_date_signal"
    if f.date_distance_days > _DATE_FAR_DAYS:
        return ADJ_LIKELY_DIFFERENT, 0.0, "far_date_distance"
    date_factor = 1.0 if f.date_distance_days <= _DATE_NEAR_DAYS else 0.5
    score = round(f.title_similarity * date_factor, 4)
    # 6) likely_same: 고유사 + 근접 시점 + publishable + 단일 후보. (자동 병합 아님 — shadow 신뢰도 표시.)
    if f.title_similarity >= _TITLE_SIM_HIGH and f.date_distance_days <= _DATE_NEAR_DAYS:
        return ADJ_LIKELY_SAME, score, "high_sim_near_date_publishable"
    # 7) 그 외 = 경계(모호) — 자동 판정 보류.
    return ADJ_AMBIGUOUS, score, "borderline"


def adjudicate(
    candidate: EventView, existing: EventView, *, link_id: str, multiple_candidates: bool
) -> AdjudicationResult:
    """두 Event + link_id → AdjudicationResult(순수). DB 영속은 adjudicate_semantic_links 가 담당."""
    features = build_adjudication_features(candidate, existing, multiple_candidates=multiple_candidates)
    status, score, reason = classify_identity_candidate(features)
    return AdjudicationResult(link_id=link_id, status=status, score=score, reason=reason, features=features)


# ── DB orchestration (shadow read + adjudication write only; events 불변) ─────────────
async def _load_event_view(session: AsyncSession, event_id) -> Optional[EventView]:
    """event_id → EventView(title·first_seen·evidence source_type 집계). 없으면 None. read-only."""
    row = (
        await session.execute(
            select(EventORM.id, EventORM.canonical_title, EventORM.first_seen_at).where(
                EventORM.id == event_id
            )
        )
    ).first()
    if row is None:
        return None
    ev_rows = (
        await session.execute(
            select(EventUpdateORM.evidence).where(EventUpdateORM.event_id == event_id)
        )
    ).scalars().all()
    source_types: list[str] = []
    for evidence in ev_rows:
        for node in evidence or ():
            if isinstance(node, dict):
                st = node.get("source_type")
                if isinstance(st, str) and st:
                    source_types.append(st)
    return EventView(
        event_id=str(row[0]),
        canonical_title=row[1] or "",
        first_seen_at=row[2],
        source_types=tuple(source_types),
    )


async def _semantic_links(
    session: AsyncSession, *,
    after_link_id: Optional[str] = None, only_unadjudicated: bool = False,
    limit: Optional[int] = None,
) -> list[tuple[str, object, object]]:
    """semantic 후보 possible-link 페이지 [(link_id, candidate_event_id, existing_event_id)]. 결정론 정렬(link id asc).

    **keyset(ADR#50, R-LiveIdentityBacklog·O(전체) scan 완화):** after_link_id/only_unadjudicated/limit 를
    **SQL 로 push**(WHERE id > cursor·NOT IN adjudication·LIMIT n) — 전 link 적재 후 메모리 slice 회피(페이지만 반환).
    인자 무지정(default)이면 기존과 동일하게 전체 link 반환(하위호환).

    **정직 경계(cursor 의미):** `event_links.id` 는 **UUIDv4(랜덤)** 라 `id` 순서는 **사전식(byte) 순서이지 시간순이
    아니다**. 따라서 after_link_id 는 한 스냅샷을 **재현 가능한 페이지로 분할**하는 경계일 뿐 "오래된 백로그부터"를 보장하지
    않는다. 진행 중 INSERT 된 link 는 cursor 아래로 떨어질 수 있어 그 keyset 패스에선 누락될 수 있다 — **백로그 완전성
    보장은 cursor 가 아니라 `only_unadjudicated`**(판정된 link 가 빠지며 다음 full/page 스캔에서 미판정 link 가 결국 처리)."""
    stmt = (
        select(EventLinkORM.id, EventLinkORM.event_id, EventLinkORM.linked_event_id)
        .where(EventLinkORM.status == "possible")
        .where(EventLinkORM.reason == SEMANTIC_LINK_REASON)
    )
    if after_link_id is not None:
        stmt = stmt.where(EventLinkORM.id > after_link_id)   # keyset cursor(UUIDv4 byte 순서·시간순 아님·재현 경계)
    if only_unadjudicated:
        # 미판정 link 만 — NOT IN 을 SQL 로(adjudication.link_id PK·non-null → NOT IN 안전·전체 id 적재 회피).
        stmt = stmt.where(~EventLinkORM.id.in_(select(EventIdentityAdjudicationORM.link_id)))
    stmt = stmt.order_by(EventLinkORM.id.asc())
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).all()
    return [(str(r[0]), r[1], r[2]) for r in rows]


async def _candidate_target_counts(
    session: AsyncSession, candidate_ids: set[str]
) -> dict[str, int]:
    """candidate_event_id → 그 candidate 의 **전체** possible-semantic link distinct target 수(ambiguity 판정용).

    **page/cursor/only_unadjudicated 와 무관하게 각 candidate 의 전 target 을 집계**(GROUP BY) — 모호성 정확성
    불변(ADR#49 'cand_targets 는 필터 전 전체' 속성을 candidate-scoped 쿼리로 보존). page candidate 로 한정해
    bounded(전체 link 적재 안 함)."""
    if not candidate_ids:
        return {}
    rows = (
        await session.execute(
            select(EventLinkORM.event_id, func.count(distinct(EventLinkORM.linked_event_id)))
            .where(EventLinkORM.status == "possible")
            .where(EventLinkORM.reason == SEMANTIC_LINK_REASON)
            .where(EventLinkORM.event_id.in_(candidate_ids))
            .group_by(EventLinkORM.event_id)
        )
    ).all()
    return {str(r[0]): int(r[1]) for r in rows}


async def _persist_adjudication(session: AsyncSession, result: AdjudicationResult, *, commit: bool) -> None:
    """adjudication status 영속(idempotent upsert — link_id PK on_conflict_do_update). events 불변."""
    stmt = pg_insert(EventIdentityAdjudicationORM).values(
        link_id=result.link_id, status=result.status, score=result.score, reason=result.reason
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["link_id"],
        set_={"status": result.status, "score": result.score, "reason": result.reason},
    )
    await session.execute(stmt)
    if commit:
        await session.commit()


async def adjudicate_semantic_links(
    session: AsyncSession, *, persist: bool = True,
    only_unadjudicated: bool = False, limit: Optional[int] = None,
    after_link_id: Optional[str] = None,
) -> list[AdjudicationResult]:
    """semantic 후보 link 를 shadow adjudication(소비처 #1). **Event 불변**(read + adjudication write only).

    각 link 의 두 Event 를 읽어 feature·status 산출, persist=True 면 event_identity_adjudication 에 idempotent
    upsert. 자동 병합/APPEND 0. candidate Event 가 서로 다른 기존 Event 다수와 link 면 multiple_candidates=True
    (모호). Event 가 없는 link(삭제 등)는 skip(결과 제외).

    **incremental(ADR#49):** only_unadjudicated=True 면 아직 adjudication 이 없는 link 만(비싼 per-link Event view
    load + persist 를 pending 에 한정 — 전수 재판정 회피). limit 이면 link id 정렬 순 상위 N(결정론 chunk).

    **keyset(ADR#50, O(전체) scan 완화):** after_link_id 면 그 cursor **초과** link 만(페이지네이션·UUIDv4 byte 순서·
    시간순 아님·진행 보장은 only_unadjudicated — `_semantic_links` 정직 경계 참조). 위 세 인자는 `_semantic_links` 에서
    SQL 로 push(WHERE id>cursor·NOT IN adjudication·LIMIT) — 전 link 적재 회피. **모호성은 page candidate 한정 GROUP BY**
    (`_candidate_target_counts`)로 각 candidate 의 **전** target 을 집계(cursor/필터/limit 무관) → page 분할이 ambiguity 를
    오염하지 않음. **각 link 의 status 는 page/cursor 분할과 무관하게 default 전체 경로와 동일**(ADR#49 정확성 속성 보존·
    bounded; candidate 가 여러 page 에 흩어지면 GROUP BY 가 page 마다 재실행되는 비용은 있음)."""
    links = await _semantic_links(
        session, after_link_id=after_link_id,
        only_unadjudicated=only_unadjudicated, limit=limit)
    # 모호성: page 의 candidate 들에 대해서만 각자의 **전체** distinct target 수를 집계(정확·bounded).
    cand_counts = await _candidate_target_counts(session, {str(c) for _l, c, _e in links})
    results: list[AdjudicationResult] = []
    views: dict[str, Optional[EventView]] = {}

    async def _view(eid) -> Optional[EventView]:
        key = str(eid)
        if key not in views:
            views[key] = await _load_event_view(session, eid)
        return views[key]

    for link_id, cand, existing in links:
        cv = await _view(cand)
        ev = await _view(existing)
        if cv is None or ev is None:
            continue  # Event 소실 link → shadow 산출 제외(영속 안 함)
        multiple = cand_counts.get(str(cand), 0) > 1
        result = adjudicate(cv, ev, link_id=link_id, multiple_candidates=multiple)
        if persist:
            await _persist_adjudication(session, result, commit=False)
        results.append(result)
    if persist and results:
        await session.commit()
    return results


def summarize_adjudication(results: list[AdjudicationResult]) -> dict:
    """shadow adjudication 분포 집계(eval/monitoring report; secret/본문 비포함).

    by_language: language_hint 분포 — fingerprint 임계의 **언어별 적합성 모니터링** 입력(한국어 어절 4-임계
    캘리브레이션 근거 수집; R-SemanticIdentityAdjudicator gap③). 영어/한국어 status 분포 편향을 드러낸다."""
    counts = {s: 0 for s in (ADJ_LIKELY_SAME, ADJ_AMBIGUOUS, ADJ_LIKELY_DIFFERENT, ADJ_INSUFFICIENT)}
    languages: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
        lang = r.features.language_hint
        languages[lang] = languages.get(lang, 0) + 1
    return {
        "total": len(results),
        "by_status": counts,
        "by_language": languages,   # language_hint 소비처(eval 언어별 모니터링).
        # 자동 병합 0 보장의 명시적 증거(report 소비자가 'merge 안 함'을 확인) — 항상 0.
        "auto_merged": 0,
    }


async def generate_shadow_adjudication_report(session: AsyncSession, *, persist: bool = True) -> dict:
    """semantic 후보 link 전체 shadow adjudication 실행 + 분포 report. **Event count 불변**(merge 0)."""
    results = await adjudicate_semantic_links(session, persist=persist)
    return summarize_adjudication(results)

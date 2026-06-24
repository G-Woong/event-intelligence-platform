"""C — live wiring: 수집 후보(records) → cross_source_dedup → resolver → Event 영속.

**합성/wiring 경계 모듈.** ingestion 의 `cross_source_dedup`(순수 stdlib 결정적 클러스터링)과
backend 의 `event_resolution_pipeline`(라우팅 결정 + 영속)을 잇는 **유일한 backend/app 합성층**.
순수 결정/영속 계층(event_resolver / event_timeline_service / event_resolution_pipeline)은
ingestion 비의존을 유지하고, 이 모듈만 양쪽을 import 한다(경계를 한 곳에 모은다).

흐름:
    수집 후보 records(eq_record dict)
      → cross_source_dedup.cluster_records   (cross-source 중복 클러스터; 단일 멤버 제외)
      → candidate_for 매퍼(클러스터 primary record → ResolvedCandidate; 본문/PII 차단)
      → event_resolution_pipeline.resolve_and_apply_cluster  (APPEND / HOLD / CREATE 영속)
      → events / event_updates / cluster_event_map / event_links

원칙:
  - **feature flag**: `settings.EVENT_RESOLUTION_ENABLED`(기본 off). off 면 영속 0(DB 미접근) —
    기존 event_cards 직접 생성 경로만 동작(비파괴).
  - **event_cards 비파괴**: 이 경로는 events/event_updates 에만 쓴다(event_cards 무변경).
    `event_cards.event_id` 자동 연결은 이번 범위 밖(set_snapshot 명시 연결만; ADR#22).
  - **후보 단위 격리**: 한 클러스터의 매핑/영속 실패가 배치 전체를 멈추지 않는다(try/except +
    rollback + 계속). `resolve_and_apply_clusters`(fail-fast)와 달리 이 진입점은 격리한다
    (production 수집 배치는 부분 실패에 강해야 한다 — R-ExpansionPartialFailure 동형).
  - **LLM 미사용**: 매퍼는 결정적(record 필드만). 요약/중요도/엔티티는 보조 레이어(이월).
  - **PII/본문 차단**: 매퍼는 title(짧은 헤드라인 라벨)·url·record_type·cluster/key 만 후보로
    만든다. 전문 본문/PII 필드는 애초에 싣지 않고, event_timeline_service 의 sanitize 가 2차 차단.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.orchestration.cross_source_dedup import (
    CONF_DUPLICATE,
    cluster_records,
    semantic_identity_fingerprint,
    titles_similar,
)
from ingestion.orchestration.eventqueue_dedup import _external_url, _official_id, compute_record_key

from backend.app.core.config import settings
from backend.app.services.event_resolution_pipeline import resolve_and_apply_cluster
from backend.app.services.semantic_identity_adjudicator import adjudicate_semantic_links
from backend.app.services.event_resolver import (
    ACTION_APPEND,
    ACTION_CREATE,
    ACTION_HOLD,
    ACTION_WITHHELD,
)
from backend.app.services.event_timeline_service import ApplyResult, ResolvedCandidate

logger = logging.getLogger(__name__)

# record_type → evidence.source_type(EvidenceNode allowlist 값). bridge 의 매핑과 동형.
_RECORD_TYPE_TO_SOURCE_TYPE = {
    "article_candidate": "article",
    "official_record": "official",
    "structured_signal": "signal",
    "search_result": "search",
    "community_signal": "community",
    # catalog 메타데이터(R-SourceCatalogFidelity, ADR#40): 비-publishable 'catalog' source_type
    # (_PUBLISHABLE_SOURCE_TYPES={official,article} 밖·authority 0 fail-closed) → catalog 메타가
    # publishable "official" Event 로 발행되는 누수 차단. 역할(KG/entity enrichment)은 라벨로 보존.
    "catalog_metadata": "catalog",
}
_MAX_TITLE_LEN = 512   # 헤드라인 라벨 상한(전문 본문 위장 차단).

# cross-batch identity anchor(ADR#40, R-CrossBatchEventIdentity)로 쓸 수 있는 source_type: publishable
# (official/article)만. community/market/catalog/search/약신호는 단독 identity anchor 금지(보수 —
# 같은 사건 판정의 강한 신호는 canonical_url/official_id 보유 publishable 출처로 한정).
_IDENTITY_ANCHOR_SOURCE_TYPES = frozenset({"official", "article"})

# record_type → 사용자용 출처 종류 라벨(delta_summary 자연어화). allowlist 밖은 라벨 생략.
_SOURCE_KIND_KO = {
    "article_candidate": "뉴스",
    "official_record": "공식",
    "structured_signal": "구조화 지표",
    "search_result": "검색",
    "community_signal": "커뮤니티",
    "catalog_metadata": "카탈로그",
}

# source_type → primary-authority 순위(ADR#34): mixed cluster 에서 Event 대표(primary)를 고를 때
# **공식>뉴스>구조화 지표>검색>커뮤니티>미지** 순. publishable(official/article)이 비-publishable
# (signal/search/community)보다 항상 높아, 발행 Event 의 title/대표 evidence 가 community/market 으로
# 잘못 잡히는 것을 차단(R-SourceTypeFidelityGate). 미지 source_type 은 0(fail-closed authority).
_SOURCE_TYPE_AUTHORITY = {"official": 5, "article": 4, "signal": 3, "search": 2, "community": 1}


def _authority_of(record: dict) -> int:
    st = _RECORD_TYPE_TO_SOURCE_TYPE.get(record.get("record_type"), "rss")
    return _SOURCE_TYPE_AUTHORITY.get(st, 0)


def _select_primary_by_authority(
    distinct_members: tuple[str, ...], index: dict[str, dict]
) -> Optional[str]:
    """distinct 멤버 중 **최고 authority** source 의 키. 동률은 입력 순서(=cross_source_dedup
    members 순서, 결정적). index 에 존재하는 멤버가 없으면 None(호출자가 fallback)."""
    present = [m for m in distinct_members if index.get(m)]
    if not present:
        return None
    return max(present, key=lambda m: _authority_of(index[m]))


def build_delta_summary(
    *, confidence: Optional[str], reason: Optional[str], member_count: int,
    record_type: Optional[str] = None,
) -> str:
    """cross_source_dedup 결과(confidence/reason/멤버수/출처종류) → **사용자용 자연어 변화 설명**.

    기존 `f"{confidence}:{reason}"` 디버그 라벨(예 `"duplicate:strong_key_match"`)을 대체한다.
    LLM/network 0(결정적 template). **resolver 가 확인한 사실만** 설명한다(출처 수·교차 신호 강도) —
    원문 본문/허위/투자판단 미생성. 과장 표현("확정/사실/검증 완료") 금지: 강신호=`보도했습니다`,
    약신호=`추정됩니다(자동 병합 전 교차 검토)`. (`reason` 은 향후 세분화 여지로 받되 현재 미사용.)
    """
    # n = **distinct 출처/근거 수**(동일 URL collapse 후). evidence 링크 개수와 일치시켜
    # "N곳"이 화면 evidence 수와 어긋나지 않게 한다(과대계수 차단, adversarial P2-1).
    n = max(int(member_count or 1), 1)
    kind = _SOURCE_KIND_KO.get(record_type or "")
    kind_prefix = f"{kind} " if kind else ""
    if confidence == "duplicate":  # 강신호(동일 링크/식별자)
        if n >= 2:
            return f"서로 다른 {kind_prefix}출처 {n}곳이 동일 식별자로 같은 사건을 보도했습니다."
        # distinct 1(동일 URL이 여러 피드에 실린 경우) — "서로 다른 N곳" 단언 금지.
        return f"{kind_prefix}보도가 동일 식별자로 확인된 사건입니다."
    if confidence == "possible_duplicate":  # 약신호(유사 제목·같은 시점)
        return (
            f"유사한 제목·같은 시점의 {kind_prefix}보도 {n}건이 같은 사건으로 추정됩니다"
            f"(자동 병합 전 교차 검토)."
        )
    return f"교차 출처 신호로 묶인 {kind_prefix}사건입니다(출처 {n}건)."


@dataclass
class EventIngestSummary:
    """ingest_records_to_events 결과 집계(모니터링/감사용; secret/본문 비포함)."""

    enabled: bool
    clusters_total: int = 0
    created: int = 0
    appended: int = 0
    held: int = 0                 # action == HOLD (약신호 전체 보류)
    held_member_links: int = 0    # held_members 로 생성된 event_links(possible) 수(clique 미달 분리)
    withheld_source_type: int = 0 # action == WITHHELD (source-type gate: pure non-publishable 미발행, ADR#33)
    failed: int = 0
    skipped_no_primary: int = 0
    singletons_dropped: int = 0   # 단일 소스 record(클러스터 미형성, cross_source_dedup 단일멤버 제외) 수
    adjudications: int = 0        # 배치 후 shadow adjudication(③) upsert 한 semantic link 수(ADR#48; 자동 병합 0)
    event_ids: list[str] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "clusters_total": self.clusters_total,
            "created": self.created,
            "appended": self.appended,
            "held": self.held,
            "held_member_links": self.held_member_links,
            "withheld_source_type": self.withheld_source_type,
            "failed": self.failed,
            "skipped_no_primary": self.skipped_no_primary,
            "singletons_dropped": self.singletons_dropped,
            "adjudications": self.adjudications,
            "event_ids": list(self.event_ids),
            "failures": list(self.failures),
        }


# ── 매퍼 헬퍼 ─────────────────────────────────────────────────────────────────────
def _parse_observed(raw: Any, *, now: datetime) -> datetime:
    """record 의 published_at_or_observed_at(ISO str) → tz-aware datetime. 파싱 실패 시 now."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str) and raw.strip():
        s = raw.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return now
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return now


def _domain_of(record: dict) -> Optional[str]:
    """record 의 canonical/external URL → host(www. 제거). 없으면 None(본문 비포함)."""
    for key in ("canonical_url", "source_url_or_evidence"):
        val = record.get(key)
        if isinstance(val, str) and val.startswith(("http://", "https://")):
            host = urlparse(val).netloc.lower()
            if host:
                return host[4:] if host.startswith("www.") else host
    return None


def build_record_index(records: Iterable[dict]) -> dict[str, dict]:
    """record 목록 → {dedup_key: record}.

    cross_source_dedup 의 member key 계약과 **동일한** `compute_record_key` 를 쓴다(클러스터
    member key ↔ record 역매핑). 키 없는 record(None)는 제외. 동일 키 충돌 시 첫 record 보존(결정적).
    """
    index: dict[str, dict] = {}
    for rec in records:
        key, _ = compute_record_key(rec)
        if key and key not in index:
            index[key] = rec
    return index


def candidate_from_cluster(
    cluster: Any, index: dict[str, dict], *, now: Optional[datetime] = None
) -> ResolvedCandidate:
    """클러스터 → ResolvedCandidate(결정적·본문/PII 비포함).

    primary record(최고 authority 멤버)의 title/시각/도메인을 사건 후보로, 멤버들의 url/source_type 을
    evidence 로, cluster_id + member key 를 source_refs 로 만든다. 본문 전문/PII 는 싣지 않는다(title 은
    짧은 헤드라인 라벨; event_timeline_service sanitize 가 2차 차단).
    """
    now = now or datetime.now(timezone.utc)
    # 같은 canonical_url 멤버는 동일 member key 로 collapse → distinct key 만 순회(evidence/ref 중복 제거).
    distinct_members = tuple(dict.fromkeys(cluster.duplicate_group))
    # primary-authority + weak-primary 정책(ADR#34/#36): 발행 Event 의 대표(title/도메인/관측시각/
    # delta_summary kind/evidence primary)를 **강신호 core 멤버 중 최고 authority**(official>article>signal>
    # search>community>미지)로 선정. **core-policy(ADR#36)**: 강신호(duplicate) cluster 는 weak_only(약신호로만
    # 끌려온 held 후보)를 대표·발행 근거에서 제외 — 검증 안 된 약신호 멤버가 Event 얼굴이 되거나 비-publishable
    # core 를 weak publishable 로 발행시키는 것 차단(R-FalseMerge 정합). 약신호(possible_duplicate) cluster 는
    # 강신호 core 가 없어 전체를 동등 저신뢰로 본다(ADR#29 뉴스 약신호 흐름 보존). tie=입력순(결정적·회귀 0).
    weak_only = set(getattr(cluster, "weak_only_members", ()) or ())
    is_strong = cluster.confidence == CONF_DUPLICATE
    core_members = tuple(m for m in distinct_members if m not in weak_only) if is_strong else distinct_members
    core_members = core_members or distinct_members  # core 는 members[0] 포함이라 보통 비지 않음(방어)
    primary_key = _select_primary_by_authority(core_members, index) or cluster.primary_record_key
    primary = index.get(primary_key) or {}
    # source-type publish gate(ADR#33/#36) 입력 = **core 멤버 source_type**(weak_only 제외). 강신호 core 에
    # publishable(official/article)이 없으면 발행 차단(weak_only publishable 로는 발행 안 함 = WITHHELD).
    core_source_types = tuple(
        _RECORD_TYPE_TO_SOURCE_TYPE.get((index.get(m) or {}).get("record_type"), "rss")
        for m in core_members if index.get(m)
    )

    title = primary.get("title_or_label")
    canonical_title = (title or f"event:{cluster.cluster_id}")[:_MAX_TITLE_LEN]
    observed_at = _parse_observed(primary.get("published_at_or_observed_at"), now=now)
    domain = _domain_of(primary)
    domains = (domain,) if domain else ()
    rt = primary.get("record_type")
    tags = (str(rt),) if rt else ()

    evidence: list[dict] = []
    for member_key in distinct_members:
        rec = index.get(member_key)
        if not rec:
            continue
        ev: dict = {
            "source_type": _RECORD_TYPE_TO_SOURCE_TYPE.get(rec.get("record_type"), "rss"),
            "relation": "primary" if member_key == primary_key else "corroborates",
        }
        url = rec.get("canonical_url") or _external_url(rec)
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            ev["url"] = url
        evidence.append(ev)

    # cross-batch identity anchor(ADR#40): **강신호 core 멤버**(weak_only/held 제외) 중 publishable
    # (official/article)이고 strong key(canonical_url 또는 official_id 보유)인 멤버의 record_key. 이게
    # event_identity_map 에 영속돼 배치를 넘어 같은 사건을 잇는다. **held(weak_only) 멤버 제외가 핵심** —
    # held 는 이 Event 에 '확정'되지 않은 possible 보류라 그 anchor 를 claim 하면 다른-제목 재등장을 잘못
    # 병합한다(ADR#38 false-merge 방어와 충돌). community/market/catalog/약신호도 anchor 금지(보수).
    identity_keys = tuple(
        m for m in core_members
        if (r := index.get(m)) is not None
        and _RECORD_TYPE_TO_SOURCE_TYPE.get(r.get("record_type")) in _IDENTITY_ANCHOR_SOURCE_TYPES
        and (r.get("canonical_url") or _official_id(_external_url(r)))
    )

    # deterministic semantic cross-batch fingerprint(ADR#41): **publishable core 멤버**(identity_keys 와 동일
    # 자격: official/article·weak_only/held 제외)의 제목 token-set + date bucket. strong anchor(canonical_url/
    # official_id)가 **없어도** 만들 수 있다 — 다른 URL 두 기사가 같은 사건을 보도하는 경우를 잡기 위함. 같은
    # fingerprint cluster 는 자동 병합되지 않고 event_links(possible) 후보로만 링크된다(false-merge 0). generic
    # 제목(유의미 토큰 < 4)·시점 불명은 fingerprint None(보수). dict.fromkeys 로 중복 제거(결정론 순서 보존).
    semantic_fingerprints = tuple(dict.fromkeys(
        fp
        for m in core_members
        if (r := index.get(m)) is not None
        and _RECORD_TYPE_TO_SOURCE_TYPE.get(r.get("record_type")) in _IDENTITY_ANCHOR_SOURCE_TYPES
        if (fp := semantic_identity_fingerprint(
            r.get("title_or_label"), r.get("published_at_or_observed_at")
        )) is not None
    ))

    return ResolvedCandidate(
        canonical_title=canonical_title,
        observed_at=observed_at,
        # 사용자용 자연어 변화 설명(디버그 라벨 `"{confidence}:{reason}"` 대체 — R-EventTimelineRenderHardening②).
        delta_summary=build_delta_summary(
            confidence=cluster.confidence,
            reason=cluster.reason,
            member_count=len(distinct_members),  # distinct 근거 수(evidence 링크 수와 일치, P2-1)
            record_type=rt,
        ),
        domains=domains,
        tags=tags,
        evidence=tuple(evidence),
        added_domains=domains,
        source_refs=(cluster.cluster_id, *distinct_members),
        heat_delta=0.0,
        # 대표 멤버 키(ADR#35): apply_routing 이 held_members 에서 제외(대표 record 의 held degenerate
        # 이중 등장 차단·방어). core-policy(ADR#36)상 primary 는 강신호 core 라 보통 held 에 없음.
        primary_member_key=primary_key,
        # source-type gate 입력(ADR#36): 강신호 core 멤버 source_type(weak_only 제외) → resolver 가
        # core publishable 0이면 WITHHELD. 약신호 cluster 는 전체.
        core_source_types=core_source_types,
        # cross-batch identity anchor(ADR#40): publishable strong-key 멤버 record_key → 배치 넘어 동일성 유지.
        identity_keys=identity_keys,
        # deterministic semantic fingerprint(ADR#41): 공유 anchor 없는 같은-사건 후보 → event_links(possible) 링크.
        semantic_fingerprints=semantic_fingerprints,
    )


def _tally(summary: EventIngestSummary, result: ApplyResult) -> None:
    if result.event_id:
        summary.event_ids.append(result.event_id)
    if result.action == ACTION_CREATE:
        summary.created += 1
    elif result.action == ACTION_APPEND:
        summary.appended += 1
    elif result.action == ACTION_HOLD:
        summary.held += 1
    elif result.action == ACTION_WITHHELD:
        summary.withheld_source_type += 1
    summary.held_member_links += len(result.link_ids)


# ── 진입점 ────────────────────────────────────────────────────────────────────────
async def ingest_records_to_events(
    session: AsyncSession,
    records: Iterable[dict],
    *,
    enabled: Optional[bool] = None,
    adjudicate_semantic: Optional[bool] = None,
    candidate_for: Optional[Callable[[Any], ResolvedCandidate]] = None,
    now: Optional[datetime] = None,
) -> EventIngestSummary:
    """수집 후보 records → Event 타임라인 영속(C live wiring 진입점).

    enabled=None 이면 `settings.EVENT_RESOLUTION_ENABLED` 를 따른다. off 면 클러스터링/영속을
    하지 않고 enabled=False summary 를 반환한다(DB 미접근 — 기존 event_cards 경로만 동작).

    클러스터마다 resolve_and_apply_cluster 를 호출하되 **후보 단위 try/except 격리**: 한 클러스터
    실패는 rollback + 계속(배치 전체 중단 금지). 각 apply_routing 은 자체 트랜잭션을 commit 하므로
    성공 클러스터는 이미 영속됨(부분 영속 안전, orphan 0 은 apply_routing 이 보장).

    **stage③ shadow adjudication 배선(ADR#48 + ADR#49 incremental):** adjudicate_semantic=None 이면
    `settings.EVENT_SEMANTIC_ADJUDICATION_ENABLED`(기본 off). on 이면 클러스터 루프(② semantic 후보 link 누적)
    뒤 `adjudicate_semantic_links(only_unadjudicated=True)`(③)를 실행해 **아직 판정 안 된 link 만** 백로그로
    누적한다 — 매 배치 전수 재판정(O(N)) 회피·**클러스터 0 인 배치에서도 이전 pending link backfill**. **자동 병합 0**
    (read + adjudication write only·Event count 불변·idempotent upsert). off(기본)면 ③ 미실행(하위호환).
    """
    flag = settings.EVENT_RESOLUTION_ENABLED if enabled is None else enabled
    summary = EventIngestSummary(enabled=flag)
    if not flag:
        return summary

    records = list(records)
    clusters = cluster_records(records)
    summary.clusters_total = len(clusters)

    index = build_record_index(records)
    # 단일 소스 사건 가시화(adversarial C): cross_source_dedup 은 단일 멤버 클러스터를 제외하므로
    # 단독 보도 record 는 Event 가 생성되지 않는다 — silent drop 방지 위해 집계만(영속 안 함).
    clustered_keys: set[str] = set()
    for c in clusters:
        clustered_keys.update(c.duplicate_group)
    summary.singletons_dropped = len(set(index) - clustered_keys)

    # 클러스터가 있으면 라우팅·영속(② semantic 후보 link 누적). 클러스터 0 이어도 아래 stage③ backfill 은
    # 실행될 수 있다(ADR#49: 이전 배치의 미판정 pending link 를 incremental 로 처리 — early-return 제거).
    if clusters:
        mapper = candidate_for or (lambda c: candidate_from_cluster(c, index, now=now))
        for cluster in clusters:
            if candidate_for is None and index.get(cluster.primary_record_key) is None:
                # primary record 를 못 찾으면(키 없음) 기본 매퍼가 후보를 합성할 수 없음 → skip(정직 집계).
                summary.skipped_no_primary += 1
                continue
            try:
                result = await resolve_and_apply_cluster(
                    session, cluster, candidate=mapper(cluster), title_matcher=titles_similar
                )
            except Exception as exc:  # 후보 단위 격리 — 한 클러스터 실패가 배치를 멈추지 않음
                await session.rollback()
                summary.failed += 1
                summary.failures.append(
                    {"cluster_id": getattr(cluster, "cluster_id", "?"), "error": type(exc).__name__}
                )
                logger.warning("event ingest cluster failed: %s", type(exc).__name__)
                continue
            _tally(summary, result)

    # stage③ shadow adjudication 배선(ADR#48 + ADR#49 incremental·no-cluster backfill, R-LiveIdentityBacklog):
    # ② semantic 후보 link 가 누적된 뒤(또는 이전 배치의 미판정 pending link) deterministic shadow adjudication 을
    # **only_unadjudicated=True** 로 실행해 event_identity_adjudication 백로그를 누적한다 — 매 배치 전수 재판정(O(N))을
    # 회피하고 **아직 판정 안 된 link 만** 처리(클러스터 0 인 배치에서도 backfill). **자동 병합 0**(read + adjudication
    # upsert only·Event/updates/cmap 미변경). 실패는 격리(배치 summary 를 깨지 않음). idempotent(link_id PK upsert).
    adj_flag = settings.EVENT_SEMANTIC_ADJUDICATION_ENABLED if adjudicate_semantic is None else adjudicate_semantic
    if adj_flag:
        try:
            results = await adjudicate_semantic_links(session, persist=True, only_unadjudicated=True)
            summary.adjudications = len(results)
        except Exception as exc:  # ③ 실패 격리 — 운영 배치(①②)는 이미 영속됨, shadow 만 누락
            await session.rollback()
            summary.failures.append({"stage": "semantic_adjudication", "error": type(exc).__name__})
            logger.warning("semantic adjudication failed: %s", type(exc).__name__)
    return summary


def make_orchestration_event_sink(
    session_factory: Callable[[], Any], *, enabled: Optional[bool] = None
) -> Callable[..., dict]:
    """`run_production_orchestration(event_resolution_sink=...)` 에 주입할 **sync** sink 어댑터.

    session_factory() → AsyncSession async 컨텍스트매니저(예: async_sessionmaker(engine)).
    sink 는 sync 경계(배치 도구)에서 호출되므로 asyncio.run 으로 async ingest 를 구동한다.
    enabled=None 이면 settings.EVENT_RESOLUTION_ENABLED. flag off 면 세션을 열지 않는다(DB 미접근).
    반환: EventIngestSummary.to_dict(). (clusters 인자는 orchestration 호환용; 내부에서 records 로
    재클러스터 — 결정적 동일 결과.)

    **배선 상태(D-1 결선됨, ADR#23):** 이 어댑터는 `backend/app/tools/run_event_orchestration.py`
    (backend-side composition root)가 전용 NullPool 엔진 + session_factory 로 주입한다 — 운영 runner 를
    `--event-resolution`(또는 `EVENT_RESOLUTION_ENABLED=true`)로 실행하면 수집 후보가 Event 로 영속
    (live-PG 입증). **잔여:** 주기 auto-trigger(Celery beat/cron) 미배선 → 자동 주기 가동은 아직(Phase 2
    이월). 즉 결선 *능력* 은 확보, 주기 *자동 가동* 은 미배선.

    **제약(async 호출처):** asyncio.run 은 실행 중 event loop 안에서 호출되면 RuntimeError 다. 현
    orchestration 은 sync 라 안전하나, async 컨텍스트(FastAPI/Celery async)에서 부르려면 async-native
    sink 가 필요하다.
    """

    def _sink(records, clusters=None) -> dict:
        flag = settings.EVENT_RESOLUTION_ENABLED if enabled is None else enabled
        if not flag:
            return EventIngestSummary(enabled=False).to_dict()

        async def _run() -> dict:
            async with session_factory() as session:
                summary = await ingest_records_to_events(session, records, enabled=True)
                return summary.to_dict()

        return asyncio.run(_run())

    return _sink

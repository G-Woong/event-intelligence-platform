from __future__ import annotations

"""C live wiring 단위/통합 — 수집 후보 records → cross_source_dedup → resolver → Event 영속.

검증 수단(정직 명시): **in-memory fake session**(실 Postgres 아님; live-PG 는
test_event_resolution_live_pg.py). 실 cross_source_dedup·candidate_for 매퍼·apply_routing 이
돈다. 실 DB FK/concurrency 는 live-PG 이월.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.selectable import Select

from ingestion.orchestration.cross_source_dedup import cluster_records

from backend.app.services import event_ingest_pipeline as ip
from backend.app.services.event_ingest_pipeline import (
    EventIngestSummary,
    build_delta_summary,
    build_record_index,
    candidate_from_cluster,
    ingest_records_to_events,
    make_orchestration_event_sink,
)


# ── delta_summary 자연어화(R-EventTimelineRenderHardening②) ──────────────────────────
def _is_debug_label(s: str) -> bool:
    # 원시 confidence/reason enum 이 본문에 누출됐는지 탐지(콜론 휴리스틱보다 견고 — adversarial P2-2).
    raw = ("duplicate:", "possible_duplicate:", "strong_key_match", "title_date_similarity")
    return any(r in s for r in raw)


def test_delta_summary_strong_signal_natural_language():
    # distinct 출처 2곳 이상 → "서로 다른 N곳".
    s = build_delta_summary(
        confidence="duplicate", reason="strong_key_match", member_count=2,
        record_type="article_candidate",
    )
    assert s == "서로 다른 뉴스 출처 2곳이 동일 식별자로 같은 사건을 보도했습니다."
    assert not _is_debug_label(s)
    assert all(w not in s for w in ("확정", "검증 완료", "사실로"))   # 과장 표현 금지
    # distinct 1(동일 URL이 여러 피드에) → "서로 다른 N곳" 단언 금지(P2-1).
    s1 = build_delta_summary(
        confidence="duplicate", reason="strong_key_match", member_count=1,
        record_type="article_candidate",
    )
    assert s1 == "뉴스 보도가 동일 식별자로 확인된 사건입니다."
    assert "서로 다른" not in s1 and "1곳" not in s1


def test_delta_summary_weak_signal_hedged():
    s = build_delta_summary(
        confidence="possible_duplicate", reason="title_date_similarity", member_count=3,
        record_type="article_candidate",
    )
    assert "추정됩니다" in s and "자동 병합 전" in s   # 약신호는 단정 금지(헤지)
    assert "3건" in s and not _is_debug_label(s)


@pytest.mark.parametrize("rt,label", [
    ("official_record", "공식"), ("structured_signal", "구조화 지표"),
    ("community_signal", "커뮤니티"), ("search_result", "검색"),
])
def test_delta_summary_source_kind_label(rt, label):
    s = build_delta_summary(confidence="duplicate", reason="strong_key_match", member_count=2, record_type=rt)
    assert label in s and not _is_debug_label(s)


def test_delta_summary_unknown_confidence_safe_fallback():
    # 미지 confidence/None → 안전 fallback(디버그 라벨/예외 없음).
    s = build_delta_summary(confidence=None, reason=None, member_count=0, record_type=None)
    assert s and not _is_debug_label(s) and "사건" in s
    s2 = build_delta_summary(confidence="weird", reason=None, member_count=1, record_type="unknown_type")
    assert s2 and not _is_debug_label(s2)


# ── 입력 record / fake session ────────────────────────────────────────────────────
def _rec(**kw):
    base = {
        "record_type": "article_candidate", "source_id": "bbc",
        "title_or_label": None, "source_url_or_evidence": None, "canonical_url": None,
        "published_at_or_observed_at": None, "body_state_or_signal": "present",
    }
    base.update(kw)
    return base


def _params(stmt):
    return stmt.compile(dialect=postgresql.dialect()).params


class _ScalarList(list):
    """list + .all()(SQLAlchemy ScalarResult 호환 — find_events_by_identity 의 .scalars().all())."""
    def all(self):
        return list(self)


class _Result:
    def __init__(self, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return _ScalarList(self._rows)

    def all(self):
        return list(self._rows)


class _FakeSession:
    """apply_routing 이 쓰는 statement 만 해석하는 최소 in-memory 세션(실 DB 아님)."""

    def __init__(self):
        self.events: dict[str, SimpleNamespace] = {}
        self.updates: list[SimpleNamespace] = []
        self.cmap: dict[str, uuid.UUID] = {}
        self.links: list[SimpleNamespace] = []
        self.cards: dict[str, SimpleNamespace] = {}   # event_cards 무변경 입증용(쓰기 0 기대)
        self.identity: dict[str, uuid.UUID] = {}      # event_identity_map(ADR#40): identity_key→event_id
        self.candidate: dict[str, uuid.UUID] = {}     # event_identity_candidate(ADR#41): candidate_key→event_id
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def execute(self, stmt):
        if isinstance(stmt, Insert):
            return self._insert(stmt)
        if isinstance(stmt, Update):
            return self._update(stmt)
        if isinstance(stmt, Select):
            return self._select(stmt)
        raise NotImplementedError(f"unexpected statement: {type(stmt).__name__}")

    def _insert(self, stmt):
        table = stmt.table.name
        p = _params(stmt)
        if table == "events":
            self.events[str(p["id"])] = SimpleNamespace(snapshot_card_id=None, **p)
        elif table == "event_updates":
            self.updates.append(SimpleNamespace(**p))
        elif table == "cluster_event_map":
            if p["cluster_id"] not in self.cmap:
                self.cmap[p["cluster_id"]] = p["event_id"]
        elif table == "event_links":
            self.links.append(SimpleNamespace(**p))
        elif table == "event_cards":
            self.cards[str(p["id"])] = SimpleNamespace(**p)
        elif table == "event_identity_map":
            # on_conflict_do_nothing(identity_key) = 첫 매핑 보존(ADR#40).
            if p["identity_key"] not in self.identity:
                self.identity[p["identity_key"]] = p["event_id"]
        elif table == "event_identity_candidate":
            # on_conflict_do_nothing(candidate_key) = 첫 매핑 보존(ADR#41 — 첫 Event 가 fingerprint hub).
            if p["candidate_key"] not in self.candidate:
                self.candidate[p["candidate_key"]] = p["event_id"]
        else:
            raise NotImplementedError(f"insert {table}")
        return _Result()

    def _update(self, stmt):
        if stmt.table.name != "events":
            raise NotImplementedError(f"update {stmt.table.name}")
        p = _params(stmt)
        eid = str(stmt.whereclause.right.value)
        observed = next(v for v in p.values() if isinstance(v, datetime))
        row = self.events.get(eid)
        if row is not None:
            row.first_seen_at = min(row.first_seen_at, observed)
            row.last_update_at = max(row.last_update_at, observed)
        return _Result()

    def _select(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        table = entity.__tablename__
        if table == "event_links":
            # find_held_parents(ADR#38) 시뮬: degenerate(canonical_title==member_key)의 possible 링크가
            # 가리키는 **매핑된 parent**(cmap 값) 목록 [(parent_id, parent_title)]. 결정적·중복 제거.
            keys = self._extract_in_values(stmt)
            mapped_parents = {str(v) for v in self.cmap.values()}
            out: list = []
            seen: set[str] = set()
            for ln in self.links:
                if getattr(ln, "status", None) != "possible":
                    continue
                de = self.events.get(str(ln.event_id))
                if de is None or str(de.canonical_title) not in keys:
                    continue
                pid = str(ln.linked_event_id)
                if pid not in mapped_parents or pid in seen:
                    continue
                seen.add(pid)
                parent = self.events.get(pid)
                out.append((ln.linked_event_id, parent.canonical_title if parent else None))
            return _Result(rows=out)
        if table == "event_identity_map":
            # find_events_by_identity(ADR#40) 시뮬: identity_key.in_(keys) 매핑 event_id distinct(정렬).
            keys = self._extract_in_values(stmt)
            eids: list = []
            seen: set[str] = set()
            for k, eid in self.identity.items():
                if k in keys and str(eid) not in seen:
                    seen.add(str(eid))
                    eids.append(eid)
            eids.sort(key=str)   # order_by event_id asc(결정적)
            return _Result(rows=eids)
        if table == "event_identity_candidate":
            # find_event_candidates_by_fingerprint(ADR#41) 시뮬: candidate_key.in_(keys) event_id distinct(정렬).
            keys = self._extract_in_values(stmt)
            ceids: list = []
            cseen: set[str] = set()
            for k, eid in self.candidate.items():
                if k in keys and str(eid) not in cseen:
                    cseen.add(str(eid))
                    ceids.append(eid)
            ceids.sort(key=str)   # order_by event_id asc(결정적)
            return _Result(rows=ceids)
        where_val = stmt.whereclause.right.value if stmt.whereclause is not None else None
        if table == "cluster_event_map":
            return _Result(scalar=self.cmap.get(where_val))
        if table == "events":
            return _Result(scalar=self.events.get(str(where_val)))
        if table == "event_updates":
            rows = sorted((u for u in self.updates if str(u.event_id) == str(where_val)),
                          key=lambda u: u.observed_at)
            return _Result(rows=rows)
        if table == "event_cards":
            return _Result(scalar=self.cards.get(str(where_val)))
        raise NotImplementedError(f"select {table}")

    @staticmethod
    def _extract_in_values(stmt) -> set:
        """find_held_parents 의 canonical_title.in_([...]) 값 추출(첫 list 값 절). 못 찾으면 빈 set."""
        wc = stmt.whereclause
        clauses = list(getattr(wc, "clauses", [wc])) if wc is not None else []
        for c in clauses:
            val = getattr(getattr(c, "right", None), "value", None)
            if isinstance(val, (list, tuple)):
                return {str(x) for x in val}
        return set()


class _ExplodingSession:
    """flag OFF 경로가 DB 를 건드리지 않음을 입증 — 어떤 호출도 즉시 실패."""

    async def execute(self, stmt):  # pragma: no cover - 호출되면 테스트 실패
        raise AssertionError("flag OFF 인데 session.execute 가 호출됨(DB 접근 금지 위반)")

    async def commit(self):  # pragma: no cover
        raise AssertionError("flag OFF 인데 commit 호출됨")

    async def rollback(self):  # pragma: no cover
        raise AssertionError("flag OFF 인데 rollback 호출됨")


def _strong_records():
    # ap+bbc 같은 canonical_url → 강신호 duplicate clique.
    return [
        _rec(source_id="ap", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="bbc", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized", published_at_or_observed_at="2025-06-02"),
    ]


# ── 1. candidate_for 매퍼 ─────────────────────────────────────────────────────────
def test_mapper_maps_primary_record_fields():
    recs = _strong_records()
    clusters = cluster_records(recs)
    idx = build_record_index(recs)
    cand = candidate_from_cluster(clusters[0], idx)
    assert cand.canonical_title == "Hormuz tanker seized"
    assert cand.observed_at == datetime(2025, 6, 2, tzinfo=timezone.utc)
    assert cand.domains == ("wire",)
    assert cand.tags == ("article_candidate",)
    # delta_summary 는 사용자용 자연어(디버그 라벨 `"{confidence}:{reason}"` 아님 — R-EventTimelineRenderHardening②).
    # 강신호+동일 URL → distinct 근거 1개 → "서로 다른 N곳" 단언 금지(evidence 수와 정합, P2-1).
    assert cand.delta_summary == "뉴스 보도가 동일 식별자로 확인된 사건입니다."
    assert len(cand.evidence) == 1 and not _is_debug_label(cand.delta_summary)
    # 같은 canonical_url 멤버는 동일 key 로 collapse → distinct evidence/ref 1개.
    assert cand.evidence == ({"source_type": "article", "relation": "primary", "url": "https://wire/x"},)
    assert cand.source_refs[0].startswith("xcluster:")
    assert len(cand.source_refs) == 2          # cluster_id + distinct member key 1


def test_mapper_no_body_or_pii_only_short_label():
    # 매퍼는 title(짧은 라벨)·url·source_type 만 — 본문/PII 비포함. 과대 title 은 상한 절단.
    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x",
             title_or_label="A" * 5000, published_at_or_observed_at="2025-06-02"),
        _rec(source_id="bbc", canonical_url="https://wire/x",
             title_or_label="A" * 5000, published_at_or_observed_at="2025-06-02"),
    ]
    cand = candidate_from_cluster(cluster_records(recs)[0], build_record_index(recs))
    assert len(cand.canonical_title) == ip._MAX_TITLE_LEN   # 전문 위장 차단
    for ev in cand.evidence:
        assert set(ev).issubset({"source_type", "relation", "url"})  # allowlist 키만


def test_mapper_distinct_urls_preserve_multi_source_evidence():
    # 서로 다른 URL + 같은 title/date(약신호) → distinct member key → 멀티소스 evidence 보존.
    recs = [
        _rec(source_id="ap", canonical_url="https://ap/x",
             title_or_label="Hormuz strait tanker seized navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="bbc", canonical_url="https://bbc/y",
             title_or_label="Hormuz strait tanker seized navy", published_at_or_observed_at="2025-06-02"),
    ]
    clusters = cluster_records(recs)
    cand = candidate_from_cluster(clusters[0], build_record_index(recs))
    urls = {ev.get("url") for ev in cand.evidence}
    assert urls == {"https://ap/x", "https://bbc/y"}          # 두 소스 모두 증거로 보존
    # 약신호 멀티소스(실 검증 코스피/대우건설 동형) → 자연어 delta_summary(헤지·디버그 라벨 아님).
    assert cand.delta_summary == (
        "유사한 제목·같은 시점의 뉴스 보도 2건이 같은 사건으로 추정됩니다(자동 병합 전 교차 검토)."
    )


def test_mapper_fallback_title_when_primary_missing():
    # primary record 가 index 에 없으면 cluster_id 기반 합성 title(크래시 금지).
    fake_cluster = SimpleNamespace(
        cluster_id="xcluster:canon:deadbeef", primary_record_key="canon:deadbeef",
        duplicate_group=("canon:deadbeef",), confidence="duplicate", reason="strong_key_match",
    )
    cand = candidate_from_cluster(fake_cluster, {})
    assert cand.canonical_title == "event:xcluster:canon:deadbeef"


# ── cross-batch identity anchor 생성 정책(ADR#40) ────────────────────────────────
def test_identity_keys_only_publishable_strong_key_core_members():
    # 강신호 cluster: ap(article,canonical)+sec(official,canonical/accession) 강신호 + blog(community) 약신호.
    # identity_keys = publishable(article/official) **강신호 core** strong-key 멤버 only.
    recs = [
        _rec(source_id="ap", record_type="article_candidate", canonical_url="https://ap/x",
             source_url_or_evidence="https://ap/Archives/0001193125-26-000111",
             title_or_label="Reactor scram", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="sec", record_type="official_record", canonical_url="https://sec/o",
             source_url_or_evidence="https://sec/Archives/0001193125-26-000111",
             title_or_label="Reactor scram", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="blog", record_type="community_signal", canonical_url="https://blog/z",
             title_or_label="Reactor scram", published_at_or_observed_at="2025-06-02"),
    ]
    clusters = cluster_records(recs)
    idx = build_record_index(recs)
    cand = candidate_from_cluster(clusters[0], idx)
    from ingestion.orchestration.eventqueue_dedup import compute_record_key
    key_ap = compute_record_key(recs[0])[0]
    key_sec = compute_record_key(recs[1])[0]
    key_blog = compute_record_key(recs[2])[0]
    # ap(article)·sec(official) 는 publishable+canonical → anchor. blog(community) 는 제외.
    assert key_ap in cand.identity_keys
    assert key_sec in cand.identity_keys
    assert key_blog not in cand.identity_keys            # community 는 identity anchor 금지


def test_identity_keys_exclude_weak_only_held_members():
    # 강신호 news core(ap+reuters via accession) + blog 약신호-only(held) → blog 는 core 아님 → anchor 제외.
    recs = [
        _rec(source_id="ap", canonical_url="https://ap/x",
             source_url_or_evidence="https://ap/Archives/0001193125-26-000111",
             title_or_label="Hormuz tanker seized navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="reuters", canonical_url="https://reuters/y",
             source_url_or_evidence="https://reuters/Archives/0001193125-26-000111",
             title_or_label="Hormuz tanker seized navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="blog", canonical_url="https://blog/z",
             title_or_label="Hormuz tanker seized navy", published_at_or_observed_at="2025-06-02"),
    ]
    clusters = cluster_records(recs)
    c = clusters[0]
    assert c.clique_ok is False and len(c.weak_only_members) == 1   # blog 약신호-only
    cand = candidate_from_cluster(c, build_record_index(recs))
    from ingestion.orchestration.eventqueue_dedup import compute_record_key
    key_blog = compute_record_key(recs[2])[0]
    assert key_blog not in cand.identity_keys            # weak_only(held) 는 anchor 금지(false-merge 방어)


def test_identity_keys_empty_for_catalog_cluster():
    # catalog 메타(비-publishable)만의 cluster → identity anchor 0(catalog 는 anchor 금지).
    recs = [
        _rec(source_id="tmdb", record_type="catalog_metadata", canonical_url="https://tmdb/1",
             title_or_label="Some Movie", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="aladin", record_type="catalog_metadata", canonical_url="https://aladin/2",
             title_or_label="Some Movie", published_at_or_observed_at="2025-06-02"),
    ]
    clusters = cluster_records(recs)
    if clusters:                                          # 같은 제목/날짜로 약신호 cluster 형성 시
        cand = candidate_from_cluster(clusters[0], build_record_index(recs))
        assert cand.identity_keys == ()                  # catalog 는 identity anchor 0


# ── cross-batch semantic identity candidate (ADR#41) ──────────────────────────────
_SEM_DATE = "2026-06-24"
_SEM_T1 = "Federal Reserve raises benchmark interest rates today"
_SEM_T2 = "Coastal refinery fire forces mass evacuation nearby"


def _sem_batch(canonical, title=_SEM_T1, date=_SEM_DATE, s1="cnn", s2="npr"):
    # 배치 **내부**는 같은 canonical 강신호 2건 → 깔끔한 단일 Event(held degenerate 없음). 배치 **간**에는
    # canonical 을 다르게 줘 공유 strong anchor 없음을 만든다(같은 제목/날짜면 semantic fingerprint 만 공유).
    return [
        _rec(record_type="article_candidate", source_id=s1, canonical_url=canonical,
             title_or_label=title, published_at_or_observed_at=date),
        _rec(record_type="article_candidate", source_id=s2, canonical_url=canonical,
             title_or_label=title, published_at_or_observed_at=date),
    ]


def test_semantic_fingerprints_populated_for_publishable_long_title():
    recs = _sem_batch("https://a/1")
    cand = candidate_from_cluster(cluster_records(recs)[0], build_record_index(recs))
    assert len(cand.semantic_fingerprints) == 1            # 같은 제목/날짜 → 1 fingerprint(dedup)
    assert cand.semantic_fingerprints[0].startswith("sem:")


def test_semantic_fingerprints_empty_for_generic_short_title():
    # 유의미 토큰 < 4(generic) → fingerprint None → 후보 비활성(충돌 차단).
    recs = _sem_batch("https://a/1", title="Market update")
    cand = candidate_from_cluster(cluster_records(recs)[0], build_record_index(recs))
    assert cand.semantic_fingerprints == ()


def test_semantic_fingerprints_empty_for_non_publishable_community():
    # community(non-publishable) 는 semantic anchor 금지 → fingerprint 0.
    recs = [
        _rec(record_type="community_signal", source_id="hn", canonical_url="https://hn/1",
             title_or_label=_SEM_T1, published_at_or_observed_at=_SEM_DATE),
        _rec(record_type="community_signal", source_id="reddit", canonical_url="https://rd/2",
             title_or_label=_SEM_T1, published_at_or_observed_at=_SEM_DATE),
    ]
    clusters = cluster_records(recs)
    assert clusters
    cand = candidate_from_cluster(clusters[0], build_record_index(recs))
    assert cand.semantic_fingerprints == ()


def test_same_token_set_same_date_forms_single_cluster_in_batch():
    # adversarial 갭 해소(구조적): 같은 token-set + 같은 날 record 들은 cross_source_dedup 의 약신호 title-link
    # (Jaccard≥0.8)로 **한 cluster 로 병합**된다 → 한 배치 안에서 같은 fingerprint 가 두 독립 cluster 로 갈리지
    # 않는다(in-batch 이중 CREATE·자기-링크 구조적 불가). semantic 후보 링크는 그래서 진짜 cross-batch(별 호출)
    # 에서만 발동한다 — same-batch 다중-cluster 오링크 시나리오는 clustering 단계에서 선제 차단된다.
    recs = [
        _rec(record_type="article_candidate", source_id="ap", canonical_url="https://ap/1",
             title_or_label=_SEM_T1, published_at_or_observed_at=_SEM_DATE),
        _rec(record_type="article_candidate", source_id="bbc", canonical_url="https://bbc/2",
             title_or_label=_SEM_T1, published_at_or_observed_at=_SEM_DATE),
    ]
    clusters = cluster_records(recs)
    assert len(clusters) == 1                              # 같은 token-set → 한 cluster(분리 안 됨)


@pytest.mark.asyncio
async def test_cross_batch_semantic_different_url_links_not_merges():
    # 상용 핵심: 공유 anchor 없는 두 다른-URL 배치가 같은 사건(같은 제목·날짜) → **병합 아님**, possible 링크.
    s = _FakeSession()
    await ingest_records_to_events(s, _sem_batch("https://wire/x1"), enabled=True)
    assert len(s.events) == 1 and len(s.candidate) == 1    # E1 + fingerprint claim
    e1 = next(iter(s.events))
    summary2 = await ingest_records_to_events(s, _sem_batch("https://cnn/y"), enabled=True)
    assert summary2.created == 1 and summary2.appended == 0  # 새 독립 Event(자동 병합 0 → false-merge 0)
    assert len(s.events) == 2                                # E1 + E2 (분열 표면화, 병합 안 함)
    sem = [l for l in s.links if getattr(l, "reason", "") == "semantic_cross_batch_candidate"]
    assert len(sem) == 1 and sem[0].status == "possible"
    assert str(sem[0].linked_event_id) == e1                # E2 → E1 후보 링크(병합 아님)


@pytest.mark.asyncio
async def test_cross_batch_semantic_idempotent_no_duplicate_link():
    s = _FakeSession()
    await ingest_records_to_events(s, _sem_batch("https://wire/x1"), enabled=True)
    b2 = _sem_batch("https://cnn/y")
    await ingest_records_to_events(s, b2, enabled=True)     # CREATE E2 + 링크
    await ingest_records_to_events(s, b2, enabled=True)     # 재실행: cluster_id mapped → APPEND, 신규 0
    assert len(s.events) == 2
    sem = [l for l in s.links if getattr(l, "reason", "") == "semantic_cross_batch_candidate"]
    assert len(sem) == 1                                    # 링크 중복 0(멱등)


@pytest.mark.asyncio
async def test_semantic_adjudication_default_off_no_stage3():
    # ADR#48: adjudicate_semantic 기본(off) → 배치 후 stage③ 미실행(adjudications 0)·_FakeSession 무영향(하위호환).
    s = _FakeSession()
    summary = await ingest_records_to_events(s, _sem_batch("https://wire/x1"), enabled=True)
    assert summary.adjudications == 0
    # 명시 False 도 동일(파라미터가 settings flag 보다 우선) — in-memory 세션이 ③ 쿼리에 노출되지 않음.
    s2 = _FakeSession()
    summary2 = await ingest_records_to_events(
        s2, _sem_batch("https://cnn/y"), enabled=True, adjudicate_semantic=False)
    assert summary2.adjudications == 0


@pytest.mark.asyncio
async def test_no_cluster_batch_flag_off_returns_clean():
    # ADR#49: 클러스터 0 배치 + adjudicate off → stage③ 미실행·DB write 0(early-return 제거 회귀·_FakeSession 무영향).
    s = _FakeSession()
    summary = await ingest_records_to_events(s, [], enabled=True)
    assert summary.clusters_total == 0 and summary.adjudications == 0
    assert s.commits == 0 and s.rollbacks == 0   # no-cluster + flag off → DB write 0


@pytest.mark.asyncio
async def test_cross_batch_semantic_different_title_no_link():
    # 다른 제목(다른 token-set)·같은 날 → fingerprint 다름 → 후보 없음 → 링크 0.
    s = _FakeSession()
    await ingest_records_to_events(s, _sem_batch("https://wire/x1"), enabled=True)
    await ingest_records_to_events(s, _sem_batch("https://cnn/y", title=_SEM_T2), enabled=True)
    assert len(s.events) == 2
    assert not any(getattr(l, "reason", "") == "semantic_cross_batch_candidate" for l in s.links)


@pytest.mark.asyncio
async def test_cross_batch_semantic_far_date_no_link():
    # 같은 제목·다른 날(scenario 4) → date bucket 다름 → fingerprint 다름 → 링크 0.
    s = _FakeSession()
    await ingest_records_to_events(s, _sem_batch("https://wire/x1"), enabled=True)
    await ingest_records_to_events(s, _sem_batch("https://cnn/y", date="2026-07-15"), enabled=True)
    assert len(s.events) == 2
    assert not any(getattr(l, "reason", "") == "semantic_cross_batch_candidate" for l in s.links)


@pytest.mark.asyncio
async def test_cross_batch_semantic_ambiguous_no_link():
    # 한 cluster 의 fingerprints 가 서로 다른 기존 Event 2개를 가리키면(모호) → 링크 안 함, 독립 CREATE(scenario 7).
    s = _FakeSession()
    await ingest_records_to_events(s, _sem_batch("https://a1/x", title=_SEM_T1), enabled=True)
    await ingest_records_to_events(s, _sem_batch("https://b1/x", title=_SEM_T2), enabled=True)
    assert len(s.events) == 2 and len(s.candidate) == 2     # E1(F1), E2(F2)
    acc = "0001193125-26-000333"
    b3 = [  # 같은 accession bridge(강신호)·다른 canonical·다른 제목(T1,T2) → core fingerprints {F1, F2}.
        _rec(record_type="article_candidate", source_id="x", canonical_url="https://x/1",
             source_url_or_evidence=f"https://x/Archives/{acc}", title_or_label=_SEM_T1,
             published_at_or_observed_at=_SEM_DATE),
        _rec(record_type="article_candidate", source_id="y", canonical_url="https://y/2",
             source_url_or_evidence=f"https://y/Archives/{acc}", title_or_label=_SEM_T2,
             published_at_or_observed_at=_SEM_DATE),
    ]
    clusters = cluster_records(b3)
    assert len(clusters) == 1 and len(dict.fromkeys(clusters[0].duplicate_group)) == 2
    summary3 = await ingest_records_to_events(s, b3, enabled=True)
    assert summary3.created == 1                            # 모호 → 병합/링크 안 함, 독립 Event
    assert not any(getattr(l, "reason", "") == "semantic_cross_batch_candidate" for l in s.links)


@pytest.mark.asyncio
async def test_strong_anchor_takes_precedence_over_semantic_no_link():
    # 공유 strong anchor(같은 canonical) 재등장은 ADR#40 경로로 APPEND(병합) — semantic 링크 경로 미발동.
    s = _FakeSession()
    await ingest_records_to_events(s, _sem_batch("https://wire/x1"), enabled=True)
    summary2 = await ingest_records_to_events(s, _sem_batch("https://wire/x1"), enabled=True)
    assert summary2.appended == 1 and len(s.events) == 1    # strong anchor APPEND(분열 0)
    assert not any(getattr(l, "reason", "") == "semantic_cross_batch_candidate" for l in s.links)


# ── 2. flag 게이트 ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_flag_off_no_db_access():
    summary = await ingest_records_to_events(_ExplodingSession(), _strong_records(), enabled=False)
    assert summary.enabled is False
    assert summary.clusters_total == 0 and summary.created == 0


@pytest.mark.asyncio
async def test_flag_default_follows_settings(monkeypatch):
    monkeypatch.setattr(ip.settings, "EVENT_RESOLUTION_ENABLED", False)
    s_off = await ingest_records_to_events(_ExplodingSession(), _strong_records())
    assert s_off.enabled is False
    monkeypatch.setattr(ip.settings, "EVENT_RESOLUTION_ENABLED", True)
    s_on = await ingest_records_to_events(_FakeSession(), _strong_records())
    assert s_on.enabled is True and s_on.created == 1


# ── 3. CREATE / APPEND / HOLD live wiring ─────────────────────────────────────────
def test_strong_cluster_id_stable_across_input_order():
    # 강신호(canonical_url 동일) cluster_id 는 입력 순서 불변 → 배치 간 APPEND 누적 안정.
    import itertools
    recs = _strong_records()
    ids = {cluster_records(list(p))[0].cluster_id for p in itertools.permutations(recs)}
    assert len(ids) == 1


def test_weak_cluster_id_stable_across_input_order():
    # ADR#37: 약신호(title-link) cluster_id 도 입력 순서 불변(멤버 키 정렬) → R-FalseMerge 약신호 split 해소.
    import itertools
    recs = [
        _rec(source_id="a", canonical_url="https://a/1",
             title_or_label="mars rover finds water ice deposit today", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="b", canonical_url="https://b/2",
             title_or_label="mars rover finds water ice deposit", published_at_or_observed_at="2025-06-02"),
    ]
    ids = {cluster_records(list(p))[0].cluster_id for p in itertools.permutations(recs)}
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_singletons_dropped_counted_not_silent():
    # 단일 소스 사건(클러스터 미형성)이 silent 누락 아니라 집계로 가시화되는지(adversarial C).
    recs = _strong_records() + [
        _rec(source_id="cnn", canonical_url="https://cnn/z",
             title_or_label="Unrelated lone story", published_at_or_observed_at="2025-07-01"),
    ]
    s = _FakeSession()
    summary = await ingest_records_to_events(s, recs, enabled=True)
    assert summary.created == 1                 # 강신호 클러스터만 Event
    assert summary.singletons_dropped == 1      # 단독 보도(cnn)는 집계로 가시화(영속 0)
    assert len(s.events) == 1


@pytest.mark.asyncio
async def test_create_first_batch():
    s = _FakeSession()
    summary = await ingest_records_to_events(s, _strong_records(), enabled=True)
    assert summary.clusters_total == 1 and summary.created == 1 and summary.appended == 0
    assert len(s.events) == 1 and len(s.cmap) == 1
    assert s.cards == {}                       # event_cards 무변경(이 경로는 events 만 씀)


@pytest.mark.asyncio
async def test_second_batch_appends_not_new_event():
    # 상용 핵심: 같은 사건 2번째 배치 → 새 Event 아님, 기존 Event 에 append.
    s = _FakeSession()
    await ingest_records_to_events(s, _strong_records(), enabled=True)
    summary2 = await ingest_records_to_events(s, _strong_records(), enabled=True)
    assert summary2.appended == 1 and summary2.created == 0
    assert len(s.events) == 1                   # Event 남발 0
    assert len(s.updates) == 2                  # genesis(1번째 배치 CREATE) + 2번째 배치 append


@pytest.mark.asyncio
async def test_rerun_idempotent_no_duplicate_event():
    s = _FakeSession()
    for _ in range(3):
        await ingest_records_to_events(s, _strong_records(), enabled=True)
    assert len(s.events) == 1 and len(s.cmap) == 1
    assert len(s.updates) == 3                   # genesis(1번째 배치) + 2·3번째 배치 append


@pytest.mark.asyncio
async def test_transitive_weak_member_held_not_merged():
    # R-FalseMerge: ap+reuters 강신호 + blog 약신호-only → blog HOLD(event_links possible).
    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="reuters", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="blog", canonical_url="https://blog/z",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
    ]
    s = _FakeSession()
    summary = await ingest_records_to_events(s, recs, enabled=True)
    assert summary.created == 1                  # 강신호 core 새 Event
    assert summary.held_member_links == 1        # blog 분리 보류
    assert len(s.links) == 1 and s.links[0].status == "possible"
    assert len(s.updates) == 1                   # core 의 genesis 1행만(자동병합 0 — blog 미흡수)


# ── source-type publish gate (ADR#33, R-SourceTypeFidelityGate) — ingest 통합 ───────
@pytest.mark.asyncio
async def test_gate_pure_community_cluster_withheld_not_published():
    # pure-community cross-source(동일 canonical_url 강신호) → 발행 금지(WITHHELD), 영속 0.
    recs = [
        _rec(record_type="community_signal", source_id="hn", canonical_url="https://ex.com/p",
             title_or_label="Show X", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="community_signal", source_id="reddit", canonical_url="https://ex.com/p",
             title_or_label="X on ex.com", published_at_or_observed_at="2025-06-02"),
    ]
    s = _FakeSession()
    summary = await ingest_records_to_events(s, recs, enabled=True)
    assert summary.clusters_total == 1                       # 강신호 클러스터는 형성됨
    assert summary.created == 0 and summary.withheld_source_type == 1
    assert len(s.events) == 0 and len(s.updates) == 0 and len(s.cmap) == 0   # 영속 0(미발행·미매핑)


@pytest.mark.asyncio
async def test_gate_pure_structured_signal_key_withheld():
    # structured 2종 동일 signal-key → 발행 금지(투자조언 경계 — 시장 신호 Event화 차단).
    recs = [
        _rec(record_type="structured_signal", source_id="coinbase",
             body_state_or_signal="price_snapshot", title_or_label="BTC spot",
             published_at_or_observed_at="2025-06-02"),
        _rec(record_type="structured_signal", source_id="binance",
             body_state_or_signal="price_snapshot", title_or_label="BTC spot",
             published_at_or_observed_at="2025-06-02"),
    ]
    s = _FakeSession()
    summary = await ingest_records_to_events(s, recs, enabled=True)
    assert summary.created == 0 and summary.withheld_source_type == 1
    assert len(s.events) == 0


@pytest.mark.asyncio
async def test_gate_official_plus_news_publishes_fidelity_preserved():
    # official+news(동일 official_id) → 발행(publishable). evidence 에 official+article 보존(fidelity).
    acc = "0001193125-26-000123"
    recs = [
        _rec(record_type="official_record", source_id="sec",
             source_url_or_evidence=f"https://sec.gov/{acc}-index.htm",
             title_or_label="Acme 8-K", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters",
             source_url_or_evidence=f"https://reuters.com/acme-{acc}",
             canonical_url=f"https://reuters.com/acme-{acc}",
             title_or_label="Acme deal per SEC filing", published_at_or_observed_at="2025-06-02"),
    ]
    s = _FakeSession()
    summary = await ingest_records_to_events(s, recs, enabled=True)
    assert summary.created == 1 and summary.withheld_source_type == 0
    assert len(s.events) == 1
    stypes = {e.get("source_type") for e in s.updates[0].evidence}
    assert "official" in stypes and "article" in stypes      # source_type fidelity 보존


# ── primary-authority (ADR#34) — mixed cluster 대표 선정 ────────────────────────────
def _cluster_and_candidate(recs):
    clusters = cluster_records(recs)
    assert len(clusters) == 1
    return candidate_from_cluster(clusters[0], build_record_index(recs))


def test_primary_authority_official_over_community():
    # community 가 첫 member 라도 official 이 Event 대표(title/primary evidence/kind).
    acc = "0001193125-26-000999"
    recs = [
        _rec(record_type="community_signal", source_id="hn",
             source_url_or_evidence=f"https://forum.example.com/t/{acc}",
             title_or_label="HN discussion thread", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="official_record", source_id="sec",
             source_url_or_evidence=f"https://sec.gov/{acc}-index.htm",
             title_or_label="SEC official filing", published_at_or_observed_at="2025-06-02"),
    ]
    cand = _cluster_and_candidate(recs)
    assert cand.canonical_title == "SEC official filing"         # community 아님 — official 대표
    rel = {e["source_type"]: e["relation"] for e in cand.evidence}
    assert rel["official"] == "primary" and rel["community"] == "corroborates"
    assert "공식" in cand.delta_summary                           # kind 도 official 반영


def test_primary_authority_news_over_market():
    # market(structured) 이 첫 member 라도 news 가 대표(market/numeric 이 Event 주체가 되면 안 됨).
    recs = [
        _rec(record_type="structured_signal", source_id="coinbase",
             body_state_or_signal="signal", source_url_or_evidence="https://api.coinbase.com/x",
             title_or_label="Oil benchmark jumps on supply shock",
             published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters",
             canonical_url="https://reuters.com/oil",
             title_or_label="Oil benchmark jumps on supply shock",
             published_at_or_observed_at="2025-06-02"),
    ]
    cand = _cluster_and_candidate(recs)
    rel = {e["source_type"]: e["relation"] for e in cand.evidence}
    assert rel["article"] == "primary" and rel["signal"] == "corroborates"
    assert "뉴스" in cand.delta_summary                           # market 아님 — news kind


def test_primary_authority_news_over_community_weak():
    # news+community 약신호(유사 제목·URL 다름), community 첫 member → news 대표.
    recs = [
        _rec(record_type="community_signal", source_id="reddit",
             canonical_url="https://reddit.com/r/x/1",
             title_or_label="Major outage hits cloud provider regions",
             published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters",
             canonical_url="https://reuters.com/outage",
             title_or_label="Major outage hits cloud provider regions",
             published_at_or_observed_at="2025-06-02"),
    ]
    cand = _cluster_and_candidate(recs)
    rel = {e["source_type"]: e["relation"] for e in cand.evidence}
    assert rel["article"] == "primary" and rel["community"] == "corroborates"


def test_primary_authority_news_news_tie_keeps_first():
    # 동률(news+news)은 입력 순서 유지(members[0]) — 기존 동작 회귀 0.
    acc = "0001193125-26-000888"
    recs = [
        _rec(record_type="article_candidate", source_id="ap",
             source_url_or_evidence=f"https://ap.example.com/{acc}", title_or_label="AP headline",
             published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters",
             source_url_or_evidence=f"https://reuters.example.com/{acc}", title_or_label="Reuters headline",
             published_at_or_observed_at="2025-06-02"),
    ]
    cand = _cluster_and_candidate(recs)
    assert cand.canonical_title == "AP headline"                 # tie → members[0](ap) 유지


# ── weak-primary 정책 (ADR#36 core-policy) ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_weak_primary_strong_community_core_weak_official_withheld():
    # ADR#36: 강신호 core 가 community(non-publishable) 2 + official 1은 weak_only(약신호 title-link).
    # weak official 로 발행하지 않는다 → WITHHELD(검증 안 된 약신호 멤버가 Event 얼굴이 되거나 비-publishable
    # core 를 weak publishable 로 발행시키는 것 차단). 이전(ADR#34/#35)엔 official 을 대표로 발행했음.
    acc = "0001193125-26-000555"
    recs = [
        _rec(record_type="community_signal", source_id="hn",
             source_url_or_evidence=f"https://hn.example.com/{acc}",
             title_or_label="Cloud outage hits region", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="community_signal", source_id="reddit",
             source_url_or_evidence=f"https://reddit.example.com/{acc}",
             title_or_label="Cloud outage hits region", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="official_record", source_id="sec",
             source_url_or_evidence="https://sec.gov/unrelated-doc",
             title_or_label="Cloud outage hits region", published_at_or_observed_at="2025-06-02"),
    ]
    s = _FakeSession()
    summary = await ingest_records_to_events(s, recs, enabled=True)
    assert summary.clusters_total == 1
    assert summary.created == 0 and summary.withheld_source_type == 1   # weak publishable 로 발행 안 함
    assert len(s.events) == 0 and summary.held_member_links == 0        # 영속 0


@pytest.mark.asyncio
async def test_weak_primary_strong_market_core_weak_news_withheld():
    # ADR#36: 강신호 core 가 structured/market(signal-key) 2 + news 는 weak_only → market 으로 발행 안 함
    # (투자조언 경계 — 시장 신호가 약신호 news 로 Event 화하지 않음). market 이 입력 첫(members[0]) → core.
    recs = [
        _rec(record_type="structured_signal", source_id="coinbase",
             body_state_or_signal="price_snapshot",
             title_or_label="Oil benchmark daily snapshot", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="structured_signal", source_id="binance",
             body_state_or_signal="price_snapshot",
             title_or_label="Oil benchmark daily snapshot", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters",
             canonical_url="https://reuters.com/oil",
             title_or_label="Oil benchmark daily snapshot", published_at_or_observed_at="2025-06-02"),
    ]
    s = _FakeSession()
    summary = await ingest_records_to_events(s, recs, enabled=True)
    assert summary.created == 0 and summary.withheld_source_type == 1
    assert len(s.events) == 0


@pytest.mark.asyncio
async def test_weak_primary_strong_news_core_weak_community_publishes():
    # ADR#36: 강신호 core 가 news 2 + community 1은 weak_only → news 대표 발행, community held(보존).
    acc = "0001193125-26-000444"
    recs = [
        _rec(record_type="article_candidate", source_id="ap",
             source_url_or_evidence=f"https://ap.example.com/{acc}",
             title_or_label="Bank collapse triggers market selloff", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters",
             source_url_or_evidence=f"https://reuters.example.com/{acc}",
             title_or_label="Bank collapse triggers market selloff", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="community_signal", source_id="hn",
             canonical_url="https://news.ycombinator.com/c",
             title_or_label="Bank collapse triggers market selloff", published_at_or_observed_at="2025-06-02"),
    ]
    s = _FakeSession()
    summary = await ingest_records_to_events(s, recs, enabled=True)
    assert summary.created == 1 and summary.withheld_source_type == 0
    assert summary.held_member_links == 1          # community weak_only → held(대표 아님)
    prims = [e for e in s.updates[0].evidence if e.get("relation") == "primary"]
    assert len(prims) == 1 and prims[0]["source_type"] == "article"   # 대표는 news(강신호 core)


@pytest.mark.asyncio
async def test_weak_news_plus_community_withheld():
    # ADR#37 weak-cluster gate: news + community 가 **약신호(possible_duplicate, 다른 canonical·유사 제목)**로만
    # 묶이면 WITHHELD — 비-publishable(community) 섞인 약신호 cluster 는 발행 안 함(weak-link 로 news 를 Event
    # 대표화하지 않음). cf. 강신호 core+weak community held 보존은 test_weak_primary_strong_news_core_weak_community.
    recs = [
        _rec(record_type="article_candidate", source_id="reuters",
             canonical_url="https://reuters.com/outage",
             title_or_label="Major outage hits cloud provider", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="community_signal", source_id="hn",
             canonical_url="https://news.ycombinator.com/x",
             title_or_label="Major outage hits cloud provider", published_at_or_observed_at="2025-06-02"),
    ]
    s = _FakeSession()
    summary = await ingest_records_to_events(s, recs, enabled=True)
    assert summary.created == 0 and summary.withheld_source_type == 1
    assert len(s.events) == 0


@pytest.mark.asyncio
async def test_weak_news_plus_news_publishes_low_confidence():
    # ADR#37: 약신호(possible_duplicate) news+news(다른 canonical·유사 제목) → 발행(전원 publishable, ADR#29 보존).
    recs = [
        _rec(record_type="article_candidate", source_id="ap", canonical_url="https://ap.com/a",
             title_or_label="Coastal refinery fire forces evacuation", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters", canonical_url="https://reuters.com/b",
             title_or_label="Coastal refinery fire forces evacuation nearby", published_at_or_observed_at="2025-06-02"),
    ]
    s = _FakeSession()
    summary = await ingest_records_to_events(s, recs, enabled=True)
    assert summary.clusters_total == 1
    assert summary.created == 1 and summary.withheld_source_type == 0


# ── 입력순서 불변 core/gate (ADR#37 fragility 수정) ────────────────────────────────
@pytest.mark.asyncio
async def test_order_invariant_strong_core_with_weak_periphery_first():
    # fragility 회귀: 단일 강신호 core(news 2 via accession) + community 약신호 주변부. community 를 입력
    # 첫(members[0])에 둬도 core 는 최대 강성분(news)이라 발행 유지(약신호 주변부가 core 가 되어 WITHHELD 되지 않음).
    acc = "0001193125-26-000777"
    news1 = _rec(record_type="article_candidate", source_id="ap",
                 source_url_or_evidence=f"https://ap.example.com/{acc}",
                 title_or_label="Reactor scram at coastal plant", published_at_or_observed_at="2025-06-02")
    news2 = _rec(record_type="article_candidate", source_id="reuters",
                 source_url_or_evidence=f"https://reuters.example.com/{acc}",
                 title_or_label="Reactor scram at coastal plant", published_at_or_observed_at="2025-06-02")
    community = _rec(record_type="community_signal", source_id="hn",
                     canonical_url="https://news.ycombinator.com/r",
                     title_or_label="Reactor scram at coastal plant", published_at_or_observed_at="2025-06-02")
    for recs in ([community, news1, news2], [news1, news2, community]):
        s = _FakeSession()
        summary = await ingest_records_to_events(s, recs, enabled=True)
        assert summary.created == 1 and summary.withheld_source_type == 0   # 강신호 news core → 발행
        prims = [e for e in s.updates[0].evidence if e.get("relation") == "primary"]
        assert len(prims) == 1 and prims[0]["source_type"] == "article"     # 대표 news(community 아님)


@pytest.mark.asyncio
async def test_order_invariant_two_strong_components_publishable_wins():
    # ADR#37 P2-2: 두 강성분(community×2 via accA / official×2 via accB, 동률 크기)이 약신호 title 로만 브릿지.
    # core = 최대 크기 → **동률이면 publishable 성분 우선**(키 사전순 무관) → official 성분이 core → 발행,
    # community 성분은 held. 입력순서 A/B 무관하게 **동일하게 official 발행**(키-자의성 제거). community 대표 0.
    accA = "0001193125-26-000111"
    accB = "0001193125-26-000222"
    title = "Grid operator declares regional emergency"
    cA1 = _rec(record_type="community_signal", source_id="hn",
               source_url_or_evidence=f"https://hn.example.com/{accA}", title_or_label=title, published_at_or_observed_at="2025-06-02")
    cA2 = _rec(record_type="community_signal", source_id="reddit",
               source_url_or_evidence=f"https://reddit.example.com/{accA}", title_or_label=title, published_at_or_observed_at="2025-06-02")
    oB1 = _rec(record_type="official_record", source_id="sec1",
               source_url_or_evidence=f"https://sec.gov/Archives/{accB}", title_or_label=title, published_at_or_observed_at="2025-06-02")
    oB2 = _rec(record_type="official_record", source_id="sec2",
               source_url_or_evidence=f"https://sec.gov/data/{accB}", title_or_label=title, published_at_or_observed_at="2025-06-02")
    for recs in ([cA1, cA2, oB1, oB2], [oB2, oB1, cA2, cA1]):
        s = _FakeSession()
        summary = await ingest_records_to_events(s, recs, enabled=True)
        assert summary.created == 1 and summary.withheld_source_type == 0   # publishable(official) 성분 발행
        prims = [e for e in s.updates[0].evidence if e.get("relation") == "primary"]
        assert len(prims) == 1 and prims[0]["source_type"] == "official"    # 대표 official(community 아님)


def test_publishable_record_types_contract_matches_source_type_mapping():
    # drift 잠금: cross_source_dedup._PUBLISHABLE_RECORD_TYPES 가 record_type→source_type 매핑 + resolver
    # publishable source_type 와 동기. core 강성분 publishable 판정과 발행 gate 가 어긋나지 않도록.
    from ingestion.orchestration.cross_source_dedup import _PUBLISHABLE_RECORD_TYPES
    from backend.app.services.event_ingest_pipeline import _RECORD_TYPE_TO_SOURCE_TYPE
    from backend.app.services.event_resolver import _PUBLISHABLE_SOURCE_TYPES
    derived = {rt for rt, st in _RECORD_TYPE_TO_SOURCE_TYPE.items() if st in _PUBLISHABLE_SOURCE_TYPES}
    assert _PUBLISHABLE_RECORD_TYPES == derived


# ── held 승격 (ADR#38) ─────────────────────────────────────────────────────────
_HP_T = "Reactor scram at coastal nuclear plant"
_HP_ACC_A = "0001193125-26-000111"
_HP_ACC_B = "0001193125-26-000222"


def _hp_batch1(title=_HP_T):
    # 강신호 news core(accA·다른 canonical) + official 약신호 title-link → CREATE P(news), official held.
    return [
        _rec(record_type="article_candidate", source_id="ap", canonical_url="https://ap.com/p1",
             source_url_or_evidence=f"https://ap.com/Archives/{_HP_ACC_A}", title_or_label=title, published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters", canonical_url="https://reuters.com/p2",
             source_url_or_evidence=f"https://reuters.com/Archives/{_HP_ACC_A}", title_or_label=title, published_at_or_observed_at="2025-06-02"),
        _rec(record_type="official_record", source_id="sec", canonical_url="https://sec.gov/o-doc",
             title_or_label=title, published_at_or_observed_at="2025-06-02"),
    ]


def _hp_batch2(title):
    # official(batch1 과 같은 canonical=같은 key) 재등장 + official2 강신호(accB).
    return [
        _rec(record_type="official_record", source_id="sec", canonical_url="https://sec.gov/o-doc",
             source_url_or_evidence=f"https://sec.gov/Archives/{_HP_ACC_B}", title_or_label=title, published_at_or_observed_at="2025-06-03"),
        _rec(record_type="official_record", source_id="sec2", canonical_url="https://sec.gov/o-doc2",
             source_url_or_evidence=f"https://sec.gov/data/{_HP_ACC_B}", title_or_label=title, published_at_or_observed_at="2025-06-03"),
    ]


@pytest.mark.asyncio
async def test_held_promotion_same_title_appends_to_parent():
    # ADR#38: 약신호로 held 된 official 이 강신호 재등장 + 제목 동일 → 새 중복 Event 0, parent APPEND.
    s = _FakeSession()
    s1 = await ingest_records_to_events(s, _hp_batch1(), enabled=True)
    assert s1.created == 1 and s1.held_member_links == 1      # P + official held
    assert len(s.events) == 2                                 # P + held degenerate
    s2 = await ingest_records_to_events(s, _hp_batch2(_HP_T), enabled=True)
    assert s2.created == 0 and s2.appended == 1               # 중복 Event 0 — parent 로 승격 APPEND
    assert len(s.events) == 2                                 # 새 Event 없음


@pytest.mark.asyncio
async def test_held_promotion_different_title_creates_independent():
    # ADR#38 false-merge 방어: held official 재등장 강신호지만 제목 무관 → parent 병합 안 함, 독립 Event CREATE.
    s = _FakeSession()
    await ingest_records_to_events(s, _hp_batch1(), enabled=True)
    assert len(s.events) == 2
    s2 = await ingest_records_to_events(s, _hp_batch2("Unrelated harbor crane maintenance notice"), enabled=True)
    assert s2.created == 1 and s2.appended == 0              # 독립 Event(병합 안 함)
    assert len(s.events) == 3                                # P + held + Q


@pytest.mark.asyncio
async def test_held_promotion_no_lineage_normal_create():
    # held lineage 없으면 승격 영향 0 — 정상 CREATE(회귀: title_matcher 가 무관 cluster 를 병합하지 않음).
    s = _FakeSession()
    s2 = await ingest_records_to_events(s, _hp_batch2(_HP_T), enabled=True)   # batch1 없이 단독
    assert s2.created == 1                                   # held lineage 0 → 정상 신규 Event
    assert len(s.events) == 1


def _hp_batch1_nonpub(held_rt, title=_HP_T):
    # news core(accA) + 비-publishable(community/market) 약신호 title-link → CREATE P, 비-publishable held.
    held = (
        _rec(record_type=held_rt, source_id="hx", canonical_url="https://hx.com/n-doc",
             body_state_or_signal="snap", title_or_label=title, published_at_or_observed_at="2025-06-02")
    )
    return [
        _rec(record_type="article_candidate", source_id="ap", canonical_url="https://ap.com/p1",
             source_url_or_evidence=f"https://ap.com/Archives/{_HP_ACC_A}", title_or_label=title, published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters", canonical_url="https://reuters.com/p2",
             source_url_or_evidence=f"https://reuters.com/Archives/{_HP_ACC_A}", title_or_label=title, published_at_or_observed_at="2025-06-02"),
        held,
    ]


def _hp_batch2_nonpub(held_rt, title):
    # 비-publishable(같은 canonical=같은 key) 재등장 + 동종 2건 강신호(community=accB / market=signal-key).
    common = dict(body_state_or_signal="snap", title_or_label=title, published_at_or_observed_at="2025-06-03")
    if held_rt == "community_signal":
        return [
            _rec(record_type=held_rt, source_id="hx", canonical_url="https://hx.com/n-doc",
                 source_url_or_evidence=f"https://hx.com/Archives/{_HP_ACC_B}", **common),
            _rec(record_type=held_rt, source_id="hx2", canonical_url="https://hx.com/n-doc2",
                 source_url_or_evidence=f"https://hx2.com/Archives/{_HP_ACC_B}", **common),
        ]
    return [  # structured_signal: 동일 signal-key(body|date|title) → 강신호
        _rec(record_type=held_rt, source_id="hx", canonical_url="https://hx.com/n-doc", **common),
        _rec(record_type=held_rt, source_id="hx2", canonical_url="https://hx.com/n-doc2", **common),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("held_rt", ["community_signal", "structured_signal"])
async def test_held_promotion_nonpublishable_title_match_appends_to_parent(held_rt):
    # ADR#38: 비-publishable(community/market) held 가 강신호 재등장 + 제목 동일 → parent 연결(corroborator
    # APPEND), 자체 Event 0(market 투자조언성 Event 금지·community 직접발행 금지 유지).
    s = _FakeSession()
    await ingest_records_to_events(s, _hp_batch1_nonpub(held_rt), enabled=True)
    assert len(s.events) == 2                                # P + 비-publishable held
    s2 = await ingest_records_to_events(s, _hp_batch2_nonpub(held_rt, _HP_T), enabled=True)
    assert s2.created == 0 and s2.appended == 1              # parent APPEND(자체 Event 0)
    assert len(s.events) == 2                                # 새 Event 없음


@pytest.mark.asyncio
@pytest.mark.parametrize("held_rt", ["community_signal", "structured_signal"])
async def test_held_promotion_nonpublishable_title_mismatch_withheld(held_rt):
    # ADR#38 회귀: 비-publishable held 재등장이지만 제목 무관 → 승격 안 함 → CREATE 경로 gate → WITHHELD
    # (pure community/market 직접 발행 차단 유지 — 승격이 gate 를 무력화하지 않음).
    s = _FakeSession()
    await ingest_records_to_events(s, _hp_batch1_nonpub(held_rt), enabled=True)
    s2 = await ingest_records_to_events(
        s, _hp_batch2_nonpub(held_rt, "Totally unrelated quarterly maintenance memo"), enabled=True
    )
    assert s2.created == 0 and s2.withheld_source_type == 1  # 승격 X → 비-publishable gate WITHHELD
    assert len(s.events) == 2                                # 새 Event 0


@pytest.mark.asyncio
async def test_gate_unknown_record_type_fail_closed_withheld():
    # ADR#35 fail-closed: 미지 record_type(→source_type "rss", non-publishable) 단독 cross-source → WITHHELD.
    recs = [
        _rec(record_type="weird_unknown_type", source_id="x", canonical_url="https://ex.com/u1",
             title_or_label="Mystery event today", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="weird_unknown_type", source_id="y", canonical_url="https://ex.com/u2",
             title_or_label="Mystery event today", published_at_or_observed_at="2025-06-02"),
    ]
    s = _FakeSession()
    summary = await ingest_records_to_events(s, recs, enabled=True)
    assert summary.clusters_total == 1                       # 약신호 클러스터는 형성
    assert summary.created == 0 and summary.withheld_source_type == 1   # 미지 → 발행 차단
    assert len(s.events) == 0


# ── 4. 후보 단위 실패 격리 ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_failed_cluster_isolated_not_batch_abort():
    # 클러스터 영속 실패가 예외로 새지 않고 격리된다(rollback + failed 집계 + 정상 종료).
    s = _FakeSession()
    with patch.object(ip, "resolve_and_apply_cluster",
                      new=AsyncMock(side_effect=RuntimeError("boom"))):
        summary = await ingest_records_to_events(s, _strong_records(), enabled=True)
    assert summary.failed == 1 and summary.created == 0
    assert s.rollbacks >= 1
    assert summary.failures and summary.failures[0]["error"] == "RuntimeError"


@pytest.mark.asyncio
async def test_failure_isolation_other_clusters_persist():
    # 2 클러스터: 첫 실패, 둘째 성공 → 둘째는 영속(부분 영속 안전).
    recs = [
        # cluster A: wire/x (ap+bbc)
        _rec(source_id="ap", canonical_url="https://wire/x", title_or_label="A story", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="bbc", canonical_url="https://wire/x", title_or_label="A story", published_at_or_observed_at="2025-06-02"),
        # cluster B: other/y (afp+dpa)
        _rec(source_id="afp", canonical_url="https://other/y", title_or_label="B story", published_at_or_observed_at="2025-06-03"),
        _rec(source_id="dpa", canonical_url="https://other/y", title_or_label="B story", published_at_or_observed_at="2025-06-03"),
    ]
    clusters = cluster_records(recs)
    assert len(clusters) == 2
    fail_id = clusters[0].cluster_id

    s = _FakeSession()

    def _cf(c):
        if c.cluster_id == fail_id:
            raise ValueError("mapper boom")
        return candidate_from_cluster(c, build_record_index(recs))

    summary = await ingest_records_to_events(s, recs, enabled=True, candidate_for=_cf)
    assert summary.failed == 1 and summary.created == 1   # 하나 실패, 하나 영속
    assert len(s.events) == 1
    assert s.rollbacks >= 1


# ── 5. evidence/source_refs sanitize 상류 통과 ────────────────────────────────────
@pytest.mark.asyncio
async def test_evidence_sanitize_through_wiring():
    # 매퍼가 allowlist scalar 만 만들고, 영속도 그대로 유지(본문/PII 차단).
    s = _FakeSession()
    await ingest_records_to_events(s, _strong_records(), enabled=True)       # CREATE
    await ingest_records_to_events(s, _strong_records(), enabled=True)       # APPEND(evidence 영속)
    stored = s.updates[-1]
    for ev in stored.evidence:
        assert set(ev).issubset({"url", "source_type", "role", "confidence", "relation", "observed_at"})
    for ref in stored.source_refs:
        assert len(ref) <= 256


# ── 6. orchestration sink 어댑터 ──────────────────────────────────────────────────
def test_orchestration_sink_flag_off_does_not_open_session():
    # flag off → session_factory 호출 안 함(DB 미접근), enabled=False 반환.
    called = {"n": 0}

    def _factory():  # pragma: no cover - 호출되면 실패
        called["n"] += 1
        raise AssertionError("flag off 인데 session_factory 호출됨")

    sink = make_orchestration_event_sink(_factory, enabled=False)
    out = sink(_strong_records(), None)
    assert out["enabled"] is False and called["n"] == 0


class _AsyncCM:
    """async with 컨텍스트매니저 래퍼(make_orchestration_event_sink ON 경로 실행용)."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def test_orchestration_sink_on_path_runs_ingest():
    # adversarial blocking-A 해소: ON 경로(asyncio.run + async session_factory + 실 ingest)를 실제 실행.
    fake = _FakeSession()
    sink = make_orchestration_event_sink(lambda: _AsyncCM(fake), enabled=True)
    out = sink(_strong_records(), None)
    assert out["enabled"] is True and out["created"] == 1
    assert len(fake.events) == 1 and fake.commits >= 1


def test_summary_to_dict_shape():
    d = EventIngestSummary(enabled=True, created=2, appended=1).to_dict()
    assert d["enabled"] is True and d["created"] == 2 and d["appended"] == 1
    assert "event_ids" in d and "failures" in d

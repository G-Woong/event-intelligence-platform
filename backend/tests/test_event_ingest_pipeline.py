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


class _Result:
    def __init__(self, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return list(self._rows)


class _FakeSession:
    """apply_routing 이 쓰는 statement 만 해석하는 최소 in-memory 세션(실 DB 아님)."""

    def __init__(self):
        self.events: dict[str, SimpleNamespace] = {}
        self.updates: list[SimpleNamespace] = []
        self.cmap: dict[str, uuid.UUID] = {}
        self.links: list[SimpleNamespace] = []
        self.cards: dict[str, SimpleNamespace] = {}   # event_cards 무변경 입증용(쓰기 0 기대)
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

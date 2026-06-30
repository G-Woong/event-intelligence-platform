"""throwaway — 비뉴스 타입 Event 형성/라우팅/fidelity 결정론 검증(event_intel_test). 커밋 금지.

실 파이프라인(cross_source_dedup → ingest_records_to_events)에 타입별 realistic eq_record 를
흘려, 타입별 라우팅(CREATE/HOLD/singleton)과 source_type 보존을 결정론으로 관측한다.
각 시나리오 전 TRUNCATE 격리.
"""
import asyncio
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.services.event_ingest_pipeline import ingest_records_to_events
from ingestion.orchestration.cross_source_dedup import cluster_records

URL = "postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel_test"
TABLES = "events, event_updates, cluster_event_map, event_links, event_cards"
ACC = "0001193125-26-000123"


def rec(**kw):
    base = {
        "record_type": "article_candidate", "source_id": "x",
        "title_or_label": None, "source_url_or_evidence": None, "canonical_url": None,
        "published_at_or_observed_at": None, "body_state_or_signal": "present",
    }
    base.update(kw)
    return base


SCENARIOS = [
    ("S1 official+news 강신호(official_id)", [
        rec(record_type="official_record", source_id="sec_edgar",
            title_or_label="Acme Corp 8-K Material Definitive Agreement",
            source_url_or_evidence=f"https://www.sec.gov/Archives/edgar/data/320193/{ACC}-index.htm",
            published_at_or_observed_at="2026-06-22T13:00:00Z"),
        rec(record_type="article_candidate", source_id="reuters",
            title_or_label="Acme strikes material deal, SEC filing shows",
            source_url_or_evidence=f"https://www.reuters.com/business/acme-deal-{ACC}",
            canonical_url=f"https://www.reuters.com/business/acme-deal-{ACC}",
            published_at_or_observed_at="2026-06-22T14:00:00Z"),
    ]),
    ("S2 structured 단일 스냅샷", [
        rec(record_type="structured_signal", source_id="coinbase_market",
            title_or_label="BTC-USD spot",
            source_url_or_evidence="https://api.coinbase.com/v2/prices/BTC-USD/spot",
            body_state_or_signal="price:67000", published_at_or_observed_at="2026-06-22T13:00:00Z"),
    ]),
    ("S3 structured 2종(겹침 없음)", [
        rec(record_type="structured_signal", source_id="coinbase_market",
            title_or_label="BTC-USD spot", source_url_or_evidence="https://api.coinbase.com/v2/prices/BTC-USD/spot",
            body_state_or_signal="price:67000", published_at_or_observed_at="2026-06-22T13:00:00Z"),
        rec(record_type="structured_signal", source_id="binance_market",
            title_or_label="ETHUSDT ticker", source_url_or_evidence="https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
            body_state_or_signal="price:3500", published_at_or_observed_at="2026-06-22T13:00:00Z"),
    ]),
    ("S4 community(HN)+news 약신호(동일 제목)", [
        rec(record_type="article_candidate", source_id="reuters",
            title_or_label="Major outage hits cloud provider across regions",
            source_url_or_evidence="https://www.reuters.com/tech/cloud-outage",
            canonical_url="https://www.reuters.com/tech/cloud-outage",
            published_at_or_observed_at="2026-06-22T10:00:00Z"),
        rec(record_type="community_signal", source_id="hacker_news",
            title_or_label="Major outage hits cloud provider across regions",
            source_url_or_evidence="https://news.ycombinator.com/item?itemid=99",
            published_at_or_observed_at="2026-06-22T11:00:00Z"),
    ]),
    ("S5 pure community 강신호(동일 canonical_url)", [
        rec(record_type="community_signal", source_id="hacker_news",
            title_or_label="Show HN: my project",
            source_url_or_evidence="https://example.com/proj", canonical_url="https://example.com/proj",
            published_at_or_observed_at="2026-06-22T10:00:00Z"),
        rec(record_type="community_signal", source_id="reddit",
            title_or_label="my project on example.com",
            source_url_or_evidence="https://example.com/proj", canonical_url="https://example.com/proj",
            published_at_or_observed_at="2026-06-22T11:00:00Z"),
    ]),
    # adversarial P2-b: structured 2건이 동일 signal-key(signal|date|title)면 강신호 클러스터→발행?
    ("S6 structured 2종 동일 signal-key(겹침)", [
        rec(record_type="structured_signal", source_id="coinbase_market",
            title_or_label="BTC-USD spot", source_url_or_evidence="https://api.coinbase.com/btc",
            body_state_or_signal="price_snapshot", published_at_or_observed_at="2026-06-22T13:00:00Z"),
        rec(record_type="structured_signal", source_id="binance_market",
            title_or_label="BTC-USD spot", source_url_or_evidence="https://api.binance.com/btc",
            body_state_or_signal="price_snapshot", published_at_or_observed_at="2026-06-22T13:00:00Z"),
    ]),
    # adversarial P2-a: pure-community 약신호(유사 제목, URL 다름)도 CREATE 저신뢰 발행?
    ("S7 pure-community 약신호(유사 제목, URL 다름)", [
        rec(record_type="community_signal", source_id="hacker_news",
            title_or_label="Massive data breach exposes millions of user records",
            source_url_or_evidence="https://news.ycombinator.com/item?itemid=1",
            published_at_or_observed_at="2026-06-22T10:00:00Z"),
        rec(record_type="community_signal", source_id="reddit",
            title_or_label="Massive data breach exposes millions of user records",
            source_url_or_evidence="https://www.reddit.com/r/news/comments/2/breach",
            published_at_or_observed_at="2026-06-22T11:00:00Z"),
    ]),
]


async def run_scenario(eng, name, records):
    async with eng.begin() as c:
        await c.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    clusters = cluster_records(records)
    cl = [{"conf": c.confidence, "clique_ok": c.clique_ok,
           "n": len(c.duplicate_group), "weak_only": len(c.weak_only_members)} for c in clusters]
    maker = async_sessionmaker(eng, expire_on_commit=False)
    async with maker() as s:
        summary = await ingest_records_to_events(s, records, enabled=True)
        evs = (await s.execute(text(
            "SELECT e.canonical_title, u.delta_summary, u.evidence FROM events e "
            "JOIN event_updates u ON u.event_id=e.id "
            "WHERE e.id IN (SELECT event_id FROM cluster_event_map) ORDER BY e.canonical_title"))).all()
        held = (await s.execute(text("SELECT count(*) FROM event_links WHERE status='possible'"))).scalar_one()
    print(f"\n=== {name} ===")
    print(f"  clusters: {cl}")
    print(f"  summary: created={summary.created} appended={summary.appended} held={summary.held} "
          f"withheld={summary.withheld_source_type} held_links={summary.held_member_links} "
          f"singletons_dropped={summary.singletons_dropped}")
    for title, ds, evidence in evs:
        stypes = [e.get("source_type") for e in (evidence or [])]
        print(f"  EVENT title={title!r}")
        print(f"    delta_summary={ds!r}")
        print(f"    evidence source_types={stypes}")
    print(f"  event_links(possible held)={held}")


async def main():
    eng = create_async_engine(URL, poolclass=NullPool)
    for name, records in SCENARIOS:
        await run_scenario(eng, name, records)
    await eng.dispose()


asyncio.run(main())

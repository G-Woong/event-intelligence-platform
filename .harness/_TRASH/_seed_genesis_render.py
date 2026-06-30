"""throwaway — render 관측용 genesis Event 시드(event_intel_test). 커밋 금지(.harness gitignored).

실 파이프라인(ingest_records_to_events)으로 강신호 cross-source 클러스터를 만들어
CREATE → genesis update(자연어 delta_summary)를 event_intel_test 에 영속하고 event_id 를 출력한다.
backend 를 이 test DB 로 띄워 /events/timeline/{id} 화면에서 genesis 자연어가 렌더되는지 관측하기 위함.
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.services.event_ingest_pipeline import ingest_records_to_events

URL = "postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel_test"
_TABLES = "events, event_updates, cluster_event_map, event_links, event_cards"

# 강신호 클러스터: 같은 canonical_url 을 2개 출처가 보도 → duplicate clique → CREATE(genesis).
RECS = [
    {"record_type": "article_candidate", "source_id": "yna",
     "title_or_label": "역대급 급락에 코스피 서킷브레이커 발동",
     "canonical_url": "https://www.example.com/markets/kospi-cb",
     "published_at_or_observed_at": "2026-06-23T01:00:00Z", "body_state_or_signal": "present"},
    {"record_type": "article_candidate", "source_id": "mk",
     "title_or_label": "역대급 급락에 코스피 서킷브레이커 발동",
     "canonical_url": "https://www.example.com/markets/kospi-cb",
     "published_at_or_observed_at": "2026-06-23T01:00:00Z", "body_state_or_signal": "present"},
]


async def main() -> None:
    eng = create_async_engine(URL, poolclass=NullPool)
    async with eng.begin() as c:
        await c.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
    maker = async_sessionmaker(eng, expire_on_commit=False)
    async with maker() as s:
        summary = await ingest_records_to_events(s, RECS, enabled=True)
        print("created=", summary.created, "appended=", summary.appended)
        rows = (await s.execute(text(
            "SELECT e.id::text, u.delta_summary FROM events e "
            "JOIN event_updates u ON u.event_id = e.id"))).all()
        for eid, ds in rows:
            print("EVENT_ID", eid)
            print("DELTA_SUMMARY", ds)
    await eng.dispose()


asyncio.run(main())

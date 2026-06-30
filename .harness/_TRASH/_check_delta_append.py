"""delta_summary 자연어가 실 DB(event_intel_test)에 APPEND 로 영속되는지 결정론 확인(강신호).
THROWAWAY · gitignored · 미커밋. 라이브 fetch 0(synthetic 강신호 클러스터로 실 파이프라인 구동)."""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.services.event_ingest_pipeline import ingest_records_to_events

_DB = "postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel_test"


def _recs(tag: str):
    # 강신호(duplicate): 같은 canonical_url 2 record → strong_key_match 클러스터.
    url = f"https://wire.example/{tag}"
    t = f"강신호 검증 합성 사건 {tag}"
    return [
        {"record_type": "article_candidate", "source_id": "ap", "title_or_label": t,
         "canonical_url": url, "source_url_or_evidence": url,
         "published_at_or_observed_at": "2026-06-23T10:00:00Z", "body_state_or_signal": "present"},
        {"record_type": "article_candidate", "source_id": "bbc", "title_or_label": t,
         "canonical_url": url, "source_url_or_evidence": url,
         "published_at_or_observed_at": "2026-06-23T10:00:00Z", "body_state_or_signal": "present"},
    ]


async def main():
    tag = uuid.uuid4().hex[:8]
    cluster_id = f"xcluster:canon:"  # 실제 키는 해시 — 아래에서 event_id 로 추적
    engine = create_async_engine(_DB)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            r1 = await ingest_records_to_events(s, _recs(tag), enabled=True)
            eid = r1.event_ids[0] if r1.event_ids else None
            print("1st ingest (CREATE):", r1.created, "appended", r1.appended, "event", eid)
        async with factory() as s:
            r2 = await ingest_records_to_events(s, _recs(tag), enabled=True)
            print("2nd ingest (APPEND 기대):", "created", r2.created, "appended", r2.appended, "held", r2.held)
        async with factory() as s:
            rows = (await s.execute(text(
                "SELECT delta_summary FROM event_updates WHERE event_id=:e ORDER BY created_at"
            ), {"e": eid})).scalars().all()
            print(f"event {eid} updates({len(rows)}):")
            for d in rows:
                print("   ", repr(d), "| 디버그라벨?", ":" in d[:12])
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

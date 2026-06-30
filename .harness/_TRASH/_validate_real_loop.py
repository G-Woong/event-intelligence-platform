"""R-RealSourceLoopUnproven 검증 하니스 (THROWAWAY · gitignored · 미커밋).

실 keyless 소스를 경로 B(수집→cross_source_dedup→event_ingest_pipeline→event_resolution
→events/event_updates)로 실제로 흘린다. event_resolution_sink 를 event_intel_test(disposable
test DB)에 결선하고 EVENT_RESOLUTION 강제 on. write_outputs=False(production state/monitoring/
mirror 미오염 — Event 테이블만 영속).

소스 선정 인자(argv[1])로 변경 가능. 기본=on-brand 겹침 가능 세트.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ingestion.core.env_loader import load_env
from ingestion.orchestration.production_scheduler import MODE_VALIDATION
from ingestion.orchestration.source_profile import load_source_profiles
from ingestion.tools.run_production_orchestration import (
    ProductionRunConfig,
    _real_probe_fn,
    run_production_orchestration,
)

from backend.app.services.event_ingest_pipeline import make_orchestration_event_sink

_DB = "postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel_test"
_DEFAULT_SOURCES = ["gdelt", "bbc", "aljazeera", "hacker_news"]


def main() -> int:
    chosen = sys.argv[1].split(",") if len(sys.argv) > 1 else _DEFAULT_SOURCES
    load_env(None)

    all_profiles = load_source_profiles("ingestion/configs/source_profiles.yaml")
    profiles = [p for p in all_profiles if p.source_id in chosen]
    print(f"=== chosen sources: {[p.source_id for p in profiles]} ===")

    engine = create_async_engine(_DB, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    _inner_sink = make_orchestration_event_sink(factory, enabled=True)

    def sink(records, clusters=None):
        # 실 record 가시화 — 왜 클러스터가 형성/미형성되는지 진단.
        print(f"\n=== WRITTEN_RECORDS dump ({len(records)}) ===")
        for r in records[:30]:
            title = (r.get("title_or_label") or "")[:48]
            url = (r.get("canonical_url") or r.get("source_url_or_evidence") or "")[:60]
            print(f"  [{r.get('source_id')}|{r.get('record_type')}] sig={r.get('body_state_or_signal')!r} key={r.get('_dedup_key','')[:40]!r}")
            print(f"      title={title!r} url={url!r}")
        return _inner_sink(records, clusters)

    config = ProductionRunConfig(mode=MODE_VALIDATION, all_due=True, force=True)
    now = datetime.now(timezone.utc)

    result = run_production_orchestration(
        config,
        profiles=profiles,
        prior_states={},          # 전부 fresh → due
        probe_fn=_real_probe_fn(),  # 실 네트워크 fetch
        event_resolution_sink=sink,
        now=now,
        write_outputs=False,      # production state/monitoring/mirror 미오염(Event 테이블만)
    )

    s = result["summary"]
    plan = result["plan"]
    print("\n=== PLAN ===")
    print("due_sources:", list(plan.due_sources))
    print("\n=== COLLECTION ===")
    print("attempted:", s.get("attempted_sources"))
    print("records_collected:", s.get("records_collected"))
    print("eventqueue_written:", s.get("records_enqueued"))
    print("record_type_counts:", s.get("record_type_counts"))
    print("rate_limited:", s.get("rate_limited"))
    print("error_by_source:", s.get("error_by_source"))
    print("error_by_root_cause:", s.get("error_by_root_cause"))
    print("\n=== CROSS_SOURCE_CLUSTERS ===")
    print(s.get("cross_source_clusters"))
    print("\n=== EVENT_RESOLUTION (경로 B 영속) ===")
    er = result.get("event_resolution")
    print(er)

    asyncio.run(engine.dispose())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

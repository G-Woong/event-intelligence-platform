"""ADR#54 — real-source identity smoke (source→record→Event→identity→stage③ 단계별 진단·report).

RealSourceLoop(R-RealSourceLoopUnproven)가 운영 데이터에서 어디까지 닿는지 **단계별 실패 분류**로 진단한다.
**기본은 fake-source injection**(network 0·DB 0·결정론) — 정적 fixture 를 fetch→record→cluster→candidate 까지
돌려 source_role_distribution + failures_by_stage 를 낸다. 실 network fetch 는 probe 주입(opt-in·CI 필수 아님).

**정직 경계:** offline 모드는 **DB 미접근** — created/held/withheld/adjudications/packet 은 None(미도달).
DB 단계는 `run_db_identity_smoke`(safe-target gated·test/dev DB 만)가 기존 `ingest_records_to_events`(live-PG 검증됨)를
호출해 채운다. 이 도구는 **실 fetch 0 이면 RealSourceLoop 를 닫았다고 주장하지 않는다**(real_fetch 플래그로 표면화).
**자동 병합 0**(no_auto_merge=True 불변·community/market/catalog 는 anchor 아님 — non_publishable_role 로 분리).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ingestion.orchestration.cross_source_dedup import cluster_records

from backend.app.core.config import settings
from backend.app.services.event_ingest_pipeline import (
    _RECORD_TYPE_TO_SOURCE_TYPE,
    EventIngestSummary,
    build_record_index,
    candidate_from_cluster,
    ingest_records_to_events,
)
from backend.app.tools.db_target import (
    UnsafeWriteTargetError,
    assert_safe_write_target,
    target_db_label,
)
from backend.app.tools.export_identity_eval_pairs import collect_adjudication_eval_pairs

DEFAULT_MAX_RECORDS = 50   # bounded smoke(폭주 차단·결정론).


def _rec(**kw: Any) -> dict:
    base = {
        "record_type": "article_candidate", "source_id": "fake",
        "title_or_label": None, "source_url_or_evidence": None, "canonical_url": None,
        "published_at_or_observed_at": None, "body_state_or_signal": "present",
    }
    base.update(kw)
    return base


def build_fake_source_records() -> list[dict]:
    """결정론 fixture(network 0) — news/official publishable 클러스터 + community-only guard + singleton + body-missing.

    publishable 2 cluster(news·official→identity anchor·semantic fingerprint), community-only 1 cluster(anchor 금지·
    non_publishable_role), singleton 1(클러스터 미형성), body-missing 1(본문 결손 분류). 실 source 가 아니라 **계약 검증용**.
    """
    return [
        _rec(record_type="article_candidate", source_id="bbc", canonical_url="https://bbc.test/x1",
             title_or_label="Hormuz strait tanker seized by naval forces", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters", canonical_url="https://reuters.test/x2",
             title_or_label="Hormuz strait tanker seized by naval forces", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="official_record", source_id="sec_edgar", canonical_url="https://sec.test/8k",
             title_or_label="Acme Corp 8-K filing on merger", published_at_or_observed_at="2025-06-03"),
        _rec(record_type="article_candidate", source_id="ap", canonical_url="https://ap.test/acme",
             title_or_label="Acme Corp 8-K filing on merger", published_at_or_observed_at="2025-06-03"),
        _rec(record_type="community_signal", source_id="hacker_news", canonical_url="https://hn.test/1",
             title_or_label="Discussion about cloud outage today reported", published_at_or_observed_at="2025-06-04"),
        _rec(record_type="community_signal", source_id="dcinside", canonical_url="https://dc.test/2",
             title_or_label="Discussion about cloud outage today reported", published_at_or_observed_at="2025-06-04"),
        _rec(record_type="article_candidate", source_id="the_verge", canonical_url="https://verge.test/solo",
             title_or_label="Completely unique singleton story headline", published_at_or_observed_at="2025-06-05"),
        _rec(record_type="article_candidate", source_id="etnews", canonical_url="https://et.test/miss",
             title_or_label="Another distinct missing body article headline",
             published_at_or_observed_at="2025-06-06", body_state_or_signal="missing"),
    ]


def run_offline_identity_smoke(
    records: Optional[list[dict]] = None,
    *,
    probe: Optional[Callable[[], list[dict]]] = None,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> dict:
    """fetch(주입)→record→cluster→candidate 까지 **write-free·결정론** 진단(DB 미접근).

    probe 주입 시 실 fetch(opt-in·network); 미주입이면 records(또는 fake fixture)를 그대로 fetch 로 본다.
    DB 단계(created/held/withheld/adjudications/packet)는 None — `run_db_identity_smoke` 가 채운다(정직).
    """
    real_fetch = probe is not None
    fetched = list(probe()) if probe is not None else list(
        records if records is not None else build_fake_source_records())
    bounded = fetched[:max_records]
    truncated = len(fetched) > len(bounded)

    role_dist: dict[str, int] = {}
    failures = {
        "body_missing": 0, "no_cluster_singleton": 0,
        "non_publishable_role": 0, "no_semantic_fingerprint": 0,
    }
    for r in bounded:
        st = _RECORD_TYPE_TO_SOURCE_TYPE.get(r.get("record_type"), "unknown")
        role_dist[st] = role_dist.get(st, 0) + 1
        if (r.get("body_state_or_signal") or "missing") == "missing":
            failures["body_missing"] += 1

    clusters = cluster_records(bounded)
    index = build_record_index(bounded)
    clustered_keys: set[str] = set()
    for c in clusters:
        clustered_keys.update(c.duplicate_group)
    singletons = len(set(index) - clustered_keys)
    failures["no_cluster_singleton"] = singletons

    semantic_fp = 0
    publishable_anchor = 0
    for c in clusters:
        cand = candidate_from_cluster(c, index)
        fp = len(cand.semantic_fingerprints)
        semantic_fp += fp
        if cand.identity_keys:
            publishable_anchor += 1
        publishable_core = any(st in ("official", "article") for st in cand.core_source_types)
        if not publishable_core:
            failures["non_publishable_role"] += 1
        elif fp == 0:
            failures["no_semantic_fingerprint"] += 1

    return {
        "mode": "offline_probe" if real_fetch else "offline_fake",
        "real_fetch": real_fetch,
        "source_count": len({r.get("source_id") for r in bounded if r.get("source_id")}),
        "fetched_records": len(bounded),
        "records_truncated": truncated,
        "clusters": len(clusters),
        "singletons_dropped": singletons,
        "semantic_fingerprint_candidates": semantic_fp,   # 잠재 cross-batch identity link 신호(실 link 아님)
        "publishable_anchor_clusters": publishable_anchor,
        "source_role_distribution": role_dist,
        "failures_by_stage": failures,
        # DB-dependent 단계 — offline 미도달(정직). live = run_db_identity_smoke(safe-target gated·test/dev DB).
        "created_events": None,
        "held_events": None,
        "withheld_events": None,
        "identity_links": None,
        "adjudications": None,
        "packet_eligible": None,
        "packet_selected": None,
        "no_auto_merge": True,
    }


def summarize_db_ingest(
    summary: EventIngestSummary, *, packet_eligible: Optional[int] = None,
    packet_selected: Optional[int] = None,
) -> dict:
    """EventIngestSummary → smoke report 의 DB-단계 필드(순수 매핑·fabrication 0). no_auto_merge 불변."""
    return {
        "created_events": summary.created,
        "appended_events": summary.appended,
        "held_events": summary.held,
        "withheld_events": summary.withheld_source_type,
        # identity 단계 신호 = ingest 가 생성한 held-member event_links(possible) 수. semantic cross-batch
        # fingerprint link(ADR#41)은 별도 생성되나 summary 미집계 → held_member_links 만 정직 보고(over-claim 0).
        "identity_links": summary.held_member_links,      # offline None 을 live 에서 실 값으로 채움(honesty)
        "held_member_links": summary.held_member_links,   # event_links(possible) — held 멤버
        "adjudications": summary.adjudications,            # stage③ shadow adjudication upsert 수
        "singletons_dropped": summary.singletons_dropped,
        "packet_eligible": packet_eligible,
        "packet_selected": packet_selected,
        "no_auto_merge": True,
    }


async def run_db_identity_smoke(
    session: AsyncSession,
    records: Optional[list[dict]] = None,
    *,
    persist: bool = False,
    allow_non_dev: bool = False,
    collect_packet: bool = False,
    app_env: Optional[str] = None,
    database_url: Optional[str] = None,
) -> dict:
    """live-DB 확장 — safe-target gated(test/dev 만) 후 기존 ingest_records_to_events 로 DB 단계 도달.

    safe-target 미통과면 UnsafeWriteTargetError(호출자 차단). persist=True 면 stage③ shadow adjudication 도 실행
    (자동 병합 아님 — adjudication write only). **운영 DB 사용 금지**(가드가 dev/test 만 허용). 실제 DB 행위는
    ingest_records_to_events 의 live-PG 검증에 귀속(이 어댑터는 thin glue)."""
    app_env = settings.APP_ENV if app_env is None else app_env
    database_url = settings.DATABASE_URL if database_url is None else database_url
    assert_safe_write_target(app_env=app_env, database_url=database_url, allow_non_dev=allow_non_dev)

    recs = list(records if records is not None else build_fake_source_records())
    offline = run_offline_identity_smoke(recs)
    summary = await ingest_records_to_events(
        session, recs, enabled=True, adjudicate_semantic=persist)
    packet_eligible: Optional[int] = None
    if collect_packet and persist:
        packet_eligible = len(await collect_adjudication_eval_pairs(session))
    db = summarize_db_ingest(summary, packet_eligible=packet_eligible)
    return {**offline, **db, "mode": "live_db"}


# ── CLI(기본 offline fake·network 0·DB 0; --live-db opt-in·safe-target gated) ──
async def _run_live_db(*, persist: bool, allow_non_dev: bool, collect_packet: bool) -> dict:
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as session:
            return await run_db_identity_smoke(
                session, persist=persist, allow_non_dev=allow_non_dev, collect_packet=collect_packet)
    finally:
        await engine.dispose()


def main(argv: Optional[list[str]] = None) -> int:
    try:  # Windows cp949 콘솔이 한국어/em-dash 에 죽지 않도록 utf-8(closeout_sig 선례).
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="real-source identity smoke (기본 offline fake·network 0·DB 0; --live-db opt-in·safe-target gated).",
    )
    parser.add_argument("--live-db", action="store_true",
                        help="test/dev DB 에 ingest 까지 도달(safe-target gated). 미지정=offline(DB 0).")
    parser.add_argument("--persist", action="store_true",
                        help="--live-db 와 함께 stage③ shadow adjudication 실행(자동 병합 아님).")
    parser.add_argument("--collect-packet", action="store_true",
                        help="--live-db --persist 후 packet eligible 후보 수 집계(read-only).")
    parser.add_argument("--allow-non-dev-db", action="store_true",
                        help="--live-db 의 safe-target 가드 override(기본 거부 — fail-closed).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if not ns.live_db:
        report = run_offline_identity_smoke()
    else:
        print(f"- live-db smoke target: {target_db_label(settings.DATABASE_URL)} (APP_ENV={settings.APP_ENV})")
        try:
            report = asyncio.run(_run_live_db(
                persist=ns.persist, allow_non_dev=ns.allow_non_dev_db, collect_packet=ns.collect_packet))
        except UnsafeWriteTargetError as e:
            print(f"- BLOCKED unsafe write target: {e}")
            return 1
        except Exception as e:   # runtime error(DB down 등) → exit 2(자격증명 미노출).
            print(f"- ERROR live-db smoke runtime failure: {type(e).__name__}: {e}")
            return 2

    print(
        f"- smoke[{report['mode']}]: real_fetch={report['real_fetch']} sources={report['source_count']} "
        f"records={report['fetched_records']} clusters={report['clusters']} "
        f"singletons={report['singletons_dropped']} fingerprints={report['semantic_fingerprint_candidates']} "
        f"publishable_anchor={report['publishable_anchor_clusters']}")
    print(f"- role_distribution: {report['source_role_distribution']}")
    print(f"- failures_by_stage: {report['failures_by_stage']}")
    print(
        f"- db_stages: created={report['created_events']} held={report['held_events']} "
        f"withheld={report['withheld_events']} adjudications={report['adjudications']} "
        f"packet_eligible={report['packet_eligible']} no_auto_merge={report['no_auto_merge']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

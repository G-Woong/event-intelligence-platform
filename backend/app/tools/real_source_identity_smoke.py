"""ADR#54/#55 — real-source identity smoke (source→record→Event→identity→stage③ 단계별 진단·report).

RealSourceLoop(R-RealSourceLoopUnproven)가 운영 데이터에서 어디까지 닿는지 **단계별 실패 분류**로 진단한다.
**기본은 fake-source injection**(network 0·DB 0·결정론) — 정적 fixture 를 fetch→record→cluster→candidate 까지
돌려 source_role_distribution + failures_by_stage 를 낸다. **ADR#55: live_network 실 fetch**(key-free official
JSON API·bounded·opt-in·CI 필수 아님)와 **live_db**(disposable test/dev DB) 를 추가해 실데이터로 한 단계 더 닿는다.

**정직 경계:** offline 모드는 **DB 미접근** — created/held/withheld/adjudications/packet 은 None(미도달).
DB 단계는 `run_db_identity_smoke`(safe-target gated·test/dev DB 만)가 기존 `ingest_records_to_events`(live-PG 검증됨)를
호출해 채운다. 이 도구는 **실 fetch 0 이면 RealSourceLoop 를 닫았다고 주장하지 않는다**(real_fetch 플래그로 표면화).
**자동 병합 0**(no_auto_merge=True 불변·community/market/catalog 는 anchor 아님 — non_publishable_role 로 분리).
**본문 미저장**(title 헤드라인[:512]·canonical·published_at 만 — 전문/PII 저장 금지·옵션 B 계약).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ingestion.orchestration.cross_source_dedup import cluster_records
from ingestion.sources._registry import get_source_instance

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
from backend.app.tools.real_source_smoke_report import assemble_activation_report

DEFAULT_MAX_RECORDS = 50   # bounded smoke(폭주 차단·결정론).
DEFAULT_MAX_PER_SOURCE = 5  # live_network: source 당 상한(rate-limit·폭주 차단).

# live_network 화이트리스트: key-free·robots-friendly·canonical+published_at·이번 턴 실측(status 200) 된 official JSON API 만.
# federal_register 만 등재 — canonical=document_number URL 파생·published_at·실 fetch 검증됨(전부 official_record).
# community/market/catalog/search/news-HTML 제외(anchor 아님 or parser 취약 or key 필요). **sec_edgar 는 보류**:
# full-text-search 응답에서 안정 doc canonical 을 파생 못 하면 anchor 자격이 못 되고(guard_only) endpoint 미실측 →
# canonical 파생 + 실측 후 등재(allowlist 에 anchor 불가 source 를 넣어 "official 인데 guard_only" 혼란 차단).
_SMOKE_SOURCE_RECORD_TYPE: dict[str, str] = {
    "federal_register": "official_record",
}


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


def _canonical_for(source_id: str, item: dict) -> Optional[str]:
    """source 별 안정 canonical URL 파생(network 0·결정론). 미파생이면 None(canonical_missing 으로 분류)."""
    if source_id == "federal_register":
        dn = item.get("document_number")
        return f"https://www.federalregister.gov/d/{dn}" if dn else None
    return None   # allowlist 밖 source: 안정 doc URL 미파생 → None(정직).


def _parse_payload_records(source_id: str, html: str, max_per_source: int) -> Optional[list[dict]]:
    """raw JSON payload → 다중 record dict(canonical·published_at·헤드라인만). parser 실패 시 None.

    adapter.extract() 는 [0] 만 반환하므로 smoke 는 payload 를 직접 파싱해 다중 record 를 만든다.
    **본문/raw_payload 미저장**(title[:512] 헤드라인·canonical·published_at 만 — 옵션 B 계약·fetch 는 abstract/
    payload 전문을 수신하나 record/DB 에는 미반영). 현재 federal_register 만 지원(allowlist 정합)."""
    try:
        data = json.loads(html)
    except Exception:
        return None   # parser_error
    items: list[dict] = []
    if source_id == "federal_register":
        items = list(data.get("results", []) or [])
    recs: list[dict] = []
    for it in items[:max_per_source]:
        if not isinstance(it, dict):
            continue
        title = (it.get("title") or "").strip()
        pub = it.get("publication_date")
        if not title:
            continue
        canon = _canonical_for(source_id, it)
        recs.append(_rec(
            record_type=_SMOKE_SOURCE_RECORD_TYPE.get(source_id, "official_record"),
            source_id=source_id, title_or_label=title[:512],
            canonical_url=canon, source_url_or_evidence=canon,
            published_at_or_observed_at=(pub or None),
            body_state_or_signal="present",
        ))
    return recs


def fetch_real_source_records(
    source_ids: list[str], *, max_per_source: int = DEFAULT_MAX_PER_SOURCE,
    transport: Optional[Callable[[str], Optional[str]]] = None,
) -> tuple[list[dict], dict[str, str]]:
    """key-free official source bounded 실 fetch(opt-in·network). transport 주입 시 결정론(테스트·network 0).

    반환: (records, failures_by_source). 실패는 source 별 단계로 분류
    (source_disabled/network_error/parser_error/no_records). **본문 미저장**."""
    records: list[dict] = []
    failures_by_source: dict[str, str] = {}
    for sid in source_ids:
        if sid not in _SMOKE_SOURCE_RECORD_TYPE:
            failures_by_source[sid] = "source_disabled"   # allowlist 밖(key-free official 아님)
            continue
        src = get_source_instance(sid)
        if src is None:
            failures_by_source[sid] = "source_disabled"
            continue
        url = src.get_entry_url()
        try:
            html = transport(url) if transport is not None else src.fetch_entry_html(url)
        except Exception:
            html = None
        if not html:
            failures_by_source[sid] = "network_error"
            continue
        recs = _parse_payload_records(sid, html, max_per_source)
        if recs is None:
            failures_by_source[sid] = "parser_error"
            continue
        if not recs:
            failures_by_source[sid] = "no_records"
            continue
        records.extend(recs)
    return records, failures_by_source


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
        "source_ids": sorted({r.get("source_id") for r in bounded if r.get("source_id")}),
        "fetched_records": len(bounded),
        "records_truncated": truncated,
        # 본문/canonical/published_at 충족도(source quality matrix·옵션 E 입력).
        "records_with_body": sum(
            1 for r in bounded if (r.get("body_state_or_signal") or "missing") != "missing"),
        "records_with_canonical_url": sum(1 for r in bounded if r.get("canonical_url")),
        "records_with_published_at": sum(1 for r in bounded if r.get("published_at_or_observed_at")),
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


async def _count_events(session: AsyncSession) -> int:
    """events 총수(read-only) — live_db smoke before/after delta 로 증분/자동병합 0 입증용."""
    return int((await session.execute(text("SELECT count(*) FROM events"))).scalar_one())


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
    event_count_before = await _count_events(session)   # §6: before/after 로 자동병합 0·증분만 입증.
    summary = await ingest_records_to_events(
        session, recs, enabled=True, adjudicate_semantic=persist)
    event_count_after = await _count_events(session)
    packet_eligible: Optional[int] = None
    if collect_packet and persist:
        packet_eligible = len(await collect_adjudication_eval_pairs(session))
    db = summarize_db_ingest(summary, packet_eligible=packet_eligible)
    return {**offline, **db, "mode": "live_db",
            "event_count_before": event_count_before, "event_count_after": event_count_after}


# ── CLI(기본 offline fake·network 0·DB 0; --live-network/--live-db opt-in·safe-target gated) ──
async def _run_live_db(records: Optional[list[dict]], *,
                       persist: bool, allow_non_dev: bool, collect_packet: bool) -> dict:
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as session:
            return await run_db_identity_smoke(
                session, records=records, persist=persist,
                allow_non_dev=allow_non_dev, collect_packet=collect_packet)
    finally:
        await engine.dispose()


_DEFAULT_LIVE_SOURCES = "federal_register"   # key-free official JSON API(robots-friendly·canonical+published_at).


def main(argv: Optional[list[str]] = None) -> int:
    try:  # Windows cp949 콘솔이 한국어/em-dash 에 죽지 않도록 utf-8(closeout_sig 선례).
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="real-source identity smoke (기본 offline fake·network 0·DB 0; --live-network/--live-db opt-in).",
    )
    parser.add_argument("--live-network", action="store_true",
                        help="key-free official source 실 fetch(opt-in·network·CI 아님). 미지정=fake fixture.")
    parser.add_argument("--source", default=_DEFAULT_LIVE_SOURCES,
                        help=f"--live-network source(콤마구분·allowlist 만). 기본={_DEFAULT_LIVE_SOURCES}.")
    parser.add_argument("--live-db", action="store_true",
                        help="test/dev DB 에 ingest 까지 도달(safe-target gated). 미지정=offline(DB 0).")
    parser.add_argument("--persist", action="store_true",
                        help="--live-db 와 함께 stage③ shadow adjudication 실행(자동 병합 아님).")
    parser.add_argument("--collect-packet", action="store_true",
                        help="--live-db --persist 후 packet eligible 후보 수 집계(read-only).")
    parser.add_argument("--allow-non-dev-db", action="store_true",
                        help="--live-db 의 safe-target 가드 override(기본 거부 — fail-closed).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if ns.collect_packet and not (ns.live_db and ns.persist):
        print("- WARNING --collect-packet 는 --live-db --persist 필요 (무시됨·packet_eligible=None)")

    records: Optional[list[dict]] = None
    failures_by_source: dict[str, str] = {}
    if ns.live_network:
        sources = [s.strip() for s in ns.source.split(",") if s.strip()]
        print(f"- live-network fetch (opt-in·bounded): sources={sources}")
        records, failures_by_source = fetch_real_source_records(sources)
        print(f"- fetched {len(records)} record(s); failures_by_source={failures_by_source}")

    run_mode = "live_db" if ns.live_db else ("live_network" if ns.live_network else "fake")
    if not ns.live_db:
        smoke = run_offline_identity_smoke(
            records, probe=((lambda: records) if (ns.live_network and records is not None) else None))
    else:
        print(f"- live-db smoke target: {target_db_label(settings.DATABASE_URL)} (APP_ENV={settings.APP_ENV})")
        try:
            smoke = asyncio.run(_run_live_db(
                records, persist=ns.persist, allow_non_dev=ns.allow_non_dev_db,
                collect_packet=ns.collect_packet))
        except UnsafeWriteTargetError as e:
            print(f"- BLOCKED unsafe write target: {e}")
            return 1
        except Exception as e:   # runtime error(DB down 등) → exit 2(자격증명 미노출).
            print(f"- ERROR live-db smoke runtime failure: {type(e).__name__}: {e}")
            return 2

    report = assemble_activation_report(
        smoke, run_mode=run_mode, app_env=settings.APP_ENV, database_url=settings.DATABASE_URL,
        failures_by_source=failures_by_source, records=records)

    print(
        f"- smoke[{report['run_mode']}]: target={report['db_target_classification']}"
        f"(consistent={report['db_target_consistent']}) sources={report['source_count']} "
        f"records={report['fetched_records']} body={report['records_with_body']} "
        f"canonical={report['records_with_canonical_url']} published={report['records_with_published_at']} "
        f"clusters={report['clusters']} singletons={report['singletons_dropped']} "
        f"fingerprints={report['semantic_fingerprint_candidates']}")
    print(f"- role_distribution: {report['source_role_distribution']}")
    print(f"- failures_by_stage: {report['failures_by_stage']} failures_by_source: {report['failures_by_source']}")
    print(
        f"- db_stages: created={report['created_events']} held={report['held_events']} "
        f"withheld={report['withheld_events']} identity_links={report['identity_links']} "
        f"adjudications={report['adjudications']} packet_eligible={report['packet_eligible']} "
        f"exportable={report['reviewer_packet_exportable']} no_auto_merge={report['no_auto_merge']}")
    print(f"- event_count: before={report['event_count_before']} after={report['event_count_after']}")
    g = report["agent_readiness_gate"]
    print(f"- agent_readiness: {g['verdict']} ({g['pass_count']}/{g['total']} PASS·unmet={g['unmet_conditions']})")
    print(f"- source_quality_matrix: {len(report['source_quality_matrix'])} row(s)")
    for a in report["next_actions"]:
        print(f"  · next: {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

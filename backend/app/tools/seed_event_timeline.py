"""D-2c — 합성(synthetic) Event 타임라인 seed (오프라인·결정론·외부 호출 0).

목적: Docker/로컬 데모에서 **사용자가 웹(`/events/timeline`)으로 실제 Event 타임라인을 보도록**
읽을 수 있는 합성 데이터를 영속한다.

왜 합성 seed 인가: 수집 결선(`event_ingest_pipeline`)의 `delta_summary` 는 현재 디버그 라벨
(`"{confidence}:{reason}"`, 예 `"0.83:strong_clique"`)이라 실 수집 데이터로는 타임라인 본문
가독성이 낮다(R-EventTimelineRenderHardening ② = 상류 자연어화 책임, 별개 이월). 데모 품질을
위해 **사람이 읽을 수 있는 delta_summary/evidence 를 가진 합성 Event 를 직접 영속**한다.

안전 계약:
  - 외부 API/LLM/embedding 호출 0 — `event_timeline_service` 직접 사용(전 경로 결정론).
  - evidence URL 은 `example.com` 합성(실 소스 아님)·allowlist 키만(전문/PII 미저장).
  - 투자조언·실기업 허위·PII·본문 전문 없음(정보 전달용 중립 서술).
  - **멱등**: cluster_id 안정키로 이미 seed 된 Event 는 건너뜀(재실행 시 중복 0).
  - **DB target 가드**(R-EventSinkDbTarget): APP_ENV=staging/production 은 `--allow-non-dev-db`
    없이 거부(fail-closed). 대상 DB(host:port/dbname, 자격증명 제외) 를 stdout 출력.

영속 경로: create_event → **map_cluster**(cluster_event_map 매핑 — 매핑돼야 공개 목록
list_events 에 노출됨, 매핑 게이트) → append_update×N. 이벤트당 단일 원자 커밋.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core.config import settings
from backend.app.services import event_timeline_service as svc
from backend.app.services.event_timeline_service import ResolvedCandidate
from backend.app.tools.db_target import assert_safe_write_target


def _utc(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _SeedUpdate:
    observed_at: datetime
    delta_summary: str
    evidence: tuple[dict, ...] = ()
    added_domains: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class _SeedEvent:
    cluster_id: str
    canonical_title: str
    domains: tuple[str, ...]
    tags: tuple[str, ...]
    first_observed_at: datetime
    updates: tuple[_SeedUpdate, ...]
    primary_entity_ids: tuple[str, ...] = field(default_factory=tuple)


def _ev(url: str, source_type: str, role: str, observed_at: datetime) -> dict:
    # allowlist 키만(url/source_type/role/observed_at) — append_update 의 _sanitize_evidence 통과.
    # observed_at 은 ISO 문자열로(JSONB 직렬화 — raw datetime 은 JSON 불가).
    return {
        "url": url,
        "source_type": source_type,
        "role": role,
        "observed_at": observed_at.isoformat(),
    }


# ── 합성 데이터(중립 정보 서술 · example.com · 투자조언/실기업/PII 없음) ──────────────────
_SEED_EVENTS: tuple[_SeedEvent, ...] = (
    _SeedEvent(
        cluster_id="seed:ai-access-policy",
        canonical_title="AI 모델 접근 정책 변경",
        domains=("technology", "policy"),
        tags=("ai", "governance"),
        primary_entity_ids=("ent-seed-ai-lab",),
        first_observed_at=_utc(2026, 6, 18, 9),
        updates=(
            _SeedUpdate(
                observed_at=_utc(2026, 6, 18, 9),
                delta_summary="한 AI 연구 그룹이 모델 API 접근 등급을 3단계로 개편한다고 공지했다. 기존 무료 등급의 호출 한도가 조정된다.",
                evidence=(_ev("https://example.com/ai-access/announce", "official_blog", "primary", _utc(2026, 6, 18, 9)),),
                source_refs=("seed:ai-access-policy:u1",),
            ),
            _SeedUpdate(
                observed_at=_utc(2026, 6, 19, 14, 30),
                delta_summary="개발자 커뮤니티에서 한도 변경이 소규모 팀에 미치는 영향에 대한 논의가 확산됐고, 다수 사용자가 마이그레이션 가이드를 요청했다.",
                evidence=(_ev("https://example.com/forum/ai-access", "community", "context", _utc(2026, 6, 19, 14, 30)),),
            ),
            _SeedUpdate(
                observed_at=_utc(2026, 6, 21, 10, 15),
                delta_summary="정책 발효일이 7월 1일로 확정됐고, 기존 사용자에게 30일 유예가 적용된다는 후속 안내가 나왔다.",
                evidence=(_ev("https://example.com/ai-access/update", "official_blog", "primary", _utc(2026, 6, 21, 10, 15)),),
            ),
        ),
    ),
    _SeedEvent(
        cluster_id="seed:semiconductor-supply",
        canonical_title="반도체 공급망 리드타임 경고",
        domains=("supply-chain", "technology"),
        tags=("semiconductor", "logistics"),
        first_observed_at=_utc(2026, 6, 17, 8),
        updates=(
            _SeedUpdate(
                observed_at=_utc(2026, 6, 17, 8),
                delta_summary="한 물류 분석 기관이 특정 공정 노드의 리드타임이 평소보다 길어지고 있다는 관측을 발표했다.",
                evidence=(_ev("https://example.com/supply/report", "official_report", "primary", _utc(2026, 6, 17, 8)),),
            ),
            _SeedUpdate(
                observed_at=_utc(2026, 6, 18, 16),
                delta_summary="복수의 무역 매체가 동일한 리드타임 지연을 독립적으로 보도하며 원인으로 계절적 수요 집중을 지목했다.",
                evidence=(_ev("https://example.com/trade/leadtime", "trade_media", "corroboration", _utc(2026, 6, 18, 16)),),
            ),
            _SeedUpdate(
                observed_at=_utc(2026, 6, 20, 11),
                delta_summary="업계 단체가 단기 재고 점검 권고를 회원사에 배포했다고 밝혔다.",
                evidence=(_ev("https://example.com/industry/advisory", "industry_body", "context", _utc(2026, 6, 20, 11)),),
            ),
        ),
    ),
    _SeedEvent(
        cluster_id="seed:public-data-api-outage",
        canonical_title="공공 데이터 API 장애",
        domains=("infrastructure", "public-sector"),
        tags=("outage", "api"),
        first_observed_at=_utc(2026, 6, 22, 3, 20),
        updates=(
            _SeedUpdate(
                observed_at=_utc(2026, 6, 22, 3, 20),
                delta_summary="공공 데이터 포털의 조회 API 가 일시적으로 응답하지 않는다는 상태 페이지 공지가 게시됐다.",
                evidence=(_ev("https://example.com/status/incident", "status_page", "primary", _utc(2026, 6, 22, 3, 20)),),
            ),
            _SeedUpdate(
                observed_at=_utc(2026, 6, 22, 5, 45),
                delta_summary="운영팀이 원인을 인증 게이트웨이 구성 변경으로 식별하고 롤백을 진행 중이라고 업데이트했다.",
                evidence=(_ev("https://example.com/status/incident", "status_page", "primary", _utc(2026, 6, 22, 5, 45)),),
            ),
            _SeedUpdate(
                observed_at=_utc(2026, 6, 22, 7, 10),
                delta_summary="서비스가 정상 복구됐으며 영향 시간은 약 4시간으로 집계됐다고 공지됐다.",
                evidence=(_ev("https://example.com/status/resolved", "status_page", "resolution", _utc(2026, 6, 22, 7, 10)),),
            ),
            _SeedUpdate(
                observed_at=_utc(2026, 6, 22, 9),
                delta_summary="포털이 사후 점검 보고를 추후 공개하겠다고 안내했다.",
                evidence=(_ev("https://example.com/notice/postmortem", "official_notice", "context", _utc(2026, 6, 22, 9)),),
            ),
        ),
    ),
    _SeedEvent(
        cluster_id="seed:weather-advisory",
        canonical_title="강풍·호우 기상 특보",
        domains=("weather", "public-safety"),
        tags=("alert", "storm"),
        first_observed_at=_utc(2026, 6, 21, 18),
        updates=(
            _SeedUpdate(
                observed_at=_utc(2026, 6, 21, 18),
                delta_summary="기상 당국이 특정 권역에 강풍·호우 특보를 발효했다.",
                evidence=(_ev("https://example.com/weather/advisory", "official_advisory", "primary", _utc(2026, 6, 21, 18)),),
            ),
            _SeedUpdate(
                observed_at=_utc(2026, 6, 22, 6),
                delta_summary="특보가 인접 권역으로 확대됐고 일부 지역에 추가 강수가 예보됐다.",
                evidence=(_ev("https://example.com/weather/expand", "official_advisory", "primary", _utc(2026, 6, 22, 6)),),
                added_domains=("transport",),
            ),
            _SeedUpdate(
                observed_at=_utc(2026, 6, 22, 20),
                delta_summary="기상 당국이 특보를 주의보로 하향하고 점차 해제될 것으로 전망했다.",
                evidence=(_ev("https://example.com/weather/downgrade", "official_advisory", "resolution", _utc(2026, 6, 22, 20)),),
            ),
        ),
    ),
)


async def seed_one(session: AsyncSession, ev: _SeedEvent) -> Optional[str]:
    """단일 합성 Event 영속(멱등). 이미 매핑된 cluster_id 면 None(건너뜀), 아니면 event_id.

    create_event → map_cluster → append_update×N 을 commit=False 로 호출하고 **이벤트당 1회
    commit** — 중단 시 updates 없는 orphan event 를 남기지 않는다.
    """
    existing = await svc.get_cluster_event(session, ev.cluster_id)
    if existing is not None:
        return None  # 멱등 — 이미 seed 됨(중복 생성 안 함).

    event_id = await svc.create_event(
        session,
        candidate=ResolvedCandidate(
            canonical_title=ev.canonical_title,
            observed_at=ev.first_observed_at,
            domains=ev.domains,
            tags=ev.tags,
            primary_entity_ids=ev.primary_entity_ids,
        ),
        commit=False,
    )
    await svc.map_cluster(session, cluster_id=ev.cluster_id, event_id=event_id, commit=False)
    for u in ev.updates:
        await svc.append_update(
            session,
            event_id=event_id,
            candidate=ResolvedCandidate(
                canonical_title=ev.canonical_title,
                observed_at=u.observed_at,
                delta_summary=u.delta_summary,
                evidence=u.evidence,
                added_domains=u.added_domains,
                source_refs=u.source_refs,
            ),
            commit=False,
        )
    await session.commit()
    return event_id


async def seed_all(session_factory: async_sessionmaker) -> dict:
    """모든 합성 Event 를 영속. {'created': [...], 'skipped': [...]} 반환(멱등 리포트)."""
    created: list[str] = []
    skipped: list[str] = []
    async with session_factory() as session:
        for ev in _SEED_EVENTS:
            event_id = await seed_one(session, ev)
            if event_id is None:
                skipped.append(ev.cluster_id)
            else:
                created.append(ev.cluster_id)
    return {"created": created, "skipped": skipped}


async def _run() -> dict:
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        return await seed_all(factory)
    finally:
        await engine.dispose()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="합성 Event 타임라인 seed (오프라인·멱등, D-2c 데모용).",
    )
    parser.add_argument(
        "--allow-non-dev-db",
        action="store_true",
        help="APP_ENV=staging/production 인 DB 에도 seed 허용(기본 거부 — fail-closed).",
    )
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    # R-EventSinkDbTarget 가드: 비-dev DB 는 명시 허용 없이 거부 + 대상 DB 출력(자격증명 제외).
    label = assert_safe_write_target(
        app_env=settings.APP_ENV,
        database_url=settings.DATABASE_URL,
        allow_non_dev=ns.allow_non_dev_db,
    )
    print(f"- seed target DB: {label} (APP_ENV={settings.APP_ENV})")

    result = asyncio.run(_run())
    print(
        f"- seeded: created={len(result['created'])} skipped(idempotent)={len(result['skipped'])} "
        f"of {len(_SEED_EVENTS)} synthetic events"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

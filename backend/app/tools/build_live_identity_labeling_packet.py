"""ADR#47 — live-derived labeling packet pilot (옵션 A=existing live-PG backlog + 옵션 D=bucket-hash sampling).

ADR#46 packet 함수(build_labeling_packet/summarize_packet_sampling)는 **in-memory 워크시트**를 받고, live-PG 를
읽는 유일한 함수는 ADR#43 `collect_adjudication_eval_pairs`(adjudication ⋈ semantic link)였다. 이 도구는 그 둘을
하나의 운영 entrypoint 로 묶어 **실 파이프라인 유래(synthetic 아님) live 후보**에서 packet 을 만들고, **왜
live_selected 가 0/소량인지**(stage ③ adjudication live 루프 미배선·운영 DB 미마이그레이션 — R-LiveIdentityBacklog)를
backlog/exclusion report 로 표면화한다.

불변(상속): read-only(events/cluster_event_map/event_links write 0)·자동 병합 0·LLM/network 0·raw body/PII 차단·
packet 에 model 판정 미포함(bias 0). 이 도구는 **gold 를 만들지 않는다** — reviewer 라벨 후 ADR#45 resolve 로만 gold.
selection 기본=bucket_hash(옵션 D·정렬 편향 완화·재현 가능; cap 미만 규모에선 효과 nil — 정직 표기).
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.event_resolution import (
    EventIdentityAdjudicationORM,
    EventLinkORM,
)
from backend.app.models.event_timeline import EventORM
from backend.app.services.identity_human_labeling import (
    DEFAULT_REVIEWERS_PER_PAIR,
    SELECTION_BUCKET_HASH,
    LabelingPacketItem,
    build_labeling_packet,
    summarize_packet_sampling,
    write_labeling_packet_jsonl,
)
from backend.app.services.semantic_identity_adjudicator import SEMANTIC_LINK_REASON
from backend.app.tools.export_identity_eval_pairs import collect_adjudication_eval_pairs

# exclusion 사유(왜 semantic link 가 packet 후보로 진입 못 하는가) — 조용한 "후보 없음" 금지.
EXCL_LINK_NO_ADJUDICATION = "semantic_link_without_adjudication"   # stage ③ adjudication 미실행(live 루프 미배선)
EXCL_ADJ_EVENT_MISSING = "adjudication_event_missing"             # adjudication 행은 있으나 Event 소실(skip)


async def _scalar_count(session: AsyncSession, stmt) -> int:
    return int((await session.execute(stmt)).scalar_one() or 0)


async def collect_live_identity_candidates(session: AsyncSession) -> tuple[list[dict], dict]:
    """live-PG identity backlog → (worksheet_rows, backlog_stats). **read-only**(write 0).

    worksheet_rows = ADR#43 collect_adjudication_eval_pairs(adjudication ⋈ semantic link·body/PII 차단·eligible 만).
    backlog_stats = 후보/배제 진단(왜 eligible 가 적은지) — total_candidate_links·total_adjudications·
    eligible_for_packet·exclusion_reasons{semantic_link_without_adjudication, adjudication_event_missing}."""
    total_links = await _scalar_count(
        session,
        select(func.count())
        .select_from(EventLinkORM)
        .where(EventLinkORM.status == "possible")
        .where(EventLinkORM.reason == SEMANTIC_LINK_REASON),
    )
    total_adj = await _scalar_count(
        session, select(func.count()).select_from(EventIdentityAdjudicationORM))
    rows = await collect_adjudication_eval_pairs(session)   # eligible(양쪽 Event 존재)만
    eligible = len(rows)
    backlog = {
        "total_candidate_links": total_links,
        "total_adjudications": total_adj,
        "eligible_for_packet": eligible,
        "exclusion_reasons": {
            EXCL_LINK_NO_ADJUDICATION: max(0, total_links - total_adj),   # adjudication 미생성 link(stage ③ 미실행)
            EXCL_ADJ_EVENT_MISSING: max(0, total_adj - eligible),         # Event 소실로 worksheet skip
        },
    }
    return rows, backlog


def assemble_live_packet_report(
    worksheet_rows: list[dict], backlog: dict, *, packet_id: str, reviewers: list[str],
    event_count_before: int, event_count_after: int,
    reviewers_per_pair: int = DEFAULT_REVIEWERS_PER_PAIR,
    targets: Optional[dict[str, int]] = None,
    selection_method: str = SELECTION_BUCKET_HASH,
) -> dict:
    """(worksheet_rows, backlog, event count) → live_packet_report(순수·결정론). 자동 병합 0.

    rows 가 비면 packet 0·live_selected 0(정직). build/summarize 는 ADR#46 재사용(같은 selection_method)."""
    items = (
        build_labeling_packet(
            worksheet_rows, packet_id=packet_id, reviewers=reviewers,
            reviewers_per_pair=reviewers_per_pair, targets=targets, selection_method=selection_method)
        if worksheet_rows else []
    )
    sampling = summarize_packet_sampling(
        worksheet_rows, targets=targets, packet_items=items, selection_method=selection_method)
    return {
        "packet_id": packet_id,
        "total_candidate_links": backlog["total_candidate_links"],
        "total_adjudications": backlog["total_adjudications"],
        "eligible_for_packet": backlog["eligible_for_packet"],
        "exclusion_reasons": backlog["exclusion_reasons"],
        "selected_count": sampling["selected_count"],
        "live_selected_count": sampling["floor_check"]["live_selected"],
        "selection_method": sampling["selection_method"],
        "selected_by_bucket": sampling["selected_by_bucket"],
        "deficit_by_bucket": sampling["deficit_by_bucket"],
        "by_language": sampling["by_language"],
        "by_source_type": sampling["by_source_type"],
        "by_risk_tag": sampling["by_risk_tag"],
        "live_vs_synthetic": sampling["live_vs_synthetic"],
        "reviewer_assignment_count": len(items),
        "unclassified_count": sampling["unclassified"],
        "floor_check": sampling["floor_check"],
        "event_count_before": event_count_before,
        "event_count_after": event_count_after,   # == before(read-only 입증·자동 병합 0)
        "auto_merge_enabled": False,
    }


async def generate_live_packet_report(
    session: AsyncSession, *, packet_id: str, reviewers: list[str],
    reviewers_per_pair: int = DEFAULT_REVIEWERS_PER_PAIR,
    targets: Optional[dict[str, int]] = None,
    selection_method: str = SELECTION_BUCKET_HASH,
) -> dict:
    """live-PG → live_packet_report. Event count before/after 로 자동 병합 0 입증(read-only)."""
    before = await _scalar_count(session, select(func.count()).select_from(EventORM))
    rows, backlog = await collect_live_identity_candidates(session)
    after = await _scalar_count(session, select(func.count()).select_from(EventORM))
    return assemble_live_packet_report(
        rows, backlog, packet_id=packet_id, reviewers=reviewers,
        event_count_before=before, event_count_after=after,
        reviewers_per_pair=reviewers_per_pair, targets=targets, selection_method=selection_method)


async def build_live_labeling_packet(
    session: AsyncSession, *, packet_id: str, reviewers: list[str],
    reviewers_per_pair: int = DEFAULT_REVIEWERS_PER_PAIR,
    targets: Optional[dict[str, int]] = None,
    selection_method: str = SELECTION_BUCKET_HASH,
) -> list[LabelingPacketItem]:
    """live-PG → packet items(ADR#46 build 재사용·같은 selection_method). 후보 0 이면 []."""
    rows, _ = await collect_live_identity_candidates(session)
    if not rows:
        return []
    return build_labeling_packet(
        rows, packet_id=packet_id, reviewers=reviewers,
        reviewers_per_pair=reviewers_per_pair, targets=targets, selection_method=selection_method)


async def write_live_labeling_packet_jsonl(
    session: AsyncSession, path: Any, *, packet_id: str, reviewers: list[str],
    reviewers_per_pair: int = DEFAULT_REVIEWERS_PER_PAIR,
    targets: Optional[dict[str, int]] = None,
    selection_method: str = SELECTION_BUCKET_HASH,
) -> int:
    """live-PG → packet JSONL(**internal ops artifact**·validate 통과). 후보 0 이면 빈 파일(0행). 반환=행 수."""
    items = await build_live_labeling_packet(
        session, packet_id=packet_id, reviewers=reviewers,
        reviewers_per_pair=reviewers_per_pair, targets=targets, selection_method=selection_method)
    return write_labeling_packet_jsonl(items, path)

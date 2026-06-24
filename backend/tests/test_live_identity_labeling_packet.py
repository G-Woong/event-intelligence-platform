"""ADR#47 — live-derived labeling packet pilot: 결정론(비-DB) 단위 테스트.

DB 리더(collect_live_identity_candidates/generate_live_packet_report)는 live-PG 테스트
(test_event_resolution_live_pg.py)에서 검증. 여기서는 순수 함수(report 조립·옵션 D 표집)만.
"""
from __future__ import annotations

import pytest

from backend.app.services import identity_human_labeling as hl
from backend.app.tools.build_live_identity_labeling_packet import (
    EXCL_ADJ_EVENT_MISSING,
    EXCL_LINK_NO_ADJUDICATION,
    assemble_live_packet_report,
)

_REVIEWERS = ["reviewer-a", "reviewer-b"]


def _live_row(pair_id: str, *, predicted="likely_same_event", reason="", language="en",
              stl="article", st_r="article", title="연준 기준금리 인상 발표"):
    # collect_adjudication_eval_pairs 출력 형태(=live·dataset_source 없음 → SOURCE_LIVE 로 집계).
    return {
        "pair_id": pair_id, "label": "unlabeled", "language": language,
        "source_type_left": stl, "source_type_right": st_r,
        "title_left": title, "title_right": title,
        "observed_at_left": "2026-06-18T11:00:00Z", "observed_at_right": "2026-06-18T14:00:00Z",
        "predicted_status": predicted, "score": 0.9, "reason": reason, "risk_tags": [],
    }


def _backlog(total_links=1, total_adj=1, eligible=1):
    return {
        "total_candidate_links": total_links,
        "total_adjudications": total_adj,
        "eligible_for_packet": eligible,
        "exclusion_reasons": {
            EXCL_LINK_NO_ADJUDICATION: max(0, total_links - total_adj),
            EXCL_ADJ_EVENT_MISSING: max(0, total_adj - eligible),
        },
    }


# ── report 조립(live 후보 존재) ────────────────────────────────────────────────────
def test_assemble_report_live_rows_counts_live_selected():
    rows = [_live_row("p1"), _live_row("p2")]
    rep = assemble_live_packet_report(
        rows, _backlog(2, 2, 2), packet_id="pkt", reviewers=_REVIEWERS,
        event_count_before=7, event_count_after=7)
    assert rep["eligible_for_packet"] == 2
    assert rep["selected_count"] == 2
    assert rep["live_selected_count"] == 2          # live worksheet 행 → live 로 집계(synthetic 0)
    assert rep["live_vs_synthetic"][hl.SOURCE_LIVE] == 2
    assert rep["live_vs_synthetic"][hl.SOURCE_SYNTHETIC] == 0
    assert rep["reviewer_assignment_count"] == 4    # 2 pair × 2 reviewer
    assert rep["unclassified_count"] == 0
    assert rep["auto_merge_enabled"] is False
    assert rep["event_count_before"] == rep["event_count_after"] == 7   # 자동 병합 0
    assert rep["selection_method"] == hl.SELECTION_BUCKET_HASH          # 옵션 D 기본


def test_assemble_report_floor_deficit_honest():
    # live 후보 << 표본 floor(189/381) → deficit 정직 노출(평균 뒤에 숨기지 않음).
    rep = assemble_live_packet_report(
        [_live_row("p1")], _backlog(1, 1, 1), packet_id="pkt", reviewers=_REVIEWERS,
        event_count_before=3, event_count_after=3)
    fc = rep["floor_check"]
    assert fc["live_selected"] == 1
    assert fc["positive_deficit"] > 0 or fc["negative_deficit"] > 0
    assert fc["live_deficit"] > 0


# ── report 조립(후보 0 — 정직한 0) ──────────────────────────────────────────────────
def test_assemble_report_empty_rows_all_zero():
    rep = assemble_live_packet_report(
        [], _backlog(0, 0, 0), packet_id="pkt", reviewers=_REVIEWERS,
        event_count_before=0, event_count_after=0)
    assert rep["eligible_for_packet"] == 0
    assert rep["selected_count"] == 0
    assert rep["live_selected_count"] == 0
    assert rep["reviewer_assignment_count"] == 0    # rows 0 → packet 0(reviewer 부족 에러 없이 빈 packet)
    assert rep["auto_merge_enabled"] is False


def test_assemble_report_exclusion_reasons_passthrough():
    # semantic link 1 있으나 adjudication 0(stage ③ 미실행) → exclusion 으로 표면화(조용한 0 금지).
    rep = assemble_live_packet_report(
        [], _backlog(total_links=1, total_adj=0, eligible=0), packet_id="pkt",
        reviewers=_REVIEWERS, event_count_before=2, event_count_after=2)
    assert rep["total_candidate_links"] == 1
    assert rep["total_adjudications"] == 0
    assert rep["exclusion_reasons"][EXCL_LINK_NO_ADJUDICATION] == 1
    assert rep["exclusion_reasons"][EXCL_ADJ_EVENT_MISSING] == 0


def test_assemble_report_adjudication_event_missing_excluded():
    # adjudication 2 있으나 eligible 1(Event 1개 소실) → adjudication_event_missing=1.
    rep = assemble_live_packet_report(
        [_live_row("p1")], _backlog(total_links=2, total_adj=2, eligible=1),
        packet_id="pkt", reviewers=_REVIEWERS, event_count_before=4, event_count_after=4)
    assert rep["exclusion_reasons"][EXCL_ADJ_EVENT_MISSING] == 1


# ── 옵션 D: bucket-hash 표집(결정론·재현·over-cap 편향 완화) ──────────────────────────
def test_bucket_hash_sampling_reproducible():
    rows = [_live_row(f"p{i:03d}") for i in range(25)]
    a = hl.build_labeling_packet(rows, packet_id="pkt", reviewers=_REVIEWERS,
                                 selection_method=hl.SELECTION_BUCKET_HASH)
    b = hl.build_labeling_packet(rows, packet_id="pkt", reviewers=_REVIEWERS,
                                 selection_method=hl.SELECTION_BUCKET_HASH)
    assert [hl.packet_item_to_dict(x) for x in a] == [hl.packet_item_to_dict(x) for x in b]


def test_bucket_hash_vs_order_diverge_when_over_cap():
    # official_news_positive cap 을 5 로 좁혀 over-cap 유도 → 두 방법 모두 cap 준수, 선택 집합은 상이(편향 완화 실재).
    rows = [_live_row(f"p{i:03d}") for i in range(25)]
    tgt = dict(hl.CANDIDATE_BUCKET_TARGETS, official_news_positive=5)
    order = hl._sample_candidate_pairs(rows, targets=tgt, selection_method=hl.SELECTION_PAIR_ID_ORDER)
    hashed = hl._sample_candidate_pairs(rows, targets=tgt, selection_method=hl.SELECTION_BUCKET_HASH)
    assert len(order) == len(hashed) == 5
    assert [r["pair_id"] for _, r in order] == [f"p{i:03d}" for i in range(5)]   # order=낮은 pair_id 편향
    assert [r["pair_id"] for _, r in order] != [r["pair_id"] for _, r in hashed]  # hash=편향 완화


def test_bucket_hash_selected_subset_of_input():
    rows = [_live_row(f"p{i:03d}") for i in range(25)]
    tgt = dict(hl.CANDIDATE_BUCKET_TARGETS, official_news_positive=5)
    hashed = hl._sample_candidate_pairs(rows, targets=tgt, selection_method=hl.SELECTION_BUCKET_HASH)
    input_ids = {r["pair_id"] for r in rows}
    assert all(r["pair_id"] in input_ids for _, r in hashed)   # cut-off 은 부분집합(가짜 행 0)


def test_invalid_selection_method_raises():
    with pytest.raises(ValueError):
        hl._sample_candidate_pairs([_live_row("p1")], selection_method="random_shuffle")


def test_default_selection_method_preserves_adr46():
    # 기본(인자 미전달)은 ADR#46 pair_id_order — 하위호환(기존 측정/테스트 불변).
    rep = hl.summarize_packet_sampling([_live_row("p1")])
    assert rep["selection_method"] == hl.SELECTION_PAIR_ID_ORDER


def test_summarize_reports_chosen_selection_method():
    rep = hl.summarize_packet_sampling([_live_row("p1")], selection_method=hl.SELECTION_BUCKET_HASH)
    assert rep["selection_method"] == hl.SELECTION_BUCKET_HASH


def test_report_no_model_verdict_leak():
    # report 의 어떤 곳에도 packet item 단위 model 판정이 새지 않는다(by_* 분포는 집계 수치).
    rep = assemble_live_packet_report(
        [_live_row("p1")], _backlog(1, 1, 1), packet_id="pkt", reviewers=_REVIEWERS,
        event_count_before=1, event_count_after=1)
    assert "predicted_status" not in rep and "score" not in rep

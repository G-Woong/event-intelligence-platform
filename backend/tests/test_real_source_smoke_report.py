"""ADR#55 — real-source smoke report 잠금(순수·결정론·DB/network 0).

source quality matrix(§9·옵션 E) source role guard·anchor 자격·실패행, agent readiness 9조건(§8) verdict,
activation report(§4) 병합·db_target 분류·no_auto_merge 불변을 잠근다. community/market/catalog anchor 금지.
"""
from __future__ import annotations

from backend.app.tools.real_source_smoke_report import (
    agent_readiness_conditions,
    agent_readiness_gate,
    assemble_activation_report,
    build_source_quality_matrix,
    classify_adjudication_block_reason,
)

_DEV_URL = "postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel"
_PROD_URL = "postgresql+asyncpg://event_user:event_pass@dbhost:5432/event_intel_prod"


def _rec(record_type, source_id, *, canonical=None, published=None, body="present"):
    return {"record_type": record_type, "source_id": source_id, "title_or_label": "t",
            "canonical_url": canonical, "source_url_or_evidence": canonical,
            "published_at_or_observed_at": published, "body_state_or_signal": body}


def _smoke(**kw):
    base = {
        "source_count": 1, "source_ids": ["federal_register"],
        "source_role_distribution": {"official": 3}, "fetched_records": 3,
        "records_with_body": 3, "records_with_canonical_url": 3, "records_with_published_at": 3,
        "clusters": 1, "singletons_dropped": 1, "semantic_fingerprint_candidates": 1,
        "created_events": None, "held_events": None, "withheld_events": None,
        "identity_links": None, "adjudications": None, "packet_eligible": None,
        "packet_selected": None, "no_auto_merge": True, "failures_by_stage": {},
    }
    base.update(kw)
    return base


# ── source quality matrix(§9) ──────────────────────────────────────────────────────────
def test_matrix_official_record_anchor_eligible():
    recs = [_rec("official_record", "federal_register", canonical="https://fr/d/1", published="2026-06-20")]
    m = build_source_quality_matrix(recs)
    row = m[0]
    assert row["source_id"] == "federal_register" and row["source_role"] == "official"
    assert row["fetch_ok"] is True and row["records_count"] == 1
    assert row["identity_linkability"] == "anchor_eligible"
    assert row["adjudication_readiness"] == "ready_on_cross_link"
    assert row["canonical_url_quality"] == "1/1" and row["published_at_quality"] == "1/1"


def test_matrix_community_is_guard_only_not_anchor():
    recs = [_rec("community_signal", "hacker_news", canonical="https://hn/1", published="2026-06-20")]
    m = build_source_quality_matrix(recs)
    assert m[0]["source_role"] == "community"
    assert m[0]["identity_linkability"] == "guard_only"           # anchor 금지
    assert m[0]["adjudication_readiness"] == "blocked_non_publishable"
    assert m[0]["body_quality"] == "conditional"


def test_matrix_market_signal_metadata_complete_guard_only():
    recs = [_rec("structured_signal", "coinbase_market", body="missing")]
    m = build_source_quality_matrix(recs)
    assert m[0]["source_role"] == "signal"
    assert m[0]["identity_linkability"] == "guard_only"           # market anchor 금지
    assert m[0]["body_quality"] == "metadata_complete"           # 본문 미추출이 실패 아님


def test_matrix_catalog_guard_only():
    recs = [_rec("catalog_metadata", "tmdb")]
    m = build_source_quality_matrix(recs)
    assert m[0]["source_role"] == "catalog"
    assert m[0]["identity_linkability"] == "guard_only"


def test_matrix_unknown_record_type_fail_closed():
    recs = [_rec("weird_type", "mystery", canonical="https://x/1")]
    m = build_source_quality_matrix(recs)
    assert m[0]["source_role"] == "unknown"                       # fail-closed
    assert m[0]["identity_linkability"] == "guard_only"


def test_matrix_failure_rows_for_fetch_failures():
    m = build_source_quality_matrix([], failures_by_source={"sec_edgar": "network_error"})
    assert len(m) == 1 and m[0]["fetch_ok"] is False
    assert m[0]["failure_stage"] == "network_error" and m[0]["records_count"] == 0


def test_matrix_anchor_needs_canonical():
    # official 이지만 canonical 미보유 → anchor_eligible 아님(강신호 없음).
    recs = [_rec("official_record", "federal_register", canonical=None, published="2026-06-20")]
    assert build_source_quality_matrix(recs)[0]["identity_linkability"] == "guard_only"


def test_matrix_failure_row_skipped_when_source_has_records():
    # 같은 source 가 일부 record 를 냈으면 fetch_ok 행으로 처리·failures_by_source 중복행 미생성.
    recs = [_rec("official_record", "federal_register", canonical="https://fr/d/1")]
    m = build_source_quality_matrix(recs, failures_by_source={"federal_register": "no_records"})
    rows = [r for r in m if r["source_id"] == "federal_register"]
    assert len(rows) == 1 and rows[0]["fetch_ok"] is True


# ── agent readiness 9조건(§8) ───────────────────────────────────────────────────────────
def test_agent_readiness_default_no_go():
    conds = agent_readiness_conditions(_smoke())
    assert len(conds) == 9
    gate = agent_readiness_gate(conds)
    assert gate["verdict"] == "No-Go"
    assert gate["unmet_conditions"] == [1, 4, 5, 7]               # backlog·gold·MERGE_GATE·uncertainty
    assert gate["pass_count"] == 3                                # 2,8,9 PASS


def test_agent_readiness_condition_statuses():
    by_n = {c["n"]: c["status"] for c in agent_readiness_conditions(_smoke())}
    assert by_n[1] == "FAIL"        # production backlog 0
    assert by_n[2] == "PASS"        # source role guard
    assert by_n[3] == "PARTIAL"     # shadow adjudication
    assert by_n[4] == "FAIL"        # no gold
    assert by_n[5] == "FAIL"        # MERGE_GATE 미통과
    assert by_n[6] == "PARTIAL"     # raw/public 분리
    assert by_n[7] == "NOT_BUILT"   # uncertainty
    assert by_n[8] == "PASS"        # community reaction layer
    assert by_n[9] == "PASS"        # time-series substrate


def test_agent_readiness_production_backlog_flips_condition_1():
    conds = agent_readiness_conditions(_smoke(), production_backlog=10)
    assert {c["n"]: c["status"] for c in conds}[1] == "PASS"


def test_agent_readiness_gold_and_merge_gate_flip_conditions():
    conds = agent_readiness_conditions(_smoke(), has_live_gold=True, merge_gate_passed=True)
    by_n = {c["n"]: c["status"] for c in conds}
    assert by_n[4] == "PASS" and by_n[5] == "PASS"


def test_agent_readiness_gate_go_when_all_met():
    conds = agent_readiness_conditions(
        _smoke(), production_backlog=10, has_live_gold=True, merge_gate_passed=True)
    # uncertainty(7) NOT_BUILT 는 여전히 미충족 → No-Go 유지(보수).
    assert agent_readiness_gate(conds)["verdict"] == "No-Go"
    assert agent_readiness_gate(conds)["unmet_conditions"] == [7]


# ── activation report 병합(§4) ──────────────────────────────────────────────────────────
def test_assemble_report_fields_and_classification():
    r = assemble_activation_report(
        _smoke(created_events=1, identity_links=1, adjudications=0,
               event_count_before=4, event_count_after=6),
        run_mode="live_db", app_env="test", database_url=_DEV_URL,
        records=[_rec("official_record", "federal_register", canonical="https://fr/d/1")])
    assert r["run_mode"] == "live_db"
    assert r["db_target_classification"] == "test" and r["is_production_target"] is False
    assert r["created_events"] == 1 and r["identity_links"] == 1
    assert r["event_count_before"] == 4 and r["event_count_after"] == 6
    assert r["no_auto_merge"] is True
    assert len(r["source_quality_matrix"]) == 1
    assert r["agent_readiness_gate"]["verdict"] == "No-Go"
    assert any("승인 전 금지" in a for a in r["next_actions"])


def test_assemble_report_reviewer_exportable_from_packet_eligible():
    r0 = assemble_activation_report(_smoke(packet_eligible=0), run_mode="live_db",
                                    app_env="test", database_url=_DEV_URL)
    assert r0["reviewer_packet_exportable"] is False              # eligible 0
    r1 = assemble_activation_report(_smoke(packet_eligible=3), run_mode="live_db",
                                    app_env="test", database_url=_DEV_URL)
    assert r1["reviewer_packet_exportable"] is True


def test_assemble_report_offline_packet_none_exportable_none():
    r = assemble_activation_report(_smoke(), run_mode="fake", app_env="dev", database_url=_DEV_URL)
    assert r["packet_eligible"] is None and r["reviewer_packet_exportable"] is None


def test_assemble_report_production_target_classified():
    r = assemble_activation_report(_smoke(), run_mode="live_network",
                                   app_env="production", database_url=_PROD_URL)
    assert r["db_target_classification"] == "production" and r["is_production_target"] is True


def test_assemble_report_fake_mode_next_actions_suggest_live_network():
    r = assemble_activation_report(_smoke(), run_mode="fake", app_env="dev", database_url=_DEV_URL)
    assert any("live-network" in a for a in r["next_actions"])


# ── §5 adjudication block-reason 분해(ADR#56) ──────────────────────────────────────────
def test_block_reason_db_not_reached_when_offline():
    assert classify_adjudication_block_reason({"adjudications": None}) == "db_not_reached"


def test_block_reason_none_when_adjudication_present():
    assert classify_adjudication_block_reason({"adjudications": 1}) == "none"


def test_block_reason_semantic_link_without_adjudication():
    # semantic 후보 link 는 있으나 미판정(persist=False 등).
    out = classify_adjudication_block_reason(
        {"adjudications": 0, "semantic_cross_batch_candidates": 2})
    assert out == "semantic_link_without_adjudication"


def test_block_reason_no_cross_batch_overlap_single_source():
    # publishable·fingerprint 있으나 같은 fingerprint 의 기존 Event 부재(단일소스 federal_register 케이스).
    out = classify_adjudication_block_reason(
        {"adjudications": 0, "semantic_cross_batch_candidates": 0,
         "semantic_fingerprint_candidates": 1, "clusters": 1})
    assert out == "no_cross_batch_overlap"


def test_block_reason_non_publishable_role():
    out = classify_adjudication_block_reason(
        {"adjudications": 0, "semantic_cross_batch_candidates": 0,
         "semantic_fingerprint_candidates": 0, "clusters": 1,
         "failures_by_stage": {"non_publishable_role": 1}})
    assert out == "non_publishable_role"


def test_block_reason_no_fingerprint_overlap_generic_title():
    # publishable 이나 fingerprint 0(generic 제목·시점 불명) — non_publishable 아님.
    out = classify_adjudication_block_reason(
        {"adjudications": 0, "semantic_cross_batch_candidates": 0,
         "semantic_fingerprint_candidates": 0, "clusters": 1,
         "failures_by_stage": {"non_publishable_role": 0}})
    assert out == "no_fingerprint_overlap"


# ── time-series replay report fields(ADR#56·§4/§5) ─────────────────────────────────────
def _replay_smoke(**kw):
    base = {
        "mode": "live_db", "smoke_mode": "time_series_replay", "artificial_replay": True,
        "real_fetch": False, "batches": 2, "records_per_batch": [2, 2],
        "source_count": 4, "source_ids": ["wire_alpha", "wire_beta", "wire_gamma", "wire_delta"],
        "created_events": 2, "appended_events": 0, "held_events": 0,
        "semantic_cross_batch_candidates": 1,
        "identity_link_reason_distribution": {"semantic_cross_batch_candidate": 1},
        "adjudications": 1, "adjudication_status_distribution": {"likely_same_event": 1},
        "event_count_before": 0, "event_count_after": 2, "no_auto_merge": True,
    }
    base.update(kw)
    return base


def test_assemble_report_replay_fields_and_block_none():
    r = assemble_activation_report(
        _replay_smoke(), run_mode="live_db", app_env="test", database_url=_DEV_URL)
    assert r["smoke_mode"] == "time_series_replay" and r["artificial_replay"] is True
    assert r["batches"] == 2
    assert r["semantic_cross_batch_candidates"] == 1
    assert r["identity_link_reason_distribution"] == {"semantic_cross_batch_candidate": 1}
    assert r["adjudication_status_distribution"] == {"likely_same_event": 1}
    assert r["adjudication_block_reason"] == "none"          # adjudication 발생(차단 아님)
    assert r["no_auto_merge"] is True
    # event_count 정확히 +2(배치당 1 CREATE·자동 병합 0).
    assert r["event_count_after"] - r["event_count_before"] == 2


def test_assemble_report_replay_next_actions_flag_artificial():
    r = assemble_activation_report(
        _replay_smoke(), run_mode="live_db", app_env="test", database_url=_DEV_URL)
    # artificial replay 가 production 검증으로 과장되지 않도록 경고가 next_actions 에 포함.
    assert any("artificial replay" in a for a in r["next_actions"])


def test_assemble_report_offline_smoke_mode_is_offline():
    # offline(DB 미도달·created None) → smoke_mode='offline'·block='db_not_reached'.
    r = assemble_activation_report(_smoke(), run_mode="fake", app_env="dev", database_url=_DEV_URL)
    assert r["smoke_mode"] == "offline"
    assert r["adjudication_block_reason"] == "db_not_reached"

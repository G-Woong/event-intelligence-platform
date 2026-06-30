"""ADR#92 §9 — live attempt pack builder tests.

검증: pack 후보는 live 를 트리거할 수 없다(operator_confirmed/live_approved 강제 False)·real payload 자동 쓰기 0·
network 0·disk read 0·코드가 event 발생 단정 0·모든 후보에 verify warning + official/news query draft·운영 명령은
수동 instruction·secret/PII 0.
"""
from __future__ import annotations

import os

from backend.app.tools.live_attempt_pack_builder import (
    ATTEMPT_PACK_ID,
    PACK_READY,
    PACK_REAL_PRESENT,
    build_candidate_event_shape,
    build_live_attempt_pack,
    sanitized_live_attempt_pack,
)
from backend.app.tools.operator_regulatory_event_payload import (
    PAYLOAD_NOT_PROVIDED,
    PAYLOAD_PRESENT_VALID,
    REAL_PAYLOAD_PATH,
)

_CANDIDATE_FIELDS = {
    "candidate_id", "regulatory_domain", "agency_or_entity", "action_phrase",
    "date_window_start", "date_window_end", "official_query_draft", "news_query_draft",
    "expected_news_angle", "source_strategy", "risk_notes",
    "operator_must_verify_occurrence", "operator_must_set_confirmed", "operator_must_set_live_approved",
}


# ── 17. pack status ready when payload absent ──
def test_pack_status_ready_when_payload_absent():
    out = build_live_attempt_pack(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["live_attempt_pack_status"] == PACK_READY
    assert out["operator_fill_required"] is True
    assert out["attempt_pack_id"] == ATTEMPT_PACK_ID


def test_pack_status_ready_when_status_not_injected():
    # status 미주입(None) → disk read 없이 ready 로 본다(frontier-safe).
    out = build_live_attempt_pack()
    assert out["live_attempt_pack_status"] == PACK_READY
    assert out["operator_fill_required"] is True


def test_pack_optional_when_real_payload_present():
    out = build_live_attempt_pack(operator_payload_status=PAYLOAD_PRESENT_VALID)
    assert out["live_attempt_pack_status"] == PACK_REAL_PRESENT
    assert out["operator_fill_required"] is False


# ── 18. candidate_count > 0 (curated seed bank has named regulatory shapes) ──
def test_candidate_count_positive():
    out = build_live_attempt_pack()
    assert out["candidate_count"] > 0
    assert len(out["candidate_event_shapes"]) == out["candidate_count"]
    assert out["available_candidate_ids"]


# ── 19./§9. every candidate has the verify warning + 14 fields ──
def test_every_candidate_has_verify_warning_and_shape():
    out = build_live_attempt_pack()
    for c in out["candidate_event_shapes"]:
        assert set(c.keys()) == _CANDIDATE_FIELDS
        assert c["operator_must_verify_occurrence"] is True
        assert c["operator_must_set_confirmed"] is True
        assert c["operator_must_set_live_approved"] is True


# ── 20./21. no candidate is confirmed/approved (cannot trigger live) ──
def test_no_candidate_confirmed_or_approved():
    out = build_live_attempt_pack()
    assert out["all_candidates_operator_confirmed_false"] is True
    assert out["all_candidates_live_approved_false"] is True
    assert out["pack_candidates_can_trigger_live"] is False


# ── §9. every candidate has official/news query draft ──
def test_every_candidate_has_official_and_news_query_draft():
    out = build_live_attempt_pack()
    for c in out["candidate_event_shapes"]:
        assert str(c["official_query_draft"]).strip()
        assert str(c["news_query_draft"]).strip()
        assert str(c["source_strategy"]).strip()


# ── 22. pack writes no real payload (existence state unchanged) ──
def test_pack_writes_no_real_payload():
    exists_before = os.path.exists(REAL_PAYLOAD_PATH)
    out = build_live_attempt_pack()
    exists_after = os.path.exists(REAL_PAYLOAD_PATH)
    assert exists_before == exists_after
    assert out["code_writes_real_payload_path"] is False
    assert out["code_reads_disk"] is False


# ── 23. pack invokes no network (sys.modules + structural — Finding E 강화) ──
def test_pack_invokes_no_network():
    import sys

    import backend.app.tools.live_attempt_pack_builder as mod

    # build 가 http client 를 **새로** 로드하지 않는지(transitive 포함·이미 로드된 상태와 무관).
    http_clients = {"httpx", "requests", "aiohttp", "urllib3"}
    before = http_clients & set(sys.modules)
    out = build_live_attempt_pack()
    after = http_clients & set(sys.modules)
    assert out["code_invokes_network"] is False
    assert after == before, "build_live_attempt_pack loaded an http client (network risk)"
    # 모듈 소스 회귀 방어(http client import 0).
    with open(mod.__file__, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "import httpx" not in text
    assert "import requests" not in text


# ── §9. pack output contains validation/live commands as manual instructions ──
def test_pack_surfaces_manual_commands():
    out = build_live_attempt_pack()
    assert "operator_regulatory_event_payload" in out["validation_command"]
    assert "operator_confirmed_live_runner" in out["manual_live_command"]
    assert out["live_command_is_manual_step"] is True
    assert REAL_PAYLOAD_PATH in out["validation_command"]


# ── §9. code does not claim event occurred / no same_event truth ──
def test_pack_does_not_assert_occurrence_or_same_event():
    out = build_live_attempt_pack()
    assert out["code_claims_event_occurred"] is False
    assert out["event_occurrence_verified_by_code"] is False
    assert out["same_event_asserted"] is False
    assert out["merge_allowed"] is False
    assert out["production_gold_count"] == 0
    assert out["actual_sending_performed"] is False


# ── §9. candidate shape builder mirrors the forced-False template (agency_or_entity present) ──
def test_candidate_event_shape_named_subject():
    seed = {
        "seed_id": "demo_named",
        "regulatory_domain": "agency final rule",
        "official_provider": "federal_register",
        "news_providers": ["guardian", "nyt"],
        "agency": "Environmental Protection Agency",
        "entity": "EPA emissions rule",
        "action_phrase": "final rule on emissions",
        "official_query": "EPA emissions final rule",
        "news_query": "EPA emissions rule",
        "expected_news_angle": "industry reaction",
        "date_window_start": "2026-06-25",
        "date_window_end": "2026-06-26",
        "risk": "title tokens may diverge",
    }
    c = build_candidate_event_shape(seed)
    assert c["candidate_id"] == "demo_named"
    assert c["agency_or_entity"] == "Environmental Protection Agency"
    assert c["official_query_draft"] == "EPA emissions final rule"
    assert "federal_register" in c["source_strategy"]
    assert "enforce_window=True" in c["source_strategy"]


# ── sanitized projection (frontier 용) ──
def test_sanitized_projection_keys():
    out = build_live_attempt_pack()
    s = sanitized_live_attempt_pack(out)
    assert set(s.keys()) == {
        "live_attempt_pack_status", "candidate_count", "operator_fill_required",
        "all_candidates_operator_confirmed_false", "all_candidates_live_approved_false",
        "pack_candidates_can_trigger_live", "live_attempt_pack_next_action",
    }
    assert s["live_attempt_pack_next_action"]

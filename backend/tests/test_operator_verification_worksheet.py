"""ADR#95 §10 (#16-21) — operator_verification_worksheet 테스트(HUMAN-fills·official↔news 분리·완료해도 확정 아님·network 0).

검증: 기본(빈 worksheet)은 incomplete·완료 차단; official/news/date_window 중 하나라도 미충족이면 completion 차단;
셋 모두 충족이면 WORKSHEET_COMPLETE 이되 **payload 아님·operator_confirmed False·code_sets_operator_confirmed_true
False**(완료 ≠ 확정); official_source_check 와 news_coverage_check 는 서로 다른 key; unresolved_questions non-empty;
operator_confirmation_fields == 12개 required fields; _assert_pii_safe 통과; CLI --json 0.
"""
from __future__ import annotations

from backend.app.tools.operator_regulatory_event_intake import OPERATOR_EVENT_REQUIRED_FIELDS
from backend.app.tools.operator_verification_worksheet import (
    CONTRACT_VERSION,
    OPERATION_NAME,
    WORKSHEET_COMPLETE,
    WORKSHEET_INCOMPLETE,
    build_operator_verification_worksheet,
    main,
    sanitized_operator_verification_worksheet,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

_REQUIRED_KEYS = {
    "operation_name", "contract_version", "worksheet_status", "candidate_id",
    "official_source_check", "news_coverage_check", "date_window_check", "agency_entity_check",
    "action_phrase_check", "canonical_url_check", "published_at_check", "source_role_check",
    "operator_confirmation_fields", "unresolved_questions", "completion_status",
    "worksheet_is_payload", "worksheet_complete_auto_confirms", "code_sets_operator_confirmed_true",
    "code_sets_live_approved_true", "operator_confirmed", "live_approved", "same_event_asserted",
    "network_invoked", "production_gold_count",
}

_CHECK_KEYS = {
    "official_source_check", "news_coverage_check", "date_window_check", "agency_entity_check",
    "action_phrase_check", "canonical_url_check", "published_at_check", "source_role_check",
}


def _sat(value: str = "recorded evidence") -> dict:
    """충족된 check 입력(confirmed True ∧ record_slot 비어있지 않음)."""
    return {"confirmed": True, "record_slot": value}


# ── required keys + operation/contract + check shape ────────────────────────────────────────────────────────────
def test_required_keys_and_lead_fields_present():
    out = build_operator_verification_worksheet()
    assert _REQUIRED_KEYS <= set(out)
    assert out["operation_name"] == OPERATION_NAME
    assert out["contract_version"] == CONTRACT_VERSION
    # 각 *_check 는 {item, instruction, record_slot, confirmed} dict.
    for key in _CHECK_KEYS:
        c = out[key]
        assert isinstance(c, dict)
        assert set(c) == {"item", "instruction", "record_slot", "confirmed"}
        assert c["confirmed"] is False
        assert c["record_slot"] == ""
        assert c["item"] and c["instruction"]


# ── default (no checks) → incomplete & blocks ───────────────────────────────────────────────────────────────────
def test_default_no_checks_incomplete_and_blocks():
    out = build_operator_verification_worksheet()
    assert out["completion_status"] == "incomplete"
    assert out["worksheet_status"] == WORKSHEET_INCOMPLETE
    assert out["operator_confirmed"] is False
    assert out["live_approved"] is False


# ── incomplete official check blocks completion (news+date satisfied, official unsatisfied) ──────────────────────
def test_incomplete_official_check_blocks_completion():
    out = build_operator_verification_worksheet(
        news_coverage_check=_sat("https://nyt.example/a"),
        date_window_check=_sat("2026-06-25"),
        # official_check 미제공 → 미충족.
    )
    assert out["completion_status"] == "incomplete"
    assert out["worksheet_status"] == WORKSHEET_INCOMPLETE


# ── incomplete news check blocks completion ─────────────────────────────────────────────────────────────────────
def test_incomplete_news_check_blocks_completion():
    out = build_operator_verification_worksheet(
        official_check=_sat("FR doc 2026-12345"),
        date_window_check=_sat("2026-06-25"),
        # news_coverage_check 미제공 → 미충족.
    )
    assert out["completion_status"] == "incomplete"
    assert out["worksheet_status"] == WORKSHEET_INCOMPLETE


# ── missing/unsatisfied date_window blocks completion ───────────────────────────────────────────────────────────
def test_missing_or_unsatisfied_date_window_blocks_completion():
    # date_window 누락.
    out_missing = build_operator_verification_worksheet(
        official_check=_sat("FR doc 2026-12345"), news_coverage_check=_sat("https://nyt.example/a"))
    assert out_missing["completion_status"] == "incomplete"
    # date_window confirmed=True 이지만 record_slot 빈칸 → 미충족(빈칸 confirm 둔갑 차단).
    out_blank = build_operator_verification_worksheet(
        official_check=_sat("FR doc 2026-12345"), news_coverage_check=_sat("https://nyt.example/a"),
        date_window_check={"confirmed": True, "record_slot": ""})
    assert out_blank["completion_status"] == "incomplete"
    assert out_blank["worksheet_status"] == WORKSHEET_INCOMPLETE


# ── confirmed without a record_slot is NOT satisfied (any check) ─────────────────────────────────────────────────
def test_confirmed_without_record_slot_not_satisfied():
    out = build_operator_verification_worksheet(
        official_check={"confirmed": True, "record_slot": "   "},   # whitespace only.
        news_coverage_check=_sat("https://nyt.example/a"),
        date_window_check=_sat("2026-06-25"))
    assert out["completion_status"] == "incomplete"


# ── fully satisfied → WORKSHEET_COMPLETE BUT complete != confirmation ────────────────────────────────────────────
def test_fully_satisfied_complete_but_not_confirmation():
    out = build_operator_verification_worksheet(
        official_check=_sat("FR doc 2026-12345"),
        news_coverage_check=_sat("https://nyt.example/article"),
        date_window_check=_sat("2026-06-25"))
    assert out["completion_status"] == "complete"
    assert out["worksheet_status"] == WORKSHEET_COMPLETE
    # 완료조차 확정이 아니다 — 코드가 operator_confirmed/live_approved 를 True 로 두지 않는다.
    assert out["worksheet_is_payload"] is False
    assert out["worksheet_complete_auto_confirms"] is False
    assert out["operator_confirmed"] is False
    assert out["live_approved"] is False
    assert out["code_sets_operator_confirmed_true"] is False
    assert out["code_sets_live_approved_true"] is False
    assert out["same_event_asserted"] is False


# ── no network (and the live/payload invariants are hardcoded False/0) ──────────────────────────────────────────
def test_no_network_and_invariants():
    out = build_operator_verification_worksheet()
    assert out["network_invoked"] is False
    assert out["worksheet_is_payload"] is False
    assert out["same_event_asserted"] is False
    assert out["production_gold_count"] == 0
    # build 시그니처에 acquisition_fn 이 없다(live 를 주입할 자리 없음).
    import inspect
    sig = inspect.signature(build_operator_verification_worksheet)
    assert "acquisition_fn" not in sig.parameters
    # 모듈 소스가 live runner 를 import/호출하지 않는다.
    import backend.app.tools.operator_verification_worksheet as mod
    with open(mod.__file__, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "operator_confirmed_live_runner" not in text
    assert "import httpx" not in text
    assert "import requests" not in text


# ── official_source_check and news_coverage_check are DIFFERENT keys (structurally separate) ─────────────────────
def test_official_and_news_checks_are_different_keys():
    out = build_operator_verification_worksheet()
    assert "official_source_check" in out
    assert "news_coverage_check" in out
    assert out["official_source_check"] is not out["news_coverage_check"]
    # official 항목은 official 어휘, news 항목은 news 어휘(같은 칸에 섞이지 않음).
    assert "official" in out["official_source_check"]["item"].lower()
    assert "news" in out["news_coverage_check"]["item"].lower()


# ── unresolved_questions is a non-empty list ────────────────────────────────────────────────────────────────────
def test_unresolved_questions_non_empty():
    out = build_operator_verification_worksheet()
    assert isinstance(out["unresolved_questions"], list)
    assert len(out["unresolved_questions"]) >= 1
    assert all(isinstance(q, str) and q for q in out["unresolved_questions"])


# ── operator_confirmation_fields == the 12 required intake fields ───────────────────────────────────────────────
def test_operator_confirmation_fields_equal_required_fields():
    out = build_operator_verification_worksheet()
    assert out["operator_confirmation_fields"] == list(OPERATOR_EVENT_REQUIRED_FIELDS)
    assert len(out["operator_confirmation_fields"]) == 12


# ── candidate fields come from the regulatory seed bank (default epa) ───────────────────────────────────────────
def test_candidate_from_seed_bank_default_epa():
    out = build_operator_verification_worksheet()
    assert out["candidate_id"] == "epa_final_rule_emissions"
    # seed-derived instruction 이 official/news query 어휘를 반영한다.
    assert "emissions" in out["official_source_check"]["instruction"].lower()
    assert "emissions" in out["news_coverage_check"]["instruction"].lower()
    # date window 가 instruction/item 에 반영된다.
    assert "2026-06-25" in out["date_window_check"]["item"]


# ── _assert_pii_safe passes on the full output (no forbidden keys at any depth) ─────────────────────────────────
def test_assert_pii_safe_passes():
    out = build_operator_verification_worksheet(
        official_check=_sat(), news_coverage_check=_sat(), date_window_check=_sat())
    # build 가 이미 호출하지만, 외부에서 한 번 더 호출해도 통과(드리프트 가드).
    _assert_pii_safe(out, _path="operator_verification_worksheet_output")


# ── sanitized projection is a strict subset-ish aggregate (no check bodies) ─────────────────────────────────────
def test_sanitized_projection_excludes_check_bodies():
    out = build_operator_verification_worksheet()
    s = sanitized_operator_verification_worksheet(out)
    for key in _CHECK_KEYS:
        assert key not in s
    assert s["worksheet_status"] == out["worksheet_status"]
    assert s["completion_status"] == out["completion_status"]
    assert s["operator_confirmation_field_count"] == 12
    assert s["unresolved_question_count"] == len(out["unresolved_questions"])
    assert s["code_sets_operator_confirmed_true"] is False


# ── CLI --json smoke (exit 0 · aggregate only) ──────────────────────────────────────────────────────────────────
def test_main_json_smoke(capsys):
    rc = main(["--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "worksheet_status" in captured.out
    assert "completion_status" in captured.out
    # check 본문(instruction)은 aggregate JSON 에 노출되지 않는다.
    assert "record_slot" not in captured.out

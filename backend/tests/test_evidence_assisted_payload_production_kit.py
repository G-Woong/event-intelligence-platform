"""ADR#95 §21 (#8-15) — evidence_assisted_payload_production_kit 테스트(operator-actionable EVIDENCE-REQUIREMENTS
kit·NOT a payload·live 트리거 0·event 발생 단정 0·network 0).

검증: kit status == evidence_payload_kit_ready, kit_is_payload/kit_can_trigger_live/network_invoked False,
official/news evidence requirements 가 비어있지 않고 acceptance 기준을 담으며, source_role_requirements 가 official=
authoritative evidence·news=public reporting·NOT same role·community/market NOT anchor 를 명시하고, validate/live
명령은 비어있지 않은 문자열로만 나오며, operator_confirmed/live_approved/same_event_asserted False·production gold 0,
sanitized 투영은 status 를 담는 strict subset, build 가 `_assert_pii_safe` 를 통과(raise 0)하고 secret/PII 0.
"""
from __future__ import annotations

from backend.app.tools.evidence_assisted_payload_production_kit import (
    CONTRACT_VERSION,
    KIT_READY,
    OPERATION_NAME,
    build_evidence_assisted_payload_production_kit,
    main,
    sanitized_evidence_assisted_payload_production_kit,
)

_FORBIDDEN_KEYS = {"reviewer_name", "name", "email", "phone", "score", "model_score", "rationale",
                   "predicted_status", "raw_body", "body", "secret", "api_key", "provider_secret"}

_REQUIRED_KEYS = {
    "operation_name", "contract_version", "evidence_payload_kit_status", "selected_candidate_id",
    "official_evidence_required", "official_evidence_required_count", "news_evidence_required",
    "news_evidence_required_count", "agency_or_entity_required", "action_phrase_required",
    "date_window_required", "expected_news_angle_required", "source_role_requirements",
    "real_payload_path", "validation_command", "live_command", "operator_next_action",
}

_INVARIANTS: dict[str, object] = {
    "kit_is_payload": False,
    "kit_can_trigger_live": False,
    "operator_confirmed": False,
    "live_approved": False,
    "same_event_asserted": False,
    "code_claims_event_occurred": False,
    "network_invoked": False,
    "production_gold_count": 0,
}


def _walk_keys(obj: object):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_keys(item)


# ── required keys + operation/contract + invariants ────────────────────────────────────────────────────────────
def test_required_keys_and_invariants_present():
    out = build_evidence_assisted_payload_production_kit()
    assert _REQUIRED_KEYS <= set(out)
    assert out["operation_name"] == OPERATION_NAME
    assert out["contract_version"] == CONTRACT_VERSION
    for key, val in _INVARIANTS.items():
        assert out[key] is val if isinstance(val, bool) else out[key] == val


# ── kit status == evidence_payload_kit_ready (default candidate epa) ───────────────────────────────────────────
def test_kit_status_ready():
    out = build_evidence_assisted_payload_production_kit()
    assert out["evidence_payload_kit_status"] == KIT_READY == "evidence_payload_kit_ready"
    assert out["selected_candidate_id"] == "epa_final_rule_emissions"


# ── kit is NOT a payload (and does not claim the event occurred) ───────────────────────────────────────────────
def test_kit_is_not_a_payload():
    out = build_evidence_assisted_payload_production_kit()
    assert out["kit_is_payload"] is False
    assert out["code_claims_event_occurred"] is False


# ── kit cannot trigger live AND network 0 ──────────────────────────────────────────────────────────────────────
def test_kit_cannot_trigger_live_and_no_network():
    out = build_evidence_assisted_payload_production_kit()
    assert out["kit_can_trigger_live"] is False
    assert out["network_invoked"] is False


# ── official evidence requirements present & non-empty (provider/query/agency/document_type/overlap/acceptance) ─
def test_official_evidence_required_present_nonempty():
    out = build_evidence_assisted_payload_production_kit()
    oe = out["official_evidence_required"]
    assert isinstance(oe, list) and oe
    assert out["official_evidence_required_count"] == len(oe)
    entry = oe[0]
    assert entry["provider"] == "federal_register"
    assert entry["query"]
    assert entry["agency"] == "Environmental Protection Agency"
    assert entry["document_type"]
    assert entry["expected_overlap_tokens"]
    assert entry["acceptance_criteria"]


# ── news evidence requirements present & non-empty (provider guardian/nyt + query/angle/action/acceptance) ──────
def test_news_evidence_required_present_nonempty():
    out = build_evidence_assisted_payload_production_kit()
    ne = out["news_evidence_required"]
    assert isinstance(ne, list) and ne
    assert out["news_evidence_required_count"] == len(ne)
    entry = ne[0]
    assert "guardian" in entry["provider"] and "nyt" in entry["provider"]
    assert entry["query"]
    assert entry["expected_news_angle"]
    assert entry["action_phrase"]
    assert entry["acceptance_criteria"]


# ── source_role_requirements present (official evidence vs news reporting · NOT same role · community NOT anchor) ─
def test_source_role_requirements_present():
    out = build_evidence_assisted_payload_production_kit()
    srr = out["source_role_requirements"]
    assert srr
    assert srr["official"] == "authoritative evidence"
    assert srr["news"] == "public reporting"
    assert srr["not_same_role"] is True
    assert srr["community_or_market_not_anchor"] is True


# ── validation/live commands present and are non-empty strings ─────────────────────────────────────────────────
def test_validation_and_live_commands_are_strings():
    out = build_evidence_assisted_payload_production_kit()
    assert isinstance(out["validation_command"], str) and out["validation_command"]
    assert isinstance(out["live_command"], str) and out["live_command"]


# ── operator_confirmed False ───────────────────────────────────────────────────────────────────────────────────
def test_operator_confirmed_false():
    out = build_evidence_assisted_payload_production_kit()
    assert out["operator_confirmed"] is False


# ── live_approved False ────────────────────────────────────────────────────────────────────────────────────────
def test_live_approved_false():
    out = build_evidence_assisted_payload_production_kit()
    assert out["live_approved"] is False


# ── same_event_asserted False ──────────────────────────────────────────────────────────────────────────────────
def test_same_event_asserted_false():
    out = build_evidence_assisted_payload_production_kit()
    assert out["same_event_asserted"] is False


# ── production_gold_count 0 ────────────────────────────────────────────────────────────────────────────────────
def test_production_gold_count_zero():
    out = build_evidence_assisted_payload_production_kit()
    assert out["production_gold_count"] == 0


# ── sanitized projection has the status and is a strict subset (no evidence body / commands) ───────────────────
def test_sanitized_projection_has_status_strict_subset():
    out = build_evidence_assisted_payload_production_kit()
    s = sanitized_evidence_assisted_payload_production_kit(out)
    assert s["evidence_payload_kit_status"] == out["evidence_payload_kit_status"]
    assert set(s).issubset(set(out))
    assert set(s) != set(out)
    for leaked in ("official_evidence_required", "news_evidence_required", "validation_command",
                   "live_command", "operator_next_action", "source_role_requirements"):
        assert leaked not in s


# ── _assert_pii_safe passes (build does not raise) AND no forbidden keys anywhere ──────────────────────────────
def test_build_pii_safe_no_forbidden_keys():
    out = build_evidence_assisted_payload_production_kit()  # build 가 _assert_pii_safe 통과(raise 0).
    keys = set(_walk_keys(out))
    assert keys.isdisjoint(_FORBIDDEN_KEYS), keys & _FORBIDDEN_KEYS


# ── CLI --json smoke (aggregate only · evidence body/commands excluded) ────────────────────────────────────────
def test_main_json_smoke(capsys):
    rc = main(["--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "evidence_payload_kit_status" in captured.out
    assert "validation_command" not in captured.out

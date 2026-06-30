"""ADR#93 §10/§20 — operator live command pack tests (#16-#23).

검증: validate-only / dry-run 명령에 live flag 0(network 0), live 명령은 approved payload 를 요구
(operator_confirmed_live_runner·ungated fidelity probe 라우팅 0), expected_provider_calls int≥1, provider_list 가시
(federal_register + guardian/nyt as appropriate), news enforce_window True, output 경로는 gitignored root,
secret/PII 0(_assert_pii_safe 통과)·이 모듈은 network 를 부르지 않는다.
"""
from __future__ import annotations

import sys

from backend.app.tools.operator_live_command_pack import (
    OLC_NO_EVENT,
    OLC_PAYLOAD_PRESENT,
    OLC_READY,
    OPERATION_NAME,
    build_operator_live_command_pack,
    sanitized_operator_live_command_pack,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

_GITIGNORED_ROOTS = ("outputs/reviewer_batch/", "outputs/live_snapshots/", "ingestion/outputs/")

_DATE_PINNED_EVENT = {
    "named_entity": "US Supreme Court",
    "event_phrase": "asylum metering ruling",
    "occurrence_date": "2026-06-25",
}

_REQUIRED_KEYS = {
    "operation_name", "operator_live_command_pack_status", "validate_payload_command", "dry_run_command",
    "live_run_command", "expected_provider_calls", "provider_list", "news_enforce_window_noted",
    "rate_limit_notes", "output_paths", "gitignore_notes", "rollback_notes", "next_action",
}

_INVARIANTS = {
    "validate_only_calls_network": False,
    "dry_run_calls_live_network": False,
    "live_run_requires_approved_payload": True,
    "secret_in_command_pack": False,
    "raw_payload_text_in_pack": False,
    "routes_through_ungated_fidelity_probe": False,
    "actual_sending_performed": False,
    "merge_allowed": False,
    "production_gold_count": 0,
}


# ── contract: required keys + honesty invariants present ──
def test_required_keys_and_invariants_present():
    out = build_operator_live_command_pack()
    assert _REQUIRED_KEYS <= set(out)
    assert out["operation_name"] == OPERATION_NAME
    for k, v in _INVARIANTS.items():
        assert out[k] == v


# ── 16. validate-only command has no live flag / no network ──
def test_16_validate_only_no_live_flag_no_network():
    out = build_operator_live_command_pack()
    cmd = out["validate_payload_command"]
    assert "operator_regulatory_event_payload" in cmd
    assert "--live-query" not in cmd
    assert out["validate_only_calls_network"] is False


# ── 17. dry-run has no live network (no --live-query) — both paths ──
def test_17_dry_run_no_live_network_seed_path():
    out = build_operator_live_command_pack()
    assert "official_news_live_acquisition" in out["dry_run_command"]
    assert "--live-query" not in out["dry_run_command"]
    assert out["dry_run_calls_live_network"] is False


def test_17_dry_run_no_live_network_date_pinned_path():
    out = build_operator_live_command_pack(operator_event=_DATE_PINNED_EVENT)
    assert "live_query_target" in out["dry_run_command"]
    assert "--live-query" not in out["dry_run_command"]
    assert out["dry_run_calls_live_network"] is False


# ── 18. live command requires approved payload (approval-gated runner, not the ungated fidelity probe) ──
def test_18_live_command_requires_approved_payload():
    out = build_operator_live_command_pack()
    cmd = out["live_run_command"]
    assert ("--live-query" in cmd) or ("operator_confirmed_live_runner" in cmd)
    assert out["live_run_requires_approved_payload"] is True
    assert "provider_date_window_fidelity" not in cmd
    assert out["routes_through_ungated_fidelity_probe"] is False


# ── 19. expected_provider_calls visible and is an int ≥1 (and == len(provider_list)) — both paths ──
def test_19_expected_provider_calls_int_seed_path():
    out = build_operator_live_command_pack()
    n = out["expected_provider_calls"]
    assert isinstance(n, int) and not isinstance(n, bool)
    assert n >= 1
    assert n == len(out["provider_list"])
    assert n == 3   # federal_register + guardian + nyt


def test_19_expected_provider_calls_int_date_pinned_path():
    out = build_operator_live_command_pack(operator_event=_DATE_PINNED_EVENT)
    n = out["expected_provider_calls"]
    assert isinstance(n, int) and not isinstance(n, bool)
    assert n == len(out["provider_list"])
    assert n == 2   # guardian + second provider


# ── 20. provider_list visible (federal_register + guardian/nyt as appropriate) ──
def test_20_provider_list_seed_path_has_official_and_news():
    out = build_operator_live_command_pack()
    assert "federal_register" in out["provider_list"]
    assert "guardian" in out["provider_list"]
    assert "nyt" in out["provider_list"]


def test_20_provider_list_date_pinned_path_is_news():
    out = build_operator_live_command_pack(operator_event=_DATE_PINNED_EVENT)
    assert "guardian" in out["provider_list"]
    assert "nyt" in out["provider_list"]


# ── 21. news enforce_window noted True (bool + stated in next_action) ──
def test_21_news_enforce_window_noted_true():
    out = build_operator_live_command_pack()
    assert out["news_enforce_window_noted"] is True
    assert "enforce_window=True" in out["next_action"]


# ── 22. output paths are gitignored roots ──
def test_22_output_paths_are_gitignored_roots():
    out = build_operator_live_command_pack()
    paths = out["output_paths"]
    assert paths
    for v in paths.values():
        assert any(v.startswith(root) for root in _GITIGNORED_ROOTS), v


# ── 23. no secret / PII (recursive guard passes + no obvious secret tokens in the commands) ──
def test_23_no_secret_or_pii():
    out = build_operator_live_command_pack(operator_event=_DATE_PINNED_EVENT)
    _assert_pii_safe(out, _path="operator_live_command_pack_output")   # forbidden 키 어떤 depth 도 0.
    blob = " ".join([out["validate_payload_command"], out["dry_run_command"], out["live_run_command"]])
    for tok in ("API_KEY", "api_key", "secret", "password", "token="):
        assert tok not in blob
    assert out["secret_in_command_pack"] is False
    assert out["raw_payload_text_in_pack"] is False


# ── rate_limit_notes derived from adapter_descriptor (spacing not hardcoded) + operator pacing floor ──
def test_rate_limit_notes_from_adapter_descriptor():
    out = build_operator_live_command_pack()
    notes = out["rate_limit_notes"]
    for prov in ("federal_register", "guardian", "nyt"):
        assert prov in notes
        assert "min_spacing" in notes[prov]
    assert notes["operator_pacing_floor"] == "guardian≥6·nyt≥13 권장"


# ── status: no event + no real payload → template only ──
def test_status_no_event_template_only_when_no_payload():
    out = build_operator_live_command_pack(real_payload_path="definitely/not/here/payload.json")
    assert out["operator_live_command_pack_status"] == OLC_NO_EVENT


# ── status: no event + real payload file present → payload-present (existence stat only) ──
def test_status_payload_present_when_file_exists(tmp_path):
    p = tmp_path / "real_payload.json"
    p.write_text("{}", encoding="utf-8")
    out = build_operator_live_command_pack(real_payload_path=str(p))
    assert out["operator_live_command_pack_status"] == OLC_PAYLOAD_PRESENT


# ── status: date-pinned operator_event present → ready + valid verdict ──
def test_status_ready_when_operator_event_present():
    out = build_operator_live_command_pack(operator_event=_DATE_PINNED_EVENT)
    assert out["operator_live_command_pack_status"] == OLC_READY
    assert out["date_pinned_named_event_valid"] is True


# ── live/validate commands reference the real payload path + batch id ──
def test_commands_reference_real_payload_and_batch_id():
    out = build_operator_live_command_pack(real_payload_path="inputs/operator_events/x.json", batch_id="ops_demo")
    assert "inputs/operator_events/x.json" in out["validate_payload_command"]
    assert "inputs/operator_events/x.json" in out["live_run_command"]
    assert "--batch-id ops_demo" in out["live_run_command"]


# ── sanitized projection (frontier 용·명령 본문 제외) ──
def test_sanitized_projection_keys():
    out = build_operator_live_command_pack(operator_event=_DATE_PINNED_EVENT)
    s = sanitized_operator_live_command_pack(out)
    assert set(s.keys()) == {
        "operator_live_command_pack_status", "expected_provider_calls", "provider_list",
        "news_enforce_window_noted", "validate_only_calls_network", "dry_run_calls_live_network",
        "live_run_requires_approved_payload", "routes_through_ungated_fidelity_probe",
        "operator_live_command_pack_next_action",
    }
    assert "validate_payload_command" not in s
    assert "live_run_command" not in s


# ── this module never calls the network (no new http client loaded by build) ──
def test_pack_invokes_no_network():
    import backend.app.tools.operator_live_command_pack as mod

    http_clients = {"httpx", "requests", "aiohttp", "urllib3"}
    before = http_clients & set(sys.modules)
    build_operator_live_command_pack(operator_event=_DATE_PINNED_EVENT)
    build_operator_live_command_pack()
    after = http_clients & set(sys.modules)
    assert after == before, "build_operator_live_command_pack loaded an http client (network risk)"
    with open(mod.__file__, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "import httpx" not in text
    assert "import requests" not in text


def test_injected_payload_status_overrides_filesystem_stat():
    # ADR#93 read-API 결정론: operator_payload_status 가 주입되면 파일시스템(stat)을 보지 않고 그 status 로 판정한다.
    # 존재하지 않는 경로를 줘도 주입 status=present 면 OLC_PAYLOAD_PRESENT → stat 미사용(injection override) 증명.
    nonexistent = "inputs/operator_events/__does_not_exist__.json"
    present = build_operator_live_command_pack(
        real_payload_path=nonexistent, operator_payload_status="present_valid_json")
    assert present["operator_live_command_pack_status"] == OLC_PAYLOAD_PRESENT
    absent = build_operator_live_command_pack(
        real_payload_path=nonexistent, operator_payload_status="not_provided")
    assert absent["operator_live_command_pack_status"] == OLC_NO_EVENT
    # 주입 미사용(standalone CLI) → stat fallback: 존재하지 않는 경로 → OLC_NO_EVENT.
    cli = build_operator_live_command_pack(real_payload_path=nonexistent)
    assert cli["operator_live_command_pack_status"] == OLC_NO_EVENT
    _assert_pii_safe(present, _path="operator_live_command_pack_output")

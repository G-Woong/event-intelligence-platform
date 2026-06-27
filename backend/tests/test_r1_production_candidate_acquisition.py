"""ADR#76 — R1 live production candidate acquisition gate + production-candidate batch freeze 테스트.

§10 시나리오를 잠근다: actual input re-check / live acquisition 6-state / source role guard /
reviewer-facing safety / dual-track contract / no merge·LLM·DB·embedding·전송. 전부 결정론(주입 seam·network 0).
"""
from __future__ import annotations

import json

import backend.app.tools.r1_production_candidate_acquisition as mod
from backend.app.services.identity_human_labeling import SOURCE_LIVE, SOURCE_SYNTHETIC
from backend.app.tools.near_match_reviewer_queue import build_near_match_reviewer_queue
from backend.app.tools.r1_production_candidate_acquisition import (
    PCAND_BLOCKED_NO_CREDENTIALS,
    PCAND_BLOCKED_NO_LIVE_OPT_IN,
    PCAND_BLOCKED_NO_LIVE_OVERLAP,
    PCAND_BLOCKED_NO_PUBLISHABLE_PAIRS,
    PCAND_PRODUCTION_BATCH_FROZEN,
    REQUIRED_PRODUCTION_GOLD,
    _is_publishable_production_pair,
    run_r1_production_candidate_acquisition,
)
from backend.app.tools.reviewer_actual_input_gate import (
    INPUT_LABELS_IMPORTED,
    INPUT_NO_ACTUAL,
    INPUT_RETURNED_PRESENT,
)
from backend.app.tools.source_overlap_discovery import (
    build_captured_overlap_fixture,
    discover_overlap,
)

# ── 결정론 fixtures(주입 seam·network 0·실 `.env` 비의존) ───────────────────────────────────────────────


def _fake_gate(**over) -> dict:
    """완전한 actual input gate 결과(기본 no_actual_input). over 로 특정 축만 바꾼다."""
    base = {
        "operation_name": "reviewer_actual_input_gate",
        "batch_id": "b", "packet_id": "p",
        "input_directory": "outputs/reviewer_batch/b/intake",
        "input_directory_exists": False,
        "actual_contact_evidence_found": False,
        "actual_returned_labels_found": False,
        "contact_evidence_files": [], "returned_label_files": [],
        "actual_input_status": INPUT_NO_ACTUAL,
        "external_input_required": True,
        "returned_label_count": 0, "missing_label_count": 0, "invalid_label_count": 0,
        "conflict_pair_count": 0, "calibration_gap": None, "calibration_delta": None,
        "production_gold_count": 0, "synthetic_gold_count": 0,
        "calibration_ready": False, "merge_gate_ready": False,
        "public_truth_exposed": False, "same_event_truth_exposed": False, "raw_pii_exposed": False,
        "score_exposed": False, "rationale_exposed": False, "predicted_status_exposed": False,
        "actual_sending_performed": False, "no_public_intelligence_unit": True,
        "merge_allowed": False, "no_merge_without_gold": True,
        "db_write": False, "llm_invoked": False, "embedding_invoked": False,
        "block_reasons": ["external_reviewer_input_required"], "next_actions": ["collect labels"],
    }
    base.update(over)
    return base


def _gate_fn(**over):
    return lambda **kw: _fake_gate(**over)


def _readiness(*, ready: bool = True) -> dict:
    return {"credential_status": {"guardian": ready, "nyt": ready},
            "any_live_query_ready": ready, "key_required_ready": (["guardian", "nyt"] if ready else [])}


def _readiness_fn(*, ready: bool = True):
    return lambda: _readiness(ready=ready)


def _smoke(**over) -> dict:
    base = {
        "smoke_name": "cross_source_live_overlap", "live_query_requested": False,
        "live_query_attempted": False, "cross_source_pair_count": 0,
        "reviewer_queue": None, "dataset_source": None, "provenance": "none",
        "block_reasons": ["not_opted_in"], "next_actions": [],
    }
    base.update(over)
    # 실 smoke 는 양 provider ok(실 records)일 때 dataset_source/provenance 둘 다 live_derived 로 세운다 — 테스트도 일치.
    if "dataset_source" not in over:
        base["dataset_source"] = base["provenance"] if base["provenance"] != "none" else None
    return base


def _mixed_role_queue() -> dict:
    """publishable(article×article) 1 + 비-publishable(community×market) 1 — 가드가 배포 산출물까지 필터하는지 검증."""
    def row(pid, rid, lt, rt):
        return {"pair_id": pid, "reviewer_id": rid, "review_round": 1, "language": "en",
                "source_type_left": lt, "source_type_right": rt,
                "title_left": f"{pid} L", "title_right": f"{pid} R",
                "observed_at_left": "2026-06-22", "observed_at_right": "2026-06-22"}
    rows = [row("nm:pub", "rev_a", "article", "article"), row("nm:pub", "rev_b", "article", "article"),
            row("nm:bad", "rev_a", "community", "market"), row("nm:bad", "rev_b", "community", "market")]
    return {"packet_rows": rows, "near_positive_count": 2,
            "hard_negative_discovery_count": 0, "hard_negative_synthetic_count": 0,
            "queue_pair_ids": ["nm:pub", "nm:bad"]}


def _acquire_fn(smoke: dict):
    return lambda **kw: smoke


def _synth_stub(**over):
    base = {"batch_id": "reviewer_pilot_exec_001", "batch_frozen": True,
            "frozen_pair_count": 5, "pilot_batch_is_production_candidate": False}
    base.update(over)
    return lambda **kw: base


def _real_publishable_queue() -> dict:
    """실 chain 으로 만든 publishable(article) near-match queue — live 후보 stand-in(acquire_fn 으로 live_derived 태깅)."""
    disc = discover_overlap(build_captured_overlap_fixture())
    return build_near_match_reviewer_queue(disc, packet_id="test_live_pkt")


def _nonpub_queue() -> dict:
    """publishable 아님(community×market) — source role guard 가 거부해야 함."""
    rows = [
        {"pair_id": "nm:x", "reviewer_id": "rev_a", "review_round": 1, "language": "en",
         "source_type_left": "community", "source_type_right": "market",
         "title_left": "t1", "title_right": "t2",
         "observed_at_left": "2026-06-22", "observed_at_right": "2026-06-22"},
        {"pair_id": "nm:x", "reviewer_id": "rev_b", "review_round": 1, "language": "en",
         "source_type_left": "community", "source_type_right": "market",
         "title_left": "t1", "title_right": "t2",
         "observed_at_left": "2026-06-22", "observed_at_right": "2026-06-22"},
    ]
    return {"packet_rows": rows, "near_positive_count": 1,
            "hard_negative_discovery_count": 0, "hard_negative_synthetic_count": 0,
            "queue_pair_ids": ["nm:x"]}


def _run(*, live_query=False, smoke=None, ready=True, gate=None, synth=None):
    return run_r1_production_candidate_acquisition(
        live_query=live_query,
        acquire_fn=_acquire_fn(smoke if smoke is not None else _smoke()),
        readiness_fn=_readiness_fn(ready=ready),
        synthetic_batch_fn=synth or _synth_stub(),
        gate_fn=gate)


# ── §10 actual input re-check (1-4) ──────────────────────────────────────────────────────────────────────


def test_no_actual_files_external_input_required():
    out = _run()
    assert out["actual_input_rechecked"] is True
    assert out["actual_input_status"] == INPUT_NO_ACTUAL
    assert out["external_input_required"] is True
    assert out["returned_labels_take_precedence"] is False


def test_returned_labels_present_takes_precedence():
    out = _run(gate=_gate_fn(
        actual_input_status=INPUT_RETURNED_PRESENT, actual_returned_labels_found=True,
        returned_label_count=3, external_input_required=False))
    assert out["returned_labels_take_precedence"] is True
    # precedence next-action 이 맨 앞.
    assert "process them" in out["next_actions"][0].lower()


def test_labels_imported_also_takes_precedence():
    out = _run(gate=_gate_fn(
        actual_input_status=INPUT_LABELS_IMPORTED, actual_returned_labels_found=True,
        returned_label_count=5, production_gold_count=5))
    assert out["returned_labels_take_precedence"] is True


def test_production_gold_count_exact_passthrough():
    out = _run(gate=_gate_fn(production_gold_count=7, synthetic_gold_count=2))
    assert out["production_gold_count"] == 7
    assert out["synthetic_gold_count"] == 2
    assert out["current_r1_gap"] == REQUIRED_PRODUCTION_GOLD - 7


def test_no_generated_input_files():
    # tool 은 입력 파일을 만들지 않는다 — 게이트 passthrough 만(external_input_required 유지).
    out = _run()
    assert out["external_input_required"] is True
    assert out["actual_returned_labels_found"] is False


# ── §10 live production candidate acquisition (5-13) ──────────────────────────────────────────────────────


def test_missing_credentials_blocked():
    out = _run(live_query=True, ready=False,
               smoke=_smoke(live_query_requested=True, live_query_attempted=False,
                            block_reasons=["missing_credentials:guardian"]))
    assert out["production_candidate_status"] == PCAND_BLOCKED_NO_CREDENTIALS
    assert out["blocked_no_live_production_candidates"] is True
    assert out["production_candidate_batch_ready"] is False


def test_live_opt_in_disabled_blocked():
    out = _run(live_query=False, ready=True)   # creds present, opt-in off.
    assert out["production_candidate_status"] == PCAND_BLOCKED_NO_LIVE_OPT_IN
    assert out["live_call_performed"] is False
    assert out["live_call_opt_in_required"] is True


def test_live_call_no_overlap_blocked():
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_requested=True, live_query_attempted=True,
                            cross_source_pair_count=0, reviewer_queue={"packet_rows": []},
                            provenance="live_derived", block_reasons=["no_cross_source_overlap"]))
    assert out["production_candidate_status"] == PCAND_BLOCKED_NO_LIVE_OVERLAP
    assert out["production_candidate_batch_ready"] is False


def test_overlap_but_no_publishable_pairs_blocked():
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_requested=True, live_query_attempted=True,
                            cross_source_pair_count=1, reviewer_queue=_nonpub_queue(),
                            provenance="live_derived", block_reasons=[]))
    assert out["production_candidate_status"] == PCAND_BLOCKED_NO_PUBLISHABLE_PAIRS
    assert out["publishable_pair_count"] == 0
    assert out["production_candidate_batch_ready"] is False
    assert out["candidate_provenance"] == "none"   # 둔갑 0 — publishable 0 이면 live_derived 박제 안 함.


def test_live_publishable_pairs_freeze_production_batch():
    q = _real_publishable_queue()
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_requested=True, live_query_attempted=True,
                            cross_source_pair_count=len(q.get("queue_pair_ids") or []),
                            reviewer_queue=q, provenance="live_derived", block_reasons=[]))
    assert out["production_candidate_status"] == PCAND_PRODUCTION_BATCH_FROZEN
    assert out["production_candidate_batch_ready"] is True
    assert out["production_frozen_pair_count"] > 0
    assert out["ready_for_manual_launch"] is True
    assert out["production_batch_signature"].startswith("sha256:")


def test_production_batch_only_from_live_derived():
    q = _real_publishable_queue()
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_attempted=True, cross_source_pair_count=5,
                            reviewer_queue=q, provenance="live_derived", block_reasons=[]))
    assert out["candidate_provenance"] == SOURCE_LIVE   # "live_derived"


def test_production_batch_never_from_synthetic_fixture():
    # synthetic 트랙은 분리·항상 non-production. production 후보는 별도 axis.
    out = _run()
    assert out["synthetic_batch_not_production"] is True
    assert out["production_candidate_batch_ready"] is False
    assert SOURCE_SYNTHETIC != SOURCE_LIVE


def test_production_candidate_does_not_imply_same_event():
    q = _real_publishable_queue()
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_attempted=True, cross_source_pair_count=5,
                            reviewer_queue=q, provenance="live_derived"))
    assert out["same_event_truth_exposed"] is False
    for pair in out["production_frozen_pairs"]:
        assert "same_event" not in pair


def test_production_candidate_does_not_increase_gold():
    q = _real_publishable_queue()
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_attempted=True, cross_source_pair_count=5,
                            reviewer_queue=q, provenance="live_derived"),
               gate=_gate_fn(production_gold_count=0))
    assert out["production_candidate_batch_ready"] is True
    assert out["production_gold_count"] == 0   # freeze ≠ gold.


def test_credential_present_fetch_failed_not_mislabeled_as_no_credentials():
    # adversarial MEDIUM: opt-in + credential present 인데 fetch 가 비-credential 사유(rate_limit 등)로 실패 →
    # blocked_no_live_overlap(키 설정 오안내 금지)·blocked_no_credentials 아님.
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_requested=True, live_query_attempted=False,
                            cross_source_pair_count=0, block_reasons=["rate_limited"]))
    assert out["production_candidate_status"] == PCAND_BLOCKED_NO_LIVE_OVERLAP
    assert out["production_candidate_status"] != PCAND_BLOCKED_NO_CREDENTIALS


def test_freeze_requires_live_derived_dataset_source():
    # adversarial MEDIUM: live_query_attempted=True 라도 dataset_source 가 live_derived 아니면 freeze 차단(둔갑 방지).
    q = _real_publishable_queue()
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_attempted=True, cross_source_pair_count=5,
                            reviewer_queue=q, provenance="none", dataset_source=None))
    assert out["production_candidate_batch_ready"] is False
    assert out["candidate_provenance"] == "none"


def test_publishable_guard_filters_deployed_worklist():
    # adversarial MEDIUM: 혼합 큐(publishable+비publishable) → frozen·서명·배포 산출물 전부 publishable 만.
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_attempted=True, cross_source_pair_count=2,
                            reviewer_queue=_mixed_role_queue(), provenance="live_derived"))
    assert out["production_candidate_batch_ready"] is True
    assert out["publishable_pair_count"] == 1                      # nm:bad 제외.
    assert out["production_frozen_pair_count"] == 1
    pids = {p["pair_id"] for p in out["production_frozen_pairs"]}
    assert pids == {"nm:pub"}
    # 배포 산출물(checklist/expected files)도 비-publishable pair 흔적 없음.
    blob = json.dumps(out["operator_launch_checklist"], ensure_ascii=False)
    assert "nm:bad" not in blob and "community" not in blob and "market" not in blob


# ── §10 source role guard (14-19) ────────────────────────────────────────────────────────────────────────


def test_official_news_pairs_allowed():
    assert _is_publishable_production_pair({"source_role_a": "official", "source_role_b": "article"})
    assert _is_publishable_production_pair({"source_role_a": "news", "source_role_b": "news"})


def test_community_pair_rejected():
    assert not _is_publishable_production_pair({"source_role_a": "community", "source_role_b": "article"})


def test_market_pair_rejected():
    assert not _is_publishable_production_pair({"source_role_a": "market", "source_role_b": "official"})
    assert not _is_publishable_production_pair({"source_role_a": "signal", "source_role_b": "official"})


def test_catalog_pair_rejected():
    assert not _is_publishable_production_pair({"source_role_a": "catalog", "source_role_b": "article"})


def test_search_pair_rejected():
    assert not _is_publishable_production_pair({"source_role_a": "search", "source_role_b": "official"})


def test_unknown_role_rejected():
    assert not _is_publishable_production_pair({"source_role_a": "unknown", "source_role_b": "article"})
    assert not _is_publishable_production_pair({"source_role_a": "article", "source_role_b": "unknown"})


# ── §10 reviewer-facing safety (20-26) ───────────────────────────────────────────────────────────────────

_FORBIDDEN = {"score", "model_score", "rationale", "predicted_status", "raw_body", "body",
              "reviewer_name", "name", "email", "phone", "secret", "api_key", "hidden_rank"}


def _walk_keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk_keys(v)


def test_production_batch_has_no_forbidden_fields():
    q = _real_publishable_queue()
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_attempted=True, cross_source_pair_count=5,
                            reviewer_queue=q, provenance="live_derived"))
    keys = set(_walk_keys(out["production_frozen_pairs"]))
    assert keys.isdisjoint(_FORBIDDEN)
    assert out["operator_launch_checklist"] is not None
    ck = set(_walk_keys(out["operator_launch_checklist"]))
    assert ck.isdisjoint(_FORBIDDEN)


def test_whole_output_has_no_forbidden_fields():
    q = _real_publishable_queue()
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_attempted=True, cross_source_pair_count=5,
                            reviewer_queue=q, provenance="live_derived"))
    keys = set(_walk_keys(out))
    assert keys.isdisjoint(_FORBIDDEN)


def test_frozen_pairs_reviewer_safe_fields_only():
    q = _real_publishable_queue()
    out = _run(live_query=True, ready=True,
               smoke=_smoke(live_query_attempted=True, cross_source_pair_count=5,
                            reviewer_queue=q, provenance="live_derived"))
    for pair in out["production_frozen_pairs"]:
        assert set(pair).issubset({
            "pair_id", "source_role_a", "source_role_b", "title_a", "title_b",
            "observed_at_a", "observed_at_b", "language", "canonical_url_a", "canonical_url_b"})


# ── §7 dual-track contract / §10 no merge·LLM·DB (27-40) ─────────────────────────────────────────────────

_CONTRACT_KEYS = {
    "contract", "synthetic_dry_run_batch_ready", "synthetic_batch_not_production",
    "production_candidate_batch_ready", "production_candidate_status", "candidate_provenance",
    "live_call_performed", "live_candidate_count", "publishable_pair_count",
    "production_frozen_pair_count", "production_batch_id", "production_batch_signature",
    "ready_for_manual_launch", "blocked_no_live_production_candidates", "validation_command",
    "intake_directory", "r1_status", "production_gold_count", "required_production_gold_count",
    "current_r1_gap", "r2_r7_no_go", "next_manual_action", "flags",
}


def test_dual_track_contract_exact_key_whitelist():
    out = _run()
    c = out["r1_production_candidate_contract"]
    assert set(c) == _CONTRACT_KEYS
    assert c["synthetic_dry_run_batch_ready"] is True
    assert c["synthetic_batch_not_production"] is True
    assert c["production_candidate_batch_ready"] is False


def test_dual_track_contract_no_forbidden_fields():
    out = _run()
    keys = set(_walk_keys(out["r1_production_candidate_contract"]))
    assert keys.isdisjoint(_FORBIDDEN)
    # public truth/IU 도 contract 표면에 없음.
    assert "public_intelligence_unit" not in keys
    assert "same_event" not in keys


def test_no_merge_no_llm_no_db_no_embedding_no_send():
    out = _run()
    assert out["merge_allowed"] is False
    assert out["no_public_intelligence_unit"] is True
    assert out["db_write"] is False
    assert out["llm_invoked"] is False
    assert out["embedding_invoked"] is False
    assert out["actual_sending_performed"] is False
    assert out["r2_r7_no_go"] is True


def test_flags_all_safe():
    out = _run()
    f = out["r1_production_candidate_contract"]["flags"]
    assert f["no_merge"] and f["no_public_iu"] and f["pii_safe"] and f["no_llm"] and f["no_db_write"]
    assert f["gold_provenance_verified"] is False


def test_credential_presence_checked_secret_safe():
    out = _run()
    assert out["credential_presence_checked_secret_safe"] is True
    assert out["providers_checked"] == ["guardian", "nyt"]


# ── 결정적 signature(같은 입력=같은 signature·order-invariant) ────────────────────────────────────────────


def test_production_batch_signature_deterministic():
    q = _real_publishable_queue()
    kw = dict(live_query=True, ready=True,
              smoke=_smoke(live_query_attempted=True, cross_source_pair_count=5,
                           reviewer_queue=q, provenance="live_derived"))
    a = _run(**kw)
    b = _run(**kw)
    assert a["production_batch_signature"] == b["production_batch_signature"]
    assert a["production_batch_signature"] != ""


# ── synthetic 트랙 실제 통합(분리 보존) ──────────────────────────────────────────────────────────────────


def test_synthetic_track_real_integration_separated():
    # 실 run_r1_reviewer_pilot_batch 사용(synth 주입 없이) — synthetic dry-run 분리·non-production 보존.
    out = run_r1_production_candidate_acquisition(
        live_query=False,
        acquire_fn=_acquire_fn(_smoke()),
        readiness_fn=_readiness_fn(ready=True))
    assert out["synthetic_dry_run_batch_ready"] is True
    assert out["synthetic_batch_not_production"] is True
    assert out["production_candidate_batch_ready"] is False
    assert out["candidate_provenance"] == "none"


def test_operation_name():
    assert mod.OPERATION_NAME == "r1_production_candidate_acquisition"

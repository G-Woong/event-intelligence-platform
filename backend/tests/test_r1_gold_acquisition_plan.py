"""ADR#74 — R1 production gold acquisition operating plan 정책 lock 테스트.

검증: actual input 재확인(no_actual_input 정직)·R1 status(4-state)·target floor(canonical 200/50/2 + 파생
67/67/20)·gap 산술·operator next manual action·산출물 readiness·no merge/LLM/embedding/DB·forbidden 필드 0.
실 reviewer 라벨/contact evidence/전송 0(파일 생성 0). 단위(pure helper)는 합성 게이트 dict 로, 통합은 실 무입력
게이트로 검증한다.
"""
from __future__ import annotations

import pytest

from backend.app.services.identity_human_labeling import (
    DEFAULT_REVIEWERS_PER_PAIR,
    GOLD_MERGE_MIN_KOREAN_GOLD,
    GOLD_MERGE_MIN_LIVE_GOLD,
)
from backend.app.tools.r1_gold_acquisition_plan import (
    OPERATION_NAME,
    R1_BLOCKED_NO_LABELS,
    R1_COLLECTING,
    R1_PARTIALLY_SATISFIED,
    R1_SATISFIED,
    R1_STATES,
    REQUIRED_HARD_NEGATIVE,
    REQUIRED_KOREAN_GOLD,
    REQUIRED_NEGATIVE_GOLD,
    REQUIRED_POSITIVE_GOLD,
    REQUIRED_PRODUCTION_GOLD,
    REVIEWER_DUPLICATION_REQUIRED,
    _current_gold_breakdown,
    _r1_status,
    run_r1_gold_acquisition_plan,
)

_FORBIDDEN_KEY_SUBSTR = (
    "score", "rationale", "predicted_status", "raw_body", "reviewer_name",
    "email", "phone", "secret", "api_key", "hidden_rank",
)


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _walk_keys(x)


# ── target floor: canonical 재사용 + ADR#74 파생 ─────────────────────────────────────────────────────────
def test_required_floors_reuse_canonical_constants():
    # 200/50/2 는 재정의가 아니라 identity_human_labeling 단일 출처 재사용.
    assert REQUIRED_PRODUCTION_GOLD == GOLD_MERGE_MIN_LIVE_GOLD == 200
    assert REQUIRED_KOREAN_GOLD == GOLD_MERGE_MIN_KOREAN_GOLD == 50
    assert REVIEWER_DUPLICATION_REQUIRED == DEFAULT_REVIEWERS_PER_PAIR == 2


def test_derived_balance_and_hard_negative_floors():
    # balance 정책(ratio≥0.5)을 총량 200 에서 만족시키는 최소 class 표본 = ceil(200/3)=67.
    assert REQUIRED_POSITIVE_GOLD == REQUIRED_NEGATIVE_GOLD == 67
    # hard-negative evaluator floor(FP=0 의미있는 측정 표본).
    assert REQUIRED_HARD_NEGATIVE == 20


# ── _r1_status(4-state) 순수 로직 ───────────────────────────────────────────────────────────────────────
def test_r1_status_blocked_no_labels():
    assert _r1_status(returned_label_count=0, production_gold_count=0, calibration_ready=False) == R1_BLOCKED_NO_LABELS


def test_r1_status_collecting_below_floor():
    # 라벨은 들어오나 총량 floor 미달.
    assert _r1_status(returned_label_count=10, production_gold_count=30, calibration_ready=False) == R1_COLLECTING


def test_r1_status_partially_satisfied_floor_met_not_calibrated():
    # 총량 floor 충족이나 sub-floor(korean/balance) 미충족 → partially_satisfied.
    assert _r1_status(returned_label_count=400, production_gold_count=210, calibration_ready=False) == R1_PARTIALLY_SATISFIED


def test_r1_status_satisfied_when_calibration_ready():
    assert _r1_status(returned_label_count=500, production_gold_count=250, calibration_ready=True) == R1_SATISFIED


def test_r1_states_set_lock_and_membership():
    # state-set lock(드리프트 차단) + _r1_status 출력이 항상 선언된 4-state 안.
    assert R1_STATES == {R1_BLOCKED_NO_LABELS, R1_COLLECTING, R1_PARTIALLY_SATISFIED, R1_SATISFIED}
    for returned, gold, cal in [(0, 0, False), (5, 30, False), (400, 210, False), (500, 250, True)]:
        assert _r1_status(returned_label_count=returned, production_gold_count=gold, calibration_ready=cal) in R1_STATES


# ── _current_gold_breakdown: gold==0 invariant + delta 파생 + fail-loud ──────────────────────────────────
def test_current_breakdown_zero_when_no_gold():
    out = _current_gold_breakdown({"production_gold_count": 0})
    assert out == {"positive": 0, "negative": 0, "korean": 0, "hard_negative": 0}


def test_current_breakdown_from_delta_when_gold_present():
    fake_gate = {
        "production_gold_count": 120,
        "calibration_delta": {
            "before_production_gold_count": 0,
            "positive_delta": 70, "negative_delta": 50, "korean_delta": 30,
        },
    }
    out = _current_gold_breakdown(fake_gate)
    assert out["positive"] == 70 and out["negative"] == 50 and out["korean"] == 30
    # hard-negative gold 별도 surface 부재 — 정직 0.
    assert out["hard_negative"] == 0


def test_current_breakdown_fail_loud_on_nonzero_baseline():
    # baseline!=0 이면 delta==current 불변이 깨진 것 → fail-loud(조용한 오집계 차단).
    bad_gate = {
        "production_gold_count": 120,
        "calibration_delta": {"before_production_gold_count": 5, "positive_delta": 1, "negative_delta": 1, "korean_delta": 1},
    }
    with pytest.raises(ValueError):
        _current_gold_breakdown(bad_gate)


# ── 통합: 실 무입력 게이트(no_actual_input·gold 0) ──────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def plan():
    # 존재하지 않는 디렉터리 → 게이트가 빈 결과(생성 0·날조 0). 실 reviewer 라벨/전송 0.
    return run_r1_gold_acquisition_plan(directory="outputs/reviewer_batch/__nonexistent_adr74__/intake")


def test_operation_name(plan):
    assert plan["operation_name"] == OPERATION_NAME


def test_actual_input_rechecked_honest(plan):
    assert plan["actual_input_rechecked"] is True
    assert plan["actual_input_status"] == "no_actual_input"
    assert plan["external_input_required"] is True
    assert plan["actual_contact_evidence_found"] is False
    assert plan["actual_returned_labels_found"] is False


def test_r1_status_blocked_when_no_labels(plan):
    assert plan["r1_status"] == R1_BLOCKED_NO_LABELS


def test_production_gold_zero_passthrough(plan):
    # production_gold_count 는 게이트 exact passthrough — plan 만으로 증가 0.
    assert plan["current_production_gold_count"] == 0
    assert plan["production_gold_count"] == 0


def test_targets_reported(plan):
    assert plan["required_production_gold_count"] == 200
    assert plan["required_korean_gold_count"] == 50
    assert plan["required_positive_gold_count"] == 67
    assert plan["required_negative_gold_count"] == 67
    assert plan["required_hard_negative_count"] == 20


def test_gaps_full_when_gold_zero(plan):
    # gold 0 → 모든 gap == 전체 target(둔갑 0).
    assert plan["label_collection_gap"] == 200
    assert plan["korean_gap"] == 50
    assert plan["positive_gap"] == 67
    assert plan["negative_gap"] == 67
    assert plan["hard_negative_gap"] == 20
    assert plan["reviewer_gap"] == 2


def test_reviewer_requirements(plan):
    assert plan["reviewer_count_required"] == 2
    assert plan["reviewer_duplication_required"] == 2
    assert plan["reviewer_agreement_required"] is True
    assert plan["conflict_adjudication_required"] is True
    # current_reviewer_count = global engaged(contact evidence)·무입력→0(per-pair coverage 주장 아님·adversarial #10).
    assert plan["current_reviewer_count"] == 0
    assert plan["r1_contract"]["current_reviewer_count"] == 0


def test_next_manual_actions_emitted(plan):
    actions = plan["next_manual_actions"]
    assert isinstance(actions, list) and len(actions) >= 4
    joined = " ".join(actions).lower()
    assert "recruit" in joined           # reviewer recruitment
    assert "adjudication" in joined      # human-only conflict adjudication
    assert "gitignored" in joined        # placement guide


def test_readiness_surfaces(plan):
    assert plan["contact_evidence_template_ready"] is True
    assert plan["returned_label_template_ready"] is True
    assert plan["returned_label_placement_guide_ready"] is True
    assert plan["internal_ops_r1_gap_visible"] is True
    assert plan["source_storage_strategy_updated"] is True


def test_no_merge_no_llm_no_embedding_no_db(plan):
    assert plan["merge_allowed"] is False
    assert plan["llm_invoked"] is False
    assert plan["embedding_invoked"] is False
    assert plan["db_write"] is False
    assert plan["no_public_intelligence_unit"] is True


def test_no_public_truth_and_no_forbidden_exposure(plan):
    assert plan["public_truth_exposed"] is False
    assert plan["same_event_truth_exposed"] is False
    assert plan["score_exposed"] is False
    assert plan["rationale_exposed"] is False
    assert plan["predicted_status_exposed"] is False
    assert plan["raw_pii_exposed"] is False
    assert plan["raw_source_body_exposed"] is False


def test_no_forbidden_keys_anywhere(plan):
    keys = [k.lower() for k in _walk_keys(plan)]
    for k in keys:
        for bad in _FORBIDDEN_KEY_SUBSTR:
            # 화이트리스트 예외: *_exposed 플래그는 노출이 아니라 '노출 안 함'을 단언하는 불리언.
            if bad in k and not k.endswith("_exposed"):
                raise AssertionError(f"forbidden key substring {bad!r} in output key {k!r}")


def test_merge_gate_not_forced_true(plan):
    assert plan["calibration_ready"] is False
    assert plan["merge_gate_ready"] is False


def test_r1_contract_sanitized_subset(plan):
    c = plan["r1_contract"]
    assert c["contract"] == "InternalOpsR1AcquisitionStatus"
    assert c["r1_status"] == R1_BLOCKED_NO_LABELS
    assert c["current_production_gold_count"] == 0
    assert c["required_production_gold_count"] == 200
    # flags 가 internal/no-public-truth/no-merge 강제.
    f = c["flags"]
    assert f["internal_only"] is True and f["no_public_truth"] is True and f["no_merge"] is True
    assert f["no_public_iu"] is True and f["no_llm"] is True and f["no_db_write"] is True
    # contract 표면에 forbidden 키 0.
    keys = [k.lower() for k in _walk_keys(c)]
    assert not any(("score" in k or "rationale" in k or "predicted_status" in k) for k in keys)

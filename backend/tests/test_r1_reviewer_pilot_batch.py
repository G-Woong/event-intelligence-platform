"""ADR#75 — R1 first reviewer pilot batch freeze + operator launch handoff 테스트(§10 시나리오).

정책을 잠근다: actual input 재확인(no_actual_input 정직)·frozen pilot batch(deterministic signature·합성
provenance 둔갑 0)·operator launch package·launch readiness·no merge/LLM/embedding/DB/전송. frozen batch 가
production_gold_count 를 늘리지 않고 same_event 를 함의하지 않음을 검증.
"""
from __future__ import annotations

from backend.app.services.identity_human_labeling import SOURCE_LIVE, SOURCE_SYNTHETIC
from backend.app.tools.r1_gold_acquisition_plan import REQUIRED_PRODUCTION_GOLD
from backend.app.tools.r1_reviewer_pilot_batch import (
    LAUNCH_AWAITING_MANUAL,
    LAUNCH_AWAITING_RETURNED,
    LAUNCH_BLOCKED_NO_CANDIDATES,
    LAUNCH_LABELS_PRESENT,
    LAUNCH_READY_FOR_MANUAL,
    LAUNCH_STATES,
    OPERATION_NAME,
    PROVENANCE_SYNTHETIC_FIXTURE,
    _batch_signature,
    _frozen_pair_list,
    _launch_status,
    run_r1_reviewer_pilot_batch,
)
from backend.app.tools.reviewer_actual_input_gate import (
    INPUT_CONTACT_ONLY,
    INPUT_INVALID_RETURNED,
    INPUT_LABELS_IMPORTED,
    INPUT_NO_ACTUAL,
    INPUT_RETURNED_PRESENT,
)
from backend.app.tools.reviewer_pilot_handoff import _HANDOFF_FORBIDDEN_KEYS

# forbidden 키(labeler-facing/ops contract 어떤 depth 에도 0). backend `_HANDOFF_FORBIDDEN_KEYS` 와 동일 벡터.
_FORBIDDEN = {
    "score", "model_score", "rationale", "predicted_status", "same_event", "raw_body", "body",
    "reviewer_name", "name", "email", "phone", "secret", "api_key", "provider_secret",
    "hidden_rank", "source_hidden_rank",
}


def _walk_keys(obj) -> set:
    found: set = set()
    if isinstance(obj, dict):
        found |= set(obj)
        for v in obj.values():
            found |= _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _walk_keys(v)
    return found


def _run(tmp_path, **kw):
    """hermetic: 존재하지 않는 intake dir 을 넘겨 no_actual_input 을 보장(outputs/ 상태 비의존)."""
    directory = kw.pop("directory", str(tmp_path / "intake"))
    return run_r1_reviewer_pilot_batch(directory=directory, **kw)


# ── §10.1 actual input re-check ───────────────────────────────────────────────────────────────────────────
def test_no_actual_input_external_required(tmp_path):
    out = _run(tmp_path)
    assert out["operation_name"] == OPERATION_NAME
    assert out["actual_input_rechecked"] is True
    assert out["actual_input_status"] == INPUT_NO_ACTUAL
    assert out["actual_returned_labels_found"] is False
    assert out["actual_contact_evidence_found"] is False
    assert out["external_input_required"] is True
    assert out["r1_status"] == "blocked_no_labels"


def test_production_gold_count_exact_passthrough_zero(tmp_path):
    out = _run(tmp_path)
    assert out["production_gold_count"] == 0
    assert out["returned_label_count"] == 0
    assert out["calibration_ready"] is False
    assert out["merge_gate_ready"] is False
    assert out["current_r1_gap"] == REQUIRED_PRODUCTION_GOLD


def test_no_generated_input_files(tmp_path):
    intake = tmp_path / "intake"
    _run(tmp_path)
    # 게이트는 스캔만 — 디렉터리/파일을 생성하지 않는다(날조 0).
    assert not intake.exists()


# ── §10.2 pilot batch freeze ──────────────────────────────────────────────────────────────────────────────
def test_candidate_pairs_produce_frozen_batch(tmp_path):
    out = _run(tmp_path)
    assert out["batch_frozen"] is True
    assert out["frozen_pair_count"] == 5          # captured fixture → 5 near-match distinct pairs.
    assert len(out["frozen_pairs"]) == 5
    assert out["batch_signature"].startswith("sha256:")


def test_deterministic_batch_signature_stable(tmp_path):
    a = _run(tmp_path)
    b = _run(tmp_path)
    assert a["batch_signature"] == b["batch_signature"]   # 같은 입력=같은 signature.


def test_batch_signature_excludes_pii_scores(tmp_path):
    out = _run(tmp_path)
    # signature 입력 canon 은 pair 정체성만 — frozen_pairs 에 forbidden 키 0(아래 safety 와 중복 방어).
    assert not (_walk_keys(out["frozen_pairs"]) & _FORBIDDEN)


def test_batch_signature_sensitive_to_batch_id_and_provenance(tmp_path):
    pairs = _run(tmp_path)["frozen_pairs"]
    base = _batch_signature(pairs, batch_id="b1", target_pair_count=200, reviewers_per_pair=2,
                            provenance=PROVENANCE_SYNTHETIC_FIXTURE)
    other_id = _batch_signature(pairs, batch_id="b2", target_pair_count=200, reviewers_per_pair=2,
                                provenance=PROVENANCE_SYNTHETIC_FIXTURE)
    other_prov = _batch_signature(pairs, batch_id="b1", target_pair_count=200, reviewers_per_pair=2,
                                  provenance="live_source_overlap")
    assert base != other_id
    assert base != other_prov


def test_batch_signature_sensitive_to_reviewers_per_pair(tmp_path):
    # code-review NIT: reviewers_per_pair 도 canon 에 포함 — 바뀌면 signature 도 바뀐다.
    pairs = _run(tmp_path)["frozen_pairs"]
    a = _batch_signature(pairs, batch_id="b1", target_pair_count=200, reviewers_per_pair=2,
                         provenance=PROVENANCE_SYNTHETIC_FIXTURE)
    b = _batch_signature(pairs, batch_id="b1", target_pair_count=200, reviewers_per_pair=3,
                         provenance=PROVENANCE_SYNTHETIC_FIXTURE)
    assert a != b


def test_frozen_pair_list_order_invariant_signature():
    # code-review NIT: _frozen_pair_list 가 pair_id 정렬→입력 순서 무관·같은 signature(order-invariance 직접 검증).
    def _row(pid, lang):
        return {"pair_id": pid, "reviewer_id": "r_a", "review_round": 1, "label": "", "label_confidence": "",
                "reviewed_at": "", "language": lang, "source_type_left": "article", "source_type_right": "community",
                "title_left": "L", "title_right": "R", "observed_at_left": "2026-06-22",
                "observed_at_right": "2026-06-22", "dataset_source": "synthetic"}
    fwd = [_row("p1", "en"), _row("p2", "ko"), _row("p3", "en")]
    rev = list(reversed(fwd))
    assert _frozen_pair_list(fwd) == _frozen_pair_list(rev)

    def sig(t):
        return _batch_signature(_frozen_pair_list(t), batch_id="b", target_pair_count=200,
                                reviewers_per_pair=2, provenance=PROVENANCE_SYNTHETIC_FIXTURE)
    assert sig(fwd) == sig(rev)


def test_frozen_pair_list_sorted_and_deduped(tmp_path):
    out = _run(tmp_path)
    pids = [p["pair_id"] for p in out["frozen_pairs"]]
    assert pids == sorted(pids)
    assert len(pids) == len(set(pids))            # dedupe(pair 당 1행·reviewer 행 병합).


def test_frozen_batch_does_not_increase_production_gold(tmp_path):
    out = _run(tmp_path)
    # frozen 5 pairs 이지만 production gold 는 0(freeze ≠ 라벨·gold).
    assert out["batch_frozen"] is True
    assert out["frozen_pair_count"] == 5
    assert out["production_gold_count"] == 0


def test_frozen_batch_does_not_imply_same_event_truth(tmp_path):
    out = _run(tmp_path)
    assert out["same_event_truth_exposed"] is False
    assert out["public_truth_exposed"] is False
    # frozen_pairs 어디에도 same_event/truth 판정 필드 없음.
    assert "same_event" not in _walk_keys(out["frozen_pairs"])


def test_synthetic_fixture_not_production_candidate(tmp_path):
    out = _run(tmp_path)
    assert out["candidate_provenance"] == PROVENANCE_SYNTHETIC_FIXTURE
    assert out["pilot_batch_is_production_candidate"] is False
    assert "synthetic_fixture_only_no_production_candidates" in out["block_reasons"]


def test_frozen_template_tagged_synthetic_not_live(tmp_path):
    # adversarial HIGH-1: 회수 라벨이 production gold(=production AND live_derived)로 둔갑하지 못하게 template 을
    # synthetic 으로 태깅 — machinery 강제(선언 아님). live_derived 면 거짓 보호.
    out = _run(tmp_path)
    assert out["frozen_label_dataset_source"] == SOURCE_SYNTHETIC
    assert out["frozen_label_dataset_source"] != SOURCE_LIVE


def test_synthetic_dry_run_hardstop_first(tmp_path):
    # adversarial MEDIUM-1: 합성 batch 는 dry-run only·production gold 수집 금지 hard-stop 이 next_action/checklist 맨 앞.
    out = _run(tmp_path)
    cl = out["operator_launch_checklist"]
    assert cl["dry_run_only"] is True
    assert "production gold" in cl["no_go_warnings"][0]
    assert "dry-run" in cl["no_go_warnings"][0].lower()
    assert "SYNTHETIC" in out["next_actions"][0]
    assert "do not collect production gold" in out["next_actions"][0].lower()


def test_pilot_n_below_r1_target(tmp_path):
    out = _run(tmp_path)
    assert out["target_pair_count"] == REQUIRED_PRODUCTION_GOLD   # 200 floor proxy.
    assert out["frozen_pair_count"] < out["target_pair_count"]    # pilot_n << target.
    assert out["r1_status"] != "satisfied"


# ── §10.3 reviewer-facing safety ──────────────────────────────────────────────────────────────────────────
def test_frozen_pairs_have_no_forbidden_fields(tmp_path):
    out = _run(tmp_path)
    keys = _walk_keys(out["frozen_pairs"])
    assert not (keys & _FORBIDDEN)
    # 허용 필드만(source_role/title/url/observed_at/language·pair_id).
    assert {"pair_id", "source_role_a", "source_role_b", "title_a", "title_b", "language"} <= keys


def test_whole_output_has_no_forbidden_fields(tmp_path):
    out = _run(tmp_path)
    # 전체 output 은 코드가 강제하는 `_assert_pii_safe`(=_HANDOFF_FORBIDDEN_KEYS) 벡터로 검사 — reviewer
    # instruction 의 라벨 어휘 키 same_event/different_event 는 truth 가 아니라 정당(handoff set 비대상).
    assert not (_walk_keys(out) & _HANDOFF_FORBIDDEN_KEYS)


def test_score_rationale_predicted_not_exposed(tmp_path):
    out = _run(tmp_path)
    assert out["score_exposed"] is False
    assert out["rationale_exposed"] is False
    assert out["predicted_status_exposed"] is False
    assert out["raw_pii_exposed"] is False
    assert out["raw_source_body_exposed"] is False


# ── §10.4 operator launch package ─────────────────────────────────────────────────────────────────────────
def test_launch_package_ready(tmp_path):
    out = _run(tmp_path)
    assert out["reviewer_instruction_ready"] is True
    assert out["label_template_ready"] is True
    assert out["placement_guide_ready"] is True
    assert out["operator_launch_checklist_ready"] is True


def test_expected_label_files_emitted_and_consistent(tmp_path):
    out = _run(tmp_path)
    assert out["expected_label_file_count"] == len(out["expected_label_files"])
    assert out["expected_label_file_count"] == 2          # reviewer_pool_slot_a/b.
    for fn in out["expected_label_files"]:
        assert fn.endswith("__labels.jsonl")
        assert out["batch_id"] in fn


def test_intake_directory_consistent_with_validation_command(tmp_path):
    out = _run(tmp_path)
    intake_dir = out["intake_directory"]
    # 게이트 스캔 경로 == intake plan 경로 == validation command 인자 == placement(단일 경로 수렴·Q8).
    assert intake_dir in out["validation_command"]
    assert out["operator_launch_checklist"]["validation_command"] == out["validation_command"]
    assert intake_dir in out["operator_launch_checklist"]["placement_guide"]
    # expected label files 는 batch-id 로 명명(directory 무관).
    for fn in out["expected_label_files"]:
        assert out["batch_id"] in fn


def test_canonical_intake_directory_contains_batch_id():
    # production 기본(directory=None) → canonical 경로가 batch_id 를 포함(상대경로·마스킹 없음).
    out = run_r1_reviewer_pilot_batch(directory="outputs/reviewer_batch/_adr75_doc_example/intake",
                                      batch_id="_adr75_doc_example")
    assert "_adr75_doc_example" in out["intake_directory"]
    assert out["intake_directory"] in out["validation_command"]


def test_manual_only_and_no_sending(tmp_path):
    out = _run(tmp_path)
    assert out["actual_sending_performed"] is False
    cl = out["operator_launch_checklist"]
    assert "manual" in cl["manual_only_contact_instruction"].lower()
    assert cl["pii_secret_forbidden_reminder"]
    assert any("not event truth" in w for w in cl["no_go_warnings"])


def test_no_generated_contact_evidence_or_labels(tmp_path):
    out = _run(tmp_path)
    # checklist 는 명세일 뿐 — 실제 contact evidence/label 파일을 만들지 않는다(전송 0·생성 0).
    assert out["actual_contact_evidence_found"] is False
    assert out["actual_returned_labels_found"] is False
    assert out["returned_label_count"] == 0


# ── §10.5 internal ops launch readiness contract ──────────────────────────────────────────────────────────
def test_contract_exposes_launch_readiness(tmp_path):
    c = _run(tmp_path)["r1_pilot_batch_contract"]
    assert c["contract"] == "InternalOpsR1PilotBatchStatus"
    assert c["launch_status"] in LAUNCH_STATES
    assert c["batch_frozen"] is True
    assert c["frozen_pair_count"] == 5
    assert c["expected_label_file_count"] == 2
    assert c["returned_labels_found"] is False
    assert c["validation_command"]
    assert c["r2_r7_no_go"] is True
    assert c["current_r1_gap"] == REQUIRED_PRODUCTION_GOLD
    assert c["candidate_provenance"] == PROVENANCE_SYNTHETIC_FIXTURE
    assert c["pilot_batch_is_production_candidate"] is False


def test_contract_is_sanitized_subset(tmp_path):
    c = _run(tmp_path)["r1_pilot_batch_contract"]
    assert not (_walk_keys(c) & _FORBIDDEN)
    expected_keys = {
        "contract", "pilot_batch_id", "batch_frozen", "batch_signature", "candidate_provenance",
        "pilot_batch_is_production_candidate", "frozen_pair_count", "target_pair_count",
        "expected_label_file_count", "launch_status", "ready_for_manual_launch", "returned_labels_found",
        "returned_label_count", "intake_directory", "validation_command", "r1_status",
        "production_gold_count", "required_production_gold_count", "current_r1_gap", "r2_r7_no_go",
        "next_manual_action", "flags",
    }
    assert set(c) == expected_keys
    assert set(c["flags"]) == {
        "internal_only", "no_public_truth", "no_merge", "no_public_iu", "pii_safe",
        "no_llm", "no_db_write", "gold_provenance_verified",
    }


# ── §10.6 no merge / no LLM / no DB ───────────────────────────────────────────────────────────────────────
def test_no_merge_no_llm_no_db_no_embedding(tmp_path):
    out = _run(tmp_path)
    assert out["merge_allowed"] is False
    assert out["no_public_intelligence_unit"] is True
    assert out["db_write"] is False
    assert out["llm_invoked"] is False
    assert out["embedding_invoked"] is False


def test_merge_gate_not_forced_true(tmp_path):
    out = _run(tmp_path)
    assert out["merge_gate_ready"] is False
    assert out["r2_r7_no_go"] is True


# ── launch_status state machine(unit) ─────────────────────────────────────────────────────────────────────
def test_launch_states_set_lock():
    assert LAUNCH_STATES == {
        LAUNCH_BLOCKED_NO_CANDIDATES, LAUNCH_READY_FOR_MANUAL, LAUNCH_AWAITING_MANUAL,
        LAUNCH_AWAITING_RETURNED, LAUNCH_LABELS_PRESENT,
    }


def test_launch_status_blocked_no_candidates():
    assert _launch_status(frozen_pair_count=0, actual_input_status=INPUT_NO_ACTUAL,
                          returned_label_count=0, dir_exists=False, contact_found=False) == LAUNCH_BLOCKED_NO_CANDIDATES


def test_launch_status_ready_for_manual():
    assert _launch_status(frozen_pair_count=5, actual_input_status=INPUT_NO_ACTUAL,
                          returned_label_count=0, dir_exists=False, contact_found=False) == LAUNCH_READY_FOR_MANUAL


def test_launch_status_awaiting_manual_when_dir_exists():
    assert _launch_status(frozen_pair_count=5, actual_input_status=INPUT_NO_ACTUAL,
                          returned_label_count=0, dir_exists=True, contact_found=False) == LAUNCH_AWAITING_MANUAL


def test_launch_status_awaiting_returned_on_contact_or_invalid():
    assert _launch_status(frozen_pair_count=5, actual_input_status=INPUT_CONTACT_ONLY,
                          returned_label_count=0, dir_exists=True, contact_found=True) == LAUNCH_AWAITING_RETURNED
    assert _launch_status(frozen_pair_count=5, actual_input_status=INPUT_INVALID_RETURNED,
                          returned_label_count=0, dir_exists=True, contact_found=False) == LAUNCH_AWAITING_RETURNED


def test_launch_status_labels_present():
    assert _launch_status(frozen_pair_count=5, actual_input_status=INPUT_RETURNED_PRESENT,
                          returned_label_count=3, dir_exists=True, contact_found=True) == LAUNCH_LABELS_PRESENT
    assert _launch_status(frozen_pair_count=5, actual_input_status=INPUT_LABELS_IMPORTED,
                          returned_label_count=9, dir_exists=True, contact_found=True) == LAUNCH_LABELS_PRESENT


# ── _frozen_pair_list unit ────────────────────────────────────────────────────────────────────────────────
def test_frozen_pair_list_dedupes_reviewer_rows():
    template = [
        {"pair_id": "p2", "reviewer_id": "r_b", "review_round": 1, "label": "", "label_confidence": "",
         "reviewed_at": "", "language": "en", "source_type_left": "article", "source_type_right": "community",
         "title_left": "L2", "title_right": "R2", "observed_at_left": "2026-06-22",
         "observed_at_right": "2026-06-22", "dataset_source": "live_derived"},
        {"pair_id": "p1", "reviewer_id": "r_a", "review_round": 1, "label": "", "label_confidence": "",
         "reviewed_at": "", "language": "ko", "source_type_left": "official", "source_type_right": "article",
         "title_left": "L1", "title_right": "R1", "observed_at_left": "2026-06-21",
         "observed_at_right": "2026-06-21", "dataset_source": "live_derived",
         "canonical_url_left": "https://a", "canonical_url_right": "https://b"},
        {"pair_id": "p1", "reviewer_id": "r_b", "review_round": 1, "label": "", "label_confidence": "",
         "reviewed_at": "", "language": "ko", "source_type_left": "official", "source_type_right": "article",
         "title_left": "L1", "title_right": "R1", "observed_at_left": "2026-06-21",
         "observed_at_right": "2026-06-21", "dataset_source": "live_derived"},
    ]
    pairs = _frozen_pair_list(template)
    assert [p["pair_id"] for p in pairs] == ["p1", "p2"]   # dedupe + sort.
    assert pairs[0]["source_role_a"] == "official"
    assert pairs[0]["canonical_url_a"] == "https://a"
    assert "reviewer_id" not in pairs[0]                    # reviewer-specific 칸 제거.
    assert "label" not in pairs[0]

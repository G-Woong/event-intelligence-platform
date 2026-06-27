"""ADR#76 — R1 live production candidate acquisition gate + production-candidate batch readiness (병합 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0).

ADR#75 가 만든 것: 결정적·오프라인 **합성** fixture 로 첫 reviewer pilot batch 를 동결(freeze→handoff→validation
machinery 증명). 그러나 그것은 dry-run artifact 다 — `candidate_provenance=synthetic_fixture`·
`pilot_batch_is_production_candidate=False`. R1 production gold 의 실제 시작점은 **합성 batch 가 아니라
live-derived production candidate** 다. "합성 batch 가 있으니 R1 라벨링이 시작됐다"는 착각의 자리가 남는다
(R-SyntheticProductionContamination / R-ProductionCandidateScarcity).

이 모듈은 **재구현이 아니라 acquisition gate + 조건부 production freeze orchestrator** 다(무거운 일은 단일 출처가 한다):
  - actual input 재확인(Lane A·production_gold_count exact passthrough): `reviewer_actual_input_gate.run_actual_input_gate`.
  - **live 후보 획득(Lane B·opt-in·secret-safe)**: `cross_source_live_overlap_smoke.run_cross_source_live_overlap_smoke`
    (Guardian×NYT adapter·`live_query` opt-in·`probe_env_var` present/missing 만·실 HTTP 는 transport=None+opt-in 일
    때만). credential presence 는 `provider_readiness.build_provider_readiness_report`(network 0·값 0).
  - **production-candidate freeze(Lane B·live-derived 만)**: live publishable×publishable 후보가 있을 때만
    `reviewer_batch_launch` / `reviewer_pilot_handoff` 순수 builder 로 동결(template `dataset_source=live_derived`).
    freeze 식별/checklist 는 ADR#75 `_frozen_pair_list`·`_batch_signature`·`build_operator_launch_checklist` 재사용.
  - **synthetic dry-run track(Lane C·분리 표시)**: `r1_reviewer_pilot_batch.run_r1_reviewer_pilot_batch` 1회 호출로
    합성 batch ready 상태만 인용(production 과 **구조적으로 분리**).
  - R1 status/floor: `r1_gold_acquisition_plan._r1_status` + `REQUIRED_PRODUCTION_GOLD`(canonical 재사용).
  - PII 재귀 가드: `reviewer_pilot_handoff._assert_pii_safe`.

이 모듈이 **새로** 더하는 것(기존에 없던 운영 결손):
  - **6-state production_candidate_status(§4)**: blocked_no_credentials / blocked_no_live_opt_in /
    blocked_no_live_overlap / blocked_no_publishable_pairs / live_candidates_found / production_batch_frozen —
    합성을 production 으로 둔갑시키지 않고 실 후보 확보 여부를 정직하게 분해.
  - **source role guard(§8)**: production candidate 는 publishable×publishable(official/article/news)만.
    community/market/signal/catalog/search/unknown 은 anchor 거부(`_is_publishable_production_pair`·fail-closed).
  - **dual-track internal ops contract(§7)**: synthetic dry-run batch 와 live production-candidate batch 를 명확히
    분리(synthetic_dry_run_batch_ready / synthetic_batch_not_production vs production_candidate_batch_ready /
    candidate_provenance / production_candidate_status). same_event truth·score·rationale·predicted_status·raw
    body·PII 는 contract 에 필드 자체가 없다(구조적 미노출).

절대 불변(상속·상용 안전 계약):
  - **합성→production 둔갑 0**: production_candidate_batch 는 `candidate_provenance=live_derived` **AND**
    live_call_performed **AND** publishable×publishable frozen pair ≥1 일 때만 True. 합성 fixture 는 절대 불가.
  - **freeze ≠ truth·≠ 라벨 생성·≠ gold**: production candidate 도 reviewer worklist 동결이지 same_event 확정이
    아니다. production_gold_count 를 늘리지 않는다(actual input gate passthrough 만).
  - **live call opt-in·secret-safe**: 기본 live_query=False → 시도 0. `.env` **값 미열람**(present/missing boolean 만).
  - **no merge / no public IU / no DB / no LLM / no embedding / no 전송 / no secret read**: 전 경로 상속.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Optional

from backend.app.services.identity_human_labeling import (
    DEFAULT_REVIEWERS_PER_PAIR,
    SOURCE_LIVE,
)
from backend.app.tools.cross_source_live_overlap_smoke import (
    _DEFAULT_PROVIDER_B,
    _PROVIDER_A,
    run_cross_source_live_overlap_smoke,
)
from backend.app.tools.provider_readiness import build_provider_readiness_report
from backend.app.tools.r1_gold_acquisition_plan import (
    REQUIRED_PRODUCTION_GOLD,
    _r1_status,
)
from backend.app.tools.r1_reviewer_pilot_batch import (
    _batch_signature,
    _frozen_pair_list,
    build_operator_launch_checklist,
    run_r1_reviewer_pilot_batch,
)
from backend.app.tools.reviewer_actual_input_gate import (
    INPUT_LABELS_IMPORTED,
    INPUT_RETURNED_PRESENT,
    run_actual_input_gate,
)
from backend.app.tools.reviewer_batch_launch import (
    build_assignment_manifest,
    build_intake_plan,
    build_label_template,
    build_reviewer_instruction,
)
from backend.app.tools.reviewer_pilot_handoff import (
    _assert_pii_safe,
    build_pilot_handoff_bundle,
)

OPERATION_NAME = "r1_production_candidate_acquisition"
PROD_BATCH_ID = "reviewer_prod_cand_001"

# ── §4 production_candidate_status(6-state·acquisition 분해) ───────────────────────────────────────────────
# blocked_no_credentials: cross-source provider credential 부재(opt-in 무의미 — 키 먼저). blocked_no_live_opt_in:
# credential present 이나 live opt-in off(시도 0). blocked_no_live_overlap: 실 call 했으나 cross-source overlap 0.
# blocked_no_publishable_pairs: overlap 있으나 publishable×publishable 후보 0(community/market/catalog/search anchor 거부).
# live_candidates_found: publishable live 후보 확보(freeze 직전). production_batch_frozen: live-derived batch 동결.
PCAND_BLOCKED_NO_CREDENTIALS = "blocked_no_credentials"
PCAND_BLOCKED_NO_LIVE_OPT_IN = "blocked_no_live_opt_in"
PCAND_BLOCKED_NO_LIVE_OVERLAP = "blocked_no_live_overlap"
PCAND_BLOCKED_NO_PUBLISHABLE_PAIRS = "blocked_no_publishable_pairs"
PCAND_LIVE_CANDIDATES_FOUND = "live_candidates_found"
PCAND_PRODUCTION_BATCH_FROZEN = "production_batch_frozen"
PCAND_STATES = frozenset({
    PCAND_BLOCKED_NO_CREDENTIALS, PCAND_BLOCKED_NO_LIVE_OPT_IN, PCAND_BLOCKED_NO_LIVE_OVERLAP,
    PCAND_BLOCKED_NO_PUBLISHABLE_PAIRS, PCAND_LIVE_CANDIDATES_FOUND, PCAND_PRODUCTION_BATCH_FROZEN,
})
PCAND_BLOCKED_STATES = frozenset({
    PCAND_BLOCKED_NO_CREDENTIALS, PCAND_BLOCKED_NO_LIVE_OPT_IN, PCAND_BLOCKED_NO_LIVE_OVERLAP,
    PCAND_BLOCKED_NO_PUBLISHABLE_PAIRS,
})

# candidate_provenance — production 후보는 live_derived 만. 오프라인/합성/none 은 production 후보 아님.
PROVENANCE_LIVE_DERIVED = SOURCE_LIVE          # "live_derived"
PROVENANCE_NONE = "none"

# §8 source role guard: production candidate anchor 는 publishable 만(event_ingest_pipeline 의 source_type vocab).
# article(=news article)·official 은 publishable; community/signal(market)/catalog/search/unknown 은 anchor 거부.
# "news" 는 registry 표기 alias 로 함께 허용(파이프라인은 article 로 매핑하나 직접 role 표기 대비).
_PUBLISHABLE_PRODUCTION_ROLES = frozenset({"official", "article", "news"})

# production_candidate_status → operator 한 줄 next action(internal ops UI 가 읽는 단일 요약).
_PCAND_NEXT_ACTION = {
    PCAND_BLOCKED_NO_CREDENTIALS: (
        "set the cross-source provider credentials (e.g. GUARDIAN_API_KEY/NYT_API_KEY) in .env (secret 커밋 "
        "금지·값 미노출), then opt in with a live query — live-derived candidates need credentials first"),
    PCAND_BLOCKED_NO_LIVE_OPT_IN: (
        "credentials are present — explicitly opt in to a bounded live query (live_query=True / --live-query) to "
        "fetch cross-source publishable candidate pairs (network·not CI; no raw body stored)"),
    PCAND_BLOCKED_NO_LIVE_OVERLAP: (
        "live query ran but found no cross-source same-date overlap — broaden the topic/time_window or add another "
        "wired publishable provider (two outlets must report the same event)"),
    PCAND_BLOCKED_NO_PUBLISHABLE_PAIRS: (
        "cross-source overlap exists but no publishable×publishable pair — community/market/catalog/search are not "
        "event anchors (do not weaken the source role guard to get more candidates)"),
    PCAND_LIVE_CANDIDATES_FOUND: (
        "live-derived publishable candidates found — freeze a production-candidate reviewer worklist (separate from "
        "the synthetic dry-run batch); the batch is a worklist, not same-event truth"),
    PCAND_PRODUCTION_BATCH_FROZEN: (
        "operator: manually distribute the frozen production-candidate worklist to >=2 pseudonymous reviewers per "
        "pair and collect returned label JSONL (no system sending); production gold stays 0 until human labels import"),
}


# ── §8: source role guard(publishable×publishable·anchor fail-closed) ────────────────────────────────────
def _is_publishable_production_pair(pair: dict) -> bool:
    """production candidate pair 가 publishable×publishable(official/article/news)인가(§8).

    한쪽이라도 community/market(signal)/catalog/search/unknown 이면 거부 — anchor 로 쓰지 않는다(fail-closed).
    더 많은 후보를 얻으려고 이 가드를 약화하지 않는다(§8 invariant)."""
    return (pair.get("source_role_a") in _PUBLISHABLE_PRODUCTION_ROLES
            and pair.get("source_role_b") in _PUBLISHABLE_PRODUCTION_ROLES)


# ── §4: production_candidate_status(6-state·acquisition 분해·둔갑 0) ──────────────────────────────────────
def _production_candidate_status(
    *, live_query: bool, smoke: dict, publishable_pair_count: int, batch_frozen: bool,
    cross_providers_ready: bool,
) -> str:
    """acquisition 결과 → production_candidate_status(6-state). 합성/오프라인을 production 으로 둔갑시키지 않고
    실 live 후보 확보 여부를 정직하게 분해한다.

    opt-in off(또는 smoke not_opted_in): credential 이 모두 present 면 blocked_no_live_opt_in(opt-in 만 하면 됨),
    아니면 blocked_no_credentials(키 먼저). opt-in 했으나 fetch 미성공: credential 결손이면 blocked_no_credentials,
    credential 은 present 인데 비-credential 사유(rate_limit/no_records/network/host_gate)면 blocked_no_live_overlap
    (정확 사유는 block_reasons/next_actions 에 smoke passthrough — "키 설정" 오안내 금지). fetch 성공·cross overlap 0
    → blocked_no_live_overlap. overlap 있으나 publishable 0 → blocked_no_publishable_pairs. publishable 있고 frozen
    → production_batch_frozen(즉시 동결 설계상 live_candidates_found 는 frozen 으로 수렴 — 미동결 transient 만 found)."""
    brs = smoke.get("block_reasons") or []
    attempted = bool(smoke.get("live_query_attempted"))
    cross = int(smoke.get("cross_source_pair_count") or 0)
    if not live_query or "not_opted_in" in brs:
        return PCAND_BLOCKED_NO_LIVE_OPT_IN if cross_providers_ready else PCAND_BLOCKED_NO_CREDENTIALS
    if not attempted:
        # opt-in 했으나 양 provider governed fetch 미성공. credential 결손이면 키 먼저(blocked_no_credentials);
        # credential present 인데 fetch 가 비-credential 사유(rate_limit/no_records/network/host_gate)로 실패하면
        # blocked_no_live_overlap(adversarial MEDIUM — credential 멀쩡한데 "키 설정" 오안내 금지·정확 사유는 passthrough).
        return PCAND_BLOCKED_NO_LIVE_OVERLAP if cross_providers_ready else PCAND_BLOCKED_NO_CREDENTIALS
    if cross <= 0:
        return PCAND_BLOCKED_NO_LIVE_OVERLAP
    if publishable_pair_count <= 0:
        return PCAND_BLOCKED_NO_PUBLISHABLE_PAIRS
    return PCAND_PRODUCTION_BATCH_FROZEN if batch_frozen else PCAND_LIVE_CANDIDATES_FOUND


def _default_acquire(*, live_query: bool) -> dict:
    """기본 live 후보 획득 경로(ADR#64 cross-source smoke·opt-in·secret-safe). 기본 live_query=False → 시도 0.

    test 는 acquire_fn 주입으로 결정론(실 network/`.env` 비의존). 실 live 호출은 live_query=True + 양 provider
    credential present + transport=None 일 때만(operator 명시 opt-in)."""
    return run_cross_source_live_overlap_smoke(live_query=live_query, semantic_scoring=False)


# ── §4: 통합 R1 production candidate acquisition entrypoint ───────────────────────────────────────────────
def run_r1_production_candidate_acquisition(
    *, directory: Optional[Any] = None, batch_id: str = PROD_BATCH_ID, as_of: Optional[str] = None,
    live_query: bool = False, acquire_fn: Optional[Callable[..., dict]] = None,
    readiness_fn: Optional[Callable[[], dict]] = None,
    synthetic_batch_fn: Optional[Callable[..., dict]] = None,
    gate_fn: Optional[Callable[..., dict]] = None,
) -> dict:
    """R1 live production candidate acquisition gate + 조건부 production-candidate batch freeze(병합 0·LLM 0·
    embedding 0·DB 0·전송 0·secret read 0).

    1) actual input 재확인(Lane A): returned/imported labels 가 이미 있으면 그 처리가 acquisition 보다 우선(Q17).
    2) credential presence(secret-safe·network 0) + live 후보 획득(Lane B·opt-in): 기본 live_query=False → 시도 0
       → blocked_no_credentials/blocked_no_live_opt_in 정직 산출. opt-in + 양 credential present 일 때만 실 fetch.
    3) production-candidate freeze(Lane B·live-derived publishable 만): 합성 fixture 는 절대 production 후보 아님.
    4) synthetic dry-run track(Lane C): 합성 batch 를 **분리** 표시(production 둔갑 0).
    어떤 경로도 입력 날조·merge·LLM·embedding·DB·전송·secret read·same_event 확정·label 생성을 하지 않는다."""
    # 1) Lane A — actual input 재확인(단일 출처 게이트 1회·production_gold_count exact passthrough).
    gate = (gate_fn or run_actual_input_gate)(directory=directory, batch_id=batch_id, as_of=as_of)
    actual_input_status = gate["actual_input_status"]
    returned_labels_take_precedence = actual_input_status in (INPUT_RETURNED_PRESENT, INPUT_LABELS_IMPORTED)

    # 2) credential presence(secret-safe·network 0·값 0) — cross-source adapter provider(guardian/nyt).
    readiness = (readiness_fn or build_provider_readiness_report)()
    cred = readiness.get("credential_status") or {}
    providers_checked = [_PROVIDER_A, _DEFAULT_PROVIDER_B]
    providers_ready = [p for p in providers_checked if cred.get(p)]
    cross_providers_ready = all(bool(cred.get(p)) for p in providers_checked)

    # 2b) Lane B — live 후보 획득(opt-in·기본 시도 0). secret-safe(present/missing 만·값 미열람).
    smoke = (acquire_fn or _default_acquire)(live_query=live_query)
    live_call_performed = bool(smoke.get("live_query_attempted"))
    cross_source_pair_count = int(smoke.get("cross_source_pair_count") or 0)
    reviewer_queue = smoke.get("reviewer_queue")

    # 3) Lane B — production-candidate freeze(live-derived publishable×publishable 만·합성 둔갑 0).
    candidate_provenance = PROVENANCE_NONE
    publishable_pair_count = 0
    production_frozen_pairs: list[dict] = []
    production_batch_signature = ""
    production_candidate_batch_ready = False
    expected_label_files: list[str] = []
    validation_command = ""
    prod_intake_directory = ""
    reviewer_instruction_ready = False
    label_template_ready = False
    placement_guide_ready = False
    operator_launch_checklist: Optional[dict] = None

    # live-derived provenance **독립 검증**(adversarial MEDIUM·machinery 강제): live_call_performed 만으로 live_derived
    # 태깅하지 않고, smoke 가 실제 records 로 `dataset_source=live_derived` 를 세웠는지 freeze 경계에서 fail-closed 확인
    # (상류 결합에 더해 둔갑-0 을 선언이 아닌 코드로 — smoke 가 향후 replay/fixture 모드를 켜도 freeze 가 자체 차단).
    smoke_live_derived = smoke.get("dataset_source") == SOURCE_LIVE
    if live_call_performed and smoke_live_derived and reviewer_queue:
        instruction = build_reviewer_instruction()
        # live 후보 template 은 **live_derived 태깅**(합성과 구조적 분리·intake chain 이 production gold 후보로만 인정).
        all_template = build_label_template(reviewer_queue, dataset_source=SOURCE_LIVE)
        all_frozen = _frozen_pair_list(all_template)
        # §8 source role guard: publishable×publishable 만 남긴다(anchor 거부·fail-closed·약화 0).
        production_frozen_pairs = [p for p in all_frozen if _is_publishable_production_pair(p)]
        publishable_pair_count = len(production_frozen_pairs)
        if publishable_pair_count > 0:
            candidate_provenance = PROVENANCE_LIVE_DERIVED
            # 운영자 배포 산출물(template/manifest/intake/bundle)도 **publishable pair 로만** 구성한다(adversarial MEDIUM
            # — 가드를 회계[count/signature]뿐 아니라 reviewer 에게 실제 배포되는 worklist 까지 적용). 상류가 이미
            # publishable 만 emit 하므로 통상 no-op 이나, 회귀/다른 큐 소스 시 비-publishable 이 배포되는 것을 차단.
            pub_ids = {p["pair_id"] for p in production_frozen_pairs}
            pub_queue = dict(reviewer_queue)
            pub_queue["packet_rows"] = [
                r for r in (reviewer_queue.get("packet_rows") or []) if r.get("pair_id") in pub_ids]
            pub_queue["queue_pair_ids"] = sorted(pub_ids)
            template = build_label_template(pub_queue, dataset_source=SOURCE_LIVE)
            manifest = build_assignment_manifest(pub_queue, batch_id=batch_id)
            intake_plan = build_intake_plan(
                batch_id, pseudonyms=manifest["pseudonymous_reviewers"],
                intake_dir=gate["input_directory"])
            bundle = build_pilot_handoff_bundle(
                batch_id=batch_id, packet_id=f"{batch_id}_prod_candidate", instruction=instruction,
                manifest=manifest, intake_plan=intake_plan, template=template,
                intake_dir_display=gate["input_directory"])
            production_batch_signature = _batch_signature(
                production_frozen_pairs, batch_id=batch_id, target_pair_count=REQUIRED_PRODUCTION_GOLD,
                reviewers_per_pair=DEFAULT_REVIEWERS_PER_PAIR, provenance=PROVENANCE_LIVE_DERIVED)
            operator_launch_checklist = build_operator_launch_checklist(
                batch_id=batch_id, batch_signature=production_batch_signature, intake_plan=intake_plan,
                bundle=bundle, frozen_pair_count=publishable_pair_count, provenance=PROVENANCE_LIVE_DERIVED)
            production_candidate_batch_ready = True
            expected_label_files = list(intake_plan["expected_label_files"])
            validation_command = intake_plan["validation_command"]
            prod_intake_directory = intake_plan["intake_directory"]
            reviewer_instruction_ready = bool(instruction) and "label_vocabulary" in instruction
            label_template_ready = bool(template)
            placement_guide_ready = True

    production_candidate_status = _production_candidate_status(
        live_query=live_query, smoke=smoke, publishable_pair_count=publishable_pair_count,
        batch_frozen=production_candidate_batch_ready, cross_providers_ready=cross_providers_ready)
    blocked_no_live_production_candidates = production_candidate_status in PCAND_BLOCKED_STATES

    # 4) Lane C — synthetic dry-run track(합성 batch 를 **분리** 인용·production 둔갑 0).
    synth = (synthetic_batch_fn or run_r1_reviewer_pilot_batch)(directory=directory, as_of=as_of)
    synthetic_dry_run_batch_ready = bool(synth.get("batch_frozen"))
    synthetic_batch_not_production = not bool(synth.get("pilot_batch_is_production_candidate"))   # 항상 True.

    # 5) R1 gap(게이트 production_gold_count exact passthrough + canonical floor·_r1_status).
    prod = gate["production_gold_count"]
    returned_label_count = gate["returned_label_count"]
    r1_status = _r1_status(
        returned_label_count=returned_label_count, production_gold_count=prod,
        calibration_ready=gate["calibration_ready"])
    current_r1_gap = max(0, REQUIRED_PRODUCTION_GOLD - prod)

    # operator next actions(returned labels 우선·Q17 → status 한 줄 → smoke → gate).
    primary_next_action = _PCAND_NEXT_ACTION[production_candidate_status]
    next_actions: list[str] = []
    if returned_labels_take_precedence:
        next_actions.append(
            "actual returned labels are already present — process them via the intake/monitor/gold chain "
            "FIRST (production candidate acquisition is secondary while labels await import)")
    next_actions.append(primary_next_action)
    next_actions.extend(smoke.get("next_actions") or [])
    next_actions.extend(gate.get("next_actions") or [])
    next_actions = list(dict.fromkeys(next_actions))

    block_reasons: list[str] = []
    if blocked_no_live_production_candidates:
        block_reasons.append(production_candidate_status)
    block_reasons.extend(smoke.get("block_reasons") or [])
    block_reasons.extend(gate.get("block_reasons") or [])
    block_reasons = list(dict.fromkeys(block_reasons))

    flags = {
        "internal_only": True,
        "no_public_truth": True,
        "no_merge": True,
        "no_public_iu": True,
        "pii_safe": True,
        "no_llm": True,
        "no_db_write": True,
        "gold_provenance_verified": False,   # production gold 무결성 선언 기반(미검증) — readiness 근거 인용 금지.
    }

    # §7 dual-track internal ops API/UI 화이트리스트 contract(sanitized·forbidden 필드 없음·public truth 아님).
    r1_production_candidate_contract = {
        "contract": "InternalOpsR1ProductionCandidateStatus",
        "synthetic_dry_run_batch_ready": synthetic_dry_run_batch_ready,
        "synthetic_batch_not_production": synthetic_batch_not_production,
        "production_candidate_batch_ready": production_candidate_batch_ready,
        "production_candidate_status": production_candidate_status,
        "candidate_provenance": candidate_provenance,
        "live_call_performed": live_call_performed,
        "live_candidate_count": cross_source_pair_count,
        "publishable_pair_count": publishable_pair_count,
        "production_frozen_pair_count": publishable_pair_count,
        "production_batch_id": batch_id if production_candidate_batch_ready else "",
        "production_batch_signature": production_batch_signature,
        "ready_for_manual_launch": production_candidate_batch_ready,
        "blocked_no_live_production_candidates": blocked_no_live_production_candidates,
        "validation_command": validation_command,
        "intake_directory": prod_intake_directory,
        "r1_status": r1_status,
        "production_gold_count": prod,
        "required_production_gold_count": REQUIRED_PRODUCTION_GOLD,
        "current_r1_gap": current_r1_gap,
        "r2_r7_no_go": True,
        "next_manual_action": primary_next_action,
        "flags": dict(flags),
    }

    result = {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        # §A actual input 재확인(Lane A·단일 출처 게이트 passthrough).
        "actual_input_rechecked": True,
        "actual_contact_evidence_found": gate["actual_contact_evidence_found"],
        "actual_returned_labels_found": gate["actual_returned_labels_found"],
        "actual_input_status": actual_input_status,
        "external_input_required": gate["external_input_required"],
        "returned_labels_take_precedence": returned_labels_take_precedence,
        # §B live production candidate acquisition(Lane B·opt-in·secret-safe).
        "live_candidate_acquisition_attempted": True,
        "live_call_performed": live_call_performed,
        "live_call_opt_in_required": not live_call_performed,
        "credential_presence_checked_secret_safe": True,
        "providers_checked": providers_checked,
        "providers_ready": providers_ready,
        "production_candidate_status": production_candidate_status,
        "blocked_no_live_production_candidates": blocked_no_live_production_candidates,
        "live_candidate_count": cross_source_pair_count,
        "publishable_pair_count": publishable_pair_count,
        # §C production-candidate batch freeze(live-derived publishable 만·합성 둔갑 0).
        "production_candidate_batch_ready": production_candidate_batch_ready,
        "production_batch_id": batch_id if production_candidate_batch_ready else "",
        "production_batch_signature": production_batch_signature,
        "production_frozen_pair_count": publishable_pair_count,
        "production_frozen_pairs": production_frozen_pairs,
        "candidate_provenance": candidate_provenance,
        "ready_for_manual_launch": production_candidate_batch_ready,
        "expected_label_files": expected_label_files,
        "validation_command": validation_command,
        "intake_directory": prod_intake_directory,
        "reviewer_instruction_ready": reviewer_instruction_ready,
        "label_template_ready": label_template_ready,
        "placement_guide_ready": placement_guide_ready,
        "operator_launch_checklist": operator_launch_checklist,
        # §D synthetic dry-run track(분리·production 둔갑 0).
        "synthetic_dry_run_batch_ready": synthetic_dry_run_batch_ready,
        "synthetic_batch_not_production": synthetic_batch_not_production,
        "synthetic_batch_id": synth.get("batch_id", ""),
        "synthetic_frozen_pair_count": synth.get("frozen_pair_count", 0),
        # §B R1 gap(게이트 exact passthrough + canonical floor).
        "r1_status": r1_status,
        "production_gold_count": prod,
        "synthetic_gold_count": gate["synthetic_gold_count"],
        "required_production_gold_count": REQUIRED_PRODUCTION_GOLD,
        "current_r1_gap": current_r1_gap,
        "calibration_ready": gate["calibration_ready"],
        "merge_gate_ready": gate["merge_gate_ready"],
        "r2_r7_no_go": True,
        # public/PII/merge 경계(정직·constant + 게이트 파생).
        "public_truth_exposed": False,
        "same_event_truth_exposed": False,
        "score_exposed": gate["score_exposed"],
        "rationale_exposed": gate["rationale_exposed"],
        "predicted_status_exposed": gate["predicted_status_exposed"],
        "raw_pii_exposed": gate["raw_pii_exposed"],
        "raw_source_body_exposed": False,
        "no_public_intelligence_unit": gate["no_public_intelligence_unit"],
        "merge_allowed": gate["merge_allowed"],
        "db_write": gate["db_write"],
        "llm_invoked": gate["llm_invoked"],
        "embedding_invoked": gate["embedding_invoked"],
        "actual_sending_performed": False,
        # §7 dual-track internal ops API/UI 화이트리스트 contract.
        "r1_production_candidate_contract": r1_production_candidate_contract,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·미래 드리프트 fail-loud).
    _assert_pii_safe(result, _path="r1_production_candidate_acquisition_output")
    return result


# ── CLI(기본 시도 0·network 0·DB 0·전송 0·secret read 0; --live-query 로 opt-in bounded live acquisition) ────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="R1 live production candidate acquisition gate + production-candidate batch readiness "
                    "(ADR#76·병합 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0).")
    parser.add_argument("--batch-id", default=PROD_BATCH_ID, help="actual input 재확인·production-candidate freeze batch id.")
    parser.add_argument("--input-dir", metavar="DIR", help="실 입력 디렉터리(미지정 시 canonical). 코드가 생성하지 않음.")
    parser.add_argument("--as-of", metavar="ISO_DATE", help="overdue 산정 기준일(ISO).")
    parser.add_argument(
        "--live-query", action="store_true",
        help="명시적 opt-in: 양 provider credential present 일 때만 bounded cross-source live fetch(network·CI 아님·값 미노출).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = run_r1_production_candidate_acquisition(
        directory=ns.input_dir, batch_id=ns.batch_id, as_of=ns.as_of, live_query=ns.live_query)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']}")
    print(f"- actual_input: rechecked={out['actual_input_rechecked']} status={out['actual_input_status']} "
          f"external_input_required={out['external_input_required']} r1_status={out['r1_status']}")
    print(f"- acquisition: attempted={out['live_candidate_acquisition_attempted']} "
          f"live_call_performed={out['live_call_performed']} status={out['production_candidate_status']}")
    print(f"- providers: checked={out['providers_checked']} ready={out['providers_ready']}")
    print(f"- candidates: live={out['live_candidate_count']} publishable={out['publishable_pair_count']} "
          f"provenance={out['candidate_provenance']}")
    print(f"- production_batch: ready={out['production_candidate_batch_ready']} "
          f"frozen={out['production_frozen_pair_count']}/{out['required_production_gold_count']} "
          f"signature={out['production_batch_signature'][:23] + '...' if out['production_batch_signature'] else '(none)'}")
    print(f"- synthetic_track: dry_run_ready={out['synthetic_dry_run_batch_ready']} "
          f"not_production={out['synthetic_batch_not_production']} id={out['synthetic_batch_id']}")
    print(f"- r1_gap: production={out['production_gold_count']}/{out['required_production_gold_count']} "
          f"gap={out['current_r1_gap']} r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- gates: merge_allowed={out['merge_allowed']} public_truth_exposed={out['public_truth_exposed']} "
          f"actual_sending={out['actual_sending_performed']} db_write={out['db_write']} "
          f"llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']}")
    print(f"- next_action: {out['next_actions'][0] if out['next_actions'] else ''}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

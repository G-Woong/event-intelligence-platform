"""ADR#72 — internal ops dashboard read-only API(reviewer pipeline workflow state·public truth 아님).

`/api/internal/ops/*` (main.py 에서 prefix `/api/internal/ops` + `require_admin_token` dependency 로 등록).
이중 게이트: ① admin-token 인증(라우터 dependency·prod fail-closed) + ② `INTERNAL_OPS_DASHBOARD_ENABLED` flag
(기본 off → 404). read-only — DB session 미사용·live fetch 0·LLM 0·embedding 0·secret read 0·DB write 0.
응답은 sanitized `InternalOpsPilotExecutionStatus` 만(actual input gate 가 산출한 ops contract). same_event truth·
reviewer raw PII·score·rationale·predicted_status 는 스키마에 필드가 없어 구조적 미노출.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.app.core.config import settings
from backend.app.schemas.internal_ops import (
    InternalOpsAcquisitionFrontierStatus,
    InternalOpsDiscreteAcquisitionFrontier,
    InternalOpsPilotExecutionStatus,
    InternalOpsPreflightStatus,
    InternalOpsR1AcquisitionStatus,
    InternalOpsR1PilotBatchStatus,
    InternalOpsR1ProductionCandidateStatus,
)
from backend.app.tools.internal_ops_preflight import run_internal_ops_preflight
from backend.app.tools.r1_discrete_event_acquisition import (
    run_discrete_event_acquisition_and_recall_probe,
)
from backend.app.tools.r1_gold_acquisition_plan import run_r1_gold_acquisition_plan
from backend.app.tools.r1_production_candidate_acquisition import (
    run_r1_production_candidate_acquisition,
)
from backend.app.tools.r1_reviewer_pilot_batch import run_r1_reviewer_pilot_batch
from backend.app.tools.r1_targeted_live_acquisition import (
    run_targeted_live_acquisition_and_near_match_diagnostic,
)
from backend.app.tools.reviewer_actual_input_gate import run_actual_input_gate

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/pilot-execution", response_model=InternalOpsPilotExecutionStatus)
def get_pilot_execution_status() -> InternalOpsPilotExecutionStatus:
    """reviewer pilot 실행 workflow state(internal ops dashboard 전용). flag off → 404(미노출).

    sync 파일 스캔이라 `def`(FastAPI 가 threadpool 실행 — event loop 미차단). actual input gate 가 기본 입력
    디렉터리(없으면 no_actual_input)를 스캔해 honest current state(예: not_started·external_input_required)를
    sanitized contract 로 반환한다. operator 입력 파일이 깨졌으면 경로/내용 누출 없이 503.
    """
    # flag off → 404. admin-token 인증은 main.py 라우터 dependency 가 강제(이중 게이트). public truth 아님.
    if not settings.INTERNAL_OPS_DASHBOARD_ENABLED:
        raise HTTPException(status_code=404, detail="not found")
    try:
        gate = run_actual_input_gate()
    except (ValueError, OSError) as exc:   # malformed operator 입력 파일 등 — detail 에 경로/내용 미포함.
        logger.warning("internal ops status unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="internal ops status temporarily unavailable") from None
    return InternalOpsPilotExecutionStatus(**gate["internal_ops_contract"])


@router.get("/preflight", response_model=InternalOpsPreflightStatus)
def get_preflight_status() -> InternalOpsPreflightStatus:
    """ADR#73 — internal ops auth/deploy posture + R1~R7 readiness(read-only). flag off → 404(미노출).

    preflight 는 settings(admin token **존재 여부만**)로 5-state posture 를 평가하고, actual input 을 재확인하며,
    R1~R7 gated roadmap 을 sanitized 로 표면화한다. admin token **값**은 응답 스키마에 필드 자체가 없다(secret 0).
    operator 입력 파일이 깨졌으면 경로/내용 누출 없이 503.
    """
    if not settings.INTERNAL_OPS_DASHBOARD_ENABLED:
        raise HTTPException(status_code=404, detail="not found")
    try:
        out = run_internal_ops_preflight()
    except (ValueError, OSError) as exc:   # malformed operator 입력 파일 등 — detail 에 경로/내용 미포함.
        logger.warning("internal ops preflight unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="internal ops preflight temporarily unavailable") from None
    return InternalOpsPreflightStatus(**out["preflight_contract"])


@router.get("/r1-gold-acquisition", response_model=InternalOpsR1AcquisitionStatus)
def get_r1_gold_acquisition_status() -> InternalOpsR1AcquisitionStatus:
    """ADR#74 — R1 production gold acquisition gap + operator next manual action(read-only). flag off → 404(미노출).

    R1 plan 은 actual input 을 재확인하고 gold floor(current/required·canonical 200/50/2 + 파생 67/67/20)의 gap 을
    산출한다. target floor 는 operating floor 이지 production truth 가 아니다(R1 satisfied 는 calibration_ready 일
    때만). 응답 스키마에 same_event truth·score·rationale·predicted_status·raw PII 필드 자체가 없다(구조적 미노출).
    operator 입력 파일이 깨졌으면 경로/내용 누출 없이 503.
    """
    if not settings.INTERNAL_OPS_DASHBOARD_ENABLED:
        raise HTTPException(status_code=404, detail="not found")
    try:
        out = run_r1_gold_acquisition_plan()
    except (ValueError, OSError) as exc:   # malformed operator 입력 파일 등 — detail 에 경로/내용 미포함.
        logger.warning("internal ops r1 acquisition unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="internal ops r1 acquisition temporarily unavailable") from None
    return InternalOpsR1AcquisitionStatus(**out["r1_contract"])


@router.get("/r1-pilot-batch", response_model=InternalOpsR1PilotBatchStatus)
def get_r1_pilot_batch_status() -> InternalOpsR1PilotBatchStatus:
    """ADR#75 — R1 first reviewer pilot batch freeze + launch readiness(read-only). flag off → 404(미노출).

    actual input 을 재확인하고, 결정적 후보 worklist 를 동결(deterministic signature)하며, launch_status·R1 gap·
    R2~R7 No-Go 를 산출한다. candidate_provenance/pilot_batch_is_production_candidate 가 합성 fixture 를 production
    후보로 오인하지 못하게 명시한다(둔갑 0). 응답 스키마에 same_event truth·score·rationale·predicted_status·raw
    PII 필드 자체가 없다(구조적 미노출). operator 입력 파일이 깨졌으면 경로/내용 누출 없이 503.
    """
    if not settings.INTERNAL_OPS_DASHBOARD_ENABLED:
        raise HTTPException(status_code=404, detail="not found")
    try:
        out = run_r1_reviewer_pilot_batch()
    except (ValueError, OSError) as exc:   # malformed operator 입력 파일 등 — detail 에 경로/내용 미포함.
        logger.warning("internal ops r1 pilot batch unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="internal ops r1 pilot batch temporarily unavailable") from None
    return InternalOpsR1PilotBatchStatus(**out["r1_pilot_batch_contract"])


@router.get("/r1-production-candidates", response_model=InternalOpsR1ProductionCandidateStatus)
def get_r1_production_candidate_status() -> InternalOpsR1ProductionCandidateStatus:
    """ADR#76 — R1 live production candidate acquisition + dual-track batch readiness(read-only). flag off → 404(미노출).

    actual input 을 재확인하고, secret-safe credential presence(값 0·network 0)를 본 뒤, live 후보 획득은 **opt-in**
    (기본 시도 0)으로 blocked_no_credentials/blocked_no_live_opt_in 등을 정직하게 산출한다. synthetic dry-run batch 와
    live production-candidate batch 를 **분리** 표시한다(합성→production 둔갑 0). 응답 스키마에 same_event truth·
    score·rationale·predicted_status·raw PII·secret 필드 자체가 없다(구조적 미노출). 입력 파일이 깨졌으면 경로/내용
    누출 없이 503. **실 live 네트워크 호출은 API 경로에서 수행하지 않는다**(opt-in CLI 전용 — read API 는 시도 0).
    """
    if not settings.INTERNAL_OPS_DASHBOARD_ENABLED:
        raise HTTPException(status_code=404, detail="not found")
    try:
        # read API 는 live_query=False 고정(시도 0). 실 live acquisition 은 operator CLI opt-in 전용.
        out = run_r1_production_candidate_acquisition(live_query=False)
    except (ValueError, OSError) as exc:   # malformed operator 입력 파일 등 — detail 에 경로/내용 미포함.
        logger.warning("internal ops r1 production candidates unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="internal ops r1 production candidates temporarily unavailable") from None
    return InternalOpsR1ProductionCandidateStatus(**out["r1_production_candidate_contract"])


@router.get("/r1-acquisition-frontier", response_model=InternalOpsAcquisitionFrontierStatus)
def get_r1_acquisition_frontier_status() -> InternalOpsAcquisitionFrontierStatus:
    """ADR#78 — near-match gap diagnostic + targeted acquisition frontier(read-only). flag off → 404(미노출).

    near-match gap status·**원인 가설들(양가·단정 아님)**·confidence·targeted seed/live attempt count·provider
    expansion·Korean strategy readiness·production candidate status·R1 gap·R2~R7 No-Go·필수 정직 copy 를 sanitized
    로 산출한다. 응답 스키마에 same_event truth·score·rationale·predicted_status·raw body·raw PII·secret 필드 자체가
    없다(구조적 미노출). 입력 파일이 깨졌으면 경로/내용 누출 없이 503. **실 live 네트워크 호출은 API 경로에서 수행하지
    않는다**(live_query=False 고정 → near_match_gap_status=insufficient_debug_artifact 가 정상; 실 live diagnostic 은
    operator CLI opt-in 전용). near-match 0 은 같은 사건 부재를 증명하지 않는다(required_copy 가 명시).
    """
    if not settings.INTERNAL_OPS_DASHBOARD_ENABLED:
        raise HTTPException(status_code=404, detail="not found")
    try:
        # read API 는 live_query=False 고정(시도 0). 실 live targeted acquisition 은 operator CLI opt-in 전용.
        out = run_targeted_live_acquisition_and_near_match_diagnostic(live_query=False)
    except (ValueError, OSError) as exc:   # malformed operator 입력 파일 등 — detail 에 경로/내용 미포함.
        logger.warning("internal ops r1 acquisition frontier unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="internal ops r1 acquisition frontier temporarily unavailable") from None
    return InternalOpsAcquisitionFrontierStatus(**out["internal_ops_acquisition_frontier"])


@router.get("/r1-discrete-acquisition", response_model=InternalOpsDiscreteAcquisitionFrontier)
def get_r1_discrete_acquisition_frontier() -> InternalOpsDiscreteAcquisitionFrontier:
    """ADR#79 — discrete-event acquisition + deterministic recall probe frontier(read-only). flag off → 404(미노출).

    discrete-event seed(shape·source)·near-match gap status·원인 가설(양가·단정 아님)·recall probe lift 신호
    (**reviewer-routing only·merge 미적용**)·provider/Korean next action·R1 gap·R2~R7 No-Go·정직 copy 를 sanitized
    로 산출한다. 응답 스키마에 same_event truth·score(per-pair)·rationale·predicted_status·raw body·raw PII·secret
    필드 자체가 없다(구조적 미노출). 입력 파일이 깨졌으면 경로/내용 누출 없이 503. **실 live 네트워크 호출은 API 경로에서
    수행하지 않는다**(live_query=False 고정 → near_match_gap_status=insufficient_debug_artifact 가 정상; 실 live 는
    operator CLI opt-in 전용). recall probe lift 는 reviewer 라우팅 신호이지 same-event 단정이 아니다(required_copy 명시).
    """
    if not settings.INTERNAL_OPS_DASHBOARD_ENABLED:
        raise HTTPException(status_code=404, detail="not found")
    try:
        # read API 는 live_query=False 고정(시도 0). recall probe 는 synthetic 검증(network 0).
        out = run_discrete_event_acquisition_and_recall_probe(live_query=False)
    except (ValueError, OSError) as exc:   # malformed operator 입력 파일 등 — detail 에 경로/내용 미포함.
        logger.warning("internal ops r1 discrete acquisition unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="internal ops r1 discrete acquisition temporarily unavailable") from None
    return InternalOpsDiscreteAcquisitionFrontier(**out["internal_ops_discrete_acquisition_frontier"])

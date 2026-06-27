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
from backend.app.schemas.internal_ops import InternalOpsPilotExecutionStatus
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

"""ADR#73 — internal ops auth/deployment preflight + product bridge readiness (병합 0·LLM 0·embedding 0·DB 0·전송 0).

ADR#72 가 만든 것: internal ops read-only API/UI(admin-token + flag 이중 게이트 + server-env gate + nav 미노출).
그러나 "이 배포 상태가 실제로 안전한가"(auth/deploy posture)를 **한 곳에서 명시·테스트로 봉인**하는 preflight 가
없었다 — 게이트 판단이 security.py·config.py·main.py·frontend page 에 흩어져 있어, `APP_ENV=dev + flag=true +
무토큰` 같은 **무인증 reachable** 조합을 단일 신호로 잡지 못했다(R-InternalOpsAuthBoundary 잔여).

이 모듈은 **재구현이 아니라 posture 평가 + actual-input 재확인 wrapper** 다:
  - actual input 재확인: `reviewer_actual_input_gate.run_actual_input_gate`(단일 출처·재호출 0). 게이트가
    gitignored 입력 디렉터리를 스캔(생성 0)해 no_actual_input/external_input_required 를 정직 산출한다.
  - auth/deploy posture: settings(APP_ENV·INTERNAL_OPS_DASHBOARD_ENABLED·ADMIN_API_TOKEN **존재 여부만**)로
    5-state posture 를 순수 평가(`evaluate_internal_ops_posture`). 토큰 **값은 절대 읽지 않는다**(`bool(...)`만).
  - R1~R7 readiness matrix: gold→MERGE_GATE→embedding→entity→KG→GraphRAG→IU 단계를 gate 기반 머신리더블
    constant 로 표면화(구현 runtime 0 — docs roadmap 과 동기). public IU 는 모든 gate 통과 전까지 No-Go.

절대 불변(상속·상용 안전 계약):
  - **secret 0**: ADMIN_API_TOKEN 값을 읽거나 출력하지 않는다 — `admin_token_configured=bool(...)` 존재 여부만.
  - **no merge / no public IU / no DB / no LLM / no embedding / no 전송**: 전 경로 상속(게이트 파생 + 상수).
  - **internal ops ≠ public truth**: posture/readiness 는 workflow·운영 상태만. same_event 확정·verified gold 렌더 0.
  - **deployment_proven=False 불변**: per-user auth 미구현 + 물리 reachability 미증명 → auth boundary 완전종결 금지.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional

from backend.app.core.config import settings
from backend.app.core.security import _PROD_LIKE_ENVS
from backend.app.tools.reviewer_actual_input_gate import run_actual_input_gate
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "internal_ops_hardening_and_product_bridge"

# ── §5 internal ops preflight posture(5-state·순수 평가) ─────────────────────────────────────────────────
# disabled_safe: flag off → 엔드포인트 404/page notFound(가장 안전한 기본). enabled_internal_safe: flag on +
# admin-token 설정 → auth 강제(환경 무관). unsafe_public_exposure: flag on + 무토큰 + 비-prod(dev/test) →
# require_admin_token 가 bypass → **무인증 reachable**(실 배포 시 노출). misconfigured: flag on + 무토큰 + prod-like
# → 503/기동거부(서비스 불가). unknown: 알 수 없는 APP_ENV.
POSTURE_DISABLED_SAFE = "disabled_safe"
POSTURE_ENABLED_INTERNAL_SAFE = "enabled_internal_safe"
POSTURE_UNSAFE_PUBLIC_EXPOSURE = "unsafe_public_exposure"
POSTURE_MISCONFIGURED = "misconfigured"
POSTURE_UNKNOWN = "unknown"
PREFLIGHT_STATES = frozenset({
    POSTURE_DISABLED_SAFE, POSTURE_ENABLED_INTERNAL_SAFE,
    POSTURE_UNSAFE_PUBLIC_EXPOSURE, POSTURE_MISCONFIGURED, POSTURE_UNKNOWN,
})
_KNOWN_ENVS = frozenset({"dev", "test", "staging", "production"})

# auth boundary roll-up(R-InternalOpsAuthBoundary posture). hardened_partial: 게이트 정상이나 per-user auth·
# 물리 분리 미증명(이번 턴 최대치). no_go: 배포 진행 불가(unsafe/misconfigured/unknown).
AUTH_BOUNDARY_HARDENED_PARTIAL = "hardened_partial"
AUTH_BOUNDARY_NO_GO = "no_go"
_SAFE_POSTURES = frozenset({POSTURE_DISABLED_SAFE, POSTURE_ENABLED_INTERNAL_SAFE})

# ── §7 R1~R7 readiness matrix(gold→MERGE_GATE→embedding→entity→KG→GraphRAG→IU·구현 runtime 0) ──────────
# 각 단계: required_input·current_status·blocker·forbidden_shortcut·next_action·test. current_status 는 현재 실측
# (production_gold_count=0 → R1 FAIL, 이후 전부 No-Go). public IU 는 모든 gate 통과 전까지 No-Go.
R1_R7_READINESS: tuple[dict[str, str], ...] = (
    {
        "stage": "R1", "goal": "production gold floor",
        "required_input": "human-reviewed production labels (live ≥200 / KO ≥50)",
        "current_status": "FAIL", "blocker": "actual returned labels (production_gold_count below floor)",
        "forbidden_shortcut": "synthetic/model/self/LLM labels as production gold",
        "next_action": "collect real reviewer returned labels via the actual input gate",
        "test": "label intake / gold preflight",
    },
    {
        "stage": "R2", "goal": "MERGE_GATE calibration",
        "required_input": "gold eval set (from R1)",
        "current_status": "No-Go", "blocker": "gold floor unmet (R1)",
        "forbidden_shortcut": "threshold without gold; auto-merge before calibration",
        "next_action": "evaluate precision ≥0.98 / FPR ≤0.01 on gold once R1 passes",
        "test": "MERGE_GATE precision/FPR test (auto_merge_enabled=False invariant)",
    },
    {
        "stage": "R3", "goal": "embedding scorer opt-in",
        "required_input": "calibrated eval (from R2)",
        "current_status": "No-Go", "blocker": "MERGE_GATE not calibrated (R2)",
        "forbidden_shortcut": "uncalibrated embedding merge; live embedding call before calibration",
        "next_action": "bounded opt-in scoring only after R2 (no merge authority)",
        "test": "secret-safe embedding test (embedding_invoked=False until opt-in)",
    },
    {
        "stage": "R4", "goal": "entity extraction",
        "required_input": "verified / held event candidates (from R2)",
        "current_status": "No-Go", "blocker": "calibrated candidates absent (R2)",
        "forbidden_shortcut": "entity from unverified raw source",
        "next_action": "provenance-bound entity candidates only",
        "test": "entity provenance test",
    },
    {
        "stage": "R5", "goal": "KG edge building",
        "required_input": "verified events / entities (from R4)",
        "current_status": "No-Go", "blocker": "entity provenance absent (R4)",
        "forbidden_shortcut": "unverified KG edge without provenance/confidence/source role",
        "next_action": "build edge candidates with provenance + confidence + source role",
        "test": "edge provenance test",
    },
    {
        "stage": "R6", "goal": "GraphRAG retrieval",
        "required_input": "verified KG / evidence (from R5)",
        "current_status": "No-Go", "blocker": "KG readiness absent (R5)",
        "forbidden_shortcut": "retrieve from noisy/unverified graph",
        "next_action": "evidence-grounded retrieval over verified graph",
        "test": "retrieval grounding test",
    },
    {
        "stage": "R7", "goal": "Agent synthesis / Intelligence Unit",
        "required_input": "verified evidence + graph + community reaction layer (from R1-R6)",
        "current_status": "No-Go", "blocker": "R1-R6 gates unmet",
        "forbidden_shortcut": "public IU from raw source or LLM summary; community/market/catalog as anchor",
        "next_action": "gated synthesis only after all gates; public IU stays No-Go until then",
        "test": "public IU safety test (no_public_intelligence_unit invariant)",
    },
)

# source role 불변(R1~R7 전반 적용). anchor 가 될 수 있는 것은 official/news 만 — 나머지는 역할이 고정된다.
SOURCE_ROLE_INVARIANTS: dict[str, str] = {
    "community": "reaction layer (not anchor)",
    "market": "signal (not anchor)",
    "catalog": "entity enrichment (not anchor)",
    "search": "URL candidate (not truth)",
    "unknown": "fail-closed",
    "kg_edge": "requires provenance + confidence + source role",
    "public_iu": "No-Go until MERGE_GATE and source role guard pass",
}

# 매트릭스 **구조 정합**(7단계 + R-numbering)일 뿐 — **단계 통과(readiness 달성)가 아니다**. R1 은 현재 FAIL(gold 0).
# operator/automation 이 "준비됨"으로 오독하지 않도록: 실 단계 상태는 r1_r7_stages[].current_status(R1/R2 live 파생).
R1_R7_READINESS_MATRIX_READY = (
    len(R1_R7_READINESS) == 7
    and all(s["stage"] == f"R{i}" for i, s in enumerate(R1_R7_READINESS, start=1))
)


def evaluate_internal_ops_posture(
    *, app_env: str, dashboard_enabled: bool, admin_token_configured: bool,
) -> dict:
    """internal ops 엔드포인트의 auth/deploy posture 를 **순수** 평가한다(settings 직접 접근 0·테스트 주입 가능).

    require_admin_token 의미론과 정합:
      - 토큰 설정 → 환경 무관 강제(401). 미설정 + prod-like → 503(fail-closed). 미설정 + dev/test → bypass(open).
    따라서 **무인증 reachable** 위험 조합은 정확히 `flag on + 무토큰 + 비-prod` 하나다(여기서 unsafe_public_exposure)."""
    if app_env not in _KNOWN_ENVS:
        # 알 수 없는 env(예: `production` 오타 `prod`)는 `require_admin_token` 에서 prod-like 아님 → 무토큰 시 bypass.
        # 따라서 flag on + 무토큰이면 실제로 무인증 reachable(honesty 필드도 그대로 반영). 단 top-line 은 항상 no_go.
        return {
            "status": POSTURE_UNKNOWN, "app_env": app_env, "prod_like": False,
            "dashboard_enabled": dashboard_enabled, "admin_token_configured": admin_token_configured,
            "endpoint_open_unauthenticated": bool(dashboard_enabled and not admin_token_configured),
            "deployment_proven": False,
            "block_reasons": ["unknown_app_env"],
            "next_actions": ["set APP_ENV to one of dev/test/staging/production"],
        }
    prod_like = app_env in _PROD_LIKE_ENVS
    block_reasons: list[str] = []
    next_actions: list[str] = []
    endpoint_open_unauthenticated = False

    if not dashboard_enabled:
        status = POSTURE_DISABLED_SAFE
        block_reasons.append("dashboard_disabled")
        next_actions.append("keep INTERNAL_OPS_DASHBOARD_ENABLED off unless internal operator access is needed")
    elif admin_token_configured:
        # 토큰 설정 → auth 강제(환경 무관). 안전하나 per-user auth·물리 분리 미증명(deployment_proven=False).
        status = POSTURE_ENABLED_INTERNAL_SAFE
        if not prod_like:
            block_reasons.append("dashboard_enabled_with_non_prod_app_env")
            next_actions.append("set APP_ENV=production for any non-local deployment (currently auth-enforced via token)")
        next_actions.append("internal-only: do not link in public nav; verify network isolation before deploy")
    elif prod_like:
        # 무토큰 + prod-like → require_admin_token 503 + assert_startup_auth_posture 기동거부. 서비스 불가(노출은 아님).
        status = POSTURE_MISCONFIGURED
        block_reasons.append("dashboard_enabled_without_admin_token_in_prod_like_env")
        next_actions.append("set ADMIN_API_TOKEN (startup refuses unauthenticated prod-like boot)")
    else:
        # 무토큰 + dev/test + flag on → bypass → **무인증 reachable**. 실 배포 시 노출.
        status = POSTURE_UNSAFE_PUBLIC_EXPOSURE
        endpoint_open_unauthenticated = True
        block_reasons.append("dashboard_enabled_without_auth_in_non_prod_env")
        next_actions.append(
            "set APP_ENV=production AND ADMIN_API_TOKEN before any non-local deploy, "
            "or disable INTERNAL_OPS_DASHBOARD_ENABLED (endpoint is currently unauthenticated)")

    return {
        "status": status, "app_env": app_env, "prod_like": prod_like,
        "dashboard_enabled": dashboard_enabled, "admin_token_configured": admin_token_configured,
        "endpoint_open_unauthenticated": endpoint_open_unauthenticated,
        "deployment_proven": False,   # per-user auth 미구현 + 물리 reachability 미증명 → 불변.
        "block_reasons": block_reasons, "next_actions": next_actions,
    }


def _auth_boundary_status(posture_status: str) -> str:
    return AUTH_BOUNDARY_HARDENED_PARTIAL if posture_status in _SAFE_POSTURES else AUTH_BOUNDARY_NO_GO


def _live_stage_status(
    *, stage: str, static_status: str, production_gold_count: int,
    calibration_ready: bool, merge_gate_ready: bool,
) -> str:
    """R1/R2 의 current_status 를 live gate 에서 파생한다(정적 상수가 gold 교차 시 거짓이 되지 않도록).

    R1(gold floor): gold 0→FAIL·gold>0 미캘리브레이션→PARTIAL·calibration_ready→PASS.
    R2(MERGE_GATE): merge_gate_ready→PASS·else No-Go. R3~R7 은 런타임 미구축이라 gold 무관 No-Go(정적 유지)."""
    if stage == "R1":
        if production_gold_count <= 0:
            return "FAIL"
        return "PASS" if calibration_ready else "PARTIAL"
    if stage == "R2":
        return "PASS" if merge_gate_ready else "No-Go"
    return static_status


def _readiness_stage_summary(
    *, production_gold_count: int = 0, calibration_ready: bool = False, merge_gate_ready: bool = False,
) -> list[dict[str, str]]:
    """API/UI 표시용 trimmed readiness 행(forbidden_shortcut/test 제외·전부 안전 roadmap 텍스트).

    R1/R2 의 current_status 는 **live gate 파생**(정적 상수의 gold-교차 거짓 차단·adversarial 6a). 정적
    R1_R7_READINESS 의 current_status 는 '현재(gold 0) baseline' 문서값으로 유지하되, 실 표시는 live 값을 쓴다."""
    return [
        {"stage": s["stage"], "goal": s["goal"],
         "current_status": _live_stage_status(
             stage=s["stage"], static_status=s["current_status"],
             production_gold_count=production_gold_count, calibration_ready=calibration_ready,
             merge_gate_ready=merge_gate_ready),
         "blocker": s["blocker"], "next_action": s["next_action"]}
        for s in R1_R7_READINESS
    ]


def run_internal_ops_preflight(
    *, directory: Optional[Any] = None, batch_id: str = "reviewer_pilot_exec_001",
    as_of: Optional[str] = None,
) -> dict:
    """internal ops auth/deploy preflight + product bridge readiness(병합 0·LLM 0·embedding 0·DB 0·전송 0).

    1) actual input 재확인: 단일 출처 게이트로 no_actual_input/external_input_required 정직 산출,
    2) auth/deploy posture: settings(토큰 **존재 여부만**)로 5-state 평가,
    3) R1~R7 readiness matrix + source role invariant 표면화.
    어떤 경로도 입력 날조·merge·LLM·embedding·DB·전송·secret read 를 하지 않는다."""
    gate = run_actual_input_gate(directory=directory, batch_id=batch_id, as_of=as_of)

    # secret 경계: 토큰 **값**을 절대 읽지 않는다 — 존재 여부(bool)만.
    posture = evaluate_internal_ops_posture(
        app_env=settings.APP_ENV,
        dashboard_enabled=bool(settings.INTERNAL_OPS_DASHBOARD_ENABLED),
        admin_token_configured=bool(settings.ADMIN_API_TOKEN),
    )
    auth_boundary_status = _auth_boundary_status(posture["status"])
    stage_summary = _readiness_stage_summary(
        production_gold_count=gate["production_gold_count"],
        calibration_ready=gate["calibration_ready"], merge_gate_ready=gate["merge_gate_ready"])
    # backstop(adversarial 6a): merge_gate_ready 인데 R1(gold floor)이 FAIL 이면 자기모순 → fail-loud(API 가 503 로 흡수).
    if gate["merge_gate_ready"] and stage_summary[0]["current_status"] == "FAIL":
        raise ValueError("inconsistent readiness: merge_gate_ready=True but R1 gold floor reports FAIL")
    ops_flags = gate["ops_ui_flags"]

    # API/UI 화이트리스트 contract(sanitized·forbidden 필드 없음).
    preflight_contract = {
        "contract": "InternalOpsPreflightStatus",
        "preflight_status": posture["status"],
        "auth_boundary_status": auth_boundary_status,
        "app_env": posture["app_env"],
        "admin_token_required": True,
        "admin_token_configured": posture["admin_token_configured"],
        "feature_flag_required": True,
        "feature_flag_enabled": posture["dashboard_enabled"],
        "frontend_server_env_required": True,
        "public_nav_exposed": False,
        "deployment_proven": posture["deployment_proven"],
        "actual_input_status": gate["actual_input_status"],
        "external_input_required": gate["external_input_required"],
        "production_gold_count": gate["production_gold_count"],
        "calibration_ready": gate["calibration_ready"],
        "merge_gate_ready": gate["merge_gate_ready"],
        "r1_r7_readiness_matrix_ready": R1_R7_READINESS_MATRIX_READY,
        "r1_r7_stages": stage_summary,
        "flags": ops_flags,
        "block_reasons": list(posture["block_reasons"]),
        "next_actions": list(posture["next_actions"]),
    }

    block_reasons = list(dict.fromkeys(list(posture["block_reasons"]) + list(gate["block_reasons"])))
    next_actions = list(posture["next_actions"]) + list(gate["next_actions"])

    result = {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        # §A actual input 재확인(단일 출처 게이트 passthrough).
        "actual_input_rechecked": True,
        "actual_contact_evidence_found": gate["actual_contact_evidence_found"],
        "actual_returned_labels_found": gate["actual_returned_labels_found"],
        "actual_input_status": gate["actual_input_status"],
        "external_input_required": gate["external_input_required"],
        # §B auth/deploy posture.
        "internal_ops_preflight_status": posture["status"],
        "auth_boundary_status": auth_boundary_status,
        "app_env": posture["app_env"],
        "admin_token_required": True,
        "admin_token_configured": posture["admin_token_configured"],
        "feature_flag_required": True,
        "feature_flag_enabled": posture["dashboard_enabled"],
        "frontend_server_env_required": True,
        "endpoint_open_unauthenticated": posture["endpoint_open_unauthenticated"],
        "deployment_proven": posture["deployment_proven"],
        # public/PII/merge 경계(정직·constant + 게이트 파생).
        "public_nav_exposed": False,
        "public_truth_exposed": False,
        "same_event_truth_exposed": False,
        "score_exposed": gate["score_exposed"],
        "rationale_exposed": gate["rationale_exposed"],
        "predicted_status_exposed": gate["predicted_status_exposed"],
        "raw_pii_exposed": gate["raw_pii_exposed"],
        "raw_source_body_exposed": False,
        # §D R1~R7 readiness matrix.
        "r1_r7_readiness_matrix_ready": R1_R7_READINESS_MATRIX_READY,
        "r1_r7_stages": stage_summary,
        "source_role_invariants": dict(SOURCE_ROLE_INVARIANTS),
        # gold/calibration passthrough(exact).
        "production_gold_count": gate["production_gold_count"],
        "synthetic_gold_count": gate["synthetic_gold_count"],
        "calibration_ready": gate["calibration_ready"],
        "merge_gate_ready": gate["merge_gate_ready"],
        # merge/LLM/embedding/DB/IU 경계(상속).
        "no_public_intelligence_unit": gate["no_public_intelligence_unit"],
        "merge_allowed": gate["merge_allowed"],
        "db_write": gate["db_write"],
        "llm_invoked": gate["llm_invoked"],
        "embedding_invoked": gate["embedding_invoked"],
        # API/UI 화이트리스트 contract.
        "preflight_contract": preflight_contract,
        "ops_ui_flags": ops_flags,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·미래 드리프트 fail-loud).
    _assert_pii_safe(result, _path="internal_ops_preflight_output")
    return result


# ── CLI(settings 기반 posture·network 0·DB 0·전송 0·secret read 0) ──────────────────────────────────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="internal ops auth/deploy preflight + product bridge readiness (ADR#73·병합 0·LLM 0·DB 0·전송 0).")
    parser.add_argument("--batch-id", default="reviewer_pilot_exec_001", help="actual input 재확인 batch id.")
    parser.add_argument("--input-dir", metavar="DIR", help="실 입력 디렉터리(미지정 시 canonical). 코드가 생성하지 않음.")
    parser.add_argument("--as-of", metavar="ISO_DATE", help="overdue 산정 기준일(ISO).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = run_internal_ops_preflight(directory=ns.input_dir, batch_id=ns.batch_id, as_of=ns.as_of)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']}")
    print(f"- actual_input: rechecked={out['actual_input_rechecked']} status={out['actual_input_status']} "
          f"external_input_required={out['external_input_required']}")
    print(f"- posture: status={out['internal_ops_preflight_status']} auth_boundary={out['auth_boundary_status']} "
          f"app_env={out['app_env']}")
    print(f"- auth: admin_token_required={out['admin_token_required']} admin_token_configured={out['admin_token_configured']} "
          f"flag_enabled={out['feature_flag_enabled']} open_unauthenticated={out['endpoint_open_unauthenticated']} "
          f"deployment_proven={out['deployment_proven']}")
    print(f"- readiness: r1_r7_ready={out['r1_r7_readiness_matrix_ready']} gold={out['production_gold_count']} "
          f"calibration_ready={out['calibration_ready']} merge_gate_ready={out['merge_gate_ready']}")
    print(f"- gates: merge_allowed={out['merge_allowed']} public_truth_exposed={out['public_truth_exposed']} "
          f"db_write={out['db_write']} llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']}")
    if out["next_actions"]:
        print(f"- next: {out['next_actions'][0]}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

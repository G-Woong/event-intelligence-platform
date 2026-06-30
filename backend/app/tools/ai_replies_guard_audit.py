"""ADR#94 — ai-replies ungated endpoint guard audit (AUDIT ONLY·엔드포인트 미수정·import 0·LLM 0·runtime 0).

문제: backend/app/api/ai_replies.py 는 `POST /api/ai-replies/request` 를 `LLMClient(provider="mock")` 로 정의하고,
backend/app/main.py 가 `app.include_router(ai_replies.router)` 를 **admin-token dependency 없이** 마운트한다(인접
라우터들은 `dependencies=[Depends(require_admin_token)]` 로 게이트됨). 즉 이 엔드포인트는 public·unauthenticated·
ungated 다. 본 모듈은 그 사실을 **정적 소스 텍스트로만** 감사하고 게이트를 권고한다 — 엔드포인트를 고치지 않는다.

설계 계약(불변):
  - **AUDIT ONLY**: 엔드포인트를 수정하지 않는다(endpoint_modified=False). 그리고 두 파일을 **import 하지 않는다** —
    backend.app.api.ai_replies 를 import 하면 로드 시 `LLMClient(provider="mock")` 가 실행되고, backend.app.main 을
    import 하면 DB/Milvus/OpenSearch 클라이언트가 끌려온다. 그래서 두 파일은 **텍스트로 읽기만** 한다(import 0).
  - **LLM 0**: LLM 을 호출하지 않고 reply 를 생성하지 않는다(llm_invoked=False·reply_generated=False·network 0).
  - **runtime 0**: 이 감사는 어떤 런타임도 켜지 않는다(runtime_enabled_by_audit=False). 권고는 계획일 뿐이다.
  - secret 값 0(present/missing only). 출력에는 소스 텍스트 원문을 싣지 않는다(aggregate 분류 결과만).

2층 설계: classify_ai_replies_guard(PURE·주입 텍스트만) → build_ai_replies_guard_audit(텍스트 None 이면 commit 된
파일을 텍스트로 읽어 classify 호출 후 정직 불변을 하드코딩). 권고: admin token + feature flag +
community_interaction_future_gate(moderation/privacy/audit/source-citation/uncertainty) 를 갖추기 전에는 실제 reply
생성 금지, provider 를 openai 로 넘기지 말 것.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "ai_replies_guard_audit"

# ai_replies_guard_audit_status — 정적 감지 결과(endpoint 존재 여부로 키잉).
STATUS_UNGATED_MOCK = "ungated_mock_endpoint_detected"
STATUS_ENDPOINT_ABSENT = "endpoint_absent"

# ungated_risk — mock provider 가 실위험을 latent 로 완화(실제 LLM 호출이 아님).
UNGATED_RISK_MEDIUM_LATENT = "medium_latent_mock_provider"
UNGATED_RISK_LOW_GATED = "low_gated"
UNGATED_RISK_NONE = "none"

RECOMMENDED_ACTION = (
    "route behind admin token + feature flag + community_interaction_future_gate "
    "(moderation/privacy/audit/source-citation/uncertainty) before any real reply generation; "
    "do not flip provider to openai until gated"
)


def _ai_replies_mount_is_ungated(main_source: str) -> bool:
    """main_source 에서 `include_router(ai_replies.router)` 가 있는 **그 줄**이 require_admin_token 을 갖지 않으면
    ungated(=runtime 노출). 그 줄이 없으면 ungated=False(마운트 안 됨). per-line 검사라 다른 라우터의 admin-token
    dependency 에 오염되지 않는다."""
    for line in main_source.splitlines():
        if "include_router(ai_replies.router)" in line:
            return "require_admin_token" not in line
    return False


def classify_ai_replies_guard(*, route_source: str, main_source: str) -> dict:
    """주입된 소스 텍스트만으로 ai-replies 엔드포인트의 게이트 상태를 분류한다(PURE·import 0·LLM 0·network 0).

    endpoint_detected 는 라우터 prefix 와 POST 시그니처가 둘 다 있을 때만 True. llm_coupling 은 LLMClient 와
    `.complete(` 가 둘 다 있을 때 True. runtime_enabled(=ungated) 는 main_source 의 마운트 줄이 require_admin_token
    없이 존재할 때 True. moderation/privacy/audit/source-citation/uncertainty 게이트는 오늘 엔드포인트에 전무하므로
    전부 required(True)."""
    endpoint_detected = (
        'APIRouter(prefix="/api/ai-replies"' in route_source
        and '@router.post("/request"' in route_source
    )
    llm_coupling = ("LLMClient" in route_source) and (".complete(" in route_source)
    runtime_enabled = _ai_replies_mount_is_ungated(main_source)

    if endpoint_detected and runtime_enabled:
        ungated_risk = UNGATED_RISK_MEDIUM_LATENT
    elif endpoint_detected:
        ungated_risk = UNGATED_RISK_LOW_GATED
    else:
        ungated_risk = UNGATED_RISK_NONE

    status = STATUS_UNGATED_MOCK if endpoint_detected else STATUS_ENDPOINT_ABSENT

    return {
        "ai_replies_guard_audit_status": status,
        "endpoint_detected": endpoint_detected,
        "llm_coupling": llm_coupling,
        "runtime_enabled": runtime_enabled,
        # 오늘 엔드포인트에는 아래 게이트가 전무 → 전부 required(True).
        "requires_public_readiness": True,
        "requires_moderation": True,
        "requires_privacy_gate": True,
        "requires_audit_log": True,
        "requires_source_citation": True,
        "requires_uncertainty_policy": True,
        "ungated_risk": ungated_risk,
        "recommended_action": RECOMMENDED_ACTION,
    }


def build_ai_replies_guard_audit(
    *, route_source: Optional[str] = None, main_source: Optional[str] = None,
) -> dict:
    """commit 된 ai_replies.py·main.py 를 **텍스트로** 읽어(주입 시 그대로 사용) classify 한 뒤 정직 불변을 하드코딩.

    두 모듈을 절대 import 하지 않는다 — 텍스트 읽기만 한다. 경로는 이 파일을 기준으로 앵커링한다:
    이 파일 = backend/app/tools/ai_replies_guard_audit.py 이므로 parents[0]=backend/app/tools, [1]=backend/app,
    [2]=backend, [3]=repo root. (parents index 가 틀리면 read_text 가 FileNotFoundError 로 즉시 드러난다.)"""
    repo_root = Path(__file__).resolve().parents[3]
    if route_source is None:
        route_source = (repo_root / "backend" / "app" / "api" / "ai_replies.py").read_text(encoding="utf-8")
    if main_source is None:
        main_source = (repo_root / "backend" / "app" / "main.py").read_text(encoding="utf-8")

    out = {
        "operation_name": OPERATION_NAME,
        **classify_ai_replies_guard(route_source=route_source, main_source=main_source),
        # ── 정직 불변(하드코딩) — 이 감사는 보지만 만지지 않는다 ──
        "endpoint_modified": False,
        "llm_invoked": False,
        "reply_generated": False,
        "runtime_enabled_by_audit": False,
        "network_invoked": False,
        "secret_values_exposed": False,
    }
    _assert_pii_safe(out, _path="ai_replies_guard_audit_output")
    return out


def sanitized_ai_replies_guard_audit(out: dict) -> dict:
    """frontier 용 aggregate-only 투영(상태 + 핵심 불변 subset)."""
    return {
        "ai_replies_guard_audit_status": out["ai_replies_guard_audit_status"],
        "endpoint_detected": out["endpoint_detected"],
        "runtime_enabled": out["runtime_enabled"],
        "ungated_risk": out["ungated_risk"],
        "runtime_enabled_by_audit": out["runtime_enabled_by_audit"],
        "secret_values_exposed": out["secret_values_exposed"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#94 ai-replies ungated endpoint guard audit (AUDIT ONLY·엔드포인트 미수정·import 0·"
                     "LLM 0·reply 0·network 0·runtime 0·secret 값 0)."))
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_ai_replies_guard_audit()
    if ns.json:
        print(json.dumps(sanitized_ai_replies_guard_audit(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['ai_replies_guard_audit_status']}")
    print(f"- endpoint_detected={out['endpoint_detected']} llm_coupling={out['llm_coupling']} "
          f"runtime_enabled(ungated)={out['runtime_enabled']} ungated_risk={out['ungated_risk']}")
    print(f"- requires: public_readiness={out['requires_public_readiness']} moderation={out['requires_moderation']} "
          f"privacy={out['requires_privacy_gate']} audit_log={out['requires_audit_log']} "
          f"source_citation={out['requires_source_citation']} uncertainty={out['requires_uncertainty_policy']}")
    print(f"- recommended_action: {out['recommended_action']}")
    print(f"- invariants: endpoint_modified={out['endpoint_modified']} llm_invoked={out['llm_invoked']} "
          f"reply_generated={out['reply_generated']} runtime_enabled_by_audit={out['runtime_enabled_by_audit']} "
          f"network_invoked={out['network_invoked']} secret_values_exposed={out['secret_values_exposed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

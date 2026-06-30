"""ADR#94 — ai-replies ungated endpoint guard audit tests.

검증: endpoint 정적 감지(시그니처 둘 다 존재)·ungated(runtime_enabled True)·gated fixture 는 runtime_enabled False·
감사는 runtime 을 켜지 않음(runtime_enabled_by_audit False)·moderation/privacy/audit/source-citation/uncertainty
전부 required·reply 0(reply_generated False)·LLM 0(llm_invoked False)·endpoint 미수정(endpoint_modified False)·
실파일 default run 이 import 없이 실제 endpoint 를 감지·build 가 ai_replies/main 을 import 하지 않음.
"""
from __future__ import annotations

import sys

from backend.app.tools.ai_replies_guard_audit import (
    STATUS_ENDPOINT_ABSENT,
    STATUS_UNGATED_MOCK,
    UNGATED_RISK_MEDIUM_LATENT,
    build_ai_replies_guard_audit,
    classify_ai_replies_guard,
    sanitized_ai_replies_guard_audit,
)

# 주입 fixture — 실제 파일을 import 하지 않고 분류기를 결정적으로 구동하기 위한 정적 텍스트.
_FIXTURE_ROUTE_SOURCE = (
    "from fastapi import APIRouter\n"
    "from backend.app.services.llm_client import LLMClient\n"
    "\n"
    'router = APIRouter(prefix="/api/ai-replies", tags=["ai-replies"])\n'
    '_client = LLMClient(provider="mock")\n'
    "\n"
    "\n"
    '@router.post("/request", response_model=dict)\n'
    "async def request_ai_reply(req):\n"
    '    reply = _client.complete("x")\n'
    '    return {"reply": reply}\n'
)

# ai_replies 마운트 줄에는 require_admin_token 이 없음(admin 줄에는 있음 → per-line 검사가 오염되지 않음을 검증).
_FIXTURE_MAIN_UNGATED = (
    "app.include_router(comments.router)\n"
    "app.include_router(ai_replies.router)\n"
    "app.include_router(admin.router, dependencies=[Depends(require_admin_token)])\n"
)

# ai_replies 마운트 줄 자체에 require_admin_token 이 있음 → gated.
_FIXTURE_MAIN_GATED = (
    "app.include_router(comments.router)\n"
    "app.include_router(ai_replies.router, dependencies=[Depends(require_admin_token)])\n"
    "app.include_router(admin.router, dependencies=[Depends(require_admin_token)])\n"
)


def _ungated_audit() -> dict:
    return build_ai_replies_guard_audit(
        route_source=_FIXTURE_ROUTE_SOURCE, main_source=_FIXTURE_MAIN_UNGATED)


# ── endpoint 정적 감지(시그니처 둘 다 존재 → True) ──
def test_endpoint_detected_when_present():
    out = build_ai_replies_guard_audit(
        route_source=_FIXTURE_ROUTE_SOURCE, main_source=_FIXTURE_MAIN_UNGATED)
    assert out["endpoint_detected"] is True
    assert out["llm_coupling"] is True
    assert out["ai_replies_guard_audit_status"] == STATUS_UNGATED_MOCK


# ── 시그니처 부재 → endpoint_absent (다른 status 분기) ──
def test_endpoint_absent_when_signatures_missing():
    out = classify_ai_replies_guard(route_source="# no router here", main_source="# nothing mounted")
    assert out["endpoint_detected"] is False
    assert out["ai_replies_guard_audit_status"] == STATUS_ENDPOINT_ABSENT


# ── ungated endpoint 분류(runtime_enabled True·ungated_risk set) ──
def test_ungated_endpoint_classified():
    out = _ungated_audit()
    assert out["runtime_enabled"] is True
    assert out["ungated_risk"] == UNGATED_RISK_MEDIUM_LATENT


# ── gated fixture(마운트 줄에 require_admin_token) → runtime_enabled False ──
def test_gated_fixture_runtime_disabled():
    out = build_ai_replies_guard_audit(
        route_source=_FIXTURE_ROUTE_SOURCE, main_source=_FIXTURE_MAIN_GATED)
    assert out["runtime_enabled"] is False
    assert out["ungated_risk"] != UNGATED_RISK_MEDIUM_LATENT


# ── 감사 자체는 runtime 을 켜지 않는다 ──
def test_runtime_remains_disabled_by_audit():
    out = _ungated_audit()
    assert out["runtime_enabled_by_audit"] is False
    assert out["network_invoked"] is False


# ── 필수 게이트들이 전부 required(True) ──
def test_public_readiness_required():
    assert _ungated_audit()["requires_public_readiness"] is True


def test_moderation_required():
    assert _ungated_audit()["requires_moderation"] is True


def test_privacy_required():
    assert _ungated_audit()["requires_privacy_gate"] is True


def test_audit_log_required():
    assert _ungated_audit()["requires_audit_log"] is True


def test_source_citation_required():
    assert _ungated_audit()["requires_source_citation"] is True


def test_uncertainty_required():
    assert _ungated_audit()["requires_uncertainty_policy"] is True


# ── reply 생성 0 ──
def test_no_reply_generated():
    assert _ungated_audit()["reply_generated"] is False


# ── LLM 호출 0 ──
def test_no_llm_invoked():
    assert _ungated_audit()["llm_invoked"] is False


# ── endpoint 미수정 ──
def test_endpoint_not_modified():
    assert _ungated_audit()["endpoint_modified"] is False


# ── 권고에 admin token + openai flip 금지가 명시 ──
def test_recommended_action_mentions_gates_and_no_openai_flip():
    action = _ungated_audit()["recommended_action"]
    assert "admin token" in action
    assert "do not flip provider to openai" in action


# ── default 실파일 run(주입 없음) 이 import 없이 실제 endpoint 를 감지 ──
def test_default_real_file_detects_endpoint():
    out = build_ai_replies_guard_audit()
    assert out["endpoint_detected"] is True
    # 현재 commit 된 main.py 는 admin-token 없이 마운트 → ungated.
    assert out["runtime_enabled"] is True
    assert out["ai_replies_guard_audit_status"] == STATUS_UNGATED_MOCK


# ── build 가 ai_replies/main 을 import 하지 않음(정적 텍스트 reader 임을 증명) ──
def test_build_does_not_import_ai_replies_or_main():
    sys.modules.pop("backend.app.api.ai_replies", None)
    sys.modules.pop("backend.app.main", None)
    build_ai_replies_guard_audit()
    assert "backend.app.api.ai_replies" not in sys.modules
    assert "backend.app.main" not in sys.modules


# ── sanitized 투영은 build 출력의 subset ──
def test_sanitized_projection_subset():
    out = _ungated_audit()
    s = sanitized_ai_replies_guard_audit(out)
    assert set(s.keys()) <= set(out.keys())
    assert s["ai_replies_guard_audit_status"] == STATUS_UNGATED_MOCK
    assert s["runtime_enabled_by_audit"] is False

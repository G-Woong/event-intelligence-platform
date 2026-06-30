"""ADR#91 §9 — operator_payload_sourcing_workflow 테스트(real path/example path·검증/live 명령·체크리스트·draft live 불가).

operator_payload_status 주입으로 real payload 상태 분기를 결정론 검증(network 0·disk write 0). real path 부재라
미주입(disk read) 경로도 not_provided 로 수렴한다."""
from __future__ import annotations

from pathlib import Path

from backend.app.tools.operator_payload_sourcing_workflow import (
    SOURCING_PRESENT_INVALID_JSON,
    SOURCING_PRESENT_PII_OR_SECRET,
    SOURCING_PRESENT_VALIDATE,
    SOURCING_TEMPLATE_READY,
    build_operator_payload_sourcing_workflow,
    sanitized_operator_payload_sourcing,
)
from backend.app.tools.operator_regulatory_event_payload import (
    EXAMPLE_PAYLOAD_PATH,
    PAYLOAD_NOT_PROVIDED,
    PAYLOAD_PRESENT_INVALID_JSON,
    PAYLOAD_PRESENT_PII_OR_SECRET,
    PAYLOAD_PRESENT_VALID,
    REAL_PAYLOAD_PATH,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_KEYS = {"secret", "api_key", "reviewer_name", "email", "phone", "score", "rationale",
                   "predicted_status", "raw_body", "body", "model_score"}


def _walk_keys(obj: object):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_keys(item)


# ── §19-9: emits exact real path ────────────────────────────────────────────────────────────────────────────
def test_09_emits_exact_real_path():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["real_payload_path"] == REAL_PAYLOAD_PATH
    assert out["real_payload_path"] == "inputs/operator_events/operator_regulatory_event_payload.json"


# ── §19-10: emits example path ──────────────────────────────────────────────────────────────────────────────
def test_10_emits_example_path():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["example_payload_path"] == EXAMPLE_PAYLOAD_PATH


# ── §19-11: emits validation command ────────────────────────────────────────────────────────────────────────
def test_11_emits_validation_command():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["validation_command"]
    assert "operator_regulatory_event_payload" in out["validation_command"]
    assert REAL_PAYLOAD_PATH in out["validation_command"]


# ── §19-12: emits manual live command ───────────────────────────────────────────────────────────────────────
def test_12_emits_manual_live_command():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["live_command"]
    assert "operator_confirmed_live_runner" in out["live_command"]
    assert out["live_command_is_manual_step"] is True


# ── §19-13/14/15: draft cannot trigger live · operator_confirmed/live_approved false ─────────────────────────
def test_13_14_15_draft_cannot_trigger_live():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["draft_can_trigger_live"] is False
    assert out["operator_confirmed_in_draft"] is False
    assert out["live_approved_in_draft"] is False
    assert out["code_writes_operator_confirmed_true"] is False
    assert out["code_writes_live_approved_true"] is False
    assert out["code_writes_real_payload_path"] is False
    assert out["code_fabricated_confirmed_event"] is False


# ── §19-16: real path gitignored ────────────────────────────────────────────────────────────────────────────
def test_16_real_path_gitignored():
    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "inputs/operator_events/" in gitignore
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["real_payload_path_gitignored"] is True


# ── §19-17: no secret/PII in workflow output ────────────────────────────────────────────────────────────────
def test_17_no_secret_pii_in_output():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    keys = set(_walk_keys(out))
    assert keys.isdisjoint(_FORBIDDEN_KEYS), keys & _FORBIDDEN_KEYS


# ── §19-8: missing payload creates actionable next_action ────────────────────────────────────────────────────
def test_08_missing_payload_actionable_next_action():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["payload_sourcing_status"] == SOURCING_TEMPLATE_READY
    assert out["real_payload_present"] is False
    assert out["next_action"].strip()
    assert REAL_PAYLOAD_PATH in out["next_action"]
    # 행동 가능한 번호 체크리스트(6단계: 템플릿→채움→저장→검증→승인→live).
    assert len(out["operator_action_checklist"]) == 6
    assert any("Save the filled JSON" in s for s in out["operator_action_checklist"])


# ── present_valid → validate-then-approve 분기 ────────────────────────────────────────────────────────────────
def test_present_valid_branches_to_validate():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_PRESENT_VALID)
    assert out["payload_sourcing_status"] == SOURCING_PRESENT_VALIDATE
    assert out["real_payload_present"] is True
    assert any("Validate the present payload" in s for s in out["operator_action_checklist"])


# ── present_invalid_json → invalid 분기 ──────────────────────────────────────────────────────────────────────
def test_present_invalid_json_branch():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_PRESENT_INVALID_JSON)
    assert out["payload_sourcing_status"] == SOURCING_PRESENT_INVALID_JSON
    assert any("not parseable as a JSON object" in s for s in out["operator_action_checklist"])


# ── present_pii_or_secret → fail-closed 분기 ─────────────────────────────────────────────────────────────────
def test_present_pii_or_secret_branch():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_PRESENT_PII_OR_SECRET)
    assert out["payload_sourcing_status"] == SOURCING_PRESENT_PII_OR_SECRET
    assert any("forbidden secret/PII/score keys" in s for s in out["operator_action_checklist"])


# ── disk-read 경로(status 미주입) → real path 부재라 not_provided 로 수렴 ──────────────────────────────────────
def test_disk_read_path_resolves_not_provided_when_absent():
    out = build_operator_payload_sourcing_workflow()
    assert out["operator_payload_status"] == PAYLOAD_NOT_PROVIDED
    assert out["payload_sourcing_status"] == SOURCING_TEMPLATE_READY


# ── read-API 안전(adversarial LOW-1 회귀 락): status 주입 시 real-path 디스크 리더 미호출 ─────────────────────
def test_status_injected_does_not_read_real_payload_disk(monkeypatch):
    """GET-path(frontier)는 operator_payload_status 를 주입한다 → load_operator_regulatory_event_payload(real path 리더)
    가 호출되지 않아야 한다. 주입 누락 회귀가 생기면 이 테스트가 깨진다(CARDINAL read-API 안전 강화)."""
    import backend.app.tools.operator_payload_sourcing_workflow as mod

    def _must_not_be_called(*_a, **_k):
        raise AssertionError("real-path disk reader must NOT be called when operator_payload_status is injected")

    monkeypatch.setattr(mod, "load_operator_regulatory_event_payload", _must_not_be_called)
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert out["payload_sourcing_status"] == SOURCING_TEMPLATE_READY
    assert out["real_payload_present"] is False


# ── safety_notes 필수(불변 안전수칙 노출) ──────────────────────────────────────────────────────────────────────
def test_safety_notes_present():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    assert len(out["safety_notes"]) >= 5
    assert any("gitignored" in n for n in out["safety_notes"])
    assert any("does not run a live query" in n for n in out["safety_notes"])


# ── sanitized 투영(aggregate-only·template 본문/명령 제외) ────────────────────────────────────────────────────
def test_sanitized_projection():
    out = build_operator_payload_sourcing_workflow(operator_payload_status=PAYLOAD_NOT_PROVIDED)
    s = sanitized_operator_payload_sourcing(out)
    assert set(s) == {"payload_sourcing_status", "operator_payload_status", "real_payload_present",
                      "draft_template_ready", "missing_required_field_count", "draft_can_trigger_live",
                      "payload_sourcing_next_action"}
    assert "payload_template" not in s
    assert "validation_command" not in s

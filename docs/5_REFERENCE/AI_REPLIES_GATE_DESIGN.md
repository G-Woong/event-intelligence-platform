# AI_REPLIES_GATE_DESIGN (ADR#95)

> Status: **FUTURE GATE-DESIGN/CONTRACT-ONLY · runtime 0 · LLM 0 · 엔드포인트 미수정 · RUNTIME No-Go**. comment/reply
> runtime 을 열기 위해 반드시 통과해야 할 게이트 10개를 하나의 계약으로 열거한다(정적 감사를 한 걸음 넘어선다). 코드:
> `backend/app/tools/ai_replies_gate_design.py` (ai_replies.py import/수정 0·reply 생성 0·network 0).

## 0. 목적

ADR#94 `ai_replies_guard_audit` 는 `POST /api/ai-replies/request` 가 admin-token 없이 마운트된 ungated·mock
엔드포인트라는 **사실을 정적 감사**하지만, 실제 comment/reply runtime 을 열기 위해 반드시 통과해야 할 **게이트 집합**을
하나의 계약으로 열거하지는 않는다. 이 모듈이 그 결손을 메우는 미래 gate-design 계약이다 — 필요한 게이트 10개를
열거하고(must_pass=True) 각 충족 여부·출처를 표면화하며, 4개 차단 게이트 중 하나라도 미충족이면 BLOCKED 다. 이
모듈은 게이트를 **설계**할 뿐이고 어떤 runtime 도 열지 않는다.

## 1. 진입점

```
build_ai_replies_gate_design(*, satisfied=None) -> dict   # satisfied: gate_name→충족여부 맵(None=전부 미충족)
보조: sanitized_ai_replies_gate_design(out) · main(--json)
```

## 2. 상태 vocab (`ai_replies_gate_design_status`)

```
GATE_DESIGN_READY   = "gate_design_ready_runtime_disabled"          # 차단 게이트 전부 충족(그래도 runtime_disabled)
GATE_DESIGN_BLOCKED = "gate_design_blocked_required_gate_missing"   # 차단 게이트 하나라도 미충족
```

차단 게이트 4개 = {public_readiness_gate, moderation_gate, privacy_gate, audit_log_gate}.

## 3. 핵심 출력 필드

```
ai_replies_gate_design_status · required_gates(10) · required_gate_count · blocking_gates · unmet_blocking_gates
current_endpoint_status · ai_replies_guard_audit_status · runtime_enabled · reply_generation_enabled · recommended_next_steps
```

- 게이트 10개: audit 파생 6(public_readiness/moderation/privacy/audit_log/source_citation/uncertainty_policy) + community
  파생 2(rate_limit_gate·human_override_gate, `COMMUNITY_GATE_REQUIREMENTS` 에서 파생) + net-new 2(llm_provider_gate·prompt_safety_gate).
- `current_endpoint_status="ungated_mock_endpoint"` 는 main.py:79 라이브 라우트의 **사실**(audit passthrough)이다 —
  계약의 `runtime_enabled=False` 는 **설계 latch** 일 뿐 엔드포인트가 gated 라는 주장이 아니다.

## 4. 불변식 (절대 금지·설계만 한다, 만지지 않는다)

```
runtime_enabled=False · reply_generation_enabled=False · endpoint_modified=False
llm_invoked=False · reply_generated=False · prompt_executed=False · public_post_body_generated=False
network_invoked=False · production_gold_count=0
```

- `ai_replies.py` 를 import 하지도 수정하지도 않는다(audit 는 정적 텍스트 reader) · 어떤 reply 도 LLM 도 호출하지 않는다 ·
  `_assert_pii_safe` 재귀 가드.
- 이번 턴: comment/reply runtime 은 정직한 No-Go · R1 gap 200 · R2~R7 No-Go · LLM/embedding/merge/DB/public-IU/Hot-Post/
  comment runtime disabled.

## 5. 합성하는 기존 모듈

- `ai_replies_guard_audit.build_ai_replies_guard_audit` (audit 파생 6 게이트·`current_endpoint_status`·
  `ai_replies_guard_audit_status` passthrough).
- `community_interaction_future_gate.COMMUNITY_GATE_REQUIREMENTS` (rate_limit·human_override 파생·미존재 시 import 시
  fail-loud) · `reviewer_pilot_handoff._assert_pii_safe`.
- 테스트: `backend/tests/test_ai_replies_gate_design.py` — 14개(전부 통과).

## 6. 이것이 아니다

- 엔드포인트 gating 이 **아니다** — `current_endpoint_status="ungated_mock_endpoint"` 는 현재 commit 된 라우트의 사실이고,
  이 계약은 그것을 고치지 않는다(endpoint_modified=False).
- LLM 호출/reply 생성/prompt 실행/public post body 생성을 하지 않는다(runtime_enabled=False·reply_generation_enabled=False).
- merge 0 · network 0 · production gold 0 — 게이트를 설계할 뿐, 차단 게이트가 모두 통과하고 reviewer 가 승인할 때까지 닫힘.

Status: ADR#95 · runtime 0

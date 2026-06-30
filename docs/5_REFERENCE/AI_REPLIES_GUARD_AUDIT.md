# AI_REPLIES_GUARD_AUDIT (ADR#94)

> Status: **AUDIT-ONLY/STATIC · 엔드포인트 미수정 · RUNTIME No-Go**. ungated 한 `POST /api/ai-replies/request`
> mock 엔드포인트를 **정적 소스 텍스트로만** 감지·분류하고 필요한 게이트를 권고한다 — 엔드포인트를 고치지 않는다.
> 코드: `backend/app/tools/ai_replies_guard_audit.py` (import 0·LLM 0·reply 0·network 0·runtime 0·secret 값 0).

## 0. 목적

`backend/app/api/ai_replies.py` 는 `POST /api/ai-replies/request` 를 `LLMClient(provider="mock")` 로 정의하고,
`backend/app/main.py` 가 이를 **admin-token dependency 없이** 마운트한다(인접 라우터는 게이트됨) — 즉 public·
unauthenticated·ungated 다. 이 모듈은 그 사실을 감사해 *기록된 ungated-path 위험* 과 *권고 게이트* 를 남긴다. 두 파일은
**텍스트로만 읽는다**(import 0) — `ai_replies` 를 import 하면 로드 시 `LLMClient(provider="mock")` 가, `main` 을 import
하면 DB/Milvus/OpenSearch 클라이언트가 끌려오기 때문이다. 엔드포인트는 **수정하지 않는다**(endpoint_modified=False).

## 1. 진입점

```
classify_ai_replies_guard(*, route_source, main_source) -> dict          # PURE·주입 텍스트만
build_ai_replies_guard_audit(*, route_source=None, main_source=None) -> dict  # None 이면 commit 파일을 텍스트로 읽음
보조: sanitized_ai_replies_guard_audit(out) · main(--json)
```

repo_root = `Path(__file__).resolve().parents[3]`(틀리면 read_text 가 즉시 FileNotFoundError 로 드러남).

## 2. 상태 vocab (`ai_replies_guard_audit_status` / `ungated_risk`)

```
status: STATUS_UNGATED_MOCK = "ungated_mock_endpoint_detected" · STATUS_ENDPOINT_ABSENT = "endpoint_absent"
risk:   UNGATED_RISK_MEDIUM_LATENT = "medium_latent_mock_provider"  # detected ∧ ungated
        UNGATED_RISK_LOW_GATED = "low_gated" · UNGATED_RISK_NONE = "none"
```

`endpoint_detected` = 라우터 prefix ∧ POST 시그니처 둘 다 · `runtime_enabled`(=ungated) = 마운트 *그 줄* 에
require_admin_token 부재(per-line 검사라 다른 라우터 의존성에 오염 0).

## 3. 핵심 출력 필드

```
ai_replies_guard_audit_status · endpoint_detected · llm_coupling · runtime_enabled
requires_public_readiness · requires_moderation · requires_privacy_gate · requires_audit_log
requires_source_citation · requires_uncertainty_policy(전부 True) · ungated_risk · recommended_action
```

- 오늘 엔드포인트에 위 게이트가 전무하므로 6개 require 가 전부 True · `recommended_action` 은 admin token + feature
  flag + community_interaction_future_gate 를 갖추기 전 reply 생성 금지·provider 를 openai 로 flip 금지를 명시.

## 4. 불변식 (절대 금지·본다, 만지지 않는다)

```
endpoint_modified=False · llm_invoked=False · reply_generated=False
runtime_enabled_by_audit=False · network_invoked=False · secret_values_exposed=False
```

- 감사는 어떤 런타임도 켜지 않는다(`runtime_enabled` 는 *기존* 노출의 관측이고 `runtime_enabled_by_audit` 는 항상
  False) · 출력에 소스 원문을 싣지 않는다(`_assert_pii_safe` 재귀 가드).
- 이번 턴: real payload 미존재가 정직한 block · production_gold_count 0 · R1 gap 200 · R2~R7 No-Go ·
  LLM/embedding/merge/DB/public-IU/Hot-Post/comment runtime disabled.

## 5. 합성하는 기존 모듈

- `community_interaction_future_gate` (권고 게이트 묶음: moderation/privacy/audit/source-citation/uncertainty) — 인용.
- `backend/app/api/ai_replies.py` · `backend/app/main.py` — **텍스트로 읽기만**(import 0).
- `reviewer_pilot_handoff._assert_pii_safe`.
- 테스트: `backend/tests/test_ai_replies_guard_audit.py` — 18개(전부 통과).

## 6. 이것이 아니다

- 엔드포인트 수정이 **아니다** — 이 감사는 ungated-path 위험을 *기록* 하고 게이트를 *권고* 할 뿐 마운트를 바꾸지 않는다.
- LLM 호출이 아니다 · reply 생성이 아니다 · 두 모듈을 import 하지 않는다.
- 권고는 계획일 뿐 — gate 를 갖추기 전엔 실제 reply 생성·openai provider flip 금지.

Status: ADR#94 · runtime 0

# PUBLIC_RUNTIME_KILL_SWITCH_MAP (ADR#94)

> Status: **KILL-SWITCH/ALL-DISABLED · override 불가 · RUNTIME No-Go**. 8개 public runtime 을 한 곳에서 **기본
> DISABLED** 로 선언하고, 각 runtime 이 *이미 어디서 강제되는지* 를 단일 출처 게이트로 compose/cite 한다(truth 재선언 0).
> 코드: `backend/app/tools/public_runtime_kill_switch_map.py` (어떤 runtime 도 켜지 않음·network/DB/LLM/embedding/전송 0).

## 0. 목적

미래 제품은 hot post 공개 게시·댓글 응답·public IU·LLM 생성·embedding·KG·DB write·실제 발송 같은 **공개 runtime** 을
연다. 그러나 그 무엇도 R1(production gold)·R2(MERGE_GATE) 가 끝나고 명시 ADR + tests 가 갖춰지기 전엔 열려선 안 된다.
이 모듈은 그 kill-switch map 이다 — 8개 runtime 의 disabled 를 선언하되, comment_reply·public_hot_post 는 순수(no I/O)
단일 출처 게이트에서 **파생** 하고, 나머지 6개는 무거운 모듈(`internal_ops_preflight` 은 호출 시 filesystem 스캔 +
settings 접근으로 **순수하지 않음**)을 *import 하지 않고* 기존 상수를 **static citation 문자열** 로만 인용한다.

## 1. 진입점

```
build_public_runtime_kill_switch_map(*, r1_satisfied=False, r2_satisfied=False) -> dict
보조: sanitized_public_runtime_kill_switch_map(out) · main(--json)
```

## 2. 상태 vocab (`public_runtime_kill_switch_status`)

```
PRKS_ALL_DISABLED = "public_runtime_kill_switch_all_disabled"
```

8개 차원(순서 고정·전부 disabled): public_hot_post · comment_reply · public_iu · llm_generation · embedding ·
kg · db_write · actual_sending. 집합이 `PUBLIC_RUNTIME_DIMENSIONS` 에서 drift 하거나 하나라도 enabled 면 fail-loud.

## 3. 핵심 출력 필드

```
public_runtime_kill_switch_status · all_public_runtime_disabled · disabled_dimensions(8·dimension/disabled/enforced_by)
disabled_dimension_count · references_community_interaction_gate · references_hot_post_gate_alignment
required_gates(r1_production_gold/r2_merge_gate/explicit_runtime_override_adr/override_tests)
r1_satisfied · r2_satisfied · gate_inputs_satisfied · explicit_adr_and_tests_present
operator_override_allowed · override_requires_tests · override_requires_explicit_adr · recommended_action
```

- comment_reply 의 disabled 는 gate 의 `comment_reply_generation=False`(ADR#90), public_hot_post 는
  `runtime_enabled=False`∧`publishable=False`(ADR#91 §13)에서 파생(재선언 0).

## 4. 불변식 (절대 금지)

```
operator_override_allowed=False · override_requires_tests=True · override_requires_explicit_adr=True
public_post_body_generated=False · comment_reply_generated=False · db_write=False · llm_invoked=False
embedding_invoked=False · actual_sending_performed=False · merge_allowed=False · network_invoked=False · public_iu_allowed=False
```

- override = `(r1 ∧ r2) ∧ explicit_adr_and_tests_present` — r1/r2 입력은 gate 를 demonstrably 떨어뜨리고, 마지막 항은
  이번 턴 False(ADR#94 는 contract/planning-only)라 **항상 False**(`_assert_pii_safe` 재귀 가드).
- 이번 턴: real payload 미존재가 정직한 block · production_gold_count 0 · R1 gap 200 · R2~R7 No-Go ·
  LLM/embedding/merge/DB/public-IU/Hot-Post/comment runtime disabled.

## 5. 합성하는 기존 모듈

- `community_interaction_future_gate` (comment_reply disabled 파생·pure) · `hot_post_gate_alignment`
  (public_hot_post disabled 파생·pure)
- cite-only(import 0): `internal_ops_preflight`(public IU/KG/DB/sending No-Go) · config 기본 `LLM_PROVIDER`/
  `EMBEDDING_PROVIDER='mock'` · `reviewer_pilot_handoff`(actual_sending_performed=False).
- 테스트: `backend/tests/test_public_runtime_kill_switch_map.py` — 19개(전부 통과).

## 6. 이것이 아니다

- 어떤 runtime 도 켜지 않는다 · operator override 는 R1 gold ∧ R2 MERGE_GATE ∧ 명시 ADR ∧ passing tests 가 모두일
  때만 가능 — 이번 턴 전부 미충족이라 kill switch 가 유지된다.
- truth 를 재선언하지 않는다(게이트를 신뢰·compose) · 무거운 비순수 모듈을 import 하지 않는다.
- public post body·comment reply·public IU·LLM·embedding·KG·DB write·발송을 만들지 않는다.

Status: ADR#94 · runtime 0

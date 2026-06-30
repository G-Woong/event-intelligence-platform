# LIVE_ATTEMPT_PACK_CONTRACT (ADR#92)

> Status: **CONTRACT/BUILDER · operator-fill required · RUNTIME No-Go**. real operator payload 가 없을 때 curated seed
> bank 에서 operator 가 바로 채울 수 있는 regulatory event 후보 묶음(pack)을 만든다. 코드:
> `backend/app/tools/live_attempt_pack_builder.py` (event fabricate 0·network 0).

## 0. 왜 필요한가

sourcing workflow 는 *하나의* selected seed → 템플릿 + 운영 절차만 주고, operator 가 "지금 어떤 regulatory event
후보들 중에서 골라 채워야 하는가" 를 한눈에 보여주지 못했다. real payload 가 아직 없을 때 operator 가 바로 검토·선택·
채울 수 있는 **후보 묶음(live attempt pack)** 이 필요하다. 이 모듈은 curated seed bank + authoring helper 위에 thin
합성만 한다(재구현 0). pack 은 real payload 가 **아니다** — operator-fill 경로를 거쳐야 live 가 된다:

```
pick candidate → confirm occurrence → fill payload → drop to real_payload_path → validate → approve → run live
```

## 1. candidate event shape (14필드·`build_candidate_event_shape`)

curated regulatory seed → operator-fillable candidate 한 건. agency/action/window/query/angle 는 authoring helper
템플릿에서 가져온다(operator_confirmed/live_approved 강제 False 패턴 상속).

```
candidate_id · regulatory_domain · agency_or_entity · action_phrase
date_window_start · date_window_end · official_query_draft · news_query_draft
expected_news_angle · source_strategy · risk_notes
operator_must_verify_occurrence · operator_must_set_confirmed · operator_must_set_live_approved
```

- `operator_must_*` 3필드는 항상 `True` — 후보는 발생 미확인·confirmed/approved 미설정이며, **코드가 event 를 단정하지
  않는다**(operator 가 발생을 확인하고 confirmed/approved 를 직접 설정해야 live).
- `source_strategy` 는 official(authoritative evidence·window-honoring) × news(public reporting·enforce_window) 를 한
  줄로 표면화 — **NOT same role**, bridge=reviewer-routing only.

## 2. pack 출력 (불변·`build_live_attempt_pack`)

```
live_attempt_pack_status · candidate_count · operator_fill_required
all_candidates_operator_confirmed_false · all_candidates_live_approved_false
validation_command · manual_live_command · safety_notes · next_action
```

- `live_attempt_pack_status` ∈ {`live_attempt_pack_ready_operator_fill_required`,
  `real_payload_present_pack_optional`, `no_candidate_event_shapes_available`}.
- real payload(valid present)면 `real_payload_present_pack_optional`(검증/승인으로 진행), 후보 seed 가 없으면
  `no_candidate_event_shapes_available`, 그 외 `live_attempt_pack_ready_operator_fill_required`.
- `all_candidates_operator_confirmed_false=True` ∧ `all_candidates_live_approved_false=True` — 모든 후보가 live 를
  트리거할 수 없음을 underlying 템플릿으로 증명. `validation_command`/`manual_live_command` 는 단일 출처 재사용(수동·
  문서화만·코드가 실행 0).

## 3. 불변 경계

```
pack 은 DRAFT 후보 집합 — confirmed event 아님
candidate 는 operator_confirmed=false ∧ live_approved=false (live 트리거 불가)
code_claims_event_occurred=false · code_writes_real_payload_path=false · code_invokes_network=false · code_reads_disk=false
same_event_asserted=false · merge_allowed=false · production_gold_count=0
```

- pack 은 R1 gold floor(live ≥200 / KO ≥50·actual returned human labels) 의 *입력 전 단계* — 후보→발생확인→fill→live→
  freeze→reviewer→gold 경로에서 가장 앞단이며, pack 자체는 gold/merge 와 무관(`production_gold_count=0`).
- real payload 는 commit 금지·secret/API key/reviewer PII 금지(`_assert_pii_safe` 재귀 가드).

## 4. Cross-links

- `R1_FIRST_CONTACT_PROTOCOL.md` (pack→live→freeze 이후 reviewer first-contact·gold 승격)
- `HOT_POST_PREVIEW_GUARD.md` (gold/merge 이후 preview·게시 경계)
- `RAG_KG_AGENT_READINESS.md §6b` (R1 gold floor·현재 R1=FAIL·R2~R7 No-Go)
- `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md §9` (커뮤니티형 제품 방향)

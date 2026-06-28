# LLM Evidence Packet Contract

> **Status: CONTRACT-ONLY · runtime No-Go (ADR#78).**
> 이 문서는 미래 LLM 판단층(§4 stage④ semantic real merge·adjudicator, 그리고 R7 Intelligence Unit synthesis)이
> **무엇을 보고·추론·인용·단정하지 못하는가**를 못박는 계약이다. **이번 시점 실 LLM 호출 0**(`llm_invoked=False`·
> `embedding_invoked=False`). R1 production gold floor(≥200 / KO ≥50) → MERGE_GATE(precision≥0.98·FPR≤0.01·
> hard-neg FP=0) 가 충족되기 전에는 이 계약의 어떤 항목도 runtime 으로 켜지지 않는다.
> 관련: `INTELLIGENCE_UNIT_CONTRACT.md` §4, `RAG_KG_ENTITY_GATE_CONTRACT.md`, `RAG_KG_AGENT_READINESS.md` §6b.

## 0. 왜 이 계약이 필요한가 (ADR#78 근거)

ADR#77/#78 의 실측: 결정론 near-match detector 는 **고정밀·저재현**이다(`cross_source_dedup._title_tokens`:
소문자+stopword+len>1, **stemming/entity 정규화 없음**). targeted live(fed_rate·7d)에서도 guardian×nyt 30
cross-source 비교쌍 전부 below hard floor(max title Jaccard 0.0526·최고중첩 쌍조차 generic 토큰만 공유). 그 0 의
원인은 (i) 같은 사건 paraphrase recall 한계인지 (ii) 서로 다른 사건인지 **단일 run 으로 미확정**이다.

따라서 LLM 은 "결정론이 못 잡은 same-event 를 메우는" 유혹의 자리에 선다. 그러나 LLM 이 같은 사건을 **단정**하면
false-merge 가 production 으로 샌다. 이 계약은 LLM 을 **evidence-bounded·source-role-aware·MERGE_GATE-gated·
uncertainty-explicit** 역할로 가둔다.

## 1. LLM 이 볼 수 있는 것 (allowed inputs)

- 정규화된 title / headline (≤512자), canonical_url, source/provider id, published_at / observed_at
- source_role (official / article / news / community / market / catalog / search / unknown)
- language, topic / query seed, normalized title tokens, date proximity, URL host
- 결정론 신호: title-token Jaccard, fingerprint 일치 여부, band(fingerprint/near/hard/below_floor)
- identity 상태: stage①anchor / ②link(possible) / ③shadow adjudication(likely_same/ambiguous/likely_different/insufficient)
- uncertainty flags, source agreement/disagreement 신호, reviewer label(있을 때·gold 무결성 검증된 것만)

## 2. LLM 이 볼 수 없는 것 (forbidden inputs)

- raw full body / 전문, API key / secret / `.env` 값, reviewer raw PII(name/email/phone)
- 다른 모델이 생성한 same_event 판정(순환 truth 금지), reviewer 에게 노출될 model rationale
- 미검증 corpus 를 retrieval 로 직접(see `RAG_KG_ENTITY_GATE_CONTRACT.md` — provenance/identity gate 우회 금지)

## 3. LLM 이 추론할 수 있는 것 (may infer) — 단, **제안일 뿐 truth 아님**

- 두 관측이 **같은 사건일 가능성**(점수/확률) — candidate hint 로서. **병합 authority 없음.**
- source 간 동의/불일치, 시계열 update 관계 후보, entity 후보(provenance 필요)
- 불확실성 수준, 추가 수집이 필요한 지점

## 4. LLM 이 반드시 인용해야 하는 것 (must cite)

- 모든 주장은 **publishable evidence(official/article/news)** 의 canonical_url + published_at 로 근거를 단다.
- official 근거와 community/market/rumor 신호를 **분리 표기**한다(혼합 금지).
- 근거가 없으면 "unverified" 로 명시한다(합성 서사 금지).

## 5. LLM 이 절대 단정하지 못하는 것 (must NOT assert)

- **same_event 확정** — MERGE_GATE(precision≥0.98·FPR≤0.01·hard-neg FP=0) + production gold floor 충족 **전까지**
  같은 사건이라고 단정하거나 병합을 트리거할 수 없다. stage④ 는 gate 통과 후에만 활성.
- community reaction 을 **사실 근거**로 승격, market 신호를 **사건 확정**으로 승격, search 결과를 **truth** 로 사용
- rumor/추측을 official 과 동급으로 제시, uncertainty 를 숨긴 단정적 서사
- reviewer label 없이 production gold 생성, score 를 truth 로 사용

## 6. uncertainty flags (필수 출력)

`same_event_confidence`(낮음일수록 보류), `evidence_sufficiency`(insufficient/partial/sufficient),
`source_agreement`(agree/mixed/disagree/single_source), `merge_gate_status`(blocked/eligible), `unverified_claim`(bool),
`community_reaction_only`(bool), `requires_human_review`(bool).

## 7. source-role boundary (불변)

| role | LLM 사용 |
|---|---|
| official / article / news | event **anchor 가능**(publishable) — 단 same_event 단정은 MERGE_GATE 후 |
| community | **reaction layer only** — `reaction_to` 로만 attach(see KG contract) |
| market | signal layer only — `market_signal_for` 는 verified entity/event link 필요 |
| catalog | enrichment only — anchor 아님 |
| search | **URL candidate only** — truth 아님·publishable canonical 로 해소 후에만 |
| unknown | anchor 거부(fail-closed) |

## 8. MERGE_GATE dependency (계약의 핵심 잠금)

LLM adjudicator(stage④)는 다음을 **모두** 충족하기 전 실 병합 0:
1. production gold floor: live ≥200 / KO ≥50 / pos ≥67 / neg ≥67 / hard-neg ≥20 / reviewer ≥2 (현재 **0** — FAIL)
2. MERGE_GATE: precision ≥0.98 · FPR ≤0.01 · hard-neg FP=0 (현재 결정론 adjudicator precision 0.57 — 미달)
3. uncertainty/calibration 통과

미충족 시 LLM 출력은 **candidate hint + uncertainty** 로만 남고, no_merge_without_gold 가 강제된다.

## 9. 이 계약이 잠그는 실패 모드

- "LLM 이 판단했으니 same_event 확정" → §5/§8 로 차단
- "near-match 0 이니 바로 LLM 으로 메운다" → §0/§8: 먼저 데이터 acquisition/결정론 recall(normalization·provider breadth)·
  reviewer gold 를 정비. LLM 은 gate 후 보조.
- "community 반응이 많으니 사실" → §5/§7: reaction layer only
- raw body / secret / PII 가 packet 에 유입 → §2 forbidden inputs

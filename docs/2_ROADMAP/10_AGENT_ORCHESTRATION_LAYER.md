# 10 — AGENT ORCHESTRATION LAYER (L10)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 📘 REFERENCE — LangGraph/Deep Agents 프레임워크 결정서(현재상태 정합). 새 방향(ADR#14) 반영.
> │ **구현순위:** #7 (00_ROADMAP_INDEX) · **그룹:** B
> │ **검증 근거:** 코드 산출물 아님(프레임워크 결정 청사진). 0.2.76 유지·DeepAgents 0건은 `16`에서 사실검증 정확. 11+14노드·`_ALLOWED_BY_LAYER`·`_UNSAFE_STRATEGIES`는 실구현(`_CANONICAL/12`).
> │ **잔여(미구현):** 6 mock 노드 실연결, P/G/F audit trace 배선, Agent Debate 별개 그래프.
> │ **완료정의(DoD):** N/A(설계 문서) — 6 mock 해제 + audit 배선의 구현으로 충족.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> 결론: LangGraph 0.2.76 **유지**가 옳다(11노드는 수초 내 완결 무상태 파이프라인, checkpointer 미사용). Deep Agents/OpenAI SDK/CrewAI 도입은 **현 단계 불필요** — 근거는 "수집이 deterministic이라서"가 **아니라**, LLM 수집 관여를 **P/G/F 3층 경계**(LAYER G 게이트가 비결정성·우회를 결정론으로 검문)로 닫았기 때문이다(ADR#14). 게이트가 검문하므로 Deep Agents의 동적 계획 자율성이 불필요하다. 진짜 작업은 6개 mock 노드 해제 + P/G/F audit trace 배선이다. **Event 토대(S1)·Agent Debate(별개 신규 그래프)는 본 그래프와 분리**된다.

---

## 1. 현재 상태

- 다운스트림 `event_processing_graph.py` 11노드: **5 REAL**(source_parse/normalize_event/retrieve_past_context/publish_or_hold + partial deduplicate) / **6 MOCK**(entity_linking/sector_mapping/impact_analysis/evidence_check/fact_check/final_writer).
- ingestion 크롤링 그래프(14노드, 조건부 엣지/retry_decision/strategy ladder) IMPLEMENTED.
- `BaseLLMClient` Protocol(complete/complete_json schema), 무상태, 예외 전파 안 함(실패→None→안전 기본값). mock↔openai = env 토글.
- tool registry 골격: `_ALLOWED_BY_LAYER` + `_UNSAFE_STRATEGIES`(proxy_rotation/captcha_bypass 영구 차단). LLM 제안은 allowed 안에서만 채택.

## 2. LangGraph 0.2.76 유지 vs 1.0 업그레이드

| | 유지(0.2.76) | 1.0 업그레이드 |
|---|---|---|
| 가치 | 안정, 회귀 0 | durable execution/checkpointing/HITL |
| 비용 | 0 | langchain 0.2.11 핀 해제, API surface 변경, 11+14노드 회귀 |
| 판단 | **현재 적합**(무상태 단발 invoke) | redis checkpointer 전환 시점에 동시 평가 |

> 1.0(2025-10 GA)이 기본 런타임이 됐으나, durable execution은 "장기 실행 중단·재개·승인"이 실제 요구로 등장할 때 값을 한다. 아직 그 요구가 없다.

## 3. Deep Agents / 벤더 SDK 도입 판단

- **deepagents**(create_deep_agent/write_todos/subagent/context offloading): "에이전트가 동적으로 계획"이 필요할 때 값. **LLM 수집 관여(ADR#14)가 도입돼도** LAYER P의 계획은 `_ALLOWED_BY_LAYER` 게이트(LAYER G) 안으로 닫히므로, 동적 자율 계획 프레임워크는 여전히 불필요. 게이트가 비결정성을 검문한다.
- OpenAI Agents SDK/CrewAI: 1-2툴엔 가볍지만, 이미 LangGraph stateful/audit/HITL + LangSmith 관측에 투자 → 프레임워크 추가는 관측·감사 일관성을 깨뜨림.
- 결론: **미도입 결정을 문서화**하고 LangGraph 일관성 유지.
- **Agent Debate Layer는 별개 신규 그래프**(ADR#15·S9): 수집/이벤트 처리 그래프와 분리된 독립 LangGraph로 설계한다(에이전트 해설/논쟁 = 커뮤니티 성장엔진·트래픽). 본 11노드 파이프라인에 끼워넣지 않는다 — 감사 경계·실패 격리·투자조언 금지(R-AgentDebateSafety) 때문. 상세 = `19 §9`. **선행: Event 토대(S1) cross-ref** — 논쟁 대상이 Event 객체이므로 S1 이후 착수.

## 4. 장기 supervisor vs 단기 judge 분리 (둘 다 LAYER P)

- **judge**: 단발·무상태(complete_json 1회, 실패 None), 노드 안에 산다. **LAYER P(계획)**에 속함 — 판단만 하고 실행은 LAYER F가.
- **SourceSupervisor**: 실패 누적·전략 메모리를 가로지르는 stateful 학습 역할. 역시 **LAYER P** — source routing/strategy hint를 *제안*하되, 제안은 LAYER G(`_ALLOWED_BY_LAYER`+budget) 게이트를 반드시 통과(ADR#14).
- 둘을 합치면 감사 추적·롤백 경계가 흐려진다 → 코드상 분리. **P/G/F 매핑:** judge·supervisor = LAYER P, allowlist/budget 게이트 = LAYER G, deterministic fetch 루프 = LAYER F(LLM 미관여).

## 5. tool registry / allowed strategy / HITL / audit + budget

- `_ALLOWED_BY_LAYER`(8 layer) + `_UNSAFE_STRATEGIES` = allowed-strategy registry 골격 = **LAYER G(게이트)**. LLM 제안은 allowed 안에서만, 밖이면 무시. 이 게이트 유지·강화.
- **budget guard 추가(ADR#14):** LAYER G는 allowlist뿐 아니라 **per-event/월 budget guard**도 검문 — expansion 호출 비용 폭주를 게이트에서 차단(R-DiscoveryCostStarvation·R-ExpansionPartialFailure). budget 상세 = `06`(tiered)·`19 §6`.
- **audit trace 의무화(ADR#14):** LLM 제안의 *제안·채택·거부*를 구조화 로깅. **정직 단서:** 현 `source_supervisor.py:104`는 허용 밖 제안을 *침묵 폐기*(반환값·로그 무기록) → audit 완화책은 **현재 미구현(TODO)**, R-LLMCollectBoundary가 추적.
- HITL은 confidence=low/manual_operator_review 경로에. audit_trace를 전 노드 커버.
- **P/G/F 경계 근거(ADR#14, M1 교정):** 수집을 "LLM 완전배제 deterministic"으로 두던 레거시 명제는 폐기됐다. 대신 **LLM은 무엇을·어디서를 계획(LAYER P)**하고 **결정론 엔진은 어떻게(준수하며)를 실행(LAYER F)**한다. 재현성·감사·rate-limit 준수는 LAYER G/F가 보장 — LLM을 페치 루프(LAYER F)에 직접 넣지는 않으므로 비결정성·우회 유혹은 게이트에서 차단된다. "LLM은 크롤러가 아니라 수집의 두뇌(planner)".

## 6. 위험 / 검증기준

- 위험: 6 mock 노드 프로덕션 오용(MOCK 표기 강제), LLM 만능주의(결정론 가능분은 NER/룰로), 비용 폭발(이벤트당 토큰 상한 + budget guard), prompt injection(외부 텍스트 격리, 14 안전 layer).
- 검증: 두 그래프 compile+invoke, 5 REAL 실동작 + 6 MOCK 명시, allowed/unsafe 게이트로 우회 영구차단, checkpointer 미도입시도 단발 invoke 완전 동작, Deep Agents/벤더SDK 미도입 결정 + 버전핀 유지(0.2.76 모니터포인트: redis checkpointer 전환 요구 등장 시 재평가, `16` 참조).
- **새 방향 RISK 링크(`docs/_RISK/RISK_REGISTER.md`):** P/G/F 수집경계 = **R-LLMCollectBoundary**(unsafe 침묵폐기·audit TODO), 별개 Agent Debate 그래프 = **R-AgentDebateSafety**(투자조언화·prompt injection), Event 토대 선행 = **R-EventModelMigration**(논쟁 대상 Event 전환·3엔진 정합성). prompt injection 교차 = R-PromptInjection.

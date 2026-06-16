# 10 — AGENT ORCHESTRATION LAYER (L10)

> 결론: LangGraph 0.2.76 **유지**가 옳다(11노드는 수초 내 완결 무상태 파이프라인, checkpointer 미사용). Deep Agents/OpenAI SDK/CrewAI 도입은 **현 단계 불필요**(수집 deterministic, 전략 선택은 규칙표로 닫혀 있음). 진짜 작업은 6개 mock 노드 해제다.

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

- **deepagents**(create_deep_agent/write_todos/subagent/context offloading): "에이전트가 동적으로 계획"이 필요할 때 값. 현재 전략 선택은 `_ALLOWED_BY_LAYER` + deterministic fallback으로 닫혀 있어 불필요.
- OpenAI Agents SDK/CrewAI: 1-2툴엔 가볍지만, 이미 LangGraph stateful/audit/HITL + LangSmith 관측에 투자 → 프레임워크 추가는 관측·감사 일관성을 깨뜨림.
- 결론: **미도입 결정을 문서화**하고 LangGraph 일관성 유지.

## 4. 장기 supervisor vs 단기 judge 분리

- **judge**: 단발·무상태(complete_json 1회, 실패 None), 노드 안에 산다.
- **SourceSupervisor**: 실패 누적·전략 메모리를 가로지르는 stateful 학습 역할.
- 둘을 합치면 감사 추적·롤백 경계가 흐려진다 → 코드상 분리.

## 5. tool registry / allowed strategy / HITL / audit

- `_ALLOWED_BY_LAYER`(8 layer) + `_UNSAFE_STRATEGIES` = allowed-strategy registry 골격. LLM 제안은 allowed 안에서만, 밖이면 무시. 이 게이트 유지·강화.
- HITL은 confidence=low/manual_operator_review 경로에. audit_trace를 전 노드 커버.
- **수집 deterministic 유지 근거**: 재현성·감사·rate-limit 준수가 생명. LLM을 페치 루프에 넣으면 비결정성·비용·우회 유혹. LLM은 "판단만, 실행 안 함".

## 6. 위험 / 검증기준

- 위험: 6 mock 노드 프로덕션 오용(MOCK 표기 강제), LLM 만능주의(결정론 가능분은 NER/룰로), 비용 폭발(이벤트당 토큰 상한), prompt injection(외부 텍스트 격리, 14 안전 layer).
- 검증: 두 그래프 compile+invoke, 5 REAL 실동작 + 6 MOCK 명시, allowed/unsafe 게이트로 우회 영구차단, checkpointer 미도입시도 단발 invoke 완전 동작, Deep Agents/벤더SDK 미도입 결정 + 버전핀 유지.

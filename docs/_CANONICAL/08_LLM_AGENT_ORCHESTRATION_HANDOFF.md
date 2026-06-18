# 08 — LLM AGENT ORCHESTRATION HANDOFF

> LLM 에이전트가 어디에 쓰이고, 무엇이 실/mock이며, 다음 연결점이 무엇인지.

---

## 1. LLM 사용 범위 (구조적 통제)

- **수집(ingestion)은 deterministic.** LLM은 가치/판단 지점에만 — 비용·비결정성·법무 리스크를 구조로 통제.
- ingestion 측 LLM 접점: `source_supervisor.py`(전략 선택 인터페이스), quality 판단. 현재 실 provider 미연결(규칙 기반 동작).
- 다운스트림 측 LLM 접점: LangGraph 노드 6개 + 임베딩.

## 2. LangGraph 11노드 real/mock (다운스트림)

| # | 노드 | 상태 |
|---|---|---|
| 1 | source_parse | REAL |
| 2 | normalize_event | REAL |
| 3 | deduplicate | PARTIAL(dedupe_key만, 벡터 임계값 미정) |
| 4 | entity_linking | MOCK |
| 5 | sector_mapping | MOCK |
| 6 | retrieve_past_context | REAL(Milvus top-k) |
| 7 | impact_analysis | MOCK |
| 8 | evidence_check | PARTIAL(실 source URL 구조검증 채택, 도달성 미검증) |
| 9 | fact_check | MOCK("pass" fallback) |
| 10 | final_writer | MOCK(요약 mock, status 기본 hold=fail-closed) |
| 11 | publish_or_hold | REAL(근거+fact_check+본문+corroboration 게이트) |

→ **5 REAL / 1 PARTIAL / 5 MOCK.** 잔여 mock 실연결은 04 T-AgtA.

> ⚠ **mock 카드 경고(2026-06-18, P0 하드닝으로 노출경로 봉인)**: entity/sector/impact/fact_check는 여전히
> mock(고정/가짜, 05 R-MockCard). 단 **published 노출경로는 fail-closed로 차단**됨:
> - `evidence_check`는 실 source URL만 근거로 채택(`evidence_rules.is_valid_evidence_url`).
> - `publish_or_hold`는 **유효 근거 URL + fact_check pass + 본문 존재**를 모두 만족할 때만 published,
>   아니면 hold. `final_writer` 기본 status도 `hold`.
> - 공개 `GET /api/events`는 published 카드만 반환(`event_service.list_events(status="published")`).
> → 근거 없는/mock evidence 카드는 published되지 않고 공개 목록 노출도 안 됨. 다만 entity/sector/impact
>   **콘텐츠 자체는 mock**이므로 published 카드라도 그 분석필드는 신뢰 금지(T-AgtA까지).
>
> **publish_or_hold corroboration(2026-06-18)**: `confirmation_policy ∈
> {unconfirmed_until_corroborated, internal_queue_only, publish_blocked_until_corrob}` 또는
> `corroboration_required=True`이면 근거/fact_check와 무관하게 `hold`. 상수는 노드에 인라인(ingestion 미의존).

## 3. mock→real 전환 (무코드, env)

| env | 기본 | real |
|---|---|---|
| `LLM_PROVIDER` | mock | openai |
| `EMBEDDING_PROVIDER` | mock | openai |
| `LANGSMITH_TRACING` | (미설정) | true |
| `ADMIN_API_TOKEN` | (빈값=bypass) | <토큰> |

## 4. LLM 추상화 계약

- `BaseLLMClient`: `complete()` + `complete_json(schema=...)`. 무상태, 예외 전파 안 함(실패→None→안전 기본값, confidence=0.0 센티넬).
- 출력 스키마는 `agents/tools/llm.py`에 집중. 신규 노드 4단계: 프롬프트 .md → 스키마 → tool helper → add_node/add_edge.
- 프롬프트 자산 `agents/prompts/*.md`(4개 초안)는 **현재 코드 미연결**(04 T-AgtC).

## 5. SourceSupervisor handoff (ingestion → 미래 LLM)

- `source_strategy_memory.yaml`에 소스별 `successful_strategy` + **`llm_agent_hints`** 축적(재사용 목적).
- 미래 SourceSupervisor가 이 hints로 전략 선택·복구 제안.
- **불변 제약(에이전트도 적용)**: proxy rotation / CAPTCHA·login·paywall·rate-limit 우회 제안 **거부**.
  synthetic slug/URL을 안정 증거로 사용 금지. google_trends_explore PASS 표기 금지.
- 실 provider 연결은 고도화(07 E-4).

## 6. handoff 체크리스트 (다음 에이전트가 알아야 할 것)

1. 수집은 deterministic — 새 소스도 LLM 없이 전략 그래프로 처리.
2. LLM은 다운스트림 사건처리(노드 6개)와 임베딩에 한정, 모두 mock→real env 토글.
3. dcinside publish는 CommunityCorroborationGate로 봉인 — 등급 소비 배선 전까지 해제 금지(04 T-IngD, 05 R-DcToS).
4. gdelt는 scheduled 429 — 재개는 cooldown 후 자동, 우회 금지(05 R-Gdelt429).

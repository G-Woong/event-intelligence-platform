# 16 — LangChain / LangGraph / Deep Agents 공식 문서 조사 및 도입 판단

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 📘 REFERENCE — 도입판단 리서치. 0.2.76/0.2.11 설치 사실·DeepAgents 0건 검증 정확.
> │ **구현순위:** #8 (00_ROADMAP_INDEX) · **그룹:** B
> │ **검증 근거(보존 필수 4대 사실):** ① `langgraph==0.2.76`·`langchain==0.2.11` 설치(§1). ② `create_agent`(v1)는 미설치·미적용. ③ DeepAgents grep 0건(`grep deepagents` → 0). ④ §8 Implementation diff blueprint = **DO NOT APPLY**(Phase F 선택 시에만, 0.2.76 재검증 후).
> │ **잔여(미구현):** 프레임워크 신규 도입 0(설계 결정). LangGraph 수집 cycle(Phase F)은 선택, Deep Agents 미도입.
> │ **완료정의(DoD):** 리서치 문서이므로 "구현" 비적용. DoD = 4대 사실 보존 + LAYER P/F 경계 정합 + next-doc 포인터 정확.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획·판단).
> └────────────────────────────────────────────────────────

> **목적**: 이 셋을 **무조건 도입하지 않는다**. 공식 문서 기준으로 기능을 조사하고, **현재 프로젝트의 수집·사건처리**에서의 효용·충돌을 평가해 "도입/보류"를 가른다.
> **가장 중요한 사실**: 레포에는 **`langgraph==0.2.76`, `langchain==0.2.11`이 이미 설치**돼 있다. 공식 문서 리서치가 설명하는 `langchain.agents.create_agent`·`docs.langchain.com/oss`는 **v1.0대 API로, 현재 설치 버전이 아니라 "업그레이드 경로"다.** 이 문서는 그 차이를 명시한다.
> **수집=비-LLM 명제의 범위 정정(ADR#14):** 이전 판본의 "수집은 비-LLM"은 이제 **LAYER F(Fetch, 결정론 실행) 한정**이다. **LAYER P(Planning)에는 LLM이 관여**한다(Triage/Query Expansion/Source Routing). 즉 "LLM은 크롤러가 아니라 수집의 두뇌(planner)"다 — 본 문서 곳곳의 "수집은 비-LLM"은 **LAYER F를 가리키는 것으로 읽어야** 한다(§0/§3/§5/§6에 명시).

---

## 0. 비개발자를 위한 설명

LangGraph/LangChain/Deep Agents는 "AI 에이전트를 만드는 도구상자"다. 하지만 도구상자가 좋다고 모든 일에 쓰는 건 아니다. 망치가 좋아도 나사를 박을 때 쓰면 안 된다.

우리 프로젝트의 수집은 **두 부분**으로 나뉜다(ADR#14의 P/G/F 경계). **"무엇을·어디서 가져올지 계획하는 부분(LAYER P)"에는 LLM이 관여**한다(처리가치 판단·확장쿼리·소스 라우팅). 반면 **"실제로 가져오는 부분(LAYER F)은 정해진 규칙대로 호출하는 일"**이라 비-LLM 결정론이다. LAYER F에 "AI가 매번 알아서 판단하는" 에이전트를 끼우면 **느려지고, 비싸지고, 결과가 예측 불가능**해진다(우회·rate 위반 위험도). 그래서 우리는:

- **LangGraph(상태 그래프)**: 수집 흐름을 "단계 지도"로 그리는 데 **유용** → 부분 도입 검토.
- **LangChain 에이전트**: AI가 도구를 자율 호출 → 수집엔 과함. **요약/추출 같은 일부 단계만** 검토.
- **Deep Agents**: 코딩 에이전트용 무거운 도구 → 수집 배치엔 **부적합. 미도입.**

또한 우리 레포엔 이미 langgraph 0.2.76이 깔려 있고, 다운스트림(`agents/`)이 이 버전으로 11노드 그래프를 돌리고 있다. 함부로 최신 버전으로 올리면 그게 깨질 수 있다.

---

## 1. 설치 버전 현실 (반드시 먼저 인지)

| 패키지 | 레포 설치 버전 | 리서치가 설명한 버전 | 함의 |
|---|---|---|---|
| langgraph | **0.2.76** | v1.0대(2025~2026) | `StateGraph`/`add_conditional_edges`는 양쪽 공통. `create_agent`(langchain.agents)는 v1 — **미적용** |
| langchain | **0.2.11** | v1.0 | `create_react_agent`(langgraph.prebuilt) 시대. v1 `create_agent`는 업그레이드 후 |
| langchain-core | 0.2.43 | — | |
| langgraph-checkpoint | 2.1.1 | — | 코어 checkpoint 존재. **sqlite/postgres saver는 미설치** |
| langchain-openai | 0.1.7 | — | OpenAI 연결 |
| langsmith | 0.1.147 | — | 관측 |

**판단 원칙(D-3)**: **0.2.76 유지.** 다운스트림 11노드 그래프가 이 버전에 의존하므로, v1 업그레이드는 별도 회귀 검증 라운드로 분리한다. 이 문서의 모든 "도입" 권고는 **0.2.76 API 기준**으로 다시 검증한 뒤 구현한다.

---

## 2. LangGraph 기능 요약 (공식 문서)

> 출처: https://docs.langchain.com/oss/python/langgraph/graph-api 외. **0.2.76에서도 핵심(StateGraph/Node/Edge/conditional/compile/invoke)은 동일하나, import 경로·세부 인자는 설치본에서 재확인 필요.**

| 기능 | 요약 | 0.2.76 가용성 | 프로젝트 적용 |
|---|---|---|---|
| StateGraph / State(TypedDict, reducer/Annotated) | 상태 공유 노드 그래프, `Annotated[list, add]`로 병합 제어 | ✅ (이미 다운스트림 사용) | **높음** — 수집 cycle을 상태 그래프로 |
| Node / Edge / conditional edges | `add_node/add_edge/add_conditional_edges` | ✅ | **높음** — 소스별 분기/fallback |
| compile / invoke / stream | `compile()` 후 `invoke`(배치)/`stream`(단계) | ✅ | **높음** — 배치는 invoke |
| checkpointer (Memory/Sqlite/Postgres) | 상태 영속, thread_id, 재개/복구 | 코어 Memory ✅ / Sqlite·Postgres saver **미설치** | **중간** — 크래시 복구 필요 시 Sqlite |
| Store (BaseStore, cross-thread) | 스레드 간 장기 메모리 | ✅(InMemoryStore) | **낮음** — 대화 메모리 개념, 배치엔 불필요 |
| interrupt / HITL | `interrupt()` + `Command(resume)` | 버전별 차이 — 재확인 | **낮음** — 무인 배치엔 개입점 없음 |
| RetryPolicy / durability | 노드 재시도, exit/async/sync 영속 | RetryPolicy ✅(`langgraph.types`) | **중간~높음** — 수집 노드 재시도 |
| streaming (stream_mode) | values/updates/messages/custom | ✅ | **낮음** — 진행 로깅 용도만 |
| subgraph | 컴파일 그래프를 노드로 내장 | ✅ | **중간** — 소스별 수집 subgraph |

---

## 3. LangChain agents 요약

| 기능 | 요약 | 0.2.76/0.2.11 가용성 | 적용 |
|---|---|---|---|
| create_agent (v1) | LangGraph 위 agent 정본 | ❌ v1 전용 — **현재 미적용** | 업그레이드 후 재평가 |
| create_react_agent (구) | `langgraph.prebuilt` | ✅ (0.2.x) | 필요 시 이 경로 |
| tool calling | LLM 도구 호출 | ✅ | 수집엔 과함 |
| structured output (with_structured_output) | 스키마 강제 출력 | ✅ (langchain-core) | **높음** — 사건 후보 JSON 추출 |
| HITL middleware | 도구 승인 미들웨어 | v1 전용 | 보류 |

**핵심 판단(ADR#14 정합)**: **수집의 제어흐름(LAYER F 실행)을 LLM 에이전트로 돌리지 않는다**(비용·비결정성·우회위험). 단 **LAYER P(계획)에는 LLM이 관여**한다 — Triage/Query Expansion/Source Routing. LLM은 **계획·추출/요약/모순 판단 노드**에서 `with_structured_output`로만 사용. 이는 이미 `ingestion/agents/llm_judge.py`가 `complete_json(schema=...)`로 하는 방식과 정합. 배선 지점:

| LAYER P 노드 | 배선 코드 | 상태 |
|---|---|---|
| Query Expansion | `query_generator.generate()` | 미배선(06·11) |
| 확장 재유입 라우팅 | `expansion_router.py`(tiered+budget gate) | 미배선(06·07 §2.1) |
| Source Routing | `source_supervisor.decide(llm_propose=…)` | `decide()`/allowlist 실구현, `llm_propose` 실 provider 미배선(11) |

> **with_structured_output / create_judge_client 우선 재사용:** LAYER P의 LLM 호출은 신규 프레임워크가 아니라 **기존 0.2.x `with_structured_output` + `create_judge_client` 래퍼**를 먼저 재사용한다(설치 0). create_agent(v1)·Deep Agents는 그 다음 후보(§5b).

---

## 4. Deep Agents 요약

| 기능 | 요약 | 적용 |
|---|---|---|
| create_deep_agent | 가상 FS + 서브에이전트 + 스킬 번들 하니스 | **낮음(런타임)** |
| built-in tools (todo, 가상 FS) | LLM 장기 자율 태스크용 | 배치 수집과 목적 불일치 |
| subagents / async subagents | 컨텍스트 격리 | HTTP 병렬화(=Celery/asyncio)와 다름 |
| skills/memory/permissions/HITL | 코딩 에이전트 기능 | 불필요 |
| backends (Filesystem/Shell) | ⚠️ 비제한·고위험 | 보안 위험 |
| MCP tools | langchain-mcp-adapters | **future review만** |

**결론(D-4)**: **Deep Agents 미도입.** 효용 < 복잡도. 게다가 프로젝트엔 이미 개발용 "팀 에이전트"(Claude Code)가 있어 개발 하니스가 중복. 런타임 오케스트레이터로 부적합.

---

## 5. 도입/보류 종합 판단표

| feature | apply_now | defer | reason | risk |
|---|---|---|---|---|
| LangGraph StateGraph(수집 cycle) | △(Phase F 선택) | — | 결정적 배치를 그래프로 표현 가능. 단 deterministic cycle(Phase A)로도 충분 | 과설계 시 복잡도 |
| LangGraph conditional edges | △(Phase F) | — | 소스별 분기/fallback | — |
| LangGraph RetryPolicy | △(Phase F) | — | 노드 재시도. 단 기존 strategy loop가 이미 재시도 | 중복 |
| LangGraph checkpointer(Sqlite) | — | ✅ | 크래시 복구 필요 시. 패키지 설치 필요 | 미설치 |
| LangGraph Store/interrupt/streaming | — | ✅ | 대화·실시간·HITL 지향, 배치 불필요 | — |
| LangChain with_structured_output | ✅(LLM 노드) | — | 사건 후보 JSON 추출 — 이미 llm_judge 사용 | LLM 비용 |
| LangChain create_agent(v1) | — | ✅ | v1 전용, 버전 업 후 | 회귀 |
| Deep Agents 전체 | — | ✅(미도입) | 배치 수집에 과함 | 복잡도·보안 |
| MCP/Plugin | — | ✅(future review) | 13번 제약 — 재도입 안 함 | tool poisoning |

---

## 5b. 고수준 오케스트레이션 프레임워크 후보 비교 (3층 구조 — 재검토 확정)

> 사용자가 후보로 제시한 4종(LangChain Agents / Deep Agents / CrewAI / Microsoft Agent Framework)을 **현재 도입이 아니라 "어느 층에, 언제"의 관점**으로 정리한다. **이번 턴에서 어떤 것도 설치하지 않는다.**

### 권장 3층 구조

```
Layer 1. Ingestion orchestration (P/G/F 경계, ADR#14)   ← 본체 (설치 0)
  LAYER P (Planning, LLM 관여): Triage · Query Expansion(query_generator) ·
           Source Routing(source_supervisor.decide(llm_propose)) · strategy hint
  LAYER G (Gate, 결정론): _ALLOWED_BY_LAYER · _UNSAFE_STRATEGIES · per-event/월 budget
  LAYER F (Fetch, 결정론·LLM 미관여): run_collection_probe · StrategyRouter ·
           EventQueue · QualityGate · bridge_to_raw_events
  → 프레임워크 없음. F는 순수 Python·비-LLM. **P만 LLM 관여**(with_structured_output 재사용).

Layer 2. Existing LangGraph event processing      ← 이미 존재 (langgraph 0.2.76 유지)
  raw_events → Redis Stream → agents/graphs/event_processing_graph.py(11노드)
  → event_cards → Milvus/OpenSearch → frontend
  → 새 프레임워크 도입 안 함. 0.2.76 StateGraph 유지.

Layer 3. Future high-level agent layer            ← MVP 이후, 지금 설치/도입 안 함
  Expansion 조사(LLM 확장쿼리 심화) / Authority 소스 발견 / Agent Debate(증거 지지·반박, 19 §9)
  + 트래픽×광고 연결(13) / 팀 에이전트 리뷰 / 관리자 리서치
```

> **§5b Layer 1 정정(ADR#14):** 이전 판본은 Layer 1을 "deterministic·LLM 없음"이라 단정했으나, **LAYER P에는 LLM이 관여**한다(수집 배제 명제 폐기). "LLM 없음"은 **LAYER F 한정**이다. Layer 1 전체가 비-LLM이 아니라, F만 비-LLM이고 P는 LLM-advised다.

### Layer 3 후보 비교표

| framework | 적합 역할 | apply_now | 도입 시점 | 충돌/리스크 | 설치 정책 |
|---|---|---|---|---|---|
| **LangChain Agents (`create_agent` v1)** | LLM 자율 도구호출(요약/모순) | ❌ | v1 업그레이드 후 | **0.2.11 미지원**(v1 전용), 다운스트림 회귀 | 지금 금지 |
| **Deep Agents** | 사건 확장 조사·증거 탐색·리서치(후보; **기존 0.2.76+create_judge_client 재사용이 먼저**) | ❌ | MVP 이후 — 0.2.76 재사용으로 부족이 실증될 때만 | 가상 FS/Shell 고위험, 비결정성, 비용 | `INSTALL_CANDIDATE_REQUIRES_USER_APPROVAL` (지금 금지) |
| **CrewAI** | 역할 기반 팀 에이전트 리뷰(비교 후보) | ❌ | MVP 이후 비교 평가 | 기존 LangGraph 위에 **새 프레임워크 추가 비용**, 학습곡선 | 지금 금지 |
| **Microsoft Agent Framework / AutoGen 후속** | 장기 엔터프라이즈 멀티에이전트 | ❌ | 장기(엔터프라이즈 수요 시) | 무거움, 현재 불필요 | 지금 금지 |

**판단 근거(공식·코드 기준, ADR#14 정합)**:
- 수집 **실행(LAYER F)**은 **deterministic이어야** 비용·비결정성·디버깅·우회위험을 통제한다. 어떤 에이전트 프레임워크도 LAYER F에 넣지 않는다. 단 **LAYER P(계획)는 LLM-advised**이며, 신규 프레임워크가 아니라 **기존 0.2.x `with_structured_output` + `create_judge_client` 재사용을 먼저** 쓴다.
- 사건 처리(Layer 2)는 **이미 LangGraph 0.2.76으로 동작**한다. 새 프레임워크로 갈아끼우는 것은 회귀 위험 대비 이득이 없다.
- Layer 3은 **Expansion 심화 조사 / Authority 소스 발견 / Agent Debate(증거 지지·반박 자연어 생성, 19 §9) / 트래픽×광고 연결(13)** 같은 **MVP 이후 부가가치**다. **Deep Agents 우선순위 재서술:** Layer 3에서도 **기존 0.2.76 + `create_judge_client` 래퍼 재사용이 1순위**다. Deep Agents는 그 위에 "장기 자율 리서치"가 실제 필요할 때만 평가하는 **후보**이지, 자동 1순위가 아니다(설치는 사용자 승인 후, `INSTALL_CANDIDATE_REQUIRES_USER_APPROVAL`). CrewAI는 팀 리뷰 비교용, MS Agent Framework는 장기 후보로만 문서화.

> **상용화 함의(10 §)**: Layer 3 고급 에이전트는 **premium analysis / B2B intelligence / research assistant** 계층이다. MVP의 1차 ROI(44소스 연결)와 분리해, 매출 검증 후 얹는다.

---

## 6. 현재 프로젝트에 적합한 그래프 설계 (만약 Phase F에서 LangGraph 채택 시)

> **전제**: Phase A의 deterministic cycle로 시작하고, "재개/복구/분기가 복잡해질 때만" LangGraph로 승격. 0.2.76 API 기준.

```
수집 cycle StateGraph (개념도 — Phase F 선택):
  State: { sources_due: list, results: Annotated[list, add], cycle_id: str }

  START → load_due_sources
        → route_each_source        (conditional: profile.preferred_strategy)
            ├─ api_branch     → collect_api (run_collection_probe)
            ├─ browser_branch → collect_browser
            └─ loop_branch    → collect_strategy_loop
        → enqueue_results          (EventQueue.enqueue)
        → update_health
        → END
  노드 RetryPolicy: collect_* 에 NETWORK_TIMEOUT/HTTP_5XX 재시도
  checkpointer(선택): SqliteSaver — cycle 중단 시 재개
```

**중요**: 이 그래프의 LAYER F 노드는 **기존 `run_collection_probe`를 호출만** 한다. LangGraph는 "흐름 제어"만 하고, 실제 fetch는 기존 deterministic 코드가 한다. **LAYER F 노드는 LLM 없음(Fetch=비-LLM).** 단 그래프 앞단의 **LAYER P 노드(route_each_source 이전의 Triage/Query Expansion/Source Routing)에는 LLM이 관여**한다(ADR#14) — 위 개념도는 F 흐름만 그린 것이며, P는 `source_supervisor.decide(llm_propose)`·`query_generator.generate()`가 담당한다.

> ⚠️ **Claude Code 팀 에이전트 vs LangGraph runtime agent 경계(필수 구분)**:
> - **Claude Code 팀 에이전트(15개)**: 개발/리뷰용. 코드를 짜고 검토하는 "개발 보조". 런타임에 안 돈다.
> - **LangGraph/runtime**: 실제 앱이 사용자에게 서비스할 때 도는 오케스트레이션. 이 문서의 대상.
> - 둘은 **이름이 비슷해도 완전히 다른 층위**다. 혼동 금지.

---

## 7. 충돌 가능성 (현재 코드와)

| 충돌 지점 | 원인 | 대응 |
|---|---|---|
| asyncio 중첩 | `fetch_with_playwright_sync`가 `asyncio.run` — LangGraph async 실행 시 "loop already running" | LangGraph 노드를 sync로, 또는 nest_asyncio |
| 두 그래프 혼동 | `ingestion/agents/graph.py`(소스 크롤링) vs `agents/graphs/event_processing_graph.py`(사건 처리) | 네이밍·문서로 구분(01 §3.1) |
| 버전 충돌 | v1 API 코드를 0.2.76에 사용 | 0.2.76 기준 재검증(§1) |
| checkpointer 미설치 | sqlite/postgres saver 없음 | 필요 시 `uv pip install langgraph-checkpoint-sqlite` |
| 중복 재시도 | LangGraph RetryPolicy + strategy loop 재시도 | 한쪽만(권장: 기존 loop) |

---

## 8. Implementation diff blueprint

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY — Phase F 선택 시에만. 0.2.76 API로 재검증 필수.
diff --git a/ingestion/orchestration/collection_graph.py b/ingestion/orchestration/collection_graph.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/collection_graph.py
@@
+# 0.2.76: from langgraph.graph import StateGraph, START, END
+# (v1 create_agent 사용 금지 — 미설치)
+from langgraph.graph import StateGraph, START, END
+from typing import Annotated, TypedDict
+from operator import add
+
+class CollectionCycleState(TypedDict):
+    sources_due: list
+    results: Annotated[list, add]
+    cycle_id: str
+
+def build_collection_graph(router, profiles):
+    g = StateGraph(CollectionCycleState)
+    g.add_node("load_due_sources", load_due_sources)
+    g.add_node("collect", collect_node)   # run_collection_probe 호출만
+    g.add_node("enqueue_results", enqueue_node)
+    g.add_edge(START, "load_due_sources")
+    g.add_edge("load_due_sources", "collect")
+    g.add_edge("collect", "enqueue_results")
+    g.add_edge("enqueue_results", END)
+    return g.compile()  # checkpointer=SqliteSaver(...) 는 선택
```

**설치(선택, 사용자 승인 후)**:
```
# 크래시 복구가 필요할 때만
uv pip install langgraph-checkpoint-sqlite
```

---

## 9. Risk Closure (checklist)

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| LangGraph 과설계 | deterministic으로 충분한데 그래프 도입 | 복잡도·디버깅 비용 | 코드 복잡도 | Phase A 우선, F는 선택 | Phase A 단독 동작 | CLOSED_BY_DESIGN |
| v1 API 오용 | 리서치 v1 코드를 0.2.76에 적용 | import 에러 | 버전 확인 | §1 명시 + 재검증 | smoke import 테스트 | DEFERRED_WITH_TRIGGER |
| asyncio 중첩 | playwright sync + async 그래프 | 런타임 에러 | smoke 테스트 | sync 노드 또는 nest_asyncio | Windows smoke | DEFERRED_WITH_TRIGGER |
| Deep Agents 도입 압력 | 트렌드 추종 | 복잡도·보안 | 설계 리뷰 | 미도입 결정(§4) | grep deepagents 0 | CLOSED_BY_DESIGN |
| MCP 재도입 | 13번 제약 위반 | tool poisoning | 설계 리뷰 | future review로 분리 | grep MCP install 0 | BLOCKED_BY_POLICY |
| 버전 업그레이드 회귀 | v1로 올림 | 다운스트림 11노드 깨짐 | 회귀 테스트 | 0.2.76 유지(D-3) | 108 테스트 회귀 | CLOSED_BY_DESIGN |

### 9.1 신규 RISK 3건 (ADR#14 — LAYER P LLM 관여 경계)

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| **R-LLMCollectBoundary** | LAYER P LLM 제안이 LAYER G 게이트를 우회/침묵폐기 | 우회·rate위반 전략이 F로 새거나, 거부가 무기록 | `source_supervisor.py:104` 허용밖 제안 침묵폐기 grep | `_ALLOWED_BY_LAYER`+`_UNSAFE_STRATEGIES` reject **+ audit trace 의무화**(제안·채택·거부 구조화) | audit replay record(미구현 TODO) | DEFERRED_WITH_TRIGGER |
| **R-PromptInjection** | 확장쿼리/소스 라우팅 입력에 적대 페이로드(LAYER P) | LLM이 악성 소스·우회전략 제안 | 제안 로그 검수 | 게이트는 결정론(G가 최종 검문), 제안은 화이트리스트 안에서만 채택 | 적대 입력 게이트 통과 0 | DEFERRED_WITH_TRIGGER |
| **R-DiscoveryCostStarvation** | LAYER P 확장이 budget guard 없이 폭주 | 토큰·호출비용 폭증, cold triage 비용 | budget 카운터 | LAYER G per-event/월 budget guard(미구현) | budget 초과 시 재유입 drop | OPEN(미구현) |

---

## 10. Commercialization Impact

- **기술 절제 = 빠른 출시 = 비용 절감**: LangGraph/Celery를 "필요해질 때만" 도입하면, MVP를 신규 인프라 0으로 출시할 수 있다. 이것이 런웨이(자금 소진 속도) 관리의 핵심.
- **결정적 수집 = 예측 가능한 비용**: LLM을 수집에 안 쓰면 토큰 비용이 수집량과 무관하게 0에 수렴 → 단가 경쟁력.
- **LLM은 가치 지점에만**: 요약·모순·사건 판단(다운스트림)에만 LLM을 써서, "AI 인텔리전스"라는 가치는 유지하되 비용은 통제.
- **업그레이드 리스크 회피**: 0.2.76 유지로 다운스트림 회귀 위험을 없애 출시 일정을 지킨다.

---

## 11. Agent Committee Review

| agent | 피드백 | status |
|---|---|---|
| orchestrator-architect | "deterministic 우선, LangGraph는 선택" 판단이 정확. 두 그래프 구분 명시 양호 | CLOSED_BY_DESIGN |
| mcp-tooling-researcher(관점) | MCP/Deep Agents 미도입 + future review 분리 적절 | BLOCKED_BY_POLICY |
| adversarial-reality-critic | v1 vs 0.2.76 차이를 숨기지 않은 점이 이 문서의 최대 가치 | CLOSED_BY_DESIGN |
| security-permission-guardian | Deep Agents FilesystemBackend 고위험 회피, MCP 보류 | CLOSED_BY_DESIGN |
| test-validation-agent | 버전 업그레이드 시 108 회귀가 게이트 | CLOSED_BY_TEST_PLAN |
| commercialization-strategist | 기술 절제 = 런웨이 관리. LLM 국소화 = 단가 경쟁력 | CLOSED_BY_DESIGN |

---

## 12. USER_CONFIRMATION_REQUIRED

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| langgraph 0.2.76 유지 vs v1 업그레이드? | 다운스트림 회귀 위험 | 0.2.76 유지(D-3) | No |
| 수집 cycle을 LangGraph로 만들까(Phase F)? | 과설계 회피 | deterministic 우선, 복잡해지면 F | No |
| Deep Agents 도입? | 복잡도/보안 | 미도입(D-4) | No |
| checkpointer(SqliteSaver) 설치? | 크래시 복구 필요 시 | 필요해질 때만 | No |
| MCP 재도입? | 13번 제약 | future review만 | Yes(정책) |
| **LAYER P LLM on/off 토글?** | LLM 미가용/예산소진 시 baseline 폴백 필요 | `LLM_PROVIDER≠""`면 LLM-advised, 비면 결정론 baseline(P 비활성·F만) | No |

> **§12 LLM on/off 계약(ADR#14):** LAYER P의 LLM 관여는 **`LLM_PROVIDER`(또는 `llm_available`) 토글**로 켜고 끈다. 빈 값이면 LAYER P는 결정론 baseline(고정 라우팅·확장 없음)으로 폴백하고 **LAYER F는 영향 없이 동작**한다. 즉 LLM은 "수집의 두뇌"지만 **없어도 수집은 멈추지 않는다**(graceful degrade). 이 토글이 R-DiscoveryCostStarvation(예산소진 시 P off)·LLM 장애의 안전판이다.

---

## 13. 구현 전 재확인 필요 항목 (UNKNOWN)

- 0.2.76의 정확한 import 경로(`langgraph.types.RetryPolicy`, `interrupt` 등) — 설치본에서 `dir()` 확인.
- checkpointer sqlite/postgres saver 미설치 → 설치 시 버전 호환(0.2.76 ↔ checkpoint-sqlite) 확인.
- Windows에서 langgraph async + playwright sync 조합 smoke 테스트 미수행 — 구현 시 검증.
- v1 업그레이드 시 다운스트림 `agents/graphs/event_processing_graph.py` 호환성 — 별도 회귀 라운드.

> 출처(주요): docs.langchain.com/oss/python/langgraph/{graph-api, persistence, durable-execution, interrupts, streaming}, reference.langchain.com/python/langgraph/types/{RetryPolicy, Durability}, docs.langchain.com/oss/python/langchain/agents, docs.langchain.com/oss/python/deepagents/customization, github.com/langchain-ai/deepagents. (모두 v1 정본 — 0.2.76 적용 시 재검증.)

> 다음 문서: `10_AGENT_ORCHESTRATION_LAYER.md`(LangGraph/Deep Agents 프레임워크 결정서). 상호참조: `00_ROADMAP_INDEX`(순위 #8) · `06`(query_generator/expansion tiered router) · `07 §2.1`(expansion 재유입 게이트) · `11 §2.1`(P/G/F 경계) · `19 §9`(Agent Debate) · `13`(트래픽×광고) · `_DECISIONS/2026-06.md` ADR#14/#15.

# 06 — LangChain / LangGraph / Deep Agents 공식 문서 조사 및 도입 판단

> **목적**: 이 셋을 **무조건 도입하지 않는다**. 공식 문서 기준으로 기능을 조사하고, **현재 프로젝트(배치/주기 수집, 실시간 X)**에서의 효용·충돌을 평가해 "도입/보류"를 가른다.
> **가장 중요한 사실**: 레포에는 **`langgraph==0.2.76`, `langchain==0.2.11`이 이미 설치**돼 있다. 공식 문서 리서치가 설명하는 `langchain.agents.create_agent`·`docs.langchain.com/oss`는 **v1.0대 API로, 현재 설치 버전이 아니라 "업그레이드 경로"다.** 이 문서는 그 차이를 명시한다.

---

## 0. 비개발자를 위한 설명

LangGraph/LangChain/Deep Agents는 "AI 에이전트를 만드는 도구상자"다. 하지만 도구상자가 좋다고 모든 일에 쓰는 건 아니다. 망치가 좋아도 나사를 박을 때 쓰면 안 된다.

우리 프로젝트의 수집 작업은 대부분 **"정해진 규칙대로 소스를 호출하는 일"**이다. 여기에 "AI가 매번 알아서 판단하는" 에이전트를 끼우면 **느려지고, 비싸지고, 결과가 예측 불가능**해진다. 그래서 우리는:

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

**핵심 판단**: **수집 라우팅 전체를 LLM 에이전트로 돌리지 않는다**(비용·비결정성). LLM은 **추출/요약/모순 판단 같은 일부 노드**에서 `with_structured_output`로만 국소 사용. 이는 이미 `ingestion/agents/llm_judge.py`가 `complete_json(schema=...)`로 하는 방식과 정합.

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

**중요**: 이 그래프의 노드는 **기존 `run_collection_probe`를 호출만** 한다. LangGraph는 "흐름 제어"만 하고, 실제 수집은 기존 deterministic 코드가 한다. LLM 노드는 없음(수집은 비-LLM).

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

---

## 13. 구현 전 재확인 필요 항목 (UNKNOWN)

- 0.2.76의 정확한 import 경로(`langgraph.types.RetryPolicy`, `interrupt` 등) — 설치본에서 `dir()` 확인.
- checkpointer sqlite/postgres saver 미설치 → 설치 시 버전 호환(0.2.76 ↔ checkpoint-sqlite) 확인.
- Windows에서 langgraph async + playwright sync 조합 smoke 테스트 미수행 — 구현 시 검증.
- v1 업그레이드 시 다운스트림 `agents/graphs/event_processing_graph.py` 호환성 — 별도 회귀 라운드.

> 출처(주요): docs.langchain.com/oss/python/langgraph/{graph-api, persistence, durable-execution, interrupts, streaming}, reference.langchain.com/python/langgraph/types/{RetryPolicy, Durability}, docs.langchain.com/oss/python/langchain/agents, docs.langchain.com/oss/python/deepagents/customization, github.com/langchain-ai/deepagents. (모두 v1 정본 — 0.2.76 적용 시 재검증.)

> 다음 문서: `07_AGENT_ORCHESTRATION_ARCHITECTURE.md`.

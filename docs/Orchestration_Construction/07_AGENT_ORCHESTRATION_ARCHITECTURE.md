# 07 — 오케스트레이션 아키텍처 (Node / Stage 설계)

> **목적**: 수집 cycle을 구성하는 **노드(단계)**를 설계한다. 각 노드가 "결정적 함수인가 / LLM 판단인가"를 명확히 가르고, 허용 도구·금지 도구·재시도·실패 처리·다음 엣지를 못 박는다.
> **핵심 원칙**: **대부분의 노드는 결정적 함수다.** LLM 판단은 (1)전략 선택 보조, (2)품질 판정, (3)모호성 해소에만 제한한다. 실제 HTTP/browser 호출은 기존 runner/tool이 한다. **에이전트가 무제한 웹을 직접 탐색하지 못하게 한다.**

---

## 0. 비개발자를 위한 설명

하나의 "수집 주기(cycle)"는 여러 단계(노드)를 거친다. 공장 컨베이어 벨트를 떠올리면 된다:

1. 오늘 수집할 소스 목록을 꺼낸다 →
2. 막힌 소스를 걸러낸다 →
3. 각 소스에 맞는 방법을 고른다 →
4. 실제로 수집한다 →
5. 본문을 뽑는다 →
6. 품질을 검사한다 →
7. 중복을 합친다 →
8. 큐에 쌓는다 →
9. 소스 건강 상태를 갱신한다 →
10. 주기 보고서를 쓴다.

이 중 **대부분은 "정해진 규칙대로" 도는 기계 단계**다. 딱 두세 곳(품질 판정, 모호한 사건 분류)에서만 AI의 판단을 빌린다. AI에게 "알아서 웹을 뒤져봐"라고 시키지 않는다 — 그건 비싸고 위험하다.

---

## 1. 노드 목록 (수집 cycle)

| # | 노드 | 책임 | 종류 | 매핑 |
|---|---|---|---|---|
| 1 | **source_profile_loader_node** | 소스 프로파일 로드 | deterministic | `load_profiles()` (03) |
| 2 | **cycle_planner_node** | 이번 cycle에 돌릴 소스 결정(주기 bucket) | deterministic | profile.freshness_need + 마지막 수집 시각 |
| 3 | **source_health_gate_node** | 격리/쿨다운/차단 소스 제외 | deterministic | `get_health_store()`, `list_due_for_retry()` |
| 4 | **strategy_router_node** | 소스별 CollectionStrategy 선택 | deterministic | `StrategyRouter.route()` (03) |
| 5 | **collection_executor_node** | 실제 수집 실행 | deterministic | `run_collection_probe()` |
| 6 | **body_extraction_node** | 본문 cascade | deterministic | `extract_body()` (04) |
| 7 | **related_expansion_node** | on-demand 검색 확장 | deterministic | enrichment runner (02) |
| 8 | **quality_judge_node** | 품질 게이트 | **하이브리드** | 09 게이트 + (선택)LLM judge |
| 9 | **dedup_cluster_node** | 중복 제거/클러스터 | deterministic | content_hash + (후속)벡터 |
| 10 | **evidence_linker_node** | 증거 연결 | deterministic | evidence_links (05) |
| 11 | **event_queue_writer_node** | 큐에 적재 | deterministic | `EventQueue.enqueue()` |
| 12 | **source_health_updater_node** | 건강 상태 갱신 | deterministic | `get_health_store().set()` |
| 13 | **rate_limit_scheduler_node** | 다음 호출 시각 계산 | deterministic | `get_store()` next_retry_at |
| 14 | **artifact_writer_node** | artifact 저장 | deterministic | `artifact_store` |
| 15 | **human_review_interrupt_node** | 사람 검토 지점(선택) | deterministic gate | 격리 4주 등 트리거 시만 |
| 16 | **final_cycle_report_node** | 주기 보고 | deterministic | JSONL 리포트 |

**LLM 판단 노드는 8번(quality_judge)뿐**이며, 그것도 **선택적**(기본은 deterministic 규칙, 모호 시에만 llm_judge). 나머지 15개는 전부 결정적.

---

## 2. 노드별 상세 명세

> 형식: responsibility / input / output / 종류 / 허용·금지 도구 / retry / failure / next / test / diff.

### 2.1 source_profile_loader_node
- **responsibility**: `source_profiles.yaml` + registry → SourceProfile dict.
- **input**: (없음, 설정 로드) **output**: `profiles: dict[str, SourceProfile]`
- **종류**: deterministic
- **허용 도구**: 파일 읽기. **금지**: 네트워크, .env 값 읽기(키 존재만).
- **retry**: 파일 없으면 즉시 실패(CONFIG_ERROR). **failure**: cycle 중단 + 리포트.
- **next**: cycle_planner_node
- **test**: 44 소스 로드, 누락 소스 기본값.

### 2.2 cycle_planner_node
- **responsibility**: freshness_need + 마지막 수집 시각 → 이번 cycle 대상 소스 목록.
- **input**: profiles, last_run_times **output**: `sources_due: list[str]`
- **종류**: deterministic (규칙: near_real_time 매 cycle, daily는 하루 1회 등)
- **금지**: 임의 소스 추가(registry에 없는 소스).
- **next**: source_health_gate_node
- **test**: bucket별 due 판정, daily 중복 호출 방지.

### 2.3 source_health_gate_node
- **responsibility**: BLOCKED_TERMINAL/쿨다운/격리 소스 제외.
- **input**: sources_due **output**: `sources_ready: list`, `sources_skipped: list`
- **종류**: deterministic. **허용**: health/rate-limit store 읽기(네트워크 0).
- **next**: strategy_router_node
- **test**: 격리 소스 skip, 쿨다운 skip.

### 2.4 strategy_router_node
- **responsibility**: 소스별 CollectionStrategy 결정.
- **input**: sources_ready, profiles, previous_failures **output**: `routing: dict[source_id, strategy]`
- **종류**: deterministic (`StrategyRouter.route`, read-only).
- **next**: collection_executor_node
- **test**: 03 §7 라우터 테스트.

### 2.5 collection_executor_node
- **responsibility**: 실제 수집 (소스당 격리 실행).
- **input**: routing **output**: `probe_results: list[CollectionProbeResult]`
- **종류**: deterministic. **허용**: `run_collection_probe` (= 기존 3-way). **금지**: 직접 httpx/playwright 호출(반드시 probe 경유), 우회.
- **retry**: NETWORK_TIMEOUT/HTTP_5XX만 지수 backoff(기존 strategy loop 내장). **failure**: 소스 격리, 다른 소스 계속.
- **next**: body_extraction_node
- **test**: 소스 격리(한 소스 실패가 다른 소스 무영향), force gate.

### 2.6 body_extraction_node
- **responsibility**: URL → 본문 cascade.
- **input**: probe_results **output**: `extracted: list[BodyExtractionState]`
- **종류**: deterministic (04 cascade). **금지**: blocker 우회, 무한 렌더.
- **next**: related_expansion_node (조건부) 또는 quality_judge_node
- **test**: 04 §9.

### 2.7 related_expansion_node
- **responsibility**: 사건 후보 significance ≥ 임계 시 on-demand 검색 확장.
- **input**: extracted, significance **output**: `related: list`
- **종류**: deterministic. **허용**: enrichment runner(serper/tavily/naver, quota guard). **금지**: 정기 폴링, quota 초과.
- **conditional edge**: significance < 임계 → skip(비용 절감).
- **test**: quota guard, 임계 미만 skip.

### 2.8 quality_judge_node (유일한 하이브리드)
- **responsibility**: 품질 게이트(body 길이/중복/신선도/신뢰도) 통과 판정. 모호 시 LLM judge.
- **input**: extracted + related **output**: `passed: list`, `rejected: list`, `needs_review: list`
- **종류**: **하이브리드** — 1차 deterministic 규칙(09), 규칙으로 못 가르는 경우만 `llm_judge.complete_json(schema=...)`.
- **허용 도구(LLM 사용 시)**: `create_judge_client()` (mock/openai). **금지**: 무제한 웹 탐색, 외부 호출, .env 직접 읽기.
- **LLM 사용 조건**: D-8(다운스트림에서만) 기본 → 수집 단계 quality_judge는 **deterministic 우선**, LLM은 옵션.
- **next**: dedup_cluster_node
- **test**: 게이트 통과/탈락, LLM mock 경로.

### 2.9 dedup_cluster_node
- **responsibility**: content_hash 중복 제거. (후속: 벡터 클러스터.)
- **종류**: deterministic. **next**: evidence_linker_node.
- **test**: 동일 URL/제목 중복 1건으로.

### 2.10 evidence_linker_node
- **responsibility**: 사건 ↔ 1차 출처(공시/규제/시세) 연결.
- **종류**: deterministic. **next**: event_queue_writer_node.

### 2.11 event_queue_writer_node
- **responsibility**: `EventQueue.enqueue(EventSeedCandidate)`.
- **종류**: deterministic. **next**: source_health_updater_node.
- **test**: 05 §7.

### 2.12~2.16 (health 갱신 / rate-limit 스케줄 / artifact / human review / report)
- 전부 deterministic. human_review_interrupt_node는 "4주 연속 BLOCKED" 같은 트리거에서만 리포트 생성(자동 수정 안 함, 사람 승인).

---

## 3. deterministic vs agentic 경계 (재확인)

```
[ deterministic — 규칙대로 ]
 profile_loader, cycle_planner, health_gate, strategy_router,
 collection_executor, body_extraction, related_expansion,
 dedup_cluster, evidence_linker, queue_writer, health_updater,
 rate_limit_scheduler, artifact_writer, report

[ agentic — LLM 판단 허용 (제한적) ]
 quality_judge (모호한 품질/사건 분류만, mock 기본, 비용 통제)
```

**에이전트가 직접 하면 안 되는 것(불변)**:
- 무제한 웹 탐색 (반드시 run_collection_probe 경유)
- CAPTCHA/login/paywall 우회
- provider 429 무시
- raw .env 읽기
- 임의 source 추가 (registry 외)
- 무검증 PASS 선언
- full-text 무단 복제

---

## 4. 실행 형태 (Phase별)

| Phase | 실행 형태 | 노드 구현 |
|---|---|---|
| A | **deterministic local cycle** — 단일 Python 함수가 노드를 순서대로 호출 | for-loop, LangGraph 없음 |
| F(선택) | **LangGraph StateGraph** — 노드를 그래프로(06 §6) | 분기/재개 복잡해질 때 |
| G | **Celery tasks** — 노드 일부를 task로 분리(collect_source 등) | plans/012 |

**핵심**: 같은 노드 설계가 Phase A(함수 호출), F(그래프), G(task) 어디에도 재사용된다. 노드 책임이 명확하면 실행 형태는 나중에 선택 가능.

---

## 5. Implementation diff blueprint

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY
diff --git a/ingestion/orchestration/nodes.py b/ingestion/orchestration/nodes.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/nodes.py
@@
+"""Cycle nodes. Each node is a pure-ish function over a cycle state dict.
+Reused by Phase A (loop), F (LangGraph), G (Celery)."""
+def source_profile_loader_node(state): ...
+def cycle_planner_node(state): ...
+def source_health_gate_node(state): ...
+def strategy_router_node(state): ...
+def collection_executor_node(state): ...   # run_collection_probe 호출만
+def body_extraction_node(state): ...        # extract_body (04)
+def related_expansion_node(state): ...
+def quality_judge_node(state): ...          # 09 게이트 + (선택)llm_judge
+def dedup_cluster_node(state): ...
+def evidence_linker_node(state): ...
+def event_queue_writer_node(state): ...     # EventQueue.enqueue
+def source_health_updater_node(state): ...
+def final_cycle_report_node(state): ...

diff --git a/ingestion/orchestration/run_orchestration_cycle.py b/ingestion/orchestration/run_orchestration_cycle.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/run_orchestration_cycle.py
@@
+def run_cycle(sources=None) -> dict:
+    """Phase A: deterministic 노드 순차 실행."""
+    state = {"cycle_id": _new_cycle_id()}
+    for node in [source_profile_loader_node, cycle_planner_node,
+                 source_health_gate_node, strategy_router_node,
+                 collection_executor_node, body_extraction_node,
+                 related_expansion_node, quality_judge_node,
+                 dedup_cluster_node, evidence_linker_node,
+                 event_queue_writer_node, source_health_updater_node,
+                 final_cycle_report_node]:
+        state = node(state)
+    return state
```

**수정하지 않는 파일**: `collection_probe.py`, `run_collection_probe.py`, `llm_judge.py`, store/registry. 노드는 호출만.

---

## 6. test plan

```
test_cycle_planner_buckets               # bucket별 due
test_health_gate_skips_quarantined       # 격리 skip
test_executor_source_isolation           # 한 소스 실패 → 다른 소스 진행
test_quality_judge_deterministic_first   # 규칙으로 가능하면 LLM 안 부름
test_quality_judge_llm_mock_path         # 모호 시 mock judge
test_queue_writer_enqueues               # EventQueue 적재
test_full_cycle_smoke                    # gdelt+yna 1 cycle → 큐 항목
test_no_unmediated_web_access            # executor가 probe 경유 (직접 httpx 금지)
```

---

## 7. Agent Committee Review

| agent | 피드백 | status |
|---|---|---|
| orchestrator-architect | 16노드 책임 분리 + 3실행형태 재사용 설계가 견고 | CLOSED_BY_DESIGN |
| source-ingestion-engineer | collection_executor가 probe 경유만 → 우회 구조적 차단 | CLOSED_BY_DESIGN |
| adversarial-reality-critic | "agentic은 quality_judge 1개뿐"이 비용·비결정성 통제. LLM 남용 방지 | CLOSED_BY_DESIGN |
| data-quality-auditor | quality_judge 하이브리드(규칙 우선)가 합리적 | CLOSED_BY_TEST_PLAN |
| security-permission-guardian | 금지 도구 목록(§3)이 명확. .env/무제한 웹 차단 | CLOSED_BY_DESIGN |
| operations-sre-agent | 소스 격리 + 노드 단위 재시도가 운영 안정성 | CLOSED_BY_DESIGN |
| test-validation-agent | 8 테스트가 노드 경계 커버. no_unmediated_web 테스트 중요 | CLOSED_BY_TEST_PLAN |

---

## 8. Risk Closure

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| 에이전트 tool overreach | LLM이 직접 웹/파일 접근 | 보안·비용 | 도구 호출 감사 | quality_judge만 LLM, 도구 제한 | no_unmediated_web 테스트 | CLOSED_BY_DESIGN |
| LLM 비용 폭발 | 모든 노드 LLM화 | 토큰 비용 | 토큰 카운트 | 15/16 deterministic | mock 기본 테스트 | CLOSED_BY_DESIGN |
| agent hallucinated source status | LLM이 PASS 임의 선언 | 거짓 상태 | 상태 출처 검증 | 상태는 deterministic gate가 판정 | 상태 일관성 테스트 | CLOSED_BY_DESIGN |
| 소스 비격리 | 한 소스 실패가 cycle 중단 | 가용성 저하 | cycle 완주율 | 소스당 try/except | isolation 테스트 | CLOSED_BY_TEST_PLAN |
| 실행형태 lock-in | Phase A가 Celery에 안 맞음 | 재작성 | 노드 재사용성 | 노드를 순수 함수로 | A/F/G 재사용 테스트 | CLOSED_BY_DESIGN |

---

## 9. Commercialization Impact

- **운영 비용 예측성**: 15/16 노드가 결정적 → 사용자 1명 추가 시 비용이 LLM 호출이 아니라 수집량에 비례(예측 가능). 단가 모델링 가능.
- **점진 확장**: 같은 노드를 Phase A→F→G로 승격 가능 → 트래픽 성장에 맞춰 인프라만 교체(코드 재사용).
- **신뢰 = 결정성**: "AI가 매번 다르게 판단"하지 않으므로, B2B 고객에게 "재현 가능한 파이프라인"을 보증할 수 있다.
- **감사 추적(agent_actions)**: LLM 판단 지점을 기록 → 규제 산업 B2B(금융·법무 인접)에 필요한 설명가능성 확보.

---

## 10. USER_CONFIRMATION_REQUIRED

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| quality_judge에서 LLM을 쓸까(수집 단계)? | 비용 vs 품질 | deterministic 우선, LLM은 다운스트림(D-8) | No |
| related_expansion 임계(significance)? | 검색 비용 | ≥0.5 | No |
| Phase A를 단일 함수로 시작? | 단순성 | 예(run_cycle 함수) | No |
| human_review 트리거(격리 몇 주)? | 운영 개입 | 4주 연속 BLOCKED | No |

> 다음 문서: `08_RETRY_RATE_LIMIT_FAILURE_POLICY.md`.

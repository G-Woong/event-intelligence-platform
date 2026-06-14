# 11 — 구현 Diff 청사진 (Implementation Diff Blueprint)

> **목적**: 다음 구현 턴에서 Claude Code가 **그대로 따라갈** 수 있는 파일 단위 변경 계획. Phase A~H로 단계화한다.
> **절대 원칙**: **이번 턴에 diff를 적용하지 않는다.** 모든 diff는 blueprint다. 경로가 불확실하면 `VERIFY PATH BEFORE APPLY`. 삭제 diff는 사용하지 않는다. 기존 수집 코드(runner/tools/configs/tests)는 **수정하지 않는다**.

---

## 0. 비개발자를 위한 설명

이 문서는 "다음에 코드를 짤 때의 작업 지시서"다. **무슨 파일을 새로 만들고, 무엇을 안 건드리는지**를 단계별로 적었다. 각 단계(Phase)는 독립적으로 완성·검증되며, 한 단계가 끝날 때마다 "테스트 통과 + 비밀키 스캔 통과"를 확인하고 넘어간다. 한 번에 다 만들지 않는다 — 작게, 안전하게, 검증하며.

---

## 1. 생성할 파일 목록 (신규)

| 파일 | Phase | 역할 |
|---|---|---|
| `ingestion/orchestration/__init__.py` | A | 패키지 |
| `ingestion/orchestration/source_profile.py` | C | SourceProfile + load_profiles |
| `ingestion/orchestration/collection_strategy.py` | C | CollectionStrategy enum |
| `ingestion/orchestration/strategy_router.py` | C | StrategyRouter |
| `ingestion/orchestration/body_extraction_state.py` | D | BodyExtractionState |
| `ingestion/orchestration/body_cascade.py` | D | extract_body cascade |
| `ingestion/orchestration/quality_gates.py` | E | deterministic 게이트 |
| `ingestion/orchestration/nodes.py` | A | cycle 노드 함수 |
| `ingestion/orchestration/run_orchestration_cycle.py` | A | Phase A 진입점 |
| `ingestion/orchestration/collection_graph.py` | F(선택) | LangGraph(0.2.76) |
| `ingestion/orchestration/celery_app.py` | G | Celery app |
| `ingestion/orchestration/tasks.py` | G | collect_source 등 task |
| `ingestion/orchestration/retry_queue.py` | G | 재시도 큐 |
| `ingestion/orchestration/quarantine.py` | G | 격리 |
| `ingestion/orchestration/quota_guard.py` | G | 일일 quota |
| `ingestion/orchestration/bridge_to_raw_events.py` | H | 다운스트림 브리지 |
| `ingestion/configs/source_profiles.yaml` | C | 44 소스 프로파일 |
| `ingestion/tests/unit/test_strategy_router.py` | C | |
| `ingestion/tests/unit/test_body_cascade.py` | D | |
| `ingestion/tests/unit/test_quality_gates.py` | E | |
| `ingestion/tests/unit/test_orchestration_cycle.py` | A | |
| `ingestion/tests/integration/test_celery_tasks.py` | G | fakeredis |
| `ingestion/tests/integration/test_bridge.py` | H | |

## 2. 수정할 파일 목록 (최소)

| 파일 | Phase | 변경 | 주의 |
|---|---|---|---|
| `ingestion/pipeline/event_queue.py` | G | `_redis_*` stub 채우기 | 인터페이스 불변, JSONL 폴백 유지 |
| `ingestion/configs/rate_limit_policy.yaml` | G | `daily_quota` 필드 추가(per_source) | 기존 키 불변 |
| `backend/alembic/versions/0004_event_candidates.py` | B(선택) | 신규 마이그레이션 | 다운스트림 |
| `docs/DOCS_FINAL.md` | (이번 턴) | Orchestration_Construction pointer 추가 | 최소 변경 |

## 3. 변경하지 않을 파일 목록 (불변 — 중요)

```
ingestion/fetch_strategies/*  (collection_probe, strategy_runner, strategy_selection,
                               failure_classifier, article_body_extractor, cloud_browser_like,
                               selenium_strategy, artifact_writer)
ingestion/tools/*             (모든 extractor, url_resolver, feed_discovery, playwright_browser_tool)
ingestion/core/*              (artifact_store, source_registry, rate_limit_store, source_health,
                               quality_score, error_taxonomy, retry_policy)
ingestion/agents/*            (graph, llm_judge, state)
ingestion/runners/*           (23개 runner)
ingestion/configs/source_registry.yaml, retry_policy.yaml, publication_policy.yaml,
                  extraction_policy.yaml, playwright_probe_sites.yaml
ingestion/tests/*             (기존 테스트 — 회귀 기준선)
backend/*, workers/*, agents/* (다운스트림 — 브리지는 호출만, Phase H의 0004 제외)
```

---

## 4. class/function schema (요약 — 상세는 각 문서)

| 심볼 | 정의처 | 시그니처 |
|---|---|---|
| SourceProfile | 03 §2 | dataclass(frozen) |
| CollectionStrategy | 03 §1 | str Enum |
| StrategyRouter.route | 03 §3 | `(source_id, purpose, previous_failure) -> str` |
| extract_body | 04 §8 | `(url, source_id, profile, *, allow_browser) -> BodyExtractionState` |
| run_quality_gates | 09 §5 | `(items, profiles, policy) -> dict` |
| run_cycle | 07 §5 | `(sources=None) -> dict` |
| bridge_to_raw_events | 05 §6 | `(item: dict) -> str` |
| collect_source(task) | 08/plans012 | `(source_id) -> dict` (= run_collection_probe 래퍼) |

---

## 5. database migration draft (Phase B, 선택)

```diff
# Proposed — DO NOT APPLY IN THIS TURN — VERIFY downstream alembic head
diff --git a/backend/alembic/versions/0004_event_candidates.py b/...
new file mode 100644
+revision = "0004_event_candidates"
+down_revision = "0003_raw_events_event_card_link"
+def upgrade():
+    op.create_table("event_candidates",
+        sa.Column("id", UUID, primary_key=True),
+        sa.Column("source_id", sa.Text),
+        sa.Column("title_or_keyword", sa.Text),
+        sa.Column("source_url", sa.Text),
+        sa.Column("timestamp", sa.DateTime(timezone=True)),
+        sa.Column("purpose", sa.Text),
+        sa.Column("body_status", sa.Text),
+        sa.Column("significance", sa.Float),
+        sa.Column("status", sa.Text, server_default="pending"),
+        sa.Column("created_at", sa.DateTime(timezone=True)),
+        sa.UniqueConstraint("source_url", "source_id", name="uq_evcand_url_src"))
+def downgrade():
+    op.drop_table("event_candidates")
```

> 기본 권장: Phase B에서는 JSONL 큐로 충분 → 이 마이그레이션은 **영속이 필요해질 때만**.

---

## 6. runner integration diff (Celery, Phase G)

```diff
# Proposed — DO NOT APPLY IN THIS TURN — VERIFY rate-limit 인터페이스(U-1)
diff --git a/ingestion/orchestration/tasks.py b/...
new file mode 100644
+from celery import shared_task
+from ingestion.fetch_strategies.collection_probe import run_collection_probe
+@shared_task(acks_late=True, time_limit=300)   # playwright 소스는 600
+def collect_source(source_id: str) -> dict:
+    result = run_collection_probe(source_id)    # 기존 코드 호출만
+    # → EventQueue.enqueue + (RATE_LIMITED 시 retry_queue) + health 갱신
+    return {"source_id": source_id, "status": result.status, "items": result.items_found}
@@
+@shared_task
+def drain_retry_queue(): ...   # 08 §5

diff --git a/ingestion/orchestration/celery_app.py b/...
new file mode 100644
+from celery import Celery
+app = Celery("ingestion", broker=os.environ["REDIS_URL"], backend=os.environ["REDIS_URL"])
+# beat 스케줄: plans/012 §2 bucket
+# ⚠️ Windows: app.conf.worker_pool = "solo" 검토 (V-4)
```

---

## 7. tests diff (각 Phase)

```
Phase A: test_orchestration_cycle.py   (cycle 노드 순차, smoke)
Phase C: test_strategy_router.py       (라우팅 분기)
Phase D: test_body_cascade.py          (cascade 폴백)
Phase E: test_quality_gates.py         (게이트 통과/탈락)
Phase G: test_celery_tasks.py          (fakeredis, 중복 차단, 재시도 큐)
Phase H: test_bridge.py                (raw_events 생성, dedup)
공통: 각 Phase 후 기존 509 + 108 회귀 0
```

---

## 8. docs diff (이번 턴만 적용 대상)

```diff
diff --git a/docs/DOCS_FINAL.md b/docs/DOCS_FINAL.md
@@ (신규 세션 읽는 순서에 한 줄 추가, 최소 변경)
+ - 오케스트레이션 구축 설계: docs/Orchestration_Construction/README.md → 00_OVERVIEW
```

> 그 외 docs는 이번 턴에 변경하지 않는다(DOCS_FINAL 최종 정리 상태 보존, 최소 pointer만).

---

## 9. phased commit plan (다음 턴들)

| Phase | commit message(예) | 검증 게이트 |
|---|---|---|
| A | `feat(orch): deterministic local collection cycle` | cycle smoke + 회귀 0 + secret scan |
| B | `feat(orch): persist queue/state (local_file/jsonl)` | roundtrip + 회귀 0 |
| C | `feat(orch): source profile + strategy router` | router 테스트 + 회귀 0 |
| D | `feat(orch): body extraction resilience cascade` | cascade 테스트 + 회귀 0 |
| E | `feat(orch): data quality gates` | gate 테스트 + 회귀 0 |
| F(선택) | `feat(orch): optional langgraph cycle (0.2.76)` | graph == cycle 동등 |
| G | `feat(orch): celery tasks + retry/quarantine/quota` | fakeredis + 중복 차단 |
| H | `feat(orch): bridge to downstream raw_events` | e2e 1건 도달 |

각 commit: push 금지, 단계별 atomic.

---

## 10. 이번 턴(설계)에서 적용하는 변경 (유일)

- `docs/Orchestration_Construction/` 신규 13개 md + README.
- `docs/DOCS_FINAL.md` pointer 1줄(최소).
- **코드 변경 0.**

---

## 11. Agent Committee Review

| agent | 피드백 | status |
|---|---|---|
| source-ingestion-engineer | "변경하지 않을 파일" 목록이 명확 — 수집 코드 보호 | CLOSED_BY_DESIGN |
| orchestrator-architect | Phase A~H 단계화 + commit plan이 atomic 원칙 충족 | CLOSED_BY_DESIGN |
| test-validation-agent | 각 Phase 회귀 0 게이트 + fakeredis 테스트 적절 | CLOSED_BY_TEST_PLAN |
| adversarial-reality-critic | U-1(rate-limit), U-3(create_raw_event), V-4(Windows Celery) VERIFY 표기 일관 | DEFERRED_WITH_TRIGGER |
| security-permission-guardian | 단계별 secret scan 게이트 유지 | CLOSED_BY_DESIGN |
| docs-memory-curator | DOCS_FINAL 최소 변경 원칙 양호 | CLOSED_BY_DESIGN |

---

## 12. Risk Closure

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| 수집 코드 훼손 | 잘못된 수정 | 회귀 | git diff | "변경 안 함" 목록(§3) | 509 회귀 0 | CLOSED_BY_DESIGN |
| 경로 오인 | VERIFY 누락 | 잘못된 diff | grep | VERIFY PATH 표기 | 구현 직전 확인 | DEFERRED_WITH_TRIGGER |
| 한 번에 과다 구현 | Phase 미분리 | 디버깅 지옥 | PR 크기 | Phase atomic + commit plan | 단계 통과 | CLOSED_BY_DESIGN |
| Windows Celery 실패 | pool 제약 | worker 미가동 | worker 起動 | solo pool / deterministic 우선 | V-4 | USER_CONFIRMATION_REQUIRED |
| 마이그레이션 충돌 | down_revision 오인 | DB 깨짐 | alembic head | VERIFY head | alembic upgrade 테스트 | DEFERRED_WITH_TRIGGER |

---

## 13. Commercialization Impact

- **단계화 = 빠른 가치 실현**: Phase A(설치 0)만으로도 "44소스가 큐에 쌓이는" 데모가 가능 → 투자/사용자에게 조기 증명.
- **변경 최소 = 안정성**: 검증된 수집 코드를 안 건드리므로 회귀 위험이 낮아 출시 신뢰도↑.
- **Phase H = 제품 완성**: 브리지 e2e 1건 도달이 "44소스 → 사용자 화면"의 첫 증명 → 제품 스토리 완결.

---

## 14. USER_CONFIRMATION_REQUIRED

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| Phase A부터 시작(설치 0)? | 빠른 증명 | 예 | No |
| event_candidates 마이그레이션 시점? | 영속 필요성 | Phase B에서 필요 시 | No |
| Windows에서 Celery worker pool? | 가동 가능성 | solo 또는 deterministic 우선 | Phase G |
| DOCS_FINAL pointer 추가 허용? | 진입점 일관성 | 1줄 추가 | No |

> 다음 문서: `12_RISK_CLOSURE_AND_VALIDATION_PLAN.md`.

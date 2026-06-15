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

## 9b. Phase별 설치/비설치 정책 (재검토 확정)

> 모든 신규 설치/컨테이너 기동은 **`INSTALL_CANDIDATE_REQUIRES_USER_APPROVAL`**. 이번 검토 턴은 설치 0.

| Phase | 신규 설치 | 비고 |
|---|---|---|
| A deterministic cycle | **0** | run_collection_probe + EventQueue(JSONL). 기존 설치 자산만 |
| B persistence | **0** | local_file/JSONL |
| C strategy router | **0** | 순수 Python |
| D body resilience | **0** | 기존 extractor 호출 |
| E quality gates | **0** | 기존 quality_score 재사용 |
| F LangGraph(선택) | 0(설치된 0.2.76) / checkpointer는 `INSTALL_CANDIDATE`(sqlite saver) | deterministic 동등 검증 후만 |
| G Celery/Redis | Redis **컨테이너 기동** `INSTALL_CANDIDATE` / Playwright chromium(worker) `INSTALL_CANDIDATE` | py 패키지(celery/redis)는 설치됨 |
| H 브리지 | Postgres **컨테이너 기동** `INSTALL_CANDIDATE` / psycopg는 **기존 backend AsyncSession 경유로 회피 가능** | bridge_to_raw_events async |
| (Layer 3, 별도 Phase I 후보) | deepagents/crewai/agent-framework `INSTALL_CANDIDATE` | MVP·매출 검증 후 |

**핵심**: **Phase A~E 신규 설치 0.** 버전 업그레이드(langgraph/langchain v1) 금지. Deep Agents/CrewAI/MS Agent Framework/MCP 지금 설치 금지.

## 9c. 운영 dashboard 지표 (후순위 — D-11)

> dashboard는 MVP 후순위. MVP는 JSONL/log/pytest/smoke로 충분. 단, 추후 dashboard에 넣을 지표를 미리 문서화한다.

```
source_success_rate         소스별 수집 성공률
source_failure_rate         소스별 실패율
rate_limited_count          429 발생 횟수
body_extraction_success_rate 본문 추출 성공률
event_candidates_count      큐 적재 사건 후보 수
raw_events_inserted_count   브리지로 raw_events 적재 수 (Phase H)
event_cards_created_count   다운스트림 카드 생성 수
quality_gate_rejection_reason 품질 게이트 탈락 사유별 분포
```

이 지표들은 Phase A~H 동안 **JSONL/로그로 먼저 산출**되고, dashboard는 그 위에 얹는 시각화 계층이다(별도 frontend STEP).

---

## 9d. Phase A/B 실제 구현 현황 (2026-06-14, 설계→코드 반영)

> 이 절은 blueprint가 아니라 **실제 적용된 코드**다. §1 표는 설계 예측이며, 실제 생성 파일은 아래가 정본이다.

**Phase A (commit 1bfcff5)** — 신규 설치 0, 회귀 656 passed:
- `ingestion/orchestration/__init__.py` / `event_seed.py` / `run_orchestration_cycle.py`
- `run_cycle()`: 소스별 `run_collection_probe` 1회 → 성공만 EventSeedCandidate로 EventQueue(JSONL) 적재. 소스 격리/probe 경유만/force=False(no bypass)/실패 비적재.
- 코드 실측 교정: `CollectionProbeResult`/`ProbeResult`에 개별 기사 리스트 없음(items_found=개수 + artifact 참조뿐) → Phase A seed = "소스별 1 수집결과". 개별 사건 분해는 Phase D/다운스트림.
- live smoke: gdelt(3)+yna(120) LIVE_SUCCESS, JSONL 2건 적재.

**Phase B (이번 턴)** — 신규 설치 0, 회귀 674 passed:
- `ingestion/orchestration/cycle_planner.py` (신규): `SourceSchedule` + `is_due()` + `select_due_sources()`. cron/Celery/Redis 없는 순수 due 판정. timezone-aware(naive→UTC 간주), last_run None→due, disabled→not due.
- `run_orchestration_cycle.run_cycle(schedules=...)` 옵션 추가: schedules 주면 due 소스만, 없으면 기존 sources/DEFAULT(Phase A 동작 불변).
- `event_seed.to_event_seed()` 확장필드 보강: `items_extracted`(ProbeResult, 없으면 None), `canonical_url`(None — Phase C/D url_resolver), artifact 경로 없을 때 None 안정 처리.
- **B-1 local_file 영속**: 기존 store 코드 수정 없이 검증만 — `LocalFileSourceHealthStore`는 이미 local_file **기본**, `LocalPersistentRateLimitStore`는 path 주입으로 영속. roundtrip 테스트(새 인스턴스=프로세스 재시작 모사)로 확인. **반복 운영 시 rate_limit backend는 `INGESTION_RATE_LIMIT_BACKEND=local_file` 권장**(기본 memory는 비영속).
- **B-4 RuntimeWarning 제거**: `__init__.py`를 PEP 562 lazy import(`__getattr__`)로 전환 → `python -m ...run_orchestration_cycle` 실행 시 runpy 경고 제거(공개 API 유지). `-W error::RuntimeWarning` 검증 통과.
- 테스트: `test_cycle_planner.py`(8) + `test_orchestration_persistence.py`(8) + `test_orchestration_cycle.py`(+2) = 신규 18.

**Phase C (이번 턴)** — 신규 설치 0, 회귀 695 passed:
- `ingestion/orchestration/source_profile.py` (신규): `SourceProfile`(dataclass frozen) + `load_source_profiles()`(yaml, 알 수 없는 필드 ValueError) + `profiles_to_schedules()`(→ Phase B SourceSchedule). 필드는 운영 최소셋(enabled/purpose/freshness_bucket/min_interval_seconds/risk_level/preferred_strategy/requires_api_key/is_community/confirmation_policy/notes) — 03 §2 풍부판을 Phase C 범위로 간소화.
- `ingestion/configs/source_profiles.yaml` (신규): registry 무수정, 보강 필드만. **특성 실측 확인된 8개 대표 소스**(gdelt/yna + community 6: hacker_news/reddit/product_hunt/youtube/dcinside/fmkorea). 44 전수는 점진 확장(검증 안 된 값 임의 기입 안 함). API 키 '값'은 미기입(.env에서만).
- `ingestion/orchestration/cycle_state.py` (신규): last_run_at local_file JSON 영속. `load/save_last_run_state`, `record_last_run`. 깨진 JSON→빈 상태 안전 처리. Redis/DB 없음.
- `ingestion/orchestration/strategy_router.py` (신규): `decide_strategy(profile)->StrategyDecision`(순수 함수, read-only metadata). community는 confirmation_policy를 `unconfirmed_until_corroborated`로 보정(단독 확정 금지). 실제 수집 라우팅은 run_collection_probe가 책임(대체 안 함).
- `run_cycle(profiles=, state_path=)` 추가: profiles→state의 last_run으로 schedule→due 소스만 수집. **성공한 수집만** last_run 기록(실패/차단은 미갱신→즉시 재시도 가능). schedules/sources 경로 불변.
- **C-5 canonical_url**: url_resolver.resolve/resolve_via_browser는 **둘 다 네트워크 호출**(httpx/Playwright) → Phase C에서 연결 안 함(선택 B). canonical_from_html은 순수하나 rendered HTML 필요 → source-level seed에선 불가. **canonical_url=None 유지, Phase D 이월**.
- 테스트: `test_source_profile.py`(8) + `test_cycle_state.py`(7) + `test_strategy_router.py`(6) = 신규 21.

**Phase C-2 (full coverage audit)** — 신규 설치 0, 회귀 713 passed:
- `source_profiles.yaml` 8 → **57 전수**(CORE_READY 44 + CAUTION 6 + 제외군 7). 정본 = INGESTION_FINAL.md + source_registry.yaml(결정적 매핑 생성, registry status/known_blockers/type 실측).
- `SourceProfile` 필드 확장: profile_status/live_eligible/skip_reason/source_group/readiness_status + enum 검증. `is_live_eligible()` 헬퍼.
- `StrategyDecision`에 live_eligible/profile_status/skip_reason 전달.
- `run_cycle(live_only=True)`: live_eligible!=true 소스를 SKIPPED(skip_reason)로 기록 — 제한적 live smoke용. CycleReport에 sources_skipped 추가.
- dry-run 전수: enabled 50 → schedule → due → run_cycle(fake) 전수 통과(`test_source_profile_full_coverage.py`, 19 테스트).
- live smoke(live_only, force=False): yna(120)/hacker_news(3) LIVE_SUCCESS 적재, gdelt RATE_LIMITED(쿨다운, 정상). requires_api_key 29 + disabled 7은 보수적 skip.
- 명명 발견: google_trends_explore는 registry/_SERVICE_CONFIGS 미등록(probe 미연결) → verify_required. registry id=_SERVICE_CONFIGS key 일치(56) 실측.

**Phase D로 넘김**: 개별 기사 분해(artifact 파싱) + canonical_url(url_resolver, 개별 기사 HTML 확보 후) + body extraction resilience cascade + requires_api_key 29소스 키 readiness 검증(V-1) + google_trends_explore probe 연결.

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

---

## Phase D 구현 완료 현황 (2026-06-14, commit 다음)

신규 파일(`ingestion/orchestration/`): `api_readiness.py`(D-0), `canonical_url.py`(D-4),
`article_candidate.py`+`artifact_parser.py`(D-2), `body_state.py`(D-3), `seed_expansion.py`(D-4b),
`live_smoke_audit.py`(D-1). 수정: `run_orchestration_cycle.py`(`expand_articles` 옵션 + `SourceOutcome.article_candidates`),
`__init__.py`(lazy export 15종 추가).

테스트(신규 63): `test_api_readiness.py`(8) `test_canonical_url.py`(12) `test_artifact_parser.py`(15)
`test_body_state.py`(13) `test_live_smoke_audit.py`(8) `test_article_candidate.py`(8, seed_expansion 포함).
fixtures(synthetic 10): gdelt/rss/generic/numeric/malformed×2/empty/snippet/no_articles/html.

검증: 전체 ingestion 회귀 **776 passed**(713→+63), 신규 설치 0, secret scan PASS, live smoke 43/44 success.
**dead-end 명시**: article candidate는 현재 카운트만(큐 적재는 source-level seed 유지). 다운스트림 흐름은
Phase H bridge(`bridge_to_raw_events`)에서 연결 — Phase D는 분해까지만.

## Phase D-P / E-0 구현 완료 현황 (2026-06-14)

신규 파일(`ingestion/orchestration/`): `production_audit.py`(SourceExpansionAudit + audit_artifact_text/file + summarize_expansion), `quality_pre_gate.py`(QualityPreGateResult + evaluate_pre_gate + normalize_published_at + compute_duplicate_key + assess_boilerplate + publication policy). 수정: `artifact_parser.py`(`html_url`/`publication_date` alias 보강 — 존재하는 URL/시각을 버리지 않음), `__init__.py`(lazy export 10종 추가).

테스트(신규 32): `test_production_audit.py`(12) `test_quality_pre_gate.py`(15) `test_pipeline_connectivity.py`(5). fixtures(synthetic 4): fed_register_results/numeric_nested/rate_limit_note/full_body_article.

검증: 전체 ingestion 회귀 **808 passed**(776→+32), 신규 설치 0, secret scan PASS, **live 호출 0**(기존 artifact 49소스 재사용).

**닫은 긍정편향**: ① html_url/publication_date 미매핑(federal_register URL/시각 복구) ② rate-limit payload(`{"Note":...}`)를 success로 위장 → `possible_rate_limit_payload` 탐지 ③ numeric/structured signal 분리(market body missing 오염 0) ④ canonical 446/446·network 0 ⑤ REDIS_URL stub 회귀 고정.

**못 닫은 것(정직)**: 기사형 본문 추출 0(present=0, RSS=snippet) → Phase E 본문 fetch. 21/49 소스 0분해(소스별 파서) → Phase E. candidate→raw_events dead-end → Phase H. dedup collapse/near-dup → Phase E.

### Phase E-1 — 소스별 body audit 구현 현황 (2026-06-14)

**신규 모듈**: `orchestration/audit_trace.py`(AuditTraceEvent/TraceRecorder, secret redaction), `orchestration/source_body_audit.py`(audit_source_body/summarize_body_audits), `orchestration/source_body_report.py`(classify_production_readiness/build_source_report), `tools/run_source_body_audit.py`(CLI runner).
**파서 보강**(`artifact_parser.py`): content:encoded/atom content→body, 중첩 `response.docs`/`hits.hits`, `_source` 평탄화, `headline.main`, `pub_date`, `api_error_payload`(opendart/bok_ecos), `_first`가 dict/list skip. `list`/`row` 의도적 제외(카탈로그 인플레 방지). `body_state` excerpt 마커 탐지 추가.
**신규 테스트(+35)**: test_audit_trace / test_source_body_audit / test_source_body_report / test_body_extraction_cascade. 전체 회귀 **843 passed**(808→+35).
**못 닫은 것**: 본문 추출 실측 ≈0(the_verge 9/10 발췌 강등, present 1) → Phase E 전체 기사 fetch. its 등 도메인 API title/url 필드 매핑 → Phase E. candidate→raw_events → Phase H.

### Phase E-2 — live full source revival 구현 현황 (2026-06-14, run 20260614T105328Z)

**신규 모듈**: `orchestration/full_source_revival.py`(SourceRevivalPlan/StrategyAttemptRecord/BodyFetchResult/StructuredSignalCandidate/RevivalEvidence, build_revival_plan, fetch_article_body[robots+excerpt+boilerplate], to_structured_signal_candidates, build_eventqueue_record/check_eventqueue_readiness, classify_final_status, summarize_revival[fully/degraded 분리]), `orchestration/source_adapters.py`(opendart/coinbase/binance source-scoped 어댑터).
**runner 확장**(`tools/run_source_body_audit.py`): `--mode full-revival` — live 호출(run_collection_probe, force=False) + `_select_best_artifact`(최적 분해 artifact 선택) + body fetch 증거(sha256+head) 보존 + source_matrix/strategy_attempts/audit event queue 산출.
**파서 보강**(`artifact_parser.py`): json dict/list 분기에 source 어댑터 dispatch(전역 인플레 회피, json_unrecognized 직전).
**신규 테스트(+45)**: test_full_source_revival / test_body_fetch_strategy / test_structured_signal_candidate / test_eventqueue_readiness / test_strategy_attempts / test_source_adapters. 전체 회귀 **888 passed**(843→+45). 신규 설치 0.
**실측 결과**: data_alive 24(fully 22+degraded 2), ARTICLE_BODY_ALIVE 6(5 live fetch 실본문), unresolved 23. 흡수 fix: artifact 선택(hacker_news), 어댑터(opendart/coinbase/binance), F1 official anchor, F3 alive 분리, F2 본문 증거.
**못 닫은 것**: sec_edgar(hits.hits 분해되나 title 매핑) 등 NEEDS_PARSER 18, 뉴스 fetch 5종(ap_news/nyt 등) → Phase E. opendart cp949 인코딩 → Phase E. candidate→raw_events → Phase H.

> 다음 문서: `12_RISK_CLOSURE_AND_VALIDATION_PLAN.md`.


## Phase E-3 — 구현 현황 (run 20260614T114401Z)

신규 모듈: `body_fetch_strategy.py`(ladder+마커+confident_full), `source_strategy_memory.py`(학습/저장/consume).
신규 config: `ingestion/configs/source_strategy_memory.yaml`(커밋, secret 없음).
변경: `source_adapters.py`(+11 JSON +2 XML adapter, generic보다 선제 dispatch),
`artifact_parser.py`(adapter 선제 dispatch + XML adapter), `full_source_revival.py`(terminal taxonomy
+ `finalize_unresolved_status` + `_SOURCE_RESOLUTION_OVERRIDE` + community degraded),
`strategy_router.py`(`decide_strategy_with_memory`), `run_source_body_audit.py`(`--mode unresolved-killer`
+ `run_unresolved_killer`). __init__에 E-3 심볼 9개 등록.
신규 테스트 6파일(+54): test_unresolved_source_killer / test_source_strategy_memory /
test_browser_strategy_policy / test_source_specific_adapters / test_body_fetch_ladder /
test_alive_status_finalization. 전체 ingestion 회귀 **942 passed**. 신규 설치 0.


## Phase F — Production Orchestration Closure

Phase F 신규 모듈(10): `ingestion/orchestration/{production_state, production_scheduler,
rate_limit_governor, quarantine, eventqueue_dedup, cross_source_dedup, time_normalizer,
bridge_to_raw_events, monitoring}.py` + `ingestion/tools/run_production_orchestration.py`.

신규 테스트 10파일(~115 tests). 전체 회귀 **1057 passed**.

CLI: `python -m ingestion.tools.run_production_orchestration --mode
{production-dry-run|production-validation} [--all-due] [--max-sources N]`.

Outputs(전부 gitignored):
- outputs/state/production_source_state.json
- outputs/state/eventqueue_dedup_index.json
- outputs/state/rate_limit_governor.json
- outputs/jsonl/production_event_queue.jsonl
- outputs/raw_events/raw_events_mirror.jsonl
- outputs/monitoring/<run>/{production_summary.json, source_health.csv, alerts.json}

신규 설치 0. Redis/Celery/Postgres 미사용(로컬 durable mirror가 동일 contract를 검증).
LangGraph 미호출 — raw_events가 Phase H로의 handoff 경계.

## Phase G — Force Production-Ready Source Closure

**판정: PARTIAL_WITH_HARD_BLOCKERS** (ALL_READY 아님).

신규 모듈:
- `vendor_api_routes.py` — bok_ecos/eia/kma/nyt/gdelt 공식 라우트. key는 env에서만, evidence URL에서 stripped.
- `source_readiness_closure.py` — 소스별 gap matrix.
- `rescue_router.py` — 비준비 소스 재라우팅.
- `body_rescue_ladder.py` — 본문 보강 ladder(현재 RSS snippet).
- `source_value_policy.py` — not_service_useful/policy 제외 판정.
- `run_source_readiness_closure.py` — closure 러너 CLI.

테스트/검증:
- +6 test 파일. 전체 회귀 **1098 passed**. secret scan **PASS(269)**. 신규 설치 없음.

산출물:
- source_profiles.yaml(its/dcinside/google_trends_explore enabled=false 반영).
- 5 sources, 38 EventQueue records → 38 raw_events mirror(re-run dedup으로 idempotency 입증).

홀드오버(정직): gdelt EXTERNAL_RATE_LIMITED 유지(신선 데이터 0), culture_info/product_hunt anchor 수정 커밋됐으나 라이브 재검증 부재로 PRODUCTION_READY_DEGRADED 유지.

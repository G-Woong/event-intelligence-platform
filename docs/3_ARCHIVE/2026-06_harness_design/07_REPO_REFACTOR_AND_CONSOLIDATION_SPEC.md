# 07 — REPO REFACTOR & CONSOLIDATION SPEC (삭제·통폐합·이관 구현 명세서)

> ✅ **실행 완료: 2026-06-19** (`git tag pre-refactor-2026-06-19` 로 복구 가능). 결과 지도: `docs/00_START_HERE.md`.
> ✅ **후속 마감(2026-06-19, 검증 라운드):** Phase 6/7/8 잔여 완료 — **P4** env-key 4벌→`5_REFERENCE/ENV_KEYS.md` 단일화(+`CORS_ORIGINS`→`CORS_ALLOW_ORIGINS` stale 정정)·commercialization 단일출처화, **P5** `*_FINAL`(509/648/635) SUPERSEDED 배너, **P6** 본 폴더의 `10_DOCS_COVERAGE_MANIFEST` → 리팩토 결과 manifest 재작성, **P7** 잔여 `Orchestration_Construction/`(00·06·11) 이관(06→`2_ROADMAP/16`, 11→`_CANONICAL/11`, 00→`_CANONICAL/12`+헤더 정정). **잔여(정책 차단):** untracked smoke 10개·`narrative_marker.json`·빈 폴더 3개는 `rm` deny 게이트로 사용자 수동 삭제 필요(§5.1/§6).
> **실행 시 편차(의도적):** §2 의 `_CANONICAL→1_CURRENT`·`_RISK→governance` **rename 은 수행하지 않음**. 이유 — 해당 폴더는 live 하네스(skill/hook/agent 41파일)와 코드가 직접 참조하므로 rename 시 **살아있는 턴-마감 하네스를 파손**. `_CANONICAL` 은 이미 깨끗한 "현재 진실" 코어이며 sprawl 통증의 원인이 아니다. 따라서 생애주기 구조를 **주변 sprawl 제거 + 신규 진입점(`00_START_HERE`)** 으로 달성하고, current-truth 코어는 `_CANONICAL/` 로 유지. 마찬가지로 `INGESTION_FINAL`·`*_FINAL`·`docs/ingestion/*` 는 9 agents+4 skills 연동이라 제자리 유지. plans slug 3개는 scratch 가 아니라 실제 history → DEL 대신 ARCHIVE 로 정정.

- 작성: 2026-06-19 (Pre-Harness 정리 마감 — 전수조사 라운드)
- 작성 근거: 3개 독립 감사 에이전트(docs 91개 전수 / 죽은코드 전수 / 메모리·설정·하네스) + 직접 grep 검증
- 성격: **실행 명세서**. 이 문서는 "무엇을, 어디로, 왜, 어떤 순서로, 무엇으로 검증하며" 옮기고 지우는지를 파일 단위로 규정한다.
- 정렬축 결정(사용자 승인): **생애주기 상태**(현재→미래→과거). 레거시 처리(사용자 승인): **공격적 통폐합**(순수중복 DELETE, 역사·아이디어 MERGE→ARCHIVE).
- 安全 원칙: ① 코드/테스트가 참조하는 파일 삭제 금지 ② git 추적 파일 삭제는 `git rm`(history 보존) ③ 이동은 `git mv`(blame 보존) ④ 각 Phase 후 전체 테스트+secret scan 통과해야 다음 Phase 진행 ⑤ 승인 필요 항목은 §10에서 분리.

---

## 1. 전수 인벤토리 (현황)

| 영역 | 수량 | 비고 |
|---|---:|---|
| docs/ .md | 91 | 13개 폴더, ~16,400줄 |
| 루트 `plans/` .md | 35 | 000~012 plan/report 쌍(빌드 히스토리) + 자동생성 slug 3 |
| `ingestion/plans/` .md | 8 | 수집 phase 설계 plan(히스토리) + dead `__init__.py` |
| 컴포넌트 README | 6 | agents/backend/frontend/ingestion/requirements/workers |
| `ingestion/outputs/` stray .py | 10 | 전부 gitignore·untracked·참조 0 (smoke/tmp 찌꺼기) |
| `ingestion/pipeline/` TEST_ONLY 모듈 | 5 | 프로덕션 미배선 고아 서브시스템 |
| `.harness/*.json` | 7 | 5 LIVE / 1 WRITE_ONLY / 1 DEAD |
| `ingestion/configs/*.yaml` | 13 | 7 LIVE / 3 DEAD(로더없음) / 3 DUP(phase) |
| 루트 메모리 | 4 | CLAUDE/PROJECT_STATUS/README(KEEP) + MIGRATION_READINESS(STALE) |

**총 문서 정리 대상 = docs 91 + plans 35 + ingestion/plans 8 = 134 .md.** 핵심 통증: 같은 사실이 4~5곳에 중복, stale 수치 산재, 빌드 히스토리(plans)가 루트에 평면 노출.

---

## 2. 타깃 구조 (생애주기 정렬축)

```
docs/
  00_START_HERE.md          ← 유일 진입점(현 _CANONICAL/00 재작성). "지금 무엇이 사실인가 / 어디를 읽나"
  1_CURRENT/                ← 오늘 구현된 시스템의 사실 (단일 출처)
      01_IMPLEMENTED_FLOW.md
      02_ARCHITECTURE.md
      03_SOURCE_STATUS.md
      04_OPEN_TASKS.md
      05_CONFLICTS_LEDGER.md          (현 06)
      06_LLM_AGENT_HANDOFF.md          (현 08)
      07_VALIDATION_AND_TESTS.md       (현 09)
      governance/
          RISK_REGISTER.md  RISK_CLOSED.md  DECISIONS_2026-06.md
  2_ROADMAP/                ← 아직 안 만든 미래 (레이어순 정렬)
      00_ENHANCEMENT_BACKLOG.md         (현 _CANONICAL/07)
      01_POSITIONING.md                 (ideation/02)
      02_TARGET_LAYERS.md               (ideation/04)
      03..N_LAYER_*.md                  (ideation/05~14, 레이어 L1→L14순)
      ROADMAP_PHASES.md                 (ideation/15 + 04 DAG)
      COMMERCIALIZATION.md              (Orch/10 + ideation/13 + ideation/18 통합)
  3_ARCHIVE/                ← 과거 사실·설계·실패시도·인사이트 (시간순 완전 정렬)
      README.md                         (시간축 인덱스 = 정렬 기준 선언)
      2026-05_build_phases/             (plans/000~012 plan+report)
      2026-06_ingestion_design/         (ingestion/plans/00~07)
      2026-06_orchestration_design/     (Orch 설계 원문, merge 후)
      2026-06_system_overview_legacy/   (수집계층 stale 부분)
      2026-06_ideation_snapshots/       (ideation/00,01,03,16,17)
      2026-06_env_trace_finals/         (Env/Trace 원문)
  4_HARNESS/                ← 이 레포 운영 도구 설계(제품과 별개 관심사)
      00_BLUEPRINT_INDEX.md ... 06_MIGRATION_PLAN.md   (현 Harness_Construction/00~06)
      07_REPO_REFACTOR_AND_CONSOLIDATION_SPEC.md       (이 문서)
  5_REFERENCE/              ← 상태중립 안정 참조 (스키마·런북·정책·용어)
      API_CONTRACT.md  EVENT_SCHEMA.md
      GLOSSARY.md                       (system_overview/02)
      FILE_MAP.md                       (system_overview/12 + ingestion 트리 추가)
      RAG_VECTOR.md  SEARCH.md  FRONTEND.md
      DEPLOYMENT.md  COMPATIBILITY.md  OBSERVABILITY.md
      ENV_KEYS.md                       (4중복 env-key 표를 단일화)
      PROMPT_GUIDE.md  LLM_CLIENT_PROTOCOL.md
      COMPLIANCE_BOUNDARY.md  DATA_POLICY.md
      artifact_manifest.md  rate_limit_evidence.md
```

**정렬 기준(단일):** "이 문서는 *지금* 사실인가 / *나중* 계획인가 / *과거* 기록인가?" — 상호배타적, 모든 문서가 정확히 한 곳에 속함. `3_ARCHIVE/` 내부만 **시간(연-월/phase)** 으로 2차 정렬한다. `_TRASH/`·`_ARCHIVE_SUPERSEDED/` scaffold는 `3_ARCHIVE/`에 흡수.

> 참고: `4_HARNESS`는 엄밀히는 web-intelligence 제품이 아니라 레포 운영 도구다. 제품 docs만 남기길 원하면 `docs/4_HARNESS`와 `1_CURRENT/governance`를 레포 루트 `harness/`로 승격 가능(§10-D6).

---

## 3. ACTION 매트릭스 A — docs/ 91개

표기: **DEL**=삭제(git rm, history 보존) / **MERGE→X**=고유내용 X로 흡수 후 원문 ARCHIVE 또는 삭제 / **ARC**=ARCHIVE 이동(배너) / **KEEP→경로**=유지(이관) / **FIX**=수치/주장 정정 필요.

### 3.1 _CANONICAL/ (10) — 전부 생존, 1_CURRENT로 이관·개명
| 현재 | → 타깃 | 액션 |
|---|---|---|
| 00_DOCS_INDEX | 00_START_HERE.md | KEEP→재작성(새 구조 반영) |
| 01_IMPLEMENTED_FLOW | 1_CURRENT/01_IMPLEMENTED_FLOW | KEEP |
| 02_CURRENT_ARCHITECTURE | 1_CURRENT/02_ARCHITECTURE | KEEP |
| 03_SOURCE_STATUS | 1_CURRENT/03_SOURCE_STATUS | KEEP |
| 04_OPEN_TASKS_BY_FOLDER | 1_CURRENT/04_OPEN_TASKS | KEEP |
| 06_CONFLICTS_AND_SUPERSEDED | 1_CURRENT/05_CONFLICTS_LEDGER | KEEP |
| 07_ENHANCEMENT_BACKLOG | 2_ROADMAP/00_ENHANCEMENT_BACKLOG | KEEP(미래) |
| 08_LLM_AGENT_ORCHESTRATION_HANDOFF | 1_CURRENT/06_LLM_AGENT_HANDOFF | KEEP |
| 09_VALIDATION_AND_TESTS | 1_CURRENT/07_VALIDATION_AND_TESTS | KEEP |
| 10_DOCS_COVERAGE_MANIFEST | (폐기 대체) | **재작성**: 구 50-doc 배너라운드 증명문 → 본 리팩토 결과 manifest로 교체 |

### 3.2 docs/ 루트 설계문서 (18)
| 파일 | 액션 | 근거 |
|---|---|---|
| API_CONTRACT.md | KEEP→5_REFERENCE | 유일 엔드포인트 I/O 계약 |
| EVENT_SCHEMA.md | KEEP→5_REFERENCE | 필드레벨 스키마 단일출처 |
| COMPLIANCE_BOUNDARY.md | KEEP→5_REFERENCE | 유일 ToS allow/block |
| DATA_POLICY.md | KEEP→5_REFERENCE | retention/PII 정책 |
| DEPLOYMENT.md | KEEP→5_REFERENCE | 로컬 런북 |
| OBSERVABILITY.md | KEEP→5_REFERENCE | log-event 표 |
| PROMPT_EXPERIMENT_GUIDE.md | KEEP→5_REFERENCE | 노드추가 런북 |
| RAG_VECTOR_DESIGN.md | KEEP→5_REFERENCE/RAG_VECTOR | Milvus 스키마 |
| SEARCH_DESIGN.md | KEEP→5_REFERENCE/SEARCH | 3엔진 패턴 |
| FRONTEND_DESIGN.md | KEEP→5_REFERENCE/FRONTEND + **FIX** | Next.js 15.0.x→15.5.18 (C-7) |
| COMPATIBILITY_NOTES.md | KEEP→5_REFERENCE/COMPATIBILITY + **FIX** | LLM_PROVIDER 기본 mock (C-6) |
| LLM_AGENT_DESIGN.md | MERGE→5_REFERENCE/LLM_CLIENT_PROTOCOL | 프로토콜 본문 유지, **노드 real/mock 표는 삭제**(08에 존재) |
| AGENT_WORKFLOW.md | **DEL** | 01+08에 흡수, LLM 경로 stale |
| ARCHITECTURE.md | **DEL** | 01+02에 흡수, 7컨테이너/8mock 전부 오류(C-5/C-8) |
| COLLECTOR_DESIGN.md | **DEL** | legacy RSS 3소스, 01B+03 흡수(C-1) |
| DOCS_FINAL.md | **DEL** | 00_START_HERE가 대체, 순수 stale 포인터 |
| SKELETON_COMPLETION_CHECKLIST.md | **DEL** | 04+09 흡수, 수치 stale |
| TRD.md | **DEL** | STEP006~010 시점핀, 현재값=02 |

### 3.3 Orchestration_Construction/ (14) — 구현 완료 엔진의 설계청사진
| 파일 | 액션 | 흡수 타깃 |
|---|---|---|
| 00_ORCHESTRATION_OVERVIEW | KEEP→1_CURRENT(부분) | §7.1 Phase 정의 = 단일출처 |
| 06_LANGCHAIN..._RESEARCH | KEEP→2_ROADMAP | 0.2.76 ADR + 업그레이드 리스크 |
| 11_IMPLEMENTATION_DIFF_BLUEPRINT | KEEP→1_CURRENT | do-not-modify 계약 + phase 테스트 baseline |
| 02_SOURCE_ROLE_AND_PURPOSE_ROUTING | MERGE→1_CURRENT/03 | role 근거 + SourceProfile 스키마 |
| 03_COLLECTION_STRATEGY_ROUTER | MERGE→1_CURRENT/02 | 전략 라우터, evidence는 ARC |
| 04_BODY_EXTRACTION_AND_URL | MERGE→1_CURRENT/01 | body ladder, excerpt-gate 근거 ARC |
| 05_EVENT_QUEUE_AND_STORAGE | MERGE→1_CURRENT/04 | bridge 계약, dedup 설계 ARC |
| 07_AGENT_ORCHESTRATION_ARCH | MERGE→1_CURRENT/01 | 노드사이클, exec-form 설계 ARC |
| 08_RETRY_RATE_LIMIT_FAILURE | MERGE→1_CURRENT/04 | 실패 taxonomy, gdelt evidence ARC |
| 09_DATA_QUALITY_GATES | MERGE→1_CURRENT/01 | 품질게이트, corroboration evidence ARC |
| 10_COMMERCIALIZATION | MERGE→2_ROADMAP/COMMERCIALIZATION | ideation/13·18과 통합 |
| 12_RISK_CLOSURE_VALIDATION | MERGE→governance/RISK_REGISTER | phase-closure 서사 |
| 01_CODEBASE..._AUDIT | **ARC** | 시점 코드감사(509 stale) |
| README | **ARC**(또는 DEL) | "설계 전용/미구현" 선언 = 정면 오류(C-4) |

### 3.4 system_overview/ (13) — 다운스트림 개요(수집계층 stale)
| 파일 | 액션 | 근거 |
|---|---|---|
| 02_GLOSSARY_FULL_TERMS | KEEP→5_REFERENCE/GLOSSARY | 유일 용어집(죽은 수집용어 prune) |
| 04_BACKEND_API_AND_DATABASE | KEEP→5_REFERENCE(또는 API_CONTRACT 흡수) | 백엔드 API/DB |
| 06_LLM_RAG_SEARCH_PIPELINE | KEEP→5_REFERENCE + **FIX** | 노드 dev detail, 수치 08과 동기화 |
| 07_FRONTEND_AND_ADMIN_UI | KEEP→5_REFERENCE | 라우트/admin |
| 08_DOCKER_INFRA_AND_ENV | KEEP→5_REFERENCE/ENV_KEYS 통합 | 10컨테이너(정확) |
| 12_FILE_MAP_FOR_MAINTENANCE | KEEP→5_REFERENCE/FILE_MAP + **확장** | ingestion/ 트리 누락 보강 |
| 01_BIG_PICTURE_FOR_NON_DEVELOPERS | MERGE→1_CURRENT/01(평문 섹션) + 수집부 ARC | 비개발자 개요 |
| 05_COLLECTOR_QUEUE_WORKER_AGENT | SPLIT | worker/queue→02, RSS수집부 ARC |
| 11_NEXT_ENHANCEMENT_ROADMAP | SPLIT | Axis A/D→2_ROADMAP, **Axis B/C DEL**(이미 구현, C-3) |
| 00_INDEX | **DEL** | nav-only, 번들 해체 |
| 03_END_TO_END_DATA_FLOW | **DEL** | 01 흡수(step1-5 legacy) |
| 09_CURRENT_IMPLEMENTATION_STATUS | **DEL** | STEP011 stale, false TODO |
| 10_STUB_MOCK_TODO_MAP | **DEL** | DART/SEC/trafilatura false-TODO(C-3) |

### 3.5 _IDEATION_WEB_INTELLIGENCE/ (19)
| 파일 | 액션 |
|---|---|
| 02_POSITIONING / 04_TARGET_LAYERS / 05~14_LAYER_* / 15_ROADMAP / 18_EXEC | KEEP→2_ROADMAP (레이어 L1→L14순 정렬; 15·18은 통합) |
| 13_COMMERCIALIZATION | MERGE→2_ROADMAP/COMMERCIALIZATION (Orch/10·18과 단일화) |
| 00_MASTER_INDEX / 01_REPO_REALITY_AUDIT | **ARC** (P0/code-state 스냅샷 stale) |
| 03_REAL_WORLD_CASES | **ARC** (2026-06 시장 리서치 스냅샷) |
| 16_LAYER_BY_LAYER_100_CHECKLISTS | **ARC** (1641줄, 유지불가 bulk — 최대 단일 dead-weight) |
| 17_TEAM_AGENT_REVIEW | **ARC** (시점 회의록) |

### 3.6 finals·ingestion·governance·scaffold
| 파일 | 액션 |
|---|---|
| ingestion/INGESTION_FINAL.md | MERGE→1_CURRENT/03 + **FIX**(44/58→46/57, 509→1293) |
| ingestion/artifact_manifest_final.md | KEEP→5_REFERENCE |
| ingestion/rate_limit_evidence.md | KEEP→5_REFERENCE |
| Environment_setup/ENVIRONMENT_SETUP_FINAL.md | MERGE→1_CURRENT/02 + 원문 ARC + **FIX**(648 stale) |
| Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md | MERGE→1_CURRENT/01 + 원문 ARC + **FIX**(635 stale) |
| _RISK/RISK_REGISTER.md, RISK_CLOSED.md | KEEP→1_CURRENT/governance |
| _DECISIONS/2026-06.md | KEEP→1_CURRENT/governance/DECISIONS_2026-06 |
| _ARCHIVE_SUPERSEDED/_INDEX.md, _TRASH/README.md | 흡수→3_ARCHIVE scaffold |
| _DOCS_MD_INVENTORY_BEFORE.txt | KEEP→3_ARCHIVE (역사 인벤토리 증거) |

### 3.7 Harness_Construction/ (7)
전부 **KEEP→4_HARNESS** (live 구현 중). 단 §6 메모리 정정 필요: 01·05가 `narrative_marker.json`을 live로 기술 → DEAD 반영 정정.

---

## 4. ACTION 매트릭스 B — 빌드 히스토리 docs (plans 35 + ingestion/plans 8)

이 묶음이 사용자가 말한 "흐름·실패시도·인사이트"의 본체다. **삭제하지 않고 3_ARCHIVE에 시간순 정렬**한다.

| 묶음 | 파일 | 액션 |
|---|---|---|
| 루트 plans/ 000~012 plan+report 쌍 (30) | `000_ENVIRONMENT_SETUP`~`012_AGENT_ORCHESTRATION` | **ARC**→`3_ARCHIVE/2026-05_build_phases/` (번호=시간순, 그대로 정렬) |
| ingestion/plans/ 00~07 (8) | MASTER_PLAN, PHASE1~3, AGENT_PIPELINE, LOGGING, SOURCE_REGISTRY, VALIDATION | **ARC**→`3_ARCHIVE/2026-06_ingestion_design/` |
| 루트 plans/ 자동생성 slug 3 | `claude-code-plan-piped-flame.md`, `c-users-...-composed-toast.md`, `repo-sunny-barto.md` | **DEL**(승인 필요 §10-D4 — Claude Code 세션 자동저장 scratch로 추정, 내용 확인 후 삭제) |
| ingestion/plans/__init__.py | **DEL** | dead 패키지 스텁(.md 이관 후 빈 디렉토리) |

> `plans/`는 `.claude/settings.json plansDirectory`로 지정된 Claude Code 플랜 폴더다. 활성 플랜 저장 위치이므로 **폴더 자체는 유지**하되, 종결된 000~012 빌드 히스토리만 ARCHIVE로 이관한다(향후 새 플랜은 plans/에 계속 쌓임). 이관 후 plans/는 활성 플랜 전용으로 비워진다.

---

## 5. ACTION 매트릭스 C — 죽은코드·찌꺼기

### 5.1 CONFIRMED DELETE (grep 0 참조, 전부 gitignore·untracked — 로컬 디스크 정리)
`ingestion/outputs/` 하위 smoke/tmp 10개:
`_hook_smoke.py`, `state/_cooldown_smoke.py`, `tmp_gen_profiles.py`, `tmp_live_smoke.py`, `tmp_live_smoke_d.py`, `tmp_final_source_closure/_verify_state.py`, `tmp_g4_final_risk_closure/_verify_dist.py`, `tmp_orchestration_clean/live_baseline_smoke.py`, `tmp_p0_hardening/live_gate_smoke.py`, `tmp_production_closure/run_audit.py`
→ git 미추적이므로 **로컬 rm**(버전관리 영향 0). 빈 tmp_* 디렉토리도 함께 정리.

### 5.2 [확정: 유지 + ROADMAP 명시] 5 TEST_ONLY pipeline 모듈
`ingestion/pipeline/{discovery_collector, query_generator, search_enrichment_collector, event_candidate_extractor, canonical_event_builder}.py` + 각 단위테스트.
- 사실: 프로덕션 임포터 0, 서로도 임포트 안 함, 자기 테스트만 참조 = 미배선 "agent pipeline" 서브시스템.
- **결정(사용자 승인 2026-06-19): 유지.** 미래 배선 예정 설계다. **삭제 금지.** 대신 `2_ROADMAP/`에
  "미배선 pipeline 모듈(discovery→query→search-enrichment→candidate→canonical-event)" 항목을 신설해
  현황(코드 존재·테스트 존재·프로덕션 미배선)과 배선 계획을 명시한다. `1_CURRENT/04_OPEN_TASKS`에도 1줄 포인터.
- `event_queue.py`는 프로덕션 20+ 임포터 → KEEP(혼동 금지).

### 5.3 STRUCTURE SMELL — `ingestion/agents/` vs 최상위 `agents/` (§10-D2)
- 둘 다 LIVE, 별개 서브시스템(수집측 fetch graph/judge vs 카드측 event-processing worker). 네이밍 충돌만.
- 결정: 명확화 위해 한쪽 rename 권장(예: `ingestion/agents/` → `ingestion/fetch_graph/`). rename은 import 광범위 → 별도 atomic PR, 본 정리와 분리.

---

## 6. ACTION 매트릭스 D — 메모리·설정

| 파일 | 액션 | 근거 |
|---|---|---|
| `.harness/narrative_marker.json` | **DEL** + 명세정정 | DEAD. `turn_state_snapshot.py:9`가 closeout_stamp로 대체됨 명시, writer/reader 0. 단 Harness_Construction/01·05가 live로 기술 → 그 문구도 정정 |
| `.harness/docs_lifecycle_audit.json` | 결정필요(§10-D3) | WRITE_ONLY(생성만, 디스크 artifact 소비자 0; 테스트는 모듈 재생성). consumer 배선 또는 disposable 표시 |
| `ingestion/configs/extraction_policy.yaml` | **DEL** | 로더 0(Orch/01 doc만 stale 언급) |
| `ingestion/configs/llm_policy.yaml` | **DEL** | 로더 0 |
| `ingestion/configs/playwright_policy.yaml` | **DEL** | 로더 0 |
| `ingestion/configs/phase1_sources.yaml` | **DEL**(DUP) | 로더 0, source_registry.yaml `phase:` 필드가 실 라우팅(run_phase.py:16) |
| `ingestion/configs/phase2_sources.yaml` | **DEL**(DUP) | 동일 |
| `ingestion/configs/phase3_sources.yaml` | **DEL**(DUP) | 동일 |
| `MIGRATION_READINESS.md`(루트) | MERGE→Environment_setup 후 **DEL** 또는 ARC | STALE("커밋대기" 거짓 배너), Harness_Construction/06이 대체 |
| `README.md`(루트) | **FIX** | 소스/테스트 수치만 갱신 |
| 7 LIVE yaml, 5 LIVE harness json, settings 3, hooks 5, skills 6, agents 15, CLAUDE.md, PROJECT_STATUS.md | **KEEP** | wiring 검증 완료 |

> **DEL 전 필수 확인**: extraction_policy/llm_policy/playwright_policy/phase{1,2,3}_sources 6개 yaml은 git 추적이므로 `git rm`. 삭제 전 `git grep`로 코드 로더 0 재확인(명세 §9 게이트). phase yaml 삭제 시 registry `phase:` 필드 완전성 확인.

---

## 7. 통폐합 클러스터 (중복 제거 맵)

| 클러스터 | 생존(survivor) | 흡수/삭제 대상 |
|---|---|---|
| architecture-snapshot | 1_CURRENT/02 | ARCHITECTURE(DEL), TRD(DEL), Orch/03(merge) |
| implemented-flow | 1_CURRENT/01 | AGENT_WORKFLOW(DEL), so/03(DEL), Orch/04/07/09(merge) |
| source-status | 1_CURRENT/03 | INGESTION_FINAL(merge), Orch/02(merge) |
| status-snapshot(테스트/mock 수) | 1_CURRENT/07+04 | so/09(DEL), so/10(DEL), SKELETON(DEL), DOCS_FINAL(DEL) |
| collection-legacy(RSS) | 1_CURRENT/01 §B | COLLECTOR_DESIGN(DEL), so/05 RSS부(ARC), so/03 step1-5(DEL) |
| orchestration-design | 1_CURRENT/01+02 + Orch/00,06,11 | Orch/03,04,05,07,08,09(merge→ARC), Orch/01·README(ARC) |
| llm-agent-design | 1_CURRENT/06 | LLM_AGENT_DESIGN(노드표 DEL), so/06(동기화), Orch/07(merge) |
| api+event schema | 5_REFERENCE: API_CONTRACT+EVENT_SCHEMA | so/04(흡수) |
| env-key 표 (★4중복) | 5_REFERENCE/ENV_KEYS (단일) | 02·so/08·COMPATIBILITY·DEPLOYMENT의 4벌 → 1벌 |
| commercialization (★3중복) | 2_ROADMAP/COMMERCIALIZATION | Orch/10·ideation/13·ideation/18 → 1벌 |
| code-state 스냅샷 | (불필요, 현재=01/09) | ideation/00,01,16,17(ARC) |
| risk | governance/RISK_REGISTER | Orch/12(merge), RISK_CLOSED(보완) |

**최대 효과 4건:** ① status-snapshot 4문서 DEL ② ideation/16(1641줄) ARC ③ Orchestration 설계 6문서 → canonical+ARC 압축 ④ env-key 표 4벌→1벌, 노드 real/mock 표 3벌→1벌.

---

## 8. 마이그레이션 실행 단계 (순서·검증 게이트)

각 Phase 종료 시 §9 게이트 전체 통과해야 다음 진행. 모든 이동은 `git mv`, 삭제는 `git rm`(추적) 또는 로컬 rm(gitignore).

- **Phase 0 — 백업 태그**: `git tag pre-refactor-2026-06-19`. 작업 브랜치 `chore/docs-code-consolidation` 생성(main 직접 금지).
- **Phase 1 — 무손실 삭제(저위험)**: §5.1 outputs 10개(로컬 rm) + §6 dead yaml 6개(`git rm`) + `.harness/narrative_marker.json`(`git rm`) + ingestion/plans/__init__.py. → 게이트.
- **Phase 2 — docs 순수중복 삭제**: §3 DEL 11개(루트6 + so 4 + so/11 BC부) `git rm`. → 게이트(링크 무결성).
- **Phase 3 — 타깃 골격 생성**: `docs/{00_START_HERE.md,1_CURRENT,2_ROADMAP,3_ARCHIVE,4_HARNESS,5_REFERENCE}` + 3_ARCHIVE 시간축 서브폴더 + `3_ARCHIVE/README.md`(정렬기준 선언). 빈 골격 커밋.
- **Phase 4 — KEEP 이관(git mv)**: _CANONICAL→1_CURRENT/2_ROADMAP, reference군→5_REFERENCE, Harness_Construction→4_HARNESS, governance→1_CURRENT/governance. 개명 동시 수행. → 게이트.
- **Phase 5 — 히스토리 ARCHIVE 이관**: plans/000~012 + ingestion/plans/*.md + ideation 스냅샷 + Orch/so legacy → 3_ARCHIVE 시간축 폴더. → 게이트.
- **Phase 6 — MERGE(고유내용 흡수)**: §7 클러스터별로 survivor에 고유내용 흡수, 흡수 후 원문 ARC/DEL. env-key·노드표·commercialization 단일화. → 게이트.
- **Phase 7 — FIX(수치/주장 정정)**: 509/635/648/~108→1293·1517, 44/58→46/57, Next 15.5.18, LLM_PROVIDER mock, DART/SEC false-TODO 제거. → 게이트.
- **Phase 8 — 인덱스·manifest 재작성**: 00_START_HERE 재작성(새 구조), 10_DOCS_COVERAGE_MANIFEST→리팩토 결과 manifest로 교체, FILE_MAP에 ingestion 트리 추가, 모든 상호링크 갱신. → 게이트.
- **Phase 9 — 최종 검증·커밋**: §9 전체 + 링크 깨짐 0 + 고아 참조 0. 커밋.

> NEEDS-DECISION 항목(§10)은 승인 전까지 건드리지 않는다. 승인 시 별도 Phase로 삽입.

---

## 9. 검증 게이트 (매 Phase 공통)

```powershell
# 1. 전체 테스트 (회귀 0)
.venv\Scripts\python.exe -m pytest ingestion/tests backend workers agents -q
# 2. 시크릿 스캔
.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths ingestion backend workers agents docs
# 3. diff/status 위생
git diff --check ; git status --short
# 4. 죽은코드 재스캔(삭제 Phase 후)
.venv\Scripts\python.exe scripts\dead_code_scan.py    # 후보 수 감소 확인
```
추가 문서 게이트:
- **링크 무결성**: 이동/삭제 후 `git grep -n "삭제된파일명\|구경로"` = 0(고아 링크 없음).
- **참조 무결성(코드)**: 삭제 yaml/모듈에 대한 `git grep "import\|safe_load(...yaml)"` = 0.
- **docs_conflict hook**: Stop hook의 google_trends_explore/status mislabel 플래그 0.
- **단일출처 불변**: 같은 수치(테스트수·소스수·버전)가 2곳 이상에 하드코딩되지 않음(grep 교차확인).

통과 기준 = 테스트 **1517 passed/5 skip 유지**(현재 baseline), secret PASS, diff clean, 링크 깨짐 0.

---

## 10. 사용자 승인 필요 결정 (실행 전 확정)

| # | 결정 | 옵션 | 권장 |
|---|---|---|---|
| D1 | 5 TEST_ONLY pipeline 모듈 | ~~(b) 폐기~~ / **(a) 유지+ROADMAP 명시** | ✅ **확정(2026-06-19): 유지**. 2_ROADMAP에 미배선 pipeline 명시(§5.2) |
| D2 | `ingestion/agents` vs `agents` rename | (a) 현상유지(스멜만 문서화) / (b) `ingestion/fetch_graph`로 rename(별도 PR) | (a) 본 정리와 분리, 추후 |
| D3 | `.harness/docs_lifecycle_audit.json` | (a) consumer 배선 / (b) disposable 표시 후 무시 | (b) |
| D4 | plans/ 자동생성 slug 3개 삭제 | 내용확인 후 DEL | **확인 요청** — scratch면 DEL |
| D5 | Orch/README·so legacy: ARC vs DEL | 공격적이면 DEL, 보수면 ARC | 사용자 정렬축=공격적 → 순수선언은 DEL, 서사는 ARC |
| D6 | 4_HARNESS·governance를 루트 `harness/`로 승격? | docs는 제품전용 / docs에 포함 | 현 명세는 **docs 포함** 유지 |

---

## 11. 리스크·롤백

| 리스크 | 완화 |
|---|---|
| 대량 git mv로 blame/링크 유실 | `git mv`만 사용(blame 보존), Phase별 게이트에서 링크 grep=0 강제 |
| MERGE 중 고유내용 누락 | 원문은 ARC로 먼저 이동 후 삭제(Phase 6은 흡수→ARC, 즉시 DEL 금지) |
| 삭제 yaml이 런타임에서 동적 로드 | §9 참조게이트 `safe_load` grep=0, 테스트 1517 유지로 이중확인 |
| 5 pipeline 모듈 오삭제 | D1 승인 전 동결 |
| 되돌리기 | `git tag pre-refactor-2026-06-19`로 전체 복구 가능 |

---

## 부록 — 정량 요약

- **DELETE(docs)**: 11 (루트6 + so4 + so11-BC). **DELETE(코드/설정)**: outputs 10(로컬) + dead yaml 6 + narrative_marker 1 + plans/__init__ 1.
- **ARCHIVE**: ideation 5 + Orch 설계원문 ~8 + so legacy 2 + plans 38(빌드히스토리) + Env/Trace 원문 2.
- **MERGE→canonical**: ~14 (Orch 6 + INGESTION/Env/Trace 3 + commercialization 3 + so split 2).
- **KEEP→이관**: _CANONICAL 10 + reference ~17 + Harness 7 + governance 4.
- **순효과**: 탐색 진입점 1개(00_START_HERE), `1_CURRENT/`는 7+governance의 신뢰 코어, 루트 평면 노출(plans 35)·중복표(env 4벌/노드 3벌) 제거. 134 .md → 활성 ~45 + ARCHIVE 정렬보관.
- **NEEDS-DECISION**: D1~D6 (특히 D1 5모듈, D4 slug 3).

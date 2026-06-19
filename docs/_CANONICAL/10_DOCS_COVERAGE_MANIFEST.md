# 10 — DOCS COVERAGE MANIFEST (전수 처리 증명)

> ⚠️ **이 manifest 는 2026-06-16 배너-only 라운드의 증명문서다(역사 기록).** 2026-06-19 구조 리팩토링(`Harness_Construction/07` 실행)으로 docs/ 가 생애주기 구조로 재편되며, 아래 표의 다수 파일이 **삭제(history 보존)·`3_ARCHIVE/`·`5_REFERENCE/`·`2_ROADMAP/` 로 이동**됐다. 현재 docs 지도는 **`docs/00_START_HERE.md`** 가 권위. 이 표는 "원본 50 + ideation 19 가 누락 없이 추적됐다"는 과거 증명으로만 유효하다.

- 원본 MD: **50개**(`docs/_DOCS_MD_INVENTORY_BEFORE.txt`와 1:1). 단 하나도 누락하지 않았다.
- 처리 결과 분류: KEEP_AS_CANONICAL / MERGED_INTO_CANONICAL / SPLIT_INTO_TASKS_AND_RISKS / SUPERSEDED_ARCHIVE(배너) / NEEDS_MANUAL_REVIEW.
- Final action의 (배너)는 원본 상단에 SUPERSEDED 배너를 부착했음을 뜻한다(**삭제·이동 없음**).

---

## 그룹 A — docs/ 루트 설계문서 (18)

| No | Source file | Summary | Items | Final action | Canonical target | Notes |
|---|---|---|---:|---|---|---|
| 1 | AGENT_WORKFLOW.md | Claude/Codex worktree·LLM 라우팅 | 7 | MERGED | 01,08 | LLM 경로 정확 |
| 2 | API_CONTRACT.md | FastAPI 엔드포인트 계약 | 10 | KEEP | 01,02 | 다운스트림 현행 |
| 3 | ARCHITECTURE.md | STEP 005 컴포넌트 스냅샷 | 7 | SUPERSEDED(배너) | 02,01 | 7컨테이너/8mock stale(C-5,C-8) |
| 4 | COLLECTOR_DESIGN.md | workers RSS 3소스 설계 | 7 | SUPERSEDED(배너) | 01B,03 | legacy 수집경로 |
| 5 | COMPATIBILITY_NOTES.md | 환경/호환 누적 노트 | 10 | SPLIT | 04,05,06 | LLM_PROVIDER 충돌(C-6) |
| 6 | COMPLIANCE_BOUNDARY.md | 법무/ToS 경계·소스 allow/block | 8 | KEEP | 05,03 | dcinside 라벨만 갱신 |
| 7 | DATA_POLICY.md | 저장 데이터 정책·TTL 미정 | 5 | KEEP | 05,04 | TTL TODO(T-BeB) |
| 8 | DEPLOYMENT.md | 로컬 스택 기동·smoke | 7 | KEEP | 01,09 | 현행 |
| 9 | DOCS_FINAL.md | 구 docs 진입점 | 7 | 포인터 갱신(배너) | 00,06 | 509/14·15 stale(C-2) |
| 10 | EVENT_SCHEMA.md | 전 스키마 정의 | 6 | KEEP | 02 | 잘 유지됨 |
| 11 | FRONTEND_DESIGN.md | Next.js 설계 | 7 | MERGED | 02,01 | 버전 stale(C-7) |
| 12 | LLM_AGENT_DESIGN.md | BaseLLMClient 계약 | 8 | MERGED | 08,02 | 로드맵 일부 stale |
| 13 | OBSERVABILITY.md | LangSmith·로그 패턴 | 7 | SPLIT | 04,05 | 미구현 항목 분리 |
| 14 | PROMPT_EXPERIMENT_GUIDE.md | 프롬프트 관리·실험 | 6 | KEEP | 08,04 | 현행 |
| 15 | RAG_VECTOR_DESIGN.md | Milvus 벡터 RAG | 8 | MERGED | 02,04 | 일부 TODO |
| 16 | SEARCH_DESIGN.md | 3엔진 검색 분리 | 7 | KEEP | 02,04 | hybrid 미구현 |
| 17 | SKELETON_COMPLETION_CHECKLIST.md | STEP 011 최종 스냅샷 | 6 | MERGED | 09,04 | ingestion 테스트 미포함 |
| 18 | TRD.md | STEP006~010 기술요구 | 9 | SUPERSEDED(배너) | 02,04 | 시점별 핀(현재값=02) |

## 그룹 B — docs/Orchestration_Construction (14)

| No | Source file | Summary | Items | Final action | Canonical target | Notes |
|---|---|---|---:|---|---|---|
| 19 | README.md | 설계세트 안내 | 5 | SUPERSEDED(배너) | 06,01 | "설계 전용" stale(C-4) |
| 20 | 00_ORCHESTRATION_OVERVIEW...md | D-1~D-11 결정·로드맵 | 14 | KEEP | 01,04,08 | Phase 정의 단일출처 |
| 21 | 01_CODEBASE..._AUDIT.md | 양 시스템 감사·삽입점 | 10 | MERGED | 02,04,05 | 509 stale, U-1/U-4 open |
| 22 | 02_SOURCE_ROLE_AND_PURPOSE_ROUTING.md | 57소스 역할·tier | 10 | MERGED | 02,03 | PurposeRouter→strategy_router 흡수 |
| 23 | 03_COLLECTION_STRATEGY_ROUTER_DESIGN.md | 전략 라우터·G3/G4 체인 | 13 | MERGED | 01,02 | enum 독립파일 미생성 |
| 24 | 04_BODY_EXTRACTION_AND_URL_RESILIENCE.md | body cascade·복원력 | 10 | MERGED | 01,04 | news body≈0 open |
| 25 | 05_EVENT_QUEUE_AND_STORAGE_SCHEMA.md | 이벤트큐·5계층 저장 | 11 | SPLIT | 01,04,05 | Redis/PG bridge 미구현 |
| 26 | 06_LANGCHAIN_LANGGRAPH_DEEPAGENTS_RESEARCH.md | 버전·Deep Agents 판단 | 8 | MERGED | 02,04,07 | collection_graph 미생성 |
| 27 | 07_AGENT_ORCHESTRATION_ARCHITECTURE.md | 노드 사이클 설계 | 9 | MERGED | 01,02,04 | nodes.py 미생성(단순화) |
| 28 | 08_RETRY_RATE_LIMIT_FAILURE_POLICY.md | 재시도·rate-limit·격리 | 11 | SPLIT | 01,04,05 | Celery 4파일 미생성 |
| 29 | 09_DATA_QUALITY_EVALUATION_AND_RISK_GATES.md | 품질·안전 게이트 | 11 | SPLIT | 01,04,05 | publish 배선 미완 |
| 30 | 10_COMMERCIALIZATION_PRODUCT_OPTIMIZATION.md | 상업화 전략 | 7 | KEEP | 07,08 | 순수 전략 |
| 31 | 11_IMPLEMENTATION_DIFF_BLUEPRINT.md | Phase A~H diff 청사진 | 15 | KEEP | 01,04 | §9d 실구현 기록 |
| 32 | 12_RISK_CLOSURE_AND_VALIDATION_PLAN.md | 25+ risk·1205 테스트 | 13 | KEEP | 05,09,04 | 위험표 정확 |

## 그룹 C — docs/system_overview (13)

| No | Source file | Summary | Items | Final action | Canonical target | Notes |
|---|---|---|---:|---|---|---|
| 33 | 00_INDEX.md | 읽기순서 안내 | 3 | NEEDS_REVIEW | 08,02 | 09/10/11 stale 라우팅 |
| 34 | 01_BIG_PICTURE_FOR_NON_DEVELOPERS.md | 비개발자 전체그림 | 6 | SPLIT | 01,03,04 | RSS 3소스 부분 폐기 |
| 35 | 02_GLOSSARY_FULL_TERMS.md | 용어사전 60+ | 10 | MERGED | 02,03 | 수집 항목 폐기 |
| 36 | 03_END_TO_END_DATA_FLOW.md | 13단계 흐름 | 4 | SPLIT | 01,03,06 | step1 폐기, 2~13 유효 |
| 37 | 04_BACKEND_API_AND_DATABASE.md | 백엔드 API·DB | 7 | KEEP | 02 | 다운스트림 현행 |
| 38 | 05_COLLECTOR_QUEUE_WORKER_AGENT.md | 수집·큐·워커·에이전트 | 8 | SPLIT | 01,03,06 | 큐/워커 유효, 수집 폐기 |
| 39 | 06_LLM_RAG_SEARCH_PIPELINE.md | LLM·RAG·검색 | 9 | KEEP | 02,04 | 노드 real/mock 정확 |
| 40 | 07_FRONTEND_AND_ADMIN_UI.md | 프론트·Admin | 7 | KEEP | 02 | 현행(15.5.18) |
| 41 | 08_DOCKER_INFRA_AND_ENV.md | 10컨테이너·env | 7 | KEEP | 02,05 | 현행 |
| 42 | 09_CURRENT_IMPLEMENTATION_STATUS.md | STEP011 상태표 | 6 | SUPERSEDED(배너) | 04,09 | 수집계층 stale(C-3) |
| 43 | 10_STUB_MOCK_TODO_MAP.md | mock/TODO 집계 | 8 | SUPERSEDED(배너) | 04,06 | DART/SEC 오TODO(C-3) |
| 44 | 11_NEXT_ENHANCEMENT_ROADMAP.md | 4축 고도화 | 8 | SUPERSEDED(배너) | 07,06,03 | AxisB/C 폐기, A/D 유효 |
| 45 | 12_FILE_MAP_FOR_MAINTENANCE.md | 파일맵 | 9 | NEEDS_REVIEW | 02,04 | ingestion/ 트리 누락 |

## 그룹 D — finals & ingestion (5)

| No | Source file | Summary | Items | Final action | Canonical target | Notes |
|---|---|---|---:|---|---|---|
| 46 | Environment_setup/ENVIRONMENT_SETUP_FINAL.md | 환경세팅 CLOSED | 12 | KEEP | 02,05 | 648 테스트 stale(범위 외) |
| 47 | Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md | closing round trace | 10 | KEEP | 01,03,09 | 635 stale(T-DocA) |
| 48 | ingestion/INGESTION_FINAL.md | 수집계층 권위문서 | 11 | NEEDS_REVIEW | 01,03,04,09 | 44/58·509 stale(C-2) |
| 49 | ingestion/artifact_manifest_final.md | 산출물 재생성 매니페스트 | 7 | MERGED | 09,01 | G-4 산출물 추가 필요(T-DocB) |
| 50 | ingestion/rate_limit_evidence.md | provider rate-limit 근거 | 8 | KEEP | 05,03 | 정확·자족적 |

## 그룹 E — docs/_IDEATION_WEB_INTELLIGENCE (19, 2026-06-16 신설)

> 원본 50개 인벤토리(`_DOCS_MD_INVENTORY_BEFORE.txt`) **이후**에 만들어진 전략/확장 문서 세트.
> 위 50행 집계에는 포함되지 않으며, 본 그룹으로 별도 추적한다. 성격은 "현재 구현"이 아니라 **확장 전략·로드맵**.
> 분류: ABSORB(구현돼 canonical이 참조) / MIXED(일부 구현) / ROADMAP_ONLY(미구현 미래) / ARCHIVE(기록물) / SUPERSEDED(코드-상태 stale).
> code-state stale 4개(00·01·16·17)에는 **STALE 배너 부착**(원문 보존, 삭제 없음). 근거: Pre-Harness Cleanup Sprint 2026-06-18.

| No | Source file | 성격 | Classification | Canonical 관계 |
|---|---|---|---|---|
| E1 | 00_MASTER_INDEX.md | 진입점·P0 결론 | SUPERSEDED(배너) | P0=배선은 완료됨 → 01,09 |
| E2 | 01_CURRENT_REPO_REALITY_AUDIT.md | 코드 실상태 감사 | SUPERSEDED(배너) | redis/mock/bridge stale → 01,09 |
| E3 | 02_SEARCH_ENGINE_VS_EVENT_INTELLIGENCE_CONCEPT.md | 포지셔닝 논제 | ABSORB | 02가 참조할 불변 논제 |
| E4 | 03_REAL_WORLD_CASES_AND_MARKET_PATTERNS.md | 36 시장 사례 | ARCHIVE | 2026-06 시점 리서치 |
| E5 | 04_TARGET_ARCHITECTURE_LAYERS.md | L0~L14 목표 | MIXED | L4/L10 현재상태 stale, 틀은 유효 |
| E6 | 05_DISCOVERY_AND_SOURCE_EXPANSION_LAYER.md | L1 discovery | MIXED | source_role 구현, 자동 discovery 미구현 |
| E7 | 06_SEARCH_API_AND_WEB_EXPLORATION_LAYER.md | L2 search router | ROADMAP_ONLY | 미구현(SearchProvider 0건) |
| E8 | 07_REDIS_QUEUE_CACHE_STREAM_LAYER.md | L4 queue | MIXED | A redis+DLQ 구현, Celery 미구현 |
| E9 | 08_RAG_VECTOR_DB_LAYER.md | L5/L6 RAG | ROADMAP_ONLY | hybrid/rerank/nori 미구현 |
| E10 | 09_KG_RAG_GRAPH_RAG_LAYER.md | L7 KG-RAG | ROADMAP_ONLY | 도입 보류(미구현) |
| E11 | 10_AGENT_ORCHESTRATION_LAYER.md | L10 agent | MIXED | 결정 유효, mock 노드 진술 stale |
| E12 | 11_LLM_SOURCE_SUPERVISOR_AND_JUDGE_LAYER.md | L9 supervisor | MIXED | decide() gate 구현, 실 provider 미배포 |
| E13 | 12_EVENT_CLUSTERING_RANKING_AND_DEDUP_LAYER.md | L8 clustering | MIXED | cross_source_dedup 구현, 고급 algo 미구현 |
| E14 | 13_COMMERCIALIZATION_AND_PRODUCT_STRATEGY.md | 수익화 전략 | ROADMAP_ONLY | product surface 미구현 |
| E15 | 14_SECURITY_LEGAL_SAFETY_AND_NO_BYPASS.md | 보안·법무 | MIXED | 정책게이트 구현, SSRF/TTL/PII 미구현 |
| E16 | 15_IMPLEMENTATION_ROADMAP.md | Phase 0~10 | ABSORB | 본문 self-reconcile, 04와 동기 |
| E17 | 16_LAYER_BY_LAYER_100_CHECKLISTS.md | 1500 체크리스트 | ARCHIVE(배너) | backlog 참조, 일부 stale |
| E18 | 17_TEAM_AGENT_REVIEW.md | 11관점 리뷰 | ARCHIVE(배너) | 시점 기록물, 일부 stale |
| E19 | 18_FINAL_EXECUTIVE_SUMMARY.md | 경영 요약 | ABSORB | §B self-reconcile, 현행 서술 |

> Group E 처리: ABSORB 4(E3·E16·E19·E5 일부) / MIXED 7 / ROADMAP_ONLY 4 / ARCHIVE 2 / SUPERSEDED 2.
> 배너: STALE 4개(E1·E2·E17·E18) + ABSORB canonical 포인터 3개(E3·E16·E19, 2026-06-18 closure). 나머지는 배너 없음.

---

## 집계

| Final action | 수 |
|---|---:|
| KEEP_AS_CANONICAL | 18 |
| MERGED_INTO_CANONICAL | 13 |
| SPLIT_INTO_TASKS_AND_RISKS | 8 |
| SUPERSEDED_ARCHIVE(배너) | 7 |
| NEEDS_MANUAL_REVIEW | 3 |
| 포인터 갱신(배너, DOCS_FINAL) | 1 |
| **합계(원본 50)** | **50** ✅ (배너 부착 = 7 + 1 = **8개** 원본) |
| (별도) Group E ideation | 19 (STALE 배너 4개 추가) |

> 누락 검증: `docs/**/*.md` 카운트(원본 50 + `_CANONICAL/` 11 + `_IDEATION_WEB_INTELLIGENCE/` 19 +
> `_DOCS_MD_INVENTORY_BEFORE.txt`는 .txt라 비대상). 원본 50행 + Group E 19행으로 전수 추적.
> 모든 원본의 원자항목은 canonical 문서로 흡수되거나 SUPERSEDED 배너로 추적된다.

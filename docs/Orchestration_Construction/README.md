# docs/Orchestration_Construction — 오케스트레이션 구축 설계 문서 세트

> **이 폴더는 설계(blueprint)다. 구현 코드는 아직 적용되지 않았다.**
> 이번 라운드는 `docs/Orchestration_Construction/` 아래 단계별 구현 상세 명세서만 작성했다.
> 실제 구현은 **다음 턴**에서, 각 Phase atomic + 검증 통과를 조건으로 진행한다.
> 상위 근거: `plans/012_AGENT_ORCHESTRATION_PLAN.md`를 비개발자도 따라갈 수 있게 확장·상세화한 것.

---

## 이 폴더가 푸는 문제 (한 문장)

레포에는 **44개 소스를 수집하는 강력한 엔진(`ingestion/`)**과 **사건을 카드로 만들어 보여주는 다운스트림 앱(`backend/workers/agents/frontend`)**이 둘 다 있지만 **연결되어 있지 않다.** 오케스트레이션은 이 둘을 잇고(브리지), 주기/이벤트 기반으로 자동 수집하며, 실패·rate-limit·격리·품질·법무 리스크를 닫는 일이다.

---

## 읽는 순서

| 순서 | 문서 | 목적 |
|---|---|---|
| 0 | **00_ORCHESTRATION_OVERVIEW_AND_USER_DECISIONS.md** | ★ 진입점. 현재 상태, 설치/결정/확인 사항, 로드맵 |
| 1 | **01_CODEBASE_AND_SYSTEM_OVERVIEW_AUDIT.md** | 코드·문서 분석 결과, insertion point |
| 2 | **02_SOURCE_ROLE_AND_PURPOSE_ROUTING.md** | 소스 특징별 목적 라우팅 |
| 3 | **03_COLLECTION_STRATEGY_ROUTER_DESIGN.md** | 전략 라우터(결정적) |
| 4 | **04_BODY_EXTRACTION_AND_URL_RESILIENCE.md** | 본문 추출 cascade·복원력 |
| 5 | **05_EVENT_QUEUE_AND_STORAGE_SCHEMA.md** | 이벤트 큐·저장 스키마 |
| 6 | **06_LANGCHAIN_LANGGRAPH_DEEPAGENTS_RESEARCH.md** | 공식 문서 조사·도입 판단(버전 차이 포함) |
| 7 | **07_AGENT_ORCHESTRATION_ARCHITECTURE.md** | 노드(단계) 설계·deterministic/agentic 경계 |
| 8 | **08_RETRY_RATE_LIMIT_FAILURE_POLICY.md** | 재시도·rate-limit·격리·quota |
| 9 | **09_DATA_QUALITY_EVALUATION_AND_RISK_GATES.md** | 품질·안전 게이트 |
| 10 | **10_COMMERCIALIZATION_PRODUCT_OPTIMIZATION.md** | 상용화·제품 최적화 |
| 11 | **11_IMPLEMENTATION_DIFF_BLUEPRINT.md** | 파일 단위 구현 청사진(Phase A~H) |
| 12 | **12_RISK_CLOSURE_AND_VALIDATION_PLAN.md** | 전체 risk 폐쇄·검증·readiness 판정 |

비개발자/의사결정자는 **00 → 10 → 12**만 읽어도 핵심(무엇을·왜·결정사항·리스크)을 파악할 수 있다.
구현자는 **00 → 01 → 03~09 → 11**을 따라간다.

---

## 현재 승인된 기본 방향 (2026-06-14 재검토 — APPROVE_DIRECTION)

코드 실재 검증(read-only) 결과 설계 전제가 실제 코드와 **전부 일치**하여 방향성을 승인하고 문서에 반영했다.

- **1차 ROI**: 신규 프레임워크가 아니라 **44개 수집 소스를 다운스트림에 `bridge_to_raw_events`로 연결**(코드로 뒷받침).
- **3층 아키텍처**: Layer 1 deterministic 수집(Phase A~E, 설치 0) / Layer 2 기존 LangGraph 0.2.76 사건처리 / Layer 3 future 고급 에이전트(Deep Agents 우선·CrewAI 비교·MS Agent Framework 장기 — **지금 설치 안 함**).
- **D-6 강화**: `create_raw_event`가 async+pydantic+AsyncSession 요구 → 별도 어댑터 확정.
- **D-5 확장**: MVP 5필드 + 근거추적 확장필드(raw_artifact_path/extracted_text_ref/canonical_url/body_missing/error_type).
- **버전**: langgraph 0.2.76 / langchain 0.2.11 유지(실측 핀 확인, v1 업그레이드 금지).
- **보안**: 루트 `gcp-service-account-key.json` = `.gitignore` 포함 + git 미추적 확인(V-9 RESOLVED).
- **원문 5계층**: artifact_store(internal) / EventQueue(JSONL) / raw_events / event_cards / Milvus+OpenSearch — 내부저장 ≠ 외부공개(전문 재배포 금지).
- **설치 정책**: Phase A~E 신규 설치 0. 모든 신규 설치/컨테이너 기동은 `INSTALL_CANDIDATE_REQUIRES_USER_APPROVAL`.
- **Phase 정의 단일 출처**: `00 §7.1 Final implementation stance` (Phase A~I 설치/인프라 의존성). 문서 간 Phase 정의가 어긋나면 이 표 기준으로 정렬한다.

## 다음 구현 턴의 시작 파일

- **Phase A 진입점(신규 생성 예정)**: `ingestion/orchestration/run_orchestration_cycle.py`
- **첫 작업**: 44 소스를 주기 bucket에 따라 `run_collection_probe`로 수집하고 결과를 `EventQueue`(JSONL)에 적재하는 deterministic local cycle. **신규 설치 0.**
- 상세: `11_IMPLEMENTATION_DIFF_BLUEPRINT.md §9 phased commit plan`.

---

## 사용자 결정 항목 요약 (상세: 00 §5, §6)

| 결정 | 기본 권장값 |
|---|---|
| 1차 구현 형태 | deterministic local cycle 먼저(Celery 보류) |
| langgraph 버전 | 0.2.76 유지(v1 업그레이드 보류) |
| Deep Agents | 미도입 |
| 다운스트림 저장 | 기존 Postgres 재사용 |
| 이벤트 큐 1차 | JSONL(→ Phase G Redis) |
| 브리지 방식 | 별도 어댑터 task |

**확인 필요(차단)**: 루트 `gcp-service-account-key.json`이 `.gitignore`에 있는지(보안). Phase G 진입 시 Redis/Postgres 컨테이너 가동 가능 여부, Windows Celery worker pool(`--pool=solo`).

---

## forbidden actions (이 폴더 전체 불변)

- 이번 턴에 오케스트레이션 코드 구현 금지(설계만).
- `source runner / ingestion code / configs / tests` 수정 금지.
- git push / git reset --hard / git clean / rm·Remove-Item 금지.
- `.env` 실제 키 값 출력 금지.
- provider rate-limit 우회 금지(proxy rotation / internal RPC / Google Trends bypass / CAPTCHA·login·paywall 우회).
- `google_trends_explore`를 PASS로 표기 금지(CONFIRMED_EXTERNAL_RATE_LIMIT).
- MCP/Plugin 설치 resurrect 금지(필요 시 future architecture review로만).
- LangChain/LangGraph/Deep Agents 도입을 무조건 전제하지 않음(06 판단 기준).
- 실패/미검증 상태를 PASS로 표기 금지.

---

## risk closure summary (상세: 12)

- 25개 risk를 status로 닫음: CLOSED_BY_DESIGN / CLOSED_BY_TEST_PLAN / USER_CONFIRMATION_REQUIRED / BLOCKED_BY_POLICY / DEFERRED_WITH_TRIGGER.
- BLOCKED_BY_POLICY(우회 불가): provider 429 우회, CAPTCHA/paywall 우회, trends bypass, MCP 재설치, .env 노출, 투자 조언.
- DEFERRED_WITH_TRIGGER: 브리지(Phase H), asyncio(Phase F/G), prompt injection(LLM 노드), U-1/U-3(구현 직전 VERIFY).
- **판정**: 다음 구현 턴은 Phase A부터 시작 가능(설치 0). 차단 요소는 보안 확인(gcp 키)뿐이며 Phase A~E 진행을 막지 않는다.

---

## 핵심 통찰 3줄

1. **이미 만든 두 자산(수집 엔진 44소스 ↔ 다운스트림 앱)을 연결하는 브리지가 최대 ROI다.**
2. **Phase A~E는 신규 인프라 0으로 가능하다. Celery/Redis(Phase G)는 그 위에 얹는 선택지이지 전제가 아니다.**
3. **수집은 deterministic, LLM은 가치 지점에만 — 비용·비결정성·법무 리스크를 구조적으로 통제한다.**

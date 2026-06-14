# 00 — 오케스트레이션 구축 개요 및 사용자 결정 사항

> **이 문서의 위치**: `docs/Orchestration_Construction/` 설계 문서 세트의 **진입점**.
> **성격**: 설계 명세(blueprint). **이 폴더의 어떤 문서도 코드를 실제로 적용하지 않는다.** 구현은 다음 턴에서 한다.
> **상위 근거**: `plans/012_AGENT_ORCHESTRATION_PLAN.md`(구현 PLAN, 2026-06-12). 이 폴더는 plans/012를 **비개발자도 따라갈 수 있도록 확장·상세화**한 것이다.
> **최종 갱신**: 2026-06-14

---

## 0. 이 문서를 읽는 사람에게 (비개발자 포함)

"오케스트레이션(orchestration)"이라는 단어가 낯설 수 있다. 한 문장으로 풀면 이렇다.

> **여러 데이터 소스(뉴스·공시·커뮤니티·트렌드·시세)를 "언제, 어떤 방법으로, 얼마나 자주, 실패하면 어떻게" 호출할지 자동으로 지휘하는 관제탑을 만드는 일이다.**

오케스트라에 비유하면: 우리는 이미 **연주자(개별 수집 스크립트 58개, 그중 44개가 즉시 연주 가능)**를 갖췄다. 하지만 아직 **지휘자**가 없다. 지금은 사람이 손으로 "이 소스 한 번 수집해봐"라고 시켜야 한다. 오케스트레이션은 그 지휘자를 코드로 만드는 작업이다. 지휘자는 다음을 책임진다.

1. **박자(주기)**: 시세는 5분마다, 뉴스는 30분마다, 박스오피스는 하루 한 번.
2. **악기 선택(전략 라우팅)**: 어떤 소스는 API로, 어떤 소스는 브라우저로, 어떤 소스는 RSS로 수집.
3. **실수 수습(실패/재시도)**: 한 소스가 "너무 자주 불렀다(429)"고 거절하면, 무리하게 다시 부르지 않고 쿨다운 후 재시도하거나 대체 소스로 넘어간다.
4. **격리(quarantine)**: 로그인/캡차로 막힌 소스는 자동으로 빼고, 나머지는 계속 돌린다.
5. **결과 전달(event queue)**: 수집한 것을 "사건 후보 대기열"에 쌓아서, 그다음 단계(AI 분석 → 사건 카드 → 화면)로 흘려보낸다.

이 폴더의 13개 문서는 이 지휘자를 **어떻게 만들지**를 단계별로 적은 설계도다.

---

## 1. 현재 프로젝트 상태 요약 (Current Project Context Snapshot)

> 이 절은 PHASE 1 분석(코드 deep-dive + system_overview 13개 흡수 + 설정 분석)의 결론이다. 상세 근거는 `01_CODEBASE_AND_SYSTEM_OVERVIEW_AUDIT.md`.

### 1.1 가장 중요한 발견 — 저장소에는 "두 개의 시스템"이 공존하며, 아직 연결되지 않았다

레포 루트에는 서로 다른 두 하위 시스템이 **모두 실재**한다.

| 시스템 | 위치 | 정체 | 상태 |
|---|---|---|---|
| **A. 수집 엔진** | `ingestion/` | 58개 소스(44 CORE_READY)를 다전략으로 수집하는 강력한 엔진. health gate, rate-limit, fallback chain, artifact 저장 완비 | 수집 자체는 **실측 검증 완료**. 단 `ingestion/pipeline/`의 다운스트림 연결부는 **전부 stub(NotImplementedError)** |
| **B. 다운스트림 스켈레톤** | `backend/` `workers/` `agents/` `frontend/` | RSS 원문 → raw_events(PostgreSQL) → Redis Stream → LangGraph 11노드 → event_cards → Milvus/OpenSearch → Next.js 화면. STEP 003~011로 구축, 컨테이너 10개 healthcheck PASS, 회귀 테스트 108건 통과 | **동작하지만 입력이 빈약**. 수집 소스가 `workers/collectors/rss_collector.py`의 **RSS 3개(BBC/Reuters/YNA)뿐**. LangGraph 11노드 중 6개는 mock |

**핵심 문제**: 시스템 A(44개 소스를 수집하는 강력한 엔진)의 출력이 시스템 B(분석·서빙 파이프라인)의 입력으로 **흐르지 않는다**. 시스템 B는 여전히 RSS 3개만 먹고 있다.

**따라서 이번 오케스트레이션의 본질은 "새 기능 추가"가 아니라 "이미 만든 두 자산을 연결하는 다리(bridge)를 놓는 것"이다.** 이 다리가 `ingestion/pipeline/event_queue.py`의 `EventQueue`이며, 이미 JSONL 모드로는 동작한다(Redis Stream 모드만 stub).

### 1.2 시스템 A(수집 엔진) 핵심 구조

- **최상위 진입점**: `ingestion/fetch_strategies/collection_probe.py:run_collection_probe(source_id, query=None, max_items=5, force=False) -> CollectionProbeResult`
- **3-way 라우팅**:
  - Route 1 (API): `_PROBE_SPEC` 등록 소스 → `run_api_live_probe`
  - Route 2 (Playwright): `playwright_required` 소스 → `CloudBrowserLikeStrategy().fetch()` 또는 `run_playwright_probe`
  - Route 3 (전략 루프): 그 외 → `run_fetch_strategy_loop` (STRATEGY_SEQUENCE 10단계: httpx_direct → … → playwright_click_more)
- **health gate**: 호출 전에 BLOCKED_TERMINAL/쿨다운/격리 소스를 **네트워크 호출 없이** 조기 차단 (`force=True`로 우회).
- **상태 저장소(backend 교체 가능)**:
  - `ingestion/core/rate_limit_store.py:get_store()` — memory / local_file / redis 3종
  - `ingestion/core/source_health.py:get_health_store()` — `.list_due_for_retry()` 제공
- **실패 분류**: `core/error_taxonomy.py`의 `ErrorType` ~40종. 차단형(CAPTCHA/LOGIN_WALL/PAYWALL/ROBOTS)은 즉시 terminal.
- **body 추출 cascade**: site_selector → trafilatura → readability → dom_heuristic.

### 1.3 시스템 B(다운스트림) 핵심 구조

- **데이터 흐름(13단계)**: RSS 수집 → raw_events 저장 → `stream:raw_events`(Redis) → worker 정규화 → `stream:to_agent` → agent-worker → LangGraph 11노드 → FinalEventCard → `/api/admin/upsert-event` → event_cards 저장 → Milvus/OpenSearch 색인 → FastAPI → Next.js.
- **LangGraph 11노드** (`agents/graphs/event_processing_graph.py`): REAL 5개(source_parse, normalize_event, retrieve_past_context, publish_or_hold + partial deduplicate), MOCK 6개(entity_linking, theme_sector_mapping, impact_analysis, evidence_check, fact_check, final_card_writer).
- **인프라**: `docker-compose.dev.yml`에 redis / postgres / milvus / opensearch / backend / worker / agent-worker / frontend **이미 정의됨**. 신규 컨테이너 불필요.
- **mock↔real 전환**: `LLM_PROVIDER=openai`, `EMBEDDING_PROVIDER=openai` 환경변수만으로 전환.

> ⚠️ **주의(USER_CONFIRMATION 후보)**: `ingestion/agents/graph.py`(소스별 크롤링 LangGraph)와 `agents/graphs/event_processing_graph.py`(사건 처리 LangGraph)는 **이름만 비슷한 서로 다른 그래프**다. 혼동 금지. 전자는 "한 소스에서 본문을 잘 뽑는" 그래프, 후자는 "수집된 사건을 카드로 만드는" 그래프다.

### 1.4 설치/버전 현실 (리서치와 레포의 차이 — 반드시 인지)

`requirements.txt`에 다음이 **이미 핀 고정 설치**되어 있다.

```
langgraph==0.2.76          langchain==0.2.11        langchain-core==0.2.43
langgraph-checkpoint==2.1.1 langchain-openai==0.1.7  celery==5.5.3
redis==5.0.0               fastapi==0.115.14        pymilvus==2.4.4
openai==1.108.1            langsmith==0.1.147       playwright==1.48.0
```

- **중요**: 설치된 langgraph는 **0.2.76**이다. 공식 문서 리서치(06 문서)가 설명한 `langchain.agents.create_agent`, `docs.langchain.com/oss` 정본은 **langgraph/langchain v1.0대(2025~2026 후반) API**다. **즉 v1 API는 "현재 코드"가 아니라 "업그레이드 경로"다.** 현 레포는 `langgraph.graph.StateGraph` + (필요 시) `langgraph.prebuilt` 시대다. 06 문서는 이 차이를 명시한다.
- `celery`, `redis` 라이브러리는 설치돼 있으나 **broker/worker 프로세스는 미가동**이고 Redis 컨테이너 연결은 미검증.
- `langgraph-checkpoint-sqlite` / `langgraph-checkpoint-postgres`는 **미설치**(checkpointer 영속이 필요하면 추가 설치 대상).

### 1.5 git/검증 기준선

- 현재 `git status` clean, `git diff --check` PASS.
- pytest 기준선: ingestion 509 passed + 스켈레톤 회귀 108 (별도 트리).
- runner orchestration readiness: 13/13 agent_ready.

---

## 2. 오케스트레이션 최종 목표

> 한 문장: **CORE_READY+CAUTION 44개 소스를 주기/이벤트 기반으로 자동 수집하고, 그 결과를 event queue를 통해 다운스트림 사건 처리 파이프라인으로 안정적으로 흘려보내되, 모든 실패·rate-limit·격리·품질·법무 리스크를 닫은 상태로 동작하게 한다.**

성공의 모습(검증 가능한 형태):

1. 사람이 손대지 않아도 소스별 주기에 맞춰 수집이 돈다(Celery beat 또는 deterministic local cycle).
2. 한 소스의 실패가 다른 소스를 막지 않는다(소스당 격리).
3. 429/차단/쿨다운이 정책대로 처리되고, 우회는 0건이다.
4. 수집 결과가 event queue에 쌓이고, 다운스트림이 그것을 소비해 사건 카드로 만든다.
5. 품질 게이트(본문 길이, 중복, 신뢰도)를 통과한 항목만 다음 단계로 간다.
6. 비용(외부 API·LLM 호출)이 예측 가능한 상한 안에서 움직인다.

---

## 3. 이번 오케스트레이션의 범위 / 하지 않는 것

### 3.1 범위 (IN SCOPE — 다음 구현 턴들이 다룰 것)

- Celery app + `collect_source(source_id)` task (= `run_collection_probe` 래퍼)
- rate_limit 캐시 Redis 백엔드 전환(워커 간 공유)
- RATE_LIMITED → 재시도 큐(sorted set), BLOCKED → 자동 격리
- daily quota guard(소스별 일일 한도 카운터)
- `EventQueue` Redis Stream 연결(현재 JSONL만 동작)
- ingestion → 다운스트림 raw_events 브리지(수집 결과를 사건 처리 파이프라인 입력으로)
- 전략 라우터/본문 추출 resilience의 명세화(코드 구조 확정)
- 품질 게이트 정의

### 3.2 하지 않는 것 (OUT OF SCOPE — 이번 설계 문서 세트에서 다루지 않거나 별도 라운드)

- **이번 턴에 코드 적용 안 함**(설계만).
- LLM 사건 추론(entity/impact/fact-check 등 mock 6노드의 실모델화) — 별도 라운드(스켈레톤 STEP 014).
- normalization/canonical event 클러스터링 — 별도 라운드.
- KRX 공식 API 연동 — 사용자 키 발급 후.
- Kubernetes/프로덕션 배포 토폴로지, TLS/CDN.
- MCP/Plugin 재도입 — `06` 문서의 "future architecture review"로만 분리.
- 인증/RBAC/OAuth — 스켈레톤 STEP 015.

---

## 4. 설치해야 하는 사항 (Install Checklist)

> 원칙: **이미 설치된 것은 재설치하지 않는다.** 실제 설치 명령은 **사용자 승인 후** 구현 턴에서 실행한다(이번 턴 설치 금지). 모든 설치는 `uv`로 한다(conda 금지).

| 범주 | 패키지/리소스 | 현재 상태 | 비고 |
|---|---|---|---|
| **이미 설치됨 (재설치 불필요)** | langgraph 0.2.76, langchain 0.2.11, celery 5.5.3, redis 5.0.0, fastapi, pymilvus 2.4.4, playwright 1.48.0, pydantic 2.11.7 | requirements.txt 핀 고정 | 버전 업그레이드는 별도 결정(§5 D-2) |
| **Required now (Phase A — deterministic cycle)** | (없음 — 신규 설치 0) | 기존 자산만으로 가능 | Phase A는 `run_collection_probe` 반복 호출 + JSONL queue로 구현 |
| **Required if Celery phase 시작 (Phase G)** | Redis **서버 컨테이너 가동** | compose에 정의됨, 미가동 | `docker compose up redis` (사용자 환경 확인 필요) |
| **Required if Playwright 소스 주기 수집** | worker 이미지에 `playwright install chromium` | 로컬엔 설치됨, **worker 컨테이너엔 미확인** | plans/012 §1 전제조건 |
| **Required if checkpointer 영속 (선택)** | `langgraph-checkpoint-sqlite` 또는 `-postgres` | 미설치 | LangGraph 크래시 복구가 필요할 때만 |
| **Required if Postgres 브리지 (Phase H)** | Postgres **컨테이너 가동** + psycopg | compose 정의됨 | raw_events 직접 기록 경로 선택 시 |
| **Deferred** | deepagents, langchain-mcp-adapters | 미설치 | 06 문서 결론상 **미도입** |

> **USER_CONFIRMATION_REQUIRED**: 위 "컨테이너 가동"(Redis/Postgres)은 사용자의 Windows + Docker Desktop 환경에서 실제로 띄울 수 있는지 확인이 필요하다(§6 확인 항목).

---

## 5. 사용자가 최종 결정해야 하는 사항 (Decisions)

> 각 항목에 **기본 권장값**을 제시한다. 사용자가 답하지 않아도 구현 턴은 이 기본값으로 안전하게 진행할 수 있다.

| ID | 결정 사항 | 선택지 | 기본 권장값 | 차단? |
|---|---|---|---|---|
| **D-1** | 초기 저장소 | SQLite first / Postgres first | **다운스트림은 이미 Postgres 스켈레톤 보유 → Postgres 재사용**. 단 ingestion 자체 상태(rate-limit/health)는 **local_file→redis** 경로 사용 | No |
| **D-2** | 오케스트레이션 1차 구현 형태 | deterministic local cycle first / Celery+Redis first / LangGraph first | **deterministic local cycle first** (Phase A). Celery는 Phase G, LangGraph 신규 그래프는 보류 | No |
| **D-3** | langgraph/langchain 버전 | 0.2.76 유지 / v1.0 업그레이드 | **0.2.76 유지** (스켈레톤 11노드가 이 버전에 의존, 업그레이드는 회귀 위험). v1은 별도 평가 | No |
| **D-4** | Deep Agents 런타임 도입 | 도입 / 미도입 | **미도입** (06 결론: 배치 수집엔 과함) | No |
| **D-5** | event queue 최소 스키마 | 최소(3필드) / 확장 | **최소: `title_or_keyword, source_url, timestamp` + `source_id, _status`** (05 문서 §event_candidates) | No |
| **D-6** | 브리지 방식 | EventQueue→raw_events 직접 / 별도 어댑터 | **별도 어댑터 task**(`bridge_to_raw_events`) — 두 시스템 결합도 최소화 | **REVIEW** |
| **D-7** | source live call 기본 빈도 | §4 bucket 그대로 / 사용자 조정 | **`04 INGESTION_FINAL §4` bucket 그대로** | No |
| **D-8** | LLM judge 사용 범위 | 수집 단계부터 / 다운스트림에서만 | **다운스트림에서만**(수집은 deterministic 유지, 비용·비결정성 회피) | No |
| **D-9** | community 소스 MVP 포함 | 포함 / 제외 | **hacker_news/youtube/product_hunt 포함, dcinside는 CAUTION 모니터링** | No |
| **D-10** | 외부 API 비용 상한 | 무제한 / 일일 상한 | **일일 상한 설정**(quota guard, 04 §enrichment budget 준수) | No |
| **D-11** | 운영 dashboard 우선순위 | 1차 포함 / 후순위 | **후순위**(MVP는 JSONL/로그 기반, dashboard는 frontend STEP에서) | No |

---

## 6. 사용자가 확인해야 하는 사항 (Verification Checklist)

| ID | 확인 항목 | 확인 방법 | 현재 추정 |
|---|---|---|---|
| **V-1** | API 키 readiness | `.env`에 OPENAI_API_KEY 등 존재(값은 비공개) | 일부 존재, alias 경고 6건(04 §15) — UNKNOWN |
| **V-2** | Redis 컨테이너 가동 가능 | `docker compose up redis` 후 `redis-cli ping` | UNKNOWN (사용자 확인 필요) |
| **V-3** | Postgres 컨테이너 가동 가능 | `docker compose up postgres` 후 `pg_isready` | UNKNOWN |
| **V-4** | Windows 로컬 worker 실행 | Celery worker가 Windows에서 prefork 제약 — `--pool=solo` 필요할 수 있음 | **주의 필요**(Celery on Windows 알려진 제약) |
| **V-5** | `.env` canonical 키 상태 | `python -m ingestion.tools.check_env_hygiene` | AMBIGUOUS_ALIAS 6건(기능 무영향) |
| **V-6** | hook이 정상 workflow 방해 안 함 | `.claude/settings.json` hook이 git/secret 차단만 하는지 | local-only 결정, 정상 |
| **V-7** | source live call 허용 시간/빈도 | 사용자가 야간/업무시간 호출 허용 범위 결정 | UNKNOWN |
| **V-8** | full-text 저장 허용 범위 | publication_policy.yaml 준수, 재배포 금지 소스 식별 | 04 §11 / 09 문서 |
| **V-9** | 루트 `gcp-service-account-key.json` | 이 파일이 `.gitignore`에 있는지 확인 필요 — **secret 파일이 레포 루트에 존재** | ⚠️ **SECURITY REVIEW** (12 문서 risk) |

---

## 7. 단계별 구현 로드맵 (다음 턴 순서)

> 상세는 `11_IMPLEMENTATION_DIFF_BLUEPRINT.md`. 각 Phase는 atomic, 단계별 pytest 회귀 0 + secret scan PASS가 완료 조건.

```
Phase A. Deterministic local orchestration cycle
   → run_orchestration_cycle.py: 소스 목록을 주기 bucket에 따라 run_collection_probe 반복 호출,
     결과를 EventQueue(JSONL)에 enqueue. Celery 없이 단일 프로세스. (신규 설치 0)
   검증: gdelt+yna 1 cycle → event_queue.jsonl에 항목 기록

Phase B. Storage persistence
   → rate_limit/health store를 local_file로 고정, event_candidates 스키마 확정(05)
   검증: 프로세스 재시작 후 cooldown 유지(roundtrip)

Phase C. Strategy router (03)
   → SourceProfile + PurposeRouter + StrategyRouter 명세를 코드로
   검증: 소스별 preferred_strategy 라우팅 단위 테스트

Phase D. Body extraction resilience (04)
   → cascade + fallback 확장, 실패 taxonomy 매핑
   검증: 본문 추출 실패율 측정, fallback 동작 테스트

Phase E. Quality gates (09)
   → body_length/duplicate/freshness/credibility 게이트
   검증: 게이트 통과/탈락 단위 테스트

Phase F. LangGraph optional integration (06 결론에 따라)
   → 필요 시 수집 cycle을 StateGraph로(과하면 보류)
   검증: 기존 deterministic cycle과 동등 결과

Phase G. Celery/Redis optional layer (plans/012 §1~8)
   → collect_source task + beat + 재시도 큐 + 격리 + quota guard + EventQueue Redis Stream
   검증: 워커 2개 중복 호출 차단, 재시도 큐 만기 재발행

Phase H. UI/API handoff preparation
   → event queue → raw_events 브리지 → 기존 다운스트림 파이프라인
   검증: 수집 1건이 event_cards까지 도달(e2e)
```

핵심 통찰: **Phase A~E는 신규 인프라 없이(설치 0) 가능**하다. Celery/Redis(Phase G)는 그 위에 얹는 선택지이지 전제가 아니다. 이것이 plans/012 §4의 "strategy loop 내부 sleep은 단일 프로세스 모드 폴백으로 유지" 설계 의도와 정합한다.

---

## 8. 팀 에이전트 평가 요약 (Agent Committee Review)

> 14개 팀 에이전트 관점에서 본 설계 세트 전체를 평가한 요약. 각 문서 하단에 해당 슬라이스가 반복된다. 상세 risk는 `12_RISK_CLOSURE_AND_VALIDATION_PLAN.md`.

| agent | 핵심 피드백 | status |
|---|---|---|
| orchestrator-architect | 두 시스템 bridge 모델이 정확. Celery는 Phase G로 미뤄 deterministic부터 시작이 옳음 | CLOSED_BY_DESIGN |
| source-ingestion-engineer | `run_collection_probe` 인터페이스 안정적 — task 래핑에 코드 수정 불필요 | CLOSED_BY_DESIGN |
| data-quality-auditor | 품질 게이트(09)가 본문 길이/중복/numeric 면제 규칙을 흡수해야 함 | CLOSED_BY_TEST_PLAN |
| test-validation-agent | 각 Phase atomic + 회귀 0 기준 명확. Windows Celery pool 제약은 검증 필요 | CLOSED_BY_TEST_PLAN |
| adversarial-reality-critic | "두 시스템이 연결 안 됨"을 숨기지 않고 1.1에 명시한 점 양호. 브리지(D-6)가 최대 미지수 | USER_CONFIRMATION_REQUIRED |
| commercialization-strategist | event queue가 제품 가치의 핵심 — 10 문서에서 구체화 | CLOSED_BY_DESIGN |
| legal-safety-compliance-reviewer | 우회 금지/재배포 금지 정책 유지. gcp 키 파일(V-9) 점검 권고 | USER_CONFIRMATION_REQUIRED |
| product-ux-strategist | dashboard 후순위 타당. event card 신뢰 지표는 10 문서 | CLOSED_BY_DESIGN |
| docs-memory-curator | DOCS_FINAL.md pointer 추가 최소화 권고 | CLOSED_BY_DESIGN |
| security-permission-guardian | secret scan gate 유지, Redis 비밀번호/네트워크 노출 검토 | CLOSED_BY_TEST_PLAN |
| business-intelligence-analyst | 소스 다양성(44)이 경쟁 우위 — 연결만 하면 즉시 가치 | CLOSED_BY_DESIGN |
| evaluation-benchmark-agent | event_relevance/freshness 지표를 게이트에 연결 | CLOSED_BY_TEST_PLAN |
| operations-sre-agent | 재시도 큐/격리/quota가 운영 안정성 핵심. Windows pool, time.sleep 차단 주의 | CLOSED_BY_DESIGN |
| frontend-integration-agent | event queue → API contract는 07/스켈레톤 재사용 | CLOSED_BY_DESIGN |

---

## 9. Risk Closure (개요 수준 — 상세는 12 문서)

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| 두 시스템 미연결 지속 | bridge 미구현 | 44 소스 가치 미실현 | event_cards에 RSS 외 소스 부재 | Phase H 브리지 task | e2e 1건 도달 | CLOSED_BY_DESIGN |
| Celery Windows 제약 | prefork pool 미지원 | 로컬 worker 미가동 | worker 起動 실패 | `--pool=solo` 또는 deterministic cycle 우선 | V-4 확인 | USER_CONFIRMATION_REQUIRED |
| 과도한 기술 도입 | LangGraph/Celery 조기 도입 | 복잡도·비용 폭발 | 구현 지연 | Phase 분리(A 우선, 설치 0) | Phase A 단독 동작 | CLOSED_BY_DESIGN |
| gcp 키 노출 | 루트 secret 파일 | 자격증명 유출 | scan_secrets/gitignore 확인 | .gitignore 점검(사람) | V-9 | USER_CONFIRMATION_REQUIRED |

---

## 10. Commercialization Impact

- **즉시 가치**: 시스템 A의 44개 소스를 시스템 B에 연결하는 순간, 사용자 화면의 사건 카드 소스가 "RSS 3개"에서 "뉴스·공시·커뮤니티·트렌드·시세 44개"로 확장된다. **이것이 제품의 1차 차별화**다(경쟁사 대비 소스 다양성).
- **비용 구조**: 수집 자체는 대부분 무료/저비용 API. 비용은 (a) LLM 추론(다운스트림), (b) 일부 유료 검색 API(serper/tavily/nyt)에 집중 → quota guard로 상한.
- **B2B 산출물**: event queue + evidence link는 "실시간 사건 피드 API"로 판매 가능(10 문서).
- **MVP 절제**: dashboard, hybrid search, KG-RAG는 후순위. 1차는 "다양한 소스 → 신뢰 가능한 사건 카드"에 집중.

---

## 11. USER_CONFIRMATION_REQUIRED (이 문서 종합)

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| 다운스트림 저장소로 기존 Postgres 스켈레톤을 재사용할까? | 새 DB 구축 중복 회피 | 재사용(D-1) | No |
| 1차를 deterministic cycle로 시작할까(Celery 보류)? | Windows Celery 제약·복잡도 회피 | 예, Phase A 우선(D-2) | No |
| langgraph 0.2.76을 유지할까? | v1 업그레이드는 스켈레톤 회귀 위험 | 유지(D-3) | No |
| ingestion→raw_events 브리지를 별도 어댑터로 둘까? | 두 시스템 결합도 최소화 | 별도 어댑터(D-6) | **REVIEW** |
| Redis/Postgres 컨테이너를 띄울 수 있는가? | Phase G/H 전제 | 사용자 환경 확인(V-2/V-3) | Phase G에서만 |
| 루트 `gcp-service-account-key.json`이 gitignore에 있는가? | 자격증명 유출 방지 | 즉시 확인 권고(V-9) | Yes(보안) |

---

## 12. 다음 구현 순서(요약)

1. `01`~`12` 문서 정독 → 2. Phase A(deterministic cycle) 구현 → 3. Phase B~E(persistence/router/body/quality) → 4. Phase G(Celery, 사용자 환경 확인 후) → 5. Phase H(브리지 e2e).

> 이 문서 세트는 **설계**다. 구현은 다음 턴에서, 각 Phase atomic + 검증 통과를 조건으로 진행한다.

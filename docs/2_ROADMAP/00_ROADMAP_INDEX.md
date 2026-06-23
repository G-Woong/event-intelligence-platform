# 00 — ROADMAP 인덱스 & 의존성 위상정렬 지도

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────────────────────────
> │ **상태:** 🧭 META — 인덱스. 각 ROADMAP 파일의 상태는 **그 파일 헤더 스탬프가 권위**.
> │ **구현 사실의 단일 출처:** `docs/_CANONICAL/*` (이 폴더는 *미래 계획*이지 현재 사실이 아니다).
> │ **생성:** 2026-06-20 · 흡수 출처: `WEB_INTELLIGENCE_{MASTER_OVERVIEW,SESSION_CONCEPT_ANALYSIS,IMPLEMENTATION_SPEC,DIRECTION_UPDATE}.md` (4파일)
> └────────────────────────────────────────────────────────────────────────────

이 문서는 `docs/2_ROADMAP/`의 **모든 ROADMAP 파일을 "구현완료 → 미구현" 순으로 정렬**하고, 각 파일의 정직한 상태 스탬프·의존성 위상정렬·흡수 출처를 한 곳에 모은 진입 지도다. 사용자는 이 인덱스를 보고 **어디서·어떤 개념부터 상용화 구현을 시작할지** 판단한다(§4 임계경로 참조).

---

## 1. 상태 스탬프 규약 (모든 ROADMAP 파일 최상위에 부착)

각 번호 md 파일 최상위에는 아래 블록이 부착된다. **정직 원칙**: 구현 사실(`_CANONICAL`)에 어긋나는 허위 "완료"는 금지한다(`CLAUDE.md`·DIRECTION §5 "미구현을 구현된 것처럼 적지 않는다").

```
> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** <아이콘 STATUS> — <한 줄 요약>
> │ **구현순위:** #N (00_ROADMAP_INDEX) · **그룹:** A/B/C/D
> │ **검증 근거:** <_CANONICAL/코드 file:line 근거 — DONE/PARTIAL 주장 시 필수>
> │ **잔여(미구현):** <무엇이 남았나 — risk와 함께>
> │ **완료정의(DoD):** <무엇이 충족되면 ✅ "risk 없이 완벽 구현완료"인가>
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────
```

### 상태 아이콘 범례

| 아이콘 | 의미 | 판정 기준 |
|---|---|---|
| ✅ **DONE** | 구현완료·검증됨·**risk 없음** | 코드 산출물 + 테스트 잠금 + 라이브 입증 + 열린 risk 0. **현재 이 스탬프를 받은 ROADMAP 파일은 없다**(토대조차 잔여 gap 보유 → 아래 PARTIAL). |
| 🟡 **PARTIAL** | 토대 일부 실구현 + 잔여 존재 | 실코드/라이브 입증된 토대가 있으나 DoD 미충족(잔여 gap·열린 risk). |
| 🔲 **NOT_DONE** | 미구현 (스텁/설계 청사진만) | grep 0건 또는 `NotImplementedError` 스텁. NET-NEW 포함. |
| 📘 **REFERENCE** | 설계·결정·개념 문서 (코드 산출물 아님) | 목표 아키텍처·판단·포지셔닝·법무분석 등. "구현" 개념 비적용. 인용 게이트 등 일부 실구현은 본문에 명시. |
| 🧭 **META / 📖 ONBOARDING** | 인덱스 / 비개발자 서사 레이어 | 사실 아님. 권위는 `_CANONICAL`·`_DECISIONS`. |

> **"risk 없이 완벽 구현완료"는 DoD가 충족될 때 부여한다.** 각 파일의 DoD 라인이 그 조건을 명문화한다. 현 시점 정직한 진실: **토대(57소스 수집·A→B bridge·Redis/DLQ·11노드 LangGraph baseline·3엔진 색인·1,517 테스트)는 라이브 입증됐으나, 어떤 ROADMAP 레이어도 "잔여 0·risk 0"에 도달하지 않았다.** 이 인덱스는 그 거리를 정직하게 보여준다.

---

## 2. 정렬: 구현완료(✅/🟡) → 미구현(🔲) (의존성·착수준비도순)

> 그룹 헤더로 정직하게 구분. 파일명 번호는 **레이어 아키텍처 의미**라 불변(재번호 안 함, 상호참조 비파괴). 정렬은 이 "구현순위"로만 표현한다.

### 그룹 A — 🟡 구현된 토대를 서술/감사하는 PARTIAL 문서 (코드 산출물 존재)

| 순위 | 파일 | 상태 | 한 줄 |
|---|---|---|---|
| 1 | **05_DISCOVERY_AND_SOURCE_EXPANSION** | 🟡 PARTIAL | registry 57·SourceCapability·정책게이트 인프라 실구현. P0 기본 sink mirror·Entity/Authority 발견엔진 미완 |
| 2 | **11_LLM_SOURCE_SUPERVISOR_AND_JUDGE** | 🟡 PARTIAL | `decide()`·allowlist·`_UNSAFE`·judge 추상화 실구현. `llm_propose` 실 provider 미배선(테스트 람다뿐) |
| 3 | **07_REDIS_QUEUE_CACHE_STREAM** | 🟡 PARTIAL | B Redis Stream·DLQ(`route_failure`/`reap_pending`) 실구현·배선·라이브. A→B EventQueue 배선·Celery·quota 미완 |
| 4 | **15_IMPLEMENTATION_ROADMAP** | 🟡 PARTIAL | Phase0 DONE / Phase1–3 PARTIAL / Phase4–10 NOT_DONE |
| 5 | **18_FINAL_EXECUTIVE_SUMMARY** | 📘 REFERENCE | 섹션 B P0배선 PARTIAL은 실사실 + 미래전략(수익화 단락 구독→광고 전면개정 대상) |

### 그룹 B — 📘 설계·결정·개념 REFERENCE (코드 0; 토대는 살아있음)

| 순위 | 파일 | 상태 | 한 줄 |
|---|---|---|---|
| 6 | **04_TARGET_ARCHITECTURE_LAYERS** | 📘 REFERENCE | L0~L14 목표 청사진(진입 지도) |
| 7 | **10_AGENT_ORCHESTRATION_LAYER** | 📘 REFERENCE | LangGraph/Deep Agents 프레임워크 결정서(현재상태 정합) |
| 8 | **16_LANGCHAIN_LANGGRAPH_DEEPAGENTS_RESEARCH** | 📘 REFERENCE | 도입판단 리서치(0.2.76/DeepAgents 0건 사실검증 정확) |
| 9 | **02_SEARCH_ENGINE_VS_EVENT_INTELLIGENCE_CONCEPT** | 📘 REFERENCE | 최상위 포지셔닝 선언(검색엔진 ≠ event intelligence) |
| 10 | **14_SECURITY_LEGAL_SAFETY_AND_NO_BYPASS** | 📘 REFERENCE | 정책/법무/안전 분석(EvidenceGate·`_UNSAFE`·SSRF·secret scan 인용 게이트는 실구현) |

### 그룹 C — 🔲 미구현 ROADMAP (착수준비도순; 의존 토대 일부 보유)

| 순위 | 파일 | 상태 | 한 줄 |
|---|---|---|---|
| 11 | **06_SEARCH_API_AND_WEB_EXPLORATION** | 🔲 NOT_DONE | `query_generator`/`search_enrichment_collector` = `NotImplementedError`, `expansion_router` 부재. S5 저렴·조기 착수 |
| 12 | **12_EVENT_CLUSTERING_RANKING_AND_DEDUP** | 🟡 PARTIAL | dedup+clique(S2b)+resolver(S2c)+CRUD 영속(S2d)+통합 파이프라인(S2e) 구현; live-PG E2E·heat/rank(S2.5~) 미구현. **임계경로(Event 라우팅)** |
| 13 | **08_RAG_VECTOR_DB_LAYER** | 📘 REFERENCE | 3엔진 색인·Milvus top-k 토대 살아있음; hybrid/RRF/rerank/nori 0% |
| 14 | **13_COMMERCIALIZATION_AND_PRODUCT_STRATEGY** | 📘 REFERENCE | 코드 0. 구독 전제 = 레거시 → 트래픽×광고×커뮤니티로 전면개정(ADR#15) |
| 15 | **09_KG_RAG_GRAPH_RAG_LAYER** | 📘 REFERENCE | **의도적 영구보류**(<1000 엔티티 도입 금지). risk 0 |

### 그룹 D — 🔲 신규 NET-NEW (전부 코드 부재, GroundTruth로 미존재 확정)

| 순위 | 파일 | 상태 | 한 줄 |
|---|---|---|---|
| 16 | **17_AUTHORITY_DISCOVERY_AND_SLM_BODY_FALLBACK** | 🔲 NOT_DONE (NET-NEW) | Entity Registry·Authority Source Graph·Sitemap·Change Detection·SLM Body Fallback |
| 17 | **19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC** | 🟡 PARTIAL (S1+S2 a~e) | **S1 토대 + S2 Event Resolution 전 단계 구현됨**(0004/0005; clique·event_resolver·event_timeline_service CRUD·event_resolution_pipeline 통합 + ADR#19/#20, 2026-06-22). live-PG E2E·Expansion·Evidence Graph·Agent Debate(S5~S11) 미구현 |

---

## 3. 4대 방향문서 → docs 흡수 매핑 (요약)

세션에서 작성된 4개 루트 문서의 고유 atom은 아래로 흡수됐다(상세 atom-단위 매핑은 흡수 매니페스트, §6 삭제판정 참조).

| 출처 문서 | 핵심 흡수처 |
|---|---|
| **DIRECTION_UPDATE** (방향 결정) | `_DECISIONS/2026-06.md` ADR#14/#15/#16(모순 M1~M6 해소·기각대안) + 본 인덱스 §4 + 13(광고)·11(P/G/F)·12(Event) |
| **SESSION_CONCEPT_ANALYSIS** (개념 원자분해) | `19`(5대 자산 스펙) + `17`(Authority/Entity/Change) + `_CANONICAL/07_ENHANCEMENT_BACKLOG` + 본 인덱스 |
| **IMPLEMENTATION_SPEC** (구현 상세) | `19`(통째 흡수: 스키마·의사코드·alembic·테스트) + `5_REFERENCE/EVENT_SCHEMA.md`(DDL) |
| **MASTER_OVERVIEW** (비개발자 개관) | `0_ONBOARDING/00_MASTER_OVERVIEW.md`(서사 4종) + `_CANONICAL/01·02`(현재 사실은 이미 보유) + 13(상용화) |

> **삭제 가능 여부:** 위 흡수가 100% 완료되면 4파일은 **조건부 삭제 가능**(CONDITIONAL DELETE). 단 ① 신규 4파일(`00_INDEX`/`17`/`19`/`0_ONBOARDING/00`) 생성 완료, ② `CLAUDE.md §4` 파괴적 명령 규율상 **사용자 명시 요청 시에만** 삭제(AI 임의 삭제 금지), ③ 안전 대안 = `_ARCHIVE_SUPERSEDED/`로 이동 후 1턴 관찰. 상세 = 본 세션 보고.

---

## 4. 의존성 위상정렬 — **착수 임계경로 (어디서부터 시작하는가)**

> 두 줄기[① Event Resolution(D)→Evidence Graph(I), ② Entity Registry(K)→Authority Graph(L)→Change Detection(N)]가 **Event 객체에서 합류**한다. **Event 토대(S1)를 먼저 고정하지 않으면 "걸음1(카드 AI 품질)"이 폐기될 1회성 카드 스키마 위에 쌓인다**(DIRECTION §0).

```
S1  Event/Update 타임라인 토대 ───────────────────────[최우선·임계경로 합류점]
    (events/event_updates + event_cards.event_id nullable FK — 최소 토대; cluster_event_map/event_links는 S2 이월)
    │   파일: 19(스펙)+EVENT_SCHEMA(DDL)+12(개정). alembic 0004. **토대 ✅ 구현 2026-06-22**(backend ORM/Pydantic+회귀 17, 1451 green); S2=Resolution.
    ├─ S1.5 Change Detection (read-only: ETag/Last-Modified/norm_hash→SKIP verdict)  ◄ 동시 착수 권장
    │       (비용 지렛대를 후속보다 먼저 켜야 S2~S6 폭주 방지 — orchestrator 인사이트 #4)
    ▼
S5  LLM Expansion Router (게이트 존재라 가장 저렴, S1 직후)  ── 파일 06+11+19
    ▼
S2  Event Resolution Engine [✓ S2-core a~c + S2d CRUD + S2e 통합 + ✅ live-PG 검증(0001~0006·2-세션 동시성·FK RESTRICT) + ✅ C live wiring 경로/seam(event_ingest_pipeline + orchestration sink, ADR#22) + ✅ D-1 운영 결선 composition root(backend-side sink 주입, NullPool 엔진 생명주기, ADR#23) 2026-06-22 + ✅ D-2a Event 타임라인 read API(`/api/events/timeline`, flag, held degenerate 제외, ADR#24) 2026-06-23 + ✅ D-2b frontend 렌더(`/events/timeline` 목록/상세 Next.js page+컴포넌트, 안전 evidence, ADR#25) 2026-06-23 + ✅ D-2b 하드닝(테스트 provider mock 격리·공개 read source_refs 제외·에러표현 통일, ADR#26) + ✅ D-2c 데모(합성 Event seed `seed_event_timeline`·DB target 2중 fail-closed 가드·**로컬**(uvicorn+next dev) 브라우저 E2E 실증=북극성 첫 가시화, ADR#27) 2026-06-23 + ✅ REAL_SOURCE_LOOP_AUDIT(ADR#28: 경로 A[수집→raw_events] 실데이터 PROVEN·경로 B[수집→Event 타임라인] **코드 배선 완료이나 실데이터 0회**·D-2c=synthetic 화면 검증≠실 파이프라인 검증→R-RealSourceLoopUnproven MEDIUM) 2026-06-23 + ✅ **실 소스 production-validation(ADR#29: keyless 뉴스 10소스·411 real records→2 클러스터→resolver CREATE 2+HOLD 3→`/api/events/timeline` 2 실 Event→브라우저 렌더[yna 코스피 서킷브레이커·매경 대우건설] → 경로 B 실 웹 데이터 Event 생성·화면 노출 최초 입증, R-RealSourceLoopUnproven MEDIUM→LOW 부분종결)** 2026-06-23; **다음 우선순위: (1) delta_summary deterministic 자연어화(실경로 디버그 라벨)→(2) APPEND 실관측·비-뉴스 타입 Event→(3) full `docker compose up --build` E2E→(4) 주기 auto-trigger→(5) event_cards 자동연결 이월**] + S3 domains/tags 2층  ── 파일 12+19
    ▼
S4  Entity Registry (NER 재사용+앵커 매칭+candidate 자동승격/병합 분리)  ── 파일 17+EVENT_SCHEMA
    ▼
S6  Source Routing 배선 (supervisor llm_propose + 사건유형→role + audit)  ── 파일 11+19
    ▼
S7  Change Detection 발견결합 → S8 Evidence Graph(09 경계 유지) → S9 Agent Debate(13 광고 연결)
    → S10 Authority Discovery → S11 SLM Body Fallback
```

**병행 가능(차단 아님):** DLQ 알림·RBAC·hybrid/nori(08)·L4 기본 sink 전환·46소스 전수 probe(05).
**선행 필수:** **상용화(13)·검색고도화(08)는 Event 토대(S1)+실데이터 이후** — 그 전엔 영업/검색이 모래성.

> **한 줄:** Event 객체부터. 그 위에 Resolution→(Change Detection 동시)→Expansion→domains→Entity→Routing→Evidence→Debate→Authority→SLM. 모든 단계 **비파괴·1517 green·우회 0·투자조언 0·전문저장 0**.

---

## 5. DIRECTION §5 docs 변경 매트릭스 (어디를 무엇으로 바꿨나)

| 문서 | 변경 | 연결 요구 |
|---|---|---|
| `11_LLM_SOURCE_SUPERVISOR…` | "관여 3층 경계(P/G/F)" 신설, audit trace 의무 | 1 |
| `06_SEARCH_API…` | tiered router(무료→유료) + per-event/월 budget guard + fallback chain | 1 |
| `05_DISCOVERY…` | Entity Registry·Authority Discovery 발견 목표(→17 위임) | 1·6 |
| `13_COMMERCIALIZATION…` | **전면 개정** — 구독 4티어 폐기, 트래픽×광고×커뮤니티 | 2 |
| `12_EVENT_CLUSTERING…` | "카드 dedup" → "Event append + timeline + heat" | 3 |
| `04_TARGET_ARCHITECTURE_LAYERS` | L8/L9/L13 새 방향 + Entity/Authority/Event 레이어 위치 | 1·2·3·6 |
| `5_REFERENCE/EVENT_SCHEMA.md` | `Event`·`EventUpdate`·`Entity`·`EvidenceNode` + Comment 확장 | 2·3 |
| `_DECISIONS/2026-06.md` | ADR#14(LLM 수집경계)·#15(구독→광고)·#16(Event 타임라인) | 1·2·3 |
| `_RISK/RISK_REGISTER.md` | 신규 RISK 7건 + 재평가 | 1·2·3 |
| `_CANONICAL/*` | **구현 후에만** 수치 갱신(미구현을 구현됨으로 적지 않음) | — |

---

## 6. UNKNOWN (구현 전 확정 불가 — 정직 표기)

1. SLM Body Fallback의 통신서버 인프라/모델 size·비용 (S11, 미정).
2. 광고 수요측 1차 인벤토리 실판매 형태(self-serve CPL vs 정액) — 콜드스타트 전 미검증(13).
3. Event 병합 해상도 임계 θ(merge_score 가중치) 도메인별 튜닝값(S2).
4. heat 가중치·half-life 실측 캘리브레이션(S2).
5. domains 통제어휘 최종 집합(현 20 제안, 거버넌스 ADR로 확장).
6. GraphRAG 진입 시점(<1000 엔티티 금지 → vector RAG 커버리지 실측 후, 09).

> 권위: 본 인덱스는 ROADMAP 정렬·진입의 단일 지도다. **구현 사실은 항상 `docs/_CANONICAL/*`**, 결정 논리는 `docs/_DECISIONS/2026-06.md`, 위험은 `docs/_RISK/RISK_REGISTER.md`가 권위다.

# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** ① D-1(운영 결선)을 커밋(`af012c3`)으로 안정화하고, ② **Event 타임라인을 웹 API로 처음 노출(D-2a)**했습니다. 그동안 DB·D-1로 "같은 사건을 하나의 타임라인으로 쌓을" 수 있었지만 **웹에서 조회할 API가 없었는데**, 이제 `/api/events/timeline`로 사건 목록과 사건별 업데이트(타임라인)를 읽을 수 있습니다(피처 플래그, 기본 꺼짐).
- **이번 턴에 실제로 끝낸 것:** D-2a — `/api/events/timeline`(사건 목록)·`/api/events/timeline/{id}`(사건+업데이트) **additive read endpoint**(기존 event_cards API 무변경) + 매핑 안 된 저품질 잔재(held degenerate)를 목록·단건 양쪽에서 제외 + read 전용·LLM/네트워크 0. **측정 게이트 backend 241 + ingestion 1331 = 1572 green**(회귀 0). 7-감사단(적대·법무가 지적한 "단건 우회로 held degenerate 노출"을 매핑 게이트(get_public_event)로 차단, "페이지네이션 중복/누락"을 결정적 정렬로 수정).
- **지금 막힌 것:** 없음(BLOCKED 0). 단 **frontend는 아직 Event 타임라인을 렌더하지 않습니다** — 화면은 여전히 기존 카드(event_cards)를 보여줍니다. 즉 "웹 API로 노출하는 능력"은 확보했으나 "사용자 화면에 타임라인 표시"는 D-2b(frontend), "Docker로 쌓이는 모습 데모"는 D-2c 이월. 데이터가 없으면 목록은 빈 배열(D-1 runner 실행/seed 필요). pre-existing embedding 환경 실패 1(아래, 무관).

## 📋 자동 수집 사실 (machine_status.json)
- HEAD `af012c3`(D-1 커밋) 위 **미커밋 D-2a 변경 = code 7(신규 1 + 수정 6) + docs 7**. (machine_status 스냅샷은 이전 턴이라 stale — Stop 훅이 재스캔.)
- 신규: `backend/tests/test_event_timeline_api.py`. 수정: `backend/app/api/events.py`·`event_timeline_service.py`(list_events/get_public_event)·`schemas/events.py`(EventTimelineResponse)·`core/config.py`(EVENT_TIMELINE_API_ENABLED)·`.env.example`·`test_event_resolution_live_pg.py`(+live-PG 3).
- 열린 RISK 28: **신규 R-EventTimelineApiScale**(read API 규모/페이지네이션, LOW·완화) · R-EventSinkDbTarget·R-EventTimelineS2Hardening·R-EventModelMigration·R-FalseMerge·R-ExpansionPartialFailure 유지(미종결).

## ✅ 이번 턴에 달성한 것 (D-1 커밋 + D-2a read API)
- **D-1 커밋(`af012c3`):** code 6 + docs 8, secret PASS·docs_lifecycle green·closeout unresolved 0 확인 후 커밋. working tree clean(push 안 함).
- **docs/2_ROADMAP 재판정 + 코드 실측:** Event 타임라인은 DB·Pydantic 스키마 준비됨·D-1로 영속가능했으나 **API endpoint 0**(기존 `/api/events`는 event_cards 서빙). docker-compose 풀스택(backend+frontend+scheduler, mock 기본)·주기 스케줄러 패턴(`recovery-scheduler`)은 이미 존재 → 갭은 "Event endpoint+렌더+데이터"이지 인프라 아님. **D-1.5 운영 보강(R-EventSinkDbTarget 가드·실 production-validation·test mock)은 Docker 데모(격리 DB·mock·synthetic seed)에서 blocker 아님** → 사용자가 D-2a(read API) 선택.
- **불일치 보고:** ① `/api/events`가 event_cards라 "Event 경유"는 신규 additive endpoint로(기존 수정 시 frontend 깨짐). ② 로드맵 "Celery beat"는 미존재(실 패턴=interval scheduler). ③ docker 풀스택·mock 기본 이미 존재. ④ Event/EventUpdate Pydantic 스키마 이미 존재.
- **D-2a read API(ADR#24):** `EVENT_TIMELINE_API_ENABLED`(config, 기본 false, write용과 분리) + `EventTimelineResponse`(event+updates) + `event_timeline_service.list_events`(매핑된 실 주제만, (last_update,id) desc 결정적 정렬)·`get_public_event`(단건도 매핑 게이트) + `/api/events/timeline`·`/timeline/{id}` endpoint(**`/{event_id}` 보다 먼저 선언**=라우트 우선순위, flag off→404). 기존 event_cards API/frontend **무변경**.
- **공개 노출 안전:** held degenerate(canonical_title=raw member key, cluster_event_map 미매핑)를 **목록·단건 양쪽에서 제외**(get_public_event 매핑 게이트 — event_cards 단건 published 게이트와 대칭, R-MockCard). evidence/source_refs는 write 시 sanitize됨(read 안전). read-only·결정론(LLM/network 0).
- **7-감사단:** architecture **CONDITIONAL**(0 blocking; 라우트 우선순위 SOUND·held 제외 정확·flag 분리 타당) · adversarial **0 blocking**(단건 우회→매핑 게이트로 해소·"웹에서 본다" 과장→"API 노출, UI 미배선" 정정) · evidence/legal **CONDITIONAL→APPROVED**(단건 매핑 게이트 추가로 R-MockCard 대칭 충족; 전문/PII 0·투자조언 0·재배포 아님) · code **3건→보강**(pagination 비결정성→(last_update,id) tie-breaker·dead status param 제거·3쿼리 유지) · pipeline/test/risk_closure 통과.
- **검증:** backend **241**(+9 D-2a: API 6 + live-PG 3) · ingestion **1331**(무변경) = **1572 green**(회귀 0) · live-PG D-2a(매핑 노출·held 제외·단건 게이트) PASS · 1 pre-existing embedding 환경 실패(아래) · 4 skipped.

## ❌ 달성하지 못한 것 & 왜
- **frontend Event 타임라인 미렌더(D-2b 이월):** 이번엔 backend read API endpoint만 — frontend(`frontend/src/app/events/`)는 아직 event_cards(FinalEventCard)를 렌더, timeline endpoint 미소비. "사용자 화면 표시"는 다음.
- **Docker 데모 미실행(D-2c 이월):** 풀스택 compose는 있으나 Event 데이터 흐름(seed/scheduler 결선)+Event 렌더 미결선. "주기적으로 Event가 쌓이는 웹" 가시화는 다음.
- **데이터 없으면 빈 목록:** dev DB에 Event가 없으면 `/timeline`은 []. D-1 runner(`--event-resolution`) 실행 또는 seed 필요(운영 자동 가동=주기 트리거는 Phase 2).
- **주기 auto-trigger·실 production-validation·event_cards 자동연결·heat(S2.5)·LLM 보조:** 이월(deterministic 토대·웹 가시화 우선).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: Event 타임라인 대규모 응답/IN-서브쿼리 plan(R-EventTimelineApiScale, live-PG EXPLAIN 후)·실 수집 데이터 Event 라우팅 정확도·주기 자동 가동 안정성.
- **pre-existing embedding 실패(D-2a 무관):** `test_get_embedding_client_singleton` 1 FAIL — `monkeypatch` 없이 실 `.env`(EMBEDDING_PROVIDER=openai)로 실 provider 인스턴스화(테스트 격리 결함). D-2a read API는 deterministic·network 0. 차기: conftest LLM/EMBEDDING=mock 강제.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-EventTimelineApiScale(신규, LOW):** read API 규모 잔여(단건 updates 무제한 로드·IN-서브쿼리 plan·deep offset). **완화:** (last_update,id) tie-breaker·limit le=100·flag off-by-default. **잔여:** 단건 updates 페이지네이션·IN-서브쿼리 EXPLAIN.
- **R-EventSinkDbTarget·R-EventTimelineS2Hardening·R-EventModelMigration·R-FalseMerge·R-ExpansionPartialFailure:** D-2a가 손대지 않음 → 유지. (event_cards 자동연결·약신호 split·query_generator 별개.)
- 신규 1(R-EventTimelineApiScale) · 완전 종결 0 · GDELT/DcToS/ContentTypeGate 무변경.

## 👉 다음 할 일
1. **[D-2b frontend Event 타임라인]** `frontend` 에서 `/api/events/timeline` 소비 → Event 목록·사건별 업데이트(타임라인) 렌더. 기존 event_cards UI 병행. webapp-testing(Playwright) E2E.
2. **[D-2c Docker 데모]** Event seed 또는 scheduler(interval) 결선 → `docker compose up` → 브라우저로 "Event가 쌓이고 업데이트되는 웹" 확인.
3. **[보강]** 단건 updates 페이지네이션(R-EventTimelineApiScale) · 주기 auto-trigger(Phase 2 interval scheduler) · event_cards↔Event 자동연결 · R-EventSinkDbTarget 구조 가드.
4. (이월) heat 4신호(S2.5) · merge_score(S4) · LLM 보조(S5/S6) · 3엔진 색인 정합.

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/app/api/events.py`(timeline endpoint) · `backend/app/services/event_timeline_service.py`(list_events/get_public_event) · `backend/app/schemas/events.py`(EventTimelineResponse) · `backend/app/core/config.py`(EVENT_TIMELINE_API_ENABLED).
- 테스트: `backend/tests/test_event_timeline_api.py`(6: flag off 404·on 목록(라우트 우선순위)·단건 event+updates·없는 event 404·레거시 무영향) · `test_event_resolution_live_pg.py`(+3 live-PG: 매핑 노출·held degenerate 제외·단건 매핑 게이트).
- 문서: `_DECISIONS/2026-06.md`(ADR#24) · `_RISK/RISK_REGISTER.md`(R-EventTimelineApiScale) · EVENT_SCHEMA·_CANONICAL/02·2_ROADMAP/{00,15,19}.

---
_as_of: 2026-06-23 · D-2a Event 타임라인 read API — `/api/events/timeline`(list[Event], 매핑된 실 주제만)·`/timeline/{id}`(EventTimelineResponse=event+updates) additive endpoint(`EVENT_TIMELINE_API_ENABLED` flag 기본 off→404, `/{event_id}` 앞 선언=라우트 우선순위, held degenerate 목록·단건 양쪽 제외=R-MockCard 대칭, read-only·결정론). 기존 event_cards API/frontend **무변경**. 측정 게이트 backend 241 + ingestion 1331 = **1572 green**(회귀 0). 7-감사단(legal CONDITIONAL: 단건 우회→get_public_event 매핑 게이트로 APPROVED; code: pagination 결정적 정렬·dead param 제거). **잔여: frontend Event 렌더(D-2b)·Docker 데모(D-2c)·주기 auto-trigger·단건 updates 페이지네이션·event_cards↔Event 자동연결.** D-1 커밋 `af012c3`. D-2a 미커밋(커밋 지시 대기). pre-existing embedding 실패 1(무관)_

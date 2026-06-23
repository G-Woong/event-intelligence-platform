# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** ① D-2c(합성 데모)를 커밋(`2f897ee`)하고, ② **"실제 웹 소스가 정말 수집→적재→Event→화면 루프를 도는지"를 코드·산출물로 전수 감사(REAL_SOURCE_LOOP_AUDIT)**했습니다.
- **이번 턴 핵심 발견(정직):** **D-2c 는 synthetic seed 기반의 로컬 첫 실거동 *가시화*이지, 실제 웹 소스별 수집→적재→확장→정제→Event→화면 노출 루프의 *검증*이 아니다.** 감사 결과 — **경로 A**(수집→raw_events; raw_events→event_cards)는 **실 웹 데이터 운반 입증**(live probe·production-validation `_prod_orch.log` 653 extract→**608 raw_events 적재**[37 dup·critical_alert 1]; ap_news 100→event_cards[**전량 hold→사용자 노출 0** — 운반 능력 입증이지 제품 노출 아님]). 그러나 **경로 B**(수집→Event 타임라인)는 **코드 배선만 완료, 실 웹 데이터가 흐른 적 0회**(전 입증이 fake session/하드코딩 가짜 record/`example.com` 합성 seed). → **R-RealSourceLoopUnproven(MEDIUM) 신규 등재.**
- **방향 결정:** **"작은 실 소스 production-validation(경로 B 실데이터)"을 먼저** 한다(제품 핵심 가치=실 웹 인텔리전스가 경로 B에서 0회 입증이라 최고 레버리지). 단 이는 **최소 배포 인프라(운영/dev DB alembic 0006 + `EVENT_RESOLUTION_ENABLED` on)를 동반**하며, full `docker compose up --build` *E2E 검증*만 후순위(실 소스 검증이 compose 전체를 무조건 선행한다는 뜻 아님). **막힌 것 없음(BLOCKED 0).** 실 소스 live 수집은 outward-facing이라 다음 턴 승인 후 진행.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `2f897ee`**(D-2c 커밋, `git rev-parse` 실측; 14파일 +608/−49, push 안 함) 위 **본 턴 docs 미커밋 변경 = docs 7**(코드 0 — 감사·문서 턴). **주의: `machine_status.json`은 `180a866`(직전 턴 Stop 시점)로 stale** — Stop 훅이 턴 끝에 갱신하므로 *인-턴* 커밋(`2f897ee`)을 아직 미반영(불일치 아님, lag).
- 변경 docs: `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#28)·`_RISK/RISK_REGISTER`(R-RealSourceLoopUnproven 신규+RenderHardening② 명확화)·`_CANONICAL/02`·`2_ROADMAP/{00,15,19}`.
- 열린 RISK **29** = machine_status `28`(R-EventSinkDbTarget 종결 반영, 본 턴 신규 미반영) **+ 신규 R-RealSourceLoopUnproven 1**. R-EventSinkDbTarget 종결 유지.

## 🔍 REAL_SOURCE_LOOP_AUDIT (2026-06-23, 3-agent 전수 코드·산출물 감사)
> **경로 A**(레거시 카드) = 수집→raw_events→event_cards. **경로 B**(신규 Event 타임라인) = 수집→cross_source_dedup→event_ingest_pipeline→event_resolution_pipeline→event_timeline_service→/api/events/timeline→/events/timeline. **절대 혼동 금지.**

| 단계 | 코드 배선 | 실 웹 데이터 입증 | 판정 | 근거 |
|---|---|---|---|---|
| source fetch(collection probe) | ✅ | ✅ live probe | **PROVEN** | `api_live_probe_round_a.jsonl`·`_prod_orch.log`(47소스·653 extract→608 raw_events 적재·37 dup·critical_alert 1) |
| parser/extractor(소스 type별) | ✅ | ✅ | **PROVEN** | `ingestion/sources/*.py`·`raw_payload/` |
| raw_events 저장 | ✅ | ✅ | **PROVEN** | `raw_events_mirror.jsonl`(897건) |
| content_type 게이트(body vs metadata/numeric) | ✅ | ✅ | **PROVEN** | `source_content_type.py`(body_state) |
| rate/robots/legal 가드 | ✅ | ✅ | **PROVEN** | `rate_limit_policy.yaml`·robots/paywall 마커 |
| cross_source_dedup | ✅ | ◐ (raw_events엔 실; **Event 경로 입력은 synthetic**) | **PARTIAL** | `cross_source_dedup.py` |
| **raw_events→event_cards(경로 A)** | ✅ | ✅ ap_news 100(**전량 hold→공개 0**) | **PROVEN(but hold)** | R-Integration 2f·`09_VALIDATION` |
| event_ingest_pipeline(경로 B) | ✅ | ❌ in-memory fake session | **NOT_PROVEN(real)** | `test_event_ingest_pipeline.py` |
| event_resolution_pipeline CREATE/APPEND/HOLD(경로 B) | ✅ | ❌ 하드코딩 synthetic record on test-DB | **NOT_PROVEN(real)** | `test_event_resolution_live_pg.py` `_rec()` |
| event_timeline_service(events/event_updates) | ✅ | ◐ 실 DB·synthetic 데이터 | **PARTIAL** | live-PG(GREATEST/LEAST/UUID 실증, 입력 synthetic) |
| /api/events/timeline | ✅ | ◐ synthetic seed만 | **PARTIAL** | D-2c live-PG seed |
| /events/timeline(frontend) | ✅ | ◐ synthetic seed만(D-2c) | **PARTIAL** | Playwright 스크린샷(합성) |
| EVENT_RESOLUTION_ENABLED sink ↔ 실 수집 결선 가동 | 배선 | ❌ **0회** | **NOT_PROVEN** | `_prod_orch.log`=mirror sink, event_resolution 미주입 |
| 주기 auto-trigger(Celery beat) | ❌ 미배선 | ❌ | **NOT_PROVEN** | `event_ingest_pipeline.py` 잔여 주석 |
| delta_summary(실경로) | 라벨 | ❌ 디버그 라벨 `"{conf}:{reason}"` | **NOT_PROVEN(가독)** | `event_ingest_pipeline.py:174` |

**결론:** 경로 A는 실데이터로 event_cards까지 PROVEN(단 hold). **경로 B(Event 타임라인)는 실 웹 데이터가 흐른 적 0회 — 전 입증이 synthetic.** D-2c 합성 seed는 경로 B의 단계 1~5(fetch→records→dedup→candidate→resolver)를 **우회**하고 timeline_service 직접 영속 → **화면 렌더 능력**만 입증.

## ✅ 이번 턴에 달성한 것
- **D-2c 커밋(`2f897ee`):** `feat(tools): add synthetic event timeline seed + DB target guard for D-2c demo`(seed+가드+compose+docs 14파일). 게이트(secret PASS·docs_lifecycle 0·closeout EXACT MATCH·unresolved 0) 확인 후 커밋. push 안 함.
- **REAL_SOURCE_LOOP_AUDIT(ADR#28):** 3-agent(수집 계층·Event 결선·실데이터 증거) 전수 감사로 경로 A/B 실증 상태 코드·산출물 실측 판정(위 표). keyless/safe 소스 15개 식별.
- **synthetic↔real 구분 문서화:** ADR#28·R-RealSourceLoopUnproven·_CANONICAL/02·roadmap 00/15/19에 "D-2c=화면 능력 검증≠실 파이프라인 검증" 명시. **거짓 종결 0**(기존 RISK·ADR가 이미 "실 production-validation 잔여"를 정직 기록 중이었음 확인).

## ❌ 달성하지 못한 것 & 왜
- **경로 B 실데이터 검증 미실행:** 실 keyless 소스 live 수집은 **outward-facing**(실 웹 fetch·rate/robots) → 다음 턴 승인 후 진행(이번 턴은 정적 감사+문서). 검증 안 된 것을 검증됐다고 쓰지 않음.
- **delta_summary 자연어화·주기 auto-trigger·full compose E2E:** 이월(우선순위는 실 소스 검증 다음).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN(경로 B 실데이터 전): 실 소스가 경로 B를 돌 때 ① Event CREATE/APPEND/HOLD 분포, ② source-type fidelity(news/numeric/catalog 성격 보존), ③ delta_summary 가독성, ④ evidence/PII 안전성(실데이터), ⑤ /events/timeline 실데이터 렌더.

## ⚠️ 이번 턴 종결/갱신 RISK
- **신규: R-RealSourceLoopUnproven(MEDIUM)** — 경로 B 실데이터 0회를 제품 수준 단일 closure로 통합 추적(R-EventTimelineS2Hardening④·R-EventModelMigration·R-EventTimelineRenderHardening②·R-Integration 분산 잔여 결집; 중복 아님). Closure: keyless 소스 선정→실 수집→records→resolver→Event→API→frontend 실데이터 입증+source-type fidelity+delta_summary 가독.
- **명확화: R-EventTimelineRenderHardening②** — 실경로 delta_summary=디버그 라벨; **synthetic seed가 자연어로 *가림***(seed 가독성은 종결 근거 아님).
- **종결 0**(이번 턴은 닫을 수 있는 RISK 없음 — 감사는 갭을 *드러냄*). **유지:** R-EventTimelineS2Hardening·ApiScale·ModelMigration·FalseMerge·ExpansionPartialFailure·RenderHardening②. R-EventSinkDbTarget 종결 유지.

## 👉 다음 할 일 (방향: 실 소스 검증 우선)
1. **[커밋 대기]** 본 턴 docs 6 커밋 여부 지시 대기. push 금지.
2. **[다음 단계 = R-RealSourceLoopUnproven 착수]** 작은 **keyless 실 소스 production-validation**(2~5소스·타입 다양): dry-run→live→`run_event_orchestration --event-resolution`로 경로 B 실데이터 결선→records/Event/API/frontend evidence 수집→source별 PASS/PARTIAL/FAIL 표→실패는 원인별 기록. (outward-facing — 승인 후.)
3. (그 다음) delta_summary deterministic 자연어화 → full compose E2E → 주기 auto-trigger → event_cards↔Event 자동연결.

## 📁 근거 (이번 턴 핵심)
- 커밋: `2f897ee`(D-2c). 감사 근거: `ingestion/outputs/{raw_events/raw_events_mirror.jsonl,_prod_orch.log}`·`ingestion/orchestration/{source_content_type,cross_source_dedup}.py`·`backend/app/services/{event_ingest_pipeline,event_resolution_pipeline,event_timeline_service}.py`·`backend/tests/{test_event_ingest_pipeline,test_event_resolution_live_pg,test_run_event_orchestration}.py`.
- 문서: ADR#28·R-RealSourceLoopUnproven(`_RISK/RISK_REGISTER`)·`_CANONICAL/02`·`2_ROADMAP/{00,15,19}`.

---
_as_of: 2026-06-23 · D-2c 커밋(`2f897ee`) + REAL_SOURCE_LOOP_AUDIT(ADR#28, 3-agent 전수). **핵심: D-2c synthetic 데모 = 로컬 화면 렌더 능력 *가시화*이지 실 웹 소스 파이프라인 *검증* 아님.** 경로 A(수집→raw_events; →event_cards) 실데이터 운반 **PROVEN**(live probe·`_prod_orch.log` 653 extract→608 적재·ap_news 100[전량 hold→노출 0]); 경로 B(수집→Event 타임라인) **코드 배선 완료·실데이터 0회**(전 입증=fake session/하드코딩 synthetic record/example.com seed; `_prod_orch.log`=mirror sink·event_resolution 미주입; EVENT_RESOLUTION_ENABLED 실가동 0; delta_summary 실경로=디버그 라벨; auto-trigger 미배선). **R-RealSourceLoopUnproven(MEDIUM) 신규**(분산 잔여 통합, 거짓 종결 0). 방향=**full compose 보다 실 소스 production-validation(경로 B 실데이터) 우선**. 코드 변경 0(감사·문서 턴) · 열린 RISK 29 · 본 턴 docs 미커밋(커밋 지시 대기) · push 안 함._

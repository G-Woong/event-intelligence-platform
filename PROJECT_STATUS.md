# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** REAL_SOURCE_LOOP_AUDIT 가 "경로 B(Event 타임라인) 실데이터 0회"라 했던 것을, **실제 웹 뉴스 소스를 라이브로 수집해 경로 B 끝까지 흘려 검증**했습니다.
- **결과(돌파):** keyless 뉴스 10소스 live fetch → **411개 실 record** → cross_source_dedup **2 클러스터** → resolver **CREATE 2 + HOLD 3** → `/api/events/timeline` **2 실 Event** → `/events/timeline` **브라우저 렌더**(실 헤드라인: 연합뉴스 `[속보] 코스피 서킷브레이커`, 매일경제 `대우건설 중동재건 TF`). **경로 B 가 실 웹 데이터로 Event 를 만들어 화면에 노출함을 최초 입증.** 약신호 corroborator 는 HOLD 로 보류(자동병합 금지 — R-FalseMerge 보호가 실데이터로 작동).
- **정직한 한계:** ① **Event 생성은 cross-source 겹침 필요** — 작은/다양한 fetch(4소스·62 records)는 클러스터 0→Event 0; 볼륨(10소스·411)에서야 2개. ② **CREATE genesis = updates 0**(evidence/delta_summary 는 APPEND 에서만 영속). ③ **delta_summary 실경로=디버그 라벨**(여전히 자연어 아님). → **R-RealSourceLoopUnproven MEDIUM→LOW 부분종결**(핵심 흐름 입증, 품질/커버리지 잔여). **막힌 것 없음(BLOCKED 0).** 코드 변경 0(검증 턴).

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `9fccbcb`**(docs audit 커밋, 직전 턴) 위 **본 턴 docs 미커밋 변경 = docs 6**(코드 0 — 실 소스 검증 턴). **`machine_status.json`은 `2f897ee`로 stale**(Stop 훅이 턴 끝 갱신 — 인-턴 커밋 `9fccbcb` 미반영, lag).
- 변경 docs: `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#29)·`_RISK/RISK_REGISTER`(R-RealSourceLoopUnproven 부분종결+RenderHardening② 확인)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.
- 열린 RISK **29**(R-RealSourceLoopUnproven 은 **부분종결=유지**, severity MEDIUM→LOW; 신규 종결 0). 검증 하니스 `.harness/_validate_real_loop.py`는 throwaway(gitignored·미커밋).

## 🔬 실 소스 production-validation 결과 (ADR#29, 2026-06-23 · event_intel_test · EVENT_RESOLUTION on)
**경로 B 단계별 (실데이터):**

| 단계 | 결과 | 판정 |
|---|---|---|
| dry-run sink 결선 | enabled=True·0 error | ✅ PROVEN |
| source fetch (10 뉴스 live) | 411 records·0 error·0 rate_limited | ✅ PROVEN |
| eventqueue dedup | 408 written (3 within-source dup) | ✅ PROVEN |
| cross_source_dedup | **2 클러스터**(possible_duplicate)·403 singleton | ✅ PROVEN |
| resolver (event_resolution_pipeline) | **CREATE 2 + HOLD(held 3→links 3)** · failed 0 | ✅ PROVEN |
| events/event_updates 영속 | events +2 mapped +3 held(비공개) | ✅ PROVEN |
| `/api/events/timeline` | **2 실 Event non-empty**(내부ID/source_refs 미노출) | ✅ PROVEN |
| `/events/timeline` 브라우저 | 실 헤드라인 렌더(yna·매경) | ✅ PROVEN |
| delta_summary 가독 | 전량 CREATE→update 미영속; 코드상 APPEND 시 디버그 라벨 | ❌ NOT_PROVEN |
| APPEND 실관측 / 비-뉴스 타입 Event / 주기 auto-trigger | 미관측/미배선 | ❌ NOT_PROVEN |

**source별 (3 배치, 전량 fetch PASS·0 error):**

| source | type | fetch | Event 기여 |
|---|---|---|---|
| yna(연합뉴스) | news | PASS | **CREATE primary** (코스피 서킷브레이커) |
| maekyung(매경) | news | PASS | **CREATE primary** (대우건설 중동재건 TF) |
| bbc·ap_news·techcrunch·the_verge·zdnet_korea·etnews·hankyung·aljazeera | news | PASS | singleton 또는 held member(약신호) |
| gdelt | official | PASS | singleton (4소스 배치) |
| hacker_news | community | PASS | singleton (4소스 배치) |
| coinbase_market·binance_market | market | PASS | 단일 집계 스냅샷 1건 → 미클러스터 |

(per-source record 수 분해는 rate limit 준수 위해 재fetch 안 함 — aggregate + 2 Event primary 만 기록.)

## ✅ 이번 턴에 달성한 것
- **D-2c·REAL_SOURCE_LOOP_AUDIT 커밋(`2f897ee`·`9fccbcb`)** 안정 기준점.
- **실 소스 경로 B 검증(ADR#29):** dry-run(결선 확인)→live(10 뉴스·411 records)→2 실 Event→API non-empty→브라우저 렌더. **경로 B 실 웹 데이터 흐름 0회→1회 입증.** R-FalseMerge 보호(HOLD) 실데이터 작동.
- **정직한 발견 문서화:** Event 생성=cross-source 겹침 필요·CREATE genesis updates 0·delta_summary 디버그 라벨. ADR#29·R-RealSourceLoopUnproven(MEDIUM→LOW)·RenderHardening②·_CANONICAL/02·roadmap 00/15 반영.

## ❌ 달성하지 못한 것 & 왜
- **delta_summary 자연어화**: 실경로 디버그 라벨(상류 `event_ingest_pipeline`) — 다음 우선순위.
- **APPEND 실관측·비-뉴스 타입 Event**: 같은 사건 재출현/타입 다양 클러스터 필요(작은 검증 미관측).
- **CREATE genesis evidence 미표시**: candidate evidence 가 CREATE 시 미영속(설계 gap — 코드 미변경, 발견만).
- **주기 auto-trigger·운영 DB 0006 배포·full compose E2E**: 이월.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: APPEND 실데이터 거동·비-뉴스 타입 Event evidence/fidelity·delta_summary 자연어화 후 가독성·운영 DB 대량 거동.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-RealSourceLoopUnproven: MEDIUM→LOW 부분종결**(핵심: 경로 B 실데이터로 Event 생성·화면 노출 입증). 잔여(LOW): delta_summary 가독성·APPEND 실관측·비-뉴스 타입 Event·CREATE genesis evidence·auto-trigger·운영 DB 배포.
- **R-EventTimelineRenderHardening② 확인**: 실 검증에서 전량 CREATE 라 delta_summary 미영속이었고, 코드상 APPEND 시 디버그 라벨(synthetic seed 가 가림). deterministic template 자연어화 우선 검토.
- **신규 종결 0**(완전 종결 아님 — 검증 안 된 것 미종결). R-EventSinkDbTarget 종결 유지. 유지: R-EventTimelineS2Hardening·ApiScale·ModelMigration·FalseMerge·ExpansionPartialFailure·RenderHardening②.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 docs 6 커밋 여부 지시 대기. push 금지.
2. **[다음 단계 = delta_summary deterministic 자연어화]** 실경로 `event_ingest_pipeline` 의 delta_summary 를 source count/type/relation/confidence/domains 기반 자연어 template 으로(LLM 전). → R-EventTimelineRenderHardening② 종결 + R-RealSourceLoopUnproven ⑦.
3. (그 다음) APPEND 실관측(같은 사건 재출현)·비-뉴스 타입 Event·주기 auto-trigger·CREATE genesis evidence 표시·full compose E2E.

## 📁 근거 (이번 턴 핵심)
- 검증: `.harness/_validate_real_loop.py`(throwaway)·`run_event_orchestration --event-resolution`·event_intel_test 실 Event 2건(yna·매경 헤드라인)·`/api/events/timeline`·Playwright 스크린샷(`.harness/_TRASH/`).
- 문서: ADR#29(`_DECISIONS`)·R-RealSourceLoopUnproven 부분종결(`_RISK/RISK_REGISTER`)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-23 · 실 소스 production-validation(ADR#29) — keyless 뉴스 10소스 live fetch **411 real records**→cross_source_dedup **2 클러스터**→resolver **CREATE 2 + HOLD 3**(약신호 corroborator 보류=R-FalseMerge 실데이터 작동)→`/api/events/timeline` **2 실 Event non-empty**→`/events/timeline` 브라우저 렌더(yna `코스피 서킷브레이커`·매경 `대우건설 중동재건 TF`). **경로 B 가 실 웹 데이터로 Event 생성·화면 노출 최초 입증 → R-RealSourceLoopUnproven MEDIUM→LOW 부분종결.** 발견: Event 생성=cross-source 겹침 필요(작은 fetch=클러스터 0)·CREATE genesis updates 0(evidence APPEND 에서만)·delta_summary 실경로=디버그 라벨(R-EventTimelineRenderHardening②). 코드 변경 0(검증 턴)·열린 RISK 29(부분종결 유지)·본 턴 docs 6 미커밋(커밋 지시 대기)·검증 하니스 throwaway(미커밋)·push 안 함._

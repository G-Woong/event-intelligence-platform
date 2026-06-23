# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 지난 턴 발견한 안전 결함 — **커뮤니티/검색/시장숫자 출처가 잘못 사건(Event)으로 발행되던 문제** — 을 코드로 막았습니다(source-type publish gate). 시장 숫자가 Event가 되는 건 투자조언 경계라 특히 중요.
- **이번 턴에 실제로 끝낸 것:** 먼저 ADR#32 검증 문서를 `c926112`로 커밋. 이어 **gate 구현**: 발행 가능 출처(공식/뉴스)가 하나도 없는 순수 커뮤니티/검색/시장 클러스터는 **WITHHELD(미발행·미저장)** 처리. **측정: backend 285 passed/4 skip/0 fail(+17 gate 테스트) + ingestion 1331 = 1616 green · frontend tsc0/test12/lint0.** 결정론 7 시나리오에서 S5/S6/S7(순수 비뉴스)→차단, S1/S4(공식/뉴스 포함)→발행 정상 확인.
- **정직한 한계(adversarial):** **R-SourceTypeFidelityGate는 MEDIUM→LOW 부분종결**(완전 종결 아님). 핵심 발행 차단은 닫혔으나 **primary-authority 미구현** 잔여 — 유일 발행가능 멤버가 약신호로 분리되면 커뮤니티가 Event 대표가 될 수 있음(드문 경우). adversarial이 잡은 P1(ADR#33 본문·RISK 갱신)·P2(drift 테스트·primary-authority)·P3(WITHHELD 단위 테스트) 반영. **BLOCKED 0.** push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `c926112`**(ADR#32 docs, 본 턴 첫 커밋) 위 **gate 구현 = 미커밋 code 4 + tests 4 + docs 6**. `machine_status.json` 은 직전 Stop 기준 **stale**(lag).
- code 4: `event_resolver.py`(ACTION_WITHHELD+gate)·`event_resolution_pipeline.py`(source_types 전달)·`event_timeline_service.py`(WITHHELD 분기)·`event_ingest_pipeline.py`(집계). tests 4: `test_event_resolver`(+gate 10·drift 1)·`test_event_ingest_pipeline`(+3)·`test_event_timeline_service`(+WITHHELD 1)·`test_event_resolution_live_pg`(+2). docs 6: `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#33)·`_RISK/RISK_REGISTER`(부분종결)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.
- 열린 RISK **29**(R-SourceTypeFidelityGate **부분종결=유지**, primary-authority 잔여; 신규 0). throwaway(검증 하니스)는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (source-type publish gate — ADR#33)
- **gate 구현**: `resolve_routing` 에 `member_source_types` + 신규 **`ACTION_WITHHELD`**. 미매핑 신규 발행(CREATE)인데 publishable 멤버(`{official, article}`)가 0이면 WITHHELD — `apply_routing` 조기반환(**DB 미접근·commit 0·미영속·미매핑·멱등**). `summary.withheld_source_type` 집계(가시화). gate 는 CREATE(미매핑)만 — 매핑된 event 의 APPEND(community corroborator)는 미적용. 마이그레이션·schema·UI/API **0**.
- **검증**: 결정론 7 시나리오(S5 pure-community 강·S6 structured 동일 signal-key·S7 pure-community 약 → **withheld=1·created=0**; S1 official+news·S4 community+news → created=1). 단위 12(resolver gate 10·publishable drift 1·WITHHELD apply_routing execute/commit 0 직접단언 1) + ingest 통합 3 + live-PG 2(실 DB pure-community withheld·official+news 발행+official fidelity). 하위호환: source_types=() 면 게이트 비활성 → 기존 news 회귀 0.
- **adversarial 반영**: P1-1(ADR#33 ledger 본문 작성)·P1-2(RISK MEDIUM→LOW 부분종결·완전 종결 금지)·P2-2(publishable 값 계약 drift 테스트)·P3-1(WITHHELD 단위 테스트). P2-1(primary-authority)·P3-2(fail-open)는 잔여로 명시.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **primary-authority(official>news>community)**: gate 는 "발행 가부"만 막고 primary 선정(`cross_source_dedup` members[0])은 통제 안 함 → 유일 publishable 멤버가 weak_only(held)면 community-primary Event 발행. candidate primary 선정 변경 필요 → 이월(R-SourceTypeFidelityGate 잔여).
- **fail-open 구조**: 커스텀 `candidate_for` 가 source_type 미제공 시 gate 우회(기본 매퍼는 안전).
- **실 cross-source 비뉴스 Event 관측**: gate 는 결정론+live-PG 로 검증(실 cross-source 겹침은 드물어 실 fetch 로 gate 발동 재현 비실용 — 정직).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: held-publishable+community-primary 실제 발생률·primary-authority 도입의 기존 title 영향 범위.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-SourceTypeFidelityGate: MEDIUM→LOW 부분종결(유지)** — pure community/search/structured 단독 cross-source **직접 발행 차단**(핵심 안전 종결, S5/S6/S7; 투자조언 경계 S6 포함). **잔여(LOW): primary-authority 미구현**(held-publishable→community-primary)·fail-open. Closure: primary authority 우선순위 도입 후 완전 종결.
- **종결 0**(부분종결만; 완전 종결 금지 — adversarial: closure 조건의 primary-authority 미구현). 유지: RealSourceLoop·S2Hardening·ModelMigration·FalseMerge·ExpansionPartialFailure·ApiScale.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 code 4 + tests 4 + docs 6 커밋 여부 지시 대기. push 금지.
2. **[다음 단계 = primary-authority]** candidate primary 선정을 authority 순(official>news>community)으로 — mixed/held-publishable 클러스터의 Event 대표를 고품질 출처로. → R-SourceTypeFidelityGate 완전 종결. (그 다음) 실 cross-source 비뉴스 Event·주기 auto-trigger·full compose E2E.

## 📁 근거 (이번 턴 핵심)
- 코드: `event_resolver.py`(`_PUBLISHABLE_SOURCE_TYPES`·`_has_publishable`·ACTION_WITHHELD)·`event_resolution_pipeline.py`·`event_timeline_service.py`·`event_ingest_pipeline.py`.
- 검증: 단위 12+ingest 3+live-PG 2(backend 285) + 결정론 하니스(`.harness/_TRASH/_validate_nonnews.py`, S5/S6/S7 withheld). frontend tsc0/test12/lint0.
- 문서: ADR#33(`_DECISIONS`)·R-SourceTypeFidelityGate 부분종결(`_RISK/RISK_REGISTER`)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-23 · source-type publish gate(ADR#33) — `resolve_routing` 에 `member_source_types`+신규 `ACTION_WITHHELD`: 미매핑 CREATE 인데 publishable 멤버(official/article) 0이면 WITHHELD(미영속·미노출·멱등; DB 미접근). pure community/search/structured 단독 cross-source 직접 발행 차단(S5/S6/S7 withheld 재현; 투자조언 경계 S6 포함). 매핑 APPEND(community corroborator)는 미적용. 마이그레이션/schema/UI 0. 검증 단위 12+ingest 3+live-PG 2(**backend 285 passed/4 skip/0 fail + ingestion 1331 green · frontend tsc0/test12/lint0**). adversarial 반영: P1(ADR#33 본문·RISK 부분종결)·P2(drift 테스트·primary-authority 잔여)·P3(WITHHELD 단위·fail-open). **R-SourceTypeFidelityGate MEDIUM→LOW 부분종결**(핵심 발행 차단 done·primary-authority 잔여 — **완전 종결 아님**). 열린 RISK 29(부분종결 유지)·code 4+tests 4+docs 6 미커밋(커밋 지시 대기)·push 안 함._

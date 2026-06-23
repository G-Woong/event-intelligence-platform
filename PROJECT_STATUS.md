# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 실 수집으로 만들어진 Event 상세 화면이 **"아직 업데이트가 없습니다"로 비어 있던 문제**를, 사건이 처음 만들어질 때 그 **생성 근거(genesis)를 타임라인 첫 항목으로 남기도록** 고쳐 해결했습니다.
- **이번 턴에 실제로 끝낸 것:** `apply_routing`(사건 생성·갱신 로직)의 **신규 생성(CREATE) 경로에 genesis update 1행 추가**(LLM 0·DB 마이그레이션 0·프런트 변경 0). 이전 "신규 생성 시 업데이트 0개" 불변식을 **의도적으로 개정**(ADR#31)하고, 이를 잠그던 **테스트 21개 단언을 의도적으로 갱신**(+genesis 자연어/evidence 검증 순증). **측정: backend 268 passed/4 skip/0 fail(live-PG 21 포함) + ingestion 1331 = 1599 green · frontend tsc0/test12/lint0.**
- **눈으로 확인한 것:** 실 파이프라인이 만든 신규 Event 를 **실제 브라우저 화면**(`/events/timeline/{id}`)에서 열어, genesis 자연어 **"뉴스 보도가 동일 식별자로 확인된 사건입니다."** + 증거 링크(`example.com … (article · primary)`)가 렌더되는 것을 **1회 관측(Playwright)**. CREATE-only Event 가 더 이상 빈 상세가 아닙니다. **BLOCKED 0.** push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `bdef241`**(delta_summary 자연어화, 본 턴 첫 커밋) 위 **genesis 변경 = 미커밋 code 1 + tests 4 + docs 8**. `machine_status.json` 은 직전 Stop 시점 기준 **stale**(lag).
- code: `backend/app/services/event_timeline_service.py`(apply_routing genesis). tests 4: `test_event_resolution_pipeline`·`test_event_ingest_pipeline`·`test_event_timeline_service`·`test_event_resolution_live_pg`. docs 8: `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#31)·`_RISK/RISK_REGISTER`·`_RISK/RISK_CLOSED`(R-EventTimelineRenderHardening 완전 종결)·`5_REFERENCE/EVENT_SCHEMA`·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.
- 열린 RISK **28**(R-EventTimelineRenderHardening **완전 종결**로 1건 감소; 신규 0). throwaway(seed 스크립트·스크린샷)는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (CREATE genesis update — ADR#31)
- **전수 분석 선행**(3-agent + 직접 정독): ① 불변식 "CREATE는 update 0"이 load-bearing(ADR#16/#19/#30·테스트 18+잠금) ② 읽기 API(`PublicEventTimelineResponse.updates`)·프런트(`EventUpdateItem`)는 변경 0으로 genesis 렌더 ③ 대안 B(Event 본체 evidence 스키마)는 마이그레이션+프런트=엄격히 더 큼 → **후보 A(genesis update) 채택**(최소 변경·승인된 closure 경로).
- **구현**: `apply_routing` clean-win CREATE(`mapped == new_id`) 분기에 `append_update(new_id, candidate)` 1회. candidate 가 이미 보유하던 delta_summary/evidence/source_refs 를 **폐기 대신 첫 타임라인 항목으로 영속**. observed_at==first_seen → FSD no-op(timestamp 왜곡 0), create→map→genesis 함수 끝 1회 commit 원자. **멱등**: genesis 는 create_event(cluster_event_map PK, 1회성)에 묶여 정확히 1회. `_tally` 는 action 기준이라 created/appended 카운트 불변.
- **시맨틱 개정**: event_updates = "변화분" → "**append-only 관측 이력**(첫 행=genesis 생성 근거, 이후=변화분)". append-only·가역성·감사 불변식 보존(INSERT 만).
- **검증**: 불변식 의존 **21단언 의도적 갱신**(unit 9: pipeline 5·ingest 3·service 1 `assert_not_awaited→awaited`; live-PG 12: count 11·evidence 인덱스 시프트 1) + genesis 순증 단언(genesis delta_summary 영속·**자연어 내용**·evidence 없음). backend 268·ingestion 1331·frontend tsc0/test12/lint0. **화면 렌더 1회 관측**(Playwright, backend→event_intel_test).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 fetch APPEND 미관측**: 같은 사건 재출현이 필요(비결정). genesis 자연어 화면 도달은 입증됐으나 APPEND 변화분 화면은 잔여.
- **비-뉴스 타입 Event**: 뉴스만 Event 형성(official/community/structured 는 singleton → 미형성). source-type fidelity 미입증.
- **주기 auto-trigger(Celery beat)·운영 DB(event_intel) 0006 배포·full `docker compose up --build` E2E·event_cards↔Event 자동연결**: 이월.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 실 fetch APPEND 거동·비-뉴스 타입 클러스터 형성 가능성·강신호 distinct≥2 클러스터(현재 실 관측은 distinct 1 → "동일 식별자로 확인" 문안).

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-EventTimelineRenderHardening: render 메커니즘 종결(①②③)** → `RISK_CLOSED.md`. ①③ ADR#26(error.tsx·Public* 구조적 제외) + ② ADR#30 자연어화 **+ ADR#31 genesis update 로 실 렌더 도달**(화면 관측 — **단 synthetic 강신호 record; 실 네트워크 fetch genesis 렌더는 R-RealSourceLoopUnproven 로 추적**). 지난 턴 adversarial P1-1 의 "화면 미도달"을 genesis 로 해소.
- **R-RealSourceLoopUnproven(LOW) 유지**: ✅ CREATE genesis 가시화 해소(ADR#31). **잔여**: 실 fetch APPEND·비-뉴스 타입 Event·주기 auto-trigger·운영 DB 0006 배포.
- **신규 RISK 0**(불변식 개정은 ADR#31 로 명시 관리, 테스트로 잠금). 유지(미종결): S2Hardening·ApiScale·ModelMigration·FalseMerge·ExpansionPartialFailure.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 code 1 + tests 4 + docs 8 커밋 여부 지시 대기. push 금지.
2. **[다음 단계 후보]** (1) **비-뉴스 타입 Event 형성**(official/community/structured 가 cross-source 클러스터·Event 를 만드는지 — source-type fidelity) → (2) 실 fetch APPEND 관측(자연어 변화분 화면 도달) → (3) full `docker compose up --build` E2E → (4) 주기 auto-trigger(Phase 2).

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/app/services/event_timeline_service.py`(apply_routing CREATE clean-win genesis). 테스트 4파일(불변식 21단언 갱신 + genesis 자연어/evidence 검증).
- 검증: backend 268/4skip/0fail(live-PG 21 — 실 파이프라인 CREATE genesis delta_summary 자연어 단언) + ingestion 1331 + frontend tsc0/test12/lint0. **화면 관측**: Playwright(throwaway 스크린샷 `.harness/_TRASH/`).
- 문서: ADR#31(`_DECISIONS`)·R-EventTimelineRenderHardening 완전 종결(`_RISK/RISK_CLOSED`)·R-RealSourceLoopUnproven 갱신(`_RISK/RISK_REGISTER`)·`5_REFERENCE/EVENT_SCHEMA`(genesis 시맨틱)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-23 · CREATE genesis update(ADR#31) — `apply_routing` clean-win CREATE 에 genesis update 1행(생성 근거: candidate 의 delta_summary/evidence) 추가로 "CREATE는 update 0" 불변식 의도적 개정(마이그레이션 0·프런트 0·멱등). event_updates="append-only 관측 이력". 불변식 의존 21단언 의도적 갱신. 실 파이프라인 CREATE→`/events/timeline/{id}` 화면에 genesis 자연어("뉴스 보도가 동일 식별자로 확인된 사건입니다.")+evidence 렌더 **1회 관측(Playwright)** → **R-EventTimelineRenderHardening 완전 종결(①②③)**, R-RealSourceLoopUnproven genesis 가시화 해소(잔여: 비뉴스 타입·실 fetch APPEND·auto-trigger·운영 DB). 측정 **backend 268 passed/4 skip/0 fail + ingestion 1331 = 1599 green · frontend tsc0/test12/lint0.** 열린 RISK 28(−1)·code 1+tests 4+docs 8 미커밋(커밋 지시 대기)·push 안 함._

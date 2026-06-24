# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 보류(held)됐던 근거가 나중에 강한 증거로 다시 나타날 때 **같은 사건이 두 개로 쪼개지지 않도록** 했습니다. 다시 나타난 묶음의 제목이 기존 사건과 같으면 그 사건에 이어붙이고(중복 0), 다르면 별개 사건으로 둡니다(잘못된 병합 방지).
- **이번 턴에 실제로 끝낸 것:** 먼저 ADR#37을 `b163c8d`로 커밋. 이어 **ADR#38 held 승격(candidate B: 제목 판정)**: held member 재등장 → 제목 같으면 parent APPEND·다르면 독립 CREATE. **측정: backend 286p/37s(live-PG Docker 대기) + ingestion 1332 green · frontend tsc0/test12/lint0.** 인메모리 7(official/community/market) + gate-bypass로 잠금.
- **정직한 한계(adversarial):** **R-FalseMerge는 닫지 않았습니다(gap① 부분종결).** held 재등장 중복 방지는 인메모리+gate-bypass로 입증했으나, **① live-PG 미실증**(Docker 미가동 — `find_held_parents` 신규 SQL이 실 DB에서 미실행) **② cross-batch event identity**(매 배치 새 기사가 새 Event로 분열·비-held 멤버 재등장은 fix 밖, semantic 층) 잔여 → **완전 종결 OVERCLAIM**. P1 0(코드)·BLOCKED 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `b163c8d`**(ADR#37, 본 턴 첫 커밋) 위 **ADR#38 = 미커밋 code 4 + tests 3 + docs 6**. `machine_status.json` 은 직전 Stop 기준 **stale**(lag).
- code 4: `cross_source_dedup.py`(titles_similar 공개)·`event_timeline_service.py`(find_held_parents)·`event_resolution_pipeline.py`(title_matcher 승격+멱등 매핑)·`event_ingest_pipeline.py`(titles_similar 주입). tests 3: `test_event_ingest_pipeline`(held 승격 7+_FakeSession 시뮬)·`test_event_resolution_live_pg`(held 승격 3·Docker 대기 SKIP)·`test_cross_source_dedup`(titles_similar). docs 6: `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#38)·`_RISK/RISK_REGISTER`(R-FalseMerge gap① 부분종결)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.
- 열린 RISK **28**(R-FalseMerge **open 유지**=gap① 부분종결; 신규 0·종결 0). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (held 승격 candidate B — ADR#38)
- **문제**: 약신호로 HOLD(degenerate held event+possible link)된 멤버가 다른 cluster_id로 강신호 재등장 → 미매핑→CREATE→**중복 Event**(같은 사건 분열).
- **구현(후보 B split-aware)**: `titles_similar`(약신호 결합과 동일 정규화/Jaccard≥0.8) 공개 + `find_held_parents`(degenerate canonical_title==member_key→possible→**매핑된** parent) + `resolve_and_apply_cluster(title_matcher)`: 미매핑 CREATE 전 held lineage 조회 → **재등장 cluster 제목↔parent 제목 같은 사건일 때만** parent 라우팅(강신호 APPEND·약신호 HOLD)+cluster_id→parent 매핑(멱등), 불일치면 독립 CREATE(false-merge 방어·무조건 병합 금지). schema/UI 0·하위호환(title_matcher None=비활성).
- **검증(인메모리 7)**: official same→APPEND(중복 0)·different→CREATE·no-lineage→CREATE + community/market match→parent 연결 corroborator APPEND(자체 Event 0)·mismatch→gate WITHHELD(승격이 직접발행/투자조언 차단 무력화 안 함). titles_similar 단위.
- **adversarial OVERCLAIM 수용** → **R-FalseMerge 닫지 않음**.

## 🔎 source orchestration 점검 (이번 턴 감사)
- **news/domain**(article→publishable): 살아 있음(ADR#29 실 fetch Event 실증). possible_duplicate 동질 gate와 정합.
- **official**(document/official→publishable): 살아 있음. *관찰*: catalog 오버라이드(aladin/tmdb/kofic/kopis/tour/igdb→catalog_metadata)가 Event 파이프라인 record_type에서 official_record로 새지 않는지 확인 필요(잠재 fidelity — 별도 점검 이월).
- **search**(→non-publishable URL candidate): 직접발행 차단 유지(gate).
- **community**(→non-publishable): 직접발행 금지·held/corroborator 유지. held 승격은 parent 연결(APPEND)만, 자체 Event 0(ADR#38 입증).
- **market/numeric/structured**(→signal, non-publishable): signal-only 유지·투자조언성 Event 금지. held 승격도 parent 연결만(mismatch→WITHHELD).
- **unknown/missing source_type**: fail-closed WITHHELD 유지(승격 경로도 미매핑 CREATE면 gate 적용).

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-FalseMerge: open 유지(gap① 부분종결, 갱신)** — held member 재등장 중복 방지 구현(ADR#38, 인메모리+gate-bypass 입증). **완전 종결 보류**(adversarial OVERCLAIM): (a) live-PG held 승격 미실증(Docker 대기) (b) cross-batch event identity 잔여. 닫지 말 RISK 5개 open 유지.
- **종결 0**(부분종결만). 유지: RealSourceLoop·S2Hardening·ModelMigration·**FalseMerge**·ExpansionPartialFailure·ApiScale.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **R-FalseMerge 완전 종결**: ① live-PG held 승격 3 테스트(작성 완료)는 Docker 미가동으로 미실행 — `find_held_parents` 신규 SQL의 실 DB 입증 필요. ② cross-batch event identity(신규 corroborating 기사 분열·비-held 확정 멤버 재등장)는 held가 아니라 fix 밖 → semantic/엔티티 동일성 층(또는 별도 RISK) 이월.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- **BLOCKED(외부 의존)**: live-PG held 승격 검증은 **Docker Desktop 미가동**으로 보류(이전 턴엔 가동·27 passed). Docker 복구 시 `pytest backend/tests/test_event_resolution_live_pg.py` 로 즉시 실증 가능(테스트 작성 완료). UNKNOWN: cross-batch event identity 정책(merge 기준).

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 code 4 + tests 3 + docs 6 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** R-FalseMerge 완전 종결: (a) Docker 가동 후 live-PG held 승격 3 green 실증 (b) cross-batch event identity 결정(semantic 동일성 vs 별도 RISK). 그 다음 실 cross-source 비뉴스/약신호 Event·실 fetch APPEND·주기 auto-trigger.

## 📁 근거 (이번 턴 핵심)
- 코드: `cross_source_dedup.py`(titles_similar)·`event_timeline_service.py`(find_held_parents)·`event_resolution_pipeline.py`(title_matcher 승격).
- 검증: 인메모리 held 승격 7(`test_event_ingest_pipeline`)+titles_similar — backend 286p/37s(live-PG Docker 대기)·ingestion 1332·frontend tsc0/test12/lint0. live-PG held 승격 3=Docker 대기.
- 문서: ADR#38(`_DECISIONS`)·R-FalseMerge gap① 부분종결(`_RISK/RISK_REGISTER`)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-23 · held 승격 candidate B(ADR#38) — held member(degenerate+possible link)가 다른 cluster_id로 강신호 재등장 시 `find_held_parents`+`titles_similar`로 **재등장 제목↔parent 제목 같은 사건일 때만** parent 라우팅(APPEND/HOLD)+멱등 매핑, 불일치면 독립 CREATE(false-merge 방어). 검증 인메모리 7(official/community/market match→parent 연결·mismatch→CREATE/WITHHELD)+titles_similar(**backend 286p/37s(live-PG Docker 대기) + ingestion 1332 green · frontend tsc0/test12/lint0**); live-PG held 승격 3=Docker 미가동 SKIP. **adversarial OVERCLAIM → R-FalseMerge open 유지(gap① 부분종결)** — live-PG 미실증(Docker 대기)+cross-batch event identity 잔여. 열린 RISK 28(종결 0)·code 4+tests 3+docs 6 미커밋(커밋 지시 대기)·push 안 함._

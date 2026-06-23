# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 두 가지 데이터 품질 결함을 고쳤습니다 — (A) 같은 근거가 "사건 대표"와 "보류 항목"으로 **중복 저장**되던 것을 제거, (B) 출처 종류를 **모를 때 조용히 발행되던 구멍**을 막았습니다(모르면 보류=fail-closed).
- **이번 턴에 실제로 끝낸 것:** 먼저 primary-authority를 `8a4b9af`로 커밋. 이어 **목표 A(held 이중등장 제거)** + **목표 B(source_type fail-closed)**. **측정: backend 295 passed/4 skip/0 fail(+5) + ingestion 1331 = 1626 green · frontend tsc0/test12/lint0.** 단위 + 영속층 + live-PG로 잠금.
- **정직한 한계(adversarial):** **R-SourceTypeFidelityGate는 여전히 LOW 부분종결**(완전 종결 아님). gate+대표authority+held-dedup+fail-closed는 됐으나, adversarial이 잡은 **약신호-primary 시맨틱**(약신호로만 묶인 공식 출처가 사건 대표가 될 수 있음 — authority>신호강도 충돌)이 R-FalseMerge와 긴장하며 **정당화 미완**. 그래서 RISK를 닫지 않았습니다(과대 종결 회피). P1 0. **BLOCKED 0.** push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `8a4b9af`**(primary-authority, 본 턴 첫 커밋) 위 **목표 A+B = 미커밋 code 3 + tests 5 + docs 6**. `machine_status.json` 은 직전 Stop 기준 **stale**(lag).
- code 3: `event_resolver.py`(fail-closed gate)·`event_timeline_service.py`(ResolvedCandidate.primary_member_key+apply_routing held 제외)·`event_ingest_pipeline.py`(candidate primary_member_key). tests 5: `test_event_resolver`·`test_event_ingest_pipeline`·`test_event_timeline_service`·`test_event_resolution_pipeline`·`test_event_resolution_live_pg`. docs 6: `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#35)·`_RISK/RISK_REGISTER`(LOW 부분종결·R-FalseMerge 교차)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.
- 열린 RISK **29**(R-SourceTypeFidelityGate **LOW 부분종결=유지**, 약신호-primary 잔여; 신규 0). throwaway(검증 하니스)는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (held-dedup + fail-closed — ADR#35)
- **목표 A(held 이중등장 제거)**: `ResolvedCandidate.primary_member_key` 추가 → `candidate_from_cluster` 가 authority 대표 키 설정 → `apply_routing` held 루프가 대표 멤버 skip(create_event/hold_link 둘 다 미호출). **키 정확 일치만 제외**(동일 record 만; 다른 source corroborator 는 held 유지=과도 제거 0). primary_member_key=None(레거시) 이면 제외 없음(하위호환). held degenerate 미생성 → event_links 도 미생성(정합). R-FalseMerge append-불변 미터치.
- **목표 B(fail-closed)**: `resolve_routing` gate 를 publishable 0이면(빈/미지/누락 포함) WITHHELD — **source_type 누락의 조용한 발행 우회 차단**. 합성 helper `_cand()`(pipeline·live-PG)에 명시 source_type 주입(누락 묵인 금지). 미지 record_type→WITHHELD.
- **검증**: 목표 A 단위 2(대표 held 제외=links 0·events 1 / corroborator held 유지=links 1)+영속층 1(primary_member_key→held 1개 제외 직접 단언). 목표 B resolver 단위(빈→WITHHELD·mixed official+미지→발행)+ingest(미지→WITHHELD). 회귀 0.
- **adversarial 반영**: P1 0. P2(약신호-primary 시맨틱 미정당화·fail-open 범위)→**R-SourceTypeFidelityGate 닫지 않음**(LOW 부분종결 유지)·잔여 명시·R-FalseMerge 교차 기재. P3(held-제외 영속층 단위·delta kind)→영속층 단위 테스트 추가.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **약신호-primary 시맨틱**: primary-authority 가 weak_only(약신호 title-link) publishable 멤버를 대표로 세울 수 있음 — 그 약신호 결합이 검증 없이 Event 얼굴이 됨. held 제외로 DB 이중등장은 막으나 시맨틱(authority>signal-strength)은 정당화 미완 → R-SourceTypeFidelityGate 완전 종결 차단. 해소엔 "core 우선/저신뢰 표시/WITHHELD" 중 설계 결정 필요.
- **delta_summary kind primary-only**·**garbage-in**(커스텀 candidate_for 가 잘못된 source_type 주입)은 가드 밖(문서).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 약신호-primary 시맨틱의 올바른 해소 방향(core 우선 vs 저신뢰 발행 vs WITHHELD)·실제 발생률.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-SourceTypeFidelityGate: LOW 부분종결(유지)** — gate(ADR#33)+primary-authority(ADR#34)+held-dedup·fail-closed(ADR#35). **완전 종결 아님**(adversarial: 약신호-primary 시맨틱 잔여·R-FalseMerge 교차). Closure: 약신호-primary 시맨틱 정당화/해소.
- **R-FalseMerge** 잔여 ①에 authority weak-primary 교차 경로 기재(미종결 유지).
- **종결 0**(부분종결만; 완전 종결 금지 — adversarial). 유지: RealSourceLoop·S2Hardening·ModelMigration·FalseMerge·ExpansionPartialFailure·ApiScale.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 code 3 + tests 5 + docs 6 커밋 여부 지시 대기. push 금지.
2. **[다음 단계 = 약신호-primary 시맨틱 결정]** weak_only publishable 멤버를 대표로 세우는 경로의 안전성 — ① primary 를 강신호 core 로 제한(core 우선) ② 저신뢰 표시(weak-link 명시) ③ WITHHELD 중 설계 결정(ADR 선행) → R-SourceTypeFidelityGate 완전 종결. (그 다음) 실 cross-source 비뉴스 Event·실 fetch APPEND·주기 auto-trigger.

## 📁 근거 (이번 턴 핵심)
- 코드: `event_timeline_service.py`(primary_member_key·held 제외)·`event_resolver.py`(fail-closed)·`event_ingest_pipeline.py`(candidate primary_member_key).
- 검증: 단위 5(resolver/ingest/timeline)+live-PG — backend 295. frontend tsc0/test12/lint0.
- 문서: ADR#35(`_DECISIONS`)·R-SourceTypeFidelityGate LOW 부분종결·R-FalseMerge 교차(`_RISK/RISK_REGISTER`)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-23 · held-dedup + fail-closed(ADR#35) — 목표 A: `ResolvedCandidate.primary_member_key` + `apply_routing` held 루프가 대표 멤버 제외(키 정확 일치만; corroborator 유지) → 대표 record 의 held degenerate **DB 이중등장 제거**. 목표 B: `resolve_routing` gate 가 publishable 0이면(빈/미지/누락) WITHHELD → **source_type 누락 조용한 발행 우회 차단**(`_cand` 합성 helper 도 명시 source_type). 검증 단위 5+영속층 1+live-PG(**backend 295 passed/4 skip/0 fail + ingestion 1331 = 1626 green · frontend tsc0/test12/lint0**). adversarial: P1 0·구현 정확/하위호환/회귀 0; **R-SourceTypeFidelityGate LOW 부분종결 유지(완전 종결 금지** — 약신호-primary 시맨틱(authority>signal-strength) 미정당화·R-FalseMerge 교차). 열린 RISK 29(부분종결 유지)·code 3+tests 5+docs 6 미커밋(커밋 지시 대기)·push 안 함._

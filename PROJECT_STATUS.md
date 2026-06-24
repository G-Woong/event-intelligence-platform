# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 약하게(추정으로) 연결된 출처가 사건을 발행시키거나 대표가 되던 마지막 구멍을 막고, **입력 순서가 바뀌어도 결과가 똑같도록** 만들었습니다. 약한 연결은 "같은 종류 출처(뉴스+뉴스)"일 때만 "추정" 표시로 발행하고, 종류가 섞이면(공식+뉴스) 보류합니다.
- **이번 턴에 실제로 끝낸 것:** 먼저 ADR#36을 `621d1a3`로 커밋. 이어 **ADR#37 약신호 정책 + 입력순서 불변**: 약신호는 동일 publishable type만 저신뢰 발행, core 선택을 입력순서·키 무관하게 결정적으로. **측정: backend 309 passed/4 skip/0 fail(+9) + ingestion 1331 = 1640 green · frontend tsc0/test12/lint0.** 단위·입력순서 회귀·live-PG로 잠금.
- **결과(adversarial 2-pass):** **R-SourceTypeFidelityGate 완전 종결**(1차 OVERCLAIM→P2-1·P2-2 수정→2차 **JUSTIFIED**). `RISK_CLOSED.md` 이관. **R-FalseMerge는 held 승격 정책 잔여로 open 유지**(ADR#37은 split만 닫음). P1 0·BLOCKED 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `621d1a3`**(ADR#36, 본 턴 첫 커밋) 위 **ADR#37 = 미커밋 code 2 + tests 3 + docs 7**. `machine_status.json` 은 직전 Stop 기준 **stale**(lag).
- code 2: `cross_source_dedup.py`(primary_root=최대 강성분→동률 publishable 우선·members 키 정렬·_PUBLISHABLE_RECORD_TYPES)·`event_resolver.py`(_homogeneous_publishable·약신호 gate). tests 3: `test_event_resolver`(약신호 gate 6)·`test_event_ingest_pipeline`(입력순서 불변 3·drift 1)·`test_event_resolution_live_pg`(+2). docs 7: `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#37)·`_RISK/RISK_REGISTER`(R-SourceTypeFidelityGate 제거·R-FalseMerge gap② 해소)·`_RISK/RISK_CLOSED`(R-SourceTypeFidelityGate)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.
- 열린 RISK **28**(R-SourceTypeFidelityGate **CLOSED**; 신규 0). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (약신호 정책 + 입력순서 불변 — ADR#37)
- **possible_duplicate 동질 publishable gate**: 약신호 cluster 는 **모든 멤버가 동일한 publishable type**(news+news, official+official)일 때만 저신뢰 발행, **혼합(official+news)·비-publishable 섞임은 WITHHELD**. → authority 높은 출처가 약신호 결합으로 다른 type 끌어와 Event 대표화하는 weak-primary 차단(directive 금지조건 충족). 동일 type 은 delta_summary "…같은 사건으로 추정됩니다"로 저신뢰 명시.
- **입력순서 불변 core/gate**: `primary_root`=members[0](인덱스) 대신 **최대 크기 강성분→동률 publishable 우선→키 최소**(전수 기반). `members` 키 정렬로 cluster_id/primary tie-break 입력순서 불변. → fragility(발행/미발행 입력순서 의존) + R-FalseMerge 약신호 cluster_id split 동시 해소. `_PUBLISHABLE_RECORD_TYPES` drift 계약 테스트.
- **검증**: 약신호 gate 6 + 입력순서 불변 3(strong/weak cluster_id permutation·강성분+약신호 주변부·두-강성분 publishable-wins) + drift 1 + live-PG 3. 회귀 0.
- **adversarial 2-pass**: 1차 OVERCLAIM(P2-1 약신호 weak-primary·P2-2 tie-break 자의성) → P2-1 동질 gate·P2-2 publishable-우선 수정 → **2차 JUSTIFIED**.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-SourceTypeFidelityGate: 완전 종결(CLOSED)** — gate(#33)+authority(#34)+held-dedup·fail-closed(#35)+강신호 core-policy(#36)+약신호 정책·입력순서 불변(#37). `RISK_CLOSED.md` 이관. adversarial 2-pass JUSTIFIED.
- **R-FalseMerge: open 유지(갱신)** — 약신호 cluster_id split(gap②)·core→gate fragility는 ADR#37로 **해소**. **held event 중복/승격 정책(gap①)만 잔여** → MEDIUM→LOW open 유지(이번에 닫지 않음).
- **종결 1**(R-SourceTypeFidelityGate). 유지: RealSourceLoop·S2Hardening·ModelMigration·**FalseMerge**·ExpansionPartialFailure·ApiScale.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **R-FalseMerge held 승격 정책**: held member 가 나중에 강신호로 자기 resolution 시 중복 Event 가능 — ADR#37 범위 밖(별개 영역). open 유지.
- **실 cross-source 비뉴스/약신호 Event·실 fetch APPEND·주기 auto-trigger·운영 DB**: R-RealSourceLoopUnproven·S2Hardening open.
- P3(비차단): news+news 약신호 단일 news primary(authority 상향 0·저신뢰 표시) · 비-primary corroborator evidence+held 이중등장(R-FalseMerge held 영역) · delta kind primary-only · official+news 약신호 WITHHELD false-negative(강신호 경로 정상).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: held 승격 정책 설계(중복 Event 방지) · 실 운영 비뉴스/약신호 Event 발생률.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 code 2 + tests 3 + docs 7 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** R-FalseMerge held 승격 정책(held→강신호 self-resolution 중복 Event 방지) → 그 다음 실 cross-source 비뉴스/약신호 Event 관측·실 fetch APPEND·주기 auto-trigger(S2Hardening)·event_cards↔Event 자동연결(ModelMigration).

## 📁 근거 (이번 턴 핵심)
- 코드: `cross_source_dedup.py`(입력순서 불변 core·키 정렬)·`event_resolver.py`(_homogeneous_publishable).
- 검증: 단위(약신호 gate 6·입력순서 불변 3·drift 1)+live-PG 3 — backend 309·ingestion 1331·frontend tsc0/test12/lint0.
- 문서: ADR#37(`_DECISIONS`)·R-SourceTypeFidelityGate CLOSED(`_RISK/RISK_CLOSED`)·R-FalseMerge gap② 해소(`_RISK/RISK_REGISTER`)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-23 · 약신호 정책 + 입력순서 불변(ADR#37) — possible_duplicate 동질 publishable gate(news+news/official+official 저신뢰 발행·혼합/비-publishable WITHHELD → 약신호 weak-primary 차단) + 입력순서 불변 core(primary_root=최대 강성분→동률 publishable 우선·members 키 정렬 → fragility·cluster_id split 해소). 검증 약신호 gate 6+입력순서 불변 3+drift 1+live-PG 3(**backend 309 passed/4 skip/0 fail + ingestion 1331 = 1640 green · frontend tsc0/test12/lint0**). **adversarial 2-pass JUSTIFIED → R-SourceTypeFidelityGate 완전 종결(RISK_CLOSED 이관)**. R-FalseMerge 는 split(gap②) 해소·held 승격(gap①) 잔여로 open 유지. 열린 RISK 28(종결 1)·code 2+tests 3+docs 7 미커밋(커밋 지시 대기)·push 안 함._

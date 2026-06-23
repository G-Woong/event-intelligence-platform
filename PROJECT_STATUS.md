# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 약하게(추정으로) 연결된 출처가 사건의 "대표"가 되거나 사건을 발행시키던 위험을 보수적으로 막았습니다(core-policy). 강하게 검증된 핵심 출처가 발행 불가(커뮤니티/시장)면, 약하게 붙은 공식 출처가 있어도 **발행하지 않습니다**(모호하면 보류).
- **이번 턴에 실제로 끝낸 것:** 먼저 ADR#35를 `e0a0893`로 커밋. 이어 **ADR#36 weak-primary 정책(후보 A core 우선 + C 보류 결합, B 저신뢰발행 기각)**: 강신호 cluster는 **강신호 core**에서만 대표·발행 판정. **측정: backend 298 passed/4 skip/0 fail(+3) + ingestion 1331 = 1629 green · frontend tsc0/test12/lint0.** 단위 3 + live-PG 1로 잠금.
- **정직한 한계(adversarial):** **R-SourceTypeFidelityGate는 여전히 LOW 부분종결**(완전 종결 **OVERCLAIM** 판정). 강신호 weak-primary는 닫았으나 **① 약신호 cluster weak-primary 미해소**(ADR#29 뉴스 흐름 보존 명목 유지)·**② members[0]→core→gate fragility**(두-강성분 브릿지가 입력순서로 발행/미발행 뒤집힘, R-FalseMerge 교차). 그래서 RISK를 닫지 않았습니다. P1 0(코드)·BLOCKED 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `e0a0893`**(ADR#35, 본 턴 첫 커밋) 위 **ADR#36 = 미커밋 code 3 + tests 2 + docs 6**. `machine_status.json` 은 직전 Stop 기준 **stale**(lag).
- code 3: `event_ingest_pipeline.py`(candidate_from_cluster core-policy·core_source_types)·`event_resolution_pipeline.py`(member_source_types=core)·`event_timeline_service.py`(ResolvedCandidate.core_source_types). tests 2: `test_event_ingest_pipeline`(+weak-primary 3)·`test_event_resolution_live_pg`(+1). docs 6: `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#36)·`_RISK/RISK_REGISTER`(부분종결·R-FalseMerge 교차)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.
- 열린 RISK **29**(R-SourceTypeFidelityGate **LOW 부분종결=유지**, 약신호 weak-primary·fragility 잔여; 신규 0). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (weak-primary core-policy — ADR#36)
- **후보 비교·선택**: A(core 우선)+C(WITHHELD 우선) 결합. **B(저신뢰 발행) 기각**(약신호 public 발행 위험·UI 저신뢰 표시 미비; 초기 상용 false-merge>missed-event 보수).
- **구현**: 강신호(duplicate) cluster 는 **강신호 core**(distinct−weak_only)에서만 primary 선정 + gate 입력(`core_source_types`)=core source_type → **weak_only publishable 로 발행 안 함(WITHHELD)·weak_only 는 대표 불가**. 약신호(possible_duplicate)는 전체 동등 저신뢰(ADR#29 뉴스 흐름 보존). `ResolvedCandidate.core_source_types` 신규·`resolve_and_apply_cluster` 가 core 기준 gate(레거시 _cand fallback). 마이그레이션/schema/UI 0.
- **검증**: 단위 3(강 community core+weak official→WITHHELD·강 market core+weak news→WITHHELD·강 news core+weak community→news 대표 발행+community held)+live-PG 1(실 DB). 회귀 0(official+news·news+news·pure-community/structured·fail-closed·held-dedup·corroborator 유지).
- **adversarial 반영**: 완전 종결 **OVERCLAIM** 판정 수용 → **R-SourceTypeFidelityGate 닫지 않음**(부분종결 유지). 잔여(약신호 weak-primary·fragility·비-primary corroborator) 명시·R-FalseMerge 교차 기재.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **약신호 cluster weak-primary**: possible_duplicate 는 core=전체라 authority 높은 weak 멤버(약신호 title-link official)가 여전히 대표·발행 가능. 강신호만 닫음(약신호는 ADR#29 흐름 보존 — 닫으면 검증된 뉴스 약신호 흐름도 죽음). 결정: WITHHELD/저신뢰표시/core 우선 중 ADR 선행 필요.
- **members[0]→core→gate fragility**: 두-강성분 약신호 브릿지 cluster 의 core(=발행 가부)가 입력순서 의존. R-FalseMerge 약신호 split 와 동일 영역(입력순서-불변 회귀 필요).
- 비-primary weak corroborator evidence+held 이중등장(기존)·delta kind primary-only·커스텀 candidate_for fail-open(가드 밖).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 약신호 cluster weak-primary 의 올바른 정책(보수 WITHHELD vs 뉴스 흐름 보존)·two-component fragility 의 실제 발생률·입력순서-불변 보장 방법.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-SourceTypeFidelityGate: LOW 부분종결(유지)** — gate(#33)+authority(#34)+held-dedup·fail-closed(#35)+**강신호 core-policy(#36)**. **완전 종결 아님**(adversarial OVERCLAIM: 약신호 weak-primary 미해소·fragility gate 전이). Closure: 약신호 weak-primary 결정 + 두-강성분 core 입력순서-불변.
- **R-FalseMerge** 잔여 ①②에 ADR#36 부분 해소·core→gate 전이 교차(미종결 유지).
- **종결 0**(부분종결만; 완전 종결 OVERCLAIM 차단). 유지: RealSourceLoop·S2Hardening·ModelMigration·FalseMerge·ExpansionPartialFailure·ApiScale.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 code 3 + tests 2 + docs 6 커밋 여부 지시 대기. push 금지.
2. **[다음 단계 = 약신호 weak-primary + fragility]** ① 약신호 cluster 의 weak-primary 정책 결정(보수 WITHHELD vs 뉴스 흐름 보존·저신뢰 표시, ADR 선행) ② 두-강성분 약신호 브릿지 core 입력순서-불변 회귀(R-FalseMerge 약신호 split 와 함께) → R-SourceTypeFidelityGate 완전 종결. (그 다음) 실 cross-source 비뉴스 Event·실 fetch APPEND·주기 auto-trigger.

## 📁 근거 (이번 턴 핵심)
- 코드: `event_ingest_pipeline.py`(core-policy: 강신호=core·약신호=전체, core_source_types)·`event_resolution_pipeline.py`·`event_timeline_service.py`.
- 검증: 단위 3(`test_event_ingest_pipeline`)+live-PG 1 — backend 298. frontend tsc0/test12/lint0.
- 문서: ADR#36(`_DECISIONS`)·R-SourceTypeFidelityGate LOW 부분종결·R-FalseMerge 교차(`_RISK/RISK_REGISTER`)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-23 · weak-primary core-policy(ADR#36) — 후보 A(core 우선)+C(WITHHELD) 결합·B(저신뢰발행) 기각. 강신호(duplicate) cluster 는 **강신호 core**(distinct−weak_only)에서만 primary 선정 + gate(`core_source_types`)=core source_type → **weak_only publishable 로 발행 안 함·weak_only 대표 불가**(강신호 weak-primary 보수적 해소·R-FalseMerge 강화). 약신호(possible_duplicate)는 전체 동등 저신뢰(ADR#29 뉴스 흐름 보존). 검증 단위 3+live-PG 1(**backend 298 passed/4 skip/0 fail + ingestion 1331 = 1629 green · frontend tsc0/test12/lint0**). adversarial **완전 종결 OVERCLAIM** 판정 → **R-SourceTypeFidelityGate LOW 부분종결 유지(닫지 않음**) — ① 약신호 cluster weak-primary 미해소 ② members[0]→core→gate fragility(입력순서 의존, R-FalseMerge 교차). 열린 RISK 29(부분종결 유지)·code 3+tests 2+docs 6 미커밋(커밋 지시 대기)·push 안 함._

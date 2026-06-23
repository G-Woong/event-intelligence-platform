# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 뉴스가 아닌 출처(공식 공시·커뮤니티·시장 숫자)가 사건(Event)으로 올바르게 다뤄지는지 **검증**했습니다 — 전부 Event로 만드는 게 아니라 **타입에 맞게**(공식→Event, 시장 숫자→신호 유지, 커뮤니티→보류).
- **이번 턴에 실제로 끝낸 것:** 먼저 genesis update를 `7e91def`로 커밋. 이어 비뉴스 검증(코드 변경 0): **결정론 5 시나리오**(실 파이프라인) + **실 fetch**(federal_register 10000·sec_edgar 100·hacker_news 3건 LIVE). 결과 — 공식+뉴스 강신호→**Event 생성**(증거에 official+article 타입 보존)·시장 숫자 단일 스냅샷→**Event 안 됨**(정상=신호 유지)·커뮤니티+뉴스 약신호→**Event(뉴스 주도)+커뮤니티 보류**(오병합 차단). **측정 변화 없음**(이번 턴 테스트 코드 무변경; 직전 게이트 backend 268/ingestion 1331/frontend tsc0 test12 lint0 유지).
- **정직한 발견(gap):** resolver가 **출처 종류를 안 보고 신호 강도로만** 라우팅 → 순수 커뮤니티끼리 겹치거나(강·약신호 모두) **시장 숫자 신호가 같은 라벨로 겹치면 발행 Event가 만들어짐**(설계의 "커뮤니티/신호 단독 발행 금지" 위반; 시장 신호 Event화는 **투자조언 경계**). 코드로 막혀 있지 않음 → **신규 RISK(R-SourceTypeFidelityGate, MEDIUM)**, 비뉴스 소스 운영 발행 전 해소 필요(큰 rule 변경이라 구현은 이월). **adversarial 검증이 이 범위 확장(structured·약신호)을 잡아 반영.** **BLOCKED 0.** push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `7e91def`**(CREATE genesis update, 본 턴 첫 커밋) 위 **비뉴스 검증 = 미커밋 docs 6**(코드 0). `machine_status.json` 은 직전 Stop 시점 기준 **stale**(lag).
- docs 6: `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#32)·`_RISK/RISK_REGISTER`(R-SourceTypeFidelityGate 신규·R-RealSourceLoopUnproven 갱신)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.
- 열린 RISK **29**(R-SourceTypeFidelityGate 신규 +1; 종결 0). throwaway(검증·probe 스크립트)는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (비뉴스 타입 Event 라우팅·fidelity 검증 — ADR#32)
- **전수 분석(3-agent + 정독)**: 설계는 타입별 라우팅을 **명시적으로 다르게** — official→Event(겹침 시), community→hold·never_direct_publish, structured/market/numeric→**signal_only_not_article_card**(Event 금지, 투자조언 금지와 정합), search→never_direct_publish. 파이프라인은 record_type 을 source_group 에서 결정론 파생, sink 는 전체 record 수신, 다운스트림이 source_type 보존 — **비뉴스 완전 배선(미구현 아님)**. Event 형성은 2+ 소스 cross-source 겹침 필수.
- **결정론 검증(실 파이프라인, event_intel_test 7 시나리오)**: S1 official+news 강신호→CREATE(evidence official+article)·S2/S3 structured 단일/비겹침→0 Event·S4 community+news 약신호→CREATE 저신뢰+community HELD(R-FalseMerge)·S5 pure-community 강신호→발행(**gap**)·**S6 structured 동일 signal-key→발행(gap, 투자조언 경계)·S7 pure-community 약신호→발행(gap)**. structured 0 Event 는 게이트 아닌 **비겹침 부수효과**(adversarial 확정).
- **실 fetch(probe, keyless·safe, rate-gate 준수)**: federal_register LIVE 10000·sec_edgar 100·hacker_news 3(http 200, 타입 분류 확인). gdelt 는 429 정책 회피. 단 단일소스 probe→싱글톤→**실 cross-source 비뉴스 Event 미관측**(예상).
- **source-type fidelity**: evidence 가 source_type 끝까지 보존(official/article/community). frontend `EvidenceRow` 가 `(source_type · role)` 렌더. 경미: delta_summary kind 라벨은 primary record_type 만 반영(혼합 클러스터).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 cross-source 비뉴스 Event**: 단일소스 probe 라 공유 식별자 없음→싱글톤. 같은 사건을 2+ 비뉴스 소스가 동시 보도해야(또는 official+news 실 겹침) — 미관측.
- **source-type publish gate**(community/search 단독 발행 차단·primary authority 우선순위): `event_resolver` 큰 rule 변경 → ADR 선행 필요 → **이월**(R-SourceTypeFidelityGate). 이번 턴 코드 무변경.
- **실 fetch APPEND·주기 auto-trigger·운영 DB 배포·full compose E2E**: 이월.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 실 환경에서 비뉴스 cross-source 겹침 빈도·official+news 실 클러스터 형성 가능성·pure-community 겹침의 실제 발생률.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-SourceTypeFidelityGate 신규(MEDIUM)**: resolver type-blind → community/search/**structured** 발행 규칙 미강제. 재현: S5 pure-community 강신호·S6 structured 동일 signal-key(시장 신호 Event화, **투자조언 경계**)·S7 pure-community 약신호 모두 CREATE 발행. 정상: community+news 약신호는 news primary+community HELD(S4). 완화: EVENT_RESOLUTION off 기본·실 운영 뉴스 위주(잠재). Closure: source-type publish gate + authority 우선순위(ADR 선행). **비뉴스 소스 운영 발행 전 선해소 권고.**
- **R-RealSourceLoopUnproven(LOW) 갱신**: 비뉴스 타입 라우팅·fidelity **결정론 입증**(ADR#32)·실 fetch 타입 분류 확인 — 단 **실 cross-source 비뉴스 Event 미관측**이라 완전 종결 아님(부분 진전).
- **종결 0**(검증으로 거동 확인 + gap 발견 → 신규 등재; 닫을 수 있는 것 없음). 유지: S2Hardening·ApiScale·ModelMigration·FalseMerge·ExpansionPartialFailure·RealSourceLoop.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 docs 6 커밋 여부 지시 대기. push 금지.
2. **[다음 단계 후보]** (1) **source-type publish gate**(community/search 단독 cross-source → HOLD/미발행 + primary authority official>news>community, ADR 선행) → (2) 실 cross-source 비뉴스 Event 관측(official+news 실 겹침) → (3) 실 fetch APPEND → (4) full `docker compose up --build` E2E → (5) 주기 auto-trigger.

## 📁 근거 (이번 턴 핵심)
- 검증: 결정론(`.harness/_TRASH/_validate_nonnews.py` throwaway, event_intel_test 5 시나리오) + 실 fetch(`.harness/_TRASH/_probe_nonnews.py` throwaway, `run_api_live_probe`). 코드 무변경.
- 분석: cross_source_dedup(official_id/signal_key 강신호)·eventqueue_dedup(compute_record_key)·run_production_orchestration(`_record_type_for`)·event_resolver(type-blind).
- 문서: ADR#32(`_DECISIONS`)·R-SourceTypeFidelityGate 신규·R-RealSourceLoopUnproven 갱신(`_RISK/RISK_REGISTER`)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-23 · 비뉴스 타입 Event 라우팅·fidelity 검증(ADR#32, 코드 무변경) — 설계는 타입별 라우팅 명시(official→Event·structured/market→signal_only_not_article_card·community/search→never_direct_publish). 결정론 5 시나리오(실 파이프라인)+실 fetch(federal_register 10000·sec_edgar 100·hacker_news 3 LIVE) 검증: official+news→CREATE(evidence official+article)·structured 단일/2종→0 Event(singleton=정상)·community+news 약신호→CREATE 저신뢰+community HELD(R-FalseMerge)·**pure-community 강신호→발행 Event(gap)**. resolver 는 source_type 무관(signal 강도 라우팅) → structured signal-only 는 **게이트 아닌 비겹침 부수효과**(S6 동일 signal-key→발행, 투자조언 경계)·**community/search never_direct_publish 미강제**(S5 강신호·S7 약신호 발행) → **R-SourceTypeFidelityGate 신규(MEDIUM, adversarial 로 범위 확장)**, source-type publish gate 는 큰 rule 변경이라 이월. R-RealSourceLoopUnproven 비뉴스 잔여 부분 진전(결정론 입증·실 cross-source 미관측). 직전 게이트 backend 268/ingestion 1331/frontend tsc0 test12 lint0 유지. 열린 RISK 29(+1)·docs 6 미커밋(커밋 지시 대기)·push 안 함._

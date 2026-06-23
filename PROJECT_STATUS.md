# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 실 검증(ADR#29)에서 드러난 **타임라인 본문이 디버그 라벨**(`"possible_duplicate:..."`)이던 문제를 **LLM 없이 사용자용 자연어 설명**으로 바꿨습니다.
- **이번 턴에 실제로 끝낸 것:** `build_delta_summary`(결정론 template) 신규 — 실경로 `event_ingest_pipeline.candidate_from_cluster` 의 delta_summary 를 자연어로(강신호 distinct≥2: **"서로 다른 뉴스 출처 N곳이 동일 식별자로 같은 사건을 보도했습니다."** / distinct 1: "보도가 동일 식별자로 확인…" / 약신호: "…추정됩니다(자동 병합 전 교차 검토)."). **출처 수는 distinct 근거 수(=evidence 링크 수)와 일치**(과대계수 차단). **측정: backend 268 passed/4 skip/0 fail(+7) + ingestion 1331 = 1599 green · frontend tsc 0/test 12/lint 0.** adversarial 검증 2건(① 종결 과대→부분종결 환원, ② "N곳" 과대계수→distinct 정합) 반영.
- **정직한 한계(adversarial P1-1):** **R-EventTimelineRenderHardening 은 부분종결**(①③ ADR#26 종결, ② **코드 자연어화는 done 이나 실 렌더 미도달**). delta_summary 는 update 행에서만 렌더되는데 실 Event 2건은 **CREATE-only(update 0)** 라 자연어가 **화면에 아직 안 보인다** — 실 fetch APPEND/genesis 전까지 미도달. **BLOCKED 0.** push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `55b839a`**(validation docs, 직전 턴) 위 **본 턴 미커밋 = code 2 + docs 6**. `machine_status.json` 은 직전 Stop 시점으로 **stale**(lag).
- code: `backend/app/services/event_ingest_pipeline.py`(build_delta_summary+candidate_from_cluster)·`backend/tests/test_event_ingest_pipeline.py`. docs 6: `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#30)·`_RISK/RISK_REGISTER`(R-EventTimelineRenderHardening 부분종결)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.
- 열린 RISK **29**(R-EventTimelineRenderHardening 은 **부분종결=유지**, ② 실 렌더 잔여; 신규 완전종결 0). R-RealSourceLoopUnproven(LOW) ⑦ 코드 가독 해소·가시화 잔여.

## ✅ 이번 턴에 달성한 것 (delta_summary deterministic 자연어화 — ADR#30)
- **`build_delta_summary(confidence, reason, member_count, record_type)` 신규**: resolver 가 확인한 사실(교차 출처 신호 강도·distinct 근거 수·출처 종류)만 사용자용 자연어로. **LLM/network 0.** 강신호=`보도했습니다`(단정, distinct≥2만 "서로 다른 N곳")·약신호=`추정됩니다(자동 병합 전 교차 검토)`(헤지). 과장 표현("확정/사실/검증 완료") 금지. 원문 본문/허위/투자판단 미생성(사건 *내용* 은 canonical_title; 전문 저장 금지 원칙).
- **candidate_from_cluster 적용**: `f"{confidence}:{reason}"` 디버그 라벨 대체. **member_count=`len(distinct_members)`**(evidence 링크 수와 일치 — adversarial P2-1: 동일 URL collapse 시 "N곳" 과대표현 차단).
- **검증**: 단위 7+(강신호 distinct≥2/1·약신호·출처종류 4·미지 fallback·원시 enum 누출 미탐·과장표현 금지) + 통합(약신호 멀티소스=실 코스피/대우건설 동형) + **live-PG 결정론**(강신호 CREATE→APPEND → 실 update 자연어). 변경 표면 회귀 0.
- **adversarial 2건 반영**: P1-1(② 완전 종결 과대 → 부분종결: 실 렌더 미도달 명시) · P2-1(member_count distinct 정합) · P2-2(`_is_debug_label` 을 원시 enum 누출 탐지로 강화).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **② 실 렌더 도달**: CREATE-only Event 는 update 0 → 자연어 delta_summary 화면 미표시. 실 fetch APPEND 또는 **CREATE genesis update** 필요.
- **CREATE genesis update**: 가시화하려면 `apply_routing` "CREATE는 update 0" 불변식(ADR#16/#19, 다수 테스트) + 시맨틱 변경 = 큰 설계 → ADR#30 이월 + R-RealSourceLoopUnproven closure.
- **실 fetch APPEND·비-뉴스 타입 Event·주기 auto-trigger·운영 DB·full compose E2E**: 이월.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: CREATE genesis 설계(불변식 영향)·실 fetch APPEND 거동·CREATE-only Event 의 화면 가독성.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-EventTimelineRenderHardening: 부분종결(유지)** — ①③(ADR#26 Public* 스키마·error.tsx, 실데이터 비의존) 종결 + ② **코드 자연어화 done**(ADR#30, 실경로 `event_ingest_pipeline`). **잔여(②): 실 렌더 도달**(CREATE-only update 0 → 화면 미표시; adversarial P1-1). Closure: 실 fetch APPEND/genesis 에서 자연어 화면 렌더 1회 관측.
- **R-RealSourceLoopUnproven(LOW) 유지**: ⑦ delta_summary **코드** 가독 해소; 가시화(genesis)·실 fetch APPEND·비-뉴스 타입·auto-trigger 잔여.
- **신규 완전종결 0**(거짓 종결 0 — adversarial 이 ② 과대 종결을 잡아 부분종결로 환원). 유지: S2Hardening·ApiScale·ModelMigration·FalseMerge·ExpansionPartialFailure.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 code 2 + docs 6 커밋 여부 지시 대기. push 금지.
2. **[다음 단계 = CREATE genesis evidence 가시화]** 실 Event 가 화면에서 evidence/자연어 변화설명을 보이게: ① CREATE 시 genesis update(불변식·테스트·멱등 영향 ADR 선행) 또는 ② genesis evidence 를 Event 자체에 두는 스키마. → R-EventTimelineRenderHardening② + R-RealSourceLoopUnproven 잔여 해소.
3. (그 다음) 실 fetch APPEND 관측·비-뉴스 타입 Event·주기 auto-trigger·full compose E2E.

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/app/services/event_ingest_pipeline.py`(`build_delta_summary` distinct 정합)·`backend/tests/test_event_ingest_pipeline.py`.
- 검증: live-PG 강신호 CREATE→APPEND → event_intel_test 실 update 자연어(throwaway `.harness/_TRASH/`).
- 문서: ADR#30(`_DECISIONS`)·R-EventTimelineRenderHardening 부분종결(`_RISK/RISK_REGISTER`)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-23 · delta_summary deterministic 자연어화(ADR#30) — `build_delta_summary`(LLM 0)가 실경로 `event_ingest_pipeline.candidate_from_cluster` 의 delta_summary 를 디버그 라벨(`"{confidence}:{reason}"`)에서 사용자 자연어로 교체(강신호 distinct≥2=`서로 다른 출처 N곳…`·distinct1=`보도가 동일 식별자로 확인…`·약신호=`…추정(자동 병합 전 교차 검토)`). member_count=distinct(evidence 수 정합, adversarial P2-1). live-PG 강신호 CREATE→APPEND 자연어 확인. **R-EventTimelineRenderHardening 부분종결**(①③ ADR#26 종결·② 코드 done·**실 렌더 도달 잔여**: CREATE-only update 0 → 화면 미표시, adversarial P1-1). 측정 **backend 268 passed/4 skip/0 fail(+7) + ingestion 1331 = 1599 green · frontend tsc0/test12/lint0.** **CREATE genesis update(가시화)는 불변식 변경이라 이월.** 열린 RISK 29(부분종결 유지)·code 2+docs 7 미커밋(커밋 지시 대기)·push 안 함._

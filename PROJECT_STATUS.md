# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 지난 턴에 만든 "같은 사건일 수 있다" 후보 연결선을 **처음으로 읽어서 판정**하는 계층을 깔았습니다. 두 사건의 제목·시점·출처·언어를 보고 `같은 사건 유력 / 모호 / 다른 사건 유력 / 판단 불가` 라벨을 붙여 쌓습니다 — **단, 자동으로 합치지는 않습니다**(shadow=그림자 평가). 합치기는 평가셋과 실측 정밀도가 확보된 뒤에만 허용합니다.
- **이번 턴에 실제로 끝낸 것:** ADR#41 커밋(`c562186`) → **ADR#42 구현**: `semantic_identity_adjudicator.py` + 신규 `event_identity_adjudication` 테이블(alembic 0009). 연결선(possible-link)을 소비해 4종 status 산출·누적(idempotent). **자동 병합/APPEND 0·API 미노출**. 측정: **backend 비-live 321p/4s · live-PG 45p · ingestion 1353p · frontend tsc0/test12/lint0**.
- **정직한 한계:** 이 판정은 **deterministic heuristic 출력**이라 자기 정밀도를 스스로 측정할 수 없고(=평가셋 필요), **실제 중복 사건 수는 1건도 줄지 않습니다**(병합 안 함). 한국어 토큰 임계 캘리브레이션도 미이행 — 그래서 **R-SemanticIdentityAdjudicator는 OPEN(부분 진전)**, 평가셋 부재를 **R-IdentityEvalDataset(신규)**로 등록. 판정 테이블 소비처도 아직 0(report 휘발성). push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `c562186`**(ADR#41, 본 턴 첫 커밋) 위 **ADR#42 = 미커밋 code 2 + tests 3 + migration 1 + docs 9(신규 파일 3: 0009·semantic_identity_adjudicator·test_semantic_identity_adjudicator)**.
- code: `semantic_identity_adjudicator(신규: build_features/classify/adjudicate/persist/report)`·`event_resolution(EventIdentityAdjudicationORM·ADJUDICATION_STATUSES)`. migration: `0009_event_identity_adjudication`. tests: 신규 `test_semantic_identity_adjudicator`(18)·`test_event_resolution_live_pg`(+adjudicator 5)·`test_event_timeline_service`(chain 0009). docs: ADR#42·RISK_REGISTER(R-SemanticIdentityAdjudicator 갱신·R-IdentityEvalDataset 신규)·EVENT_SCHEMA·CANONICAL/02·RAG_KG_AGENT_READINESS·INTELLIGENCE_UNIT_CONTRACT·ROADMAP{00,15}·PROJECT_STATUS.
- 열린 RISK: R-SemanticIdentityAdjudicator **부분 진전 유지**(open) · **R-IdentityEvalDataset 신규**(open) · R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (semantic adjudicator shadow/eval — ADR#42)
- **① ADR#41 커밋**: 19파일 → `c562186`(secret PASS·docs_lifecycle 0·closeout 검증 후, push 0).
- **② deterministic adjudicator shadow 계층**(소비처 #1): `semantic_identity_adjudicator.py` 가 `event_links(possible, semantic_cross_batch_candidate)` 를 소비 → deterministic feature(title Jaccard·date_distance·source_type·multiple_candidates·언어·generic 토큰) → `classify_identity_candidate`(보수 순서: unknown fail-closed→non_publishable→**multiple_candidates ambiguous**→no_title/generic→far_date→likely_same→borderline) → status 4종 → 신규 `event_identity_adjudication(link_id PK→event_links FK RESTRICT, alembic 0009)` idempotent upsert + `generate_shadow_adjudication_report`(by_status/by_language).
- **③ 핵심 안전 계약**: **자동 병합/APPEND 0**(events/event_updates/cluster_event_map 미변경·read+adjudication write only — 구조 테스트로 잠금)·**API 미노출**(shadow)·source role guard(community/market/catalog-only·unknown→insufficient/fail-closed)·future embedding/LLM `semantic_score` slot(현재 None).
- **adversarial 평결(동일 critic)**: safety(병합 0·API 누수 0·idempotent·source guard·우회 0) **전부 JUSTIFIED·HIGH 결함 0**. **반영한 개선 3**: ① classify 순서 multiple_candidates 우선(모호 신호 보존) ② language_hint 를 report by_language 로 소비(inert 해소) ③ 한국어 likely_same/partial 단위 테스트.

## 🧭 cross-batch identity 4단계 (정직)
- ① 확정 anchor 병합(`event_identity_map`, ADR#40·실 병합) → ② fingerprint 후보 LINK(`event_identity_candidate`, ADR#41·병합 아님) → ③ **deterministic shadow 판정**(`event_identity_adjudication`, ADR#42·**병합 아님·자동 병합 0**) → ④ semantic **실 병합**(embedding/LLM/KG·**미구현**).
- **⚠ 미해소(OPEN):** ③은 라벨만 — **중복 Event count 1건도 미감소**. 실 병합(④)·labeled 평가셋·한국어 캘리브레이션·embedding/LLM 미구현. adjudication 테이블 소비처도 0(report 휘발성). "shadow substrate 추가"를 "중복 해결"로 오기록 금지.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=반응 layer·market=signal·catalog=catalog_metadata entity enrichment·search=URL 후보·unknown=fail-closed. adjudicator도 community/market/catalog-only·unknown→insufficient(likely_same 후보 불가).
- **제품 계약(raw≠public)**: `INTELLIGENCE_UNIT_CONTRACT.md §4` semantic identity status 4단계 갱신. IU 합성기는 ③ shadow status 를 신뢰도 신호로 받되 병합은 ④ 전까지 금지. raw source 직노출 금지·Event=substrate·public=Intelligence Unit(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분 진전: R-SemanticIdentityAdjudicator**(gap① deterministic shadow consumer 부분 해소·②실병합 ③한국어 캘리브레이션 ④평가셋 ⑤테이블 소비처 0 OPEN; severity MEDIUM·**종결 금지**·완전종결=OVERCLAIM).
- **신규 등록: R-IdentityEvalDataset**(MEDIUM, OPEN) — self-labeled status 라 precision 측정 불가 → labeled identity pair set 필요. **실 병합 허용 판단의 선결**.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 병합(중복 count 감소)**: embedding/LLM/KG adjudicator + labeled 평가셋 필요·미구축. shadow status 는 그 입력.
- **한국어 fingerprint 캘리브레이션**: ADR#42 가 임계 상속(이월 약속 미이행)·한국어 likely_same 단위 테스트만 추가. stopword 영어전용 잔여.
- **adjudication 결과 소비처**: report 휘발성(persist 안 함)·API 미노출 → dead-data 한 단계 미룸(shadow substrate 로서만 정당).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- UNKNOWN: 실 병합 허용 기준(labeled precision 임계·한국어 캘리브레이션·shadow 누적) → R-IdentityEvalDataset 선결. fragment-strip same-URL 모니터링(ADR#40 잔여).

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#42 code 2 + tests 3 + migration 1 + docs 9 (총 15파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** R-IdentityEvalDataset(labeled identity pair set + precision/recall 측정) → embedding/LLM/KG **실 병합** adjudicator(중복 count 감소 입증·한국어 캘리브레이션) → 실 cross-source 비뉴스 Event·주기 auto-trigger·RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `c562186`(ADR#41). 코드: `semantic_identity_adjudicator`·`event_identity_adjudication`(0009).
- 검증: backend 비-live **321p/4s** · live-PG **45p**(adjudicator 5) · ingestion **1353p** · frontend tsc0/test12/lint0.
- 문서: ADR#42(`_DECISIONS`)·R-SemanticIdentityAdjudicator 부분진전+R-IdentityEvalDataset 신규(`_RISK/RISK_REGISTER`)·`EVENT_SCHEMA`(event_identity_adjudication)·`INTELLIGENCE_UNIT_CONTRACT §4`·`RAG_KG_AGENT_READINESS §4`·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-24 · ADR#42 semantic identity adjudicator shadow/eval — 신규 `semantic_identity_adjudicator.py`(possible-link 소비처 #1)·`event_identity_adjudication`(alembic 0009, link_id PK→event_links FK RESTRICT)·deterministic feature→status(likely_same/ambiguous/likely_different/insufficient)·idempotent upsert·by_status/by_language report. **자동 병합/APPEND 0**(events/updates/map 미변경·read+adjudication write only)·**API 미노출**·source role guard(non-publishable/unknown→insufficient). adversarial JUSTIFIED(safety 단단·HIGH 결함 0)·개선 3 반영(classify 순서·language 소비·한국어 테스트). **정직 잔여**: 실 병합 0(중복 count 미감소)·한국어 캘리브레이션 미이행·labeled 평가셋 0·adjudication 소비처 0. **R-SemanticIdentityAdjudicator 부분 진전(OPEN)·R-IdentityEvalDataset 신규 등록**·완전종결=OVERCLAIM. **backend 비-live 321p/4s · live-PG 45p · ingestion 1353p · frontend tsc0/test12/lint0**. ADR#41 커밋 `c562186` 위 ADR#42 미커밋(code 2+tests 3+migration 1+docs 9=15파일)·커밋 지시 대기·push 안 함._

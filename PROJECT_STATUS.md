# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** "같은 사건이 서로 다른 기사(다른 URL)로 다른 배치에 들어와 중복 사건으로 쪼개지는" 문제를, **LLM 없이 결정론으로 '같은 사건일 수 있다' 후보를 표면화**하는 하부를 깔았습니다. 단 — **자동으로 합치지는 않습니다**(잘못 합치면 더 위험). 합치는 건 미래의 의미판정기에게 넘기고, 지금은 "후보 연결선"만 안전하게 그어둡니다.
- **이번 턴에 실제로 끝낸 것:** ADR#40 커밋(`ffce7f5`) → **ADR#41 구현**: 신규 `event_identity_candidate` 테이블(alembic 0008) + 제목 토큰셋·날짜 기반 결정론 fingerprint + 같은 fingerprint 후보를 `event_links(possible)`로 **연결만**(병합 0 = 오병합 위험 0). 제품 계약 문서 `INTELLIGENCE_UNIT_CONTRACT.md` 신설. 측정: **backend 비-live 303p/4s · live-PG 40p · ingestion 1353p · frontend tsc0/test12/lint0**.
- **정직한 한계:** 이번 작업은 **중복 사건 수를 1건도 줄이지 않습니다**(연결선만 긋고 실제 병합은 안 함). 진짜 병합·패러프레이즈/다국어 동일성은 의미판정기(임베딩/LLM/KG, 미구축)가 필요 — **R-CrossBatchEventIdentity는 OPEN 유지**, 실 병합 잔여를 **R-SemanticIdentityAdjudicator(신규)**로 분리. 연결선은 현재 읽는 소비처가 0(미래 substrate). push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `ffce7f5`**(ADR#40, 본 턴 첫 커밋) 위 **ADR#41 = 미커밋 code 5 + tests 4 + migration 1 + docs 9(신규 파일 3: 0008·INTELLIGENCE_UNIT_CONTRACT·test_semantic_identity_fingerprint)**.
- code: `cross_source_dedup(semantic_identity_fingerprint)`·`event_ingest_pipeline(semantic_fingerprints)`·`event_resolution_pipeline(semantic 후보 LINK)`·`event_timeline_service(find/map candidate·claim)`·`event_resolution(EventIdentityCandidateMapORM)`. migration: `0008_event_identity_candidate`. tests: `test_event_ingest_pipeline`(+semantic 11·_FakeSession candidate)·`test_event_resolution_live_pg`(+semantic 4)·`test_event_timeline_service`(chain 0008)·신규 `test_semantic_identity_fingerprint`(11). docs: ADR#41·RISK_REGISTER·EVENT_SCHEMA·RAG_KG_AGENT_READINESS·CANONICAL/02·ROADMAP{00,15}·PROJECT_STATUS·신규 `INTELLIGENCE_UNIT_CONTRACT.md`.
- 열린 RISK: R-CrossBatchEventIdentity **부분종결 진전 유지**(open) · **R-SemanticIdentityAdjudicator 신규 등록**(open). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (semantic 후보 substrate — ADR#41)
- **① ADR#40 커밋**: 23파일 → `ffce7f5`(secret PASS·docs_lifecycle 0·closeout EXACT MATCH 검증 후, push 0).
- **② deterministic semantic cross-batch 후보 층**: 신규 `event_identity_candidate(candidate_key→event_id, alembic 0008, FK RESTRICT)` — `event_identity_map`(확정 anchor)과 **분리**. `semantic_identity_fingerprint(title, observed_at)`=normalized token-set(어순무관·stopword 제거)+date bucket→`sem:{sha1}`(유의미 토큰<4 generic·시점불명은 None — 고정밀·저재현). publishable core 멤버만 fingerprint. 미매핑 cluster 가 strong/held 승격에 안 잡히고 fingerprint **정확히 1개** Event 면 → CREATE 후 `event_links(possible, reason='semantic_cross_batch_candidate')` **LINK 만**, 모호(2개+)·result≠CREATE 면 링크 안 함.
- **③ 핵심 안전 결정(false-merge 회피)**: directive §6 시나리오3의 "APPEND 또는 HOLD_REVIEW" 중 — R-FalseMerge 가 cardinal sin 이라 **자동 APPEND(병합) 절대 금지, LINK 만**. false-merge surface 0.
- **④ Intelligence Unit 계약**: 신규 `INTELLIGENCE_UNIT_CONTRACT.md`(raw≠public·source role·entity/semantic identity hook). R-SemanticIdentityAdjudicator 신규 등록.
- **adversarial 평결(동일 critic)**: safety(false-merge 0·source role 우회 0·공개표면 누수 0·strong/held 우선순위·멱등) **전부 JUSTIFIED**. 정직성 의무 3건(중복 count 미감소 병기·LINK 소비처 0·한국어 4-임계 캘리브레이션 부재) docs 반영. same-batch 동일-fingerprint 다중 cluster 는 clustering 약신호 병합으로 **구조적 불가**(구조 테스트 잠금). live-PG 갭은 실 4-test 통과로 해소.

## 🧭 cross-batch identity — 닫힌 범위 vs 미해결(정직)
- **닫힌 범위(병합, ADR#40):** publishable core 가 **동일 canonical_url/official_id** 재등장(syndicated wire)→기존 Event APPEND(실 병합·분열 0). live-PG.
- **닫힌 범위(후보, ADR#41):** **공유 anchor 없는** 같은 token-set+같은 날 publishable 후보를 `event_links(possible)`로 **표면화**. live-PG.
- **⚠ 미해결(OPEN):** ADR#41 은 **LINK 만 — 중복 Event count 1건도 미감소**(실 병합 아님). 패러프레이즈/동의어/다국어/엔티티 동일성·실 병합은 **R-SemanticIdentityAdjudicator**(임베딩/LLM/KG·미구현). "후보 substrate"를 "중복 해결"로 오기록 금지.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=반응 layer(비발행)·market=signal(비발행)·catalog=catalog_metadata entity enrichment(비발행)·search=URL 후보·unknown=fail-closed. semantic fingerprint 도 **publishable core 만**(community/market/catalog/search/약신호 제외).
- **제품 계약(raw≠public)**: 단일 출처 `INTELLIGENCE_UNIT_CONTRACT.md` 신설 — raw source 직노출 금지·Event=substrate·public=Intelligence Unit(Agent/RAG/KG/LLM 정제, 미구축). 코드로 강제(publish gate+catalog fidelity+cross-batch identity/candidate+held).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분종결 진전: R-CrossBatchEventIdentity**(ADR#41 semantic 후보 substrate 추가; **단 중복 count 미감소·OPEN 유지**).
- **신규 등록: R-SemanticIdentityAdjudicator**(MEDIUM, OPEN) — possible-link 실 병합으로 중복 감소가 closure. 분리가 R-CrossBatchEventIdentity 종결 구실 아님(ADR#41 논거 선행).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **cross-batch 실 병합(count 감소)**: semantic adjudicator(임베딩/LLM/KG) 필요·미구축. possible-link 는 그 입력 substrate.
- **한국어 fingerprint 캘리브레이션**: 어절 토큰화 4-임계는 언어별 근거 부재(재현율 위험) → adjudicator 단계 이월.
- **실 fetch APPEND·실 cross-source 비뉴스 Event·주기 auto-trigger·운영 DB 0008 배포**(검증=event_intel_test).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- UNKNOWN: semantic 실 병합 기준(entity+time+domain vs embedding — eval/cost/citation/shadow) → R-SemanticIdentityAdjudicator ADR 필요. fragment-strip same-URL=다른 사건 모니터링(ADR#40 잔여).

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#41 code 5 + tests 4 + migration 1 + docs 9 (총 19파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** cross-batch **semantic adjudicator**(embedding/LLM/KG 실 병합·shadow eval·중복 count 감소 입증 — R-SemanticIdentityAdjudicator). 그 다음 실 cross-source 비뉴스 Event·주기 auto-trigger·RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `ffce7f5`(ADR#40). 코드: `event_identity_candidate`(0008)·`semantic_identity_fingerprint`·find/map candidate·semantic LINK.
- 검증: backend 비-live **303p/4s** · live-PG **40p**(semantic 4) · ingestion **1353p**(fingerprint 11) · frontend tsc0/test12/lint0.
- 문서: ADR#41(`_DECISIONS`)·R-CrossBatchEventIdentity 진전+R-SemanticIdentityAdjudicator(`_RISK/RISK_REGISTER`)·`EVENT_SCHEMA`(event_identity_candidate)·`INTELLIGENCE_UNIT_CONTRACT`(신규)·`RAG_KG_AGENT_READINESS §4`·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-24 · ADR#41 deterministic semantic cross-batch identity 후보 substrate — 신규 `event_identity_candidate`(alembic 0008, `event_identity_map` 와 분리)·`semantic_identity_fingerprint`(token-set+date·generic/시점불명 None)·publishable core fingerprint→**정확히 1개 후보면 `event_links(possible)` LINK 만**(자동 병합 0 = false-merge surface 0·**중복 Event count 미감소**)·모호→링크 0. adversarial JUSTIFIED(safety 단단)·정직성 3건(count 미감소·LINK 소비처 0·한국어 4-임계 캘리브레이션) 반영. **R-CrossBatchEventIdentity 부분종결 진전(OPEN 유지)·R-SemanticIdentityAdjudicator 신규 등록**. Intelligence Unit 계약 명문화(`INTELLIGENCE_UNIT_CONTRACT.md`). **backend 비-live 303p/4s · live-PG 40p · ingestion 1353p · frontend tsc0/test12/lint0**. ADR#40 커밋 `ffce7f5` 위 ADR#41 미커밋(code 5+tests 4+migration 1+docs 9=19파일)·커밋 지시 대기·push 안 함._

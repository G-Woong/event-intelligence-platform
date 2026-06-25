# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 지난 턴 만든 도구(ADR#56)를 안정 기준점으로 **커밋**한 뒤, "합성(가짜) 재생이 아니라 **진짜 소스**에서 같은 사건이 여러 매체에 겹쳐 나오는지" 측정하는 도구를 만들었습니다. 그리고 그 겹침을 **두 종류**로 갈랐습니다 — 컴퓨터가 정확히 잡는 겹침(제목 단어가 토씨까지 같음)과, **사람 표현이 달라 컴퓨터가 못 잡는 겹침**(같은 사건인데 문장이 다름).
- **이번 턴에 실제로 끝낸 것:** ADR#56 커밋(`9e16c44`) → **ADR#57**: `source_overlap_discovery`(DB·병합 없이 측정만). **진짜 GDELT(무료 뉴스 집계) fetch 를 시도했으나 429(요청 제한)** 로 막혀, 미리 만든 **소독된 샘플**(본문 미저장)로 측정 — 같은 사건 겹침 6쌍 중 **컴퓨터가 정확히 잡는 건 1쌍(토씨까지 동일)뿐, 5쌍은 표현이 달라 못 잡음**(향후 LLM/임베딩 영역). 즉 "진짜 소스 겹침이 왜 자동으로 안 묶이나"를 **수치로 분해**했습니다.
- **정직한 한계:** **진짜 소스 겹침은 아직 관측 못 했습니다**(GDELT 429). 샘플은 합성이라 진짜 소스 동작이 아닙니다. **production 백로그 0·운영 DB 무변경·실 gold/reviewer/병합 0·LLM/Agent 본경로 0(No-Go)·자동 병합 0** 불변. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `9e16c44`**(ADR#56, 본 턴 첫 커밋) 위 **ADR#57 = 미커밋**: 신규 2(`source_overlap_discovery.py` + `test_source_overlap_discovery.py`) + 수정 2(`real_source_smoke_report.py` §8 + `test_real_source_smoke_report.py`) + docs 8(PROJECT_STATUS 포함) = **변경 12파일**. **migration 없음·신규 코드 1파일(도구)·신규 테스트 1파일.**
- 수정/신규: `backend/app/tools/{source_overlap_discovery[신규],real_source_smoke_report}.py`·`backend/tests/{test_source_overlap_discovery[신규],test_real_source_smoke_report}.py` + docs 8(`2_ROADMAP/00·15`·`_RISK/RISK_REGISTER`·`5_REFERENCE/RAG_KG_AGENT_READINESS·INTELLIGENCE_UNIT_CONTRACT`·`_CANONICAL/02`·`_DECISIONS/2026-06`·`PROJECT_STATUS`).
- 열린 RISK: **R-RealSourceLoopUnproven 부분진전(실 cross-source overlap 다입도 분해·GDELT 429 실측)** · **R-LiveIdentityBacklog 부분진전(백로그 충원 source 구조적 희소성 분해)** · **R-SourceOverlapScarcity 신규(MEDIUM·key-free 실 cross-source overlap 구조적 희소)** · R-SemanticIdentityAdjudicator · R-IdentityEvalDataset · R-IdentityHumanLabeling · R-ReviewerAgreement · R-GoldSamplingBias · R-CrossBatchEventIdentity(open). **신규 RISK 1·종결 0.** throwaway는 `.harness/_TRASH/`·`frontend/.harness/`(gitignored).

## ✅ 이번 턴에 달성한 것 (source overlap discovery — ADR#57)
- **① ADR#56 커밋**: 13파일 → `9e16c44`(secret PASS·docs_lifecycle conflicts 0·closeout SIGNATURE MATCH 16·push 0).
- **② 원자 분석(§2·20문항)**: substrate 정독(file:line) + 2-agent 소스 레지스트리·fetch 인프라 조사. **핵심 통찰**: cross-batch identity 는 `semantic_identity_fingerprint`(**정확 token-set 일치 + date bucket**·≥4 토큰·고정밀 저재현)만 인정 → 실제 다른 매체의 같은 사건 헤드라인은 paraphrase 되어 **overlap 이 존재해도 deterministic fingerprint 사각지대**. key-free 검증 anchor=federal_register 단 1·**GDELT 만 다출처 same-event overlap 생성(429 제약)**·공식↔공식 1문서=1URL=1event 비중첩·community=reaction layer·뉴스 HTML 미allowlist.
- **③ 옵션 결정(ADR#57)**: **A 채택**(real same-event discovery probe·GDELT bounded opt-in) + **B 채택**(overlap planning matrix·agent schema) + **C 부분채택**(GDELT timespan 시점창·실패 시 분류). **D docs/schema only**(near_match_below_fingerprint 로 LLM/adjudicator 영역 명문화·실 LLM 호출 0)·**E(production) 금지**.
- **④ source_overlap_discovery.py**(write-free·no-DB·**no-merge**): `discover_overlap`(다입도 pairwise — `fingerprint_overlap`[deterministic 검출→교차배치 시 `semantic_cross_batch_candidate`] vs `near_match_below_fingerprint`[paraphrase→adjudicator/embedding/LLM 영역·gated]·`possible_same_event_pairs`·`overlap_potential_matrix`·`block_reasons`)·`build_captured_overlap_fixture`(옵션 C sanitized·**본문 미저장**)·`parse_gdelt_articles`/`fetch_gdelt_overlap_records`(GDELT bounded·key-free·transport 주입 결정론·실패 분류)·`build_agent_orchestration_schema`(§9·`no_merge_without_gate`·`no_public_intelligence_unit`·`llm_invoked=False`).
- **⑤ 측정(실데이터·정직)**: **실 GDELT bounded fetch 시도(`--live-gdelt`·timespan=7d) → `rate_limited`(429·R-Gdelt429 발현) → captured fixture fallback**(`real_fetch=False` 표면화). captured fixture: **possible_same_event 6 = fingerprint 1(verbatim wire) + near 5(paraphrase)** → deterministic 은 **1/6 만 검출**·5/6 은 adjudicator-zone. **즉 실 cross-source overlap 의 다수는 결정론 사각지대.**
- **⑥ §8 source quality matrix 보강**: `build_source_quality_matrix` 에 overlap_potential·same_event_discovery_utility·time_series_update_utility·agent_utility·community_reaction_layer_eligible·official_confirmation_utility·market_signal_utility·catalog_entity_enrichment_utility·identity/adjudication/packet_failure_reason 추가 → Agent 가 source 별 처리전략(merge_anchor/reaction_layer/market_signal/entity_enrichment) 선택할 substrate.
- **⑦ 감사 반영**: adversarial-reality-critic **PROCEED·HIGH 0**(honesty boundary HOLDS) / code-review **LOW 1건 수정**(`adjudication_failure_reason` 가 publishable-no-canonical 을 `non_publishable_role` 로 오분류 → `no_canonical_anchor` 로 정정·회귀 테스트 추가).

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·운영 배선 ADR#48~#53·activation preflight+smoke ADR#54·real-source live-db smoke ADR#55·time-series replay substrate ADR#56·**source overlap discovery ADR#57**) → ④ 실 병합(**미구현**).
- **ADR#57 위치**: discovery 는 ②/③의 *입력*(실 cross-source overlap)이 구조적으로 얼마나 희소한지 **write-free 로 측정**. deterministic(②③)이 잡는 overlap = verbatim only·paraphrase overlap 은 ④ 직전 adjudicator(embedding/LLM·MERGE_GATE·gold) 영역.
- **⚠ 미해소(OPEN):** 실 GDELT overlap(429)·실 동일사건 다중소스/시계열 fetch·운영 DB 0009 배포·실 병합·실 gold·reviewer 합의·한국어 캘리브레이션·MERGE_GATE. "discovery(능력) ≠ 실 운영 overlap(actuality)" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence(merge anchor)·community=반응 evidence(anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed. discovery 의 pairwise overlap 은 publishable(official/article) pair 만 anchor 후보·community/market/catalog 는 제외(role guard·matrix `guard_only`).
- **제품 계약(raw≠public)**: discovery 는 Intelligence Unit **merge safety substrate** 의 write-free 측정(자동 병합 0·**본문 미저장**·public API 미노출). Agent 는 overlap discovery 를 *주관/계획* 할 수 있으나(`build_agent_orchestration_schema`·recommended_source_pairs·next_fetch_plan) **MERGE_GATE·gold 없이 병합/public IU 생성 금지**(`no_merge_without_gate`·`no_public_intelligence_unit`·`llm_invoked=False`). LLM/Agent 진입 9조건 여전히 No-Go(1·4·5·7).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전: R-RealSourceLoopUnproven**(실 cross-source overlap 다입도 수치 분해·실 GDELT 시도→429 실측·"왜 안 닫히는가"를 source/fingerprint/coverage/provider 귀속) + **R-LiveIdentityBacklog**(백로그 충원 source 의 구조적 희소성 분해).
- **신규: R-SourceOverlapScarcity(MEDIUM)** — key-free 실 cross-source same-event overlap 의 구조적 희소(공식 비중첩·paraphrase fingerprint 사각지대·GDELT 429·뉴스 HTML 미allowlist). **측정 기반 실 blocker**(미래 희망 아님·adversarial JUSTIFIED). 중첩 RISK 와 경계 명시(R-RealSourceLoopUnproven=제품 통합·R-SemanticIdentityAdjudicator=검출 영역·R-Gdelt429=provider). 종결 0·신규 1.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 cross-source overlap 관측**: GDELT 429(R-Gdelt429)로 실 fetch 막힘 → captured fixture(합성)로 substrate 만 측정·실 source 아님. (다음 hard blocker — GDELT 429 우회[host-gate·재시도] 또는 key-free 뉴스 RSS/HTML allowlist 확장.)
- **paraphrase overlap 검출**: deterministic fingerprint 는 verbatim 만 → 5/6 overlap 은 미검출. 검출은 embedding/LLM adjudicator(MERGE_GATE·gold) 영역·미구축(R-SemanticIdentityAdjudicator).
- **운영 production 백로그**: 운영 DB 0009 배포(승인 필요·옵션 E 금지) + 실 fetch 볼륨 필요 → production 0.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 실 cross-source overlap = GDELT provider 429(R-Gdelt429) + source 커버리지 선결. 운영 production 백로그 = 운영 DB 0009 배포(승인) + 실 fetch 볼륨.
- UNKNOWN: paraphrase overlap 의 실 병합 허용 기준(production precision·실 gold·reviewer 합의·한국어 캘리브레이션·MERGE_GATE) → R-SemanticIdentityAdjudicator·R-IdentityHumanLabeling·R-ReviewerAgreement·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#57: 신규 2(도구+테스트) + 수정 2(report+test) + docs 8 = 12파일 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** (a) **실** GDELT overlap 확보(host-gate 배선·재시도 정책·또는 key-free 뉴스 RSS/HTML allowlist 확장) → discovery 가 `real_fetch=True 로 deterministic-detectable overlap ≥1` 산출 → live-db escalation 으로 실 `semantic_cross_batch_candidate` 누적 → (b) (승인 하) 운영 DB 0009 배포 + `APP_ENV=production` + flag on + scheduler 가동 → (c) reviewer 합의 gold + 한국어 캘리브레이션 → (d) embedding/LLM/KG **실 병합** adjudicator(paraphrase overlap·MERGE_GATE) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `9e16c44`(ADR#56). ADR#57 변경: `source_overlap_discovery.py`(신규·다입도 discovery+GDELT fetch+agent schema)·`real_source_smoke_report.py`(§8 matrix)·테스트 2·docs 8.
- 검증(정직): 실 GDELT fetch→**429 rate_limited→captured fixture fallback**(real_fetch=False)·fixture possible_same_event 6=fingerprint 1+near 5·deterministic_detectable 1·adjudicator_zone 5·overlap_potential_matrix 10 pair(community 제외)·**자동 병합 0**·**본문 미저장**. 테스트: 신규/확장 **34**(discovery 30+§8 report 4)·discovery+report 단독 **61 passed**·backend 비-live **593 passed/4 skipped/0 failed(959s)**(ADR#56 559→+34)·live-PG **94 passed**(단독 재실행·동시 실행 false-fail 확정)·ingestion **1353 passed**·frontend tsc**0**/node:test **12**/lint **0**·secret scan **PASS(265)**·docs_lifecycle conflicts **0**. 운영 DB 무변경.
- 감사: adversarial-reality-critic **PROCEED·HIGH 0**(honesty HOLDS·LOW 3=import 결합/placeholder/PROJECT_STATUS 정리) / code-review **LOW 1 수정**(`no_canonical_anchor` 오분류·회귀 테스트).
- 문서: ADR#57(`_DECISIONS`)·R-RealSourceLoopUnproven/R-LiveIdentityBacklog 부분진전+R-SourceOverlapScarcity 신규(`_RISK`)·overlap discovery 서브섹션+RealSourceLoop 표(`2_ROADMAP/15`)·(11o)(`2_ROADMAP/00`)·agent readiness 조건 3+종결(`RAG_KG §6b`)·`IU_CONTRACT`·`_CANONICAL/02`.

---
_as_of: 2026-06-25 · ADR#57 source overlap discovery — ADR#56 커밋(`9e16c44`) 후, artificial replay 를 **실 source behavior** 로 한 단계 넘기기 위해 `source_overlap_discovery.py`(write-free·no-DB·no-merge·LLM 호출 0)로 record 다입도 overlap 을 분해: `fingerprint_overlap`(정확 token-set 일치→deterministic 검출→교차배치 시 `semantic_cross_batch_candidate`) vs `near_match_below_fingerprint`(paraphrase→**deterministic 사각지대**·adjudicator/embedding/LLM 영역·gated). **실 GDELT bounded fetch 시도→429(R-Gdelt429)→captured fixture fallback**(`real_fetch=False` 정직 표면화); fixture **possible_same_event 6=fingerprint 1(verbatim)+near 5(paraphrase)** → deterministic 1/6 만 검출·5/6 adjudicator-zone. `build_agent_orchestration_schema`(§9·`no_merge_without_gate`·`no_public_intelligence_unit`·`llm_invoked=False`)·`build_source_quality_matrix` §8 overlap_potential/utility 보강. 옵션 **A+B+C 채택·D docs/schema only·E 금지**. **측정**: 신규/확장 34(discovery 30+§8 4)·backend 비-live 593p/4s/0f·live-PG 94p(단독)·ingestion 1353p·frontend tsc0/test12/lint0·secret PASS(265)·docs_lifecycle 0. 감사: adversarial HIGH 0 PROCEED·code-review LOW 1 수정. **정직 경계**: 실 GDELT overlap 미관측(429)·captured fixture/합성≠실 source·paraphrase 검출은 adjudicator(gold/MERGE_GATE) 영역·운영 DB/reviewer/gold/merge/LLM 본경로 잔여(production 백로그 0 불변·완전종결=OVERCLAIM·discovery 능력≠실 운영 actuality). **R-RealSourceLoopUnproven·R-LiveIdentityBacklog 부분진전·R-SourceOverlapScarcity 신규**·종결 0. ADR#56 커밋 `9e16c44` 위 ADR#57 미커밋(신규 2+수정 2+docs 8=12)·커밋 지시 대기·push 안 함._

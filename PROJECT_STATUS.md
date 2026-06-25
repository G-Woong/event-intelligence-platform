# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 지난 턴 도구(ADR#57)를 안정 기준점으로 **커밋**한 뒤, "여러 매체에서 같은 사건 겹침을 **실제로 가져오는 전략**"을 만들었습니다. 핵심 발견: 지난 턴 GDELT(무료 뉴스 집계)가 막혔던 진짜 이유는 "GDELT 가 막혀서"가 아니라 **우리 도구가 이미 있는 요청-속도 관리 장치를 안 거치고 막 호출했기 때문**이었습니다. 이번엔 그 장치를 **그대로 존중**하도록 고치고, GDELT 대신 **이미 검증된 무료 뉴스 RSS**(BBC·알자지라 등)로 진짜로 가져왔습니다.
- **이번 턴에 실제로 끝낸 것:** ADR#57 커밋(`5c388e3`) → **ADR#58**: (A) GDELT 요청-속도 관리 재사용(막혔으면 아예 호출 안 함) (B) **진짜 RSS 뉴스 55건을 성공적으로 수집**(요청 제한 0) (C) 어느 매체쌍을 언제 모을지 계획표 (D·핵심) **컴퓨터가 못 잡는 "표현만 다른 같은 사건"을 버리지 않고 사람 검수 대기열로 보내는 통로**. **그런데 진짜 55건에서 매체 간 같은-사건 겹침은 0건**이었습니다 — 즉 "수집은 되지만 같은-사건 겹침 자체가 구조적으로 드물다"를 **진짜 데이터로 확인**했습니다.
- **정직한 한계:** **진짜 cross-source 같은-사건 겹침은 여전히 관측 못 했습니다**(55건 수집·겹침 0). 즉 "가져오기 성공 ≠ 겹침 확보". **production 백로그 0·운영 DB 무변경·실 gold/reviewer/병합 0·LLM/Agent 본경로 0(No-Go)·자동 병합 0·본문 미저장** 불변. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `5c388e3`**(ADR#57, 본 턴 첫 커밋) 위 **ADR#58 = 미커밋**: 수정 2(`source_overlap_discovery.py`[A/B/C/D 추가] + `real_source_smoke_report.py`[§9 matrix]) + 수정 2(테스트 2) + docs 6 = **변경 12파일**(`PROJECT_STATUS` 포함 시 추적 항목). **migration 없음·새 파일 0(기존 도구 확장)·신규 코드 LOC ~842.**
- 수정: `backend/app/tools/{source_overlap_discovery,real_source_smoke_report}.py`·`backend/tests/{test_source_overlap_discovery,test_real_source_smoke_report}.py` + docs(`2_ROADMAP/00·15`·`_RISK/RISK_REGISTER`·`5_REFERENCE/RAG_KG_AGENT_READINESS·INTELLIGENCE_UNIT_CONTRACT`·`_CANONICAL/02`·`_DECISIONS/2026-06`·`PROJECT_STATUS`).
- 열린 RISK: **R-RealSourceLoopUnproven·R-LiveIdentityBacklog·R-SourceOverlapScarcity·R-Gdelt429 부분진전**(ADR#58) · R-SemanticIdentityAdjudicator · R-IdentityEvalDataset · R-IdentityHumanLabeling · R-ReviewerAgreement · R-GoldSamplingBias · R-CrossBatchEventIdentity(open). **신규 RISK 0·종결 0**(total 36). throwaway는 `.harness/_TRASH/`·`frontend/.harness/`(gitignored).

## ✅ 이번 턴에 달성한 것 (real overlap acquisition strategy — ADR#58)
- **① ADR#57 커밋**: 12파일 → `5c388e3`(secret PASS·docs_lifecycle conflicts 0·SIGNATURE MATCH 15·push 0).
- **② 원자 분석(§2·20문항)·전제 재구성**: ingestion governance 인프라+소스 레지스트리 정독. **핵심 발견**: ADR#57 GDELT 429 의 근인은 "GDELT 가 막혔다"가 아니라 **이 backend 도구가 기존 governance(`HostRateGate`·`rate_limit_policy`·`source_strategy_memory` cooldown)를 우회한 raw httpx**. `retry_policy.retry_on` 에 RATE_LIMITED 부재 → tight-retry 구조적 차단. 진짜 overlap 생성원도 GDELT 보다 **이미 검증된 key-free RSS 함대**(auth=none·source_registry 등재). 사용자 확인 → **A+B+C+D(report) 전부·near-match route 핵심** 채택.
- **③ A — GDELT governance 재사용**: `gdelt_provider_status`(read-only preflight·network/write 0 — HostRateGate.decide+`in_cooldown`+`load_rate_limit_policy` honor)+`fetch_gdelt_overlap_records` short-circuit(provider_status≠ok→**network 미시도**·우회 재발 차단·no tight retry). 새 retry 코드 0.
- **④ B — key-free RSS governed 실 fetch**: `parse_rss_items`(stdlib ET·RSS/Atom·**rel=alternate 우선**·RFC822→ISO·본문 미저장)·`fetch_rss_overlap_records`(`_SERVICE_CONFIGS` endpoint auth=none 만·shared host gate 참여·bounded·failure 분류·transport 주입 결정론). **실측: bbc/aljazeera/the_verge/techcrunch 55 record(429 0·canonical 55)→cross-source overlap 0(`no_title_overlap`)·same-beat tech 30 record 도 0.**
- **⑤ C — acquisition planning matrix**: `build_acquisition_plan`(source_pair/topic/time-window plan·expected_overlap_utility·LLM 0·no_merge_without_gate) → 무작위 수집을 목적 기반 source-pair 수집으로 전환할 substrate.
- **⑥ D — near-match reviewer route(핵심)**: `discover_overlap` near_match_pairs 캡처+`build_near_match_reviewer_candidates`(paraphrase 사각지대→reviewer/gold worksheet·기존 `EvalPair`/`build_labeling_packet` 스키마·label=unlabeled·**predicted_status 미포함**·`risk_tags=paraphrase`로 `assign_candidate_bucket` 분류·publishable×publishable 만·`no_merge_without_gold`·병합 0).
- **⑦ §9 source quality matrix 고도화**: `_ROLE_UTILITY`+`_acquisition_profile`(overlap_acquisition_utility·title_paraphrase_risk·cross_source_pairability·same_event_likelihood·body_policy·provider_accessibility·rate_limit_risk·robots_tos_status·agent_next_action·**하드 근거 source 만·나머지 unknown=fabrication 0**).
- **⑧ 감사 정정**: adversarial **PROCEED·HIGH 0**(안전계약 4종 VALID·정직 경계 유지·과대종결 0·fabrication 0)→MEDIUM 2+LOW 1 정정(bucket 토큰·CLI host_gate·doc source 목록). code-review **CONFIRMED 1+PLAUSIBLE 1 정정**(Atom rel=alternate·cooldown 비-튜플 방어). 회귀 테스트 3 추가.

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·운영 배선 ADR#48~#53·preflight+smoke ADR#54·live-db smoke ADR#55·replay substrate ADR#56·overlap discovery ADR#57·**real overlap acquisition ADR#58**) → ④ 실 병합(**미구현**).
- **ADR#58 위치**: ②③의 *입력*(실 cross-source overlap)을 **실제로 확보**하려는 acquisition 레이어. governance 재사용(A)·실 RSS fetch(B)는 검증됐으나 **실 overlap 은 untargeted feed 에서 구조적 희소**(55 record→0). near-match(D)는 deterministic 이 못 잡는 paraphrase 를 reviewer/gold(④ 직전 detection 레이어)로 보내는 통로.
- **⚠ 미해소(OPEN):** 실 cross-source same-event overlap(55 record→0)·targeted same-event acquisition(query-capable provider)·운영 DB 0009 배포·실 병합·실 gold·reviewer 합의·한국어 캘리브레이션·MERGE_GATE. "acquisition(능력) ≠ 실 overlap(actuality)" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence(merge anchor)·community=반응 evidence(anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed. acquisition/discovery 의 pairwise overlap·near-match 후보는 publishable(official/article) pair 만·community/market/catalog 제외(role guard·matrix `guard_only`).
- **제품 계약(raw≠public)**: discovery/acquisition 은 Intelligence Unit **merge safety substrate** 의 write-free 측정·계획(자동 병합 0·**본문 미저장**·public API 미노출). near-match 는 같은 사건 단정/병합/public IU 가 아니라 **reviewer/gold/MERGE_GATE 통과 전까지 hint/큐**. Agent 는 source-pair *계획* 가능하나 `no_merge_without_gate`·`no_public_intelligence_unit`·`llm_invoked=False`. LLM/Agent 진입 9조건 여전히 No-Go(1·4·5·7).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전(종결 0·신규 0)**: **R-RealSourceLoopUnproven**(429 근인=governance 우회 규명·시정·실 RSS governed fetch 검증) · **R-LiveIdentityBacklog**(near-match→reviewer/gold worksheet 통로 신설) · **R-SourceOverlapScarcity**(실 RSS 55 record→overlap 0 으로 구조적 희소 **실데이터 확증**·source_pair/time/topic plan·overlap_acquisition_utility 수치화) · **R-Gdelt429**(provider preflight·cooldown honor·no-retry-storm·fallback=RSS).
- 디렉티브 신규 RISK 후보(R-ProviderFallbackCoverage/R-NewsHtmlAllowlistPolicy/R-NearMatchReviewerQueue/R-AgentSourcePlanning)는 **독립 blocker 아님** → R-SourceOverlapScarcity·R-SemanticIdentityAdjudicator 에 포섭(RISK 남발 금지·total 36 불변).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 cross-source same-event overlap 관측**: 실 RSS fetch 는 성공(429 0·55 record)했으나 untargeted feed snapshot 의 같은-사건 overlap = 0(`no_title_overlap`)·same-beat 도 0. 구조적 희소(R-SourceOverlapScarcity). (다음 hard blocker — **targeted same-event acquisition**: RSS 고정 feed 는 query 불가·GDELT 는 query 가능하나 429.)
- **paraphrase overlap 검출**: deterministic fingerprint 는 verbatim 만 → near-match 는 미검출. 검출은 embedding/LLM adjudicator(MERGE_GATE·gold) 영역·미구축(R-SemanticIdentityAdjudicator). near-match route 는 통로일 뿐 실 reviewer 라벨/gold 0.
- **운영 production 백로그**: 운영 DB 0009 배포(승인 필요·옵션 E 금지) + 실 fetch 볼륨 필요 → production 0.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 실 cross-source overlap = source 커버리지/targeting 선결(GDELT query=429·RSS=query 불가). 운영 production 백로그 = 운영 DB 0009 배포(승인) + 실 fetch 볼륨.
- UNKNOWN: paraphrase overlap 의 실 병합 허용 기준(production precision·실 gold·reviewer 합의·한국어 캘리브레이션·MERGE_GATE) → R-SemanticIdentityAdjudicator·R-IdentityHumanLabeling·R-ReviewerAgreement·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#58: 수정 4(source 2+test 2) + docs 6 = 12파일 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** (a) **targeted same-event acquisition**(query-capable key-free provider·topic/time-windowed) → 실 near-match 후보 생성 → near-match route 로 reviewer/gold worksheet 충원 → (b) reviewer 합의 gold + 한국어 캘리브레이션 → (c) embedding/LLM/KG **실 병합** adjudicator(paraphrase overlap·MERGE_GATE) → (d) (승인 하) 운영 DB 0009 배포 + scheduler 가동 → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `5c388e3`(ADR#57). ADR#58 변경: `source_overlap_discovery.py`(A governance+B RSS+C plan+D near-match route)·`real_source_smoke_report.py`(§9 matrix)·테스트 2·docs 6.
- 검증(정직): **실 RSS smoke 성공**(bbc/aljazeera/the_verge/techcrunch **55 record·429 0**·canonical 55·published 55)→**cross-source overlap 0(`no_title_overlap`)**·same-beat 30 record 도 0(헤드라인 실제 상이)·**본문 미저장**·**자동 병합 0**. 테스트: 신규/확장 **32**(discovery +24·report §9 +8)·discovery+report **93 passed**·backend 비-live **622 passed/4 skipped/0 failed(962s full)** + 감사정정 3(targeted 재실행 green·source_overlap_discovery 자기 테스트만 import→격리)=**effective 625**·live-PG **94 passed(217s·단독)**·ingestion **1353 passed**·frontend tsc**0**/node:test **12**/lint **0**·secret scan **PASS(142)**·docs_lifecycle conflicts **0**. 운영 DB 무변경.
- 감사: adversarial-reality-critic **PROCEED·HIGH 0**(안전계약 4종 VALID·정직 경계 유지·과대종결 0·fabrication 0)·MEDIUM 2+LOW 1 정정 / code-review **CONFIRMED 1(Atom rel)+PLAUSIBLE 1(cooldown 방어) 정정**. 회귀 테스트 3 추가.
- 문서: ADR#58(`_DECISIONS`)·R-RealSourceLoopUnproven/R-LiveIdentityBacklog/R-SourceOverlapScarcity/R-Gdelt429 부분진전(`_RISK`·종결 0·신규 0)·real overlap acquisition 서브섹션+RealSourceLoop 표 #58(`2_ROADMAP/15`)·(11p)(`2_ROADMAP/00`)·agent readiness §6b(`RAG_KG`)·near-match route 계약(`IU_CONTRACT`)·`_CANONICAL/02`.

---
_as_of: 2026-06-25 · ADR#58 real overlap acquisition strategy — ADR#57 커밋(`5c388e3`) 후, ADR#57 GDELT 429 의 근인이 **이 backend 도구의 기존 governance 우회 raw httpx** 임을 규명·시정: (A) `gdelt_provider_status`(read-only preflight·HostRateGate+rate_limit_policy+in_cooldown honor·network/write 0)+fetch short-circuit(blocked→network 미시도·no tight retry), (B) key-free RSS 함대 governed 실 fetch(`fetch_rss_overlap_records`·auth=none endpoint·shared host gate 참여·본문 미저장)→**실측 bbc/aljazeera/the_verge/techcrunch 55 record(429 0)→cross-source overlap 0(`no_title_overlap`)·same-beat 30 record 도 0** = governance 검증(RSS 429 안 남·GDELT 우회와 대조)+실 same-event overlap 구조적 희소 확증(fetch 성공≠overlap), (C) `build_acquisition_plan`(source_pair/topic/time plan·LLM 0), (D·핵심) `build_near_match_reviewer_candidates`(paraphrase 사각지대→reviewer/gold worksheet·`risk_tags=paraphrase`로 다운스트림 bucket 분류·predicted_status 미포함·`no_merge_without_gold`·병합 0), §9 source quality matrix(overlap_acquisition_utility/title_paraphrase_risk/provider_accessibility/rate_limit_risk·하드 근거만). 옵션 **A+B+C+D(report) 채택·E 금지**. **측정**: 신규/확장 32·discovery+report 93p·backend 비-live 622p/4s/0f(962s full)+감사정정 3=625(격리)·live-PG 94p(단독)·ingestion 1353p·frontend tsc0/test12/lint0·secret PASS(142)·docs_lifecycle 0. 감사: adversarial PROCEED·HIGH 0(정직 경계 유지)·MEDIUM 2 정정·code-review CONFIRMED 1+PLAUSIBLE 1 정정·회귀 테스트 3. **정직 경계**: 실 cross-source same-event overlap 미관측(55 record→0)·합성/transport≠실 source·다음 게이트=targeted same-event acquisition→detection 레이어(embedding/LLM+gold)·운영 DB/reviewer/gold/merge/LLM 본경로 잔여(production 백로그 0 불변·완전종결=OVERCLAIM·acquisition 능력≠실 overlap actuality). **R-RealSourceLoopUnproven·R-LiveIdentityBacklog·R-SourceOverlapScarcity·R-Gdelt429 부분진전**·종결 0·신규 0. ADR#57 커밋 `5c388e3` 위 ADR#58 미커밋(수정 4+docs 6=12)·커밋 지시 대기·push 안 함._

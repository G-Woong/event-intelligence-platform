# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** gdelt 호스트 호출 간격을 **단일 출처(host gate)** 로 통합해 split-brain RISK를 닫고, GDELT·dcinside를 **실제로 라이브 호출**해 수집/본문 추출 가능 범위를 소스별로 검증했습니다.
- **이번 턴에 실제로 끝낸 것:** `R-GdeltGovernorSplitBrain` **종결**(신규 `HostRateGate` + 3경로를 **실제 HTTP 직전** 동일 gate로 배선) · GDELT/dcinside 라이브 probe + 조건부 소스/본문추출 감사 **8개 산출물** · 회귀 8 · ingestion **1316 green**.
- **지금 막힌 것:** GDELT는 외부 제공자가 우리 IP/윈도를 **429로 throttle 중**(코드 문제 아님) — fresh 1건은 비-throttle 윈도 필요(`R-Gdelt429` 유지). dcinside는 공개 본문 **소량(180자) 추출 확인**되나 ToS 미검증으로 승격 보류.

## 📋 자동 수집 사실 (machine_status.json)
- session 2945… turn 8 · 변경 다수(code: host_rate_gate 신규 + api_probe/collection_probe/gdelt_strategy/3 tool + 테스트, scripts 4, outputs/reports 8).
- 열린 RISK **24**건(이번 턴 종결 1 = 순 −1). HIGH 3 외.

## ✅ 이번 턴에 달성한 것
- **R-GdeltGovernorSplitBrain → CLOSED:** 신규 `ingestion/orchestration/host_rate_gate.py`(`HostRateGate` — host 키 단일 출처, file-backed `host_rate_gate.json`, decide/record 시 파일 재읽기=cross-process 가시성, record_call 호출 직전 즉시 atomic 영속). gdelt host **실제 HTTP 사이트 2곳**(`collect_gdelt`=closure/resurrection, `run_api_live_probe`=메인루프, 프로덕션 라우터 `run_collection_probe`가 주입)이 동일 gate 공유. source-level governor(메인 900s/closure 10s) 의미 보존, host floor만 추가(우회/병렬/tight-retry 0). 회귀 `test_host_rate_gate`(8).
- **적대 감사 2 blocking 즉시 반영 + 재검증:** ① 메인루프 실 HTTP가 gate 우회(어댑터 경계에만 있던 문제) → gate를 `run_api_live_probe` **실제 httpx 직전**으로 이동 + 실경로 테스트(차단 시 httpx 미호출/record-before-http). → 재검증 **BF-1 RESOLVED**. ② dcinside "142자 extracted"가 UI 보일러플레이트 → `_meaningful_body` 필터(추천/스크랩/신고·일반 이미지 파일명·숫자 카운터·반복 URL 제거) 추가, **의미있는 산문 ≥120자**만 extracted. 오도 케이스(142→1, 230→30, 191링크나열→강등)는 모두 `BODY_BOILERPLATE_ONLY`로 강등, **실제 산문 1건(meaningful=341, url/img 노이즈 0)** 만 진짜 추출. → 재검증 **BF-2 RESOLVED**.
- **라이브 전수 검증(소스별 분리, 뭉뚱그리지 않음):**
  - **GDELT:** 3회 spaced probe(≥12s+jitter, no-bypass) 모두 **PROVIDER_429**(외부 제한, cooldown 기록). fresh 0 → URL/본문 0. `R-Gdelt429` 유지.
  - **dcinside:** robots 허용 갤러리 list **30건**(title/url/time) · detail 6건 접근(200) · 보수적 필터 통과 공개 산문 본문 **1건(341 meaningful chars, url/img 노이즈 0)** → `LIMITED_PUBLIC_BODY`. PII/댓글/이미지 미수집, Cloudflare/captcha 시 중단.
  - **조건부 소스 매트릭스:** 57 프로필 중 **조건부(테스트 대상) 48 / POLICY·BLOCKED 제외 9**. queue 실적·body 상태·env 키·route를 소스별 기록.
  - **본문 추출 감사:** BODY_OK 11 · SNIPPET_ONLY 8 · STRUCTURED(본문 비대상) 8 · BODY_MISSING 3 · URL_CANDIDATE(검색=downstream 분리) 7. article은 대부분 snippet_only(EventQueue) + 전문은 `extracted_text/` 별도 레이어(22소스).
- **검증:** ingestion **1316 passed**(회귀 0) · docs_lifecycle 19 · secret scan PASS(41 files) · `.env` 무변경 · 4-감사단(test-validation PASS·legal-safety APPROVED·orchestrator SOUND·adversarial 2 blocking→**둘 다 수정·재검증**).

## ❌ 달성하지 못한 것 & 왜
- **GDELT fresh 수집 0** — 외부 제공자가 우리 IP/윈도를 throttle(단발에도 429). 우회 금지라 비-throttle 윈도가 필요(다음 기회 재probe). 메커니즘(host gate·cooldown 자동재개·429 분류)은 검증 완료.
- **조건부 48소스 전수 라이브 재probe 미수행** — rate-limit/API 키 비용으로 1턴 내 48개 실호출은 비현실적. 권위 production_state + 실적 아티팩트 기준으로 매트릭스화하고 gdelt/dcinside만 이번 턴 실호출(action_required로 분할 표시).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: GDELT throttle 해제 시점(외부 제공자 소관). host gate의 cross-process 경합 잔여(OS 파일락 없음)는 governor 429 cooldown이 흡수(수용 가능, 정직히 기록).

## ⚠️ 이번 턴 종결/갱신 RISK
- **종결 1:** `R-GdeltGovernorSplitBrain`(→ `RISK_CLOSED.md`, 증거: HostRateGate + 3경로 실 HTTP 배선 + 8 테스트 + 1316 green).
- **유지:** `R-Gdelt429`(MEDIUM — fresh 수집 시 종결), `R-DcToS`(MEDIUM — dcinside 공개 본문 역량 확인됐으나 ToS 미검증 → publish 봉인 유지; 역량≠적법). 순 open 25→**24**.

## 👉 다음 할 일
1. (이월) `R-Gdelt429`: 비-throttle 윈도에서 `python -m scripts.gdelt_live_body_probe` 재실행 → fresh 1건 + 본문 추출 시 종결.
2. (이월) 조건부 48소스 분할 라이브 재probe(action_required=needs_live_probe 우선).
3. (이월) ROADMAP 착수 = Event 토대(S1), `00_ROADMAP_INDEX §4`.

## 📁 근거 (이번 턴 핵심)
- 신규: `ingestion/orchestration/host_rate_gate.py`, `scripts/{gdelt_live_body_probe,dcinside_live_body_probe,source_condition_reaudit,body_extraction_audit}.py`, `ingestion/tests/unit/test_host_rate_gate.py`
- 변경: `ingestion/probes/api_probe.py`, `ingestion/fetch_strategies/collection_probe.py`, `ingestion/orchestration/{gdelt_strategy,__init__}.py`, `ingestion/tools/{run_production_orchestration,run_final_source_closure,run_last_chance_source_resurrection}.py`
- 산출물: `reports/{gdelt_live_body_probe,dcinside_live_body_probe,source_condition_reaudit,orchestration_body_extraction_audit}.md`, `outputs/{gdelt_live_body_probe.jsonl,dcinside_live_body_probe.jsonl,source_condition_matrix.csv,body_extraction_matrix.csv}`
- RISK: `_RISK/RISK_REGISTER.md`(−1 종결), `_RISK/RISK_CLOSED.md`(+1)
- 감사: test/code(test-validation) PASS · evidence(legal-safety) APPROVED · pipeline(orchestrator) SOUND · risk_closure(adversarial) 2 blocking→수정·재검증

---
_as_of: 2026-06-22 · R-GdeltGovernorSplitBrain 종결(host gate 단일 출처) + GDELT/dcinside 라이브 probe + 조건부/본문 감사 8산출물 · ingestion 1316 green · GDELT throttle(R-Gdelt429 유지) · app 정상_

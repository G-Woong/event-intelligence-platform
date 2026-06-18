# 09 — VALIDATION AND TESTS (검증·테스트 현황)

> 수치는 레이어별로 분리해 적는다. 섞지 않는다.

---

## 1. 테스트 현황

| 범위 | 위치 | 수 | 상태 | 기준 |
|---|---|---:|---|---|
| ingestion(수집+오케스트레이션) | `ingestion/tests/` | **1243** | PASS | P0 하드닝(2026-06-18): 1242 + policy 게이트 정정/추가 +1 |
| P0 통합(adapter/계약/멱등/정책/redis) | `ingestion/tests/integration/test_p0_*` | **38** | PASS | 네트워크 0(MockTransport/FakeRedis) |
| backend | `backend/tests/` | ~55 | PASS | +P0하드닝(events published 필터, requeue_failed_xadd) |
| agents | `agents/tests/` | ~37 | PASS | +P0하드닝(no_mock_published 9, evidence_check 검증 6) |
| workers | `workers/tests/` | ~28 | PASS | +P0하드닝(DLQ reaper 7) |
| frontend | `frontend/src/lib/__tests__/` | 8 | PASS | node --test |
| smoke(gate) | `tests/smoke/` | 8 | SKIP | `RUN_FULL_PIPELINE_SMOKE=1` 시 실행 |

- **ingestion 1205**가 현재 권위 수치. 구 문서의 509/635/648은 stale(06 C-2).
- 다운스트림(backend/agents/workers/frontend) 카운트는 **STEP 011 스냅샷** — 그 이후 드리프트 여부 `NEEDS_VERIFICATION`(재집계 시 갱신).

## 2. 검증 라운드

### 2d. Orchestration 하드닝 라운드 (2026-06-18, 수행)
- 범위: mock 노드 → 결정론적 baseline(entity/sector/impact/summary/fact_check) + publish 게이트 합성마커
  백스톱 + admin auth 운영 fail-closed(`APP_ENV`) + 복구 주기 드라이버(reconcile+requeue-failed-xadd+PEL reap).
- 단위/통합(네트워크 0): `pytest ingestion/tests` → **1243 passed**(회귀 0). `pytest backend workers agents`
  → **(2d 신규 포함, 회귀 0)**. 신규: agents `test_entity_sector_impact_fact_real_baseline`(baseline+게이트 백스톱),
  backend `test_admin_api_token_required_in_production`(5) + `test_reconciler_api`(requeue-failed-xadd 2),
  workers `test_recovery_scheduler`(5). 기존 `test_nodes_with_llm` 1건은 새 계약(openai 실패→baseline)으로 갱신.
- **라이브 baseline proof**(코어 스택 재빌드, agent-worker 새 이미지): fresh raw-event 2건 주입 →
  ① 실 URL → 카드 `published`, **entities=['OPEC','Saudi Aramco','European Union','United States','Brent']**,
     **sectors=['energy']**, impact=정직 baseline, summary=추출 실문장(전부 비-mock), 공개목록 노출 O.
  ② synthetic URL(mock.local) → hold + 공개 단건 `http_404` + 목록 X. `BASELINE_LIVE_PROOF=PASS`.
- 적대적 리뷰(adversarial-reality-critic): **REAL_BUG 1건**(openai 모드 LLM 파싱실패 시 `[fallback]` 상수가
  evidence/fact_check 게이트를 우회해 `impact_path`/`summary`로 published 노출) → 게이트 백스톱 + 노드 baseline
  복귀로 수정, 잠금 테스트 추가.
- ⚠ UNKNOWN(verified blocker): 라이브 외부 수집→backend 실적재 미실행(우회 금지), 복구 드라이버 **라이브 주기
  tick**(compose/cron 배포)·DLQ chaos는 미수행(코드/단위까지). LLM급 entity/sector + evidence 도달성 미구현.

### 2c. P0 하드닝 라운드 (2026-06-18, 수행)
- 범위: mock 카드 published 차단 게이트 + Redis DLQ/PEL reaper + xadd_failed 자동 requeue.
- 단위/통합(네트워크 0): `pytest ingestion/tests` → **1243 passed**(회귀 0). `pytest backend agents workers`
  → **156 passed / 5 skipped**(openai/milvus 통합 smoke 스킵). 신규: agents `test_event_graph_no_mock_published`(9)
  + `test_evidence_check_real_validation`(6), backend `test_events_published_filter`(1) + `test_requeue_failed_xadd`(4),
  workers `test_dlq_reaper`(7).
- **라이브 게이트 proof**(코어 스택 재빌드 후, 8컨테이너 healthy): fresh raw-event 2건 직접 주입 →
  ① 유효 source URL(reuters) → 카드 `published` + `GET /api/events` 노출 O,
  ② synthetic URL(mock.local) → 근거 grounding 실패 → 카드 `hold` + 공개목록 노출 X. `GATE_LIVE_PROOF=PASS`.
- 멱등 재확인(라이브): `run_p0_integration` 5 record_type **DUPLICATE_COLLAPSED**(content_hash on_conflict).
- worker/agent-worker crash-loop 해소 확인(redis 가용 후 healthy).
- ⚠ UNKNOWN(verified blocker): production-validation **라이브 외부 수집**→backend 실적재는 미실행(이전 세션
  사용자 중단, 우회 금지). DLQ **라이브 chaos**(worker kill 중 PEL 회수)는 단위(FakeRedis)까지만.

### 2b. P0 통합 라운드 (2026-06-18, 수행)
- `pytest ingestion/tests` → **1242 passed**(신규 37 포함, 회귀 0). `pytest agents` → 21 passed/1 skip.
- 라이브 e2e: 코어 스택 10컨테이너 healthy. `run_p0_integration` 5 record_type **E2E_OK**(article/
  official/structured/search/community) — raw_event→PG→Redis→worker→LangGraph→event_card. 재실행 멱등 collapse.
  community 카드 `hold` 봉인(agent-worker 이미지 재빌드 후). production CLI `--raw-events-sink backend`
  dry-run `bridge_contract_pass=True`.
- secret scan: `scan_secrets --paths ingestion backend workers agents docs` → **verdict=PASS files_scanned=5079**.
- `git diff --check`: DIFF_CHECK_CLEAN.
- ⚠ UNKNOWN: production-validation 라이브 외부 probe→backend 실적재는 이번 세션 미실행(사용자 중단).

### 2a. docs 라운드의 검증 (수행)
- secret scan: `python -m ingestion.tools.scan_secrets --paths docs`.
- `git diff --check`: 공백/충돌 마커 없음 확인.
- manifest 정합: `docs/**/*.md` 수 == `10_DOCS_COVERAGE_MANIFEST.md` 행 수.

## 3. 산출물·아티팩트 정책

- `ingestion/outputs/**` 전부 **gitignored**. 증거는 `docs/ingestion/artifact_manifest_final.md`에
  path + SHA256(16) + 재생성 runner로 기록(원문/비밀 미포함).
- production 상태: `ingestion/outputs/state/production_source_state.json`(57소스, 분포는 03).
- ⚠ 매니페스트 갱신 필요: G-4 모듈(community_corroboration_gate/source_specific_proof)·orchestration cycle 출력 미등재(04 T-DocB).

## 4. 정책 게이트 (검증의 일부)

- 실패를 PASS로 표기 금지. google_trends_explore = CONFIRMED_EXTERNAL_RATE_LIMIT(PASS 아님).
- gdelt fresh 0 records → READY 선언 금지(EXTERNAL_RATE_LIMITED 유지).
- 우회(robots/ToS/CAPTCHA/login/paywall/rate-limit/proxy) 전면 금지 — 위반 시 검증 무효.
- secret 출력/.env 전문 출력 금지. local 파일경로를 외부 증거로 사칭 금지.

## 5. 회귀 보호 불변

- Phase A~G-3 회귀 및 기존 테스트 약화/삭제 금지. 신규 기능은 테스트 추가로만.

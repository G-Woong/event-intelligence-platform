# 09 — VALIDATION AND TESTS (검증·테스트 현황)

> 수치는 레이어별로 분리해 적는다. 섞지 않는다.

---

## 1. 테스트 현황

| 범위 | 위치 | 수 | 상태 | 기준 |
|---|---|---:|---|---|
| ingestion(수집+오케스트레이션) | `ingestion/tests/` | **1293** | PASS | role taxonomy 라운드(2026-06-18): 1257 + source_role 36 |
| P0 통합(adapter/계약/멱등/정책/redis) | `ingestion/tests/integration/test_p0_*` | **38** | PASS | 네트워크 0(MockTransport/FakeRedis) |
| backend | `backend/tests/` | **106** | PASS | 2026-06-18 재집계(+4 skip: openai/milvus 통합 smoke) |
| agents | `agents/tests/` | **86** | PASS | 2026-06-18 재집계(+1 skip: openai smoke) |
| workers | `workers/tests/` | **32** | PASS | 2026-06-18 재집계 |
| frontend | `frontend/src/lib/__tests__/` | 8 | PASS | node --test |
| smoke(gate) | `tests/smoke/` | 8 | SKIP | `RUN_FULL_PIPELINE_SMOKE=1` 시 실행 |

- **ingestion 1293**이 현재 권위 수치(2026-06-18 role taxonomy 라운드 후). 구 문서의 509/635/648·1205·1243은 stale(06 C-2).
- 다운스트림 카운트는 2026-06-18 **재집계**(combined `pytest ingestion backend workers agents` = **1517 passed/5 skip**, 회귀 0).

## 2. 검증 라운드

### 2g. Source role taxonomy + docs↔code 동기화 라운드 (2026-06-18, 수행)
- 범위: source **역할 taxonomy 파생 계층**(헌법 3 역할별 연결) + docs↔code 동기화 정리(헌법 4·5).
- **`source_role.py`**(신규): `source_profiles.yaml`의 source_group/is_community/confirmation_policy에서
  7역할(ARTICLE_BODY/EXPANSION_SEARCH/OFFICIAL_RECORD/STRUCTURED_SIGNAL/COMMUNITY_EARLY_SIGNAL/
  ENRICHMENT_ONLY/PERIODIC_EVENT_QUEUE)을 **결정론적 파생**(새 데이터 0, 단일 출처 유지). routing_mode+
  publication_policy 동반, EXPANSION/COMMUNITY는 `never_direct_publish` 강제. **역할 ⊥ final_action**(운영 상태).
- **runner 확장(새 runner 0)**: `run_orchestration_source_validation`이 SOURCE_ROLE_MATRIX(57:
  ARTICLE 14/COMMUNITY 9/ENRICHMENT 13/EXPANSION 7/OFFICIAL 8/STRUCTURED 6) + SOURCE_FINAL_ACTION_MATRIX
  (CALLABLE_NOT_PROBED 46/SKIPPED 9/RATE_LIMITED 1/HELD 1) 동시 emit. 네트워크 0.
- 단위(네트워크 0): `pytest ingestion/tests` → **1293 passed**(회귀 0, +36 `test_source_role_taxonomy`).
  combined `pytest ingestion backend workers agents` → **1517 passed/5 skip**(회귀 0).
- **docs 동기화**: 00 §0 한 문장 요약(JSON mirror→backend sink 라이브 E2E 정정), 02 §1 연결 셀,
  06 C-2/C-9(수치·R-Integration framing), 01/03/05(role taxonomy), 04 T-DocA 수치. **삭제 0**(헌법 4).
- **검증 정직성**: Explore 감사의 부정 주장 2건(`stream:to_agent`/`fact_check.py` "코드에 없음")을 직접 grep으로
  반증 → 둘 다 코드 존재(거짓 drift 방지). `source_role` 이름은 `ingestion/runners/` audit 러너의 옛 registry
  `role` 필드와 충돌하나 별개 개념(내 모듈 미import) — docs는 validation runner 범위로만 한정(과잉주장 없음).
- 커밋: `86bebfb`(role taxonomy) + 본 docs 동기화 라운드.
- secret scan: `scan_secrets --paths ingestion backend workers agents docs` → **PASS**. `git diff --check`: clean.

### 2f. Source-to-card E2E + timeout false-fail 수정 라운드 (2026-06-18, 수행)
- 범위: 라이브 외부 source → **backend sink → event_card** end-to-end 직접 관찰(직전 verified blocker
  해소) + BackendApiRawEventsWriter timeout 거짓실패 버그 수정 + recovery-scheduler **상주 daemon** 기동.
- **backend auth 재확인(무해 probe)**: `POST /api/admin/raw-events` no-token → **422**(auth 통과, body 검증만
  실패). 즉 현 스택은 토큰 없이 admin write 수락 → 호스트 runner 가 backend sink 적재 가능(직전 세션의
  "토큰 friction" 은 현 스택에선 비차단). 우회/비밀 없음.
- **라이브 E2E proof(직접 관찰)**: `run_production_orchestration --mode production-validation
  --raw-events-sink backend --max-sources 1` → due 소스 **ap_news**(Google News RSS) 라이브 fetch
  **100 records** → raw_events PG **100 rows**(source_name=ap_news, 전부 title·published_at 채워짐) →
  Redis `stream:raw_events` +100 / `stream:to_agent` +100 → worker(group:ingest, pending 0/lag 0 소비) →
  agent-worker(group:agent) → LangGraph → **event_cards 100건**(evidence 에 news.google.com URL,
  전부 status=`hold`). snippet_only·무본문 → fact_check fail-closed → **정상 hold**(공개 published 129 불변,
  held 카드 비노출). **provenance 확정**: `evidence::text LIKE '%news.google.com%'` 카드 = 100.
- **REAL BUG 발견+수정(라이브)**: 첫 run 이 `raw_events_written=46 / raw_events_failed=54 /
  bridge_contract_pass=False / critical_alerts=2`("54 raw_events write failures") 보고했으나 **PG 엔 100건
  전부 적재 + redis +100 + backend 로그 4xx/5xx 0건**. 원인 = `BackendApiRawEventsWriter` **timeout=10초**
  (+호출마다 새 httpx.Client, 풀링 없음)가 burst 적재 tail-latency(>10초, agent-worker PATCH 와 이벤트루프
  경합)에서 **거짓 transport timeout** 을 일으켜 실패로 집계(서버는 200 으로 완료, 데이터는 정상 적재).
  → **수정**: default timeout **10→30초**(endpoint 는 content_hash on_conflict 멱등이라 timeout 재시도 안전).
  회귀 잠금: `test_p0_raw_events_writer.py` +2(default 30s, 설정가능) — **9 passed**.
- **수정 후 재검증(라이브, 2회)**: ① 재실행 → `critical=0`, `contract_pass=True`(35 dup collapse + 1 신규),
  ② **fresh burst 재검증** → 신규 record **20건 전부 write 성공**(raw_events_written=20, failed=0, `critical=0`,
  `contract_pass=True`). 직전 동일 경로 100건 중 54 false-fail 이 **0 으로 제거**됨(전수 100건 burst 는 후속).
- **recovery-scheduler 상주 daemon**: `docker compose up -d recovery-scheduler` → 즉시 첫 tick
  `recovery cycle done actions=3 ok=3`(reconcile_stuck/requeue_failed_xadd/reap_pending 전부 backend:8000
  in-network 200), 이후 `--interval-sec 60` 주기. 직전 라운드의 "--once 만" → **상시 tick** 으로 진행.
- ⚠ UNKNOWN(verified blocker): 46 CALLABLE 소스 **전수** 라이브 probe 미완(이번 라이브는 ap_news 1 + bbc급
  재실행). timeout 수정의 **100건 burst 재검증**은 후속. entity/sector LLM급 정밀도·evidence 도달성
  openai/network 라이브·RBAC 미배포. ap_news 카드는 무본문이라 전량 hold(상용 published 카드는 실본문 소스 필요).

### 2e. Orchestration source-live 라운드 (2026-06-18, 수행)
- 범위: evidence_check SSRF-safe HTTP 도달성(Phase 4) + recovery-scheduler 라이브 tick/compose service(Phase 3)
  + admin auth 자세 단일화 + APP_ENV=dev 오배포 guard(Phase 5) + source-wide final_action matrix harness(Phase 2).
- 단위/통합(네트워크 0): `pytest ingestion/tests` → **1255 passed**(회귀 0, +12 matrix 분류기).
  agents → **83 passed/1 skip**(+evidence_reachability SSRF 17, +evidence_check 배선 3). backend admin auth
  → **9 passed**(+assert_startup_auth_posture 4). workers recovery scheduler → 4 passed.
- **적대적 리뷰(adversarial-reality-critic, SSRF)**: REAL_BUG 2건 — ① DNS rebinding/TOCTOU(HIGH, 잔존 위험으로
  문서화 + "SSRF-safe" 단언 철회→best-effort), ② IPv4-mapped IPv6 분류(HIGH, `ip_is_public`을 is_global
  whitelist + 언맵으로 수정; 본 인터프리터에선 is_private이 이미 차단하나 견고화). follow_redirects 강제 추가.
  회귀 잠금 테스트 3건(`::ffff:169.254.169.254` 차단 등).
- **라이브 tick proof**(실행 스택): `recovery-scheduler` compose run `--once --dry-run` →
  reconcile_stuck(200)/requeue_failed_xadd(200)/reap_pending(claimed=0) `actions=3 ok=3` EXIT=0.
- **라이브 외부 probe proof**: `run_production_orchestration --mode production-validation --max-sources 1` →
  **bbc** 라이브 수집 36 records → EventQueue 34 + raw_events(mirror) 34, duplicates 2, rate_limited 0,
  bridge_contract_pass=True. (실제 외부 데이터가 흐르는 것을 직접 관찰; mirror sink까지.)
- secret scan: `scan_secrets --paths ingestion backend workers agents docs` → **PASS files_scanned=5210**.
  `git diff --check`: clean.
- ⚠ UNKNOWN(verified blocker): 라이브 외부→**backend sink end-to-end(card까지)** 미실행(in-network 토큰
  friction), 46 CALLABLE 소스 전수 라이브 probe 미실행(이번 1건만), 복구 daemon 상시 배포·DLQ chaos·
  evidence 도달성 LLM_PROVIDER=openai 라이브, entity/sector LLM급 정밀도.

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

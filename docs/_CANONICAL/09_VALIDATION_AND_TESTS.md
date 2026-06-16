# 09 — VALIDATION AND TESTS (검증·테스트 현황)

> 수치는 레이어별로 분리해 적는다. 섞지 않는다.

---

## 1. 테스트 현황

| 범위 | 위치 | 수 | 상태 | 기준 |
|---|---|---:|---|---|
| ingestion(수집+오케스트레이션) | `ingestion/tests/` | **1205** | PASS | G-4 기준(93e83b6) |
| backend | `backend/tests/` | ~50 | PASS | STEP 011 기준선 |
| agents | `agents/tests/` | ~22 | PASS | STEP 011 기준선 |
| workers | `workers/tests/` | ~19 | PASS | STEP 011 기준선 |
| frontend | `frontend/src/lib/__tests__/` | 8 | PASS | node --test |
| smoke(gate) | `tests/smoke/` | 8 | SKIP | `RUN_FULL_PIPELINE_SMOKE=1` 시 실행 |

- **ingestion 1205**가 현재 권위 수치. 구 문서의 509/635/648은 stale(06 C-2).
- 다운스트림(backend/agents/workers/frontend) 카운트는 **STEP 011 스냅샷** — 그 이후 드리프트 여부 `NEEDS_VERIFICATION`(재집계 시 갱신).

## 2. 이 docs 라운드의 검증 (수행)

- secret scan: `python -m ingestion.tools.scan_secrets --paths docs` → 결과는 커밋 메시지/보고에 기록.
- `git diff --check`: 공백/충돌 마커 없음 확인.
- manifest 정합: `docs/**/*.md` 수 == `10_DOCS_COVERAGE_MANIFEST.md` 행 수(원본 50 + 신규 canonical 11 + 인벤토리/매니페스트 자체는 행에서 구분).

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

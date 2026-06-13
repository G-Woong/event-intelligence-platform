# 06. Test Validation Agents 설계

> **생성일**: 2026-06-13
> **목적**: 10개 테스트·검증 에이전트 설계. 각 에이전트의 trigger, 검증 항목, 실패 시 액션 포함.
> **현재 기준선**: pytest 648 passed, secret scan PASS, runner 13/13 agent_ready

---

## 검증 에이전트 개요

단일 test-validation-agent로 모든 검증을 처리하면 병목이 생기고 책임이 흐릿해진다.
아래 10개 에이전트는 각자 독립적인 검증 영역을 담당하며, Release Gate에서 합산된다.

**공통 원칙:**
- 실패 무시하고 PASS 보고 금지
- 추정 결과를 확정 결과로 보고 금지
- 검증 명령 실행 없이 "통과로 추정" 금지

---

## 에이전트 1: unit-test-agent

| 항목 | 내용 |
|------|------|
| **trigger** | 코드 파일 수정 후, PR 전, 세션 종료 전 |
| **검증 범위** | `ingestion/tests/unit/` 하위 전체 |
| **실행 명령** | `.\.venv\Scripts\python.exe -m pytest ingestion\tests\unit -q --tb=short` |
| **성공 기준** | 0 fail, 0 error |
| **실패 시** | 실패 테스트 목록 + 원인 분석 → source-ingestion-engineer 핸드오프 |
| **현재 상태** | 648 passed (전체 포함) |

### 세부 단위 테스트 범주

| 테스트 파일 | 검증 내용 | 상태 |
|------------|----------|------|
| test_quality_score.py | QualityScore 계산 로직 | PASS |
| test_schema_validation.py | RawDocument/EventCandidate schema | PASS |
| test_source_registry.py | source_registry.yaml 로드/조회 | PASS |
| test_normalizers.py | probes/normalizers 출력 형식 | PASS |
| test_pipeline_scaffold.py | pipeline 모듈 import/smoke | PASS |
| test_site_specs.py | playwright_probe_sites.yaml 일치성 | PASS |
| test_ap_news_recovery.py | ap_news Google RSS proxy | PASS |
| test_newsapi_everything.py | newsapi /v2/everything 전환 | PASS |
| test_gdelt_stabilization.py | gdelt gate/rate-limit/truncate_query | PASS |
| test_trend_fallback.py | trends fallback chain 계약 | PASS |
| test_feed_discovery.py | feed_discovery 기법 | PASS |
| test_route1_rate_limit_record.py | Route1 429 cooldown record | PASS |
| test_trends_explore_backend_policy.py | local_file backend 영속 | PASS |
| test_api_source_field_fixes.py | federal_register/igdb/culture_info | PASS |

### proposed diff

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/agents/unit-test-agent.md b/.claude/agents/unit-test-agent.md
new file mode 100644
--- /dev/null
+++ b/.claude/agents/unit-test-agent.md
@@ -0,0 +1,18 @@
+---
+name: unit-test-agent
+description: >
+  단위 테스트 전체 실행 및 실패 분석. 코드 수정 후 또는 PR 전 사용.
+tools: Bash, Read, Glob
+---
+
+# unit-test-agent
+
+## 실행
+.\.venv\Scripts\python.exe -m pytest ingestion\tests\unit -q --tb=short
+
+## 성공: 0 fail, 0 error
+## 실패: 실패 테스트 + 원인 분석 → source-ingestion-engineer 핸드오프
+## 금지: 실패 무시하고 PASS 보고
```

---

## 에이전트 2: integration-audit-agent

| 항목 | 내용 |
|------|------|
| **trigger** | 오케스트레이션 연결 후, 복수 소스 수집 후 |
| **검증 범위** | `ingestion/tests/integration/` + pipeline 모듈 |
| **실행 명령** | `.\.venv\Scripts\python.exe -m pytest ingestion\tests\integration -q --tb=short` |
| **성공 기준** | 0 fail. pipeline 단계 연결 (discovery → enrichment → candidate → event_queue) |
| **실패 시** | 연결 지점 분석 → orchestrator-architect 핸드오프 |
| **현재 상태** | integration/ 디렉터리 존재 (현재 내용 확인 필요) |

---

## 에이전트 3: live-source-validation-agent

| 항목 | 내용 |
|------|------|
| **trigger** | 신규 소스 추가 후, 주간 source health 감사 |
| **검증 범위** | CORE_READY 소스 중 샘플 live 호출 |
| **실행 명령** | `python -m ingestion.runners.run_primary_seed_live_audit` |
| **성공 기준** | items_found ≥ 1, body_extracted ≥ 1 (뉴스 소스), status = LIVE_SUCCESS |
| **주의** | google_trends_explore 429 시 SKIP (CONFIRMED_EXTERNAL_RATE_LIMIT, PASS 판정 금지) |
| **실패 시** | 실패 소스 → data-quality-auditor → source-ingestion-engineer |

### 소스별 검증 명령

```bash
# 전체 seed 감사
python -m ingestion.runners.run_primary_seed_live_audit

# 개별 소스
python -m ingestion.runners.run_collection_probe --source gdelt --json
python -m ingestion.runners.run_collection_probe --source bbc --json
python -m ingestion.runners.run_collection_probe --source ap_news --json

# google_trends_explore (gate 확인 필수 — cooldown 중이면 실행 금지)
python -m ingestion.probes.playwright_probe --site google_trends_explore --rate-limit-backend local_file
```

---

## 에이전트 4: secret-scan-agent

| 항목 | 내용 |
|------|------|
| **trigger** | 모든 코드/문서 변경 후, 커밋 전, 세션 종료 전 |
| **검증 범위** | 전체 repo |
| **실행 명령** | `python -m ingestion.tools.scan_secrets --paths .` |
| **성공 기준** | verdict=PASS, WARNING 0, 실제 leak 0 |
| **실패 시** | leak 파일/라인 분석 → 즉시 수정, 커밋 금지 |

### False Positive 처리 규칙

```
허용 (오탐):
- URL slug 내 key-like 문자열 (엔트로피 낮음)
- access_token = func(...) 코드 참조 (함수 반환값)
- 테스트 fixture + # pragma: allowlist secret

불허 (반드시 수정):
- 따옴표 리터럴로 저장된 API 키
- .env 값이 코드/문서에 노출
- sk-* 패턴 (OpenAI 키) 직접 포함
```

---

## 에이전트 5: docs-consistency-agent

| 항목 | 내용 |
|------|------|
| **trigger** | 문서 수정 후, 새 source status 갱신 후 |
| **검증 범위** | docs/ 전체 (특히 Implementation_Instructions, ingestion, Environment_setup) |
| **검증 항목** | 1. google_trends_explore가 PASS로 표기된 문서 없음 확인 2. TRACE_FINAL이 단일 출처임 확인 3. stale instruction(APPLIED/SUPERSEDED) 재실행 금지 4. artifact_manifest_final.md 갱신 여부 |
| **실행 명령** | `Select-String -Path docs -Recurse -Pattern "google_trends_explore.*PASS"` |
| **성공 기준** | 0 conflict, 0 stale instruction in active path |
| **실패 시** | 충돌 문서 → docs-memory-curator 핸드오프 |

### 검증 명령 세트

```powershell
# google_trends_explore PASS 표기 오류 확인
Select-String -Path docs -Recurse -Pattern "google_trends_explore.*PASS"

# TRACE_FINAL이 단일 출처인지 확인 (Implementation_Instructions README 진입점)
Select-String -Path "docs\Implementation_Instructions\README.md" -Pattern "IMPLEMENTATION_TRACE_FINAL"

# Environment_setup README가 진입점인지 확인
Test-Path "docs\Environment_setup\README.md"

# 문서가 .env 키 값을 포함하지 않는지 (패턴 예시 — 공개 금지)
# 실제 키 패턴은 scan_secrets에서 처리
```

---

## 에이전트 6: artifact-manifest-agent

| 항목 | 내용 |
|------|------|
| **trigger** | 새 JSONL artifact 생성 후, 세션 종료 전 |
| **검증 범위** | `ingestion/outputs/jsonl/` vs `docs/ingestion/artifact_manifest_final.md` |
| **검증 항목** | 신규 JSONL 파일이 manifest에 기록되어 있는지, size/sha256 정확한지, runner 명령이 정확한지 |
| **실행 명령** | `Get-ChildItem ingestion\outputs\jsonl -Filter "*.jsonl"` → manifest와 비교 |
| **성공 기준** | 모든 최신 JSONL이 manifest에 기록됨 |
| **실패 시** | 누락 항목 → docs-memory-curator → artifact-manifest-skill 실행 |

---

## 에이전트 7: runner-readiness-agent

| 항목 | 내용 |
|------|------|
| **trigger** | 오케스트레이션 구현 전, runner 파일 수정 후 |
| **검증 범위** | 13개 runner 전체 |
| **실행 명령** | `python -m ingestion.runners.run_runner_orchestration_readiness` |
| **성공 기준** | 13/13 agent_ready = True |
| **실패 시** | agent_ready = False인 runner → source-ingestion-engineer |

### 현재 13개 runner 목록

```
run_primary_seed_live_audit
run_enrichment_live_audit
run_conditional_sources_e2e_audit
run_playwright_selector_sources_audit
run_api_partial_sources_audit
run_external_rate_limit_recheck
run_trend_fallback_enrichment_audit
run_structure_explorer
run_runner_orchestration_readiness
check_dependency_readiness
scan_secrets
feed_discovery (library)
url_resolver (library)
article_body_extractor (library)
```

---

## 에이전트 8: env-hygiene-agent

| 항목 | 내용 |
|------|------|
| **trigger** | .env 변경 후, 신규 API 키 추가 후 |
| **검증 범위** | .env 키 목록 vs source_registry.yaml 필요 키 |
| **검증 항목** | 1. 필요한 키가 모두 존재하는지 (값 확인 없음, 존재만) 2. AMBIGUOUS_ALIAS 확인 (기준선 6건) 3. 불필요한 키 없는지 |
| **실행 명령** | `Test-Path .env` + `python -m ingestion.tools.check_dependency_readiness` |
| **성공 기준** | 14/14 dependency READY, AMBIGUOUS_ALIAS 기준선(6건) 초과 없음 |
| **실패 시** | 누락 키 → 사용자에게 키 발급 안내 (키 값 요청 금지) |

### 현재 AMBIGUOUS_ALIAS 기준선 (TRACE_FINAL §9)

```
AMBIGUOUS_ALIAS 6건 — 기능 영향 없음 (기준선)
이 수치가 증가하면 → env-hygiene-agent가 알림
```

---

## 에이전트 9: security-redteam-agent

| 항목 | 내용 |
|------|------|
| **trigger** | major 기능 릴리즈 전, Red-Team 위원회 트리거 |
| **검증 범위** | 보안 취약점 전방위 탐색 |
| **검증 항목** | 1. .env 노출 경로 2. MCP 권한 과다 3. forbidden command 우회 가능성 4. SQL injection (DB 연결 후) 5. rate-limit 우회 가능 코드 패턴 6. source hallucination 위험 |
| **실행 명령** | `python -m ingestion.tools.scan_secrets --paths .` + `git diff --check` + Grep for dangerous patterns |
| **성공 기준** | 0 HIGH 취약점 |
| **실패 시** | security-permission-guardian에 BLOCKED 전달 |

---

## 에이전트 10: regression-bisect-agent

| 항목 | 내용 |
|------|------|
| **trigger** | 최근 변경 후 기존 테스트 실패 발생 시 |
| **검증 범위** | 실패 테스트 + git log (bisect) |
| **검증 항목** | 어느 commit이 regression을 유발했는지 특정 |
| **실행 명령** | `git log --oneline -20` + `pytest --lf` (last-failed) |
| **성공 기준** | regression 원인 commit 특정 + fix 제안 |
| **실패 시** | source-ingestion-engineer에 핸드오프 |

---

## Release Gate 통합 (모든 에이전트 합산)

```
Release Gate 통과 조건 (모두 PASS 필요):
┌─────────────────────────────────────────────────────────┐
│ 1. unit-test-agent         → pytest 0 fail              │
│ 2. secret-scan-agent       → verdict=PASS               │
│ 3. docs-consistency-agent  → conflict 0, PASS 오표기 0  │
│ 4. runner-readiness-agent  → 13/13 agent_ready          │
│ 5. env-hygiene-agent       → 14/14 READY                │
│ 6. artifact-manifest-agent → manifest 최신 상태         │
└─────────────────────────────────────────────────────────┘
선택적 (major 릴리즈 시):
│ 7. integration-audit-agent → integration test 통과      │
│ 8. live-source-validation-agent → CORE_READY 소스 확인  │
│ 9. security-redteam-agent  → 0 HIGH 취약점              │
```

---

## 검증 에이전트 실행 순서 (권장)

```
Phase 1 (빠른 체크 — 항상):
  1. secret-scan-agent
  2. unit-test-agent

Phase 2 (배포 전 — 반드시):
  3. docs-consistency-agent
  4. runner-readiness-agent
  5. env-hygiene-agent
  6. artifact-manifest-agent

Phase 3 (major 릴리즈 전):
  7. live-source-validation-agent
  8. integration-audit-agent
  9. security-redteam-agent
 10. regression-bisect-agent (실패 발생 시에만)
```

---

## 검증 실패 시 에스컬레이션 경로

```
pytest fail
  → 관련 소스 파일 특정
  → source-ingestion-engineer 수정
  → unit-test-agent 재실행

secret scan fail
  → 누출 파일/라인 특정
  → 즉시 수정 (커밋 금지)
  → scan_secrets 재실행

docs conflict fail
  → docs-memory-curator 수정
  → docs-consistency-agent 재실행

runner_readiness fail
  → source-ingestion-engineer 분석
  → runner 수정 후 재실행

security HIGH fail
  → security-permission-guardian BLOCKED 판정
  → 수정 전까지 릴리즈 금지
```

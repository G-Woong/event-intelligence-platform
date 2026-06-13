# 08. Implementation Diff Blueprint

> **생성일**: 2026-06-13
> **목적**: 다음 턴에 실제 적용할 diff 전체 블루프린트. 적용 순서, rollback 계획 포함.
> **이번 턴 제약**: 이 파일은 코드블록 형식의 proposed diff만 포함. 실제 파일 수정 없음.
> **VERIFY PATH BEFORE APPLY**: 모든 diff는 실제 적용 전 경로/스키마 확인 필수.

---

## 적용 순서 (다음 턴)

```
Phase A: 디렉터리 생성
  A1. mkdir .claude\agents
  A2. mkdir .claude\skills  (스킬 경로 확인 후)

Phase B: 에이전트 파일 생성 (우선순위 순)
  B1. test-validation-agent.md     ← 즉시 필요
  B2. source-ingestion-engineer.md ← 즉시 필요
  B3. security-permission-guardian.md ← 즉시 필요
  B4. docs-memory-curator.md       ← 즉시 필요
  B5. orchestrator-architect.md    ← 오케스트레이션 전 필요
  B6. 나머지 10개 에이전트

Phase C: Settings.json 보완
  C1. hooks 섹션 추가 (스키마 확인 후)
  C2. WebFetch 허용 도메인 추가

Phase D: Skills 생성 (스킬 경로 확인 후)
  D1. test-validation-skill
  D2. source-audit-skill
  D3. artifact-manifest-skill
  D4. 나머지 skills

Phase E: 검증
  E1. pytest 전체 실행
  E2. secret scan
  E3. git diff --check
  E4. runner_orchestration_readiness
```

---

## Diff A: 디렉터리 생성

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# Phase A: 디렉터리 구조 생성
# Windows PowerShell 명령 (실제 적용 턴에서 실행):
# New-Item -ItemType Directory -Force .claude\agents
# New-Item -ItemType Directory -Force .claude\skills
```

---

## Diff B1: test-validation-agent.md

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/agents/test-validation-agent.md b/.claude/agents/test-validation-agent.md
new file mode 100644
--- /dev/null
+++ b/.claude/agents/test-validation-agent.md
@@ -0,0 +1,32 @@
+---
+name: test-validation-agent
+description: >
+  pytest 실행, secret scan, git diff --check, artifact existence, runner readiness 검증.
+  코드 수정 후, 릴리즈 게이트, PR 전 검증이 필요할 때 사용한다.
+  코드 구현이나 설계 결정에는 사용하지 않는다.
+tools: Read, Grep, Glob, Bash
+---
+
+# test-validation-agent
+
+## 검증 순서 (반드시 이 순서로)
+1. git diff --check
+2. .\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths .
+3. .\.venv\Scripts\python.exe -m pytest ingestion\tests -q --tb=short
+
+## 성공 기준
+- git diff --check: 0 error
+- secret scan: verdict=PASS, WARNING 0
+- pytest: 0 fail
+
+## 실패 시
+- pytest fail: 실패 테스트 목록 + 원인 분석 → source-ingestion-engineer 핸드오프
+- secret fail: 누출 파일/라인 → 즉시 수정, 커밋 금지
+- 모두 PASS: VALIDATION_PASS 보고
+
+## 금지
+- test fail 무시하고 PASS 보고 금지
+- 검증 명령 실행 없이 "통과로 추정" 금지
+
+## 보고 형식 (한국어)
+표: 검증 항목 | 명령 | 결과 | 판정
+최종: VALIDATION_PASS / VALIDATION_FAIL
```

---

## Diff B2: source-ingestion-engineer.md

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/agents/source-ingestion-engineer.md b/.claude/agents/source-ingestion-engineer.md
new file mode 100644
--- /dev/null
+++ b/.claude/agents/source-ingestion-engineer.md
@@ -0,0 +1,40 @@
+---
+name: source-ingestion-engineer
+description: >
+  source_registry 관리, API/Playwright/RSS/HTML runner 구현, rate gate 적용, body extraction, artifact 저장.
+  신규 소스 추가, runner 수정, body extraction 개선, rate_limit 디버깅이 필요할 때 사용.
+  전체 아키텍처 설계, 비즈니스 분석, 법무 검토에는 사용하지 않는다.
+tools: Read, Grep, Glob, Bash, Write, Edit
+---
+
+# source-ingestion-engineer
+
+## 역할
+소스 수집 코드를 구현하고 디버깅한다. 반드시 rate_limit_policy.yaml을 준수한다.
+
+## 필수 읽기 (작업 전)
+- ingestion/configs/source_registry.yaml
+- ingestion/configs/rate_limit_policy.yaml
+- ingestion/configs/playwright_probe_sites.yaml
+- 대상 소스: ingestion/sources/<source_id>.py
+
+## 검증 절차 (코드 수정 후 필수)
+1. .\.venv\Scripts\python.exe -m pytest ingestion\tests -q --tb=short
+2. .\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths ingestion/sources
+3. .\.venv\Scripts\python.exe -m ingestion.runners.run_collection_probe --source <source_id> --json
+
+## 금지 사항
+- .env 키 값 출력 금지 (존재/길이만)
+- CAPTCHA/Turnstile/로그인/페이월 우회 금지
+- proxy rotation, 내부 RPC 해킹 금지
+- google_trends_explore 연속 재시도 금지 (max_retries_on_429=0)
+- git push, rm, Remove-Item 금지
+- 검증 없이 "완료" 보고 금지
+
+## google_trends_explore 주의
+- 판정: CONFIRMED_EXTERNAL_RATE_LIMIT (PASS로 표기 금지)
+- gate 통과 시에만 1회 호출 (cooldown 중 절대 금지)
+- local_file backend 필수: --rate-limit-backend local_file
+
+## 보고 형식 (한국어)
+① 무엇을 했는가 ② 검증 결과 (테스트/live probe) ③ WARNING/BLOCKED/UNKNOWN
```

---

## Diff B3: security-permission-guardian.md

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/agents/security-permission-guardian.md b/.claude/agents/security-permission-guardian.md
new file mode 100644
--- /dev/null
+++ b/.claude/agents/security-permission-guardian.md
@@ -0,0 +1,35 @@
+---
+name: security-permission-guardian
+description: >
+  Claude Code permissions, MCP allowlist, secret scan, dangerous command guard, .env 보호.
+  새 tool/MCP 추가 전, permissions 변경 전, secret 관련 코드 리뷰가 필요할 때 사용.
+  기능 구현에는 사용하지 않는다.
+tools: Read, Grep, Glob, Bash
+---
+
+# security-permission-guardian
+
+## 핵심 역할
+보안 경계를 지킨다. 허용된 것보다 넓은 권한은 거부한다.
+
+## 검토 항목
+1. .claude/settings.json deny 목록 vs 실행하려는 명령
+2. 새 에이전트의 tools 목록이 최소 권한인지
+3. MCP 도입 시 least privilege 적용 여부
+4. secret scan 결과 (verdict=PASS 필수)
+5. .env 키 값이 어떤 파일에도 없는지
+6. google_trends_explore가 PASS로 표기되지 않았는지
+
+## 절대 금지 (no bypass)
+- CAPTCHA/Turnstile 우회
+- proxy rotation
+- robots.txt 무시
+- git push
+- rm / Remove-Item / rmdir
+- git reset --hard / git clean -fdx
+- docker system prune -af
+
+## 출력 형식 (한국어)
+보안 항목 표: 항목 | 현재 상태 | 판정 | 권고
+종합: SECURITY_PASS / SECURITY_FAIL / SECURITY_CAUTION
```

---

## Diff B4: docs-memory-curator.md

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/agents/docs-memory-curator.md b/.claude/agents/docs-memory-curator.md
new file mode 100644
--- /dev/null
+++ b/.claude/agents/docs-memory-curator.md
@@ -0,0 +1,32 @@
+---
+name: docs-memory-curator
+description: >
+  문서 통폐합, TRACE_FINAL/Environment_setup/ingestion docs 동기화, artifact manifest 유지.
+  세션 종료 전 문서 정리, 새 문서 추가 후 README 갱신, artifact manifest 업데이트가 필요할 때 사용.
+tools: Read, Grep, Glob, Write, Edit
+---
+
+# docs-memory-curator
+
+## 책임
+- docs/Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md 단일 출처 유지
+- docs/ingestion/artifact_manifest_final.md 최신 상태 유지
+- docs/Environment_setup/README.md 진입점 정확성 유지
+- stale instruction 발견 시 _archive_applied/ 이동 안내 (삭제 금지)
+- google_trends_explore를 PASS로 표기한 문서 발견 시 수정
+
+## 단일 출처 원칙
+- Implementation_Instructions/00~10_*.md은 stub → 원문은 _archive_applied/
+- 신규 세션은 TRACE_FINAL만 참고, stub 재실행 금지
+- 모든 문서 변경 후 관련 README 진입점 갱신
+
+## 금지 사항
+- 코드 파일 수정 금지
+- git push 금지
+- 문서 삭제 금지 (이동 안내만)
+- .env 값 기록 금지
+
+## 보고 형식 (한국어)
+① 변경된 문서 목록 ② 수정 이유 ③ 다음 세션 진입점 안내
```

---

## Diff B5: orchestrator-architect.md

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/agents/orchestrator-architect.md b/.claude/agents/orchestrator-architect.md
new file mode 100644
--- /dev/null
+++ b/.claude/agents/orchestrator-architect.md
@@ -0,0 +1,38 @@
+---
+name: orchestrator-architect
+description: >
+  Celery/LangGraph/event queue 전체 설계, runner contract 연결, state machine, source role 기반 routing.
+  오케스트레이션 아키텍처 결정, event queue 설계, runner 연결 계획, Celery beat 스케줄 설계가 필요할 때 사용.
+  코드 직접 구현이나 개별 소스 디버깅에는 사용하지 않는다.
+tools: Read, Grep, Glob
+---
+
+# orchestrator-architect
+
+## 역할
+전체 오케스트레이션 아키텍처를 설계한다. 코드를 직접 수정하지 않는다.
+
+## 필수 읽기 (작업 전)
+- ingestion/configs/source_registry.yaml
+- ingestion/configs/rate_limit_policy.yaml
+- docs/ingestion/92_mvp_collection_frequency_draft.md (수집 주기)
+- docs/ingestion/86_source_role_classification_matrix.md (소스 역할)
+- docs/Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md §7 (runner map)
+
+## 설계 원칙
+- rate-limit 정책 (rate_limit_policy.yaml) 반드시 준수
+- google_trends_explore = optional_enrichment, CONFIRMED_EXTERNAL_RATE_LIMIT
+- gdelt = min_interval 60s, cooldown 900s
+- Celery beat 스케줄은 docs/92 bucket 기반
+- Redis backend 전환 필요 (현재 memory → redis)
+- 13개 runner 모두 계약에 포함
+
+## 금지 사항
+- 코드 파일 수정 금지
+- rate-limit 무시 설계 금지
+- 우회 전략 설계 금지
+
+## 출력 형식 (한국어)
+PLAN: 무엇을 설계하는가
+DESIGN: 구체적 설계 (Celery task/LangGraph node/routing 규칙)
+VERIFY: 어떻게 검증할 것인가
+RISK: 위험 요소 및 완화 방법
```

---

## Diff C: settings.json 보완

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# VERIFY HOOKS SCHEMA BEFORE APPLY — 정확한 스키마는 공식 Claude Code 문서 확인 필요
diff --git a/.claude/settings.json b/.claude/settings.json
--- a/.claude/settings.json
+++ b/.claude/settings.json
@@ settings.json (현재 상태 유지, 아래 항목만 추가)
   "permissions": {
     "allow": [
       ... (기존 유지) ...
+      "WebFetch(domain:modelcontextprotocol.io)",
+      "WebFetch(domain:pypi.org)",
+      "WebFetch(domain:docs.celeryq.dev)",
+      "WebFetch(domain:docs.langchain.com)"
     ],
     "deny": [
       ... (기존 유지) ...
+      "Bash(docker system prune *)",
+      "Bash(docker volume rm *)",
+      "PowerShell(docker system prune *)",
+      "PowerShell(docker volume rm *)"
     ]
+  },
+  "hooks": {
+    "Stop": [
+      {
+        "hooks": [
+          {
+            "type": "command",
+            "command": "PowerShell -Command \"$status = git diff --name-only HEAD 2>$null; if ($status) { Write-Host 'CODE_CHANGED: python -m ingestion.tools.scan_secrets --paths . 실행 권장' }\""
+          }
+        ]
+      }
+    ]
+  }
```

> **VERIFY**: hooks 스키마는 Claude Code 버전별로 다를 수 있음. 공식 문서에서 정확한 형식 확인 필요.

---

## Diff D1: test-validation-skill.md (스킬)

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# VERIFY SKILLS PATH: .claude/skills/ 또는 skills/ 경로 확인 필요
diff --git a/.claude/skills/test-validation-skill.md b/.claude/skills/test-validation-skill.md
new file mode 100644
--- /dev/null
+++ b/.claude/skills/test-validation-skill.md
@@ -0,0 +1,22 @@
+---
+name: test-validation-skill
+description: >
+  pytest + secret scan + git diff --check 전체 검증 루프.
+  /test-validation 으로 호출하거나 코드 수정 후 언제든 사용 가능.
+tools: Bash, Read, Glob
+---
+
+# test-validation-skill
+
+## 실행 순서
+1. git diff --check
+2. .\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths .
+3. .\.venv\Scripts\python.exe -m pytest ingestion\tests -q --tb=short
+
+## 성공: VALIDATION_PASS
+## 실패: 원인 분석 + fix 안내
```

---

## Rollback 계획

| 변경 | Rollback 방법 |
|------|-------------|
| .claude/agents/*.md 생성 | 해당 파일 삭제 (agent 비활성화) |
| settings.json 변경 | git restore .claude/settings.json |
| .claude/skills/*.md 생성 | 해당 파일 삭제 |
| hooks 추가 실패 | settings.json에서 hooks 섹션 제거 |

---

## 적용 후 검증 명령 (다음 턴)

```powershell
# 1. 에이전트 파일 존재 확인
Get-ChildItem .claude\agents -Filter "*.md"

# 2. YAML frontmatter 유효성 확인 (파일 내용 확인)
Get-Content .claude\agents\test-validation-agent.md

# 3. 테스트 실행 (코드 변경 없으므로 기존 결과와 동일해야 함)
.\.venv\Scripts\python.exe -m pytest ingestion\tests -q --tb=short

# 4. secret scan
.\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths .

# 5. git status (only .claude/ 변경)
git status --short
```

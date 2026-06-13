# 04. Skills / Hooks / Plugins 설계

> **생성일**: 2026-06-13
> **목적**: 프로젝트에 필요한 Skills, Hooks, Plugins 후보 설계 및 proposed diff.
> **이번 턴 제약**: 설계 문서만. 실제 파일 생성 없음.
> **주의**: Skills/Hooks 경로 및 형식은 Claude Code 버전에 따라 다를 수 있음 (VERIFY BEFORE APPLY).

---

## Skills 개요

Skill(스킬)은 Claude Code가 특정 작업을 반복할 때 호출하는 재사용 가능한 지시 단위다.
사용자가 `/skill-name` 형식으로 호출하거나, 오케스트레이터가 태스크 유형에 따라 자동으로 호출한다.

**스킬 파일 구조 (추정 — VERIFY BEFORE APPLY):**
```
.claude/
└── skills/
    └── <skill-name>/
        └── SKILL.md    ← 스킬 지시 + trigger 조건 + 도구 목록
```

또는 단일 파일 형식:
```
.claude/skills/<skill-name>.md
```

> **VERIFY**: 정확한 스킬 디렉터리 구조와 파일 이름은 Claude Code 공식 문서에서 확인 필요.

---

## 필수 Skills 설계

### Skill 1: source-audit-skill

**목적**: 특정 소스 또는 전체 소스 상태 감사 실행
**trigger**: 소스 health 이슈 발생, 신규 소스 추가 후, 정기 주간 감사

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY
diff --git a/.claude/skills/source-audit-skill.md b/.claude/skills/source-audit-skill.md
new file mode 100644
--- /dev/null
+++ b/.claude/skills/source-audit-skill.md
@@ -0,0 +1,30 @@
+---
+name: source-audit-skill
+description: >
+  특정 소스 또는 전체 소스 수집 상태를 감사한다.
+  소스 health 이슈, 신규 소스 추가 후, 정기 감사 시 사용.
+tools: Read, Grep, Glob, Bash
+---
+
+# source-audit-skill
+
+## 감사 절차
+1. source_registry.yaml 전체 소스 목록 확인
+2. 대상 소스에 대해 run_collection_probe 실행
+3. artifact JSONL 분석 (items_found, body_extracted, status)
+4. 결과를 docs/ingestion/70_source_status_master.md 판정 기준으로 평가
+
+## 소스별 판정 기준
+- LIVE_SUCCESS + items ≥ 1 → CORE_READY
+- LIVE_SUCCESS + caution → READY_WITH_CAUTION
+- RATE_LIMITED → cooldown 정책 확인, NOT_READY_RATE_LIMITED
+- google_trends_explore 429 → CONFIRMED_EXTERNAL_RATE_LIMIT (PASS 표기 금지)
+
+## 출력 형식
+표: source_id | 수집 방식 | status | items | body | 판정 | 주의사항
+종합: CORE_READY N / CAUTION M / BLOCKED K
+
+## 금지
+- rate_limit 무시 연속 호출 금지
+- google_trends_explore 429 우회 금지
+- 실패를 PASS로 보고 금지
```

---

### Skill 2: runner-contract-skill

**목적**: 13개 runner의 agent_ready 상태 검증
**trigger**: 오케스트레이션 구현 전, runner 수정 후

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/skills/runner-contract-skill.md b/.claude/skills/runner-contract-skill.md
new file mode 100644
--- /dev/null
+++ b/.claude/skills/runner-contract-skill.md
@@ -0,0 +1,20 @@
+---
+name: runner-contract-skill
+description: >
+  13개 ingestion runner의 agent_ready 상태와 계약을 검증한다.
+  오케스트레이션 구현 전 또는 runner 수정 후 사용.
+tools: Read, Grep, Glob, Bash
+---
+
+# runner-contract-skill
+
+## 실행 명령
+.\.venv\Scripts\python.exe -m ingestion.runners.run_runner_orchestration_readiness
+
+## 성공 기준
+- 모든 13개 runner agent_ready = True
+- JSONL artifact 생성 확인
+
+## 실패 시 액션
+- agent_ready = False인 runner 목록 추출
+- 원인 분석 후 source-ingestion-engineer에 핸드오프
```

---

### Skill 3: artifact-manifest-skill

**목적**: artifact_manifest_final.md 최신 상태 유지
**trigger**: 신규 JSONL artifact 생성 후, 세션 종료 전

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/skills/artifact-manifest-skill.md b/.claude/skills/artifact-manifest-skill.md
new file mode 100644
--- /dev/null
+++ b/.claude/skills/artifact-manifest-skill.md
@@ -0,0 +1,22 @@
+---
+name: artifact-manifest-skill
+description: >
+  ingestion/outputs/ 신규 artifact를 docs/ingestion/artifact_manifest_final.md에 기록.
+  신규 JSONL artifact 생성 후 또는 세션 종료 전 사용.
+tools: Read, Glob, Write, Edit
+---
+
+# artifact-manifest-skill
+
+## 절차
+1. ingestion/outputs/jsonl/ 최신 파일 목록 확인 (Glob)
+2. artifact_manifest_final.md §2 표와 비교
+3. 누락된 항목 추가 (size, sha256 앞 16자, runner 명령, checklist 항목)
+
+## 금지
+- raw payload 전문/기사 내용 복사 금지
+- .env 키 값 기록 금지
+- git push 금지
+
+## 출력
+추가된 행 목록 + 업데이트된 매니페스트 확인
```

---

### Skill 4: docs-sync-skill

**목적**: 구현 완료 후 TRACE_FINAL 및 관련 문서 동기화
**trigger**: 새 feature 구현 완료 후

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/skills/docs-sync-skill.md b/.claude/skills/docs-sync-skill.md
new file mode 100644
--- /dev/null
+++ b/.claude/skills/docs-sync-skill.md
@@ -0,0 +1,25 @@
+---
+name: docs-sync-skill
+description: >
+  구현 완료 후 IMPLEMENTATION_TRACE_FINAL.md와 관련 문서를 동기화.
+  새 feature 구현 완료 후 사용.
+tools: Read, Grep, Glob, Write, Edit
+---
+
+# docs-sync-skill
+
+## 동기화 체크리스트
+- [ ] IMPLEMENTATION_TRACE_FINAL.md checklist 항목 업데이트
+- [ ] artifact_manifest_final.md 신규 artifact 추가
+- [ ] 해당 docs/ingestion/ 문서 갱신 섹션 추가
+- [ ] Environment_setup/README.md 진입점 유효성 확인
+- [ ] stale instruction 발견 시 _archive_applied/ 이동 안내
+
+## 금지
+- APPLIED 지시서를 다시 활성 지시로 재실행 금지
+- Implementation_Instructions/00~10_*.md stub를 원문으로 혼동 금지
```

---

### Skill 5: trend-fallback-analysis-skill

**목적**: google_trends_explore 429 시 fallback chain 실행
**trigger**: google_trends_explore RATE_LIMITED_CONFIRMED

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/skills/trend-fallback-analysis-skill.md b/.claude/skills/trend-fallback-analysis-skill.md
new file mode 100644
--- /dev/null
+++ b/.claude/skills/trend-fallback-analysis-skill.md
@@ -0,0 +1,28 @@
+---
+name: trend-fallback-analysis-skill
+description: >
+  google_trends_explore 429 시 fallback chain(trending_now → RSS export → news search)을 실행.
+  RATE_LIMITED_CONFIRMED 상태에서 대체 트렌드 데이터 수집이 필요할 때 사용.
+tools: Read, Glob, Bash
+---
+
+# trend-fallback-analysis-skill
+
+## fallback chain (순서 중요)
+A. google_trending_now (Playwright seed) — 직전 artifact 재사용 또는 신규 호출
+B. google_trends_trending_now_export (공개 RSS) — EXPORT_AVAILABLE 확인
+C. 뉴스/검색 enrichment — serper/tavily/naver로 related_candidate 생성
+
+## 실행 명령
+.\.venv\Scripts\python.exe -m ingestion.runners.run_trend_fallback_enrichment_audit --region KR
+
+## 금지 (절대)
+- google_trends_explore 429 우회 시도 금지
+- proxy rotation 금지
+- 내부 RPC 해킹 금지
+- 연속 재시도 금지 (max_retries_on_429=0)
+
+## 성공 기준
+- collected fallback source ≥ 2
+- aggregate related_candidates ≥ 5
```

---

### Skill 6: business-reality-critique-skill

**목적**: 기능/전략에 대한 현실 비판 실행
**trigger**: 새 기능 기획, MVP 릴리즈 전

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/skills/business-reality-critique-skill.md b/.claude/skills/business-reality-critique-skill.md
new file mode 100644
--- /dev/null
+++ b/.claude/skills/business-reality-critique-skill.md
@@ -0,0 +1,18 @@
+---
+name: business-reality-critique-skill
+description: >
+  기능이나 전략 제안에 대해 기술/운영/비즈니스/법무 관점의 현실 비판을 수행.
+  새 기능 기획이나 MVP 릴리즈 전 사용. adversarial-reality-critic 에이전트를 호출.
+tools: Read, Grep, Glob
+---
+
+# business-reality-critique-skill
+
+## 비판 프레임
+1. 기술: 실제로 작동하는가? 의존성? 실패 모드?
+2. 운영: 24시간 안정적인가? 장애 복구?
+3. 비즈니스: 고객이 돈을 낼 것인가? 대안은?
+4. 법무: 약관/저작권/개인정보 문제?
+5. 데이터: 실제로 사용 가능한 품질인가?
+
+## 출력: claim별 [VALID]/[QUESTIONABLE]/[FALSE] + 위험 등급 HIGH/MEDIUM/LOW
```

---

### Skill 7: legal-safety-review-skill

**목적**: 소스 약관 및 수집 방식 법무 검토
**trigger**: 신규 소스 추가 전

**proposed diff**: `legal-safety-compliance-reviewer` 에이전트를 호출하는 래퍼 스킬.
(구체적 diff는 01_CLAUDE_CODE_TEAM_AGENTS.md의 legal-safety-compliance-reviewer 참조)

---

### Skill 8: test-validation-skill

**목적**: 전체 검증 루프 실행 (pytest + secret scan + diff check)
**trigger**: 코드 수정 후 언제든

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/skills/test-validation-skill.md b/.claude/skills/test-validation-skill.md
new file mode 100644
--- /dev/null
+++ b/.claude/skills/test-validation-skill.md
@@ -0,0 +1,22 @@
+---
+name: test-validation-skill
+description: >
+  pytest + secret scan + diff check 전체 검증 루프 실행.
+  코드 수정 후 언제든, 릴리즈 게이트에서 사용.
+tools: Bash, Read, Glob
+---
+
+# test-validation-skill
+
+## 실행 순서 (반드시 이 순서)
+1. git diff --check
+2. .\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths .
+3. .\.venv\Scripts\python.exe -m pytest ingestion\tests -q --tb=short
+
+## 성공 기준
+- diff --check: 0 error
+- secret scan: verdict=PASS
+- pytest: 0 fail
+
+## 실패 시: 원인 분석 후 fix, 재실행
```

---

### Skill 9: environment-setup-skill

**목적**: 환경 설정 완료 확인 (Python venv, Docker, .env)
**trigger**: 새 환경 세팅, 신규 개발자 온보딩

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
diff --git a/.claude/skills/environment-setup-skill.md b/.claude/skills/environment-setup-skill.md
new file mode 100644
--- /dev/null
+++ b/.claude/skills/environment-setup-skill.md
@@ -0,0 +1,28 @@
+---
+name: environment-setup-skill
+description: >
+  Python venv, Docker, .env, dependencies 환경 확인. 새 환경 세팅 또는 신규 온보딩 시 사용.
+tools: Bash, Read, Glob
+---
+
+# environment-setup-skill
+
+## 확인 항목
+1. Python 버전: py -3.11 --version (3.11.x 확인)
+2. venv 활성: .venv\Scripts\python.exe --version
+3. uv 설치: uv --version
+4. Docker: docker compose version (v2 확인)
+5. .env 존재 여부: Test-Path .env (값 출력 금지, 존재 여부만)
+6. 의존성 readiness: python -m ingestion.tools.check_dependency_readiness
+
+## .env 키 목록 (존재 여부만 확인, 값 출력 절대 금지)
+필수: LANGSMITH_API_KEY, OPENAI_API_KEY, REDIS_URL
+권장: LANGSMITH_TRACING, LANGSMITH_ENDPOINT, LANGSMITH_PROJECT, MILVUS_HOST, MILVUS_PORT
+
+## 성공 기준
+- 14/14 dependency READY (check_dependency_readiness)
+- .env 존재
+- Docker compose v2 가동
```

---

## Hooks 설계

Hook(훅)은 특정 Claude Code lifecycle 이벤트에 자동으로 실행되는 셸 명령이다.
Claude Code 자체가 실행하므로 메모리/설정으로는 대체 불가.

**lifecycle 이벤트 (추정 — VERIFY BEFORE APPLY):**
- `PreToolUse`: 도구 실행 전
- `PostToolUse`: 도구 실행 후
- `Stop`: Claude Code 응답 완료 후

**hooks 설정 위치 (추정):**
```json
// .claude/settings.json 또는 .claude/hooks.json 내 hooks: {} 섹션
```

---

### Hook 1: forbidden-command-guard (PreToolUse)

**목적**: rm/Remove-Item/git push 등 금지 명령 실행 전 차단

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# VERIFY HOOKS SCHEMA BEFORE APPLY
# settings.json 내 hooks 섹션 추가 (정확한 스키마는 공식 문서 확인 필요)
+  "hooks": {
+    "PreToolUse": [
+      {
+        "matcher": "Bash|PowerShell",
+        "hooks": [
+          {
+            "type": "command",
+            "command": "PowerShell -Command \"$cmd = $env:CLAUDE_TOOL_INPUT; if ($cmd -match 'rm |Remove-Item|git push|git reset --hard|git clean|rmdir') { Write-Error 'FORBIDDEN_COMMAND_BLOCKED'; exit 1 }\""
+          }
+        ]
+      }
+    ]
+  }
```

> **VERIFY**: hooks 스키마(matcher, hooks 배열, type, command, 환경 변수명)는 공식 Claude Code 문서 확인 필요.

---

### Hook 2: pre-commit-secret-scan-reminder (Stop)

**목적**: Claude 응답 완료 후 코드 변경이 있으면 secret scan 실행 안내

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
+    "Stop": [
+      {
+        "hooks": [
+          {
+            "type": "command",
+            "command": "PowerShell -Command \"$status = git diff --name-only HEAD; if ($status) { Write-Host '⚠ 코드 변경 감지: python -m ingestion.tools.scan_secrets --paths . 실행 권장' }\""
+          }
+        ]
+      }
+    ]
```

---

### Hook 3: post-edit-test-suggestion (PostToolUse)

**목적**: Edit/Write 도구 실행 후 영향받는 테스트 실행 안내

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
+    "PostToolUse": [
+      {
+        "matcher": "Edit|Write",
+        "hooks": [
+          {
+            "type": "command",
+            "command": "PowerShell -Command \"$file = $env:CLAUDE_TOOL_RESULT_PATH; Write-Host \"수정됨: $file — 관련 테스트 실행 권장: pytest ingestion\\tests -q -k '관련 테스트 키워드'\"\""
+          }
+        ]
+      }
+    ]
```

---

### Hook 4: artifact-manifest-freshness-check (Stop)

**목적**: 새 JSONL artifact 생성 감지 후 manifest 갱신 안내

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# Stop hook에 추가
+          {
+            "type": "command",
+            "command": "PowerShell -Command \"$jsonls = Get-ChildItem ingestion\\outputs\\jsonl -Filter '*.jsonl' -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-30) }; if ($jsonls) { Write-Host '새 JSONL artifact 감지 — artifact-manifest-skill 실행 권장' }\""
+          }
```

---

### Hook 5: docs-conflict-grep-check (Stop)

**목적**: docs 변경 후 중복/충돌 문서 경고

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
+          {
+            "type": "command",
+            "command": "PowerShell -Command \"$conflicts = Select-String -Path docs -Recurse -Pattern 'google_trends_explore.*PASS' -ErrorAction SilentlyContinue; if ($conflicts) { Write-Error 'CONFLICT: google_trends_explore를 PASS로 표기한 문서 발견!' }\""
+          }
```

---

## Plugins 설계

Plugin(플러그인)은 skills + hooks + subagents + MCP를 묶는 더 큰 단위다 (추정).

**현재 평가: 당장 필요 없음.**

이유:
1. 이 프로젝트는 아직 skills/hooks 자체를 설치하지 않은 상태다.
2. plugin 레이어를 먼저 추가하면 복잡도만 증가한다.
3. plugin은 여러 프로젝트에서 재사용할 때 의미가 있다.

**권고**: skills/hooks/agents를 먼저 안정화한 후, 오케스트레이션 완성 이후에 plugin 도입 여부를 재검토.

---

## Skills/Hooks 도입 순서 (다음 턴 적용 시)

```
Phase 1 (즉시):
  test-validation-skill        ← 모든 코드 변경 후 기본 검증
  source-audit-skill           ← 소스 상태 모니터링
  artifact-manifest-skill      ← artifact 관리

Phase 2 (오케스트레이션 전):
  runner-contract-skill        ← runner 계약 검증
  docs-sync-skill              ← 문서 동기화
  environment-setup-skill      ← 환경 확인

Phase 3 (운영 안정화 후):
  trend-fallback-analysis-skill ← 트렌드 fallback
  business-reality-critique-skill ← 비즈니스 검토
  legal-safety-review-skill    ← 법무 검토

Hooks (즉시):
  forbidden-command-guard      ← 보안 최우선
  pre-commit-secret-scan-reminder ← secret 보호

Hooks (안정화 후):
  post-edit-test-suggestion    ← 개발 편의
  artifact-manifest-freshness-check ← 문서 관리
  docs-conflict-grep-check     ← 문서 일관성
```

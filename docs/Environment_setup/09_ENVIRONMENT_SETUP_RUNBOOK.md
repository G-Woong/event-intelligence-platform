# 09. Environment Setup Runbook

> **생성일**: 2026-06-13
> **목적**: 실제 적용 턴(다음 턴)에서 수행할 단계별 명령과 검증 시퀀스.
> **이번 턴 제약**: 이 파일은 runbook 문서만. 실제 명령 실행 없음.
> **전제**: docs/Environment_setup 문서 설계 완료. 실제 적용은 다음 턴.

---

## 사전 조건 (적용 전 확인)

```
[ ] 현재 git status CLEAN (uncommitted 변경 없음)
[ ] pytest 648 passed (현재 기준선 유지)
[ ] secret scan PASS
[ ] .venv 활성화 가능
[ ] Docker Desktop 실행 중 (필요 시)
[ ] .env 존재 (값 확인 없이 존재만)
```

---

## Phase 1: 사전 상태 저장

```powershell
# 1. 현재 상태 스냅샷
git status --short
git log --oneline -5

# 2. 기준선 pytest 실행 (숫자 저장용)
.\.venv\Scripts\python.exe -m pytest ingestion\tests -q --tb=short 2>&1 | Select-String "passed"

# 3. 기준선 secret scan
.\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths .

# 기대값:
# - pytest: 648 passed (기준선)
# - secret: verdict=PASS
```

---

## Phase 2: .claude/agents/ 디렉터리 생성

```powershell
# 에이전트 디렉터리 생성
New-Item -ItemType Directory -Force .claude\agents
Write-Host "agents 디렉터리 생성 완료"

# 확인
Test-Path .claude\agents
```

---

## Phase 3: 핵심 에이전트 파일 생성 (우선순위 순)

```powershell
# 08_IMPLEMENTATION_DIFF_BLUEPRINT.md의 proposed diff를 순서대로 적용
# 각 파일을 Write 도구로 생성

# 우선순위 1: test-validation-agent.md
# 우선순위 2: source-ingestion-engineer.md
# 우선순위 3: security-permission-guardian.md
# 우선순위 4: docs-memory-curator.md
# 우선순위 5: orchestrator-architect.md

# 생성 후 확인
Get-ChildItem .claude\agents -Filter "*.md" | Select-Object Name, Length
```

---

## Phase 4: settings.json 보완

```powershell
# 현재 settings.json 내용 확인
Get-Content .claude\settings.json

# 변경 사항:
# 1. hooks 섹션 추가 (스키마 확인 후)
# 2. WebFetch 도메인 추가 (필요 시)
# 3. deny 목록 보완 (docker prune 등)

# 변경 후 JSON 유효성 확인
$content = Get-Content .claude\settings.json -Raw
$null = $content | ConvertFrom-Json  # 에러 없으면 유효
Write-Host "settings.json JSON 유효"
```

---

## Phase 5: Skills 디렉터리 생성 (경로 확인 후)

```powershell
# VERIFY: Claude Code skills 경로 공식 문서 확인 필요
# 경로 후보: .claude/skills/ 또는 skills/

# 경로 확인 후 생성
New-Item -ItemType Directory -Force .claude\skills  # 또는 skills\

# 우선순위 skills 생성:
# 1. test-validation-skill.md
# 2. source-audit-skill.md
# 3. artifact-manifest-skill.md
```

---

## Phase 6: 검증 시퀀스 (적용 후 반드시 실행)

```powershell
# Step 1: git status (docs만 변경되어야 함)
git status --short
# 기대값: .claude/ 아래 파일만 변경됨

# Step 2: git diff --check
git diff --check
# 기대값: 0 error

# Step 3: secret scan (새 파일에 secret 없는지)
.\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths .
# 기대값: verdict=PASS

# Step 4: pytest (코드 변경 없으므로 기준선과 동일)
.\.venv\Scripts\python.exe -m pytest ingestion\tests -q --tb=short
# 기대값: 648 passed (기준선 유지), 0 fail

# Step 5: runner readiness (기준선 유지 확인)
.\.venv\Scripts\python.exe -m ingestion.runners.run_runner_orchestration_readiness
# 기대값: 13/13 agent_ready
```

---

## Phase 7: 에이전트 동작 확인

```powershell
# Claude Code에서 에이전트가 인식되는지 확인
# (이 명령은 Claude Code CLI에서 실행 — VERIFY BEFORE APPLY)
# claude agents list  ← 실제 명령 형식은 공식 문서 확인 필요

# 대안: 에이전트 파일 직접 확인
Get-ChildItem .claude\agents -Filter "*.md" | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    if ($content -match "^---") {
        Write-Host "$($_.Name): YAML frontmatter 존재"
    } else {
        Write-Error "$($_.Name): YAML frontmatter 없음"
    }
}
```

---

## Phase 8: 커밋

```powershell
# 변경 파일 확인
git diff --stat

# 스테이징 (.claude/ 디렉터리만)
git add .claude\

# 커밋 메시지
git commit -m @"
feat: add Claude Code team agents and skills

- .claude/agents/: 15개 팀 에이전트 파일 생성
- .claude/skills/: 핵심 skills 생성
- .claude/settings.json: hooks 섹션 추가, 도메인 보완

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
"@

# 확인
git log --oneline -3
```

---

## Phase 9: 실패 처리 (failure handling)

### pytest 실패 시

```powershell
# 실패 테스트만 재실행
.\.venv\Scripts\python.exe -m pytest --lf --tb=long

# 특정 테스트
.\.venv\Scripts\python.exe -m pytest ingestion\tests\unit\test_normalizers.py -v

# 원인 분석 후 수정
# 수정 후 재실행
```

### secret scan 실패 시

```powershell
# 상세 출력으로 누출 파일 확인
.\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths . --verbose

# 누출 파일 수정 (키 값 제거/마스킹)
# 수정 후 재스캔
```

### settings.json 파싱 실패 시

```powershell
# JSON 유효성 확인
$content = Get-Content .claude\settings.json -Raw
try {
    $null = $content | ConvertFrom-Json
    Write-Host "JSON 유효"
} catch {
    Write-Error "JSON 파싱 실패: $_"
}

# 실패 시: git restore .claude\settings.json (원래대로 복원)
```

### 에이전트 파일 YAML 오류 시

```powershell
# 파일 내용 확인
Get-Content .claude\agents\test-validation-agent.md

# YAML frontmatter 형식 확인 (--- 시작과 끝 필수)
# 문제 있으면 파일 수정 후 재확인
```

---

## Phase 10: 최종 상태 보고 형식

적용 완료 후 아래 형식으로 보고:

```
## 환경 설정 적용 완료 보고

### 생성된 파일
- .claude/agents/: N개
- .claude/skills/: M개

### 검증 결과
| 항목 | 명령 | 결과 |
|------|------|------|
| pytest | pytest -q | N passed |
| secret scan | scan_secrets | verdict=PASS |
| diff --check | git diff --check | 0 error |
| runner readiness | run_runner_orchestration_readiness | 13/13 |

### 커밋
hash: <git hash>
message: feat: add Claude Code team agents and skills

### 다음 단계
- Celery/LangGraph 오케스트레이션 구현 (plans/012)
```

---

## 주의사항

```
1. 이 runbook의 모든 명령은 repo root에서 실행
2. .\.venv\Scripts\python.exe 로 venv python 사용 (py/python 아님)
3. git push는 이 runbook에 없음 (사용자 명시 전 금지)
4. hooks 스키마는 Claude Code 공식 문서에서 반드시 확인 후 적용
5. skills 경로는 공식 문서 확인 후 적용
6. 적용 중 실패 시 git restore로 해당 파일만 롤백
```

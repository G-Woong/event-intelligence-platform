---
name: test-validation-skill
description: Run the standard validation loop after code/docs/env changes — git diff check, secret scan, targeted or full pytest, docs conflict grep, and structure checks. Use before commits and at release gates.
when_to_use: After any code change, before a commit, or at a release gate. Invoke when you need a single standardized verdict (PASS / NOT_READY / BLOCKED_BY_POLICY) covering tests, secrets, and diff hygiene.
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob
---

# test-validation-skill

프로젝트 변경(코드/문서/환경) 후 검증 루프를 표준화한다. 이 skill은 자동 실행 도구가 아니라
Claude가 따라야 하는 절차/규약/검증 runbook이다.

## when_to_use
- 코드 수정 후, 커밋 전, 릴리즈 게이트
- "검증해줘 / 테스트 돌려줘 / 커밋 전 점검" 류 요청
- skill/hook/agent 등 `.claude` 변경 후

## procedure
1. **diff hygiene**: `git diff --check` (whitespace/conflict marker 오류 0)
2. **secret scan**: 변경 범위에 맞춰 `scan_secrets` 실행 (아래 commands 참조)
3. **docs conflict grep**: google_trends_explore PASS 오표기 등 핵심 패턴 점검
4. **tests**:
   - 변경이 특정 모듈에 한정되면 targeted pytest (`-k` 키워드)
   - 수집/probe/extractor/config 등 공유 경로 변경이면 전체 pytest
   - 문서만 변경(docs-only)이면 pytest 생략 가능하되 그 사실을 명시
5. **structure checks**: `.claude/skills/*/SKILL.md` frontmatter, agent frontmatter parse
6. **status**: `git status --short`로 의도치 않은 변경 없음 확인

## commands
```powershell
git diff --check
.\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths ingestion docs plans .claude
.\.venv\Scripts\python.exe -m pytest ingestion\tests -q --tb=short
git status --short
```
- 빠른 secret scan은 변경 경로만: `--paths .claude docs/Environment_setup`

## failure conditions
- `git diff --check` 오류 → NOT_READY
- secret scan `verdict != PASS` → BLOCKED_BY_POLICY (절대 PASS로 보고 금지)
- pytest 실패 → NOT_READY (실패 테스트명/원인 보고)
- frontmatter 누락 → NOT_READY

## success criteria
- diff --check: 0 error
- secret scan: verdict=PASS
- pytest: 0 fail (docs-only면 생략 사유 명시)
- structure: 필수 frontmatter 키 존재

## safety constraints
- git push 금지 / git reset --hard 금지 / git clean 금지
- rm / Remove-Item 금지
- .env 키 값 출력 금지 (존재/길이만)
- provider 429 우회 금지
- google_trends_explore PASS 오표기 금지
- secret scan 없이 "완료" 보고 금지

## output format
```
verdict: PASS | NOT_READY | BLOCKED_BY_POLICY
tests_run: <targeted|full|skipped(reason)>
diff_check: PASS|FAIL
secret_scan: PASS|FAIL (files_scanned=N)
warnings: [...]
remaining_items: [...]
```

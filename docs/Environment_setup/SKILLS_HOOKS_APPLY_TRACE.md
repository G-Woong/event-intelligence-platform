# SKILLS_HOOKS_APPLY_TRACE.md — Skills/Hooks 적용 trace (위원회 사전·사후 평가)

> **생성일**: 2026-06-13
> **기준 문서**: `11_SKILLS_HOOKS_MCP_PLUGIN_SPEC.md`
> **이번 턴 성격**: APPLY 턴 (skills 5개 실제 생성 + hooks 3개 실제 적용)
> **단일 출처**: 적용 결과 요약은 `ENVIRONMENT_SETUP_TRACE_FINAL.md`에도 흡수됨. 이 파일은 위원회 평가 상세 기록.

---

## 0. 적용 전 상태 (PHASE 0)

| 항목 | 상태 |
|------|------|
| git status | CLEAN |
| `.claude/agents/*.md` | 15개 |
| `.claude/skills/` | 미존재 |
| `.claude/hooks/` | 미존재 |
| `.claude/settings.json` | 존재하나 **git untracked (gitignore `.claude/*`)** |
| `.claude/settings.local.json` | 존재 (gitignore, 커밋 금지) |
| secret scan (.claude, docs/Environment_setup) | PASS (files_scanned=42) |

### 중요 발견: settings.json은 git 추적 대상이 아님
- `git ls-files .claude/settings.json` → 빈 결과 (untracked)
- 과거 `5dd417d`, `aaaaa20`에서 커밋됐다가 이후 `git rm --cached` + `.claude/*` 규칙으로 추적 해제됨 (저장소의 의도적 결정)
- 영향: hook **스크립트**(`.claude/hooks/*.py`)는 커밋 가능하지만 hook **wiring**(settings.json)은 로컬 전용
- 조치: settings.json을 임의로 force-add 하지 않음 → **USER_DECISION_REQUIRED** (settings.json 추적 여부)

---

## 1. PHASE 1 — 팀 에이전트 사전 위원회 평가

적용 전, 이미 구축된 9개 에이전트 관점으로 충돌·권한·보안·운영·문서·검증 리스크를 사전 평가했다.
(에이전트 정의 `.claude/agents/*.md`의 책임 경계에 근거하여 오케스트레이터가 종합)

| # | agent | 사전 우려 | 사전 판정 |
|---|-------|----------|----------|
| 1 | security-permission-guardian | hook이 stdin JSON을 안전 파싱하나? parse 실패 시 전체 차단 위험? `.env` 읽기 차단 패턴이 `.env.example`까지 막나? | fail-open 설계 + word-boundary 패턴 요구 → APPLY_ALLOWED |
| 2 | test-validation-agent | skill frontmatter 스키마(공식)와 일치? hook smoke를 trust 없이 검증 가능? | CLI 레벨 stdin smoke 가능 → APPLY_ALLOWED |
| 3 | docs-memory-curator | TRACE_FINAL/README drift? 새 번호 문서 남발? | 새 trace 1개만, 00~10 stub 유지 → APPLY_ALLOWED |
| 4 | source-ingestion-engineer | skill이 기존 runner와 충돌? source runner 코드 수정 유발? | skill은 CLI 래핑/읽기만, runner 코드 미수정 → APPLY_ALLOWED |
| 5 | data-quality-auditor | source-audit-skill이 provider 우회/429 반복 유도? | rate gate 준수 명시, trends PASS 금지 → APPLY_ALLOWED |
| 6 | orchestrator-architect | settings.json 변경이 공식 스키마와 일치? hook 책임 경계 명확? | 공식 hooks 스키마 확인 완료 → APPLY_ALLOWED |
| 7 | adversarial-reality-critic | skill 9개 과잉? hook이 정상 개발 막나? | Phase 1 = skill 5 + hook 3로 최소화, hook 1만 차단형 → APPLY_ALLOWED |
| 8 | legal-safety-compliance-reviewer | skill 내 수집 명령이 약관 위반/우회 유도? | proxy/CAPTCHA/login 우회 금지 명시 → APPLY_ALLOWED |
| 9 | operations-sre-agent | PreToolUse hook 실패 시 전체 도구 차단? `.gitignore` 예외 과도? | fail-open + 예외는 agents/skills/hooks만 → APPLY_WITH_TRUST_PAUSE |

### 사전 위원회 결론: **APPLY_WITH_TRUST_PAUSE**
- skills는 즉시 적용 가능 (APPLY_ALLOWED).
- hooks는 적용하되, settings.json hooks 활성화 시 Claude Code의 workspace trust/재시작이 필요할 수 있음 → 라이브 활성화 검증은 사용자 trust 후로 보류.

---

## 2. PHASE 2 — 생성된 Skills (5개)

| skill | path | tools | 구조검증 |
|-------|------|-------|---------|
| test-validation-skill | `.claude/skills/test-validation-skill/SKILL.md` | Bash, Read, Grep, Glob | PASS |
| source-audit-skill | `.claude/skills/source-audit-skill/SKILL.md` | Bash, Read, Grep, Glob | PASS |
| artifact-manifest-skill | `.claude/skills/artifact-manifest-skill/SKILL.md` | Read, Glob, Grep, Write, Edit | PASS |
| docs-sync-skill | `.claude/skills/docs-sync-skill/SKILL.md` | Read, Grep, Glob, Write, Edit | PASS |
| runner-contract-skill | `.claude/skills/runner-contract-skill/SKILL.md` | Bash, Read, Grep, Glob | PASS |

구조검증: 모든 SKILL.md가 `name`/`description`/`when_to_use`/`user-invocable`/`allowed-tools` frontmatter +
`failure conditions`/`success criteria`/`safety constraints`/`output format` 본문 보유 (5/5 PASS).

외부 skill 복붙 없음 — 전부 프로젝트 맞춤 local skill로 작성.

---

## 3. PHASE 3 — .gitignore 예외

```
.claude/*
!.claude/agents/
!.claude/agents/**
!.claude/skills/      ← 추가
!.claude/skills/**    ← 추가
!.claude/hooks/       ← 추가
!.claude/hooks/**     ← 추가
.claude/settings.local.json   ← 여전히 ignore (커밋 금지)
```
- `git add --dry-run .claude/skills/` → 5개 SKILL.md 추적 가능 확인
- `git check-ignore .claude/hooks/*.py` → exit 1 (추적 가능)
- `settings.local.json` → 여전히 ignore (확인)
- 예외 범위는 agents/skills/hooks로 한정 (과도한 `.claude/**` 허용 아님)

---

## 4. PHASE 4·5 — Hooks 적용

### 공식 스키마 확인 (code.claude.com/docs/en/hooks.md)
| 항목 | 확정 |
|------|------|
| PreToolUse stdin | `{tool_name, tool_input:{command}, hook_event_name, cwd, ...}` |
| BLOCK 방식 (권장) | stdout `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"..."}}` + exit 0 |
| Stop reminder | stdout `{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":"..."}}` + exit 0 (decision:block 미사용) |
| 등록 | exec form `command:"py"`, `args:["${CLAUDE_PROJECT_DIR}/.claude/hooks/x.py"]`, `timeout` |
| trust | settings.json hooks → workspace trust 필요 (개별 hook approval 공식 미확인) |

### 적용된 hooks (3개)
| hook | path | event | mode |
|------|------|-------|------|
| forbidden-command-guard | `.claude/hooks/forbidden_command_guard.py` | PreToolUse (Bash\|PowerShell) | **차단형** (deny JSON) |
| secret-scan-reminder | `.claude/hooks/secret_scan_reminder.py` | Stop | reminder (additionalContext, 비차단) |
| docs-conflict-grep-check | `.claude/hooks/docs_conflict_grep_check.py` | Stop | reminder (additionalContext, 비차단) |

설계 원칙:
- 차단형은 forbidden-command-guard 하나뿐 (나머지는 reminder)
- 모든 hook은 stdlib만 사용, parse/IO 오류 시 **fail-open(exit 0)** → 정상 명령 미차단
- `$env:CLAUDE_TOOL_INPUT` 방식 미사용, **stdin JSON 파싱** 사용
- settings.json hooks wiring은 **로컬 전용** (settings.json이 gitignore 대상)

---

## 5. PHASE 6 — Hook smoke test + 라이브 활성화 발견

### 초기 smoke (12 케이스, 패턴 v1)
12/12 통과 (FP 0, FN 0): git status/diff/pytest/scan_secrets/npm/confirm/.env.example → ALLOW,
git push/reset --hard/rm -rf/Remove-Item/Get-Content .env/docker prune → DENY.

### 라이브 활성화 발견 + false-positive 수정
- settings.json hooks 추가 직후, **별도 trust 프롬프트 없이 hook이 라이브로 활성화됨** (프로젝트가 이미 신뢰됨).
- 라이브 hook이 commit 명령을 차단 — 원인: 커밋 메시지 본문에 문서용으로 적은 "git push" 텍스트가 v1 패턴(`\bgit\s+push\b` anywhere)에 매치 (**false positive**).
- 제약 #15에 따라 즉시 패턴을 **command-position 앵커링**으로 정밀화 (v2):
  - 위험 토큰이 명령 시작 또는 구분자(`\n` `;` `&` `|`) 직후일 때만 매치
  - 따옴표 안 텍스트(커밋 메시지/echo/grep 인자)는 통과
  - "proxy rotation"은 shell 명령이 아니므로 가드에서 제외 (보안/법무 리뷰가 담당)

### 패턴 v2 재검증 (16 케이스, gitignored 파일 기반 드라이버)
| 분류 | 결과 |
|------|------|
| 단어 언급 git push/rm -rf/Remove-Item (커밋 메시지/echo/grep) | ALLOW ✓ (FP 수정됨) |
| git status / git add / git commit(clean) / npm / cat .env.example | ALLOW ✓ |
| git push origin main / reset --hard / rm -rf / `&& rm -rf`(실제 체이닝) / Remove-Item / Get-Content .env / docker prune | DENY ✓ |
| 따옴표 안 `&& rm -rf`(커밋 메시지 내) | DENY (의도된 보수적 차단 — regex 한계, 안전 방향) |

→ 15/16 의도대로, 1건은 문서화된 보수적 차단. 흔한 FP(단어 언급)는 전부 해소.

### 라이브 재확인
`echo "...git push...rm -rf..."`(단어 언급)이 라이브 세션에서 정상 실행됨 → hook이 라이브이며 v2 스크립트 사용 확인.

### Stop hooks
- secret-scan-reminder: 변경 감지 시 additionalContext reminder, exit 0, `decision:block` 없음 ✓
- docs-conflict-grep-check: 변경 docs 없을 때 무출력 exit 0; import 단위 테스트로 오표기 탐지 + 정책 문장 제외 (5/5 OK) ✓

### 알려진 한계 (문서화)
forbidden-command-guard는 raw 명령 문자열을 regex 스캔하므로, 따옴표 안에 구분자+위험명령(`... && rm -rf ...`)이 데이터로 포함되면 보수적으로 차단할 수 있다. 이는 안전 방향의 오차이며, 실제 hard-block은 permission deny 목록이 담당한다(이중화). 커밋 메시지에는 위험 명령 시퀀스를 넣지 않는 것을 권장.

---

## 6. PHASE 7 — 팀 에이전트 사후 위원회 평가

| agent | 사후 검증 | 사후 판정 | 잔여 리스크 |
|-------|----------|----------|-----------|
| security-permission-guardian | fail-open 확인, `.env` 차단/`.env.example` 허용, deny 패턴 정확, 라이브 차단 실증 | RISK_CLOSED | - |
| test-validation-agent | v2 smoke 15/16(+1 보수적), settings.json valid, skill 구조 5/5, 라이브 확인 | RISK_CLOSED | - |
| docs-memory-curator | trace 1개 추가, 00~10 stub 유지, drift 없음 | RISK_CLOSED | - |
| source-ingestion-engineer | skill이 runner 코드 미수정, CLI 래핑만 | RISK_CLOSED | - |
| adversarial-reality-critic | hook 1개만 차단형; FP 발견 즉시 정밀화; raw-string 한계 문서화 | RISK_CLOSED | regex 한계(보수적 차단) 문서화됨 |
| operations-sre-agent | hook 실패=fail-open, 라이브 활성화 확인, settings.json 로컬 전용 | RISK_CLOSED | settings.json 추적 여부 USER_DECISION |

### 사후 위원회 결론: **RISK_CLOSED**
- skills: RISK_CLOSED — 즉시 사용 가능, 커밋됨.
- hook 스크립트: RISK_CLOSED — v2 smoke 통과(15/16, 1건 의도된 보수적 차단), 커밋됨.
- hook **라이브 활성화**: **CONFIRMED** — settings.json hooks가 별도 trust 프롬프트 없이 라이브로 동작함을 실증(라이브 차단 1회 + 라이브 허용 1회 관찰). 패턴 v2가 라이브에서 사용됨도 확인.
- 단일 잔여 사용자 결정: settings.json git 추적 여부(현재 로컬 전용).

---

## 7. 미적용/보류 항목

| item | 상태 | 이유 |
|------|------|------|
| hook 라이브 활성화 in-session 검증 | TRUST_REQUIRED | workspace trust/재시작은 사용자 조작, 자동 승인 금지 |
| settings.json git 추적 | USER_DECISION_REQUIRED | 저장소가 의도적으로 gitignore함; 임의 force-add 안 함 |
| MCP 신규 | DEFER/REJECT | 11번 명세서 결정 유지 (Semantic Scholar만 KEEP) |
| Plugin | DEFER | skills/hooks 안정화 후 |
| WebSearch/WebFetch in 4 agents | USER_DECISION_REQUIRED | 공식 지원 확인됨, 이번 턴 미적용 |
| Phase 2/3 skills (trend-fallback 등) | DEFER | 안정화 후 |
| post-edit-test-suggestion / artifact-freshness hook | DEFER | false positive 위험, 안정화 후 |

---

## 8. 사용자 결정 / 참고 사항

### Hook 라이브 활성화: CONFIRMED (별도 trust 조작 불필요했음)
settings.json hooks 섹션 추가 후 Claude Code가 **별도 trust/approval 프롬프트 없이** hook을 라이브로 적용했다(프로젝트가 이미 신뢰됨). 라이브 동작은 실제 세션에서 직접 관찰됨:
- forbidden-command-guard가 명령을 deny하는 것을 관찰(초기 FP 사건 포함, 이후 정밀화).
- 정밀화 후 단어 언급 명령이 정상 ALLOW되는 것을 관찰.
- 따라서 별도 trust 조작 없이 hook이 동작 중이다. `/hooks`로 등록 상태를 확인할 수 있다.

### settings.json git 추적: USER_DECISION_REQUIRED
- `.claude/settings.json`은 저장소가 의도적으로 gitignore함(과거 `git rm --cached`).
- 결과: hook **스크립트**는 커밋되어 공유되지만, hook **wiring**(settings.json)은 이 머신 로컬 전용.
- 다른 환경(예: codex worktree)에서 동일 hook을 쓰려면 해당 환경의 로컬 settings.json에 같은 wiring을 추가해야 함.
- settings.json을 git 추적으로 전환(force-add)할지는 사용자 결정 사항. Claude는 임의로 force-add 하지 않음.

### forbidden-command-guard 한계 (재확인)
raw 명령 문자열 regex 스캔의 한계상, 따옴표 안 `... && rm ...` 같은 데이터는 보수적으로 차단될 수 있다. 안전 방향의 오차이며, 실제 hard-block은 permission deny 목록이 이중으로 담당한다.

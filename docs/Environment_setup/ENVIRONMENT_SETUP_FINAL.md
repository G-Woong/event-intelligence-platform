# ENVIRONMENT_SETUP_FINAL

> ⚠️ **수치 SUPERSEDED (2026-06-19):** 본 문서가 인용하는 pytest 기준선(**648 passed**)은 작성 시점 기록이며 **현재 권위 수치가 아니다.** 현재값 = `docs/_CANONICAL/09_VALIDATION_AND_TESTS.md`(ingestion **1293 passed**). 환경 세팅 절차/CLOSED 상태 자체는 유효하다.

> **상태**: 환경 세팅 **CLOSED** (2026-06-13)
> **목적**: `docs/Environment_setup/`의 단일 canonical 최종 문서. 이 디렉터리에서 읽어야 할 문서는 **이 파일 하나**다.
> **다음 작업**: 오케스트레이션 설계/구현 (Celery/LangGraph, plans/012). 환경 세팅 문제로 다시 돌아올 필요 없음.

이전의 설계/명세/적용 trace 문서(00~11, README, TRACE_FINAL, SKILLS_HOOKS_APPLY_TRACE, `_archive_applied/`)의 핵심 흐름은 모두 이 문서에 흡수되었다. 원본 상세는 git history에 보존되어 있다.

---

## 1. Final Verdict

**ENVIRONMENT_SETUP_CLOSED_WITH_LOCAL_SETTINGS**

| 영역 | 최종 상태 |
|------|----------|
| 팀 에이전트 (15) | APPLIED · committed |
| Skills (5) | APPLIED · committed |
| Hook 스크립트 (3) | APPLIED · committed |
| Hook wiring (`settings.json`) | APPLIED · **local-only (의도된 결정, git 미추적)** |
| WebSearch/WebFetch in subagents | **NOT_APPLIED_BY_DESIGN** (위원회 판정) |
| MCP 신규 | NOT_APPLIED (Semantic Scholar만 KEEP) |
| Plugin | NOT_APPLIED_BY_DESIGN |
| 문서 | 이 FINAL 하나로 통합, obsolete 제거 |

환경 세팅 관련 미결(USER_DECISION_REQUIRED) 항목은 더 이상 없다. 모든 항목이 적용 또는 의도된 미적용으로 닫혔다.

---

## 2. Current Environment State

| 항목 | 값 |
|------|-----|
| OS / Shell | Windows 11 / PowerShell 5.1 |
| Python | 3.11.9 (`.venv`, uv) — `conda` 금지 |
| 런타임 격리 | Docker Desktop (compose v2) |
| Role | main orchestrator (PLAN/리뷰/통합) |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | `"1"` (settings.json `env`, project-level) |
| repo status | CLEAN |
| pytest (기준선) | 648 passed |
| source checklist | PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1 |
| runner readiness | 13/13 agent_ready |

---

## 3. Applied Components

### 3-A. 팀 에이전트 (15)

`.claude/agents/<name>.md` — YAML frontmatter(`name`, `description`, `tools`) + 본문. 모두 `git` 추적됨.

| # | agent | tools | 비고 |
|---|-------|-------|------|
| 1 | orchestrator-architect | Read, Grep, Glob | |
| 2 | source-ingestion-engineer | Read, Grep, Glob, Edit, Write | Bash 제외(안전 우선, 실행은 test-validation에 위임) |
| 3 | data-quality-auditor | Read, Grep, Glob | |
| 4 | test-validation-agent | Read, Grep, Glob, Bash | 검증 sub-role 9개 흡수 |
| 5 | adversarial-reality-critic | Read, Grep, Glob | |
| 6 | commercialization-strategist | Read, Grep, Glob | web tool 미부여 |
| 7 | legal-safety-compliance-reviewer | Read, Grep, Glob | web tool 미부여 |
| 8 | product-ux-strategist | Read, Grep, Glob | |
| 9 | docs-memory-curator | Read, Grep, Glob, Write, Edit | |
| 10 | security-permission-guardian | Read, Grep, Glob, Bash | security-redteam 흡수 |
| 11 | mcp-tooling-researcher | Read, Grep, Glob | web tool 미부여 |
| 12 | business-intelligence-analyst | Read, Grep, Glob | web tool 미부여 |
| 13 | evaluation-benchmark-agent | Read, Grep, Glob | Bash 제외(미구현 단계) |
| 14 | operations-sre-agent | Read, Grep, Glob | Bash 제외(Celery 미구현) |
| 15 | frontend-integration-agent | Read, Grep, Glob | |

**통폐합**: 검증 계열 sub-role 9개(unit-test / integration-audit / live-source-validation / secret-scan / docs-consistency / artifact-manifest / runner-readiness / env-hygiene / regression-bisect) → `test-validation-agent`. security-redteam → `security-permission-guardian`. 독립 관점이 불필요한 동일 검증 루프/도구이기 때문.

### 3-B. Skills (5)

`.claude/skills/<name>/SKILL.md` (subdirectory 레이아웃). frontmatter: `name`, `description`, `when_to_use`, `allowed-tools`. 모두 `git` 추적됨.

| skill | allowed-tools | 역할 |
|-------|---------------|------|
| test-validation-skill | Bash, Read, Grep, Glob | 표준 검증 루프(diff/secret/pytest/structure) → PASS/NOT_READY/BLOCKED_BY_POLICY |
| source-audit-skill | Read, Grep, Glob | 소스 health/rate-limit/fallback 점검 (rate gate 통과 시에만 live) |
| artifact-manifest-skill | Read, Glob, Grep, Write, Edit | outputs를 증거로 추적(경로/sha256/크기/시각/runner), 원문·secret 미복사 |
| docs-sync-skill | Read, Grep, Glob | 문서 drift 방지 grep 체크 |
| runner-contract-skill | Bash, Read, Grep, Glob | runner 출력 계약/agent_ready 검증 |

### 3-C. Hook 스크립트 (3)

`.claude/hooks/*.py` — stdlib only, stdin JSON 파싱, parse 오류 시 **fail-open(exit 0)**. 모두 `git` 추적됨.

| hook | event | mode | 동작 |
|------|-------|------|------|
| forbidden_command_guard.py | PreToolUse(Bash\|PowerShell) | **차단(deny)** | command-position 앵커링으로 destructive 명령(git push / reset --hard / clean / rm·Remove-Item·rmdir·del·erase / .env 읽기 / docker prune·volume rm) 차단. 따옴표 안 텍스트는 통과. |
| secret_scan_reminder.py | Stop | 비차단 reminder | 변경 파일 있으면 secret scan 권고 `additionalContext` 출력 |
| docs_conflict_grep_check.py | Stop | 비차단 reminder | 변경된 docs에서 status 오표기(google_trends_explore+PASS 등) 탐지 권고 |

차단형은 forbidden_command_guard **하나뿐**. 나머지 2개는 turn을 막지 않는 reminder(`decision:block` 미사용). 라이브 활성화 **CONFIRMED**(별도 trust 프롬프트 없이 동작, 차단/허용 실증).

---

## 4. Local-only Decisions

이 프로젝트는 **단일 사용자 로컬 환경** 기준이다.

- Hook **스크립트**(`.claude/hooks/*.py`)는 repo에 커밋되어 있다.
- Hook **wiring**(`.claude/settings.json`의 `hooks` 섹션)은 **local-only**로 유지한다. `.claude/settings.json`은 과거 `git rm --cached` + `.claude/*` 규칙으로 추적 해제된 저장소의 의도적 결정이다.
- 새 환경에서 hooks가 필요하면 로컬에서 settings wiring을 수동 적용한다(아래 §12 참조).
- 이는 **단일 사용자 전제 하의 의도된 결정**이다. 환경 세팅을 다시 열어야 할 OPEN risk는 아니되, 정확히는 **허용된(accepted) risk**다 — 차단형 안전 hook(`forbidden_command_guard`)은 새 환경 clone 시 자동 적용되지 않고 §12 절차로 수동 wiring해야 한다. `settings.json`을 강제로 git add 하지 않으며, `.gitignore` 예외도 추가하지 않는다. `settings.local.json`도 커밋하지 않는다.

> **현재 web 권한 표면 (main agent 레벨, 정확 기록):**
> - `.claude/settings.json` allow: `WebSearch` + `WebFetch` 9개 도메인(github.com / raw.githubusercontent.com / api.github.com / docs.anthropic.com / docs.claude.com / docs.astral.sh / arxiv.org / api.semanticscholar.org / www.semanticscholar.org).
> - `.claude/settings.local.json`(local-only, 미추적) allow: `WebFetch(domain:blog.gdeltproject.org)` 1개 추가. 즉 web 권한은 추적되는 `settings.json`과 local-only `settings.local.json` **두 소스**의 합집합이다.
> - WebFetch는 모두 도메인 화이트리스트로 한정되며, 임의 URL fetch는 불가. web 진입점은 (subagent가 아닌) main agent로 단일화되어 있다.

---

## 5. WebSearch/WebFetch Final Decision

**결정: NOT_APPLIED_BY_DESIGN** — 4개 subagent(commercialization-strategist, legal-safety-compliance-reviewer, mcp-tooling-researcher, business-intelligence-analyst)에 WebSearch/WebFetch를 부여하지 않는다. 15개 agent는 모두 `Read, Grep, Glob`만 유지하고, web 조사는 main agent로 라우팅한다(각 agent 본문에 명시된 기존 설계 유지).

팀 에이전트 위원회 판정:

| agent | 판정 | 근거 |
|-------|------|------|
| security-permission-guardian | **BLOCK** | WebFetch는 검증 안 된 외부 콘텐츠 주입(prompt injection) 신규 공격면. frontmatter는 도메인 스코핑 불가. web 진입점 단일화가 least-privilege. |
| adversarial-reality-critic | **DEFER** | 오케스트레이션 미구현·저빈도 호출에서 1-hop 절감 이득 미실현. 법무/MCP 게이트키퍼에 직접 검색은 출처 검증 책임 분산. 15개 규약 일관성 파괴. |
| orchestrator-architect | **NOT_NEEDED_NOW** | web 소비자(runner) 미존재 → dead capability. rate-limit은 단일 진입점 enforce가 원칙. |
| mcp-tooling-researcher | NEED_WEB(WebSearch만, 자기 역할 한정) | 단, "부여 결정은 security-guardian 몫" 전제 — security가 BLOCK |

판정 규칙 #1(security BLOCK → 미적용)·#3(critic 효용 낮음 → 미적용) 발동. 4명 중 3명 미적용.

**Future review trigger** (환경 risk 아님, 아키텍처 재검토용): 다음 중 하나 충족 시 `mcp-tooling-researcher`·`business-intelligence-analyst`에 **WebSearch만**(WebFetch는 계속 불가) 한정 부여를 재검토 — (1) 오케스트레이션 가동 후 main 라우팅이 실측 병목, (2) 분산 rate-limit gate 완비. 부여 시 해당 agent 본문의 "WebSearch/WebFetch not available" 문구를 동기화 정정할 것.

---

## 6. MCP Final Decision

신규 MCP 설치 없음. `.mcp.json` 미생성/미수정. 기존 Python runner(API/Playwright/url_resolver/body_extractor)와 중복되며, 오케스트레이션 전 단계에서 권한 공격면만 늘린다는 위원회 판단.

| MCP 범주 | 결정 | 근거 | future trigger |
|----------|------|------|----------------|
| Semantic Scholar | **KEEP** | 이미 활성(`mcp__semantic-scholar__search_paper`), readonly 검색, 저위험 | — |
| Filesystem | **REJECT** | 기존 Read/Write/Edit 충분, `.env` 직접 접근 위험 | 재도입 안 함 |
| Browser | **REJECT** | `playwright_probe.py` 구현 완료, CAPTCHA 우회 오해/보안 위험 | 재도입 안 함 |
| Code Execution | **REJECT** | sandbox 탈출 CRITICAL 위험 | 재도입 안 함 |
| Web Fetch/Search MCP | **DEFER** | main agent의 WebSearch/WebFetch로 충분 | web 수요 실증 시 |
| GitHub | **DEFER** | readonly token + repo workflow 필요 시 | repo 자동화 필요 시 |
| Postgres | **DEFER** | event DB 미구현 | event DB 구현 후 |
| Redis / Celery | **DEFER** | Celery 운영 전 | Celery 운영 후 |
| Vector DB (Milvus) | **DEFER** | claim graph/vector retrieval 미설계 | 벡터 검색 설계 후 |
| Monitoring/Logging (LangSmith) | **DEFER** | service runtime 미존재 | 서비스 런타임 후 |

REJECT 3 / KEEP 1 / DEFER 6. DEFER는 환경 세팅 risk가 아니라 **오케스트레이션 단계의 future architecture review**다.

---

## 7. Plugin Final Decision

**결정: NOT_APPLIED_BY_DESIGN**

- Plugin은 skills/agents/hooks/MCP를 묶는 배포/패키징 레이어다. 여러 프로젝트/팀 배포 시 유용하나, 단일 사용자·단일 repo에는 premature.
- agents/skills/hooks가 이미 repo-local로 관리되고 있어 패키징 이점이 없고, plugin으로 묶으면 rollback/디버깅 복잡도만 증가.
- **future trigger**: 환경을 다른 프로젝트/사용자에 공유·재사용할 필요가 생길 때만 도입.

---

## 8. Risk Closure Table

| risk | previous status | final action | final status |
|------|-----------------|--------------|--------------|
| hook wiring(settings.json) git 공유 | USER_DECISION_REQUIRED | 단일 사용자 → local-only 유지, hook 스크립트만 커밋, §12에 setup note | **CLOSED** (의도된 결정) |
| WebSearch/WebFetch in subagents | USER_DECISION_REQUIRED | 위원회 BLOCK/DEFER → 미적용, web은 main 라우팅 | **CLOSED** (NOT_APPLIED_BY_DESIGN) |
| MCP 신규 도입 | NEXT_TURN_MCP_REVIEW | 범주별 KEEP/DEFER/REJECT 확정 | **CLOSED** (의도된 미적용, DEFER는 future review) |
| Plugin 도입 | DEFERRED | 단일 프로젝트 이점 없음 | **CLOSED** (NOT_APPLIED_BY_DESIGN) |
| hook이 정상 명령 차단(FP) | 발견됨(커밋 메시지 "git push") | command-position 앵커링(v2), 따옴표 텍스트 통과 | **CLOSED** |
| hook parse 실패 시 전체 차단 | 잠재 위험 | fail-open(exit 0) 설계 | **CLOSED** |
| 문서 drift/중복 | 다수 trace/spec 문서 | 이 FINAL 하나로 통합, obsolete 제거 | **CLOSED** |
| source-ingestion-engineer Bash 권한 | USER_DECISION_REQUIRED | 안전 우선 미부여 유지, 실행은 test-validation-agent 위임 | **CLOSED** (의도된 결정) |
| `permissions.allow`의 `Bash(*)`/`PowerShell(*)` 와일드카드 | 명시 안 됨 | deny 우선 모델 + forbidden_command_guard hook이 destructive 명령군을 이중 커버. 보안 경계는 deny 목록·hook의 완전성에 의존 | **CLOSED** (이중 방어, 명령군 확장 시 deny+hook 동시 갱신) |

환경 세팅 관련 OPEN risk: **없음** (위 항목은 의도된 결정 또는 허용된 risk로 분류·문서화됨).

---

## 9. Remaining Non-Risk Future Work

환경 세팅 risk가 아니라 다음 아키텍처 단계의 작업이다.

- **NEXT_TURN_ORCHESTRATION**: Celery/LangGraph 오케스트레이션 설계·구현 (plans/012). 본 환경 세팅의 후속 단계.
- MCP future review: 위 §6의 DEFER 항목들은 각 trigger(event DB / Celery / 벡터 검색 / 서비스 런타임) 충족 시에만 재검토.
- WebSearch(subagent) future review: §5 trigger 충족 시.

---

## 10. Validation Results (2026-06-13 closure)

| 검증 항목 | 결과 |
|---------|------|
| git diff --check | PASS (0 error) |
| secret scan (`.claude docs/Environment_setup`) | PASS (51 files) |
| secret scan (`ingestion docs plans .claude`) | PASS (1932 files) |
| `.claude/settings.json` JSON parse | VALID |
| hook py_compile (3/3) | OK |
| skill 구조 (frontmatter + safety + success criteria) | 5/5 PASS |
| agent frontmatter (15) | 15/15 PASS |
| docs grep (google_trends_explore PASS 오표기 / MCP·Plugin 오적용 주장 / 잔존 USER_DECISION_REQUIRED) | PASS (없음) |
| pytest | 생략 — 이번 턴은 `.claude`/docs만 변경, hook은 stdlib-only로 프로젝트 import 없음 → 회귀 영향 없음 |
| git status | CLEAN (커밋 후) |

---

## 11. Commit History

| 커밋 | 내용 |
|------|------|
| `18f4766` | docs: design environment setup for agent orchestration (12개 설계 문서) |
| `d8325bc` | env: apply claude code team agents (15개 에이전트) |
| `3047938` | docs: consolidate environment setup agent docs |
| `345ae14` | docs: specify skills hooks mcp plugin adoption plan (11번 명세서) |
| (APPLY) | env: add project skills for validation workflows (skills 5 + .gitignore) |
| (APPLY) | env: add safety hooks for claude code (hook 스크립트 3, settings.json은 local-only) |
| (APPLY) | docs: record skills hooks apply trace |
| (CLOSE) | env: finalize claude code environment decisions |
| (CLOSE) | docs: consolidate environment setup final state |

---

## 12. New Session Entry Instructions

신규 세션은 이 문서 하나만 읽으면 환경 상태를 전부 파악할 수 있다.

**새 로컬 환경에서 hooks가 필요한 경우** (local-only wiring 수동 적용):
`.claude/settings.json`에 아래 구조를 추가한다(스크립트는 이미 repo에 있음).

```jsonc
"hooks": {
  "PreToolUse": [
    { "matcher": "Bash|PowerShell",
      "hooks": [{ "type": "command", "command": "py",
        "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/forbidden_command_guard.py"],
        "timeout": 10 }] }
  ],
  "Stop": [
    { "hooks": [
      { "type": "command", "command": "py", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/secret_scan_reminder.py"], "timeout": 10 },
      { "type": "command", "command": "py", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/docs_conflict_grep_check.py"], "timeout": 10 }
    ] }
  ]
}
```

---

## 13. Forbidden Actions (모든 에이전트·세션 공통)

```
- google_trends_explore: CONFIRMED_EXTERNAL_RATE_LIMIT (PASS 표기 절대 금지)
  fallback chain: google_trending_now → RSS export → serper/naver
- gdelt: min_interval 60s, cooldown 900s
- .env 키 값 출력 금지 (존재/길이만)
- git push / git reset --hard / git clean 금지
- rm / Remove-Item / del / erase / rmdir 금지
- docker system prune / docker volume rm·prune 금지
- CAPTCHA/로그인/페이월 우회 금지, proxy rotation 금지, internal RPC scraping 금지
- 투자 조언 금지 (정보 제공이지 투자 조언 아님)
- 검증 없이 "완료" 보고 금지
```

---

## 14. Next Step

환경 세팅은 **CLOSED**다. 다음 작업은 **오케스트레이션 설계/구현**(Celery/LangGraph, plans/012)이다. 환경 세팅 문제로 이 문서로 다시 돌아올 필요는 없다.

---

## 연관 문서 (이 디렉터리 외부)

- [`docs/Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md`](../Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md) — 소스 수집 구현 단일 출처
- [`docs/ingestion/INGESTION_FINAL.md`](../ingestion/INGESTION_FINAL.md) — 전체 소스 상태 (단일 출처)
- [`docs/ingestion/artifact_manifest_final.md`](../ingestion/artifact_manifest_final.md) — Artifact 매니페스트

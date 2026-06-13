# 00. Environment Setup Master — 프로젝트 베이스라인 및 설계 개요

> **생성일**: 2026-06-13
> **목적**: 오케스트레이션 구현 전 환경 구축 설계의 단일 진입점. 프로젝트 현재 상태와 전체 설계 의도를 기록.
> **이번 턴 제약**: 문서 및 proposed diff 작성만. 실제 config 수정 없음.

---

## 1. Project Baseline Snapshot (2026-06-13 기준)

### 1.1 런타임 환경

| 항목 | 값 | 출처 |
|------|-----|------|
| OS | Windows 11 Home 10.0.26200 | CLAUDE.md |
| Shell | PowerShell 5.1 (Bash tool도 가용) | CLAUDE.md |
| Python | 3.11.9 (`.venv`, uv 기반) | CLAUDE.md |
| 패키지 매니저 | uv (`conda` 금지) | CLAUDE.md |
| 런타임 격리 | Docker Desktop (compose v2) | CLAUDE.md |
| Compose project | `event-intelligence-dev` | CLAUDE.md |
| Compose file | `docker-compose.dev.yml` | CLAUDE.md |
| 작업 디렉터리 | `C:\Users\computer\Desktop\business\claude` | CLAUDE.md |
| Branch | `main` | git status |

### 1.2 Claude Code 설정 현황 (`.claude/settings.json` 실측)

```
model: opusplan
language: korean
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1"  ← 팀 에이전트 실험 기능 이미 활성화
enableAllProjectMcpServers: false           ← MCP 서버 전역 비활성화 (기본값)
```

- **팀 에이전트**: 환경 변수 설정 완료. `.claude/agents/` 디렉터리는 아직 미생성.
- **MCP**: `enableAllProjectMcpServers: false`. 현재 등록된 MCP 서버 없음.
- **Skills**: `.claude/skills/` 디렉터리 미생성. 프로젝트 레벨 skills 없음.
- **Hooks**: 설정 없음. `hooks:` 섹션 미존재.
- **권한 deny 목록**: git push, rm/del/erase/rmdir/Remove-Item, git reset --hard, git clean -fdx — 모두 명시적으로 차단됨.

### 1.3 소스 수집 레이어 상태 (docs/70 기준)

| 판정 | 수 | 의미 |
|------|----|------|
| CORE_READY | 38 | 즉시 파이프라인 연결 가능 |
| READY_WITH_CAUTION | 6 | 조건부 수집 가능 (quota/약관 주의) |
| DEFERRED_SPECIAL_ROUND | 1 | krx_kind (공식 API 전환 필요) |
| MVP_DEFERRED | 1 | reddit (rate limit 변동성) |
| MVP_EXCLUDED | 5 | 구조적 장벽 (라이선스·로그인·봇 차단) |
| UNKNOWN | 6 | Phase 1 정적 뉴스 소스 재프로브 필요 |

- **google_trends_explore**: `CONFIRMED_EXTERNAL_RATE_LIMIT`. optional_enrichment, fallback chain으로 비차단. **NOT_READY_EXTERNAL_RATE_LIMIT** — PASS로 표기 금지.

### 1.4 테스트/검증 상태

| 항목 | 값 | 출처 |
|------|----|------|
| pytest | 648 passed, 0 fail | 사용자 제공 |
| secret scan | verdict=PASS, WARNING 0, 실제 leak 0 | closing_checklist.md |
| runner orchestration | 13/13 agent_ready | IMPLEMENTATION_TRACE_FINAL §7 |
| source checklist | PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1 | closing_checklist.md |
| env hygiene | AMBIGUOUS_ALIAS 6건 (기능 영향 없음) | TRACE_FINAL §9 |

### 1.5 핵심 인프라 파일 현황

| 파일 | 상태 | 비고 |
|------|------|------|
| `.claude/settings.json` | 존재, 설정 완료 | CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 |
| `.claude/settings.local.json` | 존재 | GDELT 블로그 domain 허용 |
| `.claude/agents/` | **미생성** | 다음 턴에 생성 필요 |
| `skills/` | **미생성** | 다음 턴에 생성 필요 |
| `AGENTS.md` | **없음** | 필요 시 root에 생성 가능 |
| `agents.toml` | **없음** | 없어도 됨 (agents/ 디렉터리 방식 사용) |
| `ingestion/configs/source_registry.yaml` | 존재 | 57개 소스 등록 |
| `ingestion/configs/rate_limit_policy.yaml` | 존재 | per-source 정책 포함 |
| `ingestion/configs/playwright_probe_sites.yaml` | 존재 | Playwright 사이트 spec |

### 1.6 다음 단계 (환경 설계 이후)

```
1. docs/Environment_setup 문서 적용 (다음 턴)
   → .claude/agents/ 생성
   → skills/ 생성
   → hooks 설정
   → permissions 보완

2. Celery/LangGraph 오케스트레이션 구현 (plans/012)
   → Event Queue 설계
   → Runner 연결
   → Rate-limit-aware scheduler
   → Redis backend 전환
```

---

## 2. 설계 의도 및 원칙

### 2.1 왜 지금 환경 설계인가

오케스트레이션 구현 전에 다음이 필요하다:
- **다중 에이전트 협업** 구조 (orchestrator-architect + 각 specialist)
- **보안 경계** (MCP/tool 허용 범위, .env 보호)
- **검증 루프** (코드 변경 → 테스트 → audit → 보고)
- **현실 비판** (비즈니스/상용화/법무 관점 동시 검토)

단일 에이전트가 오케스트레이션을 설계하면 편향이 생긴다. 팀 에이전트 구조가 필요한 이유다.

### 2.2 설계 원칙

| 원칙 | 적용 방식 |
|------|----------|
| Least privilege | MCP/tool은 최소 허용. 전역 허용 금지 |
| No bypass | rate-limit 우회, CAPTCHA 우회, proxy rotation 금지 |
| Separation of concerns | 각 에이전트는 단일 책임 |
| Verify before claim | 테스트 없이 "완료" 보고 금지 |
| 추정/공식/실험 구분 | 공식 문서 근거 vs 추정 vs 실험 필요를 명시 |

### 2.3 팀 에이전트 구성 개요

```
오케스트레이터 계층
├── orchestrator-architect     (Celery/LangGraph/event queue 설계)
├── docs-memory-curator        (문서 통폐합/TRACE_FINAL 관리)
└── security-permission-guardian (권한/MCP/보안 게이팅)

구현 계층
├── source-ingestion-engineer  (수집 runner/rate-gate)
├── data-quality-auditor       (품질/중복/boilerplate)
├── test-validation-agent      (pytest/scan/diff)
└── operations-sre-agent       (Celery/Redis/Postgres 운영)

비판/현실 계층
├── adversarial-reality-critic (기술/운영 리스크 공격)
├── commercialization-strategist (상용화 전략)
├── legal-safety-compliance-reviewer (법무/약관/저작권)
├── business-intelligence-analyst (시장 인사이트 변환)
└── product-ux-strategist      (UX/trust indicators)

연구/도구 계층
├── mcp-tooling-researcher     (MCP 후보 평가)
├── evaluation-benchmark-agent (메트릭/벤치마크 설계)
└── frontend-integration-agent (API contract/UI)
```

---

## 3. 추정/공식/실험 필요 구분

> 이 섹션은 이 문서 전체의 정보 출처 신뢰도를 명시한다.

### 공식 문서/프로젝트 근거 (HIGH confidence)

- Claude Code agent 파일 구조: `.claude/agents/<name>.md` (YAML frontmatter + instruction body)
- Claude Code 환경 변수 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`: 설정 파일에서 이미 확인
- Python venv, uv, Docker Compose: CLAUDE.md 및 프로젝트 코드에서 확인
- 소스 수집 상태: docs/70, closing_checklist.md, runner JSONL 실측

### 추정 (ESTIMATED — verify before implementation)

- Claude Code agent YAML의 정확한 스키마 필드: `name`, `description`, `tools` 외 추가 필드는 공식 문서 확인 필요
- hooks 설정 방식: `settings.json`의 `hooks:` 섹션 정확한 스키마는 실험 필요
- Claude Code skills 구조: `.claude/skills/` 경로 및 `SKILL.md` 형식은 추정
- MCP 서버별 security boundary: 공식 MCP 문서에서 확인 필요

### 실험 필요 (VERIFY BEFORE APPLY)

- 팀 에이전트 위임(delegation) 실제 동작: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 하에서 어떤 에이전트가 선택되는지 실험 필요
- hooks lifecycle 정확한 이름: `PreToolUse`, `PostToolUse`, `Stop` 등의 정확한 이벤트 이름
- MCP stdio vs http 선택: 실제 설치 후 안정성 확인 필요

---

## 4. 전체 설계 파일 맵

| 파일 | 담당 설계 영역 |
|------|---------------|
| [01_CLAUDE_CODE_TEAM_AGENTS.md](./01_CLAUDE_CODE_TEAM_AGENTS.md) | 15개 팀 에이전트 상세 설계 |
| [02_AGENT_COMMITTEE_WORKFLOWS.md](./02_AGENT_COMMITTEE_WORKFLOWS.md) | 5개 위원회 워크플로우 |
| [03_MCP_AND_TOOLING_SURVEY.md](./03_MCP_AND_TOOLING_SURVEY.md) | MCP/Tool 채택 판정표 |
| [04_SKILLS_HOOKS_PLUGINS_DESIGN.md](./04_SKILLS_HOOKS_PLUGINS_DESIGN.md) | Skills/Hooks/Plugins |
| [05_SECURITY_PERMISSIONS_POLICY.md](./05_SECURITY_PERMISSIONS_POLICY.md) | 보안·권한 정책 |
| [06_TEST_VALIDATION_AGENTS.md](./06_TEST_VALIDATION_AGENTS.md) | 검증 에이전트 10종 |
| [07_WEB_INTELLIGENCE_PIPELINE_ENVIRONMENT.md](./07_WEB_INTELLIGENCE_PIPELINE_ENVIRONMENT.md) | 파이프라인 환경 설계 |
| [08_IMPLEMENTATION_DIFF_BLUEPRINT.md](./08_IMPLEMENTATION_DIFF_BLUEPRINT.md) | 실제 diff 블루프린트 |
| [09_ENVIRONMENT_SETUP_RUNBOOK.md](./09_ENVIRONMENT_SETUP_RUNBOOK.md) | 적용 runbook |
| [10_FINAL_ENVIRONMENT_AUDIT_CHECKLIST.md](./10_FINAL_ENVIRONMENT_AUDIT_CHECKLIST.md) | 최종 감사 체크리스트 |

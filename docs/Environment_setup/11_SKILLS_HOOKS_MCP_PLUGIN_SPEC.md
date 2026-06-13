# 11_SKILLS_HOOKS_MCP_PLUGIN_SPEC.md — Skills / Hooks / MCP / Plugin 구현 명세서

> **생성일**: 2026-06-13
> **분류**: SPEC 문서 (APPLY 문서 아님). 이번 턴에서 실제 `.claude/skills/`, hooks, MCP config를 수정하지 않는다.
> **목적**: 팀 에이전트 위원회 평가 → 외부 후보 선별 → 다음 턴 apply 기준 확립.
> **다음 턴 진입점**: 이 문서의 `§7 Recommended Phase 1 Apply Set` → `§14 Next Turn Implementation Plan`.
> **NEVER_APPLY_DIRECTLY**: 이 문서를 직접 실행하지 마라. 스펙 확인 후 별도 APPLY 턴에서 적용.

---

## 0. 공식 문서 조사 결과 (이번 턴 핵심 발견)

이번 턴에서 Claude Code 공식 문서를 조사한 결과 설계 문서(04번)와 다른 중요 사항이 발견됐다.

| 항목 | 이전 설계 문서(04) 가정 | 공식 문서 확인 결과 | 영향 |
|------|----------------------|-------------------|------|
| Skills 경로 | `.claude/skills/<name>.md` (flat file) | `.claude/skills/<name>/SKILL.md` (**subdirectory 필수**) | 다음 턴 경로 전면 수정 |
| Skills frontmatter 필드 | `name`, `description`, `tools` (agent 파일과 동일) | `name`, `description`, `when_to_use`, `user-invocable`, `allowed-tools`, `disallowed-tools`, `model` 등 **별도 스키마** | frontmatter 재작성 필요 |
| Hooks 입력 방식 | `$env:CLAUDE_TOOL_INPUT` (환경 변수) | **stdin JSON** 파싱 (env var 아님) | hook 명령 재작성 필요 |
| WebSearch/WebFetch in agents | UNKNOWN (공식 미확인으로 제외) | **공식 지원 확인** (`tools: Read, Grep, WebSearch`) | 4개 에이전트 frontmatter 업데이트 후보 |
| MCP 설정 파일 | `.claude/mcp_config.json` (추정) | **.mcp.json** (프로젝트 루트) 또는 `~/.claude.json` | 설정 파일 경로 확정 |
| Hooks 설정 위치 | settings.json `hooks` 섹션 | settings.json `hooks` 섹션 (동일) | 변경 없음 |
| Agent teams 상태 | experimental | **experimental 유지** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 필수) | 변경 없음 |
| Agent frontmatter `model` | 생략(기본 모델) 권장 | 지원 확인 (`sonnet`/`opus`/`haiku`/`fable`/`inherit`) | 필요 시 추가 가능 |

---

## 1. 목적

이 문서는 웹 인텔리전스 플랫폼 프로젝트의 **skills/hooks/MCP/plugin 적용을 위한 구현 명세서**다.

- **이번 턴**: 조사·평가·명세서 작성만. 실제 `.claude/skills/`, hooks, MCP config 수정 없음.
- **다음 턴**: 이 명세서 기반으로 Phase 1 Apply Set을 적용.
- **기준**: 공식 문서 조사 결과 + 팀 에이전트 12개 관점 위원회 평가.

---

## 2. Project Fit Baseline

### 2-A. 현재 코드/운영 상태

| 항목 | 상태 | 상세 |
|------|------|------|
| 수집 pipeline | 운영 가능 | Route 1(API) + Route 2(Playwright) + Route 3(RSS/HTML fallback) |
| 소스 수 | 58개 (CORE_READY 38, CAUTION 6, DEFERRED 2, EXCLUDED 5, UNKNOWN 6) | source_registry.yaml + YAML 미등록 1 |
| runner readiness | 13/13 agent_ready | run_runner_orchestration_readiness 실측 |
| pytest | 648 passed | 코드 결함 0 |
| secret scan | PASS | scan_secrets 전체 |
| google_trends_explore | CONFIRMED_EXTERNAL_RATE_LIMIT | optional_enrichment, fallback chain 구현됨 |
| gdelt | PASS (min_interval 60s) | live LIVE_SUCCESS, soft-limit 보수 정책 |

### 2-B. 현재 toolchain (MCP 없이 이미 구현된 것)

| 기능 | 구현체 | 위치 |
|------|--------|------|
| API 수집 | api_probe | `ingestion/probes/api_probe.py` |
| Playwright 수집 | playwright_probe | `ingestion/probes/playwright_probe.py` |
| body 추출 cascade | site_selector→trafilatura→readability→dom | `ingestion/fetch_strategies/` |
| secret scan | scan_secrets | `ingestion/tools/scan_secrets.py` |
| rate-limit gate | gate_check | `ingestion/probes/collection_probe.py` |
| feed 탐색 | feed_discovery | `ingestion/tools/feed_discovery.py` |
| URL 정규화 | url_resolver | `ingestion/tools/url_resolver.py` |
| runner 오케스트레이션 | run_runner_orchestration_readiness | `ingestion/runners/` (13개 CLI) |
| trend fallback | run_trend_fallback_enrichment_audit | `ingestion/runners/` |
| dependency check | check_dependency_readiness | `ingestion/tools/` |
| env hygiene | check_env_hygiene | `ingestion/tools/` |

**결론**: Python runner가 이미 대부분의 수집/검증 기능을 커버한다. MCP 추가 가치는 낮다.

### 2-C. 팀 에이전트 현황

| 항목 | 상태 |
|------|------|
| 에이전트 수 | 15개 (.claude/agents/*.md) |
| CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS | "1" (settings.json, project-level) |
| WebSearch/WebFetch in agents | 이전: 제외 (공식 미확인) → 이번 조사: 공식 지원 확인 |
| skills 연동 | agent frontmatter에 `skills` 필드 지원 확인 |

### 2-D. 환경 제약

| 제약 | 내용 |
|------|------|
| OS | Windows 11, PowerShell 5.1 |
| shell | PowerShell 우선, Bash 보조 |
| hooks 명령 | PowerShell 문법 사용 |
| stdin JSON 파싱 | `$input \| ConvertFrom-Json` (Windows PS 주의: `$input`은 PS automatic var) |
| Destructive 금지 | rm, Remove-Item, git push, git reset --hard, git clean |
| google_trends_explore | PASS 표기 절대 금지 |

---

## 3. External Candidate Inventory

### 3-A. Skills 후보

| 후보명 | 출처 | 유형 | 비고 |
|--------|------|------|------|
| test-validation-skill | 내부 설계 (04번 문서) | project-local | 외부 복사 아님 |
| source-audit-skill | 내부 설계 (04번 문서) | project-local | |
| artifact-manifest-skill | 내부 설계 (04번 문서) | project-local | |
| docs-sync-skill | 내부 설계 (04번 문서) | project-local | |
| runner-contract-skill | 내부 설계 (04번 문서) | project-local | |
| trend-fallback-analysis-skill | 내부 설계 (04번 문서) | project-local | |
| environment-setup-skill | 내부 설계 (04번 문서) | project-local | |
| business-reality-critique-skill | 내부 설계 (04번 문서) | project-local | |
| legal-safety-review-skill | 내부 설계 (04번 문서) | project-local | |
| Claude Code 공식 example skills | 공식 문서 | official_example | 참고만, 직접 복사 금지 |
| 커뮤니티 GitHub skill 예시 | 커뮤니티 | community | study-only |

> **판정**: 외부 skill 직접 복사 없음. 모두 프로젝트 맞춤 작성 (ADAPT_PROJECT_LOCAL).

### 3-B. Hooks 후보

| 후보명 | 이벤트 | 출처 |
|--------|--------|------|
| forbidden-command-guard | PreToolUse | 내부 설계 (04번 문서) |
| pre-commit-secret-scan-reminder | Stop | 내부 설계 (04번 문서) |
| docs-conflict-grep-check | Stop | 내부 설계 (04번 문서) |
| post-edit-test-suggestion | PostToolUse | 내부 설계 (04번 문서) |
| artifact-manifest-freshness-check | Stop | 내부 설계 (04번 문서) |

### 3-C. MCP 후보

| 후보 | 출처 | 현재 판정 |
|------|------|---------|
| mcp__semantic-scholar | settings.json allow 목록 | ALREADY_ACTIVE |
| GitHub MCP | 공식 (@modelcontextprotocol/server-github) | DEFER |
| Postgres MCP | 공식 | DEFER (DB 미도입) |
| Redis MCP | 커뮤니티 | DEFER (Redis 미도입) |
| Filesystem MCP | 공식 | REJECT |
| Browser/Playwright MCP | 공식+커뮤니티 | REJECT |
| Web Fetch MCP | 공식 | DEFER (WebFetch tool로 충분) |
| Vector DB (Milvus) MCP | 커뮤니티 | DEFER (오케스트레이션 이후) |
| LangSmith MCP | 커뮤니티 | DEFER (LangGraph 미구현) |
| Code Execution MCP | 커뮤니티 | REJECT (CRITICAL 보안) |

### 3-D. Plugins 후보

현재 skills/hooks/agents 자체가 안정화되지 않은 상태. Plugin은 이들을 번들하는 상위 개념으로,
지금 도입하면 복잡도만 증가한다.

**판정**: 전체 DEFER.

---

## 4. Candidate Evaluation Matrix

### 4-A. Skills

| candidate_name | category | source_type | purpose | overlaps_existing | requires_shell | prompt_injection_risk | supply_chain_risk | recommended_action | reason |
|----------------|----------|-------------|---------|-------------------|----------------|-----------------------|-------------------|--------------------|--------|
| test-validation-skill | skill | project-local | pytest+secret scan+diff check 검증 루프 | test-validation-agent와 목적 유사하나 skill은 사용자 트리거 | Yes (Bash) | LOW | NONE | ADAPT_PROJECT_LOCAL | 외부 skill 아님. agent와 병존 가능(skill=사용자 트리거, agent=Claude 내부 위임) |
| source-audit-skill | skill | project-local | 소스 health 감사 | source-ingestion-engineer와 유사하나 읽기+실행 | Yes (Bash) | LOW | NONE | ADAPT_PROJECT_LOCAL | runner CLI 호출, 외부 의존 없음 |
| artifact-manifest-skill | skill | project-local | artifact manifest 동기화 | docs-memory-curator와 유사하나 skill=즉시 실행 | No (Read+Write) | LOW | NONE | ADAPT_PROJECT_LOCAL | 외부 의존 없음 |
| docs-sync-skill | skill | project-local | TRACE_FINAL 및 관련 문서 동기화 | docs-memory-curator와 유사 | No (Read+Write+Edit) | LOW | NONE | ADAPT_PROJECT_LOCAL | |
| runner-contract-skill | skill | project-local | 13개 runner agent_ready 검증 | test-validation-agent 일부 | Yes (Bash) | LOW | NONE | ADAPT_PROJECT_LOCAL | |
| trend-fallback-analysis-skill | skill | project-local | fallback chain 실행 | source-ingestion-engineer의 일부 | Yes (Bash) | LOW | NONE | ADAPT_PROJECT_LOCAL | |
| environment-setup-skill | skill | project-local | 환경 점검 (venv/Docker/.env) | 없음 | Yes (Bash) | LOW | NONE | ADAPT_PROJECT_LOCAL | Phase 2 (즉시성 낮음) |
| business-reality-critique-skill | skill | project-local | adversarial 비판 트리거 | adversarial-reality-critic 래퍼 | No (Read+Glob) | LOW | NONE | ADAPT_PROJECT_LOCAL | Phase 2 |
| legal-safety-review-skill | skill | project-local | 법무 검토 트리거 | legal-safety-compliance-reviewer 래퍼 | No (Read+Glob) | LOW | NONE | ADAPT_PROJECT_LOCAL | Phase 3 |

### 4-B. Hooks

| candidate_name | event | blocking | false_positive_risk | shell_complexity | recommended_action | reason |
|----------------|-------|----------|--------------------|-----------------|--------------------|--------|
| forbidden-command-guard | PreToolUse | Yes (exit 1) | MEDIUM | HIGH (stdin JSON 파싱 필요) | ADAPT_PROJECT_LOCAL | 핵심 보안. 단, stdin JSON 파싱 방식 수정 필요 |
| pre-commit-secret-scan-reminder | Stop | No (알림만) | LOW | LOW | ADAPT_PROJECT_LOCAL | 안전, 가치 높음 |
| docs-conflict-grep-check | Stop | No (알림만) | LOW | LOW | ADAPT_PROJECT_LOCAL | google_trends_explore PASS 오표기 방어 |
| post-edit-test-suggestion | PostToolUse | No (알림만) | HIGH (모든 편집에 반응) | MEDIUM | DEFER | false positive 빈번. 안정화 후 적용 |
| artifact-manifest-freshness-check | Stop | No (알림만) | MEDIUM (30분 임계값 조정 필요) | MEDIUM | DEFER (Phase 2) | 기능 가치 있으나 즉시성 낮음 |

### 4-C. MCP

| candidate_name | security_risk | data_risk | overlaps_existing | required_credentials | recommended_action | reason |
|----------------|--------------|-----------|-------------------|---------------------|-------------------|--------|
| Semantic Scholar MCP | LOW | LOW | 없음 | API key (현재 활성) | KEEP (ALREADY_ACTIVE) | 학술 검색, 비즈니스 리스크 낮음 |
| GitHub MCP | HIGH (push 금지 정책 충돌) | MEDIUM | git CLI로 충분 | GITHUB_TOKEN | DEFER | readonly 제한 후 재검토 |
| Postgres MCP | MEDIUM | HIGH | DB 미구현 | DB_URL | DEFER | plans/012 이후 |
| Redis MCP | MEDIUM | MEDIUM | Redis 미도입 | REDIS_URL | DEFER | plans/012 이후 |
| Filesystem MCP | HIGH (.env 노출 위험) | HIGH | Read/Write/Edit tool 충분 | 없음 | REJECT | 기존 도구 충분, 위험만 증가 |
| Browser MCP | HIGH (세션 탈취) | HIGH | playwright_probe 구현됨 | 없음 | REJECT | Python runner가 이미 구현 |
| Web Fetch MCP | MEDIUM (SSRF) | LOW | WebFetch tool 허용 | 없음 | DEFER | 현재 WebFetch tool로 충분 |
| Vector DB MCP | MEDIUM | MEDIUM | 미구현 | Milvus conn | DEFER | 오케스트레이션 이후 |
| LangSmith MCP | LOW | MEDIUM | LangGraph 미구현 | LANGSMITH_API_KEY | DEFER | LangGraph 구현 후 |
| Code Execution MCP | CRITICAL | CRITICAL | Bash tool 있음 | 없음 | REJECT | sandbox 없는 임의 코드 실행 |

---

## 5. Agent-by-Agent Review

### 5-1. mcp-tooling-researcher

**MCP 후보 조사 관점 평가**

| MCP | KEEP/DEFER/REJECT | 이유 |
|-----|-------------------|------|
| Semantic Scholar | KEEP | 비즈니스 리스크 낮음, 이미 활성 |
| Filesystem | REJECT | 기존 Read/Write/Edit tool 충분. .env 노출 위험 |
| Browser | REJECT | playwright_probe.py 구현 완료. 중복 + 보안 위험 |
| Code Execution | REJECT | CRITICAL 보안. Bash tool로 충분 |
| GitHub | DEFER | push 정책 충돌. readonly 제한 후 재검토 |
| Postgres/Redis/Milvus | DEFER | plans/012 오케스트레이션 이후 |
| LangSmith | DEFER | LangGraph 미구현 |
| Web Fetch | DEFER | WebFetch tool + 허용 도메인으로 충분 |

**supply_chain_risk 평가**: 커뮤니티 MCP는 tool description에 악의적 지시를 숨길 수 있음 (tool poisoning). 설치 전 README 및 소스 전체 수동 검토 필수.

**recommendation**: 이번 턴: MCP 추가 없음. Semantic Scholar 현 상태 유지.

---

### 5-2. security-permission-guardian

**보안 관점 평가**

```
BLOCK 조건:
- Filesystem MCP: .env 읽기 가능 → REJECT
- Browser MCP: session token 탈취 가능 → REJECT  
- Code Execution MCP: sandbox 없는 임의 실행 → REJECT
- 모든 MCP는 tool poisoning 공격면 추가

Hook forbidden-command-guard:
- 현재 설계(04번): $env:CLAUDE_TOOL_INPUT (env var) 사용 → 잘못됨
- 수정 필요: stdin JSON 파싱 방식으로 변경
- Windows PowerShell의 $input (automatic variable)과 충돌 주의
- 테스트: hook dry-run 필수, 실제 명령 차단 전 stub 테스트

Skills:
- Bash 사용 skills(test-validation, source-audit, runner-contract, trend-fallback): 
  allowed-tools에 Bash 명시 필요
- skills에서 .env 키 값 출력 절대 금지
- skills 파일은 secret 패턴 포함 금지 (scan_secrets 검증 필수)

최소 권한 요구사항:
- test-validation-skill: Bash(pytest, scan_secrets, git diff --check)만 허용
- source-audit-skill: Bash(run_collection_probe)만, 네트워크 외부 접근 최소화
- trend-fallback-analysis-skill: Bash(run_trend_fallback_enrichment_audit)만
```

**recommendation**: Hook 명령 stdin JSON 파싱 방식 수정 후 적용. Skills에서 allowed-tools 명시.

---

### 5-3. legal-safety-compliance-reviewer

**법무 관점 평가**

```
Skills 내 명령:
- run_collection_probe 호출 자체는 법무 리스크 없음
- google_trends_explore 재시도 금지 명시 유지 필수
- proxy rotation, CAPTCHA bypass, login wall 통과 명령 포함 금지

Hook:
- PreToolUse 차단 hook은 도구 실행 차단이므로 법무 문제 없음
- Stop hook의 grep 패턴에 개인정보 포함 금지

MCP:
- Filesystem MCP: 개인정보 포함 파일 접근 가능 → REJECT 지지
- GitHub MCP: 비공개 repo의 저작권 콘텐츠 노출 위험 → readonly 제한 후 재검토
- Semantic Scholar: 학술 논문 접근, 인용 정책 준수 필요

Skills 내 수집 명령:
- newsapi: free tier 상업 사용 금지 조항 — skill에서 상업 목적 쿼리 자동화 금지
- nyt: 500/day 제한 — skill에서 반복 호출 금지
- guardian: 재배포 금지 — skill 출력에 전문 포함 금지

신규 소스 추가 전 필수: legal-safety-compliance-reviewer 에이전트 위임
```

**recommendation**: Skills 내 수집 자동화 명령에 quota/약관 주의사항 주석 필수.

---

### 5-4. source-ingestion-engineer

**수집 파이프라인 관점 평가**

```
MCP 중복 분석:
- Filesystem MCP: Read/Write/Edit로 충분 → 중복
- Browser MCP: playwright_probe.py 구현 완료 → 중복
- Web Fetch MCP: WebFetch tool 충분 → 중복
- 결론: 모든 수집 관련 MCP는 기존 runner와 중복

Skills project integration:
- test-validation-skill → 기존 pytest + scan_secrets 직접 호출. integration EASY.
- source-audit-skill → run_collection_probe CLI 호출. integration EASY.
- runner-contract-skill → run_runner_orchestration_readiness CLI. integration EASY.
- trend-fallback-analysis-skill → run_trend_fallback_enrichment_audit CLI. integration EASY.
- artifact-manifest-skill → Glob + docs/ingestion/artifact_manifest_final.md Read+Edit. EASY.

구현 난이도: 모두 LOW (기존 CLI/파일에 래핑만)
도입 후 테스트 대상:
- skills SKILL.md frontmatter 검증 (allowed-tools 포함)
- hook stdin JSON 파싱 정확성
- hook false positive 없음 (정상 명령 차단 안 됨)
```

**recommendation**: Skills 5개 Phase 1 적용 적합. MCP 추가 없음.

---

### 5-5. test-validation-agent

**검증 관점 평가**

```
Skills 적용 시 필요한 검증:
1. .claude/skills/<name>/SKILL.md 파일 구조 확인
   - grep: frontmatter "name:", "description:", "user-invocable:", "allowed-tools:" 존재
2. secret scan: skill 파일에 key/token 없음
3. git diff --check: whitespace error 없음
4. hook 검증:
   - forbidden-command-guard: 정상 명령(git status) → 통과, 금지 명령(git push) → 차단
   - Stop hooks: 알림만 출력, 비차단 동작 확인
5. regression: 기존 pytest 648 passed 유지

Release gate:
- secret scan PASS
- diff --check PASS  
- skill 파일 구조 PASS (subdirectory + SKILL.md)
- hook dry-run PASS
- pytest PASS (skip if docs-only)

주의: hooks 적용 후 Claude Code 재시작 필요 (settings.json 변경 반영)
```

**recommendation**: Phase 1 apply 전 반드시 hook dry-run 수행.

---

### 5-6. docs-memory-curator

**문서 관점 평가**

```
이번 턴 결과물:
- 11_SKILLS_HOOKS_MCP_PLUGIN_SPEC.md (이 파일) 생성
- ENVIRONMENT_SETUP_TRACE_FINAL.md 갱신 필요 (§15 추가)
- README.md 갱신 필요 (11번 문서 추가)

다음 턴 적용 후 갱신 대상:
- ENVIRONMENT_SETUP_TRACE_FINAL.md: skills/hooks 적용 섹션 추가
- README.md: Phase 1 apply 완료 항목 이동
- 12번 stub 생성 불필요 (이 문서는 SPEC이므로 적용 완료 후 archived 처리)

중복 방지:
- 04_SKILLS_HOOKS_PLUGINS_DESIGN.md: stub (_archive_applied에 이미 이동됨)
- 이 11번 문서가 04번 설계를 완전히 대체함

문서 일관성 체크:
- google_trends_explore가 PASS로 적힌 곳 없는지 grep
- "proxy rotation" 권장 없는지 grep
- "immediately apply" 표기 없는지 grep (SPEC 문서임을 명확히)
```

**recommendation**: 이번 턴 커밋에 TRACE_FINAL + README 갱신 포함.

---

### 5-7. adversarial-reality-critic

**현실 비판 평가**

```
BRUTAL CRITIQUE:

1. Skills이 에이전트를 중복하는가?
   - test-validation-skill vs test-validation-agent:
     차이: skill=사용자가 /test-validation-skill로 직접 호출
           agent=Claude가 내부적으로 위임
     → 중복 아님. 접근 방식이 다름.
   - 하지만: 팀 에이전트가 이미 15개인데 skill 9개 추가 → 
     "너무 많은 추상화 레이어" 위험 있음.
   → 판정: Phase 1은 5개로 최소화. 나머지 Phase 2/3.

2. Hook이 실제로 필요한가?
   - forbidden-command-guard: settings.json deny 목록이 이미 있음.
     deny 목록 vs hook 이중화는 합리적 (deny는 tool-level, hook은 pattern-level).
     → VALID
   - pre-commit-secret-scan-reminder: 알림이라 실제 실행을 강제하지 않음.
     → 유용하나 선택적.
   - docs-conflict-grep-check: 실제 충돌 발생 빈도가 낮을 수 있음.
     → VALID (비용 낮음)

3. 복잡도 증가 vs 가치:
   - Skills 9개: 9개 모두 즉시 필요 없음. 5개로 줄여라.
   - Hooks: Stop hook 2개는 알림이라 비용 낮음. 적합.
   - PreToolUse hook: stdin JSON 파싱 복잡. 잘못 작성하면 오히려 위험.
     → "VERIFY BEFORE APPLY" 필수.

4. MCP 추가 없음이 옳은가?
   - Python runner가 이미 모든 수집을 커버함.
   - MCP 추가는 공격면 증가 대비 이득 없음.
   → CORRECT 판단.

REJECT/DEFER 권고:
- environment-setup-skill: 현재 운영 세션에서 한 번 쓸까 말까 → Phase 2
- business-reality-critique-skill: 에이전트로 이미 가능 → Phase 2
- legal-safety-review-skill: 에이전트로 이미 가능 → Phase 3
- post-edit-test-suggestion hook: false positive 많음 → DEFER
- artifact-manifest-freshness-check hook: 유용하나 즉시성 낮음 → Phase 2
```

**recommendation**: Phase 1은 skills 5개 + hooks 3개로 최소화. 나머지 DEFER.

---

### 5-8. commercialization-strategist

**비즈니스 가치 평가**

```
HIGH business value:
- test-validation-skill: 품질 게이트 → 리포트 신뢰도 직결
- source-audit-skill: 소스 health → 사용자가 보는 데이터 품질
- trend-fallback-analysis-skill: 트렌드 데이터 끊김 방지 → 사용자 체류

MEDIUM business value:
- artifact-manifest-skill: 운영 추적 → 내부 가치
- docs-sync-skill: 내부 문서 → 직접 비즈니스 가치 낮음
- runner-contract-skill: 운영 안정성 → 간접 가치

LOW business value (현재 시점):
- environment-setup-skill: 온보딩 도구, 지금 팀 규모에서 불필요
- business-reality-critique-skill: 에이전트로 이미 가능
- legal-safety-review-skill: 에이전트로 이미 가능

business value ranking:
1위 test-validation-skill (품질 = 신뢰 = 전환율)
2위 trend-fallback-analysis-skill (트렌드 연속성)
3위 source-audit-skill (데이터 신선도)
```

**recommendation**: Phase 1 우선순위 = test-validation → trend-fallback → source-audit 순.

---

### 5-9. data-quality-auditor

**데이터 품질 관점 평가**

```
Skills 도입 시 데이터 품질 영향:
- test-validation-skill: 직접 품질 보호 (pytest로 추출 로직 검증)
- source-audit-skill: 소스별 body 추출률 모니터링 → 품질 지표 유지
- trend-fallback-analysis-skill: fallback chain 작동 확인 → 트렌드 데이터 연속성

Hook 도입 시 품질 영향:
- forbidden-command-guard: 수집 코드 의도치 않은 삭제 방어
- docs-conflict-grep-check: "PASS" 오표기 방어 → 문서 품질

MCP 관련:
- 현재 Python runner의 rate-limit 정책이 데이터 품질 보호 주요 수단
- MCP 추가 없음이 안정적 수집 유지에 유리

주의:
- source-audit-skill에서 수집 실행 시 rate-limit 정책 준수 필수
- skill 내 GDELT 호출: min_interval 60s 전제 명시
- google_trends_explore 호출 금지 (CONFIRMED_EXTERNAL_RATE_LIMIT)
```

**recommendation**: Phase 1 skills는 데이터 품질 보호 역할. 적합.

---

### 5-10. operations-sre-agent

**운영 관점 평가**

```
Skills 운영 부담:
- 5개 skills: .claude/skills/<name>/SKILL.md 파일 각 1개 → 관리 부담 낮음
- 기존 runner CLI를 래핑하므로 추가 의존성 없음

Hooks 운영 부담:
- PreToolUse hook: 모든 Bash/PowerShell 실행 전에 실행됨
  → 실행 빈도 높음. hook 자체 실패 시 모든 도구 차단 위험
  → 테스트 철저히, timeout 설정 권장
- Stop hooks: Claude 응답 종료 시에만 실행. 부담 낮음

장기 연결 (plans/012 이후):
- Postgres MCP: DB 미도입 → DEFER 지지
- Redis MCP: Redis 미도입 → DEFER 지지  
- Milvus MCP: 오케스트레이션 이후 → DEFER 지지

failure isolation:
- hook 실패 시 Claude 동작 영향 최소화 위해 비차단 hook은 exit 0 권장
- forbidden-command-guard만 차단(exit 1), 나머지는 알림(exit 0)

rollback:
- skills: .claude/skills/<name>/ 디렉터리 제거
- hooks: settings.json에서 hooks 섹션 제거
- MCP: settings.json allow 목록에서 제거 / .mcp.json 제거
```

**recommendation**: PreToolUse hook의 실패 모드 주의. timeout 설정 필수.

---

### 5-11. product-ux-strategist

**제품/UX 관점 평가**

```
사용자 직접 체감:
- /test-validation-skill → 즉각적 검증 → 개발 속도 향상
- /source-audit-skill → 소스 상태 빠른 확인 → UX 설계 결정 속도
- /trend-fallback-analysis-skill → 트렌드 연속성 → 최종 사용자 경험 보호

event card/evidence pane에 직접 기여:
- source-audit-skill로 소스 health 시각화 데이터 유지
- artifact-manifest-skill로 evidence artifact 추적

dashboard 연결 가능성 (미래):
- source-audit-skill 출력 → source health dashboard 피드
- runner-contract-skill 출력 → orchestration status panel

현재 UI 없음이므로 skills는 내부 운영 도구로만 사용.
```

**recommendation**: Phase 1 skills는 내부 운영 도구. UI 연결은 orchestration 이후.

---

### 5-12. orchestrator-architect

**아키텍처 관점 최종 평가**

```
전체 pipeline에서 skills/hooks의 위치:

수집 → 정규화 → 랭킹 → 저장 → 서빙
       ↑                    ↑
   source-audit-skill   artifact-manifest-skill
   
Claude Code 세션 레이어:
PreToolUse hook → [Bash/PowerShell 실행]
PostToolUse hook → [Edit/Write 완료 후 알림]
Stop hook → [secret scan 알림 + docs conflict 체크]

skills 책임 경계:
- skills = 사용자 트리거, 표준화된 절차
- agents = Claude 내부 위임, 독립적 판단
- hooks = 자동 사이드이펙트, 라이프사이클 연결

다음 적용 순서:
1. Skills 5개 (Phase 1): test-validation, source-audit, artifact-manifest, docs-sync, runner-contract
2. Hooks 3개 (Phase 1): forbidden-command-guard, secret-scan-reminder, docs-conflict-check
3. WebSearch/WebFetch 에이전트 추가 (선택): mcp-tooling-researcher 등 4개 에이전트 업데이트
4. Skills 4개 (Phase 2): trend-fallback, environment-setup, business-reality-critique + 1
5. Hooks 2개 (Phase 2): post-edit-test-suggestion, artifact-manifest-freshness-check
6. MCP 재검토 (Phase 3): plans/012 완료 후
7. Plugin (Phase 4): skills/hooks/agents 안정화 후
```

**recommendation**: Skills + Hooks 최소 세트 Phase 1, MCP/Plugin DEFER.

---

## 6. Committee Final Decision

위원회: mcp-tooling-researcher, security-permission-guardian, legal-safety-compliance-reviewer,
source-ingestion-engineer, test-validation-agent, docs-memory-curator,
adversarial-reality-critic, commercialization-strategist, orchestrator-architect

### 결정 규칙 적용 결과

| 규칙 | 적용 결과 |
|------|---------|
| security-permission-guardian BLOCK | Filesystem/Browser/Code-Execution MCP → REJECT |
| legal-safety-compliance-reviewer BLOCK | 없음 (기존 runner 수집 정책 유지 시) |
| source-ingestion-engineer "기존 runner 중복" | Filesystem/Browser/Web-Fetch MCP → DEFER/REJECT |
| test-validation-agent "검증 불가" | PreToolUse hook stdin JSON 파싱 → VERIFY_BEFORE_APPLY 조건부 |
| adversarial-reality-critic "복잡도만" | environment/business/legal skills → Phase 2/3 |
| commercialization-strategist high value | test-validation, trend-fallback, source-audit → Phase 1 지지 |

### 최종 분류

| 항목 | 유형 | 결정 | 근거 |
|------|------|------|------|
| test-validation-skill | skill | **Phase 1 Apply** | 검증 핵심, 기존 CLI 래핑, 보안 안전 |
| source-audit-skill | skill | **Phase 1 Apply** | 소스 health 추적, 기존 CLI 래핑 |
| artifact-manifest-skill | skill | **Phase 1 Apply** | artifact 관리, 부수효과 없음 |
| docs-sync-skill | skill | **Phase 1 Apply** | TRACE_FINAL 동기화, 필수 |
| runner-contract-skill | skill | **Phase 1 Apply** | 오케스트레이션 준비 필수 검증 |
| forbidden-command-guard | hook | **Phase 1 Apply** (조건부: stdin 파싱 수정 후) | 핵심 보안. settings.json deny와 이중화 |
| pre-commit-secret-scan-reminder | hook | **Phase 1 Apply** | 비차단 알림, 가치 높음, 위험 낮음 |
| docs-conflict-grep-check | hook | **Phase 1 Apply** | google_trends_explore PASS 오표기 방어 |
| Semantic Scholar MCP | mcp | **KEEP (ALREADY_ACTIVE)** | 현 상태 유지 |
| trend-fallback-analysis-skill | skill | **Phase 2 Apply** | Playwright 실행 포함, 안정화 후 |
| environment-setup-skill | skill | **Phase 2 Apply** | 즉시성 낮음 |
| business-reality-critique-skill | skill | **Phase 2 Apply** | 에이전트로 대체 가능 |
| post-edit-test-suggestion hook | hook | **Phase 2 Apply** | false positive 위험 |
| artifact-manifest-freshness hook | hook | **Phase 2 Apply** | 유용하나 즉시성 낮음 |
| legal-safety-review-skill | skill | **Phase 3 Apply** | 에이전트로 대체 가능 |
| GitHub MCP | mcp | **DEFER** | push 정책 충돌, readonly 제한 후 |
| Postgres/Redis/Milvus MCP | mcp | **DEFER** | plans/012 이후 |
| LangSmith MCP | mcp | **DEFER** | LangGraph 미구현 |
| Web Fetch MCP | mcp | **DEFER** | 기존 WebFetch tool 충분 |
| Filesystem MCP | mcp | **REJECT** | 기존 도구 충분 + .env 노출 위험 |
| Browser MCP | mcp | **REJECT** | playwright_probe.py 구현 완료 + 보안 위험 |
| Code Execution MCP | mcp | **REJECT** | CRITICAL 보안, Bash tool 충분 |
| Plugin (모든 후보) | plugin | **DEFER** | skills/hooks 안정화 후 |
| WebSearch/WebFetch in 4 agents | agent update | **USER_DECISION_REQUIRED** | 공식 지원 확인됨. 추가 여부는 사용자 결정 |

---

## 7. Recommended Phase 1 Apply Set

### Skills (5개)

```
.claude/skills/
├── test-validation-skill/
│   └── SKILL.md
├── source-audit-skill/
│   └── SKILL.md
├── artifact-manifest-skill/
│   └── SKILL.md
├── docs-sync-skill/
│   └── SKILL.md
└── runner-contract-skill/
    └── SKILL.md
```

### Hooks (3개, settings.json hooks 섹션 추가)

```json
"hooks": {
  "PreToolUse": [
    {
      "matcher": "Bash|PowerShell",
      "hooks": [
        { "type": "command", "command": "<forbidden-command-guard — §9 참조>" }
      ]
    }
  ],
  "Stop": [
    {
      "hooks": [
        { "type": "command", "command": "<secret-scan-reminder — §9 참조>" },
        { "type": "command", "command": "<docs-conflict-grep-check — §9 참조>" }
      ]
    }
  ]
}
```

### MCP

변경 없음. Semantic Scholar KEEP.

### Plugins

DEFER.

---

## 8. Required Local Rewrites

설계 문서(04번)의 코드를 **그대로 복사하지 않는다**. 다음 이유로 재작성 필요:

| 항목 | 설계 문서(04번) 가정 | 수정 필요 내용 |
|------|---------------------|--------------|
| Skills 경로 | `.claude/skills/<name>.md` (flat file) | `.claude/skills/<name>/SKILL.md` (subdirectory 필수) |
| Skills frontmatter | `tools: Read, Bash` (agent 스키마) | `allowed-tools: [Bash, Read, Glob]` (skill 스키마) |
| Skills frontmatter 추가 필드 | 없음 | `user-invocable: true`, `when_to_use: <설명>` 추가 |
| Hook 입력 방식 | `$env:CLAUDE_TOOL_INPUT` (env var) | stdin JSON 파싱: `$json = [Console]::In.ReadToEnd() \| ConvertFrom-Json` |
| Hook PowerShell $input | `$input` 사용 | PS automatic variable 충돌 → `[Console]::In.ReadToEnd()` 사용 |
| Hook 명령 인코딩 | 단순 문자열 | Windows 인코딩 이슈 고려, `chcp 65001` 또는 UTF-8 설정 |

**삭제해야 할 위험한 내용**:
- 04번 문서 Hook 예시의 `$env:CLAUDE_TOOL_INPUT` → 실제 동작 안 함
- 04번 문서 `VERIFY BEFORE APPLY` 주석 달린 모든 코드 → 이제 공식 문서 기반으로 재작성

---

## 9. Proposed Local Skill Specs

### Skill 1: test-validation-skill

```
path: .claude/skills/test-validation-skill/SKILL.md
trigger: 코드 수정 후, 커밋 전, 릴리즈 게이트
user-invocable: true
when_to_use: After any code changes, before commits, or at release gates
allowed-tools: Bash, Read, Glob

procedure:
1. git diff --check
2. .\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths .
3. .\.venv\Scripts\python.exe -m pytest ingestion\tests -q --tb=short

success_criteria:
- diff --check: exit 0
- secret scan: verdict=PASS
- pytest: 0 fail (648+ passed)

forbidden_actions:
- git push 금지
- google_trends_explore PASS 표기 금지
- .env 키 값 출력 금지
- 검증 없이 "완료" 보고 금지

expected_output:
검증 결과 표: 항목 | 결과 | 상세
```

### Skill 2: source-audit-skill

```
path: .claude/skills/source-audit-skill/SKILL.md
trigger: 소스 health 이슈, 신규 소스 추가 후, 정기 감사
user-invocable: true
when_to_use: When verifying source health, after adding new sources, or during routine audits
allowed-tools: Bash, Read, Grep, Glob

procedure:
1. source_registry.yaml 전체 소스 목록 확인
2. 대상 소스에 대해 run_collection_probe 실행
3. artifact JSONL 분석 (items_found, body_extracted, status)
4. 결과를 docs/ingestion/70_source_status_master.md 판정 기준으로 평가

source-specific rules:
- GDELT: min_interval 60s 준수 필수
- google_trends_explore: 호출 금지 (CONFIRMED_EXTERNAL_RATE_LIMIT)
  대신 fallback chain 실행: runner-contract-skill → run_trend_fallback_enrichment_audit
- newsapi: 100/day 제한, 절약 모드

forbidden_actions:
- rate_limit 무시 연속 호출 금지
- google_trends_explore 429 우회 시도 금지
- 실패를 PASS로 보고 금지
- proxy rotation 금지

expected_output:
표: source_id | 수집 방식 | status | items | body | 판정 | 주의사항
종합: CORE_READY N / CAUTION M / BLOCKED K
```

### Skill 3: artifact-manifest-skill

```
path: .claude/skills/artifact-manifest-skill/SKILL.md
trigger: 신규 JSONL artifact 생성 후, 세션 종료 전
user-invocable: true
when_to_use: After new JSONL artifacts are generated or before session end
allowed-tools: Read, Glob, Write, Edit

procedure:
1. ingestion/outputs/jsonl/ 최신 파일 목록 확인 (Glob)
2. docs/ingestion/artifact_manifest_final.md §2 표와 비교
3. 누락된 항목 추가 (size, sha256 앞 16자, runner 명령, checklist 항목)

forbidden_actions:
- raw payload/기사 내용 전문 복사 금지
- .env 키 값 기록 금지
- git push 금지
- JSONL 파일 직접 편집 금지

expected_output:
추가된 행 목록 + 업데이트된 매니페스트 확인 (라인 수 변화)
```

### Skill 4: docs-sync-skill

```
path: .claude/skills/docs-sync-skill/SKILL.md
trigger: 새 feature 구현 완료 후, 세션 종료 전
user-invocable: true
when_to_use: After completing a feature implementation or before session end
allowed-tools: Read, Grep, Glob, Write, Edit

procedure:
1. IMPLEMENTATION_TRACE_FINAL.md checklist 항목 업데이트
2. artifact_manifest_final.md 신규 artifact 추가
3. 관련 docs/ingestion/ 문서 갱신 섹션 추가
4. Environment_setup/README.md 진입점 유효성 확인
5. stale instruction 발견 시 _archive_applied/ 이동 안내

forbidden_actions:
- APPLIED 지시서를 다시 활성 지시로 재실행 금지
- Implementation_Instructions/00~10_*.md stub를 원문으로 혼동 금지
- _archive_applied/ 파일 무단 삭제 금지
- git push 금지

expected_output:
동기화된 항목 목록 + 남은 TODO
```

### Skill 5: runner-contract-skill

```
path: .claude/skills/runner-contract-skill/SKILL.md
trigger: 오케스트레이션 구현 전, runner 수정 후
user-invocable: true
when_to_use: Before orchestration implementation or after runner modifications
allowed-tools: Bash, Read, Glob

procedure:
1. .\.venv\Scripts\python.exe -m ingestion.runners.run_runner_orchestration_readiness
2. 결과 JSONL artifact 분석 (agent_ready 상태)
3. agent_ready = False인 runner 목록 추출

success_criteria:
- 13/13 runner agent_ready = True
- JSONL artifact 생성 확인

failure_action:
- agent_ready = False인 runner 목록 → source-ingestion-engineer에 핸드오프

forbidden_actions:
- rate_limit 무시 반복 실행 금지
- runner 결함을 PASS로 보고 금지

expected_output:
표: runner | agent_ready | notes
종합: N/13 READY
```

---

## 10. Proposed Hook Specs

### Hook 1: forbidden-command-guard (PreToolUse)

```
event: PreToolUse
blocking: YES (exit 1)
matcher: "Bash|PowerShell"
purpose: rm/Remove-Item/git push 등 금지 명령 실행 전 차단

input mechanism:
  - Claude Code가 hook에 stdin으로 JSON 전달
  - 형식: {"tool_name": "Bash", "tool_input": {"command": "git push ..."}}
  - PowerShell에서 읽기: $json = [Console]::In.ReadToEnd() | ConvertFrom-Json

proposed command (draft — VERIFY BEFORE APPLY):
  PowerShell -NoProfile -Command "$json = [Console]::In.ReadToEnd() | ConvertFrom-Json; $cmd = $json.tool_input.command; $forbidden = @('git push','git reset --hard','git clean','rm -','rm /','Remove-Item','rmdir','del ','erase '); foreach ($f in $forbidden) { if ($cmd -like \"*$f*\") { Write-Error \"FORBIDDEN_COMMAND_BLOCKED: $f\"; exit 1 } }; exit 0"

VERIFY_BEFORE_APPLY:
  - stdin JSON 스키마 (tool_name, tool_input 필드명) — 공식 문서에서 정확히 확인 필요
  - Windows PowerShell 5.1에서 stdin JSON 파싱 동작 확인
  - false positive 테스트: "git status", "git diff" → 통과 확인
  - false negative 테스트: "git push", "rm file.txt" → 차단 확인

dry-run test plan:
  1. "git status --short" 명령 → exit 0 (통과) 확인
  2. "git push" (settings.json deny 목록에도 있음) → hook이 먼저 차단 or deny가 먼저
  3. hook 자체 실패 시 → Claude 동작 중단 여부 확인

false_positive_risk: MEDIUM (명령 문자열 부분 매치 오동작 가능)
rollback: settings.json hooks.PreToolUse 섹션 제거
```

### Hook 2: pre-commit-secret-scan-reminder (Stop)

```
event: Stop
blocking: NO (exit 0, 알림만)
purpose: 코드 변경 감지 시 secret scan 실행 권장 메시지 출력

proposed command:
  PowerShell -NoProfile -Command "$status = git diff --name-only HEAD 2>$null; if ($status) { Write-Host '[REMINDER] 코드 변경 감지: python -m ingestion.tools.scan_secrets --paths . 실행 권장' }; exit 0"

주의:
  - Stop event는 항상 실행됨 (코드 변경 없어도). git diff로 필터링.
  - exit 0 필수 (비차단)
  - Write-Host (stdout) 사용. Write-Error (stderr) 사용 금지 (차단 오인 가능)

false_positive_risk: LOW
rollback: settings.json hooks.Stop 섹션에서 해당 명령 제거
```

### Hook 3: docs-conflict-grep-check (Stop)

```
event: Stop
blocking: NO (exit 0, 경고 메시지만. 차단 아님)
purpose: google_trends_explore를 PASS로 오표기한 문서 경고

proposed command:
  PowerShell -NoProfile -Command "$conflicts = Select-String -Path docs -Recurse -Pattern 'google_trends_explore.*PASS' -Include '*.md' -ErrorAction SilentlyContinue; if ($conflicts) { Write-Host '[WARNING] google_trends_explore를 PASS로 표기한 문서 발견:'; $conflicts | ForEach-Object { Write-Host $_.Filename } }; exit 0"

주의:
  - _archive_applied/ 내 문서도 검색될 수 있음 → -Exclude 추가 고려
  - exit 0 필수 (비차단)

false_positive_risk: LOW (패턴 특이적)
rollback: settings.json hooks.Stop에서 해당 명령 제거
```

### Hooks settings.json 삽입 위치

```json
// .claude/settings.json에 추가할 섹션 (현재 "permissions" 레벨과 동일)
"hooks": {
  "PreToolUse": [
    {
      "matcher": "Bash|PowerShell",
      "hooks": [
        {
          "type": "command",
          "command": "PowerShell -NoProfile -Command \"$json = [Console]::In.ReadToEnd() | ConvertFrom-Json; $cmd = $json.tool_input.command; $forbidden = @('git push','git reset --hard','git clean','rm -','Remove-Item','rmdir'); foreach ($f in $forbidden) { if ($cmd -like \"*$f*\") { Write-Error 'FORBIDDEN_COMMAND_BLOCKED'; exit 1 } }; exit 0\""
        }
      ]
    }
  ],
  "Stop": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "PowerShell -NoProfile -Command \"$status = git diff --name-only HEAD 2>$null; if ($status) { Write-Host '[REMINDER] 코드 변경 감지: python -m ingestion.tools.scan_secrets --paths . 실행 권장' }; exit 0\""
        },
        {
          "type": "command",
          "command": "PowerShell -NoProfile -Command \"$conflicts = Select-String -Path docs -Recurse -Pattern 'google_trends_explore.*PASS' -Include '*.md' -ErrorAction SilentlyContinue; if ($conflicts) { Write-Host '[WARNING] google_trends_explore PASS 오표기 발견!' }; exit 0\""
        }
      ]
    }
  ]
}
```

> **VERIFY_BEFORE_APPLY**: 위 JSON은 초안이다. 실제 적용 전:
> 1. stdin JSON 스키마 공식 확인 (hook event payload 필드명)
> 2. settings.json 전체 JSON 유효성 검증 (`python -m json.tool .claude/settings.json`)
> 3. PowerShell 5.1에서 `ConvertFrom-Json` 동작 확인
> 4. hook dry-run: 단순 `echo` 명령으로 먼저 테스트

---

## 11. MCP Decision Log

| MCP | 결정 | 이유 | credentials | 보안 조건 | 도입 시점 |
|-----|------|------|------------|---------|---------|
| Semantic Scholar | KEEP | 이미 활성, 보안 리스크 낮음 | 없음 | 현재 conditions 유지 | 현재 |
| GitHub | DEFER | git push 금지 정책과 충돌. readonly 토큰 제한 후 재검토 | GITHUB_TOKEN | readonly scope만, push 금지 검증 | plans/012 이후 |
| Postgres | DEFER | DB 미도입 | DB_URL | read-only 쿼리만 허용 | plans/012 Postgres 도입 후 |
| Redis | DEFER | Redis 미도입 | REDIS_URL | FLUSHALL 등 위험 명령 차단 | plans/012 Redis 전환 후 |
| Filesystem | REJECT | 기존 Read/Write/Edit tool 충분. .env 노출 위험 | 없음 | - | 영구 거절 |
| Browser/Playwright | REJECT | playwright_probe.py 구현 완료. 보안 위험 | 없음 | - | 영구 거절 |
| Code Execution | REJECT | CRITICAL 보안. sandbox 없는 임의 실행 | 없음 | - | 영구 거절 |
| Web Fetch | DEFER | WebFetch tool + 허용 도메인으로 충분 | 없음 | 허용 도메인 화이트리스트 필수 | 필요 시 재검토 |
| Vector DB (Milvus) | DEFER | 오케스트레이션 이후 단계 | Milvus conn | read-only query 제한 | Milvus 도입 후 |
| LangSmith | DEFER | LangGraph 미구현 | LANGSMITH_API_KEY | key 값 노출 금지 | LangGraph 구현 후 |

---

## 12. Plugin Decision Log

| 항목 | 결정 | 이유 |
|------|------|------|
| 모든 plugin 후보 | DEFER | skills/hooks/agents 안정화 전 plugin 패키징은 조기 추상화 |
| plugin 도입 조건 | - | skills 5개 안정 운영 + hooks 3개 false positive 없음 + 오케스트레이션 완성 |
| plugin 정의 | - | skills + hooks + agents + MCP를 하나의 재사용 단위로 묶는 상위 개념 |
| 재검토 시점 | - | plans/012 Celery/LangGraph 구현 완료 후 |

---

## 13. Conflict and Risk Analysis

### 13-A. Agent-Skill Conflict

| 에이전트 | 유사 Skill | 충돌 여부 | 해소 방안 |
|---------|----------|---------|---------|
| test-validation-agent | test-validation-skill | 중복 아님 | agent=Claude 내부 위임, skill=사용자 /command 트리거 |
| source-ingestion-engineer | source-audit-skill | 중복 아님 | agent=코드 수정, skill=health 감사 실행 |
| docs-memory-curator | docs-sync-skill, artifact-manifest-skill | 중복 아님 | agent=긴 문서 작업, skill=즉시 동기화 절차 |

### 13-B. Hook False Positive 위험

| Hook | 시나리오 | 심각도 | 대응 |
|------|---------|--------|------|
| forbidden-command-guard | "Remove-Item" 이 파일명에 포함된 경우 → 정상 명령 차단 | HIGH | 패턴을 단어 경계로 정밀화 필요 |
| forbidden-command-guard | stdin JSON 파싱 실패 → 모든 명령 차단 | HIGH | try-catch 추가, 파싱 실패 시 exit 0으로 폴백 |
| secret-scan-reminder | 문서만 수정해도 git diff 감지 → 불필요한 알림 | LOW | 알림이므로 허용 |
| docs-conflict-grep-check | _archive_applied/ 내 역사 문서에서 "PASS" 감지 | MEDIUM | -Exclude 패턴으로 archive 제외 |

### 13-C. MCP Security Risk

| 위험 | 대상 | 수준 | 현재 대응 |
|------|------|------|---------|
| Tool Poisoning | 모든 커뮤니티 MCP | HIGH | 설치 금지 (이번 턴) |
| .env 노출 | Filesystem MCP | CRITICAL | REJECT |
| Prompt Injection | 외부 콘텐츠 반환 MCP | MEDIUM | 허용 MCP 없음 |
| Supply Chain | npm 패키지 기반 MCP | HIGH | 비공식 MCP 사용 금지 |

### 13-D. Skills Path 수정 미적용 시 위험

설계 문서(04번) 그대로 flat file `.claude/skills/<name>.md`로 생성하면:
- Claude Code가 skill 파일을 인식하지 못함
- `/test-validation-skill` 커맨드가 동작 안 함
- 잘못된 파일이 `.claude/` 아래에 남음

### 13-E. Context Bloat 위험

Skills SKILL.md 파일 9개가 모두 Claude context에 로드되면 context 증가.
- 대응: `user-invocable: true` 명시, 필요 시에만 로드
- Phase 1: 5개로 최소화

### 13-F. WebSearch/WebFetch Agents Update 결정 지연 위험

공식 지원이 확인됐으나 4개 에이전트(mcp-tooling-researcher, commercialization-strategist,
legal-safety-compliance-reviewer, business-intelligence-analyst)에 추가하지 않으면:
- 에이전트가 외부 정보 수집 불가 (현재 상태 유지)
- "main agent must request web research" 정책 지속

→ **USER_DECISION_REQUIRED**: 에이전트 frontmatter 업데이트 여부 사용자 결정 후 별도 커밋.

---

## 14. Next Turn Implementation Plan

### PHASE A. 사전 확인

```
1. git status --short → CLEAN 확인
2. dir .claude/agents → 15개 에이전트 존재 확인
3. Test-Path .claude/skills → False 확인 (미존재)
4. cat .claude/settings.json → hooks 섹션 없음 확인
5. git diff --check → PASS
6. python -m ingestion.tools.scan_secrets --paths .claude docs/Environment_setup → PASS
```

### PHASE B. Skills 생성 (5개 — subdirectory 형식 필수)

```
B1. New-Item -ItemType Directory .claude/skills/test-validation-skill
B2. Write .claude/skills/test-validation-skill/SKILL.md (§9 Skill 1 내용)

B3. New-Item -ItemType Directory .claude/skills/source-audit-skill
B4. Write .claude/skills/source-audit-skill/SKILL.md (§9 Skill 2 내용)

B5. New-Item -ItemType Directory .claude/skills/artifact-manifest-skill
B6. Write .claude/skills/artifact-manifest-skill/SKILL.md (§9 Skill 3 내용)

B7. New-Item -ItemType Directory .claude/skills/docs-sync-skill
B8. Write .claude/skills/docs-sync-skill/SKILL.md (§9 Skill 4 내용)

B9. New-Item -ItemType Directory .claude/skills/runner-contract-skill
B10. Write .claude/skills/runner-contract-skill/SKILL.md (§9 Skill 5 내용)
```

### PHASE C. Hooks 적용 (.claude/settings.json 수정)

```
C1. Read .claude/settings.json
C2. Edit: hooks 섹션 추가 (§10 JSON 초안 기반)
    - forbidden-command-guard (PreToolUse)
    - secret-scan-reminder (Stop)
    - docs-conflict-grep-check (Stop)
C3. python -m json.tool .claude/settings.json → JSON 유효성 확인
```

### PHASE D. gitignore 확인

```
.claude/skills/ 디렉터리가 .gitignore에서 제외되는지 확인.
현재: .claude/* 제외 + !.claude/agents/ + !.claude/agents/**
→ .claude/skills/ 도 예외 추가 필요:
  !.claude/skills/
  !.claude/skills/**
```

### PHASE E. 검증

```
E1. dir .claude/skills → 5개 디렉터리 존재 확인
E2. 각 SKILL.md frontmatter grep: name, description, user-invocable, allowed-tools
E3. python -m json.tool .claude/settings.json → JSON 유효성
E4. git diff --check → PASS
E5. python -m ingestion.tools.scan_secrets --paths .claude docs/Environment_setup → PASS
E6. Hook dry-run: PowerShell 5.1에서 stdin JSON 파싱 테스트
E7. pytest 648+ passed (skills/hooks는 코드 변경 아님 → 빠른 확인)
```

### PHASE F. 커밋

```
git add .claude/skills/
git add .claude/settings.json  # hooks 섹션 추가
git add .gitignore  # .claude/skills/ 예외 추가
git add docs/Environment_setup/ENVIRONMENT_SETUP_TRACE_FINAL.md
git add docs/Environment_setup/README.md
git commit -m "env: apply skills and hooks phase 1"

Push 금지.
```

### 검증 명령 전체

```powershell
# 1. 구조 확인
Get-ChildItem .claude/skills -Force

# 2. frontmatter 확인
Get-ChildItem .claude/skills -Recurse -Filter SKILL.md | ForEach-Object {
  $content = Get-Content $_.FullName -Raw
  $hasName = $content -match '(?m)^name:'
  $hasDesc = $content -match '(?m)^description:'
  $hasTools = $content -match '(?m)^allowed-tools:'
  [PSCustomObject]@{File=$_.FullName; name=$hasName; description=$hasDesc; allowed_tools=$hasTools}
}

# 3. JSON 유효성
python -m json.tool .claude/settings.json

# 4. secret scan
.\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths .claude docs/Environment_setup

# 5. diff check
git diff --check
```

---

## 15. Final Verdict

### Overall Verdict: APPLY_READY_WITH_REWRITES

| 분류 | 항목 | 이유 |
|------|------|------|
| APPLY_READY_WITH_REWRITES | Skills 5개 | 경로/frontmatter 스키마 수정 필요 (flat→subdirectory, tools→allowed-tools) |
| APPLY_READY_WITH_REWRITES | Hooks 3개 | stdin JSON 파싱 수정 필요 (env var → [Console]::In.ReadToEnd()) |
| DEFER_MCP_ONLY | 모든 신규 MCP | plans/012 이후 또는 영구 거절 |
| DEFER | Plugin | skills/hooks 안정화 후 |
| USER_DECISION_REQUIRED | WebSearch/WebFetch in 4 agents | 공식 지원 확인됨. 추가 여부 사용자 결정 |

### 중요 수정 사항 요약 (설계 문서 04번 대비)

1. **Skills 경로**: `.claude/skills/<name>.md` → `.claude/skills/<name>/SKILL.md`
2. **Skills frontmatter 키**: `tools:` → `allowed-tools:`, `user-invocable: true`, `when_to_use:` 추가
3. **Hook 입력**: `$env:CLAUDE_TOOL_INPUT` → stdin JSON 파싱
4. **WebSearch/WebFetch in agents**: 공식 지원 확인 → 추가 가능 (USER_DECISION_REQUIRED)
5. **.gitignore**: `.claude/skills/**` 예외 추가 필요

---

## 16. 공통 주의사항

이 명세서에서 적용되는 모든 skills/hooks/MCP는 다음을 준수한다:

```
- google_trends_explore: CONFIRMED_EXTERNAL_RATE_LIMIT (PASS 표기 절대 금지)
- 프록시 로테이션, 내부 RPC, CAPTCHA 우회, 로그인 우회 도구 도입 금지
- git push 금지
- .env 키 값 출력 금지 (존재/길이만)
- 검증 없이 "완료" 보고 금지
- 투자 조언 포함 금지 (정보 제공이지 투자 조언 아님)
- 설계 문서에 없는 신규 에이전트/skill/hook 임의 생성 금지
```

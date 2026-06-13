# docs/Environment_setup — 단일 진입점

> **상태**: 팀 에이전트 적용 완료 + Skills/Hooks/MCP/Plugin 구현 명세서 확정 (2026-06-13).
> 현재 읽어야 할 단일 문서: **[ENVIRONMENT_SETUP_TRACE_FINAL.md](./ENVIRONMENT_SETUP_TRACE_FINAL.md)**
> 다음 적용 기준: **[11_SKILLS_HOOKS_MCP_PLUGIN_SPEC.md](./11_SKILLS_HOOKS_MCP_PLUGIN_SPEC.md)**
> 00~10 번호 문서들은 적용 완료 stub이다. 재실행하지 말 것.

---

## 이 디렉터리의 목적

오케스트레이션(Celery/LangGraph, plans/012) 구현 전에 필요한 **Claude Code 환경 구축** 설계 및 적용 기록을 담는다.

---

## 신규 세션 진입점

| 문서 | 역할 |
|------|------|
| **[ENVIRONMENT_SETUP_TRACE_FINAL.md](./ENVIRONMENT_SETUP_TRACE_FINAL.md)** | 환경 설정 적용 흐름 단일 출처. 여기서 시작하라. |
| **[11_SKILLS_HOOKS_MCP_PLUGIN_SPEC.md](./11_SKILLS_HOOKS_MCP_PLUGIN_SPEC.md)** | Skills/Hooks/MCP/Plugin 구현 명세서. 다음 턴 apply 기준. |
| [README.md](./README.md) | 이 파일 — 디렉터리 안내 |

---

## 실제 적용 완료 항목 (2026-06-13)

```
✅ CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 (settings.json에 이미 활성)
✅ .claude/agents/ 생성
✅ 15개 팀 에이전트 파일 생성 (.claude/agents/*.md)
✅ 역할 중복/충돌 분석 및 10개 sub-role 통폐합 (→ test-validation-agent)
✅ ENVIRONMENT_SETUP_TRACE_FINAL.md 생성
✅ 00~10 번호 문서 stub 축약 + 원본 _archive_applied/ 이동
```

---

## 적용 완료 항목 (2026-06-13 APPLY 턴)

| 항목 | 상태 |
|------|------|
| Skills (`.claude/skills/*/SKILL.md`) | APPLIED — 5개 (test-validation, source-audit, artifact-manifest, docs-sync, runner-contract) |
| Hook 스크립트 (`.claude/hooks/*.py`) | APPLIED — 3개 (forbidden-command-guard 차단형 / secret-scan-reminder / docs-conflict-grep-check) |
| Hook wiring (`settings.json` hooks) | APPLIED (로컬 전용 — settings.json은 git untracked) |
| Hook 라이브 활성화 | CONFIRMED (별도 trust 조작 없이 동작; 라이브 차단/허용 실증) |

> 상세 평가/검증: [SKILLS_HOOKS_APPLY_TRACE.md](./SKILLS_HOOKS_APPLY_TRACE.md)

## 이번 턴 미적용 항목

| 항목 | 상태 | 다음 단계 |
|------|------|---------|
| MCP 신규 설치 | NOT_APPLIED (REJECT 3 + DEFER 7) | NEXT_TURN_MCP_REVIEW |
| Plugins | DEFERRED (skills/hooks 안정화 후) | - |
| settings.json git 추적 | USER_DECISION_REQUIRED (현재 로컬 전용) | - |
| WebSearch/WebFetch in 4 agents | USER_DECISION_REQUIRED (공식 지원 확인됨) | - |
| Phase 2/3 skills, 추가 hooks | DEFERRED | 안정화 후 |

---

## 다음 적용 순서

1. **settings.json 추적 여부** — hook wiring을 git으로 공유할지 사용자 결정 (현재 로컬 전용)
2. **WebSearch/WebFetch in agents** — 사용자 결정 후 4개 에이전트 frontmatter 업데이트
3. **MCP** — 신규 없음. Semantic Scholar KEEP. 나머지 DEFER/REJECT 유지.
4. **Orchestration** — Celery/LangGraph 구현 (plans/012)

---

## 번호 문서 00~10 안내

이 파일들은 적용 완료 stub이다. 원본은 `_archive_applied/`에 보존되어 있다.

| 파일 | 상태 |
|------|------|
| 00_ENVIRONMENT_SETUP_MASTER.md | stub (원본: _archive_applied/) |
| 01_CLAUDE_CODE_TEAM_AGENTS.md | stub (원본: _archive_applied/) |
| 02_AGENT_COMMITTEE_WORKFLOWS.md | stub (원본: _archive_applied/) |
| 03_MCP_AND_TOOLING_SURVEY.md | stub (원본: _archive_applied/) |
| 04_SKILLS_HOOKS_PLUGINS_DESIGN.md | stub (원본: _archive_applied/) — **11번 명세서로 대체됨** |
| 05_SECURITY_PERMISSIONS_POLICY.md | stub (원본: _archive_applied/) |
| 06_TEST_VALIDATION_AGENTS.md | stub (원본: _archive_applied/) |
| 07_WEB_INTELLIGENCE_PIPELINE_ENVIRONMENT.md | stub (원본: _archive_applied/) |
| 08_IMPLEMENTATION_DIFF_BLUEPRINT.md | stub (원본: _archive_applied/) |
| 09_ENVIRONMENT_SETUP_RUNBOOK.md | stub (원본: _archive_applied/) |
| 10_FINAL_ENVIRONMENT_AUDIT_CHECKLIST.md | stub (원본: _archive_applied/) |
| **11_SKILLS_HOOKS_MCP_PLUGIN_SPEC.md** | **활성 명세서 — 다음 턴 apply 기준** |

**주의: stub 재실행 금지. 이미 TRACE_FINAL에 흡수됨.**

---

## 연관 문서 (이 디렉터리 외부)

- [`docs/Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md`](../Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md) — 소스 수집 구현 단일 출처
- [`docs/ingestion/70_source_status_master.md`](../ingestion/70_source_status_master.md) — 전체 소스 상태
- [`docs/ingestion/artifact_manifest_final.md`](../ingestion/artifact_manifest_final.md) — Artifact 매니페스트

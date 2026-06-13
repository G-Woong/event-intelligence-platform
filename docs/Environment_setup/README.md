# docs/Environment_setup — 단일 진입점

> **상태**: 문서 설계 완료 (2026-06-13). **실제 config 적용은 다음 턴에서 수행.**
> 이번 턴에서 생성된 모든 diff는 `proposed diff` 형식이며, `.claude/` 실제 파일을 수정하지 않았다.

---

## 이 디렉터리의 목적

오케스트레이션(Celery/LangGraph, plans/012) 구현 전에 필요한 **Claude Code 환경 구축 설계**를 담는다.
팀 에이전트, MCP, Skills, Hooks, Plugins, 권한 정책, 검증 에이전트, 웹 인텔리전스 파이프라인 환경, diff 블루프린트를 섹터별로 정리한다.

---

## 읽는 순서

| 순서 | 파일 | 핵심 내용 |
|------|------|----------|
| 1 | [00_ENVIRONMENT_SETUP_MASTER.md](./00_ENVIRONMENT_SETUP_MASTER.md) | 프로젝트 베이스라인 스냅샷, 전체 설계 개요 |
| 2 | [01_CLAUDE_CODE_TEAM_AGENTS.md](./01_CLAUDE_CODE_TEAM_AGENTS.md) | 15개 팀 에이전트 설계 (역할/tools/계약) |
| 3 | [02_AGENT_COMMITTEE_WORKFLOWS.md](./02_AGENT_COMMITTEE_WORKFLOWS.md) | 5개 위원회 워크플로우 설계 |
| 4 | [03_MCP_AND_TOOLING_SURVEY.md](./03_MCP_AND_TOOLING_SURVEY.md) | MCP 후보 조사 및 채택/보류/거절 판정 |
| 5 | [04_SKILLS_HOOKS_PLUGINS_DESIGN.md](./04_SKILLS_HOOKS_PLUGINS_DESIGN.md) | Skills/Hooks/Plugins 설계 |
| 6 | [05_SECURITY_PERMISSIONS_POLICY.md](./05_SECURITY_PERMISSIONS_POLICY.md) | 권한·보안 정책 (least privilege 기준) |
| 7 | [06_TEST_VALIDATION_AGENTS.md](./06_TEST_VALIDATION_AGENTS.md) | 10개 테스트·검증 에이전트 설계 |
| 8 | [07_WEB_INTELLIGENCE_PIPELINE_ENVIRONMENT.md](./07_WEB_INTELLIGENCE_PIPELINE_ENVIRONMENT.md) | 파이프라인 단계별 필요 환경 |
| 9 | [08_IMPLEMENTATION_DIFF_BLUEPRINT.md](./08_IMPLEMENTATION_DIFF_BLUEPRINT.md) | 다음 턴 적용 diff 전체 블루프린트 |
| 10 | [09_ENVIRONMENT_SETUP_RUNBOOK.md](./09_ENVIRONMENT_SETUP_RUNBOOK.md) | 실제 적용 턴 runbook (단계별 명령) |
| 11 | [10_FINAL_ENVIRONMENT_AUDIT_CHECKLIST.md](./10_FINAL_ENVIRONMENT_AUDIT_CHECKLIST.md) | 최종 감사 체크리스트 |

---

## 연관 문서 (이 디렉터리 외부 — 읽기 전용)

- [`docs/Implementation_Instructions/README.md`](../Implementation_Instructions/README.md) — 소스 연결 Closing 라운드 INDEX
- [`docs/Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md`](../Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md) — 적용 완료 상태 단일 출처
- [`docs/ingestion/70_source_status_master.md`](../ingestion/70_source_status_master.md) — 전체 소스 상태
- [`docs/ingestion/86_source_role_classification_matrix.md`](../ingestion/86_source_role_classification_matrix.md) — 소스 역할 매트릭스
- [`docs/ingestion/92_mvp_collection_frequency_draft.md`](../ingestion/92_mvp_collection_frequency_draft.md) — 수집 주기 초안
- [`docs/ingestion/artifact_manifest_final.md`](../ingestion/artifact_manifest_final.md) — Artifact 매니페스트

---

## 현재 단계 (2026-06-13)

```
[DONE] 소스 연결 Closing 라운드 — PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1
[DONE] runner orchestration readiness — 13/13 agent_ready
[DONE] pytest 648 passed, secret scan PASS
[DONE] Environment Setup 문서 설계 (이번 턴)
[NEXT] Environment Setup 실제 적용 (.claude/agents, skills, hooks, permissions)
[NEXT] Celery/LangGraph 오케스트레이션 구현 (plans/012)
```

---

## 실제 적용 전 주의사항

1. **이번 턴에서 실제 config를 수정하지 않았다.** 모든 diff는 문서 내 코드블록으로만 존재한다.
2. 다음 턴에서 `08_IMPLEMENTATION_DIFF_BLUEPRINT.md`의 diff를 순서대로 적용하라.
3. 적용 전 반드시 `10_FINAL_ENVIRONMENT_AUDIT_CHECKLIST.md`의 전제 조건을 확인하라.
4. `05_SECURITY_PERMISSIONS_POLICY.md`의 least privilege 원칙을 따르라.
5. `.env` 값은 어떠한 경우에도 출력하지 말 것.
6. `git push`는 사용자 명시 전까지 금지.

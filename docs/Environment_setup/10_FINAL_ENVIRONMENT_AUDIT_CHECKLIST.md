# 10. Final Environment Audit Checklist

> **생성일**: 2026-06-13
> **목적**: 환경 설정 완료 기준 체크리스트. 실제 적용 후 이 체크리스트로 CLEAN 확인.
> **현재 상태**: 문서 설계 완료. 실제 적용 전 단계.

---

## 판정 기준 정의

| 판정 | 의미 |
|------|------|
| **PASS** | 명령 실행 또는 파일 확인으로 충족 확인 |
| **PENDING** | 아직 미적용 (다음 턴 적용 예정) |
| **IN_LOOP** | 반복 진행 중 (지속 모니터링 필요) |
| **BLOCKED** | 외부 의존성 또는 사용자 결정 필요 |
| **NOT_APPLICABLE** | 이 프로젝트에 해당 없음 |

---

## 섹션 A: 기반 환경

| # | 항목 | 상태 | 검증 명령 | evidence |
|---|------|------|----------|----------|
| A1 | Python 3.11 venv (.venv) | PASS | `.\.venv\Scripts\python.exe --version` | Python 3.11.9 |
| A2 | uv 패키지 매니저 | PASS | `uv --version` | CLAUDE.md |
| A3 | Docker Desktop (compose v2) | PASS | `docker compose version` | CLAUDE.md |
| A4 | .env 파일 존재 | PASS | `Test-Path .env` | 존재 (값 확인 없음) |
| A5 | 의존성 14/14 READY | PASS | `python -m ingestion.tools.check_dependency_readiness` | TRACE_FINAL §9 |
| A6 | CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 | PASS | `.claude/settings.json` 확인 | settings.json 실측 |

---

## 섹션 B: Claude Code 팀 에이전트

| # | 항목 | 상태 | 검증 | evidence |
|---|------|------|------|----------|
| B1 | .claude/agents/ 디렉터리 존재 | **PENDING** | `Test-Path .claude\agents` | 다음 턴 생성 |
| B2 | test-validation-agent.md | **PENDING** | `Test-Path .claude\agents\test-validation-agent.md` | 08_DIFF §B1 |
| B3 | source-ingestion-engineer.md | **PENDING** | `Test-Path .claude\agents\source-ingestion-engineer.md` | 08_DIFF §B2 |
| B4 | security-permission-guardian.md | **PENDING** | `Test-Path .claude\agents\security-permission-guardian.md` | 08_DIFF §B3 |
| B5 | docs-memory-curator.md | **PENDING** | `Test-Path .claude\agents\docs-memory-curator.md` | 08_DIFF §B4 |
| B6 | orchestrator-architect.md | **PENDING** | `Test-Path .claude\agents\orchestrator-architect.md` | 08_DIFF §B5 |
| B7 | 나머지 10개 에이전트 파일 | **PENDING** | `Get-ChildItem .claude\agents -Filter "*.md" | Measure-Object` | 01_AGENTS |
| B8 | YAML frontmatter 유효성 | **PENDING** | 파일 내용 검토 | 08_DIFF |

---

## 섹션 C: Skills

| # | 항목 | 상태 | 검증 | evidence |
|---|------|------|------|----------|
| C1 | .claude/skills/ 경로 확인 | **PENDING** | 공식 문서 확인 | VERIFY BEFORE APPLY |
| C2 | test-validation-skill.md | **PENDING** | `Test-Path .claude\skills\test-validation-skill.md` | 04_SKILLS §8 |
| C3 | source-audit-skill.md | **PENDING** | 파일 존재 | 04_SKILLS §1 |
| C4 | artifact-manifest-skill.md | **PENDING** | 파일 존재 | 04_SKILLS §3 |
| C5 | runner-contract-skill.md | **PENDING** | 파일 존재 | 04_SKILLS §2 |
| C6 | docs-sync-skill.md | **PENDING** | 파일 존재 | 04_SKILLS §4 |

---

## 섹션 D: Hooks

| # | 항목 | 상태 | 검증 | evidence |
|---|------|------|------|----------|
| D1 | hooks 스키마 확인 | **PENDING** | 공식 Claude Code 문서 | VERIFY BEFORE APPLY |
| D2 | forbidden-command-guard hook | **PENDING** | settings.json hooks 섹션 | 04_SKILLS §Hook1 |
| D3 | pre-commit-secret-scan-reminder | **PENDING** | Stop hook 존재 | 04_SKILLS §Hook2 |

---

## 섹션 E: MCP

| # | 항목 | 상태 | 검증 | evidence |
|---|------|------|------|----------|
| E1 | enableAllProjectMcpServers: false | PASS | `.claude/settings.json` | 안전, 유지 |
| E2 | Semantic Scholar MCP (허용) | PASS | settings.json allow 목록 | 실측 |
| E3 | Filesystem MCP 거절 | PASS | 설치 없음 | 03_MCP §1 (NO) |
| E4 | Browser MCP 거절 | PASS | 설치 없음 | 03_MCP §5 (NO) |
| E5 | Code Execution MCP 거절 | PASS | 설치 없음 | 03_MCP §8 (NO) |
| E6 | GitHub MCP (보류) | PASS (DEFER) | 설치 없음 | 03_MCP §2 (DEFER) |

---

## 섹션 F: 소스 수집 상태

| # | 항목 | 상태 | 검증 | evidence |
|---|------|------|------|----------|
| F1 | CORE_READY 소스 38개 | PASS | docs/70 기준 | 70_source_status_master.md |
| F2 | pytest 648 passed | PASS | `pytest -q` | 사용자 제공 |
| F3 | secret scan PASS | PASS | `scan_secrets --paths .` | closing_checklist.md |
| F4 | runner 13/13 agent_ready | PASS | `run_runner_orchestration_readiness` | TRACE_FINAL §7 |
| F5 | source checklist 14/1 | PASS | closing_checklist.md | 14 PASS + 1 CONFIRMED_EXTERNAL |
| F6 | gdelt min_interval 60s | PASS | rate_limit_policy.yaml | per_source.gdelt |
| F7 | google_trends_explore 상태 | PASS | CONFIRMED_EXTERNAL_RATE_LIMIT | fallback chain 운영 |
| F8 | google_trends_explore ≠ PASS | PASS | docs 문서 검토 | NOT_READY_EXTERNAL_RATE_LIMIT |

---

## 섹션 G: 보안 정책

| # | 항목 | 상태 | 검증 | evidence |
|---|------|------|------|----------|
| G1 | git push deny | PASS | settings.json deny 목록 | 실측 |
| G2 | rm/Remove-Item deny | PASS | settings.json deny 목록 | 실측 |
| G3 | git reset --hard deny | PASS | settings.json deny 목록 | 실측 |
| G4 | git clean deny | PASS | settings.json deny 목록 | 실측 |
| G5 | .env gitignore | PASS (가정) | `git check-ignore .env` | VERIFY |
| G6 | outputs/ gitignore | PASS | artifact_manifest_final.md §1 | 실측 |
| G7 | .env 키 값 문서 노출 없음 | PASS | scan_secrets PASS | closing_checklist.md |

---

## 섹션 H: 문서 상태

| # | 항목 | 상태 | 검증 | evidence |
|---|------|------|------|----------|
| H1 | IMPLEMENTATION_TRACE_FINAL.md 단일 출처 | PASS | Implementation_Instructions/README.md | 실측 |
| H2 | artifact_manifest_final.md 최신 | PASS | docs/ingestion/artifact_manifest_final.md | 실측 |
| H3 | Environment_setup/README.md 진입점 | PASS | 이번 턴 생성 | 실측 |
| H4 | Environment_setup/ 00~10 문서 | PASS | 이번 턴 생성 | 실측 |
| H5 | Implementation_Instructions 00~10 stub | PASS | README §문서상태 | stub만, 원문은 _archive_applied/ |
| H6 | google_trends_explore PASS 표기 없음 | PASS | `Select-String docs -Pattern "google_trends_explore.*PASS"` | docs-consistency-agent |
| H7 | proposed diff만 존재 (실제 적용 없음) | PASS | 이번 턴 제약 준수 | 이번 턴 |

---

## 섹션 I: 오케스트레이션 준비 (다음 단계)

| # | 항목 | 상태 | 계획 |
|---|------|------|------|
| I1 | Celery 설치 (plans/012) | PENDING | 오케스트레이션 구현 턴 |
| I2 | LangGraph 설치 | PENDING | 오케스트레이션 구현 턴 |
| I3 | Redis backend 전환 | PENDING | rate_limit_policy.yaml backend: redis |
| I4 | Milvus 연결 (docker-compose) | PENDING | 벡터 검색 구현 시 |
| I5 | FastAPI 설치 | PENDING | API 레이어 구현 시 |
| I6 | PostgreSQL 연결 | PENDING | event 저장 구현 시 |

---

## 최종 CLEAN 조건

아래 **모든** 항목이 PASS일 때 Environment Setup CLEAN:

```
필수 (현재 단계):
✅ A1-A6: 기반 환경 PASS
✅ E1-E6: MCP 정책 PASS
✅ F1-F8: 소스 수집 PASS
✅ G1-G7: 보안 정책 PASS
✅ H1-H7: 문서 상태 PASS

다음 턴 적용 후 추가:
⬜ B1-B8: 에이전트 파일 PASS
⬜ C1-C6: Skills PASS
⬜ D1-D3: Hooks PASS (스키마 확인 후)
```

---

## 이번 턴 최종 상태 (2026-06-13)

```
이번 턴 달성:
✅ docs/Environment_setup/ 아래 11개 문서 생성 (README + 00~10)
✅ 프로젝트 베이스라인 스냅샷 기록
✅ 15개 팀 에이전트 설계 + proposed diff
✅ 5개 위원회 워크플로우 설계
✅ MCP 후보 전수 조사 (즉시/보류/거절 판정)
✅ Skills/Hooks/Plugins 설계 + proposed diff
✅ 보안 권한 정책 문서화
✅ 10개 검증 에이전트 설계
✅ 파이프라인 환경 설계 (단계별)
✅ diff 블루프린트 작성
✅ runbook 작성
✅ 실제 config 수정 없음 (proposed diff만)
✅ git push 없음

다음 턴:
⬜ .claude/agents/ 생성 및 에이전트 파일 적용
⬜ .claude/skills/ 생성 및 skills 적용
⬜ hooks 설정 적용 (스키마 확인 후)
⬜ Celery/LangGraph 오케스트레이션 구현 (plans/012)
```

---

## 남은 항목 분류

| 항목 | 분류 |
|------|------|
| .claude/agents/ 생성 및 에이전트 파일 | NEXT_TURN_IMPLEMENTATION |
| .claude/skills/ 생성 | NEXT_TURN_IMPLEMENTATION |
| hooks 설정 (스키마 확인 후) | NEXT_TURN_IMPLEMENTATION |
| hooks 스키마 공식 확인 | USER_DECISION_REQUIRED (또는 자체 조사) |
| skills 경로 공식 확인 | USER_DECISION_REQUIRED (또는 자체 조사) |
| Celery/LangGraph 오케스트레이션 | NEXT_TURN_IMPLEMENTATION |
| Business Reality Committee 실제 실행 | NEXT_TURN_IMPLEMENTATION |
| Legal review for all READY_WITH_CAUTION 소스 | NEXT_TURN_IMPLEMENTATION |

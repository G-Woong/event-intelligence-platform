# docs/DOCS_FINAL.md — docs 최종 진입점 (신규 세션 최우선 문서)

- 최종 갱신: 2026-06-14
- 목적: docs/ 전체의 단일 진입점. 신규 세션에서 무엇을 읽을지 안내.

---

## 1. 신규 세션 진입 순서

오케스트레이션(plans/012) 구현 준비 세션:

1. **CLAUDE.md** (프로젝트 원칙 + 제약)
2. **docs/DOCS_FINAL.md** (이 파일 — docs 전체 구조)
3. **docs/ingestion/INGESTION_FINAL.md** (수집 계층 최종 상태)
4. **docs/Environment_setup/ENVIRONMENT_SETUP_FINAL.md** (환경 세팅 완료 상태)
5. **docs/Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md** (closing round 완료 trace)
6. 필요 시: `docs/system_overview/09_CURRENT_IMPLEMENTATION_STATUS.md` (시스템 전체 상태, STEP 011 기준)

---

## 2. 현재 프로젝트 상태

| 영역 | 상태 | 비고 |
|------|------|------|
| 환경 세팅 | **CLOSED** | ENVIRONMENT_SETUP_CLOSED_WITH_LOCAL_SETTINGS |
| 수집 계층 | **PASS 14/15** | google_trends_explore CONFIRMED_EXTERNAL_RATE_LIMIT (비차단) |
| 팀 에이전트 | **APPLIED 15개** | `.claude/agents/*.md` |
| skills | **APPLIED 5개** | `.claude/skills/*/SKILL.md` |
| hooks | **APPLIED 3개** | `.claude/hooks/*.py` (local-only settings.json) |
| MCP | KEEP 1 (Semantic Scholar) / 신규 없음 | NOT_APPLIED_BY_DESIGN |
| Plugin | NOT_APPLIED_BY_DESIGN | 패키징 이점 없음 |
| pytest | **509 passed 기준선** (closing round 후 추가 통과) | 무회귀 |
| **다음 작업** | **plans/012 Celery/LangGraph 오케스트레이션** | 수집 계층 인터페이스 준비 완료 |

---

## 3. docs 최종 구조

```
docs/
  DOCS_FINAL.md                           ← 이 파일 (전체 진입점)
  ingestion/
    INGESTION_FINAL.md                    ← 수집 계층 canonical (단일 출처)
    artifact_manifest_final.md            ← artifact 재생성 매니페스트
    rate_limit_evidence.md                ← provider rate-limit 근거 문서
  Implementation_Instructions/
    IMPLEMENTATION_TRACE_FINAL.md         ← closing round 완료 trace (단일 출처)
  Environment_setup/
    ENVIRONMENT_SETUP_FINAL.md            ← 환경 세팅 완료 상태 (단일 출처)
  system_overview/                        ← STEP 011.5 시스템 전체 명세 (2026-05-24)
    00_INDEX.md ~ 12_FILE_MAP_FOR_MAINTENANCE.md
  [설계 문서 17개]                          ← STEP 003-011 단편 설계 문서
    ARCHITECTURE.md, API_CONTRACT.md, EVENT_SCHEMA.md, ...
```

---

## 4. 설계 문서 목록 (docs/ 루트)

STEP 003-011 구현 시 작성된 설계 문서. system_overview가 통합 색인 역할.

| 파일 | 내용 |
|------|------|
| ARCHITECTURE.md | 전체 시스템 아키텍처 |
| API_CONTRACT.md | FastAPI 계약 초안 |
| EVENT_SCHEMA.md | 이벤트 스키마 정의 |
| COLLECTOR_DESIGN.md | 수집 계층 설계 |
| LLM_AGENT_DESIGN.md | LangGraph 에이전트 설계 |
| AGENT_WORKFLOW.md | 에이전트 워크플로우 |
| RAG_VECTOR_DESIGN.md | Milvus + 벡터 검색 설계 |
| SEARCH_DESIGN.md | 검색 설계 |
| FRONTEND_DESIGN.md | Next.js 프론트엔드 설계 |
| DEPLOYMENT.md | Docker 배포 설계 |
| OBSERVABILITY.md | 관측성 설계 |
| DATA_POLICY.md | 데이터 정책 |
| COMPLIANCE_BOUNDARY.md | 컴플라이언스 경계 |
| TRD.md | 기술 요구사항 문서 |
| COMPATIBILITY_NOTES.md | 호환성 노트 |
| PROMPT_EXPERIMENT_GUIDE.md | 프롬프트 실험 가이드 |
| SKELETON_COMPLETION_CHECKLIST.md | 스켈레톤 완성 체크리스트 |

---

## 5. system_overview 안내

`docs/system_overview/` — STEP 011.5 기준 시스템 전체 명세 (2026-05-24).

**주의**: system_overview는 STEP 011(원래 RSS 수집기 기반 아키텍처) 기준이다.
현재 `ingestion/` 계층(collection_probe, multi-strategy routing, 57+ sources)은 이 이후에 대폭 교체되었다.
시스템 전체 아키텍처(FastAPI, LangGraph, Redis, Milvus 등)는 참조 가능하지만,
수집 계층 상세는 반드시 `INGESTION_FINAL.md`를 우선한다.

| 파일 | 내용 |
|------|------|
| 00_INDEX.md | 읽기 순서 가이드 |
| 01 | 비개발자용 전체 그림 |
| 02 | 핵심 용어 사전 |
| 03 | RSS→Next.js 13단계 데이터 흐름 |
| 04 | FastAPI + Postgres + Alembic |
| 05 | 수집→큐→워커→에이전트 |
| 06 | LLM + LangGraph + Milvus |
| 07 | Next.js + Admin |
| 08 | Docker 10개 컨테이너 |
| 09 | 현재 구현 상태 (STEP 011, stale) |
| 10 | mock/stub/TODO 집계 (STEP 011, stale) |
| 11 | 다음 고도화 축 (STEP 011, stale) |
| 12 | 파일 경로 인덱스 |

---

## 6. 제거된 문서 (2026-06-14 정리)

| 범위 | 제거 수 | 이유 |
|---|---|---|
| docs/ingestion/00~93 (숫자 파일) | 91개 | INGESTION_FINAL.md로 흡수 |
| docs/Implementation_Instructions/README.md | 1개 | DOCS_FINAL.md로 역할 이전 |
| docs/Implementation_Instructions/00_OVERVIEW_AND_CLOSING_LOOP.md | 1개 | 제약은 CLAUDE.md / IMPLEMENTATION_TRACE_FINAL.md에 보존 |
| docs/Implementation_Instructions/ROADMAP.md | 1개 | stub (적용 완료) |
| docs/Implementation_Instructions/01~10 root stubs | 10개 | stub (적용 완료) |
| docs/Implementation_Instructions/_archive_applied/01~10 | 10개 | historical (git history 보존) |
| docs/Implementation_Instructions/_progress/closing_checklist.md | 1개 | IMPLEMENTATION_TRACE_FINAL.md에 흡수 |
| 이전 세션: docs/Environment_setup/ 26개 | 26개 | ENVIRONMENT_SETUP_FINAL.md로 흡수 |

git history 검색: `git log --all -- <path>` 또는 `git show <hash>:<path>`

---

## 7. 운영 원칙 (이 파일에서 한 번만 기록)

- **투자 조언 금지**: 정보 제공이지 투자 권유 아님.
- **절대 제약**: git push / rm / Remove-Item / git reset --hard / git clean 금지 (사용자 명시 전).
- **CAPTCHA/우회 금지**: robots / login / paywall / rate-limit 우회 금지.
- **google_trends_explore PASS 표기 금지**: CONFIRMED_EXTERNAL_RATE_LIMIT.
- **실패를 PASS로 보고 금지**.
- **신규 MCP 설치**: 보안/권한/중복/운영 리스크 전부 통과해야 함 (현재 신규 없음).
- **pytest 기준선**: 509 passed. 코드 변경 후 기준선이 깨지면 즉시 수정.
- **source runner 코드 수정**: source-ingestion-engineer 에이전트를 통해서만.

---

## 8. 다음 세션 next step

**plans/012 Celery/LangGraph 오케스트레이션 구현**
- 수집 계층 인터페이스 준비 완료: `run_collection_probe`, `get_store()`, `get_health_store().list_due_for_retry()`
- 환경: Python 3.11, `.venv`, Docker Desktop, docker-compose.dev.yml
- 팀 에이전트 활용: orchestrator-architect, source-ingestion-engineer, operations-sre-agent

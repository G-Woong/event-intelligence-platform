# STEP 002 후속 정리 · STEP 003 사전 설계 PLAN

## Context
STEP 002(인프라 검증)는 완료했다. 본 단계는 **앱 scaffold 진입(STEP 003) 직전의 운영/문서 정리** 단계로, 다음 4개 목적을 갖는다.

1. STEP 002에서 남긴 WARNING 3건을 가능한 범위에서 해결.
2. claude/codex worktree 운영 구조와 Codex 파일 구조 정책을 명문화.
3. `.gitignore` 손상(들여쓰기로 무력화된 패턴) 및 추적 파일 정책 정리.
4. STEP 003(앱 scaffold) 상세 실행 계획을 별도 plan 파일로 분리.

본 단계에서는 **FastAPI / Next.js / LangGraph 앱 scaffold 코드를 작성하지 않는다.**

## 현재 상태 점검 결과

| 항목 | 상태 |
|---|---|
| 작업 디렉토리 | `C:\Users\computer\Desktop\business\claude` |
| git branch | main, origin/main보다 2 commits 앞섬 |
| 미커밋 변경 | `.gitignore` 1건 (들여쓰기로 손상된 1–5 라인) |
| 최신 commit | `1a74cbb` (lancedb 다운그레이드) |
| worktree | claude=main(1a74cbb), codex=codex(90903c1) |
| Docker | 4개 서비스 모두 healthy (`ei-redis`, `ei-milvus-etcd`, `ei-milvus-minio`, `ei-milvus`) |
| `.venv` | Python 3.11.9, serve/worker/ai/vector/dev 설치 완료 |
| `docs/` | `COMPATIBILITY_NOTES.md` 1개만 존재 |
| `plans/` | 000, 001, repo-sunny-barto (현재 plan) |
| codex worktree 상태 | `.claude/settings.json`, `CLAUDE.md` **deleted** 상태 (작업트리에 물리적으로 없음) |
| codex 브랜치 ahead/behind | main에서 1 commit 뒤짐 (lancedb 핀 미포함) |

### 추가 발견
- `.gitignore` 1–5 라인이 4-space 들여쓰기 → `.claude/`, `CLAUDE.md` 패턴이 **사실상 무력화**되어 있음. main 트리에 `.claude/` 와 `CLAUDE.md`가 추적되고 있는 원인.
- codex worktree에 `.claude/` 와 `CLAUDE.md`가 없어 deleted로 보고됨. 추적 해제(`git rm --cached`)로 자동 해소될 부분.

## 사용자 결정 (이 단계에서 반영)
- lancedb optional 파일명: **`requirements/graph_optional.txt`**
- `.claude/` / `CLAUDE.md` 추적: **Claude가 `git rm --cached`로 추적 해제 후 commit** (파일 자체는 디스크 유지 — 안전한 명령, deny 정책 미저촉)

## 실행 순서

### 1. `.gitignore` 정상화
파일: `C:\Users\computer\Desktop\business\claude\.gitignore`

- 1–5 라인의 들여쓰기를 제거하고 섹션을 표준화한다.
- Codex 관련 섹션, 백업 디렉토리 항목을 추가한다.

수정 후 최종 형태(요지):
```
# Claude Code / local orchestration
.claude/
CLAUDE.md
.claude/settings.local.json
.claude/cache/

# Codex / local sub-agent
.codex/
AGENTS.md
.codex/config.toml
.codex/cache/
.codex/logs/

# Local backups
.codex_premerge_backup/

# Secrets
.env
.env.*
!.env.example

# (Python / Node / Editor / Logs / Backups 섹션은 기존 유지)
```

### 2. `.claude/` 와 `CLAUDE.md` 추적 해제
- `git rm --cached -r .claude/`
- `git rm --cached CLAUDE.md`
- 파일 자체는 디스크에 남는다 (Claude Code가 계속 읽음).
- codex worktree의 deleted 상태도 자동 해소된다.

### 3. requirements 재구성 (lancedb 분리)
- `requirements/vector.txt`에서 `lancedb`, `pylance`, `tantivy` 3줄을 제거. pymilvus 중심으로 유지.
- 신규 `requirements/graph_optional.txt` 생성:
  - `-r base.txt`
  - `lancedb==0.19.0`
  - `pylance==0.23.0`
  - `tantivy==0.25.1`
  - 파일 헤더 주석에 "Milvus가 primary, LanceDB는 optional / future GraphRAG 후보. 본 파일은 STEP 003 scaffold 범위에 포함되지 않음." 명시.
- `requirements/README.md`가 존재하면 새 파일을 표에 추가, 없으면 만들지 않고 `docs/COMPATIBILITY_NOTES.md`에만 명시.
- `.venv`에는 이미 lancedb 0.19.0이 설치되어 있어 **재설치 / 제거를 수행하지 않는다**. 단순히 핀 파일을 분리해 STEP 003 표준 설치 라인에서 빠지게 한다.

### 4. `docs/COMPATIBILITY_NOTES.md` 보강
다음 섹션을 누적 기록한다.

- `.codex_premerge_backup/` 처리:
  - 로컬 백업 잔여물. git 추적 제외 (`.gitignore` 추가됨).
  - **사용자 직접 정리 필요** — Claude는 삭제하지 않는다.
  - 사용자 수동 명령(안내만):
    ```
    Remove-Item -Recurse -Force C:\Users\computer\Desktop\business\.codex_premerge_backup
    ```
- pymilvus / pkg_resources warning:
  - 원인: pymilvus 2.4.x 또는 하위 의존성의 `pkg_resources` import. setuptools 80.x deprecation 경고.
  - Milvus Docker image: `milvusdb/milvus:v2.4.10` ↔ pymilvus 2.4.4 (서버-클라이언트 동일 메이저/마이너).
  - 임시 핀: `requirements/vector.txt`의 `setuptools>=80.9.0,<81` 유지.
  - 런타임 영향: **없음** (connect 성공 확인됨).
  - 정식 해결: pymilvus 2.6.x + Milvus image 2.6.x 동시 업그레이드 — STEP 003 이후 compatibility task로 분리.
- LanceDB 정책:
  - Milvus가 **primary vector store**.
  - LanceDB는 **optional / future GraphRAG experiment** 후보로 분리됨 (`requirements/graph_optional.txt`).
  - STEP 003 앱 scaffold 범위에서 사용하지 않음.

### 5. `docs/AGENT_WORKFLOW.md` 신규
운영 구조와 Codex 파일 정책을 명문화한다. 핵심 내용:

- worktree 역할
  - `C:\Users\computer\Desktop\business\claude` (main 브랜치): Claude Code main orchestrator. PLAN / 통합 / 리뷰 / 최종 판단 / merge gate.
  - `C:\Users\computer\Desktop\business\codex` (codex 브랜치): Codex sub-agent execution. atomic task 구현 / 테스트 / 대안 코드.
- 작업 흐름
  1. Claude가 task spec(plans 또는 `.codex/tasks/`)을 작성.
  2. Codex는 codex 브랜치에서 atomic task 수행, diff/patch로 보고.
  3. Codex는 origin에 직접 push/merge하지 않는다.
  4. Claude가 diff 리뷰 → 수용 시 main으로 cherry-pick 또는 merge.
  5. 같은 파일 동시 수정 금지.
  6. `.env`, `.claude/`, `.codex/`, local config는 commit 금지.
  7. commit 단위는 작게 유지.
- Codex 파일 구조 (설계만, 본 단계에서 모든 디렉토리를 생성하지 않음)
  ```
  C:\Users\computer\Desktop\business\codex
  ├── AGENTS.md                # gitignore 대상 (로컬 운영 노트)
  ├── .codex/
  │   ├── config.toml          # 로컬 실행 환경, gitignore
  │   ├── tasks/               # 로컬 task spec, gitignore
  │   ├── reports/             # 로컬 실행 보고, gitignore
  │   └── local/               # 잡다한 로컬, gitignore
  └── plans/                   # main과 동기화 (git 추적)
  ```
- 현재 단계에서는 `docs/AGENT_WORKFLOW.md`만 신규 작성하고, codex worktree 안에 실제 `.codex/`나 `AGENTS.md`를 만들지 않는다. (필요한 시점에 별도 생성)

### 6. `plans/003_APP_SCAFFOLD_PLAN.md` 신규
STEP 003 상세 plan을 별도 파일로 분리한다. 본 plan에는 outline만 두고, 실제 step-by-step은 003 파일로.

003 파일 outline:
- 목적: 앱 scaffold (FastAPI + LangGraph + Worker + Milvus client + 헬스 엔드포인트 + Dockerfile) 및 docker compose 통합 검증.
- 산출물:
  - `backend/app/main.py`
  - `backend/app/api/health.py`, `backend/app/api/events.py`
  - `backend/app/core/config.py` (pydantic-settings, `.env` 키 8개 + 향후 확장)
  - `backend/app/db/redis.py`, `backend/app/db/milvus.py`
  - `agents/graphs/event_processing_graph.py`
  - `agents/nodes/*.py` (normalize, dedupe, rank, summarize — mock LLM)
  - `workers/queue/producer.py`, `workers/queue/consumer.py`
  - `workers/pipelines/raw_event_pipeline.py`
  - `backend/Dockerfile`, `workers/Dockerfile`, `agents/Dockerfile`
  - `docker-compose.dev.yml` 업데이트 (backend / worker / agent-worker 서비스 추가)
  - `docs/EVENT_SCHEMA.md` 초안
  - `docs/API_CONTRACT.md` 초안
  - `tests/smoke/*.py`
- 비범위(STEP 003에서 하지 않음):
  - Next.js 풀 UI 구현
  - 실제 대규모 crawler / Playwright / Selenium
  - torch / transformers / Gemma 로컬 서빙
  - 실제 KG-RAG 고도화
  - production deploy / 도메인 연결
- 검증 절차:
  - `docker compose -f docker-compose.dev.yml config`
  - `docker compose ... build backend worker agent-worker`
  - `docker compose ... up -d`
  - `curl http://localhost:8000/health`
  - Redis ping (컨테이너 ↔ 호스트, app ↔ Redis)
  - Milvus connect (app ↔ Milvus)
  - sample raw event enqueue → worker consume → LangGraph mock pipeline → final_card 조회

### 7. pymilvus warning 실측 (선택 — venv import smoke)
이미 STEP 002에서 import / connect 성공 확인. warning 텍스트만 짧게 캡처해 `COMPATIBILITY_NOTES.md`에 인용. 본 단계에서 새로 설치 / 업그레이드하지 않는다.

### 8. commit
- 메시지: `chore: finalize step 002 orchestration setup`
- 포함 변경:
  - `.gitignore` 정상화
  - `.claude/`, `CLAUDE.md` 추적 해제 (`git rm --cached`)
  - `requirements/vector.txt` (lancedb 3줄 제거)
  - `requirements/graph_optional.txt` 신규
  - `docs/COMPATIBILITY_NOTES.md` 갱신
  - `docs/AGENT_WORKFLOW.md` 신규
  - `plans/003_APP_SCAFFOLD_PLAN.md` 신규
- **push는 수행하지 않는다.**

## 수정·생성 대상 파일

| 경로 | 작업 |
|---|---|
| `.gitignore` | 수정 (들여쓰기 제거 + Codex/백업 섹션) |
| `.claude/`, `CLAUDE.md` | `git rm --cached`로 추적 해제 (디스크 유지) |
| `requirements/vector.txt` | 수정 (lancedb/pylance/tantivy 제거) |
| `requirements/graph_optional.txt` | 신규 |
| `docs/COMPATIBILITY_NOTES.md` | 수정 (3개 섹션 추가) |
| `docs/AGENT_WORKFLOW.md` | 신규 |
| `plans/003_APP_SCAFFOLD_PLAN.md` | 신규 |
| `plans/repo-sunny-barto.md` | 본 plan (현재 작성 중) |

## 검증 (최종 보고에 포함)
- [ ] `git status` clean (커밋 후)
- [ ] `git log --oneline -5` 신규 commit 표시
- [ ] `git ls-files .claude CLAUDE.md` → empty (추적 해제 확인)
- [ ] `Test-Path .claude\settings.json` = True (디스크 유지 확인)
- [ ] `Test-Path CLAUDE.md` = True (디스크 유지 확인)
- [ ] `requirements/vector.txt`에 lancedb/pylance/tantivy 부재
- [ ] `requirements/graph_optional.txt` 존재 및 3개 패키지 핀
- [ ] `docs/AGENT_WORKFLOW.md`, `plans/003_APP_SCAFFOLD_PLAN.md` 신규 존재
- [ ] `docs/COMPATIBILITY_NOTES.md`에 `.codex_premerge_backup`, pymilvus, lancedb 섹션 추가
- [ ] codex worktree의 deleted 상태 해소 (`git -C codex status`)
- [ ] Docker 4개 서비스 healthy 유지

## 사용자 직접 정리 필요 (Claude가 실행하지 않음)
- `C:\Users\computer\Desktop\business\.codex_premerge_backup\` 물리 삭제
  - 안내 명령(사용자가 직접 입력): `Remove-Item -Recurse -Force C:\Users\computer\Desktop\business\.codex_premerge_backup`

## 금지 사항 (재확인)
- ❌ `Remove-Item`, `rm`, `del`, `rmdir` (deny 정책)
- ❌ `git push` (사용자 명시 요청 전까지)
- ❌ `git reset --hard`, `git clean -fdx`
- ❌ FastAPI / Next.js / LangGraph 앱 scaffold 코드
- ❌ ml / crawler 의존성 설치 (torch, playwright 등)
- ❌ pymilvus / Milvus 버전 업그레이드 (STEP 003 이후 별도 task)
- ❌ Docker 컨테이너 down/stop (running 상태 유지)
- ❌ `.env` 실값 출력/로그/외부 전송

## STEP 003 진입 조건 (본 단계 완료 후)
1. 본 plan의 검증 항목 모두 PASS
2. codex 브랜치 상태 정상 (deleted 미표시)
3. `plans/003_APP_SCAFFOLD_PLAN.md`에 다음 단계 명세가 명확히 기록됨
4. 사용자가 STEP 003 시작 승인

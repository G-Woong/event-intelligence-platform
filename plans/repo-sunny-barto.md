# STEP 002.6 — codex worktree 실행환경 실검증/복구

## Context

STEP 002.5(orchestration 정리)는 main worktree 기준으로 완료했지만, codex worktree는 아직 "껍데기"만 있는 상태다. 본 단계의 목적은 **codex가 단순 폴더/브랜치가 아니라 실제로 atomic task를 수행할 수 있는 독립 실행 환경**임을 검증하고 부족분을 보강하는 것이다.

### 사전 점검 결과 (read-only)

| 항목 | 상태 |
|---|---|
| `git worktree list` | ✅ claude=main(`c93695f`), codex=codex(`511c944`) — 정상 worktree로 인식 |
| codex 브랜치 head | `511c944 chore: untrack .claude/ and CLAUDE.md (mirror main)` |
| codex `.env` | ✅ 8개 키 모두 PRESENT (실값 미노출) |
| codex `.venv` | ❌ **없음** — Python 환경 미구성 |
| codex `AGENTS.md` | ❌ 없음 |
| codex `.codex/config.toml` | ❌ 없음 |
| codex `requirements/vector.txt` | ⚠️ main과 어긋남 (lancedb==0.29.2/pylance==2.0.0이 남아있음) |
| codex `pyproject.toml` | main에 없는 파일. codex `.gitignore`에 추적 제외로 추가됨 |
| codex `.gitignore` modified | 사용자가 IDE에서 `pyproject.toml` 라인 추가한 상태 |
| Docker (claude 측) | ✅ 4개 서비스 healthy (ei-redis, ei-milvus, ei-milvus-etcd, ei-milvus-minio) |
| `uv` PATH | ⚠️ 현 PowerShell 세션에서 인식 안 됨 (재시작 또는 풀 경로 필요) |
| `py -3.11` | ✅ Python 3.11.9 사용 가능 |

### 사용자 결정 (본 단계에 반영)

1. **codex 동기화**: main → codex **merge** (vector.txt 정리, `.gitignore` 통일, `graph_optional.txt`, docs/plans 동기)
2. **pyproject.toml**: 현재 상태 유지. codex `.gitignore`의 추적 제외 라인 유지, main에는 추가하지 않음
3. **uv fallback**: 풀 경로(`%USERPROFILE%\.local\bin\uv.exe` 등) 탐색 후 사용

## 실행 순서

### 1. codex `.gitignore` 검토 (modified 상태 처리)
- codex `.gitignore`의 현재 modified 변경(=`pyproject.toml` 라인 추가)을 **그대로 살린다**.
- 단, main의 `.gitignore`와 비교해 누락 섹션(`.codex_premerge_backup/`, Codex 섹션 정리 등)이 있으면 동일 형식으로 조정한다.
- main과 동일하게 깔끔하게 재정렬하되, `pyproject.toml` 라인은 보존.

### 2. main → codex merge
codex worktree에서:
```
git -C C:\Users\computer\Desktop\business\codex fetch  # 필요시
git -C C:\Users\computer\Desktop\business\codex merge main
```
- 충돌 가능 지점: `requirements/vector.txt`, `.gitignore` → 사용자 결정 기준으로 해결
  - `requirements/vector.txt`: main 버전 채택 (LanceDB 제거)
  - `.gitignore`: main 형식 채택 + codex의 `pyproject.toml` 라인 유지
- `pyproject.toml`은 codex 전용 파일이므로 merge로 인해 사라지지 않는다. (main에 없음 + .gitignore에 추적 제외 라인 유지)
- merge commit 메시지: `chore: sync codex with main (step 002.5)`

### 3. codex `.venv` 생성
PowerShell에서 uv 풀 경로를 먼저 탐색한다:
- 후보 경로: `$env:USERPROFILE\.local\bin\uv.exe`, `$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe`, `$env:LOCALAPPDATA\Programs\uv\uv.exe`
- `Get-Command uv -ErrorAction SilentlyContinue` 1차 시도
- 둘 다 안 되면 `winget show astral-sh.uv` 정보로 설치 경로 추론

uv 발견 시:
```
& <uv full path> venv "C:\Users\computer\Desktop\business\codex\.venv" --python 3.11
```

검증:
```
C:\Users\computer\Desktop\business\codex\.venv\Scripts\python.exe --version
```
→ `Python 3.11.9` 기대.

### 4. requirements 설치 (codex .venv)
설치 범위 (지정된 5+1 레이어):
- `requirements/base.txt`
- `requirements/serve.txt`
- `requirements/worker.txt`
- `requirements/ai.txt`
- `requirements/vector.txt`
- `requirements/dev.txt`

**설치 금지**:
- `requirements/ml.txt`
- `requirements/crawler.txt`
- `requirements/graph_optional.txt`

명령(uv pip):
```
& <uv path> pip install --python C:\Users\computer\Desktop\business\codex\.venv\Scripts\python.exe -r requirements\serve.txt
... (worker, ai, vector, dev 순으로 반복; base는 -r 체이닝으로 자동 포함)
```

각 단계 후 exit code 확인. 실패 시 BLOCKED로 보고하고 진행 중단.

### 5. codex `AGENTS.md` 생성
파일: `C:\Users\computer\Desktop\business\codex\AGENTS.md`
(`.gitignore`에 의해 추적 제외, 디스크에만 존재)

내용(간결):
```
# AGENTS.md — Codex sub-agent execution worktree

- Codex는 sub-agent execution worktree다.
- main 브랜치에 직접 merge/push 금지.
- atomic task만 수행. 완료 후 diff/report 작성.
- Claude main orchestrator가 수용 여부 판단.
- `.env` 실값 출력/로그/외부 전송 금지.
- destructive command(rm/Remove-Item/git reset --hard 등) 실행 금지.
- 본 worktree는 별도 .venv를 가지며, Docker infra는 claude의 docker-compose.dev.yml을 공유한다.
```

### 6. codex `.codex/config.toml` 생성
경로: `C:\Users\computer\Desktop\business\codex\.codex\config.toml`
(`.gitignore`에 의해 추적 제외)

내용(최소):
```toml
# .codex/config.toml — Codex worktree 로컬 실행 환경
# 본 파일은 .gitignore 대상이며 commit되지 않는다.

[worktree]
role = "sub-agent-execution"
python_venv = ".venv"
python_version = "3.11"

[infra]
shared_compose = "../claude/docker-compose.dev.yml"
redis_url = "redis://localhost:6379/0"
milvus_host = "localhost"
milvus_port = 19530

[policy]
allow_push = false
allow_destructive = false
allow_main_merge = false
```

`.codex/tasks/`, `.codex/reports/`, `.codex/local/`은 본 단계에서는 디렉토리 생성만 하지 않고 필요 시점에 생성한다.

### 7. Docker shared infra 연결 검증 (codex .venv 기준)
- Docker daemon 상태: `docker ps`로 확인
- compose 상태: `docker compose -f C:\Users\computer\Desktop\business\claude\docker-compose.dev.yml ps`
- codex .venv Python으로 다음 import 및 smoke:
  ```
  python -c "import fastapi, redis, pymilvus, langgraph, langchain, openai, pydantic, pytest; print('imports ok')"
  python -c "import redis; r=redis.from_url('redis://localhost:6379/0'); print('redis ping:', r.ping())"
  python -c "from pymilvus import connections; connections.connect(host='localhost', port='19530'); print('milvus connect ok')"
  ```
- LangSmith / OpenAI 키는 `os.getenv` 존재 여부만 확인 (실값 출력 금지)

### 8. 문서 업데이트
`docs/AGENT_WORKFLOW.md`에 다음 내용을 추가/보강:
- claude worktree = orchestration / review / merge gate
- codex worktree = isolated execution / test / atomic implementation
- **codex는 별도 `.venv`를 가진다**
- **Docker infra는 기본적으로 claude의 docker-compose.dev.yml을 공유한다** (codex localhost로 접근)
- 추후 필요 시 `COMPOSE_PROJECT_NAME`으로 codex 독립 infra를 띄울 수 있다는 가능성만 한 줄로 명시
- 현재 단계 default는 shared infra

### 9. 보고서 생성
`plans/002_6_CODEX_ENV_RECOVERY_REPORT.md` 신규 작성. 다음 항목을 포함:
- codex worktree 정상 인식 여부
- codex 브랜치 / 최근 commit
- main → codex merge 결과 (commit hash, 충돌 처리 내역)
- codex `.venv` 생성 결과 (Python 버전 확인 출력)
- requirements 설치 결과 (5+1 레이어, 각 단계 exit code)
- codex `.env` 키 점검 (masked)
- `AGENTS.md`, `.codex/config.toml` 생성 여부
- Docker shared infra 연결 결과 (Redis ping, Milvus connect)
- 핵심 패키지 import smoke 결과
- 남은 WARNING / BLOCKED / UNKNOWN
- STEP 003 진입 가능 여부

### 10. commit (main worktree)
- 메시지 후보: `docs: document codex worktree env recovery (step 002.6)`
- 포함 변경:
  - `docs/AGENT_WORKFLOW.md` 보강
  - `plans/002_6_CODEX_ENV_RECOVERY_REPORT.md` 신규
  - `plans/repo-sunny-barto.md` 본 plan (참고용)
- **push 금지**

codex worktree commit:
- main merge commit (step 2)
- `.gitignore` 정리 commit (필요 시)
- **codex 측 commit 메시지는 모두 prefix `chore(codex):` 사용**

## 수정·생성 대상 파일 정리

| 경로 | worktree | 작업 |
|---|---|---|
| `codex/.gitignore` | codex | 정리 (pyproject.toml 라인 유지, main 형식 정렬) |
| `codex/requirements/vector.txt` | codex | merge 시 main 버전 채택 |
| `codex/.venv/` | codex | 신규 (uv venv) |
| `codex/AGENTS.md` | codex | 신규 (gitignore 대상) |
| `codex/.codex/config.toml` | codex | 신규 (gitignore 대상) |
| `claude/docs/AGENT_WORKFLOW.md` | main | 보강 (venv/shared infra 명시) |
| `claude/plans/002_6_CODEX_ENV_RECOVERY_REPORT.md` | main | 신규 |
| `claude/plans/repo-sunny-barto.md` | main | 본 plan |

## 검증 (최종 보고에 포함)

- [ ] `git worktree list` claude=main, codex=codex 정상
- [ ] `git -C codex status` clean (merge 후)
- [ ] `git -C codex log --oneline -3`에 main 동기 commit 표시
- [ ] `codex/.venv/Scripts/python.exe --version` → Python 3.11.x
- [ ] codex `.venv`에서 fastapi/redis/pymilvus/langgraph/langchain/openai/pydantic/pytest import 성공
- [ ] codex `.venv`에서 Redis ping = True
- [ ] codex `.venv`에서 Milvus connect 성공
- [ ] codex `.env` 8개 키 PRESENT (masked)
- [ ] codex `AGENTS.md`, `.codex/config.toml` 디스크 존재 + git ls-files에서 empty (추적 제외 확인)
- [ ] `docs/AGENT_WORKFLOW.md`에 venv/shared infra 문구 추가됨
- [ ] `plans/002_6_CODEX_ENV_RECOVERY_REPORT.md` 신규 존재
- [ ] Docker 4개 서비스 healthy 유지

## 금지 사항 (재확인)

- ❌ `Remove-Item`, `rm`, `del`, `rmdir` (deny 정책)
- ❌ `git push` (사용자 명시 요청 전까지)
- ❌ `git reset --hard`, `git clean -fdx`
- ❌ FastAPI / Next.js / LangGraph 앱 scaffold 코드 (STEP 003에서 진행)
- ❌ `requirements/ml.txt`, `requirements/crawler.txt`, `requirements/graph_optional.txt` 설치
- ❌ pymilvus / Milvus 버전 업그레이드
- ❌ Docker 컨테이너 down/stop (running 유지)
- ❌ `.env` 실값 출력/로그/외부 전송
- ❌ codex 측 commit을 main으로 자동 merge/push

## BLOCKED 처리 기준

다음 상황이 발생하면 즉시 BLOCKED로 보고하고 사용자 결정을 요청한다:
- main → codex merge 충돌이 사용자 결정(vector.txt=main, .gitignore=main+pyproject 라인) 범위를 넘는 경우
- uv 풀 경로를 어떤 후보에서도 찾지 못함 → 사용자에게 설치 경로 문의
- requirements 설치 단계 중 어느 한 레이어가 실패
- Redis ping 또는 Milvus connect 실패

## STEP 003 진입 조건 (본 단계 완료 후)

1. 본 plan의 검증 항목 모두 PASS
2. codex `.venv`에서 핵심 라이브러리 import 및 shared infra 연결 OK
3. `plans/002_6_CODEX_ENV_RECOVERY_REPORT.md` 작성 완료
4. 사용자가 STEP 003 시작 승인

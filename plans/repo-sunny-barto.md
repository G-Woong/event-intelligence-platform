# STEP 002 PLAN — codex worktree · Docker 인프라 up · requirements 설치 검증

## Context
STEP 001에서 환경/메타 파일을 정의하고 GitHub에 push까지 완료했다. 본 단계는 **앱 코드 작성 직전 인프라 검증** 단계로, 다음을 실제로 가동시켜 다음 phase(scaffold)가 안전하게 출발할 토대를 만든다:

1. `C:\Users\computer\Desktop\business\codex`를 **claude 레포의 git worktree**로 정식 구성 (별도 `codex` 브랜치)
2. codex worktree에서도 `.claude/settings.json`(프로젝트 권한) + `.env`가 사용 가능한지 확인
3. `docker-compose.dev.yml`로 Milvus 스택(etcd/minio/standalone) + Redis 실제 `up`, 헬스체크 통과 확인
4. `.venv`에 backend/agents/workers 핵심 layer(`serve` + `worker` + `ai` + `vector` + `dev`) 실제 설치 → import smoke test
5. Redis/Milvus 연결을 venv에서 코드로 검증

**범위 밖**: FastAPI/Next.js 앱 scaffold, ML(`torch`) / crawler(`playwright`) 의존성 설치.

## 사전 정리 (블로커 해소)

claude/ 작업트리에 미커밋 변경 3건 존재 → **삭제 확정 커밋** (사용자 결정):
- `D .env.example` (커밋되어 있었으나 사용자가 의도적으로 제거)
- `D requirements.txt` (원본 잠금파일도 함께 제거)
- ` M .gitignore` (현재 내용으로 확정)

> ⚠️ WARNING: `.env.example`은 8개 키 가이드 문서였으나 사용자 결정에 따라 제거한다. 키 가이드는 `CLAUDE.md`의 `.env 정책` 섹션에 남아있으므로 정보 손실은 없음.
> ⚠️ WARNING: 원본 잠금 스냅샷 `requirements.txt`는 사라진다. STEP 001 plan에서 보존 정책이었으나 사용자 재결정에 따라 폐기. 의존성 핀은 `requirements/*.txt` 8개 분리본에 보존되어 있음.

## 실행 순서

### 1. 잔여 미커밋 변경 커밋
- `git add -A` 후 메시지: `chore: drop legacy requirements.txt and .env.example, finalize .gitignore`
- push는 사용자 명시 요청이 있을 때만 수행. 본 단계에서는 push 보류.

### 2. codex 디렉토리 통째로 백업 (worktree 경로 비우기)
codex/에는 다음 2개 파일이 있어 git worktree add를 차단한다:
- `codex\.env` (2157B, claude/.env와 동일 추정 — 라인수 75 일치)
- `codex\requirements.txt` (7448B, UTF-16 BOM, 폐기 대상)

`Remove-Item` / `rmdir`은 deny 정책에 걸리므로 `Move-Item`으로 **디렉토리 자체를 통째로 옮긴다**(rename 효과):
```
Move-Item C:\Users\computer\Desktop\business\codex C:\Users\computer\Desktop\business\.codex_premerge_backup
```
이렇게 하면 codex 경로가 비고, worktree add가 새 디렉토리를 생성할 수 있다. 기존 `.env` / `requirements.txt`는 `.codex_premerge_backup\` 아래에 보존된다.

### 3. codex worktree 생성
claude/ 안에서:
```
git worktree add -b codex C:\Users\computer\Desktop\business\codex
```
- `-b codex`: main에서 새 `codex` 브랜치 생성 후 해당 경로 체크아웃
- `git worktree list`로 확인: claude=main, codex=codex 두 항목.

### 4. codex worktree에 .env 복원
- `Copy-Item C:\Users\computer\Desktop\business\.codex_premerge_backup\.env C:\Users\computer\Desktop\business\codex\.env`
- (`Copy-Item`은 deny 대상 아님. backup 폴더는 사용자가 추후 직접 정리하도록 유지.)
- `.env`는 `.gitignore`에 등재되어 있으므로 git에 추적되지 않음 (codex 브랜치에도 영향 없음).
- 백업 폴더의 구 `requirements.txt`는 폐기 대상이지만 deny 정책 때문에 본 단계에서 삭제하지 않고 보고에 안내.

### 5. codex worktree 설정 검증
- `Test-Path codex\.claude\settings.json` → `True` 기대 (main에서 트래킹된 파일이 worktree에 자동 노출됨)
- `Test-Path codex\.env` → `True` 기대
- `Test-Path codex\CLAUDE.md` → `True` 기대
- `git -C codex status` → clean working tree on codex branch
- `git -C codex log --oneline -3` → 5dd417d 포함된 main 기준 history 노출

### 6. Docker 스택 가동
- `docker compose -f docker-compose.dev.yml up -d`
- 직후 `docker compose -f docker-compose.dev.yml ps`로 4개 서비스(etcd / minio / milvus / redis) 상태 점검
- 헬스체크 대기:
  - 백그라운드로 `docker compose ... ps` 폴링 (모두 `healthy` 도달까지 최대 ~3분 예상)
  - 실패 시 `docker compose logs <서비스>`로 원인 기록 → compose 수정 → 재시도

### 7. 포트 / 연결 확인
| 서비스 | 포트 | 확인 명령 |
|---|---|---|
| Redis | 6379 | `docker exec ei-redis redis-cli ping` → `PONG` |
| Milvus gRPC | 19530 | `Test-NetConnection localhost -Port 19530` → TcpTestSucceeded True |
| Milvus REST | 9091 | `curl http://localhost:9091/healthz` → 200 |
| MinIO console | 9001 | `Test-NetConnection localhost -Port 9001` → True |

### 8. uv venv에 핵심 requirements 설치
`.venv` (Python 3.11.9, 기존 존재)에서:
```
uv pip install -r requirements\serve.txt -r requirements\worker.txt -r requirements\ai.txt -r requirements\vector.txt -r requirements\dev.txt --python .venv\Scripts\python.exe
```
- 실패 시:
  - 충돌 핀 식별 → 해당 `requirements/*.txt` 수정 (예: `setuptools<81` 같은 호환 핀 추가)
  - 재시도 후 결과 기록

### 9. 설치 후 smoke import
venv 활성화 후:
```python
import fastapi, uvicorn, starlette
import celery, redis, rq
import langchain, langgraph, langsmith, openai
import pymilvus, lancedb
import pytest, ruff, mypy   # 도구류는 모듈 import가 안 되는 경우 console_scripts 호출로 대체
```
모듈별 `__version__` 또는 존재 여부 출력.

### 10. Redis/Milvus 실연결 확인 (venv ↔ 컨테이너)
- Redis: `python -c "import redis; r=redis.from_url('redis://localhost:6379/0'); print(r.ping())"` → `True`
- Milvus: `python -c "from pymilvus import connections; connections.connect(alias='default', host='localhost', port='19530'); print('ok')"` → `ok`

### 11. 종료 (Docker 컨테이너 stop 여부)
- 본 단계 완료 후 컨테이너 stop은 **사용자 결정 사항**. 기본은 **유지**(STEP 003에서 즉시 활용 가능).
- 보고에 컨테이너 상태와 종료 방법(`docker compose ... stop` / `down`) 안내.

## 수정·생성 대상 파일 / 경로

| 경로 | 작업 | 비고 |
|---|---|---|
| `claude/` (git) | commit | 미커밋 deletions 확정 |
| `C:\Users\computer\Desktop\business\codex` | worktree로 재구성 | 기존 파일 2개 backup 후 |
| `codex\.env` | 백업본 복원 | 75 lines |
| `codex` 브랜치 | 신규 생성 | from main |
| `requirements\*.txt` | 필요 시 핀 수정 | 설치 실패 시에만 |
| `docker-compose.dev.yml` | 필요 시 수정 | 헬스체크 실패 시에만 |
| `.codex_oldreq.bak` (business 직속) | UTF-16 원본 보관 | 사용자 정리 대상 |

## 검증 (최종 보고에 포함)
- [ ] `git worktree list` 출력 (claude=main, codex=codex)
- [ ] `git -C codex branch --show-current` = `codex`
- [ ] `Test-Path codex\.claude\settings.json` = True
- [ ] `Test-Path codex\.env` = True (키 8개 라인 존재, 값은 마스킹)
- [ ] `docker compose -f docker-compose.dev.yml ps` — 4개 서비스 healthy
- [ ] `docker exec ei-redis redis-cli ping` = `PONG`
- [ ] `curl http://localhost:9091/healthz` = 200
- [ ] venv에서 pymilvus / redis 연결 성공 출력
- [ ] 설치 패키지 수, 실패 / 충돌 여부 기록
- [ ] WARNING / BLOCKED / UNKNOWN 항목 명시

## 금지 사항 (재확인)
- ❌ `Remove-Item`, `rm`, `del`, `rmdir` 계열 (deny 정책)
- ❌ `git push` (사용자 명시 요청 없으면 보류)
- ❌ `git reset --hard`, `git clean -fdx`
- ❌ FastAPI / Next.js 앱 scaffold 생성
- ❌ ml / crawler 의존성 설치 (torch, playwright 등)
- ❌ 전역 Claude Code 설정(`~/.claude/settings.json`) 수정
- ❌ `.env` 실값 출력/로그/외부 전송

## STEP 003 진입 조건
모두 PASS 시 STEP 003(앱 scaffold) 진입 가능:
1. codex worktree clean, codex 브랜치 활성
2. Milvus + Redis 컨테이너 healthy
3. 핵심 requirements(serve/worker/ai/vector/dev) `.venv`에 설치 완료, import 정상
4. venv에서 Redis/Milvus 실연결 확인

하나라도 FAIL이면 STEP 003 보류, 원인 기록 후 사용자 결정 요청.

## STEP 003 예고
- `app/` 디렉토리 scaffold (FastAPI + LangGraph + Celery + Milvus client + 헬스 엔드포인트)
- `Dockerfile` (app, worker)
- `docker-compose.dev.yml`에 app/worker 서비스 추가
- 최소 LangGraph 그래프 1개로 end-to-end smoke test
- Next.js 프론트엔드는 그 이후 단계로 분리

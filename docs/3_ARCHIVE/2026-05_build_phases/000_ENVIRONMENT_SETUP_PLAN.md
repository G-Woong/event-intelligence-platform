# 000 — 환경 세팅 PLAN

## 목적
"전세계 실시간 사건/이벤트 인텔리전스 웹앱" 본 구현 전에 운영 기반(설정, 가상환경, Docker, 운영 문서)을 확정한다.

## 1. 환경 점검 결과 (이번 단계)

| 항목 | 상태 | 메모 |
|---|---|---|
| 작업 디렉토리 | `C:\Users\computer\Desktop\business\claude` | ✅ |
| git repo (claude/) | INITIALIZED (이번 단계) | `git init`만 실행, commit/push 없음 |
| git repo (codex/) | 미초기화 | 사용자 결정에 따라 보류 |
| `.env` (claude/, codex/) | 8/8 키 PRESENT | 값 미노출, 길이만 확인 |
| `CLAUDE.md` | UTF-8 재작성 완료 | 기존은 `.bak`으로 백업 |
| `.gitignore` | UTF-8 재작성 완료 | 기존은 `.bak`으로 백업 |
| `requirements.txt` | UTF-16, 181줄 | **이번 단계에서 손대지 않음** (다음 단계에서 분리) |
| `.claude/settings.json` | 생성 | 프로젝트 스코프 |
| `plans/` | 생성 | 본 문서 포함 |
| `docs/` | 생성 | `COMPATIBILITY_NOTES.md` 포함 |
| `.venv/` | uv venv로 생성 (Python 3.11) | uv winget 설치 후 |
| uv | 설치 | winget |
| Python 3.11 | 사용 가능 | `py -3.11` |
| Docker | 27.4.0 client/server | ✅ daemon 실행 중 |
| Docker Compose | v2.31.0-desktop.2 | ✅ |

## 2. Claude Code 설정 적용 내역
파일: `.claude/settings.json` (프로젝트 스코프)
- `model`: `opusplan` (스키마 미등재, 보존)
- `language`: `korean`
- `showClearContextOnPlanAccept`: `true`
- `plansDirectory`: `plans`
- `enableAllProjectMcpServers`: `false`
- `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`: `"1"` (지원 불명, 보존)
- `permissions.allow`: PowerShell/Bash 와일드카드, WebFetch 허용 도메인, `mcp__semantic-scholar__search_paper`, `Skill(update-config)` 등
- `permissions.deny`: `git push`, `rm`/`del`/`erase`/`rmdir`/`Remove-Item` 계열, `git reset --hard`, `git clean -fdx`

## 3. uv venv 상태
- uv: winget `astral-sh.uv`로 설치
- venv 생성: `uv venv .venv --python 3.11`
- 검증: `.\.venv\Scripts\python.exe --version` → Python 3.11.x
- **이번 단계에서 requirements 설치는 절대 수행하지 않음**

## 4. Docker 상태
- `docker version`: 27.4.0 client+server
- `docker compose version`: v2.31.0-desktop.2
- daemon 동작 확인됨
- **build/up 미수행**

## 5. 다음 단계 작업 예고
1. `requirements.txt` UTF-8 재인코딩 + 용도별 분리 (`requirements/base.txt`, `requirements/dev.txt`, `requirements/serve.txt`, `requirements/worker.txt` 등)
2. `pyproject.toml` 설계 (선택)
3. `docker-compose.dev.yml` 작성 (Milvus, Redis, app)
4. `.env.example` 생성 (실값 없이 키 이름만)
5. 앱 scaffold (FastAPI + LangGraph + Celery + Milvus + Redis)
6. codex worktree git 정책 결정

## 6. 금지 사항 (재확인)
- ❌ 앱 scaffold (모듈/엔드포인트 코드)
- ❌ `pip install` / `uv pip install` (requirements 설치)
- ❌ `docker compose build/up`
- ❌ `git commit` / `git push`
- ❌ destructive 명령 (rm/del/Remove-Item/git reset --hard/git clean -fdx)
- ❌ `.env` 실값 출력
- ❌ codex/ git init

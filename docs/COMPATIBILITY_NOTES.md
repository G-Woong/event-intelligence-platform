# COMPATIBILITY NOTES

이 문서는 환경/도구의 호환성과 지원 여부를 기록한다. **삭제하지 말고 누적**한다.

## Claude Code 설정 옵션
참조: `code.claude.com/docs/en/settings.md`, `code.claude.com/docs/en/permissions.md`

| 키 | 상태 | 비고 |
|---|---|---|
| `showClearContextOnPlanAccept` | SUPPORTED | "Git & Attribution" 섹션 |
| `plansDirectory` | SUPPORTED | "Memory & Storage" 섹션, 예: `"./plans"` |
| `language` | SUPPORTED | "Language & Localization" — Korean도 동작 가능 |
| `enableAllProjectMcpServers` | SUPPORTED | "MCP & Plugins" |
| `env` 객체 | SUPPORTED | 임의 env 변수 주입 가능 |
| `permissions.allow` / `permissions.deny` | SUPPORTED | `Bash(...)`, `PowerShell(...)`, `WebFetch(domain:...)`, `mcp__server__tool` 등 |
| `model: "opusplan"` | **UNKNOWN** | 공식 settings 스키마에는 미등재. CLI alias로는 알려진 값이라 보존. 동작 검증 필요. 미지원 시 fallback은 `"opus"` 또는 `"claude-opus-4-6"`. |
| `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | **UNKNOWN** | 공식 환경변수 목록 미등재. 동작/효과 미확인. |
| `Skill(update-config)` 권한 문법 | **UNKNOWN** | Skill 권한 문법은 공식 예시에 부재. 실제 invocation 시 prompt 발생 여부 관찰 필요. |

## 권한 규칙 문법 (확인됨)
- `Bash(git push *)`, `Bash(git push)`
- `PowerShell(Remove-Item *)`, `PowerShell(rm *)`
- `Bash(git reset --hard *)`, `Bash(git reset --hard)`
- `Bash(git clean -fdx *)`, `Bash(git clean -fdx)`
- `WebFetch(domain:github.com)`
- `mcp__semantic-scholar__search_paper` (`mcp__<server>__<tool>`)

## 프로젝트 vs 로컬 스코프
- `.claude/settings.json` — 커밋용, 팀 공유
- `.claude/settings.local.json` — gitignore, 개인 오버라이드

## Python / uv
- Python 3.11: 사용 가능 (`py -3.11 → C:\Users\computer\AppData\Local\Programs\Python\Python311\python.exe`)
- Python 3.13.5: 기본이지만 본 프로젝트는 3.11 고정
- uv: winget(`astral-sh.uv`)으로 설치, `uv venv .venv --python 3.11`로 가상환경 생성
- conda: 사용 금지

## Docker
- Docker Desktop 27.4.0 (client+server)
- docker compose v2.31.0-desktop.2
- daemon: 실행 중
- 이번 단계 build/up 미수행

## .env 점검
실값 미노출. 길이만 확인.

| 키 | claude/.env | codex/.env |
|---|---|---|
| LANGSMITH_TRACING | PRESENT | PRESENT |
| LANGSMITH_ENDPOINT | PRESENT | PRESENT |
| LANGSMITH_API_KEY | PRESENT | PRESENT |
| LANGSMITH_PROJECT | PRESENT | PRESENT |
| OPENAI_API_KEY | PRESENT | PRESENT |
| MILVUS_HOST | PRESENT | PRESENT |
| MILVUS_PORT | PRESENT | PRESENT |
| REDIS_URL | PRESENT | PRESENT |

## .codex_premerge_backup/ 처리

- 로컬 백업 잔여물. git 추적 제외 (`.gitignore`에 `.codex_premerge_backup/` 추가됨).
- **사용자 직접 정리 필요** — Claude는 삭제하지 않음 (deny 정책).
- 사용자 수동 명령(참고용):
  ```powershell
  Remove-Item -Recurse -Force C:\Users\computer\Desktop\business\.codex_premerge_backup
  ```

## pymilvus pkg_resources 경고

- 원인: pymilvus 2.4.x 또는 하위 의존성의 `pkg_resources` import. setuptools 80.x deprecation 경고.
- Milvus Docker image: `milvusdb/milvus:v2.4.10` ↔ pymilvus 2.4.4 (서버-클라이언트 동일 메이저/마이너).
- 임시 핀: `requirements/vector.txt`의 `setuptools>=80.9.0,<81` 유지.
- 런타임 영향: **없음** (connect 성공 확인됨).
- 정식 해결: pymilvus 2.6.x + Milvus image 2.6.x 동시 업그레이드 → STEP 003 이후 별도 compatibility task로 분리.
- 실측 경고 텍스트 (STEP 002.5 smoke):
  ```
  UserWarning: pkg_resources is deprecated as an API.
    See https://setuptools.pypa.io/en/latest/pkg_resources.html.
    The pkg_resources package is slated for removal as early as 2025-11-30.
    Refrain from using this package or pin to Setuptools<81.
  DeprecationWarning: The '__version_info__' attribute is deprecated (environs/marshmallow).
  ```

## LanceDB 정책

- Milvus가 **primary vector store**.
- LanceDB는 **optional / future GraphRAG experiment** 후보로 분리됨.
- 별도 핀 파일: `requirements/graph_optional.txt` (lancedb==0.19.0, pylance==0.23.0, tantivy==0.25.1).
- STEP 003 앱 scaffold 범위에서 사용하지 않음.
- `.venv`에는 lancedb 0.19.0이 이미 설치된 상태 유지 (재설치/제거 없음).

## Alembic + SQLAlchemy async (STEP 004)

- 앱(FastAPI)은 `asyncpg` driver (`DATABASE_URL = postgresql+asyncpg://...`).
- Alembic은 동기 실행 전용 → `env.py`에서 URL의 `+asyncpg`를 `+psycopg`로 in-place 치환.
- psycopg 패키지: `requirements/serve.txt`에 `psycopg[binary]==3.2.3` 핀. 모듈명은 `psycopg` (URL에서 `+psycopg`).
- alembic `script_location = backend/alembic` — `/app` CWD 기준 상대 경로.
- Migration 실행: `backend/entrypoint.sh`에서 `alembic -c backend/alembic.ini upgrade head` 후 `exec uvicorn`.
- `entrypoint.sh`는 LF 라인 엔딩 필수. Dockerfile에 `sed -i 's/\r$//'` 보호 추가.

## 미검증 / 다음 단계에서 다룰 항목
- LangSmith 실제 연결 검증 (호출 안 함)
- Celery + Redis 동작 검증
- LangGraph 그래프 실행 검증
- `model: "opusplan"`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, `Skill(update-config)` 의 실제 동작 검증

## STEP 004.5 Skeleton Audit — 추가 기록

### W4: milvus `_connected` 모듈 플래그 stale 가능성

- 위치: `backend/app/db/milvus.py:29-30`
- `_connected = False` 모듈 수준 플래그. 프로세스 내에서 한 번 연결되면 재확인 없이 `True` 유지.
- 현 skeleton 단계(stub)에서 실 영향 없음. 실 Milvus 호출 도입 시 ping 기반 연결 확인으로 전환 권장.
- **다음 STEP 처리**: STEP 006 (Milvus 실호출) 시점에 `is_connected()` 실 ping으로 교체.

### W5: themes/sectors 정적 상수 (의도된 skeleton)

- 위치: `backend/app/api/themes.py:12-18`, `sectors.py:12-18`
- `_THEMES`, `_SECTORS` 리스트는 DB/service layer 없이 in-memory 상수.
- **의도된 skeleton**: 현 단계 테마/섹터는 고정 분류 체계이므로 정적 상수가 적절.
- DB로 옮길 필요가 생기면 별도 migration + service layer 추가. 현재는 변경 대상 아님.

### W6: worker/agent-worker healthcheck 미정의

- 위치: `docker-compose.dev.yml:134-165`
- `worker`, `agent-worker` 서비스에 `healthcheck` 없음.
- 현재: `restart: on-failure`로 장애 복구. compose `ps`에서 healthcheck 상태 미표시.
- **다음 minor STEP 후보**: consumer loop 도는지 확인하는 lightweight healthcheck 추가 (예: `/tmp/worker.alive` 파일 터치 방식).

### W7: ai.txt의 llama-index-vector-stores-lancedb 분류

- 위치: `requirements/ai.txt:30`
- `llama-index-vector-stores-lancedb`가 `ai.txt`에 포함됨. LanceDB 관련 패키지는 `graph_optional.txt`가 더 일관된 위치.
- 현재 기능에 영향 없음 (ai.txt가 graph_optional.txt를 include하므로 중복 설치 없음).
- **향후**: LanceDB experiment 실제 사용 시 ai.txt에서 제거 후 graph_optional.txt로 이동 고려.

### Codex worktree 동기화 (2026-05-23, STEP 004.5)

- 동기화 전 codex HEAD: `e21ee3d` (STEP 002.5 기준 마지막 sync)
- 동기화 후: main `7704d17` (STEP 003) 포함 merge 완료
- merge 전략: `ort` (충돌 없음), 70개 파일 추가
- codex 고유 변경: `.gitignore`의 `pyproject.toml` 제외 항목 유지됨
- STEP 004 Postgres 변경 (uncommitted in main)은 이번 sync 범위 외 — 다음 commit 후 재sync 필요

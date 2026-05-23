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

## 미검증 / 다음 단계에서 다룰 항목
- LangSmith 실제 연결 검증 (호출 안 함)
- Celery + Redis 동작 검증
- LangGraph 그래프 실행 검증
- Docker Compose dev 스택 빌드/기동 (backend / worker / agent-worker 서비스)
- `model: "opusplan"`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, `Skill(update-config)` 의 실제 동작 검증

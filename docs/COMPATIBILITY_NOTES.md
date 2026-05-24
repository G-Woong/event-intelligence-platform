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

## STEP 008B Docker Migration 정책

### 문제
`COPY backend/ backend/` 레이어 캐시가 재사용되어 신규 alembic revision 파일이 컨테이너에 반영되지 않는 경우가 발생.

### 해결
`backend/Dockerfile`에 두 가지 안전망 추가:

1. **ARG CACHEBUST + 분리 COPY 레이어**  
   ```dockerfile
   ARG CACHEBUST=0
   COPY backend/alembic/versions/ backend/alembic/versions/
   ```
   `COPY backend/ backend/` 직후에 위치. `CACHEBUST` 값이 바뀌면 이 레이어부터 캐시 무효화.

2. **빌드 절차 명시**  
   신규 revision 추가 시 반드시 `--no-cache` 또는 `--build-arg CACHEBUST` 사용:
   ```
   docker compose -f docker-compose.dev.yml build --no-cache backend
   # 또는
   docker compose -f docker-compose.dev.yml build --build-arg CACHEBUST=$(date +%s) backend
   ```
   `CACHEBUST=0` (default)이면 일반 빌드에서 캐시 그대로 사용 — 추가 비용 없음.
   신규 revision 추가 시에만 위 명령 사용.

## STEP 008C Admin Auth — 추가 기록

날짜: 2026-05-24

### Dev-mode unauthenticated fallback 정책

- `ADMIN_API_TOKEN` 이 비어 있으면(기본) → startup 시 `WARNING: ADMIN_API_TOKEN unset — admin endpoints unauthenticated (dev only)` 출력 후 모든 admin/internal 호출 허용.
- `ADMIN_API_TOKEN` 설정 시 → `X-Admin-Token: <token>` 헤더 없음 또는 불일치 → **401** 즉시.
- 비교: `secrets.compare_digest` (timing-safe). 헤더 누락 시 early exit.

### 향후 RBAC TODO

- 현재는 단일 token (전체 admin 허용 또는 거부). per-endpoint scope 없음.
- STEP 010+ 에서 OAuth2 / RBAC 진입 시 이 의존성(`require_admin_token`)을 교체 포인트로 사용.
- `scripts/reconcile_stuck_once.py`도 `ADMIN_API_TOKEN` env로 헤더 삽입 — token 교체 시 env만 갱신하면 됨.

### Prod 체크리스트

1. `.env`에 `ADMIN_API_TOKEN=<strong-random-string>` 설정 (길이 ≥ 32 권장).
2. backend startup log에서 `ADMIN_API_TOKEN unset` 경고 미출력 확인.
3. `X-Admin-Token` 헤더 없이 `/api/admin/jobs` → 401 확인.
4. collector/worker/agent-worker의 `ADMIN_API_TOKEN` env도 동일 값으로 설정.

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

## STEP 005 LLM Agent 도입 — 추가 기록

### Settings LLM_* 5개 필드

`backend/app/config.py` (또는 `agents/config.py`) 에 아래 5개 필드를 추가한다.

| 필드 | 타입 | 기본값 | 비고 |
|---|---|---|---|
| `LLM_PROVIDER` | `str` | `"openai"` | `"openai"` \| `"local"` |
| `LLM_MODEL` | `str` | `"gpt-4o-mini"` | provider별 모델 식별자 |
| `LLM_TIMEOUT_SEC` | `float` | `30.0` | API 호출 timeout (초) |
| `LLM_MAX_TOKENS` | `int` | `512` | 응답 최대 토큰 수 |
| `LLM_TEMPERATURE` | `float` | `0.0` | 샘플링 온도 (0.0 = deterministic) |

모두 `.env` 에서 `os.getenv` 또는 `pydantic-settings` 로 읽는다.

### docker-compose.dev.yml — agent-worker 환경변수 추가

`agent-worker` 서비스에 아래 두 환경변수를 명시한다.

```yaml
agent-worker:
  environment:
    LLM_PROVIDER: openai     # 또는 local
    LLM_MODEL: gpt-4o-mini
```

`LLM_TIMEOUT_SEC`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE` 는 기본값 사용 시 생략 가능.
비기본값 사용 시 동일하게 environment 블록에 추가.

### 디렉터리 신설

| 경로 | 용도 |
|---|---|
| `agents/prompts/` | prompt 파일(`.md`) 저장소. `load_prompt()` 가 이 디렉터리를 탐색. |
| `agents/tools/` | tool helper 함수 + structured output schema 정의. 진입점은 `agents/tools/llm.py`. |

`agents/prompts/` 은 런타임에 파일 시스템 읽기가 발생하므로 Docker 이미지 빌드 시
COPY 대상에 포함해야 한다.

```dockerfile
COPY agents/prompts /app/agents/prompts
```

### RUN_OPENAI_SMOKE=1 opt-in 패턴

- 환경변수 `RUN_OPENAI_SMOKE=1` 을 설정해야만 실제 OpenAI API 를 호출하는 smoke 테스트가 실행된다.
- CI 환경에서는 미설정 → 자동 skip.
- 테스트 파일 내 `pytest.mark.skipif(os.getenv("RUN_OPENAI_SMOKE") != "1", ...)` 패턴 사용.

### MockLLMClient.complete_json() 분기 방식

`MockLLMClient` 는 `schema.__name__` (클래스명) 기반으로 픽스처를 반환한다.

```python
class MockLLMClient:
    def complete_json(self, prompt: str, schema: Type[BaseModel]) -> BaseModel | None:
        name = schema.__name__
        if name == "ImpactAnalysisOutput":
            return ImpactAnalysisOutput(
                severity="medium",
                affected_sectors=["energy"],
                confidence=0.8,
                rationale="mock",
            )
        if name == "FactCheckOutput":
            return FactCheckOutput(
                verdict="unconfirmed",
                confidence=0.5,
                sources=[],
            )
        if name == "SummaryOutput":
            return SummaryOutput(
                summary="mock summary",
                key_points=["point A"],
                tags=["mock"],
            )
        return None
```

새 schema 가 추가될 때마다 `MockLLMClient.complete_json()` 분기도 함께 추가한다.

## STEP 006 Milvus Vector Skeleton — 추가 기록

날짜: 2026-05-23

### W4 해소: `is_connected()` 실 ping 기반으로 교체

- `backend/app/db/milvus.py:is_connected()`가 모듈 플래그 대신 `utility.get_server_version()` 호출로 교체됨.
- `/health` 엔드포인트의 milvus 판정이 실 ping 기반. 컨테이너 다운 시 즉시 "error" 반영.

### pymilvus 2.4.4 API 호환 노트

- `hit.entity.get(key)`: 1 인자만 허용. default 인자 없음. `hit.entity.get("field") or ""` 패턴 사용.
- `CollectionSchema(fields=fields, description=...)`: `enable_dynamic_field` 미사용 (skeleton).
- `Collection.insert(data)`: column-order list of lists. auto_id 필드는 포함하지 않음.
- `Collection.search()`: `output_fields` 명시 필수. `limit`는 top_k + exclude 여유분.

### STEP 006 검증 결과

| 항목 | 결과 |
|---|---|
| `docker compose config --quiet` | PASS |
| `pytest backend/tests -q` | 26/26 PASS + 4 SKIP |
| `pytest agents/tests -q` | 15/15 PASS + 1 SKIP |
| `pytest tests/smoke/test_pipeline.py test_persistence.py -q` | 2/2 PASS |
| `pytest backend/tests/test_milvus_wrapper.py -q` (RUN_MILVUS_INTEGRATION=1) | 3/3 PASS |
| `pytest tests/smoke/test_vector_search.py -q` (RUN_MILVUS_INTEGRATION=1) | 1/1 PASS |
| `/health` milvus | "ok" (실 ping) |
| upsert_card → Milvus insert | 동작 확인 |
| retrieve_past_context → backend API → Milvus search | 동작 확인 |

## STEP 005.5 LLMClient E2E 안정화 — 추가 기록

날짜: 2026-05-23 | 검증 환경: Windows 11 / PowerShell 5.1 / Docker Desktop 27.4.0

### 검증 결과 요약

| 항목 | 결과 |
|---|---|
| `docker compose config --quiet` | PASS |
| `pytest backend/tests -q` | 11/11 PASS |
| `pytest agents/tests -q` | 10/10 PASS + 1 SKIP (openai_smoke) |
| backend/worker/agent-worker 이미지 재빌드 | PASS |
| 7개 컨테이너 Up/healthy | PASS |
| `/health` 응답 | `{"status":"ok","redis":"ok","milvus":"ok","postgres":"ok"}` |
| smoke 2파일 (pipeline + persistence) | 2/2 PASS (33.7s) |
| agent-worker 내부 `LLM_PROVIDER` | `mock` (기대값 일치) |
| mock 출력 `[mock]` 패턴 | 3개 schema 모두 확인됨 |
| OpenAI 실호출 | 미실행 (opt-in 미설정) |
| Commit A (STEP 005) | 완료 |
| Commit B (STEP 005.5) | 완료 |
| git push | 미실행 |
| codex ff-only merge | STEP 005.5 commit 후 재시도 |

### W8: pytest 실행 시 PYTHONPATH 명시 필요

- 로컬(`.venv`) 환경에서 `pytest backend/tests` 또는 `pytest agents/tests` 실행 시
  `ModuleNotFoundError: No module named 'backend'` 발생.
- 원인: `.venv`가 프로젝트 루트를 sys.path에 자동 추가하지 않음.
- 해결: `$env:PYTHONPATH = "C:\Users\computer\Desktop\business\claude"` 설정 후 실행.
- **CI 대응**: `pyproject.toml` 또는 `pytest.ini`에 `pythonpath = .` 추가를 STEP 006 시점에 검토.

### W9: `complete_json` 키워드 전용 인자 (`schema=`)

- `BaseLLMClient.complete_json(prompt, *, schema=...)` — `schema`는 keyword-only.
- 위치 인자로 호출(`complete_json(prompt, SomeSchema)`) 시 TypeError.
- 컨테이너 내부 임시 테스트 코드에서 오류 발생 (실 파이프라인은 keyword 형태로 올바르게 호출).
- 실 파이프라인 영향: 없음. 노드 코드가 모두 `schema=OutputClass` 형태 사용.

### W10: agent-worker `source_parse` 노드 dict 입력 거부

- `event_processing_graph.run(dict)` 직접 호출 시 `AttributeError: 'dict' object has no attribute 'raw_text'`.
- 원인: `source_parse` 노드가 `RawEvent` Pydantic 객체를 기대하나 plain dict 전달.
- 실 파이프라인 영향: 없음. `publish_pipeline.py`가 `RawEvent` 객체를 생성 후 전달.
- smoke 테스트 2/2 PASS로 실 경로 정상 동작 확인.

### OpenAI opt-in 절차 (미실행, 참고용)

```powershell
$env:RUN_OPENAI_SMOKE = "1"
pytest agents/tests/test_openai_smoke.py -q
```

키 값 출력 금지. 실행 시 응답 길이/모델명만 보고.

## STEP 007 RSS Collector — 추가 기록

날짜: 2026-05-23

### feedparser 6.0.11 동작 노트

- `feedparser.parse(url, agent=UA, request_headers={...})` — `agent` 파라미터가 HTTP User-Agent 헤더를 설정.
- `entry.published_parsed` → `time.struct_time (9-tuple)` → `datetime(*parsed[:6], tzinfo=timezone.utc)` 로 UTC 변환 필수.
- `entry.id` 또는 `entry.guidislink` 가 없는 경우 `entry.link`를 external_id fallback으로 사용.
- `<guid isPermaLink="true">` (기본) 인 경우 feedparser가 `entry.link`에 guid 값을 복사함. `isPermaLink="false"` 인 경우 `entry.link`는 null.
- `bozo=1` 인 경우 feed parse는 진행되며 `bozo_exception`으로 오류 내용 확인 가능.
- feedparser는 기본적으로 socket timeout을 설정하지 않음. `socket.setdefaulttimeout(N)` 으로 설정 필요 (thread-safe 주의: 이전 값 저장 후 복원).
- 한국어(YNA) 피드: UTF-8 명시하면 정상 파싱. 인코딩 mismatch는 `bozo=1` 발생하나 콘텐츠는 살림.

### raw_event_service asyncio 주의

- `enqueue_raw_event()` 는 동기 Redis 클라이언트 사용.
- FastAPI async 핸들러에서 직접 호출 시 이벤트 루프를 블록 → uvicorn 전체 hang.
- 해결: `await asyncio.to_thread(enqueue_raw_event, raw_event)`.

### `/collect-rss-once` self-call 패턴

- backend가 자신의 `/api/admin/raw-events`를 호출하는 self-call 구조.
- `asyncio.to_thread(rss_collector.run)` 로 블로킹 피드 fetch + 동기 httpx 호출을 스레드에 격리.
- backend 내부에서 `BACKEND_INTERNAL_URL = http://backend:8000` → Docker 내에서 자기 자신 호출.
- 이 패턴은 uvicorn이 추가 커넥션을 수락할 수 있는 한 (asyncio.to_thread 사용 시) 정상 동작.

### STEP 007 검증 결과

| 항목 | 결과 |
|---|---|
| `pytest workers/tests/test_rss_collector.py -v` | 16/16 PASS |
| `pytest backend/tests/test_raw_events_api.py -v` | 5/5 PASS |
| `pytest tests/smoke/test_rss_collector_fixture.py -v` | 3/3 PASS |
| alembic upgrade head (0001→0002) | PASS |
| alembic downgrade -1 + upgrade head roundtrip | PASS |
| raw_events 테이블 + 2 UNIQUE + 5 index | 확인 |
| event_cards 기존 13개 데이터 보존 | PASS |
| `POST /api/admin/raw-events` 중복 is_duplicate=true | PASS |
| `POST /api/admin/collect-rss-once` summary 반환 | PASS (sources=3, items_seen=152) |
| `RawEvent` schema 무변경 | git diff 0 hunks |
| 컨테이너 8개 Up/healthy | PASS |

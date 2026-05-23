# STEP 002.6 — Codex 실행환경 복구 보고서

작성일: 2026-05-23

---

## 1. codex worktree 인식

| 항목 | 결과 |
|---|---|
| `git worktree list` | ✅ claude=main(`c93695f`), codex=codex(`e21ee3d`) |
| codex 브랜치 | `codex` |
| codex HEAD commit | `e21ee3d chore: sync codex with main (step 002.5)` |

---

## 2. main → codex merge 결과

- merge commit: `e21ee3d`
- 충돌 발생 파일: `.gitignore`
- 충돌 해결 내역:
  - `.gitignore`: main 형식 채택 + codex의 `pyproject.toml` 라인 유지
  - `requirements/vector.txt`: main 버전 자동 채택 (LanceDB/pylance 제거됨)
- 신규 추가된 파일 (main 동기):
  - `docs/AGENT_WORKFLOW.md`
  - `docs/COMPATIBILITY_NOTES.md` (수정)
  - `plans/003_APP_SCAFFOLD_PLAN.md`
  - `plans/repo-sunny-barto.md` (수정)
  - `requirements/graph_optional.txt`

---

## 3. codex .venv 생성

| 항목 | 결과 |
|---|---|
| uv 경로 | `%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe` |
| 명령 | `uv venv codex\.venv --python 3.11` |
| 검증 출력 | `Python 3.11.9` ✅ |

---

## 4. requirements 설치 (5+1 레이어)

| 레이어 | 파일 | 결과 |
|---|---|---|
| base (serve 포함) | `serve.txt` | ✅ exit 0 |
| worker | `worker.txt` | ✅ exit 0 |
| ai | `ai.txt` | ✅ exit 0 |
| vector | `vector.txt` | ✅ exit 0 (pymilvus==2.4.4) |
| dev | `dev.txt` | ✅ exit 0 |

설치 제외 (계획대로): `ml.txt`, `crawler.txt`, `graph_optional.txt`

---

## 5. codex .env 키 점검

| 키 | 상태 |
|---|---|
| LANGSMITH_TRACING | PRESENT (len=4) |
| LANGSMITH_ENDPOINT | PRESENT (len=31) |
| LANGSMITH_API_KEY | PRESENT (len=51) |
| LANGSMITH_PROJECT | PRESENT (len=6) |
| OPENAI_API_KEY | PRESENT (len=164) |
| MILVUS_HOST | PRESENT (len=9) |
| MILVUS_PORT | PRESENT (len=5) |
| REDIS_URL | PRESENT (len=24) |

---

## 6. AGENTS.md / .codex/config.toml

| 파일 | 디스크 존재 | git 추적 제외 확인 |
|---|---|---|
| `codex/AGENTS.md` | ✅ | ✅ (`git ls-files` 결과 없음) |
| `codex/.codex/config.toml` | ✅ | ✅ (`git ls-files` 결과 없음) |

---

## 7. Docker shared infra 연결 검증

### Docker 서비스 상태
| 서비스 | 이미지 | 상태 |
|---|---|---|
| ei-redis | redis:7.4-alpine | healthy ✅ |
| ei-milvus | milvusdb/milvus:v2.4.10 | healthy ✅ |
| ei-milvus-etcd | quay.io/coreos/etcd:v3.5.5 | healthy ✅ |
| ei-milvus-minio | minio/minio:RELEASE.2023-03-20T20-16-18Z | healthy ✅ |

### 연결 테스트
| 항목 | 결과 |
|---|---|
| Redis ping | `True` ✅ |
| Milvus connect | `milvus connect ok` ✅ |

---

## 8. 핵심 패키지 import smoke

```
import fastapi, redis, pymilvus, langgraph, langchain, openai, pydantic, pytest
→ imports ok ✅
```

WARNING: `pymilvus`가 `pkg_resources` deprecated 경고 출력. 동작에는 영향 없음.
원인: pymilvus==2.4.4가 setuptools<81 핀에도 불구하고 pkg_resources API를 사용.

---

## 9. 검증 체크리스트

- [x] `git worktree list` claude=main, codex=codex 정상
- [x] `git -C codex status` clean (merge 후)
- [x] `git -C codex log --oneline -3`에 main 동기 commit 표시
- [x] `codex/.venv/Scripts/python.exe --version` → Python 3.11.9
- [x] codex `.venv`에서 fastapi/redis/pymilvus/langgraph/langchain/openai/pydantic/pytest import 성공
- [x] codex `.venv`에서 Redis ping = True
- [x] codex `.venv`에서 Milvus connect 성공
- [x] codex `.env` 8개 키 PRESENT (masked)
- [x] codex `AGENTS.md` 디스크 존재 + git 추적 제외
- [x] codex `.codex/config.toml` 디스크 존재 + git 추적 제외
- [x] `docs/AGENT_WORKFLOW.md`에 venv/shared infra 문구 추가됨
- [x] `plans/002_6_CODEX_ENV_RECOVERY_REPORT.md` 신규 존재
- [x] Docker 4개 서비스 healthy 유지

---

## 10. WARNING

| 항목 | 내용 |
|---|---|
| pymilvus pkg_resources 경고 | pymilvus==2.4.4가 deprecated `pkg_resources` 사용. 동작 무관. setuptools<81 핀으로 제어 중. |

## BLOCKED / UNKNOWN

없음.

---

## STEP 003 진입 가능 여부

✅ **진입 가능**. 모든 검증 항목 PASS. 사용자 승인 후 STEP 003 시작.

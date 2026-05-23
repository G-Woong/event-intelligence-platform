# 001 — 다음 단계 PLAN (의존성 분리 · 컨테이너 정의 · GitHub 연동)

## 목적
환경 세팅(000) 이후, 본 단계는 **앱 코드 작성 직전 단계의 토대**를 정리한다:
1. `requirements.txt` 인코딩 정상화 및 용도별 분리
2. `.env.example` 추가 (실값 없이)
3. `docker-compose.dev.yml` 정의 (build/up은 다음 단계)
4. `pyproject.toml` 기본 메타 + ruff/pytest/mypy 설정
5. GitHub 원격 `G-Woong/event-intelligence-platform` 연동

## 완료 항목

### 1. requirements 분리
원본 `requirements.txt`를 UTF-8로 재인코딩(7448B → 3847B, BOM 제거)하고, 다음 8개 파일로 분리:
- `requirements/base.txt`
- `requirements/serve.txt`
- `requirements/worker.txt`
- `requirements/ai.txt`
- `requirements/ml.txt`
- `requirements/crawler.txt`
- `requirements/vector.txt`
- `requirements/dev.txt`
- `requirements/README.md`

원본 `requirements.txt`는 잠금 스냅샷 reference로 보존.

### 2. .env.example
`.env.example` 신규. 8개 키(`LANGSMITH_TRACING`, `LANGSMITH_ENDPOINT`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `OPENAI_API_KEY`, `MILVUS_HOST`, `MILVUS_PORT`, `REDIS_URL`)만 노출, 실값 없음.

### 3. docker-compose.dev.yml
신규. 정의 서비스:
- `milvus-etcd` (etcd v3.5.5)
- `milvus-minio` (MINIO 2023-03-20)
- `milvus-standalone` (Milvus v2.4.10)
- `redis` (Redis 7.4-alpine)

`app` / `worker` 서비스는 scaffold 후 추가. **build/up은 본 단계에서 수행 안 함.**

### 4. pyproject.toml
신규. `[project]`, `[tool.uv]`, `[tool.ruff]`, `[tool.pytest.ini_options]`, `[tool.mypy]` 설정.

### 5. GitHub 원격
- `git remote add origin https://github.com/G-Woong/event-intelligence-platform.git`
- 원격 상태: PUBLIC, isEmpty=true (충돌 위험 없음)
- 초기 commit 생성 후 push 시도 — push는 settings.json deny에 의해 권한 prompt 발생할 수 있음

## 검증 항목
- 분리 파일 8개 존재 및 줄 수 확인
- `.env.example`는 키 이름만, 값 없음 확인
- `docker-compose.dev.yml` 파일 파싱 (`docker compose -f docker-compose.dev.yml config --quiet`)
- `pyproject.toml` 파싱 확인
- `git remote -v`로 origin 등록 확인
- `git log --oneline`로 초기 commit 확인

## 다음 단계 예고 (002)
1. `codex/` 측 git 정책 결정 (init 여부, 메인과의 worktree 관계)
2. app scaffold (FastAPI + LangGraph + Celery + Milvus + Redis 디렉토리 구조 — `app/`, `app/api/`, `app/graphs/`, `app/workers/`, `app/sources/`, `app/storage/`)
3. `Dockerfile` (app, worker 이미지)
4. `docker-compose.dev.yml`에 app/worker 서비스 추가
5. `docker compose up`으로 Milvus + Redis 통합 검증
6. 의존성 설치 (`uv pip install -r requirements/serve.txt -r requirements/ai.txt -r requirements/vector.txt`)
7. 기본 헬스 엔드포인트 + LangGraph 최소 그래프 1개로 end-to-end smoke test

## 금지 사항 (재확인)
- ❌ `docker compose build` / `docker compose up`
- ❌ 의존성 설치 (`uv pip install` / `pip install`)
- ❌ 앱 코드 scaffold (`app/`, 엔드포인트, 그래프)
- ❌ `git push --force`
- ❌ destructive 명령
- ❌ `.env` 실값 노출

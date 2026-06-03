# Migration Readiness — Windows → MacBook

> 작성일: 2026-06-03  
> 상태: **런타임 안전 / git 위생 정리 완료 (커밋 대기)**

---

## 종합 판정

| 영역 | 상태 | 비고 |
|------|------|------|
| 소스코드 내 절대경로 | ✅ 안전 | `C:\Users\...` 0건, 전부 `Path(__file__)` 상대해석 |
| Docker 볼륨 | ✅ 안전 | named volume only, 호스트 바인드 마운트 0건 |
| OS 분기 코드 | ✅ 안전 | `sys.platform != "win32"` 가드로 Windows 전용 코드 격리 |
| `.sh` 줄바꿈 | ✅ 안전 | 인덱스 내 LF 저장 확인 |
| `__pycache__` / `.pyc` 추적 | 🔧 정리 완료 | 51개 → 인덱스 제거 (`--cached`) |
| `ingestion/outputs/` 아티팩트 | 🔧 정리 완료 | 73개 산출물 → 인덱스 제거, `.gitkeep` 보존 |
| `ingestion/logs/` jsonl | 🔧 정리 완료 | 33개 로그 → 인덱스 제거, `.gitkeep` 보존 |
| `.gitattributes` | 🔧 추가 완료 | CRLF 정규화 규칙 적용 |

---

## 안전 항목 (수정 불필요)

### 소스코드 절대경로 — 0건
- 전체 `.py` 파일에서 `C:\\Users`, `C:/Users`, `/home/` 패턴 검색 결과 0건.
- 경로 처리는 `Path(__file__).parent` 또는 환경변수 기반.

### Windows 전용 코드 격리
- `ingestion/strategies/selenium_strategy.py`에 `chrome.exe` / `Program Files` 참조 존재하나, 진입 전 `if sys.platform != "win32": return False` 가드로 맥에서 절대 도달 불가.
- Selenium 전략은 NOT_READY scaffold라 실제 런타임에 호출되지 않음.

### Docker 이식성
- `docker-compose.dev.yml` 볼륨: 전부 named volume (`milvus_data`, `redis_data` 등).
- 모든 이미지: 멀티아치 지원 (`milvusdb/milvus`, `redis:7-alpine` 등).
- Apple Silicon(arm64)에서 추가 설정 없이 `docker compose up` 가능.

### `.env` 보안
- `.env` 자체는 `.gitignore`에 의해 추적 안 됨 (정상).
- `.env.example`에 실제 키 값 없음 (플레이스홀더만 존재).

---

## CRITICAL 발견 및 조치

### 왜 `.gitignore`가 있어도 무시가 안 됐는가?

`.gitignore`는 **한 번도 추적된 적 없는 파일**만 무시한다.  
`git add`로 한 번이라도 인덱스(staging area)에 올라간 파일은 이미 "추적 중(tracked)" 상태이므로  
`.gitignore` 규칙이 있어도 git은 계속 해당 파일의 변경을 감시한다.

해결책: `git rm --cached <path>` — 디스크 파일은 삭제하지 않고 **인덱스에서만 제거**한다.  
제거 후에는 `.gitignore` 규칙이 정상 작동하여 이후 커밋에서 자동 무시된다.

### 1. `__pycache__` / `.pyc` — 51개 추적 중

| 항목 | 내용 |
|------|------|
| 심각도 | CRITICAL |
| 대상 | `ingestion/**/__pycache__/*.pyc` 51개 |
| 맥 영향 | Windows CPython 3.11 바이트코드 → 맥에서 stale import 오류 유발 가능 |
| 조치 | `git rm -r --cached` 로 인덱스 제거. `.gitignore`의 `__pycache__/` 규칙이 이후 자동 무시 |

### 2. `ingestion/outputs/` 아티팩트 — 73개 추적 중

| 항목 | 내용 |
|------|------|
| 심각도 | CRITICAL |
| 대상 | `raw_html` 28개 / `extracted_text` 11개 / `jsonl` 11개 / `reports` 23개 |
| 맥 영향 | 저장소 비대화(~12MB) + 외부 콘텐츠 저작권 리스크 |
| 조치 | `git rm -r --cached` 로 인덱스 제거. `.gitkeep` 유지. `.gitignore`의 `ingestion/outputs/` 규칙이 이후 자동 무시 |

### 3. `ingestion/logs/` jsonl — 33개 추적 중

| 항목 | 내용 |
|------|------|
| 심각도 | CRITICAL |
| 대상 | `attempts/`, `errors/`, `runs/` 하위 `.jsonl` 33개 |
| 맥 영향 | 머신별 로그 충돌 + diff 노이즈 |
| 조치 | `git rm -r --cached` 로 인덱스 제거. `.gitkeep` 유지. `.gitignore` 규칙이 이후 자동 무시 |

---

## WARNING

### `.gitattributes` 부재 → CRLF 혼입 위험

- 조치 전 인덱스 내 CRLF 파일 약 95개.
- 맥에서 파일 편집 시 줄바꿈 diff 노이즈 발생, `.sh` CRLF 혼입 시 `bad interpreter` 실행 오류.
- **조치**: `.gitattributes` 추가 (`* text=auto eol=lf`, `.sh eol=lf`, `.ps1 eol=crlf`).

---

## 적용한 정리 조치 요약

```
git rm -r --cached ingestion/**/__pycache__  # .pyc 51개 인덱스 제거
git rm -r --cached ingestion/outputs/        # 아티팩트 73개 인덱스 제거 (gitkeep 보존)
git rm -r --cached ingestion/logs/           # 로그 33개 인덱스 제거 (gitkeep 보존)
git add .gitattributes                       # CRLF 정규화 규칙 추가
git add --renormalize .                      # 기존 파일 줄바꿈 재정규화
```

디스크상 파일은 **모두 보존** (`--cached` 옵션).

---

## 맥북 Clone 후 셋업 체크리스트

```bash
# 1. 저장소 클론
git clone <repo-url>
cd claude

# 2. Python 환경
brew install python@3.11      # 없으면 설치
python3.11 -m venv .venv
source .venv/bin/activate
pip install uv
uv pip install -r requirements/base.txt
uv pip install -r requirements/serve.txt   # API 서버
uv pip install -r requirements/worker.txt  # Celery worker
# ml.txt (torch, llama-cpp-python)는 필요할 때만 — Apple Silicon 빌드 마찰 가능

# 3. 환경변수
cp .env.example .env
# .env 편집: OPENAI_API_KEY, LANGSMITH_API_KEY 등 실값 입력
# GOOGLE_APPLICATION_CREDENTIALS: Docker 실행 시 무해, bare 실행 시 맥 경로로 수정

# 4. Playwright
python -m playwright install chromium

# 5. Docker (선택 — Milvus/Redis 필요 시)
docker compose -f docker-compose.dev.yml up -d

# 6. 동작 확인
python -c "import ingestion; print('OK')"
```

> `requirements/ml.txt`는 `torch`와 `llama-cpp-python`을 포함합니다.  
> Apple Silicon 빌드 마찰이 있을 수 있으므로 API/worker 구동에는 `serve/ai/vector/worker/crawler` 조합으로 충분합니다.

---

## 커밋되지 않는 것 (맥북에서 재생성)

| 항목 | 이유 |
|------|------|
| `.venv/` | 머신별 바이너리, clone 후 재생성 |
| `.env` | 보안 키, clone 후 `.env.example` 복사하여 실값 입력 |
| `ingestion/outputs/**` | 런타임 산출물, 실행 후 재생성 |
| `ingestion/logs/**` | 런타임 로그, 실행 후 재생성 |
| `__pycache__/` | 바이트코드, import 시 자동 재생성 |

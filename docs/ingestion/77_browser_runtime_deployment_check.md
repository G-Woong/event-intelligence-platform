# 77. Browser Runtime / Deployment Check 보고서 (RISK 12-4)

날짜: 2026-06-12

## 1. 무엇을 닫았는가

브라우저 전략(playwright 4변형 + selenium fallback)이 배포 환경에서 실제로 동작하는지
검증할 자동화 수단이 없었다. 신규 러너가 이를 닫는다.

## 2. 러너

```powershell
python -m ingestion.runners.run_browser_runtime_check [--launch] [--json] [--strict]
```

점검 항목:
- Python 버전 (3.11+)
- playwright import + 버전
- chromium 설치 여부 — 기본은 **비기동** 경로 확인 (`executable_path` 존재 검사만)
- `--launch` 시에만 headless chromium 실제 기동 + screenshot 저장
  (`ingestion/outputs/screenshots/_runtime_check/`)
- selenium import + chrome binary (기존 `selenium_env_status()` 재사용)
- screenshot 가능 여부

종합 판정: playwright와 selenium 둘 다 ready → `READY`, 한쪽만 → `PARTIAL`,
둘 다 불가 → `NOT_READY`. **NOT_READY여도 exit 0** (수집 자체를 막지 않음) —
`--strict`일 때만 exit≠0 (CI 게이트용). 리포트에 env 값/secret 미포함 (테스트 가드).

## 3. 현재 환경 실측 (2026-06-12, Windows 11 로컬)

```
overall=READY
python 3.11.9 ok=True
playwright installed=True version=1.48.0 chromium_installed=True
selenium installed=True ready=True
```

## 4. Docker 배포 전제 (실제 빌드는 이번 라운드 범위 아님)

Celery worker(plans/012)를 컨테이너로 올릴 때 브라우저 런타임 전제:

### 옵션 A — 공식 Playwright 이미지 (권장)

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy
# 브라우저+OS deps 사전 포함. 이미지 태그는 requirements의 playwright 버전과 일치시킬 것.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

### 옵션 B — 일반 python 이미지 + 설치

```dockerfile
FROM python:3.11-slim
RUN pip install playwright==1.48.0 && playwright install --with-deps chromium
```

### 공통 주의사항

- **한글 폰트**: 한국 사이트 screenshot 깨짐 방지 — `apt-get install -y fonts-nanum`
  (또는 `fonts-noto-cjk`). 미설치 시 렌더링은 되나 스크린샷 글자가 □로 나옴.
- **headless 플래그**: 컨테이너에는 X 서버가 없으므로 headless 필수 (현 코드 기본값).
  공유 메모리 부족 시 `--disable-dev-shm-usage` 또는 compose에 `shm_size: 1gb`.
- **selenium fallback**: 컨테이너에 chrome binary가 없으면 `selenium_env_status()["ready"]
  =False` → 전략 선택에서 자동 제외 (이미 gate 존재, docs/78). playwright만으로 PARTIAL
  운용 가능.
- 배포 후 `python -m ingestion.runners.run_browser_runtime_check --launch --strict`를
  컨테이너 entrypoint 사전 점검 또는 CI 단계로 실행 권장.

## 5. 검증

`ingestion/tests/unit/test_browser_runtime_check.py` — **5 passed**:
리포트 구조, playwright 미설치 mock→NOT_READY, selenium만 ready→PARTIAL,
리포트에 env 값 없음, NOT_READY 안전 반환/--strict exit 1.

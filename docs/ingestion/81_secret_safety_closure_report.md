# 81. Secret Safety Closure 보고서 (RISK 12-8)

날짜: 2026-06-12

## 1. 무엇을 닫았는가

기존에는 `_sanitize_response`(api_probe)가 응답 본문에서 사용된 키 값을 마스킹하는
**단일 방어선**뿐이었다. artifact/문서/계획 파일에 secret이 섞였는지 사후 점검할 자동화
수단이 없었다 (RISK-S01).

신규 도구 `ingestion/tools/scan_secrets.py`가 이를 닫는다.

## 2. 도구 설계

```powershell
python -m ingestion.tools.scan_secrets --paths ingestion\outputs docs\ingestion plans [--json] [--env-path PATH]
```

### 2계층 탐지

| 계층 | 탐지 방식 | 심각도 | 비고 |
|------|-----------|--------|------|
| ① 패턴 | sk-/AKIA/ghp_/AIza/xox*/Bearer/serviceKey=/api_key 대입/PRIVATE KEY 블록 (20+자) | WARNING | placeholder 허용목록(YOUR_, `<...>`, REDACTED, example, xxxx, ...) hit는 제외 |
| ② .env 실값 정확 일치 | `.env`를 메모리에만 로드 후 라인 단위 substring 비교 | BLOCKED | **credential 성격 키 이름**(KEY/SECRET/TOKEN/PASSWORD/CREDENTIAL)이고 값 len≥8인 항목만 비교 |

설계 결정 — 계층 ②를 credential 키 이름으로 제한한 이유: `MILVUS_HOST=localhost` 같은
인프라 설정값이 모든 HTML artifact("localhost" 포함)에 매칭되어 BLOCKED 오탐 수백 건을
발생시켰다 (초기 스캔에서 실측). HOST/PORT/URL/플래그 값은 secret이 아니다.

### 안전 원칙

- 리포트에는 **키 NAME·파일·라인번호만** 포함. 값은 어떤 경로로도 출력되지 않는다.
- `.env` 파일 자체는 스캔 대상에서 제외 (secret의 원천이지 유출 대상이 아님).
- 바이너리(png/jpg/pdf/zip/pyc)·5MB 초과 파일 제외.
- 테스트의 값 비교는 boolean (`(value in out) is False`) — pytest assertion diff에 값이
  섞이지 않는다.

### Exit code

| code | 의미 |
|------|------|
| 0 | PASS |
| 1 | WARNING (패턴 hit — 검토 필요) |
| 2 | BLOCKED (.env 실값 유출 — 즉시 조치) |

## 3. 검증 결과

- `ingestion/tests/unit/test_scan_secrets.py` — **11 passed**
  - fake secret fixture → BLOCKED + env_key NAME만 노출
  - placeholder → PASS
  - 리포트 직렬화에 실값 미포함 (boolean 비교)
  - exit code 3종
  - `_sanitize_response` 회귀 3종 (마스킹, 짧은 값 무시, 다중 secret)
- baseline 스캔: `ingestion/outputs` + `docs/ingestion` + `plans` 683개 파일 → **verdict=PASS, exit=0**

## 4. pre-commit / CI 적용 방법

### pre-commit (로컬)

`.git/hooks/pre-commit` 또는 `pre-commit` 프레임워크 사용 시 `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: scan-secrets
        name: scan secrets in artifacts/docs
        entry: python -m ingestion.tools.scan_secrets --paths ingestion/outputs docs/ingestion plans
        language: system
        pass_filenames: false
```

### CI (GitHub Actions 예시)

```yaml
- name: Secret scan
  run: python -m ingestion.tools.scan_secrets --paths ingestion/outputs docs/ingestion plans
  # exit 1(WARNING)도 실패 처리하려면 그대로 두고,
  # WARNING 허용하려면 `|| [ $? -lt 2 ]` 게이트 사용
```

이번 라운드에서는 도구·테스트·baseline 검증까지 수행했고, hook/CI 실제 등록은 사용자
결정 사항으로 남긴다 (git hook 설치는 로컬 환경 변경이므로).

## 5. 한계 / 이월

- 계층 ②는 credential 키 이름 휴리스틱 기반 — secret을 비표준 이름(예: `MY_VALUE=`)으로
  저장하면 계층 ①(패턴)만 방어. `.env` 키 명명 규칙 준수가 전제.
- base64 재인코딩된 유출은 미탐 — 향후 entropy 기반 탐지로 보강 가능 (이월).

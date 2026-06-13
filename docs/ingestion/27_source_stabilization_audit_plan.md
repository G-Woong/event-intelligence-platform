# 27 — Source Stabilization Audit Plan

**라운드 목적**: 56개 수집 소스의 실제 동작 여부를 재검증하고, Adaptive Fetch Framework를 상용 수준 재시도 구조로 강화한다.

---

## 1. 배경

직전 라운드(docs 19–26)는 "38개 LIVE_SUCCESS"를 서술했으나, probe 리포트는 마지막 단일 실행만 덮어쓰기로 보관하여 재현 근거가 없었다. 이번 라운드는 모든 소스를 artifact 우선으로 재검증하고 실패/부분/보류/차단 원인을 분해한다.

---

## 2. 감사 범위

| 구분 | 소스 수 |
|---|---|
| Phase 1 (뉴스) | 10 |
| Phase 2 (커뮤니티/소셜) | 11 |
| Phase 3 (공식/데이터) | 10 |
| Phase 4 (확장 후보) | 25 |
| **합계 (실질)** | **56** |

`_dummy`는 테스트 픽스처로 카운트 제외.

---

## 3. 성공 기준

| 등급 | 정의 |
|---|---|
| LIVE_SUCCESS | 200 응답 + 유효 데이터 (JSON items / RSS entries / HTML contents) |
| LIVE_SUCCESS_UNVERIFIED | 연결 성공이나 샘플 품질 미검증 |
| LIVE_PARTIAL | 연결은 되나 데이터 불완전 (빈 items / 단일 항목 / 파라미터 오류) |
| FAILED_RETRYABLE | 일시적 실패 (429 rate limit, 5xx 서버오류) |
| FAILED | 영속적 실패 (잘못된 endpoint, 잘못된 URL 형식) |
| MISSING_KEY | 키 미설정 or 키 이름 불일치 |
| BLOCKED | 봇 차단 / 로그인 필요 / 페이월 |
| DEFERRED | JS 렌더링 복잡 or 서버 오류로 이번 라운드 미시도 |
| UNKNOWN | probe 실행 기록 없음 |

---

## 4. 검증 방법

1. **Artifact 우선**: `ingestion/outputs/raw_payload/<id>/`, `raw_signal/<id>/` 존재 시 해당 파일 품질로 판정.
2. **재호출**: artifact 없거나 LIVE_PARTIAL/FAILED인 소스는 `run_api_live_probe --service <id> --max-calls 1` 최대 1회.
3. **Playwright**: playwright_probe_sites.yaml 등록 소스는 runner 실행으로 판정.

---

## 5. 이연 항목 (이번 라운드 불시도)

- Selenium 실제 live (chromedriver 부재, NOT_READY)
- reddit OAuth, x/blind/reuters (BLOCKED 유지)
- IGDB Twitch OAuth 흐름 구현
- kma/its/tour 공공데이터포털 키 형식 해결
- Celery+Redis 비동기 수집 연결

---

## 6. 보안 하드 제약

- 모든 문서에서 API 키·Authorization 값 미출력 (끝 4자리도 금지)
- login/CAPTCHA/paywall 우회 코드 금지
- destructive 명령 미사용
- 실 키 발견 시 즉시 SECURITY_BLOCKED 처리

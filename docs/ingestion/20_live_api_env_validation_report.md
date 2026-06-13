# 20. Live API 환경 검증 보고서

작성일: 2026-06-03

## 키 인식 결과 (값 미출력)

| 서비스 | 정식 키명 | 인식 상태 |
|---|---|---|
| kofic | KOFIC_API_KEY | PRESENT (LIVE_SUCCESS) |
| culture_info | CULTURE_INFO_KEY | PRESENT (LIVE_SUCCESS 후) |
| sec_edgar | SEC_USER_AGENT (선택적) | 미설정→honest UA fallback |
| naver_news_search | NAVER_CLIENT_ID/SECRET | PRESENT |
| bok_ecos | BOK_ECOS_API_KEY (alias: ECOS_API_KEY) | PRESENT |

## Live probe 결과 요약 (56개 소스)

| 결과 | 수 | 비고 |
|---|---|---|
| LIVE_SUCCESS | 38 | 정상 수집 가능 |
| MISSING_KEY | 1 | google_programmable_search (키 미기입) |
| BLOCKED | 3 | x, blind, reuters (컴플라이언스 유지) |
| DEFERRED | 5 | google_trending_now, signal_bz(→수렴), loword 등 |
| Other | 9 | rate_limited(gdelt), invalid_key(kma/its/igdb), network_error(tour) 등 |

## 재분류 결과

이전 MISSING_KEY 16개 중:
- LIVE_SUCCESS로 재분류: kofic, culture_info, twelve_data 등
- INVALID_KEY: kma, its, igdb (키 값 오류 또는 플랜 제한)
- NETWORK_ERROR: tour (서버 오류)
- 실제 MISSING_KEY: google_programmable_search (1개)

## 보안 확인

- outputs 디렉토리 내 Authorization 헤더 노출: NONE
- 응답 본문 sanitize: 모든 API 키 값 ***REDACTED*** 치환 확인

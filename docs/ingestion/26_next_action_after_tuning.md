# 26. 튜닝 이후 다음 액션

작성일: 2026-06-03

## 한 줄 결론

56개 소스 중 **38개 LIVE_SUCCESS**, 핵심 인프라(rate_limit, selenium fallback, adaptive fetch) 구현 완료. 다음 라운드 준비됨.

## P0 (즉시 처리)

| 항목 | 상태 | 내용 |
|---|---|---|
| GDELT 429 재시도 | PASS | rate_limit_policy 구현, cooldown 300s |
| Selenium NOT_READY | PASS | graceful fallback, graph.py dispatch 등록 |
| kofic/culture_info 키 정합 | PASS | KOFIC_API_KEY, CULTURE_INFO_KEY 확정 |

## P1 (이번 스프린트)

| 항목 | 상태 | 내용 |
|---|---|---|
| Celery+Redis 비동기 수집 연결 | DEFERRED | 별도 라운드 |
| kma/its INVALID_KEY 원인 조사 | TODO | 공공데이터포털 키 형식 확인 필요 |
| igdb Twitch OAuth | TODO | client_credentials flow 구현 필요 |
| google_programmable_search 키 | TODO | GOOGLE_CUSTOM_SEARCH_API_KEY + CX 기입 필요 |

## P2 (다음 라운드)

| 항목 | 상태 | 내용 |
|---|---|---|
| fmkorea | BLOCKED | Cloudflare Turnstile — 우회 불가 |
| krx_kind | DEFERRED | 서버 오류, 재시도 예정 |
| google_trends_explore | DEFERRED | Google 429 rate limit |
| reddit OAuth | BLOCKED | OAuth 플로우 미구현 |
| x/blind/reuters | BLOCKED | 컴플라이언스 유지 |

## BLOCKED/DEFERRED/UNKNOWN 요약

- **BLOCKED**: fmkorea(봇), x(login), blind(login), reuters(login)
- **DEFERRED**: krx_kind(서버오류), google_trends_explore(429), loword, Celery연결, Selenium live(chromedriver 부재)
- **UNKNOWN**: tour API 서버 오류 간헐적

# 19. Tuning Plan — LIVE_PARTIAL 고도화 및 Adaptive Fetch 업그레이드

작성일: 2026-06-03

## 목적

56개 소스 1차 검증 이후 남은 문제를 해결하기 위한 라운드 계획.

## 작업 범위

| 항목 | 내용 |
|---|---|
| 키 이름 정합 | kofic: KOBIS_API_KEY→KOFIC_API_KEY, culture_info: CULTURE_INFO_API_KEY→CULTURE_INFO_KEY |
| GDELT rate limit | ErrorType.RATE_LIMITED 추가, cooldown 정책 구현 |
| Selenium fallback | NOT_READY graceful 등록 (chromedriver 부재 시 크래시 없음) |
| Adaptive Fetch | EXTRACTION_EMPTY→playwright jump, RATE_LIMITED→no advance 규칙 |
| Playwright 튜닝 | signal_bz/eu_press_corner 수렴, fmkorea BLOCKED, krx_kind 서버 오류 DEFERRED |

## 완료 여부

모든 항목 이번 라운드에서 구현 완료.

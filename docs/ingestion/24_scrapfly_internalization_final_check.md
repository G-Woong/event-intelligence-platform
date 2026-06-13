# 24. Scrapfly 내부화 최종 판정

작성일: 2026-06-03

## 판정: DEFERRED (불필요)

현재 구현된 내부 스택으로 56개 소스 중 38개 LIVE_SUCCESS 달성.

- Playwright 기반 렌더링: signal_bz/dcinside/eu_press_corner 등 커버
- EXTRACTION_EMPTY→playwright 자동 escalation 구현
- Selenium fallback 조건부 등록 완료

외부 스크래핑 클라우드(Scrapfly) 도입 필요 시점:
- 현재 내부 Playwright가 재현 불가능한 봇 우회가 필요한 경우
- fmkorea처럼 Cloudflare Turnstile 봇 챌린지를 상용 서비스로 해결해야 할 때
- 현재 단계에서는 해당 없음 — 컴플라이언스 상 봇 우회 금지

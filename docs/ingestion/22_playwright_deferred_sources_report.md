# 22. Playwright 동적 사이트 보고서

작성일: 2026-06-03

## 수렴 완료

| 사이트 | 결과 | 선택자 | 비고 |
|---|---|---|---|
| signal_bz | LIVE_SUCCESS (items=5) | .rank-tex | wait_after_ms=3000 + wait_for 추가 |
| dcinside | LIVE_SUCCESS (items=3) | tr.ub-content .gall_tit a | 기존 선택자 유효 |
| eu_press_corner | LIVE_SUCCESS (items=1) | ecl-content-item | Angular ECL 선택자로 교체 |

## BLOCKED

| 사이트 | 사유 |
|---|---|
| fmkorea | Cloudflare Turnstile 봇 챌린지 — 우회 금지, deferred 유지 |

## DEFERRED

| 사이트 | 사유 |
|---|---|
| krx_kind | "잠시 후 다시 이용해 주세요" 서버 오류 페이지 반환 |
| google_trends_explore | Google 429 rate limit |

## 구현 변경

- `playwright_probe.py`: wait_after_ms + wait_selector 지원 추가
- `playwright_browser_tool.py`: `open_page()`에 `wait_after_ms`, `wait_selector` 매개변수 추가
- `site_specs.py`: `SiteSpec.wait_after_ms` 필드 추가

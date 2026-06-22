# Body Ladder Probe — 산문형 소스(nyt/opendart/culture_info)

- run: 2026-06-22T03:52:14Z (UTC)
- body_alive: 1 · blocked_no_bypass: 0 · no_body: 2
- ladder: httpx→trafilatura→readability→bs4→(browser off). no-bypass(robots/paywall/login/captcha 차단).
- body policy: body_length(숫자)만 기록, 전문/preview 미저장.

| source | content_type | eligible | urls | best_status | verdict | body_len | paywall | login | captcha |
|---|---|---|---|---|---|---|---|---|---|
| nyt | article | True | 3 | HTTP_ERROR | NO_BODY | 0 | False | False | False |
| opendart | document | True | 3 | ROBOTS_BLOCKED | NO_BODY | 0 | False | False | False |
| culture_info | detail | True | 3 | PARTIAL | ARTICLE_PARTIAL_ALIVE | 53 | False | False | False |

## 판정
- ARTICLE_BODY_ALIVE / ARTICLE_PARTIAL_ALIVE: 산문 본문 추출 성공(ladder 연결 효과 확인).
- PAYWALL/LOGIN/CAPTCHA_BLOCKED_NO_BYPASS: 정책상 우회 금지 → 본문 미수집(정직 보고).
- NO_BODY: 본문 컨테이너 없음(구조 변경/JS 렌더). NOT_ELIGIBLE_METADATA_COMPLETE: 카탈로그형(대상 아님).

## 참고
카탈로그형(aladin·tmdb·kofic·kopis·tour·igdb)은 body ladder 대상이 아니다 — metadata-complete.
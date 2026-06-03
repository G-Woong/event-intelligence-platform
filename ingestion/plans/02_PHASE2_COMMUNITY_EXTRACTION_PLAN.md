# 02_PHASE2_COMMUNITY_EXTRACTION_PLAN — 커뮤니티 10개

## 대상 소스

| ID | 이름 | 알려진 차단 |
|---|---|---|
| reddit | Reddit | login_wall, captcha |
| hackernews | Hacker News | 없음 |
| twitter_x | X (Twitter) | login_wall, captcha, JS |
| naver_news | Naver News | 없음 |
| dcinside | DCinside | captcha |
| blind | Blind | login_wall, captcha |
| ppomppu | 뽐뿌 | 없음 |
| fmkorea | 에펨코리아 | 없음 |
| clien | 클리앙 | 없음 |
| bobaedream | 보배드림 | 없음 |

## 목표 필드

`title`, `body`, `author`(익명화), `engagement`(upvotes/comments/views)

## 특수 처리

- **reddit**: JSON API (`/r/{sub}.json`) 우선 시도 — 로그인 없이 가능
- **hackernews**: Algolia API (`hn.algolia.com`) 우선
- **twitter_x**: 로그인 없이 접근 불가 → `LOGIN_WALL_DETECTED` 예상, BLOCKED 기록
- **blind**: 로그인 필요 → `LOGIN_WALL_DETECTED`, BLOCKED 기록
- **dcinside**: CAPTCHA 가능성 → `CAPTCHA_DETECTED`, BLOCKED 기록

## 익명화 정책

저자 정보는 추출하되 이름 해시 또는 "Anonymous" 처리.
report에 실제 닉네임 저장 안 함.

## BLOCKED 정책

- login_wall / captcha / JS-only → BLOCKED_* 상태 즉시 기록
- 우회(세션 재사용, 쿠키 주입) 시도 없음

## 다음 라운드 작업

Step D: 각 소스 SourceCrawler 구현 + JSON API 라우팅.

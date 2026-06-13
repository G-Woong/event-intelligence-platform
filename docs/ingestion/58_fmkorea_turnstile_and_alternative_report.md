# 58 — FMKorea Turnstile 원인 분석 및 대체 소스 보고

## 개요

FMKorea (`fmkorea.com`) 주식 게시판에 대한 접근 차단 원인을 분석하고, MVP 단계에서의 제외 결정 및 대체 소스를 정리한다.

---

## 현황

- `playwright_probe_sites.yaml` 설정:
  - `deferred: true`
  - `deferred_reason: "BLOCKED: Cloudflare Turnstile bot challenge detected on 2026-06-03; bypass not permitted"`

---

## 감지 메커니즘

`error_taxonomy.py:classify_content_blocker()` 함수가 아래 신호를 감지하면 즉시 `BLOCKED + CAPTCHA_DETECTED` 반환:

| 감지 신호 | 설명 |
|-----------|------|
| `"cf-challenge"` | Cloudflare challenge 페이지 클래스 |
| `"just a moment..."` | Cloudflare 로딩 페이지 제목 |
| `"__cf_chl_opt"` | Cloudflare challenge 옵션 스크립트 |

**Challenge solving 금지** — 감지 즉시 차단 처리, 우회 시도 없음.

---

## 단계별 분석

### 1. httpx 직접 접근

- Cloudflare가 JS 렌더링 없는 요청을 차단
- HTML 오류 페이지 반환 (JS challenge 페이지)

### 2. Playwright 접근

- Cloudflare Turnstile challenge 페이지 렌더
- `classify_content_blocker()` 가 신호 감지 → `BLOCKED` 즉시 반환

### 3. stock 게시판 특정 시도 (`/index.php?mid=stock`)

- Cloudflare 설정이 게시판별로 다를 수 있으나 우회 시도 금지
- 동일 도메인 내 다른 경로도 동일 Turnstile 적용 가능성 높음

### 4. 다른 공개 게시판 시도

- 동일 도메인(`fmkorea.com`) 하위 경로
- Cloudflare 정책이 도메인 단위로 적용될 가능성 높음
- 추가 시도 불필요

---

## 결론

**`BLOCKED_BOT_PROTECTION` (= `CAPTCHA_DETECTED`) — MVP 제외 확정**

Cloudflare Turnstile은 합법적인 봇 차단 수단이며, 이를 우회하는 것은 본 시스템의 운영 원칙(bypass not permitted)에 위배된다.

---

## 대체 소스 제안

| 소스 | 유형 | 상태/비고 |
|------|------|-----------|
| `dcinside` (stock_new1) | community | 이미 구현, `deferred=false` |
| `naver_blog_search` | search API | Naver API 키 필요 |
| `naver_news_search` | search API | 이미 구현 |
| `google_trending_now` | playwright | 이미 구현 |
| `signal_bz` | playwright | 이미 구현 |
| `loword` | playwright | 이미 구현 |
| `serper` / `tavily` / `exa` | search API | 별도 API 키 필요 |

---

## 다음 라운드 권장 사항

- **dcinside 안정화 우선** — 커뮤니티 소스 중 가장 안정적인 대안
- **FMKorea MVP 제외 확정** — 재시도 불필요, 별도 라운드 불필요
- naver_blog_search 추가를 검토할 경우 Naver API 키 발급 필요

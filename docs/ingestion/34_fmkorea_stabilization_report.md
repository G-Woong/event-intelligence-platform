# 34 — FMKorea Stabilization Report

**대상**: fmkorea (에펨코리아)  
**원칙**: 봇 차단 우회 코드 금지. BLOCKED 확정 시 중단.

---

## 1. 현황

| 항목 | 내용 |
|---|---|
| base_url | https://www.fmkorea.com |
| target page | /index.php?mid=stock |
| known_blockers | cloudflare, anti_bot |
| playwright_probe_sites.yaml | `deferred: true` |

---

## 2. 접근 시도 이력

### httpx (일반 HTTP)
- **raw_payload/fmkorea**: 74KB HTML 수집됨
- **수집 페이지**: 메인 페이지 (fmkorea.com)
- **내용**: 에펨코리아 메인 (유머/축구/게임). 스톡 게시판 아님.
- **봇 신호**: 없음 (메인 페이지는 크롤링 허용)

### playwright (스톡 게시판)
- **URL**: `https://www.fmkorea.com/index.php?mid=stock`
- **결과**: Cloudflare Turnstile bot challenge 감지
- **증거**: playwright_probe_sites.yaml `deferred_reason: "BLOCKED: Cloudflare Turnstile bot challenge detected on 2026-06-03; bypass not permitted"`

---

## 3. Turnstile 분석

Cloudflare Turnstile은 CAPTCHA의 차세대 버전으로:
- JavaScript 챌린지 + 브라우저 fingerprint 검사
- 자동화 도구(Playwright/Selenium) 탐지에 특화
- 우회 시도 = 서비스 약관 위반 + 기술적으로도 현재 스택 불가

**결론**: 우회 불가, 우회 금지.

---

## 4. 공개 페이지 접근성

| 페이지 | 접근성 |
|---|---|
| 메인 (fmkorea.com) | httpx로 접근 가능 (content 없음) |
| 스톡 게시판 (/index.php?mid=stock) | Turnstile 차단 |
| 다른 게시판 | 미확인 |

스톡 게시판이 목표이므로, httpx 수집 가능한 메인 페이지는 의미 없음.

---

## 5. 결론 및 향후 계획

| 항목 | 결정 |
|---|---|
| 현재 상태 | BLOCKED_BOT_PROTECTION |
| 우회 시도 | 금지 (약관 + 기술 이중 제약) |
| MVP 포함 여부 | 제외 (P3 이후) |
| 향후 연결 방식 | Turnstile 제거되거나 공식 API 제공 시 재검토. 현재로서는 대안 없음. |

**향후 연결 가능 조건** (참고용):
- 에펨코리아가 공식 API를 출시하는 경우
- Cloudflare Turnstile을 제거하는 경우
- 파트너십 체결로 whitelist 처리되는 경우

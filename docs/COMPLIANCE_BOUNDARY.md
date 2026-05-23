# Compliance Boundary

## 절대 금지 (STEP 007 포함 전 단계)

| 행위 | 이유 |
|---|---|
| 기사 본문 크롤링 | 저작권법 위반 위험 |
| robots.txt 우회 | 서비스 약관(ToS) 위반 |
| Paywall 우회 | 서비스 약관 위반 + 법적 위험 |
| Anti-bot 우회 (captcha 등) | CFAA(미국) / 정보통신망법(한국) 위반 위험 |
| 로그인 세션 탈취 | 위법 |
| 개인 SNS 계정 스크레이핑 | 개인정보보호법 위반 위험 |
| IP rotation / proxy 남용 | 서비스 약관 위반 |

## 허용 범위

| 행위 | 조건 |
|---|---|
| 공개 RSS 피드 파싱 | robots.txt 확인, User-Agent 정직하게 표시 |
| 공개 API 사용 (DART, SEC EDGAR) | API 약관 준수, rate limit 준수 |
| 공개 뉴스 요약(summary) 저장 | 전문 저장 금지, 출처 표시 |

## User-Agent 정책

모든 HTTP 요청에 정직한 User-Agent를 전송:
```
event-intelligence/0.7 (+ei)
```

봇 차단을 회피하기 위한 UA 위장 금지.

## Rate Limiting

- RSS 피드: 수동 트리거(one-shot) 또는 최소 15분 간격 폴링
- 과도한 요청으로 피드 서버에 부하를 줄 경우 즉시 중단

## Playwright/Selenium

- STEP 007 범위 외.
- 본문 크롤링 목적의 Playwright/Selenium 사용은 위 "절대 금지" 항목 위반 가능성 있음.
- 도입 전 법무 검토 필수.

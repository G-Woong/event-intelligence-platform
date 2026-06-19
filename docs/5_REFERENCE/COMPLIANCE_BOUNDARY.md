# Compliance Boundary

> 갱신: Round 1.5 안정화 + Round 2 구조 반영 (2026-06-03).
> 상호참조: `docs/ingestion/INGESTION_FINAL.md` §11 (금지 정책)

## 절대 금지 (Hard prohibitions)

| 행위 | 이유 |
|---|---|
| 로그인·CAPTCHA·paywall 우회 | ToS 위반 + 법적 위험 (CFAA/정보통신망법) |
| robots.txt 우회 | ToS 위반 |
| bot-protection 우회 (UA 위장 포함) | CFAA(미국) / 정보통신망법(한국) 위반 위험 |
| IP rotation / proxy 남용 | ToS 위반 |
| 개인 SNS 계정 스크레이핑 | 개인정보보호법 위반 위험 |
| API 키·토큰·인증 정보 로그·화면·외부 전송 노출 | 보안 위반 |
| `.env` 실값 출력·커밋·외부 전송 | 보안 위반 |
| X(Twitter)·Blind 수집 시도 | 로그인 필수 — BLOCKED Round 1 |
| Reuters 직접 스크레이핑 | bot_protection + paywall — NEEDS_LICENSE_OR_API |

## Ingestion Layer 허용 범위

| 행위 | 조건 |
|---|---|
| 공개 RSS/Atom/Sitemap 파싱 | robots.txt 확인, User-Agent 정직하게 표시 |
| 공개 JSON API 사용 | ToS 준수, rate limit 준수 |
| 공개 정적 HTML one-shot fetch | source/license status 기록; 전문 장기 저장 금지 |
| Playwright 공개 페이지 렌더링 | 공개 페이지 한정; login/CAPTCHA/paywall 접근 금지 |
| UA 전략 `httpx_mobile_ua`·`httpx_random_ua` | 공개 페이지 진단/호환성 테스트 목적으로만 허용; paywall·login·bot-protection 우회 목적 사용 금지 |

## 전문 저장 정책

> 사용자 화면·상용 DB에 기사 전문을 장기 저장·재게시하지 않는다.
> 개발 단계 내부 artifact(`outputs/extracted_text/`, `outputs/raw_html/`)는 품질 검증 목적의 **제한적 저장**만 허용.
> 단, 다음 조건 적용:
> - `.gitignore`에 의해 원격 추적 제외
> - 외부 노출 금지
> - retention: 검증 후 주기적 정리
> - source ID 및 license status 기록

## 소스별 허용 상태 (Round 1.5 기준)

| 소스 | 상태 | 근거 |
|---|---|---|
| BBC, AP News, TechCrunch, The Verge, ZDNet Korea, ETNews, YNA, Hankyung, Maekyung, AlJazeera, CNBC | ALLOWED | 공개 RSS/HTML (document_discovery) |
| Reddit (public .json) | ALLOWED | 공개 read-only JSON 엔드포인트 |
| HackerNews | ALLOWED | 공개 Firebase API |
| ProductHunt | ALLOWED | 공식 API (PRODUCT_HUNT_ACCESS_TOKEN 설정 후) |
| YouTube | ALLOWED | 공식 API (YOUTUBE_API_KEY 설정 후) |
| DCInside, FMKorea | ALLOWED | 공개 HTML; robots.txt 준수 필수 |
| NaverBlogSearch, NaverNewsSearch | ALLOWED | 공식 Naver 개발자 API |
| GDELT, SEC EDGAR, Federal Register, EIA, OpenDart, BOK ECOS | ALLOWED | 공개/공식 API |
| KRX KIND | NEEDS_PLAYWRIGHT | JS 렌더링 필요; Round 2에서 Playwright 구현 예정 |
| EU Press Corner | NEEDS_PLAYWRIGHT | JS 렌더링 의존 확인; Round 2 Playwright 구현 예정 |
| X (Twitter) | BLOCKED | 로그인 필수; 공개 타임라인 접근 불가 |
| Blind | BLOCKED | 로그인 필수 |
| Reuters | NEEDS_LICENSE_OR_API | 공식 API 또는 라이선스 검토 필요 |

## Phase 4 확장 후보 사전 허용 조건

| 그룹 | 소스 | 조건 |
|---|---|---|
| search_enrichment | Serper, Tavily, Exa, GNews | 공식 API 키 획득 후 허용; ToS 상업적 이용 확인 필수 |
| search_enrichment | Guardian, NYT | 공식 API 키; 비상업적 재배포 금지 조항 준수 |
| fast_signal (external) | google_trending_now, signal_bz, loword | 공식 API 없음 → low-evidence 진단 데이터로만 활용; HTML 스크레이핑 시 robots.txt 준수; 비상업적 목적 한정 |
| market_signal | Finnhub, Twelve Data, Alpha Vantage, Polygon | 공식 API 키; 시장 데이터는 정보 제공 목적만; 투자 조언 출력 금지 |
| market_signal | Coinbase, Binance | 공개 market data API; 공식 rate limit 준수 |
| domain_signal | KMA, TourAPI, ITS | 공공데이터포털(data.go.kr) 키; 공공데이터 이용약관 준수 |
| domain_signal | KOBIS, TMDB, KOPIS, Aladin, IGDB, CultureInfo | 공식 키; 각 서비스 ToS 준수; Aladin 상업적 이용 별도 계약 필요 |

## User-Agent 정책

모든 HTTP 요청에 정직한 User-Agent 전송:
```
event-intelligence/0.7 (+ei)
```

`httpx_mobile_ua`·`httpx_random_ua` 전략은 **공개 페이지 UA 호환성 진단 전용**으로만 허용.
login/CAPTCHA/paywall/bot-protection 우회 목적으로는 절대 사용 금지.

## Rate Limiting

- RSS/HTML 소스: 수동 트리거(one-shot) 또는 최소 15분 간격 폴링
- JSON API: 각 API 공식 rate limit 준수 (`03_env_and_api_policy.md` 참조)
- SEC EDGAR: 10 req/s 초과 금지
- Binance: 1200 req/min weight limit 준수
- 과도한 요청으로 서버에 부하 시 즉시 중단

## Playwright / Selenium

- 공개 페이지 렌더링 한정 (Round 2에서 KRX KIND, EU Press Corner 대상)
- login/CAPTCHA/paywall 페이지 접근 금지
- 도입 전 대상 사이트 ToS 확인 필수

## 정보 제공 원칙

- 본 시스템은 **사건/이벤트 정보 전달** 목적이다.
- 투자 권유·매수/매도 추천·금융 조언을 출력하지 않는다.
- 시장 데이터(EIA, BOK ECOS, Finnhub 등) 언급 시 가치 판단 금지.

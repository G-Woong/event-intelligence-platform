# 93. Live Collection Audit 최종 보고 (docs/85~93 라운드)

- 작성일: 2026-06-13
- 라운드 범위: query 주입 구현 + 1차 seed/2차 enrichment live audit + 주기 수집 시뮬레이션 + readiness 평가
- 비구현(범위 준수): 정규화/병합/게시/LLM 생성/Celery/DB migration 없음

## 1. 한 줄 결론

수집 계층이 "소스가 살아있다"를 넘어 **"이벤트 큐 seed 21종 + query 확장 9종 + 주기 수집 게이트"가 용도 기준으로 실측 검증**되었고, Celery 오케스트레이션(plans/012) 진입 전 남은 것은 소스 정비 4건과 Route 1 429 cooldown 기록 gap 1건이다.

## 2. 종료 조건 체크리스트 (§12)

| # | 항목 | 판정 | 근거 |
|---|------|------|------|
| 1 | 1차/2차 source 분류 완료 | **PASS** | docs/86 (전체 소스, role 5종) |
| 2 | 소스별 역할·expected output 정리 | **PASS** | docs/86 컬럼 충족 |
| 3 | limit/frequency profile | **PASS** | docs/87 (UNKNOWN은 conservative 명시) |
| 4 | 1차 live audit | **PASS** | 40 소스 × 1회, 전 소스 record (docs/88) |
| 5 | 2차 live audit (seed 기반 + 대분류 기반) | **PASS** | 35 호출, seed 17 + 대분류 18, query별 배정 기록 (docs/89) |
| 6 | periodic simulation | **PASS** | 8 소스 × 2 cycle (docs/90) |
| 7 | rate limit/cooldown/health 동작 검증 | **PASS (gap 1건 발견)** | cache_skip dedup PASS·local_file 영속 PASS·health 누적 PASS. cooldown_skip literal은 미관찰 — 원인이 **Route 1 429 미기록 gap**으로 규명되어 RISK-T04 등재 (docs/90 §3) |
| 8 | event queue readiness 평가 | **PASS** | 기준 10종 + 그룹 4종 판정 (docs/91) |
| 9 | EventSeedCandidate schema 제안 | **PASS** | docs/91 §4 (문서 제안만, migration 없음) |
| 10 | frequency draft | **PASS** | docs/92 (bucket 5종, provisional 표기) |
| 11 | secret scan | **PASS** | verdict=PASS, 896 files |
| 12 | env hygiene 기록 | **PASS (WARNING 6건)** | 기존 legacy alias 6건 — 변동 없음, 기능 영향 없음 (docs/82 동일) |
| 13 | pytest 통과 | **PASS** | **509 passed, 0 failed** (기준선 450 + 신규 59) |
| 14 | 신규 runner 실행 결과 기록 | **PASS** | outputs/jsonl·reports 6종 (88·89·90에 경로 명시) |
| 15 | docs/85~93 생성 | **PASS** | 9편 전부 |
| 16 | docs/70~73 갱신 | **PASS** | 각 문서 06-13 섹션 추가 |
| 17 | google_trends_explore 호출 | **DEFERRED** | 계획대로 기본 off (`--include-trends-explore` opt-in) — 429 이력 보호 우선, 이번 라운드 미실행 |

## 3. 1차 결과 (seed)

40 소스 호출: LIVE_SUCCESS 38, ap_news HTML 에러 페이지, gdelt 429. **seed_ready yes 23 / partial 9 / no 8**. 뉴스 RSS 그룹(yna 120건 등)이 title+url+timestamp 완비로 최상위. 상세 docs/88.

## 4. 2차 결과 (enrichment)

35 query 호출: LIVE_SUCCESS 30, **relevance high 24/medium 2**. 핵심 그룹: serper·tavily·exa·naver×2·gnews·guardian·nyt·youtube. 실패: newsapi 0건×2(endpoint 부적합), gdelt PARSE_ERROR+429, 장문 공시명 query 0건. 상세 docs/89.

## 5. seed→enrichment 연결 (핵심 검증)

signal_bz 실검 **"이재명 대통령 멜로니" → serper/naver_news_search에서 관련 기사 3건+ (relevance high)** — 1차 감지 keyword가 2차 확장 수집으로 이어지는 파이프라인이 실측으로 성립. kofic "군체" → tmdb가 영문 제목 "Colony"를 정확 조회 (cross-language lookup 성립).

## 6. 대분류 검증

한글 10종/영문 8종 대분류 query를 언어 호환 소스에 배정 — 호출된 전 조합에서 items>0 + high relevance (newsapi 제외). 대분류 기반 카테고리 모니터링 운영 가능.

## 7. 주기 수집 가능성

2 cycle 시뮬레이션 무오류 (called 14/14 LIVE_SUCCESS). gdelt cache(ttl 900s)가 프로세스를 넘어 재호출 차단 (artifacts_new 0 — dedup 실증). local_file backend 영속 확인. cycle당 ~40s (playwright 2종 포함).

## 8. Event Queue Readiness / 권장 주기

ready 21 + enrichment 9 + caution 8 + not_ready 7 (docs/91). 주기: near_real_time 4종(yna/finnhub/binance/gdelt-15분) / short 20여 종 / medium(trends 2h+, 검색은 이벤트 트리거) / daily 12종 (docs/92, provisional 표기 포함).

## 9. 실패·주의 소스

| 소스 | 문제 | next_action |
|---|---|---|
| gdelt | 429 ×2 + PARSE_ERROR (실측 3/3 실패) | 15분+ 간격 + 오류 내성, RISK-S02 |
| ap_news | RSS가 HTML 에러 페이지 | endpoint 점검 (RISK-S03) |
| newsapi | top-headlines+q 0건 | /v2/everything 전환 (RISK-S04) |
| loword/google_trending_now/dcinside/eu_press_corner | selector 미매칭 (page title만) | update_selector (RISK-S05) |
| hacker_news | id 목록만 | item detail 2차 호출 설계 |
| bok_ecos/eia/its | sample 매핑 부재 (수집은 정상) | `_SAMPLE_PATHS` 추가 |
| **Route 1 429 (인프라)** | cooldown 미기록 gap | **plans/012 전 수정 권장 (RISK-T04)** |

## 10. 테스트·보안

- pytest **509 passed, 0 failed** (신규: query 주입 25 + audit_common 26 + runner 8)
- 기존 450 테스트 **무수정 통과** (collection_probe는 query 없을 때 기존 호출 형태 유지)
- scan_secrets **PASS** (896 files, 실키 0건) / env hygiene WARNING 6건(기존 alias, 변동 없음)
- `.env` 미수정, 키 값 미출력, CAPTCHA/login 우회 없음, 호출 총량 ~91회 (예산 ~90 정합, 전 소스 quota 10% 미만)

## 11. 판정

종료 조건 17항 중 PASS 16 / DEFERRED 1 (trends_explore — 계획상 opt-in). 미충족을 "완료"로 표기한 항목 없음.

**판정: A** — 라운드 목표(1차/2차 용도 검증·제한/주기 확정·반복 수집 검증·readiness 평가) 전부 달성. 단, plans/012 진입 전 RISK-T04(Route 1 429 cooldown 기록)와 소스 정비 4건(ap_news/newsapi/gdelt/selector)을 선행 권장.

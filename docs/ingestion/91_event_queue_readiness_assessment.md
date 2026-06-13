# 91. Event Queue Readiness Assessment

- 작성일: 2026-06-13
- 근거: docs/88(1차 실측), docs/89(2차 실측), docs/90(시뮬레이션)
- 목적: 정규화/병합 구현 **전에** "어떤 소스의 데이터가 이벤트 큐 seed로 투입 가능한가"를 실측 기준으로 판정

## 1. 평가 기준 10종

| # | 기준 | 실측 결과 |
|---|---|---|
| 1 | seed 가능 소스 수 | 1차 40개 중 seed_ready yes 23 / partial 9 |
| 2 | 최소 필드(3+) 충족률 | called 40 중 23 (57.5%) — 뉴스/검색/공시 그룹은 90%+ |
| 3 | title 존재율 | 32/40 (시장 flat 응답·hacker_news id 목록 제외) |
| 4 | source_url 존재율 | 19/40 — RSS/검색/공시는 보유, 국내 공공 API·시장 데이터는 항목 URL 개념 없음 |
| 5 | timestamp 존재율 | 22/40 — 부재 소스는 observed_at(수집 시각)으로 대체 가능 |
| 6 | 중복 가능성 | gdelt cache_skip 실증(docs/90) — cache ttl 보유 소스는 인프라가 차단. ttl 0 소스는 정규화 단계 dedup 필요 (URL hash 기준) |
| 7 | hint 존재 (category/country) | RSS category tag·kma 지역격자·kofic rank 등 부분적 — 스키마에 optional hint 필드 필요 |
| 8 | 2차 query 생성 가능성 | signal_bz 실검→serper/naver 확장 실증 (docs/89 §4). 단 장문 title은 절단 필요 |
| 9 | 운영 주기 실현성 | 시뮬레이션 2 cycle 무오류, cycle당 ~40s — docs/92 주기 실행 가능 |
| 10 | 정규화 전 gap | sample 매핑 부재(bok_ecos/eia/its), hacker_news 2차 호출, newsapi endpoint 교체, Route1 429 cooldown 미기록(docs/90 §3) |

## 2. 소스 그룹 판정

### event_queue_ready_sources (즉시 seed 투입 가능 — title+url+timestamp 실측 확인, 21)
bbc, techcrunch, the_verge, yna, hankyung, maekyung, aljazeera, cnbc, youtube, opendart, sec_edgar, kofic, tmdb, kopis, aladin, kma, tour, twelve_data, product_hunt*, zdnet_korea*, etnews*
(\* timestamp 또는 url 1개 결손 — observed_at/고정 URL로 보완 가능한 수준)

### enrichment_ready_sources (2차 확장 실측 검증 완료, 9)
serper, tavily, exa, naver_news_search, naver_blog_search, gnews, guardian, nyt, youtube
(+ 파라미터형 lookup 15종은 검증용 enrichment — docs/89 §3)

### caution_sources (동작하나 조건부, 8)
- gdelt — both 역할 가치 높으나 429/PARSE_ERROR 불안정. 15분+ 간격, 오류 내성 후 투입
- signal_bz — keyword seed 실증, 단 selector 취약층 (browser_risk)
- google_trending_now, loword — LIVE_SUCCESS이나 keyword selector 미매칭 (`update_selector`)
- dcinside, eu_press_corner — page title만 추출 (`update_selector`)
- newsapi — endpoint 교체 전 enrichment 부적합
- ap_news — RSS endpoint HTML 에러 페이지 (점검 필요)

### not_ready_sources (이번 라운드 기준 seed 부적합, 7)
- hacker_news (id 목록만 — item detail 호출 설계 필요)
- bok_ecos, eia, its (sample 매핑 부재 — 수집은 정상)
- finnhub, alpha_vantage, polygon, coinbase_market, binance_market — **수치 signal 그룹**: 문서형 seed가 아닌 임계값 트리거(가격 급변 감지)로 별도 설계 (EventSeedCandidate가 아니라 MarketSignal 경로)

### 제외 유지
krx_kind, reddit, x, blind, reuters, fmkorea, google_programmable_search, google_trends_explore(수동 전용)

## 3. required_schema_before_normalization

정규화 진입 전 최소 요건:
1. 모든 seed에 `observed_at`(수집 시각, UTC ISO 8601) 필수 — published_at 부재 소스 보완.
2. `source_url` 부재 소스는 `raw_artifact_path`로 원본 추적 가능해야 함.
3. dedup key: `hash(source_id + (source_url or title_or_keyword) + date_bucket)` 제안.
4. 수치 signal 소스는 본 스키마 대상 외 (별도 MarketSignal 설계).

## 4. EventSeedCandidate schema 제안 (문서 제안만 — DB migration 금지)

```yaml
EventSeedCandidate:
  seed_id: str            # uuid — 생성 시 부여
  source_id: str          # registry id (필수)
  source_layer: str       # document_discovery | community_signal | official_evidence |
                          # fast_signal | domain_signal (market_signal은 별도 경로)
  title_or_keyword: str   # 필수 — 기사 title 또는 트렌드 keyword (120자 절단)
  snippet: str | null     # 200자 절단
  source_url: str | null  # 항목 URL (없으면 raw_artifact_path로 추적)
  observed_at: str        # 필수 — 수집 시각 (UTC ISO 8601)
  published_at: str | null  # 소스 제공 발행 시각 (포맷 정규화 필요: RFC822/ISO 혼재 실측)
  country_hint: str | null   # 예: KR(yna/kma), US(sec_edgar) — 소스 기본값 매핑
  category_hint: str | null  # RSS category, kofic=culture, kma=weather 등
  entity_hints: list[str]    # title에서 추출한 인물/기업/지명 후보 (정규화 단계 채움)
  evidence_level: str        # registry evidence_level 복사 (tier1~3)
  raw_artifact_path: str     # 필수 — outputs/raw_payload|rendered_dom 경로
  collection_status: str     # PROBE_STATUS 값 (LIVE_SUCCESS 등)
```

검증 규칙 제안: `title_or_keyword` 비어있으면 생성 금지 / `observed_at` 필수 / `source_id`는 registry 존재 검증 / 같은 dedup key는 큐 투입 전 병합.

## 5. 결론

- 1차 seed 공급망(뉴스 RSS 10 + 공시 2 + 도메인 6 + 트렌드 1)과 2차 확장망(검색·뉴스 API 9)이 **실측으로 연결 검증됨** — Celery 오케스트레이션(plans/012)의 데이터 전제 충족.
- 차단 요건은 스키마가 아니라 **개별 소스 정비 4건** (ap_news endpoint, newsapi everything 전환, gdelt 내성, selector 보강 3종)과 **Route 1 429 cooldown 기록 gap** (docs/90 §3).

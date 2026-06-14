# 02 — 소스 역할 및 목적별 라우팅 설계

> **목적**: 58개 소스를 "같은 방식으로 일괄 수집"하지 않는다. 각 소스의 **특징(데이터 모양, 접근 방식, 신선도 요구, rate-limit 민감도, 법무 위험, 상업 가치)**을 파악해, **목적(이벤트 발견 / 후보 추출 / 정보 확장 / 본문 보강 / 커뮤니티 반응 / 공식 확인 / 신호)**별로 다른 파이프라인에 태운다.
> **핵심 원칙**: 오케스트레이션은 단순 cron이 아니다. **"어떤 소스를, 어떤 목적으로, 어떤 전략으로"의 3차원 매핑**이다.

---

## 0. 비개발자를 위한 설명

뉴스 한 건을 모으는 것과, 한국은행 통계를 모으는 것과, 디시인사이드 반응을 모으는 것은 **전혀 다른 일**이다.

- 뉴스는 "새 기사가 떴는가?"를 자주 확인해야 한다(신선도 중요).
- 한국은행 통계는 하루 한 번이면 충분하다(느리게 변함).
- 커뮤니티 반응은 "사건이 터진 뒤"에야 의미가 있다(이벤트 트리거).
- 시세는 5분만 지나도 낡는다(초신선도).

그래서 우리는 소스를 **9개 성격 그룹**으로 나누고, 각 그룹이 **무슨 목적에 쓰이는지**를 정한다. 이렇게 하면 "비싼 검색 API를 5분마다 호출해서 돈을 날리는" 같은 실수를 구조적으로 막을 수 있다.

---

## 1. 소스 카테고리 (9개 성격 그룹)

> 분류 근거: `docs/ingestion/INGESTION_FINAL.md §2, §3` + `ingestion/configs/source_registry.yaml`.

### 1.1 breaking/news sources (속보·뉴스, 약 10개)
- **소스**: bbc, ap_news, techcrunch, the_verge, zdnet_korea, etnews, yna, hankyung, maekyung, aljazeera, (caution: cnbc)
- **특징**: RSS/HTML, 분~시간 단위 신선도, 본문 추출 난이도 중간, 재배포 일부 제한
- **현재 runner**: Route 3(전략 루프) 또는 RSS. ap_news는 Google News RSS 프록시.
- **목적**: **event_discovery**(사건 발견) + **event_candidate_extraction**(후보 추출)
- **수집 주기**: short_interval(30~60분), yna는 near_real_time(5~15분)

### 1.2 official/company sources (공식·기업, 일부)
- **소스**: eu_press_corner, (기업 블로그류는 뉴스에 흡수)
- **특징**: 공식 발표, 신뢰도 최상(tier1), 본문 구조 안정, 재배포 보통 허용
- **목적**: **official_confirmation**(공식 확인 — 뉴스/커뮤니티 주장과 대조)
- **주기**: medium_interval(2~6시간)

### 1.3 regulatory/filing sources (규제·공시, 약 6개)
- **소스**: sec_edgar, federal_register, opendart, bok_ecos, eia, (deferred: krx_kind)
- **특징**: API/구조화 데이터, 법적 1차 출처(최고 증거력), 본문=구조화 필드, rate-limit 관대(sec 10req/s)
- **현재 runner**: Route 1(API)
- **목적**: **official_confirmation** + **evidence_backfill**(증거 보강)
- **주기**: official: 1시간 / 통계: daily

### 1.4 community sources (커뮤니티, 약 3~5개)
- **소스**: hacker_news, youtube, product_hunt, reddit(MVP_DEFERRED), (caution: dcinside), (excluded: blind, fmkorea)
- **특징**: 반응·여론, 신뢰도 낮음~중간, 노이즈 많음, 일부 봇 차단(fmkorea=Cloudflare Turnstile)
- **현재 runner**: hacker_news=API(2차 detail 호출), youtube=API, dcinside=Route 2/검색
- **목적**: **community_reaction**(사건 발생 후 여론 수집) — **이벤트 트리거 전용, 정기 폴링 비권장**
- **주기**: short_interval 또는 on-demand
- **원칙(D-9 확정, 불변)**: 커뮤니티는 **early signal**이지 **confirmed fact가 아니다.** 커뮤니티 **단독으로 사건을 확정·발행하지 않는다.** 공식/뉴스/다중출처 보강 없이 publish 시 `community_signal`/`unconfirmed` 라벨 필수(09 §community_vs_official_balance). hacker_news/youtube/product_hunt는 MVP 포함, dcinside는 CAUTION 모니터링.

### 1.5 trend/search sources (트렌드·검색, 약 9개)
- **트렌드**: signal_bz, google_trending_now, loword, (caution: google_trends_explore=CONFIRMED_EXTERNAL_RATE_LIMIT)
- **검색**: serper, tavily, exa, gnews, naver_news_search, naver_blog_search, (caution: newsapi)
- **특징**: 트렌드=급상승 키워드 감지, 검색=쿼리 기반 확장. 검색은 **유료 quota** 민감.
- **목적**: 트렌드 → **event_discovery**(새 사건 신호) / 검색 → **related_information_expansion**(이미 발견된 사건의 주변 정보 확장)
- **주기**: 트렌드=medium(2시간+ 고정, Google IP 차단 위험) / 검색=**on-demand(이벤트 트리거), 정기 폴링 금지**

### 1.6 numeric/market sources (시세·수치, 약 6개)
- **소스**: finnhub, twelve_data, alpha_vantage, polygon, coinbase_market, binance_market
- **특징**: API, 숫자 신호(body 없음 정상), 초신선도, alpha_vantage=일 25req 극제한
- **현재 runner**: Route 1(API), NUMERIC_SIGNAL_SOURCES 분류
- **목적**: **numeric_signal**(시세 급변 = 사건 신호). body_length 게이트 면제.
- **주기**: near_real_time(5~15분), alpha_vantage만 daily

### 1.7 academic/evidence sources (학술·근거)
- **소스**: (현재 전용 소스 미약 — sec_edgar/federal_register가 1차 증거 역할 겸함)
- **목적**: **evidence_backfill** — 사건 주장의 근거 문서 연결
- **주기**: on-demand

### 1.8 domain/vertical sources (도메인 특화, 약 9개)
- **소스**: kofic(영화), igdb(게임), tmdb(영화/TV), kopis(공연), aladin(도서), kma(기상), tour(관광), its(교통), culture_info(문화)
- **특징**: API, 도메인 한정 신호, 일 단위 갱신, 상업 가치는 버티컬 의존
- **목적**: **domain_signal**(특정 산업 사건) — 버티컬 제품에서 가치
- **주기**: daily~6시간

### 1.9 fallback/related expansion sources (대체·확장)
- **소스**: google_trending_now(트렌드 fallback), RSS export, serper/tavily/naver(검색 fallback)
- **특징**: 1차 소스 실패 시 자동 대체. `extract_related_candidates` 규칙 기반 확장.
- **목적**: **related_expansion** + **fallback** — 주 소스가 막혀도 사건 맥락을 잃지 않게.

### 1.10 blocked/deferred sources (제외·보류, 6개)
- **소스**: x(유료), blind(login), reuters(라이선스+bot), fmkorea(Turnstile), google_programmable_search(CX 미설정), reddit(MVP_DEFERRED)
- **처리**: **스케줄 대상에서 제외**. registry `status`를 스케줄러가 읽어 자동 skip. 코드는 보존(우회 금지).

---

## 2. 목적별 라우팅 (Purpose Router)

오케스트레이션은 "수집 목적"을 먼저 정하고, 그 목적에 맞는 소스 그룹을 부른다.

| 목적(purpose) | 의미 | 주 소스 그룹 | 트리거 |
|---|---|---|---|
| **event_discovery** | 새 사건 후보 감지 | 뉴스, 트렌드, 시세 | 주기(bucket) |
| **event_candidate_extraction** | 발견된 원문 → 사건 후보 | 뉴스, 공식 | event_discovery 직후 |
| **related_information_expansion** | 사건 주변 정보 확장 | 검색(serper/tavily/naver) | event 후보 생성 시(on-demand) |
| **body_enrichment** | URL → 본문 추출 보강 | 모든 소스(04 cascade) | 후보에 body 부족 시 |
| **official_confirmation** | 공식 출처로 사실 확인 | 공시, 규제, 공식 | 사건 후보가 공식성 요구 시 |
| **community_reaction** | 여론·반응 수집 | 커뮤니티 | 사건 확정 후(on-demand) |
| **numeric_signal** | 시세 급변 신호 | 시세 | 주기(near_real_time) |
| **source_health_probe** | 소스 생존 점검 | 전체 | 격리 소스 주 1회 |
| **evidence_backfill** | 근거 문서 연결 | 규제/학술 | 사건 카드 작성 시 |

**라우팅 흐름 예시 (사건 1건의 생애)**:
```
1. event_discovery: yna 주기 수집 → "삼성전자 신규 투자" 기사 발견
2. event_candidate_extraction: 기사 본문 → EventSeedCandidate(title, url, timestamp)
3. related_information_expansion: serper/naver_news로 "삼성전자 투자" 검색(on-demand, quota 차감)
4. official_confirmation: opendart에서 관련 공시 조회
5. numeric_signal: finnhub/krx 시세 변동 첨부(가치판단 없이 정보로만)
6. community_reaction: hacker_news/dcinside 반응(노이즈 필터 후)
7. evidence_backfill: federal_register/sec_edgar 근거 링크
→ 사건 카드 완성 → 다운스트림(event queue → LangGraph → UI)
```

---

## 3. 카테고리별 상세 (특징 / runner / 전략 / 금지 / fallback / rate-limit / output / risk)

> 각 카테고리를 구현 가능한 수준으로 못 박는다. **금지 전략**을 명시해 우회·과호출을 구조적으로 차단한다.

### 3.1 breaking/news

| 항목 | 내용 |
|---|---|
| source 특징 | RSS/HTML, 본문 추출 필요, 재배포 일부 제한(guardian/nyt CONDITIONAL) |
| 현재 runner | Route 3 전략 루프, ap_news는 Google News RSS 프록시 |
| 적합 전략 | httpx_direct → readability/trafilatura. RSS 있으면 feed 우선 |
| 금지 전략 | paywall 우회 금지(nyt/guardian 유료벽 → preview만). proxy rotation 금지 |
| fallback | RSS export → Google News 프록시 → 검색 enrichment |
| rate-limit | 매체별 30~60분. 과호출 시 봇 차단 위험 |
| output contract | EventSeedCandidate(title, url, timestamp) + ExtractedArticle(body) |
| risk | 재배포 위반(full-text 저장), 봇 차단 |
| implementation diff | `03` StrategyRouter에 `preferred_strategy="rss_feed_fetch"` 매핑 |

### 3.2 regulatory/filing

| 항목 | 내용 |
|---|---|
| source 특징 | API, 구조화 필드, 최고 증거력, rate-limit 관대 |
| 현재 runner | Route 1 API (`run_api_live_probe`) |
| 적합 전략 | `api_json_fetch` |
| 금지 전략 | 무차별 entity 조회(quota 낭비). sec_edgar entity query ≤50/day |
| fallback | API 실패 시 재시도(지수 backoff), 우회 없음 |
| rate-limit | sec 10req/s, opendart/bok 키 기반 |
| output contract | 구조화 필드 그대로(body 추출 불필요) |
| risk | quota 초과, 키 노출 |
| implementation diff | `numeric_signal`처럼 body 면제. SourceProfile `body_extraction_difficulty="none"` |

### 3.3 community

| 항목 | 내용 |
|---|---|
| source 특징 | 반응·노이즈, 신뢰도 낮음, 일부 Turnstile/login 차단 |
| 현재 runner | hacker_news=API(2차 detail), youtube=API, dcinside=검색/Route2 |
| 적합 전략 | API 우선. dcinside는 search_url→본문 |
| 금지 전략 | **fmkorea Turnstile 우회 금지, blind login 우회 금지** → 즉시 BLOCKED_TERMINAL |
| fallback | 차단 소스는 격리. 대체 커뮤니티 없으면 community_reaction skip(비차단) |
| rate-limit | short_interval, on-demand 권장 |
| output contract | ExtractedPost(반응 텍스트 + 메타) |
| risk | 노이즈 증폭, 명예훼손(개인 발언 재배포), 봇 차단 |
| implementation diff | 09 품질 게이트에 community noise 필터 |

### 3.4 trend/search

| 항목 | 내용 |
|---|---|
| source 특징 | 트렌드=키워드 신호, 검색=유료 quota |
| 현재 runner | 트렌드=Route2/RSS, 검색=Route1 API |
| 적합 전략 | 트렌드: `structure_explorer`/RSS. 검색: `api_json_fetch`(on-demand) |
| 금지 전략 | **google_trends_explore 429 우회 금지**(proxy/internal RPC/login). 검색 정기 폴링 금지(quota 폭발) |
| fallback | google_trends_explore → google_trending_now → RSS export → 검색 enrichment(04 §6 chain) |
| rate-limit | 트렌드 7200s 고정. 검색 일일 budget(serper ≤30, tavily/exa ≤30) |
| output contract | 트렌드: 키워드 리스트+rank. 검색: 결과 URL+snippet |
| risk | **google_trends_explore를 PASS로 오기 금지**(CONFIRMED_EXTERNAL_RATE_LIMIT). quota 비용 폭발 |
| implementation diff | quota guard(06 §) + fallback chain(04 §6) |

### 3.5 numeric/market

| 항목 | 내용 |
|---|---|
| source 특징 | 숫자 신호, body 없음 정상, 초신선도 |
| 현재 runner | Route 1 API, NUMERIC_SIGNAL_SOURCES |
| 적합 전략 | `numeric_signal_fetch` |
| 금지 전략 | alpha_vantage 일 25 초과 호출 금지(1일 1회 고정) |
| fallback | API 실패 시 직전 값 재사용(stale 표기), 가치판단 금지 |
| rate-limit | near_real_time 5~15분 |
| output contract | NumericSignal(symbol, value, ts) — body_length 게이트 면제 |
| risk | **투자 조언화 금지**(CLAUDE.md 원칙 1) — 가격을 "사라/팔라"로 변환 금지 |
| implementation diff | 09 게이트에서 numeric `signal_ready` 판정 |

### 3.6 domain/vertical

| 항목 | 내용 |
|---|---|
| source 특징 | API, 도메인 한정, 일 단위 |
| 적합 전략 | `api_json_fetch` |
| 금지 전략 | 불필요한 고빈도 호출 |
| fallback | API 실패 시 daily 재시도 |
| rate-limit | daily~6시간 |
| output contract | 도메인 신호(영화 박스오피스, 공연 일정 등) |
| risk | 버티컬 가치 외 노이즈 |
| implementation diff | MVP에선 일부만 활성(D-9), 나머지 deferred |

---

## 4. SourceProfile 스키마 (이 문서의 산출 — 03에서 구현)

각 소스에 대해 다음을 정의한다(상세 코드 구조는 `03_COLLECTION_STRATEGY_ROUTER_DESIGN.md`).

```
SourceProfile:
  source_id: str
  source_type: news|regulatory|community|trend|search|numeric|domain|fallback
  role: primary_seed|enrichment|both|deferred|excluded
  data_shape: article|structured_filing|post|keyword_list|numeric|search_result
  access_method: api|rss|playwright|strategy_loop
  freshness_need: near_real_time|short|medium|daily
  rate_limit_sensitivity: low|medium|high   # google 계열=high
  body_extraction_difficulty: none|low|medium|high
  legal_risk: low|conditional|excluded       # nyt/guardian=conditional
  commercial_value: low|medium|high
  reliability_score: 0.0~1.0                  # tier1 공식=high
  preferred_strategy: <CollectionStrategy>
  fallback_strategies: [<CollectionStrategy>, ...]
  blocked_conditions: [captcha, login, paywall, robots, quota]
  artifact_policy: full|signal_only|preview_only
  next_retry_policy: <from rate_limit_policy.yaml>
```

---

## 5. 목적별 라우팅 매핑 표 (요약 — 구현 참조)

| source 그룹 | 주 목적 | preferred_strategy | 트리거 | quota 민감 |
|---|---|---|---|---|
| 뉴스 | event_discovery+extraction | rss_feed_fetch / strategy_loop | 주기(short) | 낮음 |
| 규제·공시 | official_confirmation | api_json_fetch | 주기(1h)+on-demand | 낮음 |
| 커뮤니티 | community_reaction | api/search | on-demand(이벤트 후) | 중간 |
| 트렌드 | event_discovery | structure_explorer/rss | 주기(2h+ 고정) | **높음(Google)** |
| 검색 | related_expansion | api_json_fetch | **on-demand only** | **높음(유료)** |
| 시세 | numeric_signal | numeric_signal_fetch | 주기(5~15분) | 중간(alpha=높음) |
| 도메인 | domain_signal | api_json_fetch | daily | 낮음 |
| fallback | related/fallback | (chain) | 주 소스 실패 시 | 중간 |

---

## 6. Agent Committee Review

| agent | 피드백 | status |
|---|---|---|
| source-ingestion-engineer | 카테고리별 preferred_strategy가 기존 3-way 라우팅과 정합 | CLOSED_BY_DESIGN |
| orchestrator-architect | 목적 라우터(purpose) + 전략 라우터(strategy) 2단 분리가 핵심. on-demand vs 주기 구분 명확 | CLOSED_BY_DESIGN |
| data-quality-auditor | community noise / numeric body 면제 규칙이 09 게이트와 연결됨 | CLOSED_BY_TEST_PLAN |
| legal-safety-compliance-reviewer | nyt/guardian preview-only, fmkorea/blind 우회 금지 명시 — 승인 | CLOSED_BY_DESIGN |
| commercialization-strategist | 소스 다양성을 목적별로 묶어 제품 가치(증거 다층화)로 연결 | CLOSED_BY_DESIGN |
| adversarial-reality-critic | "검색 정기 폴링 금지"가 가장 흔한 비용 사고 — 구조적 차단 양호. on-demand 트리거 구현이 미지수 | USER_CONFIRMATION_REQUIRED |
| evaluation-benchmark-agent | reliability_score를 evidence_completeness 지표에 연결 | CLOSED_BY_TEST_PLAN |

---

## 7. Risk Closure

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| 검색 quota 폭발 | 유료 검색을 정기 폴링 | 비용 급증 | quota 카운터 | on-demand only + daily budget | quota guard 테스트 | CLOSED_BY_DESIGN |
| google_trends 우회 유혹 | 429 회피 욕구 | IP 차단/약관 위반 | 전략 로그에 proxy 검출 | BLOCKED_BY_POLICY 고정 | grep "proxy rotation" 0건 | BLOCKED_BY_POLICY |
| community 노이즈 증폭 | 저신뢰 반응 다량 유입 | 사건 품질 저하 | noise 비율 측정 | 09 noise 게이트 | 게이트 단위 테스트 | CLOSED_BY_TEST_PLAN |
| numeric→투자조언 | 가격을 매수/매도로 변환 | 정책 위반 | 출력 grep | 정보 환원 규칙(CLAUDE.md 원칙1) | 출력 톤 검사 | CLOSED_BY_DESIGN |
| 재배포 위반 | nyt/guardian full-text 저장 | 법적 위험 | publication_policy 검사 | preview-only artifact_policy | 08 §정책 테스트 | CLOSED_BY_DESIGN |

---

## 8. Commercialization Impact

- **증거 다층화가 제품 신뢰의 원천**: 한 사건을 "뉴스+공식 공시+시세+커뮤니티 반응"으로 교차 제시하면, 단일 소스 경쟁사 대비 신뢰도가 확연히 높다. 목적별 라우팅이 이 다층 구조를 가능케 한다.
- **버티컬 확장 경로**: domain/vertical 소스(영화·게임·공연·기상)는 B2B 버티컬 제품(예: 콘텐츠 산업 인텔리전스)의 씨앗.
- **비용 절제**: on-demand 라우팅으로 유료 검색 호출을 "사건 발생 시"로 한정 → 비용을 사용자 가치와 연동.

---

## 9. USER_CONFIRMATION_REQUIRED

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| on-demand 검색 트리거의 임계(사건 후보 몇 점 이상에서 확장)? | 비용·품질 균형 | significance ≥ 0.5에서 확장 | No |
| community 소스 MVP 범위? | 노이즈 vs 풍부함 | hacker_news/youtube/product_hunt 포함, dcinside CAUTION | No |
| domain 소스 MVP 활성 범위? | 버티컬 우선순위 | kofic/tmdb/kma만 1차, 나머지 deferred | No |

> 다음 문서: `03_COLLECTION_STRATEGY_ROUTER_DESIGN.md`.

---

## 10. Phase C-2 — SourceProfile Full Coverage Audit (2026-06-14)

> 목적: 개별 소스 수집 검증(완료)을 넘어, **canonical 소스 전체가 오케스트레이션 레이어에서 빠짐없이 연결**되는지 확정. 산출물 = `ingestion/configs/source_profiles.yaml` 전수화 + dry-run/live smoke 검증.

### 10.1 Canonical source set (정본: docs/ingestion/INGESTION_FINAL.md + source_registry.yaml)

| 분류 | count | 처리 |
|---|---|---|
| **CORE_READY** | 44 | enabled=true. no-key & no-blocker는 live_eligible=true |
| **READY_WITH_CAUTION** | 6 (cnbc, guardian, nyt, newsapi, dcinside, google_trends_explore) | enabled=true, profile_status=caution |
| **DEFERRED_SPECIAL_ROUND** | 1 (krx_kind) | enabled=false, skip=needs_api_integration |
| **MVP_DEFERRED** | 1 (reddit) | enabled=false, skip=disabled_by_policy |
| **MVP_EXCLUDED** | 5 (x, blind, reuters, fmkorea, google_programmable_search) | enabled=false, skip=login/paywall/captcha_no_bypass |
| _dummy(픽스처) | 1 | 미등록(운영 대상 아님) |
| **source_profiles.yaml 등록 합계** | **57** | CORE_READY 44 + CAUTION 6 + 제외군 7 |

> **명명 주의**: `google_trends_explore`(CAUTION)는 registry/`_SERVICE_CONFIGS`에 **미등록**(runner만 존재) → 프로파일은 등록하되 `live_eligible=false, skip=needs_api_integration, profile_status=verify_required`. registry id = `_SERVICE_CONFIGS` key 일치(56, _dummy 제외) 실측 확인.

### 10.2 Orchestration coverage 집계

| 지표 | 값 |
|---|---|
| 등록 프로파일 | 57 |
| enabled (orchestration 대상) | 50 |
| disabled (제외군 + skip_reason) | 7 |
| live_eligible=true | 17 (no-key 뉴스 10 + hacker_news + 공식 no-key 3 + 시장 no-key 2 + eu_press_corner) |
| live_eligible=conservative | 4 (cnbc, signal_bz, google_trending_now, loword) |
| requires_api_key | 29 (CORE_READY/CAUTION에 키 필요 — 키 있으면 작동, live smoke는 보수적 skip) |
| is_community | 9 (전부 unconfirmed_until_corroborated) |

### 10.3 Dry-run orchestration (fake probe/queue, 네트워크 0)

전체 enabled(50) → profiles_to_schedules → select_due → run_cycle(fake) 전수 통과: 50소스 각 1회 probe, 50 enqueue, disabled 7 미호출, 단일 실패 격리 확인. (`test_source_profile_full_coverage.py`)

### 10.4 Live orchestration smoke (제한적 — live_only=True, force=False, max_items=1)

| source_id | attempted_live | status | items_found | enqueued | skip_reason | notes |
|---|---|---|---|---|---|---|
| yna | yes | LIVE_SUCCESS | 120 | yes | - | RSS |
| hacker_news | yes | LIVE_SUCCESS | 3 | yes | - | community, unconfirmed 유지 |
| gdelt | yes | RATE_LIMITED | 0 | no | - | 직전 호출 쿨다운(15분) — health gate 정상 차단, no bypass |
| 그 외 live_eligible=true 14 | no | - | - | - | smoke_scope_limited | 부하/시간 절약, dry-run으로 orchestration 경로 검증됨 |
| requires_api_key 29 | no | - | - | - | requires_api_key | live skip(키 유무 비검증, 보수적) |
| conservative 4 | no | - | - | - | conservative_gate | rate-limit/external signal — gate 필수 |
| disabled 7 | no | - | - | - | blocked/deferred | no bypass |

> live smoke 2/3 LIVE_SUCCESS(적재), gdelt는 일시적 rate-limit(정책상 정상). live_eligible 정책 유효(전부 실패 아님). community(hacker_news)는 enqueue되어도 decision의 confirmation_policy=unconfirmed 유지.

### 10.5 남은 coverage risk (Phase D 이후)

- **requires_api_key 29소스**: 키 존재 시 CORE_READY지만 live smoke 미수행(.env 비검증). 실제 운영 전 키 readiness 확인 필요(V-1).
- **google_trends_explore**: probe 미연결 → Phase D/별도 라운드에서 runner 연결 또는 registry 등록 결정.
- **개별 기사 분해**: 현재 source-level seed. article-level 후보화는 Phase D.

### Phase D 갱신 (2026-06-14)
- **API key readiness (D-0)**: requires_api_key 29 중 키 정의 보유 28개 → ready 23 / ambiguous(alias) 5 /
  missing 0 (사용자 .env 키 투입 확인). x(login wall)는 키 정의 없음. `api_readiness.py`가 `_SERVICE_CONFIGS`
  키 + `env_status`(alias 해석)로 판정, **키 값 비노출**.
- **live smoke (D-1)**: key-ready+public 44 소스 → 43 LIVE_SUCCESS / 1 RATE_LIMITED(gdelt). requires_api_key
  28개 전부 live 검증 완료(C-2의 "키 비검증" 리스크 해소). Playwright 4종만 이번 라운드 제외.
- **google_trends_explore**: 여전히 probe 미연결(readiness=unknown). registry 연결 또는 runner 등록은 후속.

### Phase D-P / E-0 Production Closure Audit (2026-06-14)

실제 on-disk artifact 49소스를 분해 감사한 결과(긍정편향 제거, live 호출 0):
- **분해의 진실**: artifact 존재 49/49이지만 candidate_total 4102 중 numeric_exempt 3633(binance 3600 등 시세 원소). 기사형 본문 `present=0/partial=0` — RSS 뉴스(yna/ap_news 등)는 title/url 100%지만 본문은 description뿐(snippet_only).
- **21/49 소스 0-candidate**: sec_edgar(중첩 `hits.hits`), hacker_news(id-list), opendart/kma/nyt/guardian/serper/naver_news_search 등. numeric_exempt(정상)와 **parser 미지원 실패**(`no_candidates_from_artifact`)를 risk_flag로 분리. 면제가 아니라 Phase E 소스별 파서 보강 대상.
- **role/purpose 라우팅 자체는 끊김 없음**: SourceProfile→StrategyDecision→readiness→seed→candidate→pre_gate 전 구간 연결 검증(test_pipeline_connectivity). 병목은 라우팅이 아니라 소스별 artifact 스키마 커버리지.

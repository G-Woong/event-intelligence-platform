# 01 — Target Architecture

> 2라운드 이후 목표 계층. Round 1에서는 `ingestion/` 루트 레벨 레이아웃(평면)만 확정.
> 여기서 정의한 계층 재배치는 Round 2 작업 범위.

## 1. 목표 디렉터리 구조 (Round 2 이후)

```
ingestion/
├── collectors/
│   ├── discovery/       DiscoveryCollector (entry URL fetch + URL 추출)
│   ├── enrichment/      SearchEnrichmentCollector (Naver/YouTube 검색 보강)
│   └── watchlist/       WatchlistCollector (구독형 소스 주기 폴링)
├── pipeline/
│   ├── event_candidate_extractor.py
│   ├── event_queue.py
│   ├── query_generator.py
│   └── canonical_event_builder.py
├── sources/
│   ├── news/            BBC, AP, TechCrunch, TheVerge, ZDNet, ETNews, YNA,
│   │                    Hankyung, Maekyung, AlJazeera, CNBC, Reuters
│   ├── community/       Reddit, HackerNews, ProductHunt, DCInside, FMKorea
│   ├── official/        OpenDart, SEC EDGAR, KRX KIND, BOK ECOS, EIA,
│   │                    FederalRegister, EUPressCorner, GDELT
│   ├── search/          NaverBlogSearch, NaverNewsSearch
│   ├── media/           YouTube
│   └── blocked/         X, Blind (login wall; BLOCKED 상태 유지)
├── agents/              LangGraph (현 위치 유지)
├── core/                공유 유틸리티 (현 위치 유지 + env_loader)
├── schemas/             Pydantic 모델 (현 위치 유지)
├── configs/             YAML 레지스트리 (Round 2: layered 재설계)
├── runners/             진입점 (현 위치 유지)
├── tests/
│   ├── unit/            env_loader, quality_score, error_taxonomy, schema
│   └── integration/     api_connectivity, source_smoke
├── tools/               추출/페칭 툴 (현 위치 유지 + check_env_hygiene)
└── outputs/             수집 산출물 (gitignored)
```

## 2. 30개 소스 → 레이어 매트릭스

| 소스 | Layer | 인증 | 비고 |
|---|---|---|---|
| BBC | fast_signal | none | RSS |
| AP News | fast_signal | none | RSS |
| TechCrunch | fast_signal | none | RSS |
| The Verge | fast_signal | none | RSS |
| ZDNet Korea | fast_signal | none | HTML |
| ETNews | fast_signal | none | HTML |
| YNA | fast_signal | none | RSS |
| Hankyung | fast_signal | none | RSS |
| Maekyung | fast_signal | none | RSS |
| AlJazeera | fast_signal | none | RSS |
| CNBC | fast_signal | none | RSS |
| Reuters | fast_signal | license_review | 라이선스 검토 필요 |
| Reddit | community_signal | none (public json) | POST 제외 |
| HackerNews | community_signal | none | Firebase API |
| ProductHunt | community_signal | bearer_token | PRODUCT_HUNT_API_KEY |
| YouTube | community_signal | api_key | YOUTUBE_API_KEY |
| DCInside | community_signal | none | HTML |
| FMKorea | community_signal | none | HTML |
| NaverBlogSearch | search_enrichment | header | NAVER_CLIENT_ID/SECRET |
| NaverNewsSearch | search_enrichment | header | NAVER_CLIENT_ID/SECRET |
| X (Twitter) | community_signal | login_wall | BLOCKED — Round 1 제외 |
| Blind | community_signal | login_wall | BLOCKED — Round 1 제외 |
| GDELT | official_evidence | none | JSON API |
| OpenDart | official_evidence | query_param | OPENDART_API_KEY |
| SEC EDGAR | official_evidence | none | 10 req/s limit |
| KRX KIND | official_evidence | playwright | Round 2 |
| BOK ECOS | official_evidence | query_param | BOK_ECOS_API_KEY |
| EIA | official_evidence | query_param | EIA_API_KEY |
| FederalRegister | official_evidence | none | Public API |
| EUPressCorner | official_evidence | none | Public HTML |

## 3. 신규 후보 소스 (Round 2+ 검토)

| 소스 | Layer | 근거 | evidence_level |
|---|---|---|---|
| Google Trending Now | fast_signal | 트렌드 지표; 비공식 API 존재 | low — UNKNOWN |
| Signal.bz | fast_signal | 한국 미디어 인기 기사 집계 | medium — 공식 API UNKNOWN |
| Loword | community_signal | 커뮤니티 집계 | low — robots.txt 확인 필요 |
| Coinbase/Binance market API | market_signal | 시장가 이벤트 트리거 | medium — API 있음 |

> 후보 소스 도입 전 ToS·robots.txt·라이선스 검토 필수.

## 4. Pipeline 6모듈 (Round 2 신규)

| 모듈 | 역할 |
|---|---|
| `DiscoveryCollector` | Entry URL fetch + candidate URL 추출 |
| `SearchEnrichmentCollector` | Naver/YouTube 검색 쿼리 실행 |
| `EventCandidateExtractor` | LLM 기반 이벤트 후보 추출 |
| `EventQueue` | Redis 기반 이벤트 큐 관리 |
| `QueryGenerator` | 소스 스펙 기반 검색 쿼리 생성 |
| `CanonicalEventBuilder` | 중복 제거 + 정규화된 이벤트 빌드 |

## 5. Layered source_registry.yaml 재설계 (Round 2)

Round 2에서 configs/source_registry.yaml에 다음 필드를 추가:

```yaml
sources:
  - id: bbc
    layer: fast_signal
    input_type: rss
    collection_methods: [httpx_direct]
    auth:
      type: none
    rate_limit_policy:
      requests_per_minute: 4
      respect_crawl_delay: true
```

현재 Round 1의 YAML 구조는 변경 없이 유지.

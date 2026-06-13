# Next Round TODO

> Round 2 우선순위 목록 (2026-06-03 기준).

## P0 — 즉시 필요

- [ ] **pipeline 6모듈 실제 로직 구현**
  - `EventCandidateExtractor`: LLM judge (ingestion/agents/llm_judge.py) 연결
  - `EventQueue`: Redis Stream 구현 (REDIS_URL 환경 변수 활용)
  - `DiscoveryCollector`: source registry 연결, raw artifact 저장 훅 구현
  - `QueryGenerator`: entity/title 기반 ko/en 쿼리 생성 로직
  - `CanonicalEventBuilder`: 클러스터링 + skeleton 생성

- [ ] **Phase 4 API 키 발급**
  - 우선순위: Serper, Tavily, Finnhub, KOBIS, TMDB (P1)
  - 그 다음: Exa, GNews, Guardian, KMA, TourAPI (P2)

- [ ] **sources/ 물리 이동 (안전망 확보 후)**
  - `test_source_map_imports.py` PASS 확인 후 진행
  - `git mv ingestion/sources/bbc.py ingestion/sources/news/bbc.py` 방식
  - `_SOURCE_MAP` dotted-path 동시 업데이트
  - re-export wrapper 전략: `ingestion/sources/news/__init__.py`에서 backward-compatible import

## P1 — 중요

- [ ] **Playwright 구현 (KRX KIND, EU Press Corner)**
  - robots.txt + ToS 확인 선행
  - CDP 세션 + 타임아웃 설정
  - Round 2 smoke test 추가

- [ ] **`--live` 실행 (사용자 승인 필요)**
  - Phase 1-3 no-key 소스부터 검증
  - API 키 있는 소스는 키 설정 후

- [ ] **search_enrichment 실제 연동**
  - Serper / Tavily 우선 구현
  - SearchEnrichmentCollector 로직 완성

- [ ] **market_signal dry-run 검증**
  - coinbase_market, binance_market: 공개 API이므로 바로 테스트 가능
  - Finnhub: 키 발급 후

## P2 — 다음 라운드

- [ ] **fast_signal external scrape 가능성 평가**
  - google_trending_now, signal_bz, loword
  - 공식 API 없음 → robots.txt 확인 + 스크레이핑 ToS 검토
  - 결과에 따라 ALLOWED/BLOCKED 재분류

- [ ] **domain_signal 순차 구현**
  - KOBIS 박스오피스 → TMDB → IGDB 순서 권장
  - 한국 공공데이터(KMA, TourAPI, ITS, KOPIS, CultureInfo) — data.go.kr 키 통합 관리

- [ ] **Reuters 라이선스 검토**
  - Thomson Reuters Connect API (유료) 또는 Refinitiv 데이터 피드 검토
  - 비용 확인 후 NEEDS_LICENSE → ALLOWED or EXCLUDED 최종 결정

- [ ] **Redis Stream EventQueue 연동**
  - Docker compose redis 서비스 활성화 확인
  - EventQueue._redis_enqueue/dequeue 구현

- [ ] **LangSmith 트레이싱 연결**
  - LLM judge 호출 시 LangSmith trace 자동 기록
  - LANGSMITH_API_KEY 설정 후 확인

# 06 — SEARCH API & WEB EXPLORATION LAYER (L2)

> 결론: event candidate 1건에서 관련 웹문서를 **검색 API로 확장**한다. 직접 전체 웹 크롤링이 아니다. 무료(GDELT/NewsData.io/Guardian/GNews) 우선 → 유료(Brave/Google CSE/SerpAPI) fallback의 **provider-agnostic tiered router**. 현재 이 layer는 **미구현**이다.

---

## 1. 현재 상태

- 검색 외부 확장 layer 부재(`search/expansion` 모듈 없음). ingestion은 소스에서 직접 수집만.
- 일부 검색 provider(serper/tavily/exa/newsapi)는 LIVE probe만 있고 파이프라인 미배선.

## 2. 목표 아키텍처

```text
event candidate ──> query formulation ──> [tiered router]
                                            ├─ 무료: GDELT, NewsData.io, Guardian, GNews, Google CSE(소량)
                                            └─ 유료 fallback: Brave(~$5/1k), SerpAPI(검증전용)
                    ──> NormalizedHit(title/url/ts/source/lang/snippet)
                    ──> dedup/canonical ──> corroboration ──> raw_events 보강
```

- **provider-agnostic 추상화** `SearchProvider.query(q, opts) -> NormalizedHits`. 2+ 구현체 동일 인터페이스.
- **tiered router**: 무료쿼터 우선소진 → 유료 fallback. per-event 호출 상한 + 월 예산 guard.
- **caching(TTL)** + dedup 후에만 유료 호출/임베딩.

## 3. 웹 리서치 근거 (2026-06)

| Provider | 비용/쿼터 | 비고 |
|---|---|---|
| Brave Search API | 무료티어 폐지(2026-02), ~$5/1k, LLM Context 엔드포인트 | 유료 fallback |
| Bing Web Search | **폐지(2025-08-11)** → Azure Grounding(40-483%↑) | **의존 금지** |
| Google CSE | 무료 소량 + 유료 | 보조 |
| SerpAPI | 종량(고단가) | 검증/감사 전용 |
| GDELT DOC 2.0 | 무료, rate-limited | 광역 1차 그물 |
| NewsData.io | 무료 200/day(상업가능), $199/mo | 1차 무료 뉴스 |
| NewsAPI.org | 무료=localhost, $449/mo | 상업 배포 시 제외 |
| GNews | 무료 100/day | 소량 보조 |
| Guardian | 무료 5000/day, 재배포금지 | 영문 보강(요약+링크) |
| Perigon | 유료, 1M articles/day | 고용량 후보(미채택 기본) |

## 4. 핵심 교훈 — 단일 provider = 단일 장애점

Bing 폐지·Brave 무료티어 폐지는 **단일 provider 의존이 곧 단일 장애점이자 가격협상력 0**임을 보여준다. 검색 layer는 다중 fallback + graceful degradation으로, 한 provider가 폐지·인상해도 동작해야 한다.

## 5. 비용 / 위험 / 법무

- 비용: 무료쿼터 우선, 유료는 event 트리거 시에만. 환율(USD), 단가 변동성 정기 갱신.
- 위험: rate-limit 위반 차단(백오프 준수), 과확장(noise 유입), LLM query gen 비용·환각 URL.
- 법무(L3/L11 연계): 검색 API ToS 준수, 스크래핑 금지, snippet 저작권(전문 재배포 금지), PII 필터.

## 6. 검증기준 (완전 달성)

tiered router(무료→유료)가 동작하고, candidate→query formulation→citation/source-diversity 확장→dedup→raw_events 적재까지 연결되며, per-event·월 예산 guard·rate-limit 백오프·ToS/저작권/PII 준수·provider health/circuit-breaker·corroboration 신뢰신호가 충족되고, ingestion deterministic 경로가 불변일 때.

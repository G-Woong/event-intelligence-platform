# 06 — SEARCH API & WEB EXPLORATION LAYER (L2)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 🔲 NOT_DONE — 스텁만. `query_generator`/`search_enrichment_collector` = `NotImplementedError`, `expansion_router` 부재(provider 6종 레지스트리 선언만).
> │ **구현순위:** #11 (00_ROADMAP_INDEX) · **그룹:** C
> │ **검증 근거:** `search/expansion` 모듈 부재(grep 0). provider(serper/tavily/exa/newsapi 등)는 LIVE probe·레지스트리 선언만 있고 파이프라인 미배선. 정밀 근거는 `_CANONICAL/04`(OPEN_TASKS).
> │ **잔여(미구현):** ① `expansion_router.py`(tier1 무료→tier2 유료 라우팅) ② per-event/월 budget guard ③ fallback chain ④ Change Detection skip(seen_content_hash) 결합 ⑤ candidate→tiered→raw_events E2E.
> │ **완료정의(DoD = S5):** off시 1517 green · candidate→tiered→raw_events E2E 1건 · 예산초과 graceful degradation · POLICY 차단 입증 · audit trace · 우회/rate위반 0.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> 결론: event candidate 1건에서 관련 웹문서를 **검색 API로 확장**한다. 직접 전체 웹 크롤링이 아니다. 무료(GDELT/NewsData.io/Guardian/GNews) 우선 → 유료(Brave/Google CSE/SerpAPI) fallback의 **provider-agnostic tiered router**. 현재 이 layer는 **미구현**(스텁만)이다. **착수 시점 = S5**(게이트층이 이미 존재해 가장 저렴·조기 착수, `00_ROADMAP_INDEX §4`).

---

## 1. 현재 상태

- 검색 외부 확장 layer 부재(`search/expansion` 모듈 없음). ingestion은 소스에서 직접 수집만.
- 일부 검색 provider(serper/tavily/exa/newsapi)는 LIVE probe만 있고 파이프라인 미배선.

## 2. 목표 아키텍처 — P/G/F + 게이트층 (ADR#14)

검색 확장은 ADR#14의 **P/G/F 3층 경계** 위에 올린다. LLM은 *무엇을·어디서*(쿼리·provider 선택 계획)만 관여하고, 게이트와 fetch는 결정론이다.

```text
event candidate
  │
  ▼ [Change Detection skip]  ── seen_content_hash 일치 → SKIP verdict (확장 자체를 건너뜀, 비용 0)
  │
  ▼ LAYER P (Planning, LLM 관여·비결정 허용)
  │    query_generator.generate()  ── 확장쿼리 생성(환각 URL 금지·근거 기반)
  │
  ▼ LAYER G (Gate, 결정론 검문)  ── expansion_router.py
  │    ① POLICY 게이트: allowlist provider만 · ToS/robots 사전판정
  │    ② budget guard (per-event 호출 상한 + 월 예산) ── 초과 시 graceful degradation(중단 아닌 축소)
  │    ③ tier 선택: tier1 무료 우선소진 → tier2 유료 fallback
  │
  ▼ LAYER F (Fetch, 결정론 실행·LLM 미관여)
  │    [tiered router]
  │      tier1 무료: google_programmable_search(Google CSE 소량), GDELT, NewsData.io, Guardian, GNews
  │      tier2 유료 fallback: tavily, exa, serper, Brave(~$5/1k)   ── SerpAPI는 검증/감사 전용
  │
  ▼ NormalizedHit(title/url/ts/source/lang/snippet)
  ▼ dedup/canonical ──> corroboration ──> raw_events 보강 (Event append 재유입은 12로 라우팅)
```

- **provider-agnostic 추상화** `SearchProvider.query(q, opts) -> NormalizedHits`. 2+ 구현체 동일 인터페이스.
- **신규 `expansion_router.py`**: **tier1 무료(`google_programmable_search`) → tier2 유료(`tavily`/`exa`/`serper`)** fallback chain. 무료쿼터 우선소진 후에만 유료로 강등.
- **per-event/월 budget guard 승격**: 단순 "상한"이 아니라 **LAYER G의 1급 게이트**다 — 초과 시 예외 전파가 아니라 **graceful degradation**(유료 tier skip·축소)으로 결정론적 강등. budget 초과가 파이프라인을 죽이지 않는다.
- **fallback chain 명시**: 한 provider 실패/폐지/쿼터소진 시 다음 tier로 결정론적 강등 → 단일 provider = 단일 장애점 회피(§4).
- **Change Detection skip 결합**: `seen_content_hash`(ETag/Last-Modified/norm_hash) 일치 시 확장 자체를 SKIP(비용 0). 비용 지렛대를 라우터 *앞단*에 두어 S2~S6 폭주 방지(`00_ROADMAP_INDEX §4` S1.5).
- **caching(TTL)** + dedup 후에만 유료 호출/임베딩.
- **불변:** 모든 tier에서 우회·rate위반·proxy·RPC 스크래핑 0. provider ToS·snippet 저작권(전문 재배포 금지) 준수.

## 3. 웹 리서치 근거 (2026-06)

| Provider | 비용/쿼터 | tier / 레지스트리 정합 |
|---|---|---|
| google_programmable_search (Google CSE) | 무료 소량 + 유료 | **tier1 무료(라우터 1순위)** |
| GDELT DOC 2.0 | 무료, rate-limited | tier1 무료 — 광역 1차 그물 |
| NewsData.io | 무료 200/day(상업가능), $199/mo | tier1 무료 — 1차 무료 뉴스 |
| GNews | 무료 100/day | tier1 무료 — 소량 보조 |
| Guardian | 무료 5000/day, 재배포금지 | tier1 무료 — 영문 보강(요약+링크) |
| tavily | 종량 | **tier2 유료 fallback** (레지스트리 6종) |
| exa | 종량 | **tier2 유료 fallback** (레지스트리 6종) |
| serper | 종량 | **tier2 유료 fallback** (레지스트리 6종) |
| Brave Search API | 무료티어 폐지(2026-02), ~$5/1k, LLM Context 엔드포인트 | tier2 유료 fallback |
| SerpAPI | 종량(고단가) | 검증/감사 전용(파이프라인 비채택) |
| NewsAPI.org | 무료=localhost, $449/mo | 상업 배포 시 제외 |
| Bing Web Search | **폐지(2025-08-11)** → Azure Grounding(40-483%↑) | **의존 금지** |
| Perigon | 유료, 1M articles/day | 고용량 후보(미채택 기본) |

> **레지스트리 정합:** `expansion_router.py`의 tier2 유료 후보(`tavily`/`exa`/`serper`)는 ingestion provider 레지스트리 6종(serper/tavily/exa/newsapi 등 — LIVE probe만, 미배선)과 동일 식별자를 쓴다. 표의 tier 컬럼이 §2 라우터 흐름과 1:1 정합한다. provider 폐지/인상 시 이 표를 갱신하고 라우터 tier만 조정하면 코드 변경 없이 강등된다.

## 4. 핵심 교훈 — 단일 provider = 단일 장애점

Bing 폐지·Brave 무료티어 폐지는 **단일 provider 의존이 곧 단일 장애점이자 가격협상력 0**임을 보여준다. 검색 layer는 다중 fallback + graceful degradation으로, 한 provider가 폐지·인상해도 동작해야 한다.

## 5. 비용 / 위험 / 법무

- 비용: 무료쿼터 우선, 유료는 event 트리거 시에만. 환율(USD), 단가 변동성 정기 갱신.
- 위험: rate-limit 위반 차단(백오프 준수), 과확장(noise 유입), LLM query gen 비용·환각 URL.
- 법무(L3/L11 연계): 검색 API ToS 준수, 스크래핑 금지, snippet 저작권(전문 재배포 금지), PII 필터.

## 6. 검증기준 (S5 DoD)

S5 완료정의(DoD)는 다음을 모두 충족할 때다:

1. **off시 1517 green** — expansion layer 비활성(`LLM_PROVIDER=""` 등 off) 시 기존 1,517 테스트 무영향(비파괴).
2. **candidate → tiered → raw_events E2E** — event candidate 1건이 query 생성 → tier1 무료 우선 → (필요 시) tier2 유료 fallback → dedup/canonical → corroboration → raw_events 적재까지 1건 연결.
3. **예산초과 graceful** — per-event/월 budget guard 초과 시 예외 전파 0, graceful degradation(유료 tier skip·축소)으로 결정론 강등.
4. **POLICY 차단 입증** — allowlist 밖 provider·우회 전략 제안은 LAYER G에서 reject(차단 입증).
5. **audit trace** — 제안·채택·거부·tier 선택·budget 판정이 구조화 audit로 기록(R-LLMCollectBoundary 완화).

부가: rate-limit 백오프·ToS/저작권(전문 재배포 금지)/PII 준수·provider health/circuit-breaker·corroboration 신뢰신호·ingestion deterministic 경로 불변.

## 7. 고도화 (팀 인사이트 반영)

- **orchestrator #1 — Change Detection을 stage별 cost-gate로:** §2의 Change Detection skip은 라우터 1회가 아니라 *stage별* cost-gate로 일반화한다(query 생성 전·tier 호출 전 각각). seen_content_hash로 비용 발생 지점마다 조기 차단 → S2~S6 비용 폭주 방지.
- **orchestrator #4 — S1.5 read-only 동시착수가 seen_hash skip 인프라 선행:** Change Detection(S1.5, read-only ETag/Last-Modified/norm_hash→SKIP)을 S5보다 *먼저/동시* 착수해야 한다 — seen_hash skip 인프라가 expansion router의 비용 게이트 선행조건이기 때문(`00_ROADMAP_INDEX §4`).
- **adversarial #6 — generate_batch fail-all 격리:** `query_generator`의 batch 생성이 1후보 실패로 전체 확장을 중단(fail-all)하면 안 된다 → **후보단위 폴백 격리**(1후보 실패는 그 후보만 skip, 나머지 진행). 위험 추적 = **R-ExpansionPartialFailure**.

---

## 관련 문서 (링크)

- `_RISK/RISK_REGISTER.md` — **R-LLMCollectBoundary**(LLM 수집 라우팅/확장쿼리 우회·rate위반·비용폭주)·**R-ExpansionPartialFailure**(batch fail-all)·R-PromptInjection.
- `2_ROADMAP/11_LLM_SOURCE_SUPERVISOR_AND_JUDGE_LAYER.md` — P/G/F 경계·judge/supervisor 분리·`google_trends_explore` PASS 금지.
- `2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md` — LLM Expansion Router 의사코드·단계 S5(NET-NEW, `00_ROADMAP_INDEX` 순위 17).
- `2_ROADMAP/12_EVENT_CLUSTERING_RANKING_AND_DEDUP_LAYER.md` — raw_events 보강 후 **Event append 재유입**(카드 dedup 아닌 timeline append).
- `_DECISIONS/2026-06.md` — ADR#14(P/G/F 수집경계).

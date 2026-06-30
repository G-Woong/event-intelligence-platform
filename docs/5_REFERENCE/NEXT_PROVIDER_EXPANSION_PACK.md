# NEXT_PROVIDER_EXPANSION_PACK (ADR#93)

> Status: **PLANNING-ONLY/PROVIDER CARDS · GDELT 실행 0 · RUNTIME No-Go**. no-yield 사유별로 *다음에 추가/교정할*
> provider 를 권고하는 카드 덱(계획일 뿐 runtime 확장은 별도 ADR + explicit approval). 코드:
> `backend/app/tools/next_provider_expansion_pack.py` (network 0·`runtime_enabled=False`).

## 0. 목적

bounded live 가 수율 0 일 때 taxonomy 는 *왜* 0 인지 분류하지만(`live_no_yield_taxonomy`), "그래서 다음에 어느
provider 를 어떤 risk 로 추가/교정하나" 의 per-provider 카드가 없었다. 이 모듈은 upstream `news_breadth_trigger` 를
**인용**(=`_classify` 재구현 0)해 taxonomy 키로 headline provider + provider 카드를 risk 필드와 함께 낸다.

## 1. 진입점

```
build_next_provider_expansion_pack(*, no_yield_reason=None, news_records_count=0,
                                   official_records_count=0, in_window_news_count=0) -> dict
보조: sanitized_next_provider_expansion_pack(out)
     main(--reason / --news-records / --official-records / --in-window-news / --json)
```

## 2. 상태 vocab (`next_provider_expansion_status`)

```
NPE_NEWS_BREADTH   = "recommend_news_breadth_provider"
NPE_PROVIDER_DATE  = "recommend_provider_or_date_strategy"
NPE_OFFICIAL_FIRST = "recommend_official_side_fix_first"
NPE_OVERLAP_REFINE = "recommend_overlap_refinement_no_new_provider"
NPE_NOT_TRIGGERED  = "no_expansion_recommended"
```

friendly→TX 해소: `"freeze_unsafe"`→`TX_FREEZE_UNSAFE`("bridge_candidate_found_but_freeze_unsafe", 유일 별칭) ·
`news_no_records`/`no_in_window_news`/`official_no_records` 는 TX 값과 동일 · 미지/None → `TX_NOT_RUN`(fail-closed).

## 3. 핵심 출력 필드

```
next_provider_expansion_status · resolved_taxonomy_key · recommended_provider · why_recommended
source_role · date_filter_capability · credential_requirement(secret-safe) · rate_limit_risk
attribution_risk · canonical_url_risk · body_availability_risk · implementation_cost
next_adr_candidate · ko_lane_recommendation(EN 과 분리) · provider_cards
```

- `provider_cards` = gdelt / ap_reuters_like / official_agency_pr / sec_edgar / federal_register.

## 4. 불변식 (절대 금지)

```
runtime_enabled=False · gdelt_executed=False · network_invoked=False
aggregator_truth=False · ko_lane_separate=True · secret_values_exposed=False
```

- risk fact 는 `window_honoring_source_readiness`/`provider_breadth_inventory` 인용(재선언 0) — AP·Reuters-like /
  official-agency PR 만 inline 신규.

## 5. 합성하는 기존 모듈

- `live_no_yield_taxonomy` (`TX_*` canonical 키·friendly 별칭 해소)
- `window_honoring_source_readiness` (provider role/date/rate/attribution 행)
- `provider_breadth_inventory` (credential/canonical_url/body risk 행)

## 6. 이것이 아니다

- runtime expansion 이 **아니다** · GDELT 실행이 아니다.
- aggregator ≠ truth · KO floor(0/50) 해결이 아니다(별도 행만 권고).
- counts 는 입력 echo 일 뿐 권고를 재분류하지 않는다.

Status: ADR#93 · runtime 0

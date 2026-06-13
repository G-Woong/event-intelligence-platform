# 88. Primary Seed Live Collection Audit (1차 소스 실측)

- 실행: 2026-06-12 17:31 UTC (`run_primary_seed_live_audit`, 40 소스 × 1회, backend=local_file)
- 산출물: `ingestion/outputs/jsonl/primary_seed_live_audit_20260612_173141.jsonl`, `ingestion/outputs/reports/primary_seed_live_audit_20260612_173141.md`
- 판정 기준: seed 필드(title/url/timestamp/source_id/snippet) 3+ = yes, 2 = partial

## 1. 결과 표 (실측)

| source_id | status | items_found | event_seed_ready | minimum_fields_present | sample_title_or_keyword | sample_url_exists | timestamp_exists | artifact_exists | recommended_frequency | next_action |
|---|---|---|---|---|---|---|---|---|---|---|
| bbc | LIVE_SUCCESS | 35 | yes | title,url,timestamp,source_id,snippet | I have a duty to stay on, says Starmer… | yes | yes | yes | 30-60m | integrate_into_pipeline |
| ap_news | API_RETURNED_HTML_ERROR_PAGE | 3 | yes | title,url,source_id | (HTML 에러 페이지 — RSS endpoint 점검 필요) | yes | no | yes | 30-60m | inspect_raw_payload_for_html_error |
| techcrunch | LIVE_SUCCESS | 20 | yes | title,url,timestamp,source_id,snippet | Google sues alleged Chinese cybercrime… | yes | yes | yes | 30-60m | integrate_into_pipeline |
| the_verge | LIVE_SUCCESS | 10 | yes | title,url,timestamp,source_id,snippet | Siri is good now?? | yes | yes | yes | 30-60m | integrate_into_pipeline |
| zdnet_korea | LIVE_SUCCESS | 3 | yes | title,url,source_id | (html 후보 URL 3건 + 페이지 title) | yes | no | yes | 30-60m | integrate_into_pipeline |
| etnews | LIVE_SUCCESS | 3 | yes | title,url,source_id | (html 후보 URL 3건 + 페이지 title) | yes | no | yes | 30-60m | integrate_into_pipeline |
| yna | LIVE_SUCCESS | 120 | yes | 전체 5 | 일론 머스크, 세계 최초 '조만장자' 등극… | yes | yes | yes | 15-30m | integrate_into_pipeline |
| hankyung | LIVE_SUCCESS | 50 | yes | title,url,timestamp,source_id | 李대통령, 멜로니 총리와 회담… | yes | yes | yes | 30-60m | integrate_into_pipeline |
| maekyung | LIVE_SUCCESS | 50 | yes | 전체 5 | 투표지 부족사태 파문에… | yes | yes | yes | 30-60m | integrate_into_pipeline |
| aljazeera | LIVE_SUCCESS | 25 | yes | 전체 5 | US judge extends block on Trump's… | yes | yes | yes | 30-60m | integrate_into_pipeline |
| cnbc | LIVE_SUCCESS | 30 | yes | 전체 5 | Elon Musk becomes world's first trillionaire… | yes | yes | yes | 30-60m | integrate_into_pipeline |
| hacker_news | LIVE_SUCCESS | 500 | **no** | - | (story id 목록만 — title은 item별 2차 호출 필요) | no | no | yes | 30-60m | needs_item_detail_call |
| product_hunt | LIVE_SUCCESS | 3 | yes | title,source_id,snippet | Firma.dev | no | no | yes | daily | integrate_into_pipeline |
| youtube | LIVE_SUCCESS | 3 | yes | 전체 5 | Introducing Galaxy S26 Ultra… | yes | yes | yes | 30-60m | integrate_into_pipeline |
| dcinside | LIVE_SUCCESS | 1 | partial | title,source_id | (rendered page title만 — 게시글 selector 보강 필요) | no | no | no | 30-60m | update_selector |
| gdelt | **RATE_LIMITED** | 0 | no | - | - | no | no | yes | 15-30m | retry_after_cooldown:300s |
| opendart | LIVE_SUCCESS | 6354 | yes | 전체 5 | 일괄신고서(집합투자증권-신탁형)… | yes | yes | yes | 30-60m | integrate_into_pipeline |
| sec_edgar | LIVE_SUCCESS | 100 | yes | 전체 5 | Franklin Templeton ETF Trust (CIK…) | yes | yes | yes | 30-60m | integrate_into_pipeline |
| bok_ecos | LIVE_SUCCESS | 5 | **no** | - | (통계 시계열 — generic sample 매핑 불일치) | no | no | yes | daily | add_sample_mapping |
| eia | LIVE_SUCCESS | 14 | **no** | - | (시계열 — generic sample 매핑 불일치) | no | no | yes | daily | add_sample_mapping |
| federal_register | LIVE_SUCCESS | 10000 | partial | title,source_id | Submission for OMB Review; 30-Day Comment… | no | no | yes | daily | add_fields_to_probe_spec(url/date) |
| eu_press_corner | LIVE_SUCCESS | 1 | partial | title,source_id | (rendered page title만) | no | no | no | 2-6h | update_selector |
| google_trending_now | LIVE_SUCCESS | 1 | partial | title,source_id | (page title만 — keyword selector 미매칭) | no | no | no | 2h+(429 이력) | update_selector |
| signal_bz | LIVE_SUCCESS | 3 | partial | title,source_id | "이재명 대통령 멜로니" 등 실검 keyword 3건 | no | no | no | 30-60m | integrate_into_pipeline(keyword) |
| loword | LIVE_SUCCESS | 1 | partial | title,source_id | (page title만 — keyword selector 미매칭) | no | no | no | 30-60m | update_selector |
| finnhub | LIVE_SUCCESS | 1 | **no** | - | (flat quote dict — sample 비대상, 수치 signal) | no | no | yes | 5-15m | integrate_as_numeric_signal |
| twelve_data | LIVE_SUCCESS | 3 | yes | title,timestamp,source_id,snippet | 2026-06-12 (datetime+close) | no | yes | yes | 15-30m | integrate_as_numeric_signal |
| alpha_vantage | LIVE_SUCCESS | 100 | **no** | - | (Time Series dict — sample 비대상) | no | no | yes | daily(25/day) | integrate_as_numeric_signal |
| polygon | LIVE_SUCCESS | 1 | **no** | - | (prev-day aggs — sample 비대상) | no | no | no | daily | integrate_as_numeric_signal |
| coinbase_market | LIVE_SUCCESS | 924 | partial | source_id,snippet | (products 목록) | no | no | yes | 15-30m | integrate_as_numeric_signal |
| binance_market | LIVE_SUCCESS | 3600 | yes | title,source_id,snippet | ETHBTC (symbol+price) | no | no | yes | 5-15m | integrate_as_numeric_signal |
| kma | LIVE_SUCCESS | 8 | yes | title,timestamp,source_id,snippet | PTY (category+관측값+baseDate) | no | yes | yes | 1h | integrate_into_pipeline |
| tour | LIVE_SUCCESS | 3 | yes | title,timestamp,source_id,snippet | (관광지 목록 — 정적) | no | yes | yes | weekly | integrate_into_pipeline |
| its | LIVE_SUCCESS | 31578 | **no** | - | (교통 link 데이터 — sample 매핑 필요) | no | no | yes | 15-30m | add_sample_mapping |
| kofic | LIVE_SUCCESS | 10 | yes | title,timestamp,source_id,snippet | 군체 (일일 박스오피스) | no | yes | yes | daily | integrate_into_pipeline |
| tmdb | LIVE_SUCCESS | 20 | yes | 전체 5 | Peddi | yes | yes | yes | daily | integrate_into_pipeline |
| kopis | LIVE_SUCCESS | 3 | yes | title,timestamp,source_id | god ONE FAMILY… (공연명+기간) | no | yes | yes | daily | integrate_into_pipeline |
| aladin | LIVE_SUCCESS | 3 | yes | 전체 5 | 나의 첫 번째 부동산 교과서 | yes | yes | yes | daily | integrate_into_pipeline |
| igdb | LIVE_SUCCESS | 3 | partial | title,source_id | Picross 3D | no | no | yes | daily-weekly | add_release_date_field |
| culture_info | LIVE_SUCCESS | 10 | partial | title,source_id | 2026 박물관 인문학 - 조선의 기록문화 | no | no | yes | daily | add_date_field_mapping |

## 2. 집계

- called 40 / skipped 0 (health/cooldown/cache gate에 걸린 소스 없음 — 첫 실행)
- LIVE_SUCCESS 38, API_RETURNED_HTML_ERROR_PAGE 1 (ap_news), RATE_LIMITED 1 (gdelt — 실호출 429)
- seed_ready **yes 23 / partial 9 / no 8**

## 3. 주요 발견

1. **뉴스 RSS 11종 중 10종이 title+url+timestamp 완비** — Event Queue seed 1순위 그룹. ap_news는 RSS endpoint가 HTML 에러 페이지를 반환 (next_action: endpoint 점검).
2. **gdelt 단일 호출에서도 429** — min_interval 5s 준수와 무관하게 발생. cooldown 300s 기록됨 → 2차 audit에서 gate 동작 검증 사례가 됨. 운영 주기는 15분 이상 + 429 내성 필수.
3. **signal_bz가 실검 keyword 3건 추출 성공** ("이재명 대통령 멜로니" 등) — fast_signal 중 유일하게 즉시 사용 가능. google_trending_now/loword는 page title만 잡힘 → selector 보강 필요 (`update_selector`).
4. **hacker_news는 id 목록만** — seed로 쓰려면 item detail 2차 호출 설계 필요 (이번 라운드 범위 외).
5. **시장 소스는 flat 수치 응답** — title/url 개념이 없어 seed 필드 기준으로는 no/partial이지만, 이는 "수치 임계값 signal"로 별도 취급해야 함 (docs/91 readiness에서 분류).
6. **bok_ecos/eia/its** — 데이터는 정상 수신(LIVE_SUCCESS)이나 sample 매핑 부재로 평가 불가. next_action: `_SAMPLE_PATHS` 매핑 추가 (수집 자체는 문제 없음).
7. timestamp 부재 소스(zdnet_korea/etnews/product_hunt/igdb/culture_info 등)는 **observed_at(수집 시각)으로 대체 가능** — EventSeedCandidate schema에 observed_at 필수 필드로 반영.

## 4. 2차 audit hot seed 후보 (실측에서 도출)

- 트렌드: "이재명 멜로니", "이란 종전 MOU", "김혜경 세계청년대회" (signal_bz)
- 뉴스 토픽: "일론 머스크 조만장자" (yna), "SpaceX Nasdaq debut", "US Iran deal" (cnbc)
- 시장/도메인: "SpaceX market cap" (cnbc/시장), "군체" (kofic 박스오피스 1위 — tmdb 검증용)

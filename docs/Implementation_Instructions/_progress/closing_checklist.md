# Closing Checklist — 2026-06-13 (최종: PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1)

> **최종 상태(2026-06-13)**: 15 checklist 전부 종결 — **PASS 14 / google_trends_explore CONFIRMED_EXTERNAL_RATE_LIMIT 1**.
> gdelt PASS(승격), trends fallback chain PASS, runner orchestration **13/13 agent_ready**, 전체 pytest 통과, **secret scan verdict=PASS(WARNING 0)**.
> 아래 표·iter 섹션은 누적 기록(historical)이며 "PENDING / 이후 턴 / WARNING 오탐" 류 문구는 **해당 iter 시점 기준**이다(현재 상태는 본 헤더와 맨 끝 최종 섹션 기준).

| # | 항목 | 상태 | iter | 가설/원인 | 증거(명령/출력/경로) | 종결 시각 |
|---|------|------|------|----------|---------------------|----------|
| 1 | RISK-T04 Route1 429 | PASS | 1 | Route 1 `run_api_live_probe`가 429에서 `record_rate_limited` 미호출 + `next_retry_at` 미설정 | `pytest test_route1_rate_limit_record.py` 5 passed; **live 영속 증거**: source_health.json gdelt `next_retry_at=2026-06-13T04:29:46Z`(=last_checked 04:14:46Z+900s, 현재 04:21:30Z보다 미래) state=RATE_LIMITED_COOLDOWN — apply_probe_outcome(source_health.py:139)가 probe_result.next_retry_at을 재계산 없이 그대로 저장하므로 ProbeResult.next_retry_at이 non-None이었음을 입증 | 2026-06-13 |
| 2 | gdelt | **PASS** (live collected) | 1 | 다단어 query 따옴표 없이 전송 시 GDELT가 오류 텍스트를 200으로 응답; 단발 429는 공유 IP rate limit (raw payload 실측: "Please limit requests to one every 5 seconds...") | **docs/10 PHASE 3 재검증**: gate 통과 후 live 1회 → **LIVE_SUCCESS, items=3 실기사**(aif.ru/crisisgroup.org/naslovi.net), candidates 3, body_extracted=1(676자, httpx_trafilatura). raw `outputs/raw_payload/gdelt/20260613_184729...json`. min_interval(60s) 준수 시 수집 가능 입증(빠른 연속 호출만 soft-429). evidence JSONL `external_rate_limit_recheck_*`. policy 근거 docs/ingestion/rate_limit_evidence.md. `pytest test_gdelt_stabilization.py` 6 passed | 2026-06-13 |
| 3 | ap_news | PASS | 1 | H1(endpoint 폐기): `?format=feed&type=rss`가 무시되고 AP 홈 HTML 응답 — 브라우저 UA로도 동일 HTML이라 H2(UA 차단) 기각. rsshub는 Cloudflare 403. | 채택=§4-B Google News RSS 프록시. `run_collection_probe --source ap_news --json` → **LIVE_SUCCESS, items_found=100**, sample title="Anthropic ... offline to comply with export controls - AP News", url=news.google.com redirect. raw: `outputs/raw_payload/ap_news/20260613_133804_...xml`. `pytest test_ap_news_recovery.py` 3 passed. **함정**: query를 endpoint에 박으면 httpx가 빈 params로 query string을 덮어써 404 → q/hl/gl/ceid를 `_PROBE_SPEC.extra_params`로 이동. | 2026-06-13 |
| 4 | newsapi | PASS | 1 | top-headlines+q는 헤드라인 풀 한정이라 임의 phrase 0건(구조적 부적합) | 채택=`/v2/everything` 전환(country 제거, 기본 q="news"). `run_collection_probe --source newsapi --query "AI semiconductor" --json` → **LIVE_SUCCESS, items_found=3**, 전부 고관련(Sigurd chip/Marvell semiconductor/China AI). extracted: `outputs/extracted_payload/newsapi/20260613_133816_...json`. NEWSAPI_API_KEY 존재(len 32, 값 비노출). `pytest test_newsapi_everything.py` 3 passed. | 2026-06-13 |
| 5 | google_trends_explore | **CONFIRMED_EXTERNAL_RATE_LIMIT** (optional_enrichment + **fallback chain으로 비차단**, PHASE 2) | 4 | Google IP rate limit 지속(코드/selector 문제 아님). CAPTCHA/로그인/동의 없음 → BLOCKED_TERMINAL 아님. backend 영속 결함은 CLOSED. selector 유효성은 정상 DOM 부재로 판정 불가(미검증). **docs/10 PHASE 4 재검증**: live 1회 → rendered DOM = Google 정품 `<title>Error 429 (Too Many Requests)!!1</title>` + `images/errors/robot.png`(1730 bytes) → **진짜 provider 429 확정**(selector miss 아님). screenshot+rendered_dom 디스크 존재, next_retry `2026-06-13T10:49:28Z`(local_file 영속). 검색 근거: pytrends 공식 quota 부재·429 빈발·Retry-After 부재(docs/ingestion/rate_limit_evidence.md). evidence JSONL `external_rate_limit_recheck_*` | **iter2(이번 턴)**: gate 선확인 → cooldown 활성(현재 05:51:39Z < next_retry 06:32:08Z, ~40분 잔여) → **live 미수행**(gate 미통과, 의도된 보호 동작). selector 유효성: 저장된 google_trends_explore artifact 25개 전수 검사 결과 **전부 rate-limit 페이지**(robot.png "Error 429" 5개 + 32바이트 `<html>rate limit exceeded</html>` 19개) → 위젯 담긴 정상 DOM 0개 → selector(`.fe-related-queries-item` 등) 판정 불가 = **미검증**(429 페이지로 selector 실패 오판 금지). **backend warning CLOSED**: standalone 경로에 `_select_rate_limit_backend`+CLI `--rate-limit-backend local_file` 추가(playwright_probe.py, 기존 API 불변). `test_trends_explore_backend_policy.py` 5 passed(local_file 영속 across-restart / memory 미영속=기대값 / CLI가 probe 전 backend 강제). **재개 조건**: 06:32:08Z UTC 윈도우 이후 `python -m ingestion.probes.playwright_probe --site google_trends_explore --query <hot seed> --region KR --rate-limit-backend local_file` 1회. iter1 증거: JSONL `next_retry_at=2026-06-13T06:32:08Z, cooldown 3600s`. 연속 재시도 금지(max_retries_on_429=0) | 2026-06-13(외부 rate limit 이월) |
| 6a | loword selector | PASS | 1 | Route 2가 site spec wait/selector 힌트를 버리는 구조 결함(selector 자체는 유효). styled-components 해시 클래스라 fragile이나 현재 매칭 | run_playwright_probe 위임 후 items=20 실데이터(실검 키워드: 동성애 퀴어축제 반대/이정후 연속 안타 중단...). JSONL `...085151` loword 행 | 2026-06-13 |
| 6b | google_trending_now selector | PASS | 1 | 동일 Route 2 구조 결함(selector 유효) | items=20 실데이터(트렌드: 최불암/한화 대 키움...). JSONL `...085151` | 2026-06-13 |
| 6c | dcinside selector+본문 | PASS | 2 | 목록 selector 유효(Route2 결함). 검색 페이지 DOM 상이→explorer로 `a.tit_txt` 도출. 본문은 readability가 "자동 짤방" boilerplate 오선택→`.write_div` site selector로 해결 | 검색 items=20 + 본문 2건 site_selector(203/410자 실게시글). JSONL `...085151` | 2026-06-13 |
| 6d | eu_press_corner selector | PASS | 1 | SPA — Route 2가 wait 4000ms+wait_for 버려서 렌더 전 DOM에서 page title만 추출. 위임으로 해결 | items=20 실데이터(보도자료 제목+`detail/en/ip_26_*` URL). JSONL `...085151` | 2026-06-13 |
| 7 | signal_bz 보강 | PASS | 1 | keyword 3→10, rank 필드 부재 | items=10 + rank 1~10(`_extract_list_items` enumerate). JSONL `...085151` | 2026-06-13 |
| 8 | dcinside 검색 영구 path | PASS | 1 | 검색 URL 진입 경로 부재 | `search_url`=search.dcinside.com/combine/q/{query} → `a.tit_txt`→board/view detail→`.write_div` 본문. e2e 1회 성공(query "삼성전자") | 2026-06-13 |
| 9 | federal_register fields | PASS | 1 | fields[]=title만 요청해 url/date 부재 | fields[]→[title,html_url,publication_date,abstract,document_number] list. live LIVE_SUCCESS items=10000, sample url+publication_date 존재, seed=yes, body_extracted=1. JSONL `api_partial...092502`. `test_api_source_field_fixes.py` | 2026-06-13 |
| 10a | igdb 날짜/url | PASS | 1 | apicalypse가 url 미요청 + $root 배열 미매핑 + epoch 미변환 | apicalypse_body에 url 추가 + _SAMPLE_PATHS igdb($root) + epoch→ISO. live items=3, sample url=igdb.com/games/* + date 2009-03-03, seed=yes | 2026-06-13 |
| 10b | culture_info 날짜 | PASS | 1 | 구 artifact는 Service Error(과거 param). XML 필드명 RSS 표준과 상이 | _XML_FIELD_NAMES[culture_info] 추가. live LIVE_SUCCESS items=10, title+startDate+realmName 추출, seed=yes (key는 CULTURE_INFO_KEY alias로 resolve) | 2026-06-13 |
| 11 | hacker_news detail | PASS | 1 | topstories.json은 정수 id 배열만 — detail 2차 호출 부재 | detail_endpoint_template + api_probe 후처리(/v0/item/{id}.json ≤3) + collect_samples extracted fallback. live items=3, title+url+time(epoch), seed=yes, body_extracted=1 | 2026-06-13 |
| 12 | bok_ecos/eia/its 샘플 매핑 | PASS | 1 | _SAMPLE_PATHS 부재로 평가 불가 | _SAMPLE_PATHS bok_ecos(StatisticTableList.row)/eia(response.routes)/its(body.items). live signal_ready(items 5/14/31582). artifact 단위 테스트 3건 | 2026-06-13 |
| 13 | 시장 numeric_signal 분류 | PASS | 1 | seed 5필드 체계로 수치형은 영원히 no(분류 오류) | NUMERIC_SIGNAL_SOURCES + seed_ready_label_for(items_found>0=signal_ready). finnhub flat quote도 _evaluate_seed가 probe items_found 사용→signal_ready. live finnhub=signal_ready | 2026-06-13 |
| 14 | 장문 query 절단 | PASS | 1 | opendart 공시명 장문이 그대로 query로 전달되어 0건 | `pytest test_gdelt_stabilization.py::test_truncate_query` 통과; `_audit_common.truncate_query` | 2026-06-13 |
| 15 | 의존성/기법 흡수 | PASS | 2 | 09 §1 의존성(선행)+ §2 즉시 기법 흡수 | **09 §1 DONE**: `check_dependency_readiness.py` 14 READY/0 MISSING. **§2 즉시 기법**: 기법2·3 `feed_discovery.py`(discover_feeds/validate_feed/google_news_proxy_url/discover_sitemaps), 기법4 url_resolver(기구현), 기법5 article_body_extractor cascade(07 재사용), 기법10 `RATE_LIMITED_SIGNALS`를 error_taxonomy로 승격(playwright_probe·api_probe 공유). `test_feed_discovery.py` 8 passed. **§3 결정**: LangGraph 채택(신규 패키지 보류)·MCP 보조 위치 → docs/72 등재. 기법 6·8·12는 설계 고정 | 2026-06-13 |

## 05 + 09§1 턴 (google_trends_explore 검증 + 의존성 점검, 2026-06-13)

> 범위: ① 09 §1 런타임 의존성 점검 ② 05 google_trends_explore 활용 가능성 live 검증. 03/04는 미접촉(PASS 유지), gdelt 미접촉(이월 DEFERRED).

- **의존성 readiness = READY (14/14)**: `check_dependency_readiness.py` 신설. import 10종 + chromium launch + selenium_env + state_writable + rate_limit_backend 전부 READY. MISSING 0. → 06/07 진행 전제 충족.
- **google_trends_explore = DEFERRED(429 cooldown)**: live 1회 = 진짜 Google 429 페이지(robot.png). CAPTCHA 아님 → BLOCKED_TERMINAL 아님. cooldown 머신러리 발화 확인(next_retry_at=2026-06-13T06:32:08Z, 3600s). selector 유효성은 위젯 로드 전 429로 차단 → 동반 이월.
- **역할/운영 정책(확정, docs/86 행과 일치)**: role=`enrichment(related_queries)` — 1차 seed 소스 아님. 1차 실검 소스(google_trending_now/signal_bz/loword)가 감지한 hot seed keyword를 받아 연관 검색어를 확장하는 2차 enrichment. recommended_frequency=`2h+ 또는 hot seed 트리거`. 주기 수집 편성=`cycle당 최상위 hot seed 1개에 대해서만 gate(7200s) 통과 시 1회`. min_interval 7200s / cooldown 3600s / max_retries_on_429=0 (보수 정책, 반복 호출 구조적 차단).
- **운영 메모(WARNING → CLOSED, 아래 iter2에서 종결)**: standalone `run_playwright_probe`는 기본 `memory` backend라 cooldown이 디스크 미영속(프로세스 내 ProbeResult에만 반영). 운영 경로(audit/simulation runner)는 `INGESTION_RATE_LIMIT_BACKEND=local_file`을 설정하므로 영속됨. 05 재검증/주기 편성 시 local_file backend 사용 필수.
- **검증**: `test_dependency_readiness.py` 5 passed + `test_trends_explore_activation.py` 3 passed; 전체 `pytest ingestion\tests -q` → **552 passed**(직전 544 + 8); secret scan PASS.

## 05 iter2 턴 (google_trends_explore 잔여 3항목 종결, 2026-06-13)

> 범위: #5의 남은 미완 3개 — ① live extraction 미검증 ② selector validity 미검증 ③ standalone memory backend warning. gdelt/newsapi/ap_news/03/04 미접촉.

- **① live extraction**: gate 선확인에서 cooldown 활성(현재 `05:51:39Z` < next_retry `06:32:08Z`) → **live 미수행**(gate 미통과 시 호출 금지 원칙 준수). source_health.json엔 google_trends_explore 항목 없음 + rate_limit_cache.json엔 어제 만료분(`2026-06-12T09:59:47Z`)만 → iter1의 진짜 429 cooldown이 memory backend라 영속 안 됐음을 실증(=warning의 실질 위험: 영속 상태만 믿으면 gate 오판). 재개 조건: 06:32:08Z UTC 윈도우 이후 local_file backend로 1회.
- **② selector validity = 미검증(판정 불가)**: 저장된 artifact 25개 전수 검사 → robot.png "Error 429" 5개 + `<html>rate limit exceeded</html>`(32B) 19개 = **전부 rate-limit 페이지, 정상 위젯 DOM 0개**. 따라서 selector 유효성을 판정할 수 없으며, 429 페이지로 selector 실패를 오판하지 않는다. 정상 DOM 확보(다음 gate 윈도우 live 성공) 시점에 offline 판정.
- **③ backend warning = CLOSED (선택 A 채택)**: standalone 경로에 backend 강제 wrapper 추가 — `_select_rate_limit_backend(backend)` + CLI `python -m ingestion.probes.playwright_probe --site ... --rate-limit-backend local_file`(playwright_probe.py). 기존 `run_playwright_probe` 라이브러리 시그니처 불변(회귀 0). 정책: **RATE_LIMITED 재검증/주기 수집은 local_file backend 필수**, dev 단발 탐색만 memory 허용. 테스트 `test_trends_explore_backend_policy.py` 5 passed — (a) local_file에서 `record_rate_limited`→파일 영속→재기동 후 next_retry 생존, (b) memory는 재기동 시 소실=의도된 동작(코드 결함 아님), (c) `_select_rate_limit_backend('local_file')`→get_store()가 LocalPersistent, (d) None=noop(memory 기본 유지), (e) CLI main이 probe 호출 전 backend 강제.
- **선택 근거(A vs B)**: 선택 A 채택 — 영속 책임을 official runner에만 두면(B) standalone로 RATE_LIMITED를 검증할 때마다 cooldown이 소실돼 다음 프로세스가 gate를 오판(이번 턴 실측된 위험)한다. 명시적 `--rate-limit-backend` 플래그는 dev memory 기본값을 깨지 않으면서 검증 경로에서 영속을 강제하므로 최소 변경으로 위험을 제거한다.
- **#5 판정**: `DEFERRED_EXTERNAL_RATE_LIMIT` — backend warning은 CLOSED, live extraction·selector validity는 외부 rate limit로 이월(active warning 아님).
- **검증**: `test_trends_explore_backend_policy.py` 5 passed; 전체 `pytest ingestion\tests -q` → **557 passed**(직전 552 + 5); 변경 파일 secret scan PASS(2 files).

## 03/04 anomaly closure (마이크로 턴, 2026-06-13)

> 목표: 직전 턴 03/04 결과의 active anomaly/active warning을 0개로 닫는다. gdelt는 미접촉(이월 DEFERRED).
> 최종 상태는 CLOSED / EXTERNAL_PROVIDER_LIMIT / BLOCKED_BY_PROVIDER 중 하나.
> **갱신(2026-06-13 2차)**: redirect 정규화를 Playwright 1-hop으로 재실험 → 3/3 성공으로 **CLOSED**.
> evidence_level은 canonical AP URL 확보로 `DISCOVERY_PROXY_NOTE`로 하향(WARNING 아님).

| anomaly | root cause | active runtime impact | fix / mitigation | regression test | final status |
|---------|-----------|----------------------|------------------|-----------------|--------------|
| 기존 AP hub RSS endpoint가 HTML 200 반환 | `?format=feed&type=rss` 파라미터를 AP가 무시하고 홈페이지 HTML 응답(endpoint 폐기). 브라우저 UA로도 동일 → UA 차단 아님 | **없음** — active endpoint는 Google News RSS 프록시. 폐기 endpoint는 runtime path에 없음 | endpoint 교체 + 폐기 endpoint를 retired로 명문화(코드 주석 + 테스트 상수 `_RETIRED_AP_ENDPOINT`) | `test_anomaly1_retired_ap_hub_endpoint_not_active` (active endpoint ≠ 폐기 URL, `apnews.com/hub` 미포함) | **CLOSED** (root cause identified + retired endpoint) |
| rsshub 후보 Cloudflare 403 | rsshub.app가 Cloudflare "Just a moment..." challenge로 403. 우회 금지(00 §0-3) | **없음** — rsshub는 후보 단계에서 거부, active endpoint 아님 | candidate rejected / not selected. 우회 시도 안 함 | `test_anomaly2_rsshub_not_selected_as_active_endpoint` (active endpoint에 `rsshub` 미포함) | **CLOSED** (candidate rejected / blocked by Cloudflare) |
| Google News RSS query-string 404 | query를 endpoint URL에 박으면 httpx가 빈 `params={}`로 기존 query string을 통째 덮어써 `/rss/search`(404) | **없음** — q/hl/gl/ceid를 `_PROBE_SPEC.extra_params`로 이동, endpoint는 query string 없음 | extra_params로 분리 + `_build_request`가 params를 정상 전달함을 고정 | `test_anomaly3_query_in_params_not_in_endpoint_url` (endpoint에 `?`/`q=` 없음, `_build_request` params에 q/hl/gl/ceid, httpx build_request가 query 보존) | **CLOSED** |
| ap_news item link가 news.google.com redirect URL (원본 정규화 필요) | Google News 신형 기사 URL(`CBM...`)은 HTTP redirect가 아닌 클라이언트 JS 디코드 — HTTP HEAD/GET은 news.google.com에 머물고(og:url=news.google.com, canonical 자기참조, 본문 apnews 없음), 오프라인 blob은 불투명 protobuf 토큰. **그러나 Playwright headless 1-hop이 JS navigation을 따라가 원본에 도달**(nav: news.google.com→news.google.com→apnews.com) | **해소** — `extract_sample_items(resolve_canonical=True, canonical_via_browser=True)`가 sample에 apnews.com canonical_url 부착. live 3/3 정규화 | HTTP `resolve()`(일반 redirect용, 09 §2-4) + **`resolve_via_browser()` Playwright 승격** + `extract_sample_items` 2단 사다리 연결. 동의/CAPTCHA 페이지는 우회 않고 원본 반환(BLOCKED_BY_PROVIDER 로그), fail-safe/캐시/timeout·max_wait | `test_url_resolver.py` 13종(HTTP: 3-hop→apnews, 실패→원본, max_hops, Google News opaque→불변, HEAD→GET 폴백, 캐시 / 브라우저: needs_browser, canonical_from_html og/canonical/anchor/none, via_browser 성공·fail-safe) + `test_canonical_via_browser_escalates_google_news_urls` | **CLOSED** (Playwright 1-hop 정규화 3/3, live 검증) |
| Google News 프록시 evidence_level 정책 | AP 직접 feed가 아닌 Google News RSS 프록시 경유 (discovery path 간접) | 없음 — canonical AP URL 확보로 **AP source identity 회복**(tier1 유지). discovery path만 프록시 | canonical_url=apnews.com 확보 후 재판정: WARNING/CAVEAT 아니라 discovery 경로 표기로 하향. docs/70·source_registry 동기화 | (정책 기록) | **DISCOVERY_PROXY_NOTE** (canonical AP URL 확보 → identity 회복, 발견 경로만 프록시) |

**closure 요약: active anomaly 0, active warning 0, EXTERNAL_PROVIDER_LIMIT 0, BLOCKED_BY_PROVIDER 0. CLOSED 4 + DISCOVERY_PROXY_NOTE 1(정책 표기).**
재검증 명령: `pytest test_url_resolver.py test_ap_news_recovery.py test_newsapi_everything.py -q` → 24 passed; 전체 **544 passed**; secret scan PASS(1043). live integration: ap_news 3개 Google News URL → Playwright 1-hop **3/3 apnews.com 정규화**(예: `apnews.com/article/anthropic-artificial-intelligence-trump-...`).

## 항목 2 (gdelt) 최종 상태 (확정)

이번 턴에서 gdelt는 **실제 기사 JSON 수집 성공까지는 확인되지 않았다.** live 호출 결과
GDELT public API가 IP 단위 rate limit 평문을 반환했고, 수정된 api_probe는 이를 PARSE_ERROR가
아니라 RATE_LIMITED로 정확히 분류했다.

| 세부 항목 | 상태 |
|----------|------|
| code/test | PASS (전체 회귀 520 passed) |
| phrase quoting | PASS (`test_quote_phrase_wraps_multiword`, `test_apply_query_override_uses_transform`) |
| non-json rate-limit text classification | PASS (`test_non_json_rate_limit_text_reclassified`, `test_gdelt_soft_limit_plaintext_reclassified`) |
| long-query truncation | PASS (`test_truncate_query`) |
| live JSON article fetch | **DEFERRED** |

- **DEFERRED 사유**: 외부 GDELT public API의 IP 단위 rate limit 의존 — 본 코드 변경과 독립.
- **재개 조건**: `source_health.json`의 gdelt `next_retry_at`(현재 2026-06-13T04:29:46Z) 만료 후
  **live 1회만** 재검증 (`run_collection_probe --source gdelt --query "global conflict" --json`).
- **재검증 분기**:
  - `LIVE_SUCCESS` → 완전 PASS (기사 JSON 수집 확정).
  - `RATE_LIMITED` → cooldown 기록 증거 유지 (현 상태 그대로, DEFERRED 연장).
  - `PARSE_ERROR` → 02 루프(00 §3.2 STEP B)로 복귀해 원인 재진단.
- 00 §3.3에 따라 429 발생 시 01의 cooldown 기록 경로(health gate)로 보호되므로 무한 재호출 위험 없음.

## RISK-T04 / rate-limit backend 운영 메모 (확정)

- RISK-T04 핵심 경로는 검증됨: `ProbeResult.next_retry_at` non-None 생성 + `source_health.json`에
  gdelt `state=RATE_LIMITED_COOLDOWN` 및 미래 `next_retry_at` 영속 기록 → health gate `should_skip`
  무력화 문제 해결.
- 단, `rate_limit_cache.json`에는 gdelt next_retry가 남지 않음 — 현재 `INGESTION_RATE_LIMIT_BACKEND`가
  **memory 기본값**이라 프로세스 종료 시 rate-limit store 기록이 소멸하기 때문.
- **운영/Celery/멀티워커 도입 전 조치(필수)**: `INGESTION_RATE_LIMIT_BACKEND=local_file` 또는 공유
  backend(redis 등)로 고정해야 rate-limit store 기록이 워커 간/재기동 후에도 생존한다. (health store는
  이와 무관하게 항상 영속.)

## CONDITIONAL_SOURCES_E2E_AUDIT (01~05 실수집·본문추출 종결, 2026-06-13)

> 목표: 01~05를 기존 30+ 검증완료 소스가 통과한 **실제 수집→candidate→JSONL 누적→article URL 본문
> 추출→body artifact 저장** 파이프라인으로 end-to-end 재검증. 실패/쿨다운은 PASS가 아니라
> collected=false + NOT_CLOSED_*. backend는 `INGESTION_RATE_LIMIT_BACKEND=local_file` 강제.
>
> 신설: `ingestion/runners/run_conditional_sources_e2e_audit.py`(+`test_conditional_sources_e2e.py` 18 tests).
> 산출 JSONL: `ingestion/outputs/jsonl/conditional_sources_e2e_audit_20260613_081243.jsonl` (5줄, 전 대상 기록).

| source_or_component | collected | candidates_created | body_extracted | status | evidence_artifact | next_action |
|---|---|---|---|---|---|---|
| #1 RISK-T04 | n/a(인프라) | 0 | 0 | **PASS** (VERIFIED_PERSIST_AND_SKIP) | gdelt live 429(08:12)→`rate_limit_cache.json` next_retry `08:27:43Z` 영속(local_file)+health RATE_LIMITED_COOLDOWN+gate가 재호출 차단. trends cooldown `08:56:20Z`도 영속+gate skip | closed |
| #2 gdelt | **false** | 0 | 0 | **NOT_CLOSED_EXTERNAL_RATE_LIMIT** | cooldown 만료(08:11:16) 대기 후 live 1회 → 실제 429 재발(GDELT IP rate limit). next_retry `08:27:43Z` 영속 | next_retry 만료 후 live 1회 재시도(연속 금지) |
| #3 ap_news | **true** | 4 | **3** | **PASS** | JSONL ap_news 행(candidates 4, canonical=apnews.com via Playwright 1-hop). body: `extracted_text/ap_news/*_httpx_trafilatura.txt` 3건(1713/5389/6541자). httpx→Playwright fallback로 AP 간헐 throttle 극복 | closed |
| #4 newsapi | **true** | 3 | **3** | **PASS** | JSONL newsapi 행(/v2/everything, q="AI semiconductor"). body: `extracted_text/newsapi/*_httpx_trafilatura.txt` 3건. NEWSAPI_API_KEY 존재(값 비노출) | closed |
| #5 google_trends_explore | **false** | 0 | 0(not_required) | **NOT_CLOSED_EXTERNAL_RATE_LIMIT** | cooldown 활성(next_retry `08:56:20Z`, Google IP 429 지속). gate cooldown_skip로 보호. article source 아님→body=not_required | next_retry 만료 후 local_file backend로 related_query 추출 1회 |

**E2E 결과 요약**: 대상 5 — collected 2/4(데이터 소스 중 ap_news·newsapi), candidates 총 7, body_extracted 총 **6**(전부 디스크 존재 확인), PASS 3(#1·#3·#4) / NOT_CLOSED_EXTERNAL_RATE_LIMIT 2(#2·#5).

**#2/#5 재판정(기존 DEFERRED → E2E 기준)**: 실제 데이터 수집 기준으로 여전히 외부 429 → **NOT_CLOSED_EXTERNAL_RATE_LIMIT**(PASS 아님). #2는 code/test PASS(직전 턴) 유지하되 live JSON article 수집은 미달. #5는 related_query 추출 미달(cooldown). 둘 다 코드/selector 결함 아님(외부 IP rate limit).

**본문 추출 파이프라인(기준선 동일)**: article URL → httpx(브라우저 UA) → 실패 시 Playwright headless fallback → `extract_with_trafilatura` → `save_extracted_text`(헤더 title/published_at/source_url/selected_strategy + 본문). 베이스라인 30+ 소스의 `extracted_text/` 포맷과 동일.

**검증**: `pytest test_conditional_sources_e2e.py` 18 passed; 전체 `pytest ingestion\tests -q` → **575 passed**(직전 557 + 18); secret scan: 신규 코드/JSONL PASS. WARNING 1건은 **오탐**(AP 공개 기사 URL 슬러그 `...mu`+`sk-spacex-tesla-ipo-...`가 OpenAI 키 정규식 `sk-[A-Za-z0-9_-]{20,}`에 매칭 — 실제 키 아님, 스크랩된 공개 콘텐츠. 베이스라인 extracted_text도 동일 노출).

**RISK-T04 backend 영속 확정**: 이번 턴 gdelt 실 429가 **local_file backend**에서 `rate_limit_cache.json`에 next_retry로 영속됨을 실측(`gdelt:global conflict` → `08:27:43Z`, `google_trends_explore:삼성전자` → `08:56:20Z`). 직전 턴 운영 메모(memory 기본값이라 미영속)의 잔여 위험이 운영 경로(local_file 강제)에서 해소됨을 end-to-end로 입증.

## PLAYWRIGHT_SELECTOR_SOURCES_E2E_AUDIT (06/07 — Playwright/selector 소스 5종 실수집·본문추출 종결, 2026-06-13)

> 목표: #6a~6d, #7, #8을 30+ 검증완료 소스와 동일한 **실수집→event candidate→candidate
> JSONL 누적→(가능 시) 본문 추출 artifact** 기준으로 end-to-end 종결. page title fallback
> 성공 처리 금지. backend `INGESTION_RATE_LIMIT_BACKEND=local_file` 강제.
>
> **구조적 진단(RISK-S05 근본 원인)**: "selector 미매칭"의 대부분은 selector 결함이 아니라
> **Route 2(CloudBrowserLikeStrategy)가 site spec의 렌더링 힌트(wait_after_ms/wait_for/scroll)
> 와 selector 추출·click-through를 통째로 버리는 구조 결함**이었다. 1순위 수정은 selector 교체가
> 아니라 **Route 2 → run_playwright_probe 위임**(collection_probe.py).
>
> 신설: `run_structure_explorer.py`(+`test_structure_explorer.py` 7), `article_body_extractor.py`
> (cascade: site_selector→trafilatura→readability→dom_heuristic), `run_playwright_selector_sources_audit.py`,
> `test_route2_delegation.py`(12). 수정: collection_probe(Route2 위임), site_specs(search_url),
> playwright_probe(search_url 분기/rank/본문 cascade), playwright_probe_sites.yaml(dcinside search_url/body).
> 산출 JSONL: `ingestion/outputs/jsonl/playwright_selector_sources_e2e_audit_20260613_085151.jsonl`(5줄).

| source_id | collected | items_found | candidates_created | body_extracted | status | evidence_artifact | next_action |
|---|---|---|---|---|---|---|---|
| signal_bz | true | 10 | 10 | n/a(trend) | **PASS** | rank 1~10 실검 키워드. raw_signal/signal_bz/*.json | closed |
| google_trending_now | true | 20 | 20 | n/a(trend) | **PASS** | 트렌드 키워드(최불암/한화 대 키움). raw_signal/google_trending_now | closed |
| loword | true | 20 | 20 | n/a(trend) | **PASS** | 실검 키워드. selector fragile(styled-components) 주석 유지 | closed (재빌드 시 explorer 재채굴) |
| dcinside | true | 20 | 20 | **2** | **PASS** | 검색 e2e: `a.tit_txt`→board/view→`.write_div` 본문. extracted_payload/dcinside 2건(203/410자 실게시글) | closed |
| eu_press_corner | true | 20 | 20 | 0(opt) | **PASS** | 보도자료 제목+`detail/en/ip_26_*` URL. wait 4000ms 적용 후 SPA 렌더 | closed (본문 추출은 선택) |

**E2E 결과 요약**: 대상 5 — collected **5/5**, candidates 총 **90**, body_extracted **2**(dcinside, 전부 디스크 존재), PASS **5/5**. page title fallback 성공 처리 **0건**.

**소스별 루프(원인→수정→테스트→재검증)**:
- **6a/6b/6d/7**: STEP A(위임 후 재시도)에서 즉시 items≥기대치 → selector는 처음부터 유효, Route 2 결함이 단일 원인. signal_bz는 `rank` 필드 추가(enumerate). 실데이터 확인(page title fallback 아님).
- **6c/8 dcinside**: ① 검색 selector — items=0 재현 → explorer offline 분석으로 `a.tit_txt`(검색 결과 게시글→board/view detail URL) 도출 → YAML 적용 → live items=20. ② 본문 — readability가 "자동 짤방" 공통 안내 박스(208자 동일)를 오선택 → detail DOM 실측으로 `.write_div` 본문 컨테이너 확인 → site selector를 cascade보다 우선(매칭됐으나 짧으면 cascade 폴백 금지 = boilerplate 회피) → 재검증 본문 2건 site_selector(실게시글). offline 테스트 2건 추가.

**본문 추출 cascade**: `extract_article_body(html, url, body_selectors)` — site_selector(있으면 우선, boilerplate 회피) → trafilatura → readability → dom_heuristic. 200자 미만/실패 시 다음 단계. dcinside 본문은 `save_extracted_payload`로 저장(url/title/body/method).

**검증**: `pytest test_structure_explorer.py test_route2_delegation.py` 19 passed; 전체 `pytest ingestion\tests -q` → **594 passed**(직전 575 + 19); secret scan PASS(신규 코드+JSONL). 기존 `test_fetch_strategies` dcinside 테스트는 위임 결과로 갱신(CloudBrowserLike→run_playwright_probe 위임 검증).

**남은 gap(외부/구조 무관, 정직 기록)**: loword는 styled-components 해시 클래스 의존이라 사이트 재빌드 시 selector 깨질 수 있음(현재 매칭, fragile 주석 + explorer 재채굴 경로 확보). eu_press_corner 본문 추출은 이번 종결 기준에서 선택(opt)이라 미수행 — 필요 시 click_target+body selector 추가로 동일 e2e 가능. **수정 가능한 selector/wait/body 결함은 0건 잔존**(전부 이번 턴 종결).

## API_PARTIAL_SOURCES_E2E_AUDIT (08 partial/no 소스 + 09 즉시 기법 종결, 2026-06-13)

> 목표: #9~#13(federal_register/igdb/culture_info/hacker_news/bok_ecos/eia/its/시장 수치)을
> 실제 sample → event_candidate 또는 numeric_signal → (URL 보유 시) 본문 추출 artifact 기준으로
> end-to-end 종결. 키 부재는 PASS 아닌 DEFERRED_NEEDS_KEY. seed_ready 부적합 수치원은 억지
> seed PASS 금지(numeric_signal 평가 경로 분리).
>
> 신설: `run_api_partial_sources_audit.py`, `feed_discovery.py`(09 기법2·3·6),
> `test_api_source_field_fixes.py`(16), `test_feed_discovery.py`(8), `test_api_partial_audit.py`(7).
> 수정: api_probe(federal_register fields[]/igdb url/hacker_news detail), _audit_common
> ($root/epoch/_XML_FIELD_NAMES/_SAMPLE_PATHS 5종/NUMERIC_SIGNAL_SOURCES/seed_ready_label_for/
> collect_samples extracted fallback), error_taxonomy(RATE_LIMITED_SIGNALS 승격=기법10),
> playwright_probe(_detect_429 공유), run_primary_seed_live_audit(seed_ready_label_for + flat numeric).
> 산출 JSONL: `ingestion/outputs/jsonl/api_partial_sources_e2e_audit_20260613_092502.jsonl`(8줄).

| source_id | root_cause | output_type | live | collected | samples | candidates | numeric | body | status |
|---|---|---|---|---|---|---|---|---|---|
| federal_register | A | event_candidate | y | y | 3 | 3 | 0 | 1 extracted | **PASS** |
| igdb | A | event_candidate | y | y | 3 | 3 | 0 | not_required | **PASS** |
| culture_info | B | event_candidate | y | y | 3 | 3 | 0 | not_required | **PASS** |
| hacker_news | A | event_candidate | y | y | 3 | 3 | 0 | 1 extracted | **PASS** |
| bok_ecos | B+C | numeric_signal | y | y | 3 | 0 | 3 | not_required | **PASS** |
| eia | B+C | numeric_signal | y | y | 3 | 0 | 3 | not_required | **PASS** |
| its | B+C | numeric_signal | y | y | 3 | 0 | 3 | not_required | **PASS** |
| finnhub | C | numeric_signal | y | y | 0(flat) | 0 | 1 | not_required | **PASS** |

**E2E 요약**: 대상 8 — collected **8/8**, candidates 총 **12**, numeric_signals 총 **10**, body_extracted **2**(federal_register/hacker_news, 디스크 존재 확인), PASS **8/8**. DEFERRED_NEEDS_KEY 0(igdb/culture_info 키는 .env에 IGDB_*·CULTURE_INFO_KEY alias로 존재).

**소스별 루프(원인→수정→검증)**:
- **federal_register(A)**: fields[] 1개→5개 list. 즉시 url+date 풍부. body 1건 추출.
- **igdb(A)**: apicalypse url 추가 + _SAMPLE_PATHS $root + epoch→ISO. url=igdb.com/games/*.
- **culture_info(B)**: 구 artifact 전수가 Service Error(과거 param) → live 재호출 LIVE_SUCCESS items=10 확인 → _XML_FIELD_NAMES로 title/startDate/realmName 매핑. key는 CULTURE_INFO_KEY alias.
- **hacker_news(A)**: detail_endpoint_template + api_probe 2차 호출(/v0/item/{id}.json) + collect_samples extracted_payload fallback. title+url+time(epoch).
- **bok_ecos/eia/its(B/C)**: _SAMPLE_PATHS 추가 + NUMERIC_SIGNAL_SOURCES 분리. signal_ready.
- **finnhub(C) flat quote 루프**: collect_samples가 list 없는 flat quote에서 0건 → 1차 NOT_CLOSED_NO_SAMPLES 재현 → `_flat_numeric_signal`(scalar 필드 묶음) + `_evaluate_seed`가 probe items_found 사용하도록 수정 → signal_ready/PASS. (selector/mapping 결함 0건 잔존.)

**공식 primary_seed_live_audit 재검증(8 subset)**: 전부 LIVE_SUCCESS — federal_register/igdb/culture_info/hacker_news=**yes**, bok_ecos/eia/its/finnhub=**signal_ready**. seed_ready no(signal 제외)=0. JSONL `primary_seed_live_audit_20260613_092750`.

**검증**: `pytest test_api_source_field_fixes.py test_feed_discovery.py test_api_partial_audit.py` 31 passed; 전체 `pytest ingestion\tests -q` → **625 passed**(직전 594 + 31); 신규 산출물/코드 secret scan PASS(6 files). env hygiene = 기존 AMBIGUOUS_ALIAS 6건(증감 없음). 전체 outputs/docs scan WARNING 1건은 기존 오탐(ap_news 공개 기사 URL 슬러그 `sk-spacex-tesla-ipo-...`, 실제 키 아님 — 직전 턴부터 기록).

**남은 gap**: 수정 가능한 fields/mapping/body/candidate 결함 **0건 잔존**(전부 이번 턴 종결). 09 기법 6(sitemap 깊은 백필)·8(self-healing streak)·12(DOM fingerprint)는 설계 고정(후속 라운드 부분 구현). 기법 7(Conditional GET)·11(LLM judge)은 plans/012 주기 수집/이벤트 큐 투입 시.

## docs/10 최종 Closing 턴 (외부 rate-limit 실검증 + enrichment + 오케스트레이션 재감사, 2026-06-13)

> 목표: "rate limit인 듯"으로 끝내지 않고 검색 근거 + 실제 재호출 artifact로 #2/#5를 닫고,
> enrichment live audit·secret FP·runner orchestration readiness까지 실제 실행으로 확정한다.

- **PHASE 1-2 provider evidence**: `docs/ingestion/rate_limit_evidence.md` 신설. GDELT 공식 블로그(수치 미공개·UA 필수)·gdelt-doc-api #22·pytrends Issues(#243/#561/#578/#622/#631, 공식 quota 없음·429 빈발·Retry-After 부재) 정리. `rate_limit_policy.yaml` 값(gdelt 60s/900s, trends 7200s/3600s)은 근거보다 보수적 → **변경 불필요**(실측 cooldown과 정합: gdelt +900s, trends +3600s).
- **PHASE 3 gdelt = PASS**: gate 통과 live 1회 → LIVE_SUCCESS items=3 실기사 + body 676자(aif.ru). 빠른 2차 호출만 soft-429(→ min_interval 정책 필요성 재확인). raw/extracted/body artifact 디스크 존재.
- **PHASE 4 google_trends_explore = RATE_LIMITED_CONFIRMED**: live 1회 → rendered DOM `Error 429 (Too Many Requests)!!1` + robot.png(1730B) = 정품 Google 429(selector miss 아님). screenshot+rendered_dom 저장, next_retry 10:49:28Z local_file 영속.
- **신규 runner** `run_external_rate_limit_recheck.py`: gate-aware 재검증(쿨다운 시 직전 성공 artifact로 판정, provider 재호출 금지). JSONL `external_rate_limit_recheck_*` (gdelt PASS / trends RATE_LIMITED_CONFIRMED).
- **PHASE 5 enrichment live audit 실제 실행**: `enrichment_live_audit_20260613_095628.jsonl` — live 33회 전부 collected(items>0), relevance high 27/low 6, gdelt 2건 health_skip(쿨다운 정직 기록), query_unsupported 24(파라미터 lookup/fixed feed 참조). **본문 추출 cascade 연결**: enrichment article URL 4건 시도 → 3건 추출(guardian 3588/gnews 3867/newsapi 2565자), nyt 1건 paywall 실패(정직).
- **PHASE 6 secret FP CLOSED**: `sk-` 오탐 4건 전부 기사 URL slug(ri[sk]-if-iran…, mu[sk]-spacex…) 확인. scan_secrets에 좁은 판별 추가(`sk`가 단어 중간이거나 고엔트로피 토큰 부재 → slug). `sk-*` 전체 무시 아님. 테스트 2건 추가. **캐노니컬 scan(outputs/docs/plans) = PASS**(1526 files).
- **PHASE 7 runner orchestration readiness**: 신규 `run_runner_orchestration_readiness.py` → `runner_orchestration_readiness_*.jsonl`. 12개 스크립트 **전부 agent_ready=True**(CLI 9 + 라이브러리 3). 모든 audit runner가 source/status/next-action 구조화 출력 보유.
- **검증**: 전체 `pytest ingestion\tests -q` → **627 passed**(직전 625 + scan_secrets 2). env hygiene 6 AMBIGUOUS_ALIAS(기준선 동일). 캐노니컬 secret scan PASS.
- **최종 판정**: #2 gdelt **PASS 승격**, #5 google_trends_explore **CONFIRMED_EXTERNAL_RATE_LIMIT**(provider 429 실증, 재개=10:49:28Z 윈도우 후 1회). 15항목 중 PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1. 수정 가능 gap 0건.

## Trends fallback + 문서 통폐합 턴 (PHASE 1~8, 2026-06-13)

> 목표: google_trends_explore 429를 강제로 뚫지 않고 안전·합법 fallback으로 "트렌드 seed/related expansion"을 계속 확보 + 전체 runner/문서 동기화 + Implementation_Instructions 통폐합.

- **PHASE 1 역할 3분할**: Google Trends(제품명, source_id 아님) / google_trending_now(primary trend seed, PASS) / google_trends_explore(optional_enrichment, CONFIRMED_EXTERNAL_RATE_LIMIT, critical dependency 제외). docs/86·92·70 반영.
- **PHASE 2 fallback chain** 신규 `run_trend_fallback_enrichment_audit.py`:
  - A google_trending_now(Playwright) — cooldown 시 직전 raw_signal artifact.
  - B **google_trends_trending_now_export** — 공개 RSS `trends.google.com/trending/rss?geo={region}` → **EXPORT_AVAILABLE 실측**(feed_discovery 검증). 못 찾으면 EXPORT_UNAVAILABLE.
  - C 뉴스/검색 enrichment — hot seed 1개 → serper/tavily/naver(+영문 시 exa/gnews/newsapi/guardian/ap_news) → `_audit_common.extract_related_candidates`(규칙 기반: repeated_term/title_bigram/proper_entity/한글 2-gram).
  - 신규 헬퍼 `extract_related_candidates`(_audit_common.py).
- **PHASE 3 정책 고정**: google_trends_explore = min_interval 7200s / cooldown 3600s / **max_retries_on_429=0** / body_status=not_required / 실패 시 collected=false + fallback. 테스트 `test_trend_fallback.py` 8 passed.
- **PHASE 4 실측**(trend_fallback_enrichment_audit_20260613_102354.jsonl): A collected / **B EXPORT_AVAILABLE**(items 3) / C serper·tavily·naver collected(related 8/3/12, body 1 extracted) / explore RATE_LIMITED_CONFIRMED. **aggregate related_candidate 19(≥5), collected fallback source 5(≥2), body 1(≥1)**. en 전용 소스는 한글 seed라 LANG_SKIP(누락 아님). 우회 0건.
- **PHASE 5 runner readiness**: 신규 fallback runner 등록 → `runner_orchestration_readiness_20260613_102603` **13/13 agent_ready**(JSONL 계약 source_id/status/next_action 충족).
- **PHASE 6 문서 동기화**: docs/70·86·92·rate_limit_evidence(§5 추가)·closing_checklist #5 갱신.
- **PHASE 7 통폐합**: `IMPLEMENTATION_TRACE_FINAL.md`(통합 trace) + `README.md`(진입점 index) 신설. 00=ROOT 배너, 01~10=APPLIED/SUPERSEDED 배너(비파괴, 삭제 없음).
- **PHASE 8 검증**: 전체 `pytest ingestion\tests -q` → **635 passed**(627 + 8). secret scan 캐노니컬 PASS. env hygiene 6 AMBIGUOUS_ALIAS(기준선). git push/reset/clean 미사용.
- **판정**: `PASS_WITH_GOOGLE_TRENDS_EXPLORE_EXTERNAL_GAP` — fallback chain이 실제 related_candidate 생성(19). google_trends_explore만 외부 provider 429 이월(optional, 비차단). 15 checklist PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1.

## 최종 정리 턴 — CLEAN 전환 (secret scan PASS + 통폐합 stub + manifest, 2026-06-13)

> 목표: 잔여 WARNING / untracked 문서 / 문서 중복 / artifact 재현성 약점을 규약에 맞게 닫아 최종 상태를 CLEAN으로 만든다.

- **secret scan WARNING → PASS(WARNING 0)**: 6건 전부 false positive로 분류·종결(REAL_SECRET 0). ① `api_probe.py` `access_token = _igdb_get_access_token(...)` = 함수 호출 → scan_secrets에 좁은 코드참조 FP 판별 추가(따옴표 리터럴은 그대로 WARNING). ② 테스트 fixture(test_scan_secrets×4, test_env_alias_precedence×1) = 라인별 `# pragma: allowlist secret`(Layer1만 면제, Layer2 BLOCKED는 면제 불가). `sk-*` 전체 무시 아님. 신규 테스트 4건(함수호출 FP/따옴표 리터럴 탐지/pragma 억제/pragma가 env값 누출은 미억제). **캐노니컬 scan(ingestion docs plans) verdict=PASS**.
- **Implementation_Instructions 통폐합**: 00=ROOT(절대 제약 유지). 01~10 + ROADMAP = 원래 경로 **stub**, 원문 전체는 `_archive_applied/`로 `git mv`(경로 이력 보존). ROADMAP 방법론(실행 순서/A→E 루프/안정성 서열)은 TRACE_FINAL **부록 A**로 흡수. README가 단일 진입점.
- **artifact manifest**: `docs/ingestion/artifact_manifest_final.md` 신설 — outputs 미커밋(gitignore) 사유 + 8개 핵심 JSONL의 size/SHA256/재생성 명령/checklist + 대표 body/DOM/screenshot 경로.
- **_audit_common contract test 강화**: truncate_query(이중 상한·한영혼합·None), seed_ready_label_for(article vs numeric_signal), extract_related_candidates malformed 내성(None sample skip) 추가.
- **검증**: 전체 `pytest ingestion\tests -q` 통과(635 + 신규). `git diff --check` 통과. **secret scan verdict=PASS**. git push/reset/clean/rm 미사용.
- **판정**: **CLEAN** — untracked 문서 0, secret scan WARNING 0, 문서 상태 충돌 0, ROADMAP/01~10 stub 완료, artifact manifest 존재. outputs는 gitignore(매니페스트 기록).

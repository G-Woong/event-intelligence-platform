# Provider Rate-Limit Evidence & Policy Alignment (docs/10 PHASE 1-2)

- 작성: 2026-06-13 (UTC)
- 목적: gdelt / google_trends_explore의 rate limit이 코드 결함이 아니라 외부 provider
  제한임을 **검색 근거 + 실제 재호출 artifact**로 입증하고, `rate_limit_policy.yaml`
  값이 그 근거와 정합한지 점검한다.
- 보안: 어떤 키/토큰 값도 기록하지 않는다. URL은 공개 엔드포인트만.

## 1. Provider Limit Evidence

| source_id | evidence_source | official_or_unofficial | found_limit_or_signal | applied_policy | 비고 |
|---|---|---|---|---|---|
| gdelt | GDELT Project Blog — "Ukraine, API Rate Limiting & Web NGrams 3.0" (blog.gdeltproject.org) | official | "Our APIs are rate limited to protect the underlying ElasticSearch clusters" — **수치 미공개**, 대안으로 Web NGrams/BigQuery 권장 | min_interval 60s / cooldown 900s | 공식이 숫자를 안 줌 → 실측 기반 보수 설정 |
| gdelt | alex9smith/gdelt-doc-api Issue #22 "Recommended fix for rate limit response" | unofficial(community) | "the API now needs a user agent before returning any data" + 429 발생 → **User-Agent 헤더 필수** | probe가 `User-Agent` 송신(api_probe.py:451) | UA 미송신 시 데이터 거부 |
| gdelt | 커뮤니티 통념(gdelt-doc-api) | unofficial | 관용적 "1 request / 5s" 권장(공식 문서엔 없음) | min_interval 60s (**5s보다 12배 보수적**) | soft-limit은 200+평문으로도 옴 |
| google_trends_explore | GeneralMills/pytrends Issues #243/#561/#578/#622/#631 | unofficial | 공식 public API 없음. 429 "Too Many Requests" 빈발. "**60s sleep** once you reach the limit", proxy/login으로만 한도 상향 | min_interval 7200s / cooldown 3600s | 고정 quota 미공개 |
| google_trends_explore | 실측(2026-06-13 rendered DOM) | observed | `<title>Error 429 (Too Many Requests)!!1</title>` + `images/errors/robot.png` (1730 bytes) | cooldown 3600s 적용, next_retry 영속 | **Retry-After 헤더 없음**(렌더드 에러 페이지) |

근거 요약:
- **gdelt**: 공식 블로그는 "rate limited"만 명시하고 **수치를 공개하지 않는다**. 따라서 숫자는
  실측/응답문 기반으로 보수 설정한다. 커뮤니티 통념 "5s"보다 우리 정책(60s)이 더 보수적이므로
  근거 위반이 아니다. User-Agent 필수 조건은 이미 충족(probe가 honest UA 송신).
- **google_trends_explore**: Google은 Trends에 **공식 public API/quota를 제공하지 않는다**.
  429는 anti-abuse 신호이며 Retry-After 헤더가 없다. 비공식 접근의 운영 리스크(IP 차단)가 크므로
  primary가 아니라 **optional enrichment**로만 유지한다. proxy rotation/로그인/CAPTCHA 우회는
  하드 제약상 금지 → 정책은 "장주기 + 429시 장쿨다운 + 재시도 0"으로 고정한다.

## 2. Policy Alignment 점검 (`ingestion/configs/rate_limit_policy.yaml`)

| source_id | min_interval_seconds | cooldown_on_429_seconds | max_retries_on_429 | cache_ttl_seconds | 근거 대비 판정 |
|---|---|---|---|---|---|
| gdelt | 60 | 900 | 1 | 900 | 커뮤니티 5s·공식 무수치보다 **보수적** → 유지 |
| google_trends_explore | 7200 | 3600 | 0 | 7200 | pytrends 60s·공식 무quota보다 **보수적**, Retry-After 부재 → conservative cooldown 유지 |
| google_trending_now | 7200 | 3600 | 0 | 7200 | 동일 provider(Google Trends) → 동일 정책 |

판정: **정책 변경 불필요**. 모든 값이 검색 근거(있는 경우)보다 같거나 더 보수적이며, provider보다
공격적인 값이 없다. 실측 결과와도 정합:
- gdelt 실측 cooldown = 900s 적용(2026-06-13 09:48Z 429 → next_retry 10:03Z = +900s) → policy와 일치.
- google_trends 실측 cooldown = 3600s 적용(09:49Z 429 → next_retry 10:49Z = +3600s) → policy와 일치.
- Retry-After가 policy보다 길면 우선한다는 원칙은 적용 대상 없음(두 provider 모두 Retry-After 미제공).

## 3. 실제 재호출 검증 (PHASE 3-4 요약, 상세는 external_rate_limit_recheck JSONL)

| source_id | live_called | response | samples/items | candidates | body | next_retry_at | final |
|---|---|---|---|---|---|---|---|
| gdelt | y (2026-06-13 09:47Z) | LIVE_SUCCESS (application/json) | 3 | 3 | 1 (676자, aif.ru, trafilatura) | (쿨다운은 빠른 2차 호출이 유발, 1차는 성공) | **PASS** |
| google_trends_explore | y (2026-06-13 09:49Z) | RATE_LIMITED (Error 429 rendered DOM) | 0 | 0 | not_required | 2026-06-13T10:49:28Z | **RATE_LIMITED_CONFIRMED** |

- gdelt는 min_interval(60s) 준수 시 정상 JSON 수집 가능 = **수집 능력 입증**. 빠른 연속 호출은
  GDELT가 soft-limit(200+평문)으로 거부 → 이는 `min_interval_seconds: 60` 정책의 필요성을 재확인.
- google_trends_explore는 단일 호출에도 IP 단위 429 → 정책(장쿨다운/재시도0)대로 cooldown 영속,
  연속 재시도 금지 준수. 우회 없음.

## 4. 결론

두 소스의 rate limit은 **외부 provider 제한**이며 코드/selector/mapping 결함이 아니다.
정책 값은 근거와 정합하고 보수적이다. gdelt는 주기 호출 시 수집 가능(종결 PASS),
google_trends_explore는 confirmed external rate limit으로 optional enrichment에 한해 유지한다.

## Sources
- https://blog.gdeltproject.org/ukraine-api-rate-limiting-web-ngrams-3-0/
- https://github.com/alex9smith/gdelt-doc-api/issues/22
- https://github.com/GeneralMills/pytrends/issues/578
- https://github.com/GeneralMills/pytrends/issues/622
- https://github.com/GeneralMills/pytrends/issues/243
- https://github.com/GeneralMills/pytrends/issues/631
- https://github.com/GeneralMills/pytrends/issues/561

## 5. Google Trends fallback (PHASE 2, 2026-06-13)

google_trends_explore의 429(외부 provider)를 강제로 뚫지 않고 안전·합법 대체 경로로 동일 목적
("트렌드 seed / related expansion")을 확보한다. 우회(CAPTCHA/로그인/proxy rotation/internal RPC) 없음.

| fallback_stage | 경로 | 합법성 근거 | 실측(2026-06-13) |
|---|---|---|---|
| A | google_trending_now (Playwright `/trending`) | 공개 페이지, 기존 PASS | LIVE_SUCCESS, trend item ≥3 |
| B | google_trends_trending_now_export (공개 RSS `trends.google.com/trending/rss?geo=`) | 공개 RSS feed(내부 batchexecute 아님) | **EXPORT_AVAILABLE**, items 3 |
| C | 뉴스/검색 enrichment (serper/tavily/naver/exa/gnews/newsapi/guardian/ap_news) | 각 provider 공식 API/공개 RSS | collected 3+(serper/tavily/naver), related 19, body 1 |

- google_trends_explore 정책 고정: role=optional_enrichment, min_interval 7200s, cooldown 3600s,
  **max_retries_on_429=0**, body_status=not_required, 실패 시 collected=false + fallback chain 실행.
- 정책 테스트: `test_trend_fallback.py::test_google_trends_explore_policy_is_optional_no_retry`.
- 실측 artifact: `trend_fallback_enrichment_audit_20260613_102354.jsonl`.

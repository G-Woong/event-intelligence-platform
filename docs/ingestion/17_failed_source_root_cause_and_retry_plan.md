# 17 — Failed Source Root Cause & Retry Plan

> 비개발자도 읽을 수 있는 설명으로 작성. 각 실패 원인과 적용된 해결책 기록.

---

## 1. ap_news — rsshub 403 → AP 공식 RSS 전환

**증상**: `https://rsshub.app/apnews/topics/ap-top-news`에서 HTTP 403 반환  
**원인**: rsshub.app은 AP News 공식 서버가 아닌 제3자 RSS 변환 서비스. rsshub 서버가 AP에서 차단되거나 서비스 정책이 변경됨.  
**해결책**: AP News 공식 Atom/RSS 피드로 엔드포인트 교체  
`https://apnews.com/hub/ap-top-news?format=feed&type=rss`  
**적용 위치**: `ingestion/runners/run_api_connectivity_check.py` `_SERVICE_CONFIGS["ap_news"]`  
**재검증**: dry-run PASS. live 검증은 다음 라운드에서 확인 필요.

---

## 2. sec_edgar — LIVE_PARTIAL (중첩 필드 미해석)

**증상**: HTTP 200 응답이지만 `items_found = 0`, 상태 LIVE_PARTIAL  
**원인**: SEC EDGAR API 응답 구조가 `{"hits": {"hits": [...], "total": {...}}}` — `hits`라는 최상위 키 안에 실제 배열 `hits`가 중첩됨. 기존 `_count_items`는 중첩 경로를 지원하지 않아 `hits` 최상위 딕셔너리를 찾고 리스트가 아니므로 count=0 처리.  
**해결책**: `_count_items`에 dotted path 지원 추가 (`hits.hits`, `response.routes`, `data.posts.edges` 등). `_PROBE_SPEC["sec_edgar"]["meaningful_fields"]` 를 `["hits.hits"]`로 갱신.  
**적용 위치**: `ingestion/probes/api_probe.py`  
**재검증**: `test_count_items_dotted_hits_hits` 테스트 PASS.

---

## 3. eia — LIVE_PARTIAL (response.routes 중첩 필드)

**증상**: EIA v2 routes 엔드포인트에서 응답 성공이나 `routes` 필드 미탐지  
**원인**: EIA API v2의 루트 응답은 `{"response": {"routes": [...]}}` 구조. 기존 스펙 `meaningful_fields: ["routes"]`는 최상위에서만 탐색하여 실제 데이터를 찾지 못함.  
**해결책**: `meaningful_fields`를 `["response.routes"]`로 갱신 (dotted path 지원으로 처리)  
**적용 위치**: `ingestion/probes/api_probe.py` `_PROBE_SPEC["eia"]`  
**재검증**: `test_count_items_dotted_response_routes` PASS.

---

## 4. product_hunt — LIVE_PARTIAL (GraphQL 중첩 응답)

**증상**: GraphQL POST 요청 성공이나 items_found = 0  
**원인**: product_hunt GraphQL 응답 구조 `{"data": {"posts": {"edges": [...]}}}`. 기존 `meaningful_fields: ["data"]`는 `data` 딕셔너리를 찾지만 list가 아니므로 count=0.  
**해결책**: `meaningful_fields`를 `["data.posts.edges"]`로 갱신  
**적용 위치**: `ingestion/probes/api_probe.py` `_PROBE_SPEC["product_hunt"]`  
**재검증**: `test_count_items_dotted_data_posts_edges` PASS.

---

## 5. kopis/aladin — XML 응답 파싱 부재

**증상**: HTTP 200 응답(XML)이지만 items_found = 1 (고정) — 실제 항목 수 미파악  
**원인**: 기존 코드가 XML 응답을 단순히 "content가 100자 이상이면 성공"으로 처리. 실제 XML 파싱 없음.  
**해결책**: `run_api_live_probe`에 XML 분기 추가: `xml.etree.ElementTree`로 `<item>` 또는 `<entry>` 요소를 카운트. 파싱 실패 시 기존 fallback 유지.  
**적용 위치**: `ingestion/probes/api_probe.py`  
**재검증**: `test_run_api_live_probe_xml_rss_counts_items` PASS (kopis/aladin은 키 없어 live 불가 — XML 파싱 경로만 검증).

---

## 6. gdelt — 429 RATE_LIMITED

**증상**: 단기 반복 호출 시 HTTP 429 반환  
**원인**: GDELT 무료 API는 rate limit이 있으며 문서화되지 않음.  
**해결책**: `strategy_runner.run_fetch_strategy_loop`의 backoff (`delay_for_attempt`) 가 자동 적용됨. RATE_LIMITED → `ErrorType.HTTP_4XX` 분류 → 재시도 정책에서는 HTTP_4XX가 retry_on에 없으므로 1회 기록 후 중단. 수동 재시도 간격 권장.  
**재검증**: backoff 로직은 `test_strategy_runner.py` budget/delay 테스트로 간접 검증.

---

## 7. DEFERRED: reddit (OAuth), x/blind (login), reuters (license)

**증상**: 데이터 수집 불가  
**원인**:  
- **reddit**: 공개 `.json` 엔드포인트는 접근 가능하나 최근 API 정책 변경으로 신뢰성 불명. OAuth 기반 확장은 이번 라운드 DEFERRED.  
- **x (Twitter)**: Bearer token 또는 OAuth 1.0a 필수. 무료 API 정책 제한적.  
- **blind**: 로그인 전용 콘텐츠. login wall 우회 코드 금지.  
- **reuters**: 콘텐츠 재배포 라이선스 검토 필요.  
**해결책 없음 (이번 라운드)**: BLOCKED/DEFERRED 기록. 우회 코드 미작성.

---

## 8. opendart — 날짜 범위 파라미터 갱신

**증상**: 이전 날짜(`bgn_de: "20260101"`)로 3영업일 내 데이터가 적을 가능성  
**원인**: 날짜가 6개월 전 고정값.  
**해결책**: `bgn_de: "20260529"` (최근 3영업일)로 갱신. 실제 probe는 키 없어 live 불가.

---

## 9. DEFERRED: dcinside/fmkorea/signal_bz (Playwright 필요)

**증상**: httpx로는 빈 DOM 반환, 실제 콘텐츠가 JS로 렌더링됨  
**원인**: Vue/React SPA 또는 JS 조건부 렌더링  
**해결책**: `CloudBrowserLikeStrategy`로 라우팅 준비 완료 (`_PLAYWRIGHT_FIRST_SOURCES`). 실제 selector 갱신 및 live 검증은 다음 라운드.

---

## 10. 키 없는 API 소스 (serper/tavily/exa/newsapi 등)

**증상**: MISSING_KEY — 데이터 수집 불가  
**원인**: `.env`에 키 미등록  
**해결책**: `_PROBE_SPEC`에 POST 빌더 추가 완료. 키 발급 후 `.env`에 등록하면 즉시 동작.  
**현재 상태**: MISSING_KEY 기록, 빌더만 준비.

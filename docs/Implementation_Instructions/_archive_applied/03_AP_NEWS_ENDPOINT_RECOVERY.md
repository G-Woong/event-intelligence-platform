# 03. ap_news 복구 — RSS endpoint HTML 에러 페이지 원인 규명 + 대체 경로

> **상태: APPLIED — SUPERSEDED_BY [IMPLEMENTATION_TRACE_FINAL.md](./IMPLEMENTATION_TRACE_FINAL.md)** (2026-06-13). 본 지시문은 적용 완료. 원문은 이력 보존용이며 파괴적 삭제 금지. 현재 상태는 trace final + docs/ingestion/70·86·92 참조.

> ## ✅ 적용 완료 (2026-06-13)
> **원인 판정: H1(endpoint 폐기)** — `apnews.com/hub/ap-top-news?format=feed&type=rss`가 파라미터를
> 무시하고 AP 홈페이지 HTML(200)을 반환. 브라우저 UA로 동일 호출해도 같은 HTML이라 **H2(UA 차단) 기각**,
> rsshub 후보는 Cloudflare 403. **채택 해결책: §4-B — Google News RSS 프록시**로 endpoint 교체.
> - 변경: `_SERVICE_CONFIGS["ap_news"].endpoint = https://news.google.com/rss/search` (+ note),
>   `_PROBE_SPEC["ap_news"].extra_params = {q: "site:apnews.com", hl, gl, ceid}`.
> - **실측 함정**: query를 endpoint URL에 박으면 httpx가 빈 `params={}`로 기존 query string을 통째
>   덮어써 `/rss/search`(404)로 감 → query 파라미터를 `extra_params`로 이동해 해결.
> - live 검증: `run_collection_probe --source ap_news --json` → **LIVE_SUCCESS, items_found=100**,
>   sample title+url 확보(RSS pubDate는 `extract_sample_items`가 채움 — 단위 테스트로 입증).
> - 테스트: `ingestion/tests/unit/test_ap_news_recovery.py` 3 passed. 전체 회귀 526 passed.

> 선행: 01. 변경: `ingestion/runners/run_api_connectivity_check.py`(`_SERVICE_CONFIGS`), 경우에 따라 `ingestion/configs/source_registry.yaml`·`ingestion/sources/ap_news.py` 정합 확인. live 진단 호출 수: 최대 4회 (전부 키 불필요 public).

## 1. 해석 — 사실 관계

- 현재 등록: `_SERVICE_CONFIGS["ap_news"].endpoint = "https://apnews.com/hub/ap-top-news?format=feed&type=rss"` (`run_api_connectivity_check.py:48-55`). note에 "rsshub 403 → AP official RSS/Atom feed (2026-06-03)" — **06-03에는 이 URL이 동작했다.**
- 06-12 실측(docs/88): `API_RETURNED_HTML_ERROR_PAGE` — HTTP 200이지만 body가 `<html`/`<!doctype`로 시작 (api_probe.py:705-708의 감지 로직). 단, items_found 3 + url 존재로 기록된 것은 HTML fallback 추출이 페이지에서 링크를 주운 것이지 RSS가 아니다.
- 사용자 질문 "playwright/selenium까지 다 돌렸는데도 에러 페이지였나?"에 대한 답: **아니다.** ap_news는 `_PROBE_SPEC`에 entry(xml)가 있어 Route 1(API/httpx)로만 호출되었다. Playwright/Selenium 전략은 시도된 적 없다. 따라서 이번 라운드에서 전략 사다리를 실제로 태워 규명한다.

## 2. 원인 가설 (STEP B에서 구분 실험)

| 가설 | 내용 | 구분 실험 |
|------|------|----------|
| H1 | AP가 `?format=feed&type=rss` 파라미터 지원을 제거 (endpoint 폐기) | 브라우저 UA로 같은 URL 호출 → 여전히 HTML이면 H1 유력 |
| H2 | bot 차단(UA 기반) — 정직한 UA `event-intelligence/0.7`이 Akamai 등에서 차단되어 에러/안내 페이지 | 브라우저 UA httpx 호출 → RSS XML이 오면 H2 확정 |
| H3 | 지역/JS challenge — JS 렌더링 후에만 콘텐츠 | playwright로 열어 콘텐츠 확인 |

## 3. 진단 절차 (STEP A→B, 순서 고정)

**(1) 기존 artifact 검안 (호출 없음)**: `ingestion/outputs/raw_payload/ap_news/`의 최신 `.xml` 파일을 열어 처음 1000자를 확인. `<title>` 태그 내용과 에러 문구(예: "Access Denied", "Page not found", 정상 홈페이지 HTML 여부)를 체크리스트에 기록. 정상 홈페이지 HTML이면 H1(파라미터 무시→홈으로 응답) 쪽.

**(2) UA 실험 (live 1회)**: 임시 스크립트가 아닌 일회성 파이썬 한 줄로:
```powershell
.\.venv\Scripts\python.exe -c "import httpx; r=httpx.get('https://apnews.com/hub/ap-top-news?format=feed&type=rss', headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}, follow_redirects=True, timeout=20); print(r.status_code, r.headers.get('content-type')); print(r.text[:300])"
```
- XML(`<rss`/`<feed`)이 보이면 → **H2 확정** → §4-A 적용.
- 여전히 HTML이면 → (3)으로.

**(3) 대체 RSS 후보 실험 (live 최대 2회)**: 아래 후보를 위와 같은 방식으로 **위에서부터 성공할 때까지만** 시도 (전부 UNKNOWN — 존재 보장 없음, 실험으로 확정):
1. `https://rsshub.app/apnews/topics/apf-topnews` — 과거 403이었으나 재확인 가치 있음
2. `https://news.google.com/rss/search?q=site:apnews.com&hl=en-US&gl=US&ceid=US:en` — **Google News RSS 프록시 (가장 확실한 영구 path)**. AP 자체 feed가 아니라는 trade-off가 있으나 title/url/timestamp 완비 + 표준 RSS.

**(4) Playwright 실험 (위 전부 실패 시, live 1회)**: H3 검증 겸 HTML 수집 경로 평가:
```powershell
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_collection_probe --source ap_news --json
```
은 Route 1로 가므로 직접 못 쓴다. 06 문서의 `run_structure_explorer`(만들어진 후) 또는 `run_playwright_probe`로 `https://apnews.com/hub/ap-top-news`를 열어 기사 링크 selector가 잡히는지 확인.

## 4. 해결책별 구현 diff (진단 결과에 따라 **하나만** 적용)

### 4-A. H2 (UA 차단) 확정 시 — 소스별 UA 메타

`api_probe.py`의 `_build_request`(원본 421행)는 sec_edgar만 UA 예외다. 동일 패턴으로 일반화한다:

```python
# 원본:
    _ua = os.environ.get("SEC_USER_AGENT", _HONEST_UA) if service_id == "sec_edgar" else _HONEST_UA
# 교체:
    _ua = _HONEST_UA
    if service_id == "sec_edgar":
        _ua = os.environ.get("SEC_USER_AGENT", _HONEST_UA)
    elif probe_spec.get("browser_ua"):
        _ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
```
그리고 `_PROBE_SPEC["ap_news"]`에 `"browser_ua": True` 추가:
```python
    "ap_news": {"extra_params": {}, "meaningful_fields": [], "response_format": "xml", "browser_ua": True},
```
**준법 메모**: robots.txt가 수집 자체를 금지하는 경로면 중단해야 하지만, RSS feed는 구독 배포용 공개 자원이고 UA 정규화는 차단 우회가 아닌 호환성 조치다. CAPTCHA/로그인이 끼면 즉시 BLOCKED_TERMINAL.

### 4-B. H1 (endpoint 폐기) + 대체 feed 확보 시 — endpoint 교체

`_SERVICE_CONFIGS["ap_news"]`의 endpoint를 실험에서 확정된 URL로 교체하고 note를 갱신:
```python
    "ap_news": {
        "keys": [], "auth": "none",
        "endpoint": "<실험으로 확정된 RSS URL>",
        "free_plan": "Public RSS — no key required",
        "docs_url": "https://apnews.com",
        "layer": "document_discovery",
        "note": "hub?format=feed 경로 HTML 에러페이지 전환(2026-06-12) → <선택 경로> (2026-06-13 검증)",
    },
```
Google News 프록시를 채택한 경우 추가 주의 2건을 note에 명시: ① item link가 news.google.com redirect URL — 정규화 단계에서 원 URL 해석 필요(09 문서 §2-4 기법) ② evidence_level은 AP 직접 feed보다 한 단계 낮게 (source_registry.yaml의 ap_news 항목에 주석으로 동기화).

### 4-C. H3 (JS 필요) 확정 시 — Route 2 전환

`_PROBE_SPEC`에서 ap_news entry를 **삭제**하면 Route 1 조건(`has_probe_spec`)이 꺼지고, `playwright_probe_sites.yaml`에 site spec을 신설해 Route 2로 보낸다 (07 문서의 신규 site 등록 절차를 그대로 따름 — selectors는 06 explorer로 도출). 이 경로는 비용이 커서 최후 수단이다.

## 5. 신규 테스트

`ingestion/tests/unit/test_ap_news_recovery.py` — 채택 경로에 따라:
- 4-A 채택: `_build_request("ap_news", config, _PROBE_SPEC["ap_news"])`의 headers["User-Agent"]가 Mozilla로 시작함을 단언 + sec_edgar/기타 소스는 기존 UA 유지 단언 (회귀 방지).
- 4-B 채택: `_SERVICE_CONFIGS["ap_news"]["endpoint"]`가 새 URL임을 단언 + (Google 프록시 경우) endpoint에 `news.google.com/rss`가 포함됨을 단언.
- 공통: 저장된 정상 RSS 샘플(fixture 문자열)로 `extract_sample_items("ap_news", <tmp 파일>)`이 title+url+published_at을 채우는지 단언.

## 6. live 최종 검증 + 종결 기준

```powershell
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_primary_seed_live_audit --sources ap_news
```
- [ ] status=LIVE_SUCCESS, items_found ≥ 5
- [ ] sample에 title + url + published_at(timestamp) 전부 존재 → seed_ready **yes**
- [ ] 채택 가설·기각 가설·증거를 체크리스트 #3에 기록, docs/70의 ap_news 행 갱신
- [ ] 전체 pytest 통과
- 4 iteration 내 모든 경로 실패 시: `BLOCKED_TERMINAL(AP feed 미제공)` + Google News 프록시조차 실패한 사유 명기 — 단 이는 매우 비현실적이므로 그 전에 가설을 의심하라.

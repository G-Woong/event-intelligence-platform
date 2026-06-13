# 07. Playwright 소스 5종 — Route 2 구조 결함 수정 + selector 보강 + 본문 추출 + 검색 영구 path

> 대상: signal_bz, google_trending_now, loword, dcinside, eu_press_corner (+ 검색 path는 dcinside 우선). 선행: **06 완료** (structure explorer), 01. 변경: `collection_probe.py`, `site_specs.py`, `playwright_probe_sites.yaml`, `playwright_probe.py`, 신규 `article_body_extractor.py`, 테스트.

## 1. 해석 — RISK-S05의 **구조적** 원인 (개별 selector 문제가 아니다)

코드 조사로 확정한 사실: 수집 경로가 2벌 있고 능력이 비대칭이다.

| 능력 | `run_playwright_probe` (probes/playwright_probe.py) | Route 2 (collection_probe → CloudBrowserLikeStrategy) |
|------|------|------|
| `{query}`/`{region}` URL 템플릿 | **있음** (94-103행) | 없음 (`_SERVICE_CONFIGS.endpoint` 원문 사용) |
| site spec `wait_after_ms`/`wait_for`/scroll | **있음** (110-122행) | **없음** — `fetch_with_playwright_sync`는 이 인자를 받지 않음 |
| selector 기반 item 추출 (`items_found`) | **있음** (`_extract_list_items`) | 없음 (html 존재 여부만 → items 1) |
| click_target 본문 추출 | **있음** (200-221행, trafilatura) | 없음 |
| 429 감지 → `record_rate_limited` + `next_retry_at` | **있음** (148-171행) | 감지·기록은 하나 **ProbeResult가 없어 health store에 next_retry_at 미전달** |

직전 audit은 Route 2를 탔다. 따라서 eu_press_corner(SPA, wait 4000ms 필요)는 **렌더 완료 전 DOM**에서 selector를 찾았고, 당연히 page title만 나왔다. 즉 "selector 미매칭" 진단의 상당 부분은 selector가 아니라 **Route 2가 site spec의 렌더링 힌트를 버리는 결함**이다. 그러므로 이 문서의 1순위 수정은 selector 교체가 아니라 **Route 2가 site spec 보유 소스를 `run_playwright_probe`로 위임**하게 만드는 것이고, selector 교체는 그 후에도 실패하는 소스에만 적용한다(최소 변경 원칙).

## 2. 구조 수정 diff — Route 2 위임

### 2-1. `ingestion/fetch_strategies/collection_probe.py`

Route 2 블록(원본 67-94행)을 다음으로 교체:

```python
    # Route 2: Playwright-required or external-signal
    if source_id in _PLAYWRIGHT_FIRST_SOURCES or _is_playwright_required(source_id, service_config):
        # site spec 보유 소스는 run_playwright_probe로 위임 — URL 템플릿/wait 힌트/
        # selector 추출/click-through/429 기록을 단일 경로로 통일 (docs/RISK-S05 구조 수정).
        site_spec = None
        try:
            from ingestion.probes.site_specs import load_site_specs
            site_spec = load_site_specs().get(source_id)
        except Exception:
            pass
        if site_spec is not None and not site_spec.deferred:
            from ingestion.probes.playwright_probe import run_playwright_probe
            probe_result = run_playwright_probe(
                source_id, query=query, max_items=max_items
            )
            ap = probe_result.artifact_paths or {}
            return _update_health(CollectionProbeResult(
                source_id=source_id,
                status=probe_result.status,
                strategy_used="playwright_site_spec",
                items_found=probe_result.items_found,
                probe_result=probe_result,
                artifact_paths=ArtifactPaths(
                    raw_payload=ap.get("raw_signal"),
                    screenshot=ap.get("screenshot"),
                ),
                error_category=probe_result.error_category,
                next_action=probe_result.next_action,
            ))

        # site spec 없는 playwright 소스만 기존 generic 렌더 경로 유지
        endpoint = (service_config or {}).get("endpoint", "")
        if not endpoint:
            return CollectionProbeResult(
                source_id=source_id,
                status="UNKNOWN",
                error_category="no_endpoint",
                next_action="add_endpoint_to_service_config",
            )
        from ingestion.fetch_strategies.cloud_browser_like import CloudBrowserLikeStrategy
        rendered = CloudBrowserLikeStrategy().fetch(endpoint, source_id)
        ...  # (이하 기존 코드 그대로 — 수정하지 않는다)
```

효과 3가지: ① `probe_result.next_retry_at`이 `_update_health`(원본 168-169행)로 흘러 **Route 2의 429도 health gate가 잡는다** ② `{query}` 템플릿 동작 (05의 trends_explore 통합 경로) ③ items_found가 진짜 item 수가 된다.

**ArtifactPaths 필드 확인**: `ingestion/fetch_strategies/models.py`에서 `ArtifactPaths`가 `raw_payload/screenshot` 외 어떤 필드(`rendered_dom`?)를 갖는지 확인하고 있으면 `ap.get("rendered_dom")`도 매핑하라. 없는 필드를 추가하지는 말 것.

**기존 테스트 회귀 처리(중요)**: `Select-String -Path ingestion\tests -Pattern "CloudBrowserLikeStrategy" -Recurse`로 Route 2를 mock하는 테스트를 찾아라. site spec 보유 소스(signal_bz 등)로 Route 2를 검증하던 테스트는 이번 위임의 **직접 결과**로 깨진다 — 해당 테스트만 `run_playwright_probe`를 monkeypatch(collection_probe 모듈 namespace 기준 `ingestion.probes.playwright_probe.run_playwright_probe`)하도록 갱신한다. fallback 경로(CloudBrowserLike)는 site spec이 없는 가짜 source_id로 검증을 유지한다. 무관 테스트는 건드리지 않는다.

### 2-2. `_audit_common.collect_samples` 정합

위임 후 Route 2 결과에는 `extraction.rendered_page`가 없고 `raw_payload=raw_signal`(JSON 배열 `[{"keyword","url"}...]`)이 온다. `_sample_from_json`의 generic fallback이 root 리스트를 처리하지만 title 키 후보에 `keyword`가 이미 있어(`_GENERIC_TITLE_KEYS`) **추가 수정 없이 동작한다.** 단위 테스트로 고정하라(§7).

## 3. 검색 영구 path + 본문 추출 (커뮤니티/탐색형)

### 3-1. `SiteSpec.search_url` 필드 신설

`ingestion/probes/site_specs.py`의 dataclass에 1필드, 로더에 1줄:

```python
    search_strategy: str = ""
    search_url: str = ""          # ← 추가: query 검색 진입용 URL 템플릿 ({query})
```
```python
            search_strategy=data.get("search_strategy", ""),
            search_url=data.get("search_url", ""),
```

### 3-2. `playwright_probe.py` — query 시 검색 URL 사용 + 본문 캐스케이드

URL 빌드(원본 94-103행) 직전에 분기 추가:

```python
    # Build URL from template — query가 있고 search_url이 정의된 사이트는 검색 진입
    url = spec.start_url
    if query and getattr(spec, "search_url", ""):
        url = spec.search_url
    if region:
        ...  # (기존 치환 로직 그대로 — search_url에도 동일 적용됨)
```

click-through 본문 추출(원본 214-221행)의 trafilatura 직접 호출을 §4의 캐스케이드로 교체:

```python
            try:
                from ingestion.fetch_strategies.article_body_extractor import extract_article_body
                body = extract_article_body(detail_html, detail_url)
                if body and body.get("body"):
                    items_extracted += 1
                    from ingestion.core.artifact_store import save_extracted_payload
                    ep = save_extracted_payload(run_id, site_id, detail_uh, {
                        "url": detail_url,
                        "title": body.get("title"),
                        "body": body["body"][:5000],
                        "method": body.get("method"),
                    })
                    artifact_paths[f"extracted_body_{items_extracted}"] = str(ep)
            except Exception as exc:
                logger.warning("body extraction failed for %s: %s", detail_url, exc)
```
(기존 코드는 본문을 추출하고도 **screenshot 경로**를 artifact로 기록하는 결함이 있었다 — 이번에 본문 payload 저장으로 교정. 5000자 상한은 저장 비용 통제이며 보고서 절단 규칙과 별개다.)

### 3-3. dcinside YAML — 검색 path + 본문 selector

`playwright_probe_sites.yaml`의 dcinside에 2키 추가 (selectors는 explorer 결과로 갱신하기 전까지 유지):

```yaml
  dcinside:
    ...
    search_url: "https://search.dcinside.com/combine/q/{query}"
    selectors:
      list:
        - "tr.ub-content .gall_tit a"
        - ".ub-content td.gall_tit a"
        - ".listwrap .ub-content a"
        # explorer 검증 후: 검색 결과 페이지용 selector를 여기 앞에 추가
        # (검색 페이지와 갤러리 목록 페이지는 DOM이 다르다 — 둘 다 list에 누적)
      click_target:
        - "tr.ub-content .gall_tit a"
```
**노이즈 정책(사용자 승인)**: 커뮤니티 본문은 노이즈를 감수하고 수집한다. evidence_level=low 유지, 본문은 추출만 하고 게시/생성에 쓰지 않는다(기존 헌법). min_interval_minutes 10 준수.

eu_press_corner는 공식 검색이 있으면 동일 패턴(`search_url: "https://ec.europa.eu/commission/presscorner/home/en?keywords={query}"` — **실측으로 URL 형식 확인 후** 기입, 추측 기입 금지).

## 4. 신규 모듈 — `ingestion/fetch_strategies/article_body_extractor.py` (본문 추출 캐스케이드)

```python
"""본문 추출 캐스케이드: trafilatura → readability → DOM 휴리스틱.

각 단계는 실패(예외/빈 본문/200자 미만) 시 다음 단계로 폴백한다.
반환: {"title", "body", "method"} 또는 None. 네트워크 호출 없음 (html 입력 전제).
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger("ingestion.fetch_strategies.article_body_extractor")
_MIN_BODY_CHARS = 200


def extract_article_body(html: str, url: str) -> Optional[dict]:
    if not html:
        return None
    for method, fn in (
        ("trafilatura", _try_trafilatura),
        ("readability", _try_readability),
        ("dom_heuristic", _try_dom_heuristic),
    ):
        try:
            out = fn(html, url)
        except Exception as exc:
            logger.debug("%s failed for %s: %s", method, url, exc)
            continue
        if out and out.get("body") and len(out["body"]) >= _MIN_BODY_CHARS:
            out["method"] = method
            return out
    return None
```
`_try_trafilatura`는 기존 `extract_with_trafilatura`, `_try_dom_heuristic`은 기존 `extract_with_dom_heuristic`을 감싸 `{"title","body"}`로 정규화한다 (`ExtractionResult`의 실제 필드명을 `ingestion/core/extraction_result.py`에서 확인해 매핑하라). `_try_readability`는 `readability-lxml`(이미 설치됨)의 `Document(html).summary()` + `short_title()`를 쓰고, summary HTML은 BeautifulSoup `get_text("\n", strip=True)`로 평문화한다. 기존 `ingestion/tools/readability_extractor.py`가 이미 이 일을 하면 **그것을 감싸고 새로 만들지 마라** (먼저 읽어볼 것).

## 5. 소스별 종결 절차 (루프 STEP A~E — 반드시 이 순서로 싸게부터)

**공통 STEP A (재현·재평가)**: §2 위임 적용 후, 소스별로 먼저 기존 selector 그대로 1회 재시도:
```powershell
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_playwright_probe --site <id> --max-items 10
```
**여기서 items≥3이 나오면 selector는 처음부터 유효했던 것** (Route 2 결함이 원인) — explorer 없이 즉시 PASS 후보. 실패한 소스만 STEP B(explorer)로.

| 소스 | STEP A 후 추가 힌트 (실패 시) | 종결 기준 |
|------|------------------------------|----------|
| **eu_press_corner** | SPA — STEP A에서 해결될 확률 최고(wait 4000ms+wait_for가 이제 적용됨). 그래도 0건이면 explorer의 **network capture**로 presscorner 내부 JSON API를 찾아라 (보도자료 목록 XHR이 있을 가능성 높음 → Route 1 전환이 상책) | item ≥5 (보도자료 title+detail URL) |
| **google_trending_now** | selector 이전에 **RSS 실험 1회**: `https://trends.google.com/trending/rss?geo=KR` 를 httpx(브라우저 UA)로 GET — 유효한 RSS면 `_SERVICE_CONFIGS.google_trending_now.endpoint`를 이 URL로 바꾸고 `_PROBE_SPEC`에 `{"response_format":"xml"}` entry 추가 + `status_override` 제거로 **Route 1 전환** (DOM 의존 제거가 근본 해결). RSS가 죽었으면 explorer (단, gate 7200s 준수) | keyword ≥5 + (가능 시) traffic 메타 |
| **signal_bz** | 이미 3건 성공 — 목표는 ≥10. explorer로 두 번째 rank 그룹 selector(`.rank-layer` 변형) 확인. `_extract_list_items`에 DOM 순서 기반 `"rank": i+1` 필드 추가(1줄) | keyword ≥10 + rank 필드 |
| **loword** | styled-components(해시 클래스)라 selector는 본질적으로 fragile. explorer **network capture 최우선** — XHR JSON 발견 시 그 endpoint를 기록하되, 비공식 API이므로 Route 1 등록 시 note에 "unofficial, 변경 위험" 명시. JSON도 없으면 inline style selector 갱신 + `stability: fragile` 주석 유지 | keyword ≥5 |
| **dcinside** | ① 목록: STEP A 재시도 ② 검색: §3-3 적용 후 `run_playwright_probe --site dcinside --query "삼성전자" --max-items 5` ③ 본문: click_target 경유 `items_extracted ≥1` 확인. 검색 페이지 selector는 explorer로 도출 | 목록 ≥3 + 검색 ≥3 + 본문 추출 ≥1 (e2e) |

각 소스 PASS 시 `playwright_probe_sites.yaml`의 해당 entry에 `# verified: 2026-06-13 items=N` 주석을 남겨라 (다음 깨짐 때 기준선).

## 6. rate limit 메모

site spec `min_interval_minutes`는 참고치일 뿐 강제 게이트가 아니다(직전 라운드와 동일). 이 라운드의 검증 호출은 소스당 STEP A 1회 + 검증 1~2회 수준이라 안전하나, **같은 소스 연속 호출 사이 최소 60초**를 지켜라 (playwright_browser_tool의 2초 글로벌 딜레이만으로는 부족).

## 7. 신규 테스트 — `ingestion/tests/unit/test_route2_delegation.py`

```python
def test_route2_delegates_to_playwright_probe_for_spec_sites(monkeypatch):
    from ingestion.fetch_strategies import collection_probe as cp
    from ingestion.probes.models import ProbeResult
    captured = {}

    def fake_probe(site_id, query=None, region=None, max_items=10):
        captured.update(site_id=site_id, query=query, max_items=max_items)
        return ProbeResult(source_id=site_id, method="playwright",
                           status="LIVE_SUCCESS", items_found=7)

    monkeypatch.setattr("ingestion.probes.playwright_probe.run_playwright_probe", fake_probe)
    result = cp.run_collection_probe("signal_bz", query="삼성", max_items=10, force=True)
    assert captured["site_id"] == "signal_bz" and captured["query"] == "삼성"
    assert result.items_found == 7
    assert result.strategy_used == "playwright_site_spec"


def test_route2_falls_back_to_cloud_browser_without_spec(monkeypatch):
    # site spec에 없는 playwright 소스: load_site_specs를 빈 dict로 패치하고
    # CloudBrowserLikeStrategy.fetch를 mock — 기존 경로 보존 검증
    ...


def test_search_url_used_when_query_present(monkeypatch):
    # 05 문서의 fake_open_page 패턴 재사용: dcinside + query → search.dcinside.com URL 캡처
    ...


def test_body_cascade_falls_back(monkeypatch):
    from ingestion.fetch_strategies.article_body_extractor import extract_article_body
    import ingestion.fetch_strategies.article_body_extractor as abe
    monkeypatch.setattr(abe, "_try_trafilatura", lambda h, u: None)
    html = "<html><body><article><h1>제목</h1>" + "<p>본문 문단입니다. " * 30 + "</p></article></body></html>"
    out = extract_article_body(html, "https://x.test/1")
    assert out and out["method"] in ("readability", "dom_heuristic")
    assert len(out["body"]) >= 200


def test_collect_samples_reads_raw_signal_json(tmp_path):
    # Route 2 위임 후 raw_signal([{"keyword","url"}]) 경로 샘플 추출 (§2-2 고정)
    import json
    p = tmp_path / "sig.json"
    p.write_text(json.dumps([{"keyword": "실검1", "url": "https://a"}]), encoding="utf-8")
    from ingestion.runners._audit_common import extract_sample_items
    samples = extract_sample_items("signal_bz", str(p))
    assert samples and samples[0]["title"] == "실검1"
```

`...` 두 건은 위 패턴대로 완성하라. 전체 회귀 + 기존 Route 2 테스트 갱신분 포함 통과가 STEP D다.

## 8. 종결 기준 (체크리스트 #6a~6d, #7, #8)

- [ ] Route 2 위임 diff 적용 + 위 테스트 + 전체 회귀 통과
- [ ] 5개 소스 각각 §5 표의 종결 기준 충족 (증거: run_playwright_probe 출력 + raw_signal/extracted artifact 경로)
- [ ] dcinside e2e: query → 검색 → 목록 → 본문 1건 (영구 path 실증)
- [ ] YAML verified 주석 + docs/70 해당 행 갱신
- [ ] 4 iteration 초과 소스는 사유와 함께 BLOCKED_TERMINAL/DEFERRED 분류 (예: trending_now가 매 호출 429면 "RSS 전환 실험 결과"까지 기록)

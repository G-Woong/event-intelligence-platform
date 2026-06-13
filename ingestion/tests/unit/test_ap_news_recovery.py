"""ap_news 복구(03 문서) 단위 테스트 — 네트워크 없음.

진단 결과: H1(endpoint 폐기/param 무시 → 홈 HTML). 브라우저 UA로도 동일 HTML이라
H2(UA 차단) 기각. 채택 경로 = §4-B Google News RSS 프록시 endpoint 교체.

하단 test_anomaly_* 3종은 직전 턴에서 발견된 이상현상이 재발하지 않도록 고정한다:
  - 이상현상1: 폐기된 AP hub RSS endpoint가 active endpoint로 다시 들어오는 것
  - 이상현상2: rsshub(Cloudflare 403) 후보가 active endpoint로 선택되는 것
  - 이상현상3: query를 endpoint URL에 박아 httpx 빈-params가 query string을 덮어써 404 나는 것
"""
from ingestion.runners._audit_common import extract_sample_items
from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS

# 폐기 확정 endpoint — active config에 다시 들어오면 안 된다 (root cause: param 무시 → 홈 HTML 200)
_RETIRED_AP_ENDPOINT = "https://apnews.com/hub/ap-top-news?format=feed&type=rss"


def test_ap_news_endpoint_is_google_news_proxy():
    endpoint = _SERVICE_CONFIGS["ap_news"]["endpoint"]
    # H1 확정 후 §4-B 채택: hub?format=feed 가 아닌 Google News RSS 프록시
    assert "news.google.com/rss" in endpoint
    # query는 endpoint가 아닌 params로 전달(httpx 빈-params 덮어쓰기 404 회피)
    assert "?" not in endpoint


def test_ap_news_query_params_filter_apnews():
    from ingestion.probes.api_probe import _PROBE_SPEC
    params = _PROBE_SPEC["ap_news"]["extra_params"]
    assert params.get("q") == "site:apnews.com"  # AP 기사만 site: 필터
    assert params.get("ceid")  # Google News RSS 필수 로케일 파라미터


# 정상 RSS 샘플(Google News 프록시 형식) — extract_sample_items가 title+url+published_at 채움
_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>"site:apnews.com" - Google News</title>
<item>
  <title>Anthropic takes latest AI models offline to comply with export controls - AP News</title>
  <link>https://news.google.com/rss/articles/CBMabc123</link>
  <guid>CBMabc123</guid>
  <pubDate>Sat, 13 Jun 2026 02:36:00 GMT</pubDate>
  <description>&lt;a href="https://apnews.com/article/x"&gt;Anthropic...&lt;/a&gt;</description>
</item>
<item>
  <title>Markets rally as central banks hold rates - AP News</title>
  <link>https://news.google.com/rss/articles/CBMdef456</link>
  <guid>CBMdef456</guid>
  <pubDate>Sat, 13 Jun 2026 01:10:00 GMT</pubDate>
  <description>&lt;a href="https://apnews.com/article/y"&gt;Markets...&lt;/a&gt;</description>
</item>
</channel></rss>
"""


def test_extract_sample_items_parses_google_news_rss(tmp_path):
    f = tmp_path / "ap_news_sample.xml"
    f.write_text(_SAMPLE_RSS, encoding="utf-8")
    samples = extract_sample_items("ap_news", str(f), max_samples=3)
    assert len(samples) == 2
    first = samples[0]
    assert first["title"] and "Anthropic" in first["title"]
    assert first["url"] and first["url"].startswith("https://news.google.com/rss")
    assert first["published_at"] and "2026" in first["published_at"]


# ── 이상현상 회귀 고정 ────────────────────────────────────────────────────────

def test_anomaly1_retired_ap_hub_endpoint_not_active():
    """이상현상1: 폐기된 AP hub RSS endpoint가 active config로 다시 들어오면 실패."""
    endpoint = _SERVICE_CONFIGS["ap_news"]["endpoint"]
    assert endpoint != _RETIRED_AP_ENDPOINT, "폐기된 AP hub RSS endpoint가 재등장했다"
    assert "apnews.com/hub" not in endpoint, "AP hub 경로(홈 HTML 200 반환)는 폐기되었다"


def test_anomaly2_rsshub_not_selected_as_active_endpoint():
    """이상현상2: Cloudflare 403으로 거부된 rsshub 후보가 active endpoint면 실패."""
    endpoint = _SERVICE_CONFIGS["ap_news"]["endpoint"]
    assert "rsshub" not in endpoint, "rsshub(Cloudflare 403 차단)는 active runtime path로 쓰지 않는다"


def test_anomaly3_query_in_params_not_in_endpoint_url():
    """이상현상3: query는 endpoint URL이 아니라 extra_params에만 둔다.

    endpoint에 ?q=...를 박으면 _build_request가 params={...}를 따로 넘기지 않는 한
    httpx가 빈 params로 기존 query string을 덮어써 /rss/search 404가 난다(실측).
    """
    from ingestion.probes.api_probe import _PROBE_SPEC, _build_request
    endpoint = _SERVICE_CONFIGS["ap_news"]["endpoint"]
    assert "?" not in endpoint and "q=" not in endpoint, \
        "query string을 endpoint에 박으면 httpx 빈-params 덮어쓰기로 404가 재발한다"

    method, url, params, headers, json_body, used_secrets = _build_request(
        "ap_news", _SERVICE_CONFIGS["ap_news"], _PROBE_SPEC["ap_news"]
    )
    assert "?" not in url, "_build_request url에도 query string이 없어야 한다"
    # Google News RSS 필수 파라미터가 params로 정상 전달되는지 (이것이 404 회피의 핵심)
    for key in ("q", "hl", "gl", "ceid"):
        assert key in params, f"Google News RSS 파라미터 '{key}'가 params로 전달되어야 한다"
    assert params["q"] == "site:apnews.com"

    # httpx가 실제 요청 URL을 구성할 때 params가 query string으로 보존되는지 고정
    import httpx
    built = httpx.Client().build_request("GET", url, params=params).url
    assert "q=site" in str(built), "params가 실제 요청 query string으로 보존되어야 한다(404 회귀 방지)"
    assert str(built).startswith("https://news.google.com/rss/search?")


def test_canonical_url_attached_when_resolve_enabled(tmp_path, monkeypatch):
    """resolve_canonical=True면 sample에 canonical_url이 부착된다(url_resolver 연결 고정)."""
    import ingestion.tools.url_resolver as url_resolver

    def _fake_resolve(url, **kwargs):
        # news.google.com redirect URL → 원본 apnews.com (mock)
        return "https://apnews.com/article/resolved"

    monkeypatch.setattr(url_resolver, "resolve", _fake_resolve)

    f = tmp_path / "ap_news_sample.xml"
    f.write_text(_SAMPLE_RSS, encoding="utf-8")
    samples = extract_sample_items("ap_news", str(f), max_samples=2, resolve_canonical=True)
    assert samples
    assert samples[0]["canonical_url"] == "https://apnews.com/article/resolved"
    # resolve_canonical 기본값(off)에서는 canonical_url 키가 없어야 한다(순수 파싱 무영향)
    plain = extract_sample_items("ap_news", str(f), max_samples=2)
    assert "canonical_url" not in plain[0]


def test_canonical_via_browser_escalates_google_news_urls(tmp_path, monkeypatch):
    """canonical_via_browser=True면 news.google.com URL은 브라우저 resolver로 승격된다."""
    import ingestion.tools.url_resolver as url_resolver

    def _fake_browser(url, **kwargs):
        return "https://apnews.com/article/via-browser"

    def _fake_http(url, **kwargs):
        return url  # HTTP 경로는 google에 머문다(실제 동작 모사)

    monkeypatch.setattr(url_resolver, "resolve_via_browser", _fake_browser)
    monkeypatch.setattr(url_resolver, "resolve", _fake_http)

    f = tmp_path / "ap_news_sample.xml"
    f.write_text(_SAMPLE_RSS, encoding="utf-8")
    samples = extract_sample_items(
        "ap_news", str(f), max_samples=2,
        resolve_canonical=True, canonical_via_browser=True,
    )
    # news.google.com URL이므로 브라우저 승격 경로로 apnews 원본 확보
    assert samples[0]["canonical_url"] == "https://apnews.com/article/via-browser"

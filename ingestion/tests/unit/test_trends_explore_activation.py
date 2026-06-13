"""google_trends_explore 활성화(05) 단위 테스트 — 전부 네트워크 없음.

DEFERRED의 원인은 코드 부재가 아니라 audit runner 플래그(기본 off)였다.
spec/정책/URL 템플릿 치환이 이미 구현돼 있음을 고정하고, 보수적 rate 정책
(min_interval 7200s, 429 재시도 0회)이 유지되는지 회귀로 묶는다.
"""


def test_spec_not_deferred_and_has_query_template():
    from ingestion.probes.site_specs import load_site_specs
    spec = load_site_specs()["google_trends_explore"]
    assert spec.deferred is False
    assert "{query}" in spec.start_url and "{region}" in spec.start_url
    assert spec.min_interval_minutes >= 120


def test_rate_policy_is_conservative():
    from ingestion.core.rate_limit_policy import load_rate_limit_policy
    p = load_rate_limit_policy("google_trends_explore")
    assert p.min_interval_seconds >= 7200
    assert p.max_retries_on_429 == 0          # 루프 내 재시도 금지의 코드화
    assert p.cache_ttl_seconds >= 7200


def test_url_template_substitution(monkeypatch):
    # playwright_probe의 치환 로직 검증: open_page를 가로채 URL만 캡처, html=None 반환
    from ingestion.probes import playwright_probe as pp
    captured = {}

    async def fake_open_page(url, **kw):
        captured["url"] = url
        return None

    monkeypatch.setattr(pp, "open_page", fake_open_page)
    pp.run_playwright_probe("google_trends_explore", query="이재명 멜로니", region="KR")
    assert "geo=KR" in captured["url"]
    assert "{query}" not in captured["url"] and "{region}" not in captured["url"]
    assert "%EC%9D%B4%EC%9E%AC%EB%AA%85" in captured["url"]  # quote_plus 인코딩 확인

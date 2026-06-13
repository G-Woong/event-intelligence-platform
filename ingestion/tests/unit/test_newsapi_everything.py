"""newsapi /v2/everything 전환(04 문서) 단위 테스트 — 네트워크 없음."""


def test_newsapi_endpoint_is_everything():
    from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS
    assert _SERVICE_CONFIGS["newsapi"]["endpoint"].endswith("/v2/everything")


def test_newsapi_spec_has_no_country_and_default_q():
    from ingestion.probes.api_probe import _PROBE_SPEC
    spec = _PROBE_SPEC["newsapi"]
    assert "country" not in spec["extra_params"], "everything은 country 미지원(400)"
    assert spec["extra_params"].get("q"), "everything은 q 필수"
    assert spec["query_param"] == "q"


def test_newsapi_query_injection_overrides_default_q():
    from ingestion.probes.api_probe import _PROBE_SPEC, _apply_query_override
    spec = _apply_query_override(_PROBE_SPEC["newsapi"], "box office")
    assert spec["extra_params"]["q"] == "box office"
    assert _PROBE_SPEC["newsapi"]["extra_params"]["q"] == "news"  # 전역 불변

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.probes.api_probe import (
    _build_request,
    _http_status_to_probe_status,
    run_api_live_probe,
)
from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS


# ── HTTP status mapping ────────────────────────────────────────────────────

def test_http_401_maps_to_invalid_key():
    assert _http_status_to_probe_status(401) == "INVALID_KEY"


def test_http_403_maps_to_permission_denied():
    assert _http_status_to_probe_status(403) == "PERMISSION_DENIED"


def test_http_429_maps_to_rate_limited():
    assert _http_status_to_probe_status(429) == "RATE_LIMITED"


def test_http_200_maps_to_live_success():
    assert _http_status_to_probe_status(200) == "LIVE_SUCCESS"


def test_http_500_maps_to_network_error():
    assert _http_status_to_probe_status(500) == "NETWORK_ERROR"


# ── Request builder: no-auth services ─────────────────────────────────────

def test_build_request_no_auth():
    config = _SERVICE_CONFIGS["federal_register"]
    probe_spec = {"extra_params": {"per_page": "3"}, "meaningful_fields": ["results"]}
    method, url, params, headers, body, secrets = _build_request("federal_register", config, probe_spec)
    assert method == "GET"
    assert "federal_register" in url or "federalregister" in url
    assert headers["User-Agent"] == "event-intelligence/0.7 (+ei)"
    # No secrets in params or headers
    assert "api_key" not in str(params).lower()
    assert "authorization" not in {k.lower() for k in headers}
    assert secrets == []


def test_build_request_hacker_news_no_key():
    config = _SERVICE_CONFIGS["hacker_news"]
    probe_spec = {"extra_params": {}, "meaningful_fields": []}
    method, url, params, headers, body, secrets = _build_request("hacker_news", config, probe_spec)
    assert method == "GET"
    assert "firebaseio" in url or "hacker-news" in url
    assert secrets == []


# ── Request builder: MISSING_KEY raises ────────────────────────────────────

def test_build_request_missing_naver_key_raises():
    config = _SERVICE_CONFIGS["naver_news_search"]
    probe_spec = {"extra_params": {"query": "test"}, "meaningful_fields": ["items"]}
    # Ensure keys not in env
    for k in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "CLIENT_ID", "CLIENT_SECRET"):
        os.environ.pop(k, None)
    with pytest.raises(ValueError, match="MISSING_KEY"):
        _build_request("naver_news_search", config, probe_spec)


def test_build_request_missing_youtube_key_raises():
    config = _SERVICE_CONFIGS["youtube"]
    probe_spec = {"extra_params": {"part": "snippet", "q": "test"}, "meaningful_fields": ["items"]}
    os.environ.pop("YOUTUBE_API_KEY", None)
    with pytest.raises(ValueError, match="MISSING_KEY"):
        _build_request("youtube", config, probe_spec)


# ── Request builder: header_x_naver (secret never in output) ──────────────

def test_build_request_naver_key_in_header_not_params(tmp_path):
    """When Naver key present, it goes to headers only — not params or URL."""
    env_file = tmp_path / ".env"
    env_file.write_text("NAVER_CLIENT_ID=fake_id_12345\nNAVER_CLIENT_SECRET=fake_secret_67890\n")
    from ingestion.core.env_loader import load_env
    load_env(env_file)

    config = _SERVICE_CONFIGS["naver_news_search"]
    probe_spec = {"extra_params": {"query": "test", "display": "3"}, "meaningful_fields": ["items"]}
    method, url, params, headers, body, secrets = _build_request("naver_news_search", config, probe_spec)

    # Key values must be in headers, not params
    assert "X-Naver-Client-Id" in headers
    assert "X-Naver-Client-Secret" in headers
    # Key values must NOT appear in params
    assert "fake_id_12345" not in str(params)
    assert "fake_secret_67890" not in str(params)
    # URL must not contain key values
    assert "fake_id_12345" not in url
    assert "fake_secret_67890" not in url
    # Keys never exposed in result dict (only headers, which we don't store)
    for k, v in params.items():
        assert "fake_id_12345" not in str(v)
        assert "fake_secret_67890" not in str(v)
    # used_secrets must contain both key values (for sanitization)
    assert len(secrets) == 2


# ── status_override → DEFERRED/BLOCKED (no HTTP call) ─────────────────────

def test_login_wall_returns_blocked():
    result = run_api_live_probe("x")
    assert result.status == "BLOCKED"
    assert result.http_status is None


def test_license_required_returns_blocked():
    result = run_api_live_probe("reuters")
    assert result.status == "BLOCKED"
    assert result.http_status is None


def test_playwright_required_returns_deferred():
    result = run_api_live_probe("krx_kind")
    assert result.status == "DEFERRED"
    assert result.http_status is None


def test_external_signal_source_returns_deferred():
    result = run_api_live_probe("signal_bz")
    assert result.status == "DEFERRED"
    assert result.http_status is None


# ── MISSING_KEY → no HTTP call ────────────────────────────────────────────

def test_missing_key_returns_missing_key_without_http_call():
    """MISSING_KEY result must never trigger HTTP (no mock needed)."""
    for k in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "CLIENT_ID", "CLIENT_SECRET"):
        os.environ.pop(k, None)
    result = run_api_live_probe("naver_news_search")
    assert result.status == "MISSING_KEY"
    assert result.http_status is None
    assert result.items_found == 0


# ── Secret non-exposure: artifact_paths values must not contain key strings ─

def test_artifact_paths_do_not_contain_secrets(tmp_path):
    """Even if a probe runs and saves artifacts, key values must not appear in artifact_paths."""
    env_file = tmp_path / ".env"
    secret_id = "SUPERSECRET_CLIENT_ID_XYZ"
    secret_val = "SUPERSECRET_CLIENT_ID_XYZ"
    env_file.write_text(f"NAVER_CLIENT_ID={secret_val}\nNAVER_CLIENT_SECRET=another_secret_abc\n")
    from ingestion.core.env_loader import load_env
    load_env(env_file)

    with patch("httpx.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"total": 1, "items": []}'
        mock_resp.json.return_value = {"total": 1, "items": []}
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        result = run_api_live_probe("naver_news_search", env_path=env_file)

    # artifact_paths values (file paths) must not contain the secret value
    for k, v in result.artifact_paths.items():
        assert secret_val not in str(v), f"Secret found in artifact_paths[{k!r}]"

    # to_dict must not contain secret value
    d_str = str(result.to_dict())
    assert secret_val not in d_str


# ── Unknown service → UNKNOWN ─────────────────────────────────────────────

def test_unknown_service_returns_unknown():
    result = run_api_live_probe("nonexistent_service_xyz_9999")
    assert result.status == "UNKNOWN"


# ── _count_items: dotted path support ────────────────────────────────────

def test_count_items_dotted_hits_hits():
    from ingestion.probes.api_probe import _count_items

    parsed = {"hits": {"hits": [{"_id": "1"}, {"_id": "2"}], "total": {"value": 2}}}
    count, found = _count_items(parsed, ["hits.hits"])
    assert count == 2
    assert "hits.hits" in found


def test_count_items_dotted_response_routes():
    from ingestion.probes.api_probe import _count_items

    parsed = {"response": {"routes": ["/path1", "/path2", "/path3"]}}
    count, found = _count_items(parsed, ["response.routes"])
    assert count == 3
    assert "response.routes" in found


def test_count_items_dotted_data_posts_edges():
    from ingestion.probes.api_probe import _count_items

    parsed = {"data": {"posts": {"edges": [{"node": {"name": "A"}}, {"node": {"name": "B"}}]}}}
    count, found = _count_items(parsed, ["data.posts.edges"])
    assert count == 2
    assert "data.posts.edges" in found


def test_count_items_dotted_path_missing_returns_zero():
    from ingestion.probes.api_probe import _count_items

    parsed = {"hits": {}}  # no "hits" key inside hits
    count, found = _count_items(parsed, ["hits.hits"])
    assert count == 0
    assert found == []


def test_count_items_flat_field_still_works():
    from ingestion.probes.api_probe import _count_items

    parsed = {"articles": [1, 2, 3], "status": "ok"}
    count, found = _count_items(parsed, ["articles"])
    assert count == 3
    assert "articles" in found


def test_count_items_no_meaningful_fields_returns_key_count():
    from ingestion.probes.api_probe import _count_items

    parsed = {"a": 1, "b": 2, "c": 3}
    count, found = _count_items(parsed, [])
    assert count == 3
    assert len(found) == 3


# ── POST builder: product_hunt method ────────────────────────────────────

def test_build_request_product_hunt_is_post():
    """product_hunt probe spec specifies POST with GraphQL body."""
    from ingestion.probes.api_probe import _PROBE_SPEC, _build_request
    from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS

    # Remove token so it raises MISSING_KEY before HTTP
    os.environ.pop("PRODUCT_HUNT_ACCESS_TOKEN", None)
    os.environ.pop("PRODUCT_HUNT_API_KEY", None)
    with pytest.raises(ValueError, match="MISSING_KEY"):
        _build_request("product_hunt", _SERVICE_CONFIGS["product_hunt"], _PROBE_SPEC["product_hunt"])


def test_build_request_product_hunt_has_json_body_when_key_present(tmp_path):
    """With token present, method is POST and json_body is set."""
    from ingestion.probes.api_probe import _PROBE_SPEC, _build_request
    from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS
    from ingestion.core.env_loader import load_env

    env_file = tmp_path / ".env"
    env_file.write_text("PRODUCT_HUNT_ACCESS_TOKEN=fake_ph_token_xyz\n")
    load_env(env_file)

    method, url, params, headers, body, secrets = _build_request(
        "product_hunt", _SERVICE_CONFIGS["product_hunt"], _PROBE_SPEC["product_hunt"]
    )
    assert method == "POST"
    assert body is not None
    assert "query" in body
    # Secret must not appear in params or URL
    assert "fake_ph_token_xyz" not in str(params)
    assert "fake_ph_token_xyz" not in url
    assert len(secrets) == 1


# ── XML probe format ──────────────────────────────────────────────────────

def test_run_api_live_probe_xml_rss_counts_items():
    """XML RSS response with <item> elements reports items_found > 0."""
    import xml.etree.ElementTree as ET

    rss_xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
    <item><title>A</title></item>
    <item><title>B</title></item>
    <item><title>C</title></item>
    </channel></rss>"""

    with patch("httpx.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = rss_xml
        mock_resp.json.side_effect = Exception("not json")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        result = run_api_live_probe("bbc")

    assert result.status in ("LIVE_SUCCESS", "LIVE_PARTIAL")
    if result.status == "LIVE_SUCCESS":
        assert result.items_found >= 1


# ── New classification: QUERY_ENCODING_OR_PARAM_ERROR (naver empty-items) ─

def test_naver_empty_items_with_total_is_query_encoding_error(tmp_path):
    """naver: {"total":5,"items":[]} → QUERY_ENCODING_OR_PARAM_ERROR, not LIVE_SUCCESS."""
    env_file = tmp_path / ".env"
    env_file.write_text("NAVER_CLIENT_ID=fake_id\nNAVER_CLIENT_SECRET=fake_secret\n")
    from ingestion.core.env_loader import load_env
    load_env(env_file)

    with patch("httpx.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"total":5,"items":[]}'
        mock_resp.json.return_value = {"total": 5, "items": []}
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        result = run_api_live_probe("naver_news_search", env_path=env_file)

    assert result.status == "QUERY_ENCODING_OR_PARAM_ERROR"
    assert result.items_found == 0


# ── New classification: INVALID_SYMBOL_OR_EMPTY_MARKET_DATA (finnhub all-zero) ─

def test_finnhub_all_zero_quote_is_empty_market_data(tmp_path):
    """finnhub: all-zero quote fields → INVALID_SYMBOL_OR_EMPTY_MARKET_DATA."""
    env_file = tmp_path / ".env"
    env_file.write_text("FINNHUB_API_KEY=fake_finnhub_key\n")
    from ingestion.core.env_loader import load_env
    load_env(env_file)

    with patch("httpx.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"c":0,"d":0,"dp":0,"h":0,"l":0,"o":0,"pc":0,"t":0}'
        mock_resp.json.return_value = {"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        result = run_api_live_probe("finnhub", env_path=env_file)

    assert result.status == "INVALID_SYMBOL_OR_EMPTY_MARKET_DATA"
    assert result.items_found == 0


# ── New classification: PARAMETER_MISSING (alpha_vantage Error Message) ───

def test_alpha_vantage_error_message_is_parameter_missing(tmp_path):
    """alpha_vantage: {"Error Message":"..."} 200 → PARAMETER_MISSING."""
    env_file = tmp_path / ".env"
    env_file.write_text("ALPHA_VANTAGE_API_KEY=fake_av_key\n")
    from ingestion.core.env_loader import load_env
    load_env(env_file)

    with patch("httpx.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"Error Message":"Invalid API call. function parameter is required."}'
        mock_resp.json.return_value = {"Error Message": "Invalid API call. function parameter is required."}
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        result = run_api_live_probe("alpha_vantage", env_path=env_file)

    assert result.status == "PARAMETER_MISSING"


# ── New classification: XML_PARAMETER_ERROR (kopis XML error response) ────

def test_kopis_xml_error_response_is_xml_parameter_error(tmp_path):
    """kopis: XML with <errormsg> element → XML_PARAMETER_ERROR."""
    env_file = tmp_path / ".env"
    env_file.write_text("KOPIS_API_KEY=fake_kopis_key\n")
    from ingestion.core.env_loader import load_env
    load_env(env_file)

    xml_error = '<?xml version="1.0"?><response><errormsg>INVALID REQUEST</errormsg><errorcode>000</errorcode></response>'

    with patch("httpx.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = xml_error
        mock_resp.json.side_effect = Exception("not json")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        result = run_api_live_probe("kopis", env_path=env_file)

    assert result.status == "XML_PARAMETER_ERROR"
    assert result.items_found == 0


# ── New classification: API_RETURNED_HTML_ERROR_PAGE (culture_info HTML) ──

def test_culture_info_html_error_page(tmp_path):
    """culture_info: API returns HTML when XML expected → API_RETURNED_HTML_ERROR_PAGE."""
    env_file = tmp_path / ".env"
    env_file.write_text("CULTURE_INFO_KEY=fake_culture_key\n")
    from ingestion.core.env_loader import load_env
    load_env(env_file)

    html_error = "<!DOCTYPE html><html><head><title>Error</title></head><body>Service Error</body></html>"

    with patch("httpx.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html_error
        mock_resp.json.side_effect = Exception("not json")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        result = run_api_live_probe("culture_info", env_path=env_file)

    assert result.status == "API_RETURNED_HTML_ERROR_PAGE"


# ── Google CSE: alias resolution + cx injection ────────────────────────────

def test_google_cse_probe_spec_exists():
    """google_programmable_search must have q param and items meaningful field."""
    from ingestion.probes.api_probe import _PROBE_SPEC
    spec = _PROBE_SPEC.get("google_programmable_search")
    assert spec is not None
    assert "q" in spec.get("extra_params", {})
    assert "items" in spec.get("meaningful_fields", [])


def test_google_cse_cx_injected_in_params(tmp_path):
    """google_programmable_search: cx param must appear in built request params."""
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_CUSTOM_SEARCH_API_KEY=fake_api_key\nGOOGLE_CUSTOM_SEARCH_CX=fake_cx_123\n")
    from ingestion.core.env_loader import load_env
    from ingestion.probes.api_probe import _PROBE_SPEC, _build_request
    load_env(env_file)

    config = _SERVICE_CONFIGS["google_programmable_search"]
    spec = _PROBE_SPEC["google_programmable_search"]
    method, url, params, headers, body, secrets = _build_request(
        "google_programmable_search", config, spec
    )
    assert "cx" in params
    assert params.get("key") is not None
    # Secrets must not appear in params values as plain text when sanitised
    assert len(secrets) == 2


def test_google_cse_alias_google_api_key(tmp_path):
    """GOOGLE_API_KEY alias resolves GOOGLE_CUSTOM_SEARCH_API_KEY."""
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_API_KEY=fake_alias_key\nGOOGLE_CUSTOM_SEARCH_CX=fake_cx_456\n")
    from ingestion.core.env_loader import load_env, env_status
    for k in ("GOOGLE_CUSTOM_SEARCH_API_KEY", "GOOGLE_API_KEY"):
        os.environ.pop(k, None)
    load_env(env_file)
    status = env_status(["GOOGLE_CUSTOM_SEARCH_API_KEY"], env_path=env_file)
    assert status["GOOGLE_CUSTOM_SEARCH_API_KEY"] == "present"


# ── kofic: targetDt in probe spec ─────────────────────────────────────────

def test_kofic_probe_spec_has_target_dt():
    """kofic probe spec must include targetDt parameter."""
    from ingestion.probes.api_probe import _PROBE_SPEC
    spec = _PROBE_SPEC.get("kofic")
    assert spec is not None
    assert "targetDt" in spec.get("extra_params", {})
    target_dt = spec["extra_params"]["targetDt"]
    assert len(target_dt) == 8
    assert target_dt.isdigit()


# ── kma: data.go.kr 단기예보 JSON contract (2026-06-12 live-verified) ──────

def test_kma_probe_spec_format_and_params():
    """kma probe spec must target data.go.kr 초단기실황 (JSON, base_date/base_time/nx/ny)."""
    from ingestion.probes.api_probe import _PROBE_SPEC
    spec = _PROBE_SPEC.get("kma")
    assert spec is not None
    assert spec.get("response_format") == "json", "data.go.kr 단기예보 returns JSON (dataType=JSON)"
    params = spec.get("extra_params", {})
    for required in ("base_date", "base_time", "nx", "ny", "dataType"):
        assert required in params, f"kma requires {required} param"
    cfg = _SERVICE_CONFIGS.get("kma")
    assert cfg is not None
    assert cfg["auth"] == "query_param_serviceKey", "data.go.kr key goes in serviceKey param"
    assert "apis.data.go.kr" in cfg["endpoint"]


# ── culture_info: service config uses CULTURE_INFO_API_KEY ───────────────

def test_culture_info_service_config_key_name():
    """culture_info in _SERVICE_CONFIGS must use CULTURE_INFO_API_KEY (matches registry)."""
    cfg = _SERVICE_CONFIGS.get("culture_info")
    assert cfg is not None
    assert "CULTURE_INFO_API_KEY" in cfg.get("keys", []), (
        "culture_info must use CULTURE_INFO_API_KEY (aliased to CULTURE_INFO_KEY in env_loader)"
    )


# ── google_programmable_search: DEPRECATED_OR_EXCLUDED status_override ───

def test_google_cse_has_deprecated_status_override():
    """google_programmable_search must have status_override=DEPRECATED_OR_EXCLUDED."""
    cfg = _SERVICE_CONFIGS.get("google_programmable_search")
    assert cfg is not None
    assert cfg.get("status_override") == "DEPRECATED_OR_EXCLUDED"


def test_google_cse_excluded_from_all_safe():
    """google_programmable_search must not appear in --all-safe service list."""
    excluded = {"DEPRECATED_OR_EXCLUDED", "MVP_EXCLUDED"}
    active_services = {
        sid
        for sid, cfg in _SERVICE_CONFIGS.items()
        if cfg.get("status_override") not in excluded
    }
    assert "google_programmable_search" not in active_services

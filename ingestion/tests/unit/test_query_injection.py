"""query 주입(docs/85 Step 1) 단위 테스트 — 전부 네트워크 없음."""
from __future__ import annotations

import copy

import pytest

from ingestion.probes.api_probe import _PROBE_SPEC, _apply_query_override


# ── _apply_query_override 3분기 ──────────────────────────────────────────────

def test_apply_query_override_params_branch():
    spec = {"extra_params": {"display": "3"}, "query_param": "query"}
    out = _apply_query_override(spec, "삼성전자")
    assert out["extra_params"]["query"] == "삼성전자"
    assert out["extra_params"]["display"] == "3"
    assert out is not spec


def test_apply_query_override_json_body_branch():
    spec = {
        "json_body": {"q": "breaking news", "num": 3},
        "query_param": "q",
        "query_in": "json_body",
    }
    out = _apply_query_override(spec, "AI semiconductor")
    assert out["json_body"]["q"] == "AI semiconductor"
    assert out["json_body"]["num"] == 3
    assert out is not spec


def test_apply_query_override_no_meta_returns_original():
    spec = {"extra_params": {"targetDt": "20260602"}}
    out = _apply_query_override(spec, "아무거나")
    assert out is spec  # query_param 없음 → 원본 그대로


def test_apply_query_override_empty_query_returns_original():
    spec = {"extra_params": {}, "query_param": "q"}
    assert _apply_query_override(spec, None) is spec
    assert _apply_query_override(spec, "") is spec


# ── _PROBE_SPEC 전역 불변 (deepcopy 보장) ────────────────────────────────────

@pytest.mark.parametrize("source_id,query", [
    ("naver_news_search", "삼성전자"),
    ("serper", "stock surge"),
    ("tavily", "climate disaster"),
    ("gdelt", "politics"),
])
def test_probe_spec_global_not_mutated(source_id, query):
    before = copy.deepcopy(_PROBE_SPEC[source_id])
    _apply_query_override(_PROBE_SPEC[source_id], query)
    assert _PROBE_SPEC[source_id] == before


# ── 신규 entry 존재 + query 메타 검증 ────────────────────────────────────────

@pytest.mark.parametrize("source_id,expected_param", [
    ("gnews", "q"),
    ("guardian", "q"),
    ("nyt", "q"),
])
def test_new_search_entries_exist(source_id, expected_param):
    spec = _PROBE_SPEC.get(source_id)
    assert spec is not None, f"{source_id} entry must exist in _PROBE_SPEC"
    assert spec["query_param"] == expected_param
    assert spec["response_format"] == "json"


@pytest.mark.parametrize("source_id,expected_param,expected_in", [
    ("naver_news_search", "query", "params"),
    ("naver_blog_search", "query", "params"),
    ("youtube", "q", "params"),
    ("gdelt", "query", "params"),
    ("sec_edgar", "q", "params"),
    ("newsapi", "q", "params"),
    ("federal_register", "conditions[term]", "params"),
    ("tmdb", "query", "params"),
    ("serper", "q", "json_body"),
    ("tavily", "query", "json_body"),
    ("exa", "query", "json_body"),
])
def test_query_meta_on_existing_entries(source_id, expected_param, expected_in):
    spec = _PROBE_SPEC[source_id]
    assert spec["query_param"] == expected_param
    assert spec.get("query_in", "params") == expected_in


def test_tmdb_query_endpoint_switch_meta():
    spec = _PROBE_SPEC["tmdb"]
    assert spec["query_endpoint"].endswith("/search/movie")


# ── Route 1 query 전달 (monkeypatch kwargs 캡처) ─────────────────────────────

def test_collection_probe_route1_passes_query(monkeypatch):
    from ingestion.fetch_strategies import collection_probe as cp
    from ingestion.probes.models import ProbeResult

    captured: dict = {}

    def fake_probe(source_id, max_calls=1, query=None, **kwargs):
        captured["source_id"] = source_id
        captured["query"] = query
        return ProbeResult(source_id=source_id, method="api", query=query,
                           status="LIVE_SUCCESS")

    monkeypatch.setattr(cp, "run_api_live_probe", fake_probe)
    monkeypatch.setattr(cp, "_health_gate", lambda source_id, force=False: None)
    monkeypatch.setattr(cp, "_update_health", lambda result: result)

    result = cp.run_collection_probe("naver_news_search", query="기후 재난")
    assert captured["source_id"] == "naver_news_search"
    assert captured["query"] == "기후 재난"
    assert result.status == "LIVE_SUCCESS"


def test_run_api_live_probe_signature_backward_compatible():
    import inspect
    from ingestion.probes.api_probe import run_api_live_probe
    sig = inspect.signature(run_api_live_probe)
    assert "query" in sig.parameters
    assert sig.parameters["query"].default is None

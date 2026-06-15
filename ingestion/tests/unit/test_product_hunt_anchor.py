"""G-3: product_hunt anchor — 확장 GraphQL 실 url/createdAt, 합성 slug 금지."""
from __future__ import annotations

from ingestion.orchestration.vendor_api_routes import _canonical_ph_url, fetch_product_hunt

_ENV = {"PRODUCT_HUNT_ACCESS_TOKEN": "test_token"}


def _edges(nodes):
    return {"data": {"posts": {"edges": [{"node": n} for n in nodes]}}}


def test_real_url_and_createdAt_promote():
    nodes = [{"id": "1", "name": "Novu", "tagline": "t",
              "url": "https://www.producthunt.com/products/novu?utm_campaign=producthunt-api",
              "slug": "novu-connect", "createdAt": "2026-06-15T07:01:00Z"}]
    def _post(url, *, json_body=None, bearer=None):
        return 200, _edges(nodes), None
    res = fetch_product_hunt(env=_ENV, http_post=_post, limit=1)
    assert res.success and res.item_count == 1
    rec = res.records[0]
    # utm 추적 쿼리 제거된 canonical 실 url
    assert rec["source_url_or_evidence"] == "https://www.producthunt.com/products/novu"
    assert rec["published_at_or_observed_at"] == "2026-06-15T07:01:00Z"


def test_node_without_real_url_skipped():
    # url/createdAt 없는 노드는 합성하지 않고 스킵(둔갑 금지).
    nodes = [{"id": "2", "name": "NoUrl", "tagline": "t"}]
    def _post(url, *, json_body=None, bearer=None):
        return 200, _edges(nodes), None
    res = fetch_product_hunt(env=_ENV, http_post=_post, limit=1)
    assert res.success is False and res.error == "no_real_url_or_date"


def test_canonical_strips_tracking_params():
    u = "https://www.producthunt.com/products/novu?utm_source=x&ref=y"
    assert _canonical_ph_url(u) == "https://www.producthunt.com/products/novu"


def test_missing_token_blocks(monkeypatch):
    monkeypatch.delenv("PRODUCT_HUNT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("PRODUCT_HUNT_API_KEY", raising=False)
    res = fetch_product_hunt(env={}, http_post=lambda *a, **k: (200, _edges([]), None), limit=1)
    assert res.success is False and res.error == "key_missing"

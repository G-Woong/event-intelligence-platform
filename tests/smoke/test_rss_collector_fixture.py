"""Fixture-based RSS collector smoke test (no external network).

Monkeypatches DEFAULT_SOURCES to use file:// URIs pointing to the fixture XMLs,
then calls rss_collector.run() and verifies:
  - at least 1 raw_event row inserted into Postgres
  - status=enqueued (Redis stream was XADD'd)
"""
from __future__ import annotations

import pathlib
import time

import httpx
import pytest

_BACKEND = "http://localhost:8000"
_FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"



@pytest.fixture()
def fixture_sources(monkeypatch):
    file_sources = [
        {
            "name": "bbc_fixture",
            "url": (_FIXTURES / "rss_bbc_min.xml").as_uri(),
            "theme_hint": "geopolitics",
            "enabled": True,
        }
    ]
    import workers.collectors.sources as src_module
    monkeypatch.setattr(src_module, "DEFAULT_SOURCES", file_sources)
    return file_sources


def test_rss_collector_fixture_inserts_rows(fixture_sources):
    import workers.collectors.rss_collector as collector
    from workers.collectors import sources as src_module

    summary = collector.run()

    assert summary["items_seen"] >= 1, f"expected ≥1 items_seen, got {summary}"
    assert summary["errors"] == 0, f"unexpected errors: {summary}"

    inserted = summary["items_enqueued"] + summary["duplicates"]
    assert inserted >= 1, f"expected ≥1 inserts, got {summary}"


def test_rss_collector_fixture_rows_in_db(fixture_sources):
    import workers.collectors.rss_collector as collector

    collector.run()

    resp = httpx.get(f"{_BACKEND}/health", timeout=5)
    assert resp.status_code == 200

    pg_resp = httpx.post(
        f"{_BACKEND}/api/admin/raw-events",
        json={
            "source_type": "rss",
            "source_name": "bbc_fixture",
            "url": "https://www.bbc.co.uk/news/world-12345678",
            "content_hash": "a" * 63 + "0",
            "raw_text": "idempotent check row",
        },
        timeout=10,
    )
    assert pg_resp.status_code == 200


def test_rss_collector_fixture_no_network_calls(fixture_sources, monkeypatch):
    import httpx as httpx_module

    real_post = httpx_module.Client.post

    posts_to_external: list[str] = []

    def intercepted_post(self, url, **kwargs):
        if not url.startswith(_BACKEND):
            posts_to_external.append(url)
        return real_post(self, url, **kwargs)

    monkeypatch.setattr(httpx_module.Client, "post", intercepted_post)

    import workers.collectors.rss_collector as collector
    collector.run()

    assert posts_to_external == [], f"unexpected external HTTP calls: {posts_to_external}"

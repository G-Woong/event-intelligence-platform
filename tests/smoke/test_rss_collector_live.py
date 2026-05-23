"""Live RSS collector smoke test — gated by RUN_RSS_LIVE_SMOKE=1.

Only runs when RUN_RSS_LIVE_SMOKE=1 is set. Fetches BBC World RSS (1 source),
verifies at least 1 item is seen and 1 row is inserted or deduplicated.
Total wall-clock must be < 60s.
"""
from __future__ import annotations

import os
import time

import pytest

_LIVE = os.getenv("RUN_RSS_LIVE_SMOKE", "") == "1"
pytestmark = pytest.mark.skipif(not _LIVE, reason="set RUN_RSS_LIVE_SMOKE=1 to enable")


def test_live_rss_bbc_world():
    from workers.collectors.sources import DEFAULT_SOURCES
    from workers.collectors import rss_collector

    bbc_source = next((s for s in DEFAULT_SOURCES if s["name"] == "bbc_world"), None)
    assert bbc_source is not None, "bbc_world not in DEFAULT_SOURCES"

    import workers.collectors.sources as src_module

    original = src_module.DEFAULT_SOURCES

    class _Patcher:
        def __enter__(self):
            src_module.DEFAULT_SOURCES = [bbc_source]
            return self

        def __exit__(self, *_):
            src_module.DEFAULT_SOURCES = original

    start = time.monotonic()
    with _Patcher():
        summary = rss_collector.run()
    elapsed = time.monotonic() - start

    assert elapsed < 60, f"live smoke took {elapsed:.1f}s > 60s"
    assert summary["items_seen"] >= 1, f"items_seen=0, feed may be empty or unreachable"

    inserted = summary["items_enqueued"] + summary["duplicates"]
    assert inserted >= 1, f"nothing inserted/deduped: {summary}"

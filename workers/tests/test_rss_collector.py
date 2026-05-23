from __future__ import annotations

import pathlib
import unittest.mock as mock
from datetime import datetime, timezone

import feedparser
import pytest

from workers.collectors import rss_collector

_FIXTURES = pathlib.Path(__file__).parent.parent.parent / "tests" / "fixtures"


def _fixture_feed(name: str):
    content = (_FIXTURES / name).read_text(encoding="utf-8")
    return feedparser.parse(content)


def _make_source(fixture_url: str) -> dict:
    return {"name": "test_feed", "url": fixture_url, "theme_hint": "test", "enabled": True}


class TestStripHtml:
    def test_strips_tags(self):
        assert rss_collector._strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_no_tags(self):
        assert rss_collector._strip_html("plain text") == "plain text"


class TestContentHash:
    def test_deterministic(self):
        h1 = rss_collector._content_hash("rss", "src", "eid", "http://a.com", "title", "text")
        h2 = rss_collector._content_hash("rss", "src", "eid", "http://a.com", "title", "text")
        assert h1 == h2

    def test_differs_on_summary_change(self):
        h1 = rss_collector._content_hash("rss", "src", "eid", "http://a.com", "t", "text1")
        h2 = rss_collector._content_hash("rss", "src", "eid", "http://a.com", "t", "text2")
        assert h1 != h2

    def test_length_64(self):
        h = rss_collector._content_hash("rss", "src", None, "http://a.com", "t", "text")
        assert len(h) == 64

    def test_none_external_id_uses_url(self):
        h1 = rss_collector._content_hash("rss", "src", None, "http://a.com", "t", "text")
        h2 = rss_collector._content_hash("rss", "src", "http://a.com", "http://a.com", "t", "text")
        assert h1 == h2


class TestParsePublished:
    def test_valid_parsed(self):
        class FakeEntry:
            def get(self, key, default=None):
                if key == "published_parsed":
                    return (2026, 5, 23, 8, 0, 0, 4, 143, 0)
                return default
        result = rss_collector._parse_published(FakeEntry())
        assert result == datetime(2026, 5, 23, 8, 0, 0, tzinfo=timezone.utc)

    def test_none_published(self):
        class FakeEntry:
            def get(self, key, default=None):
                return default
        assert rss_collector._parse_published(FakeEntry()) is None


class TestProcessSource:
    def _mock_ok_response(self, is_duplicate: bool = False) -> mock.MagicMock:
        resp = mock.MagicMock()
        resp.json.return_value = {"is_duplicate": is_duplicate, "enqueued_msg_id": "1-0"}
        resp.raise_for_status = mock.MagicMock()
        return resp

    def test_valid_two_entries(self):
        fixture_path = (_FIXTURES / "rss_bbc_min.xml").as_uri()
        source = _make_source(fixture_path)
        client = mock.MagicMock()
        client.post.return_value = self._mock_ok_response()

        result = rss_collector._process_source(source, client)

        assert result["items_seen"] == 2
        assert result["items_enqueued"] == 2
        assert result["duplicates"] == 0
        assert result["errors"] == 0
        assert client.post.call_count == 2

    def test_empty_feed(self):
        fixture_path = (_FIXTURES / "rss_empty.xml").as_uri()
        source = _make_source(fixture_path)
        client = mock.MagicMock()

        result = rss_collector._process_source(source, client)

        assert result["items_seen"] == 0
        assert result["items_enqueued"] == 0
        assert client.post.call_count == 0

    def test_malformed_bozo_continues(self):
        fixture_path = (_FIXTURES / "rss_malformed.xml").as_uri()
        source = _make_source(fixture_path)
        client = mock.MagicMock()
        client.post.return_value = self._mock_ok_response()

        result = rss_collector._process_source(source, client)
        assert result["errors"] == 0

    def test_no_link_entry_skipped(self):
        fixture_path = (_FIXTURES / "rss_no_link.xml").as_uri()
        source = _make_source(fixture_path)
        client = mock.MagicMock()
        client.post.return_value = self._mock_ok_response()

        result = rss_collector._process_source(source, client)
        assert result["items_seen"] == 1

    def test_duplicate_response_counted(self):
        fixture_path = (_FIXTURES / "rss_bbc_min.xml").as_uri()
        source = _make_source(fixture_path)
        client = mock.MagicMock()
        client.post.return_value = self._mock_ok_response(is_duplicate=True)

        result = rss_collector._process_source(source, client)

        assert result["duplicates"] == 2
        assert result["items_enqueued"] == 0

    def test_payload_shape(self):
        fixture_path = (_FIXTURES / "rss_bbc_min.xml").as_uri()
        source = _make_source(fixture_path)
        client = mock.MagicMock()
        client.post.return_value = self._mock_ok_response()

        rss_collector._process_source(source, client)

        call_kwargs = client.post.call_args_list[0]
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs.kwargs["json"]
        assert "source_type" in payload
        assert payload["source_type"] == "rss"
        assert "content_hash" in payload
        assert len(payload["content_hash"]) == 64
        assert "url" in payload
        assert "raw_metadata" in payload

    def test_one_source_network_failure_does_not_kill_run(self):
        sources = [
            {"name": "failing", "url": "http://localhost:1/nonexistent", "theme_hint": "x", "enabled": True},
            {"name": "ok", "url": (_FIXTURES / "rss_bbc_min.xml").as_uri(), "theme_hint": "x", "enabled": True},
        ]
        client = mock.MagicMock()
        client.post.return_value = self._mock_ok_response()

        results = []
        for s in sources:
            results.append(rss_collector._process_source(s, client))

        ok_result = next(r for r in results if r["source"] == "ok")
        assert ok_result["items_seen"] == 2

    def test_backend_5xx_counted_as_error(self):
        import httpx

        fixture_path = (_FIXTURES / "rss_bbc_min.xml").as_uri()
        source = _make_source(fixture_path)
        client = mock.MagicMock()

        err_resp = mock.MagicMock()
        err_resp.status_code = 500
        client.post.side_effect = httpx.HTTPStatusError("server error", request=mock.MagicMock(), response=err_resp)

        result = rss_collector._process_source(source, client)
        assert result["errors"] == 2
        assert result["items_enqueued"] == 0

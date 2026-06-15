"""G-3: dcinside detail body audit — list→detail 추출, 본문 추출/빈본문/차단 마커(우회 없음)."""
from __future__ import annotations

from ingestion.orchestration.dcinside_strategy import (
    audit_dcinside_detail_body,
    detail_urls_from_records,
)

_VIEW = "https://gall.dcinside.com/mgallery/board/view/?id=stockus&no={}"


def _records(nos):
    return [{"source_url_or_evidence": _VIEW.format(n), "record_type": "community_signal"} for n in nos]


def test_detail_urls_extracted_from_list_records():
    urls = detail_urls_from_records(_records([1, 2, 3]) + [{"source_url_or_evidence": "https://x/list"}])
    assert len(urls) == 3 and all("/board/view/?id=" in u for u in urls)


def test_detail_body_alive_when_static_has_body():
    body = "<html><body><div class='write_div'>" + ("실제 게시글 본문 텍스트 " * 20) + "</div></body></html>"
    audit = audit_dcinside_detail_body(detail_urls=[_VIEW.format(1)],
                                       http_get=lambda u: (200, body))
    assert audit.conclusion == "DETAIL_BODY_ALIVE"
    assert audit.body_available and audit.best_body_chars >= 120


def test_detail_body_empty_static_stays_preview_only():
    body = "<html><body><div class='write_div'></div><div class='gallview_contents'></div></body></html>"
    audit = audit_dcinside_detail_body(detail_urls=[_VIEW.format(1)],
                                       http_get=lambda u: (200, body))
    assert audit.conclusion == "DETAIL_BODY_EMPTY_STATIC"
    assert audit.body_available is False


def test_block_marker_stops_no_bypass():
    body = "<html><body>Just a moment... checking your browser cf-chl</body></html>"
    audit = audit_dcinside_detail_body(detail_urls=[_VIEW.format(1)],
                                       http_get=lambda u: (200, body))
    assert audit.conclusion == "BLOCKED_NO_BYPASS"
    assert audit.block_marker == "cloudflare_challenge"


def test_robots_disallow_detail_no_fetch():
    called = {"n": 0}
    def _get(u):
        called["n"] += 1
        return (200, "<div class='write_div'>x</div>")
    audit = audit_dcinside_detail_body(detail_urls=[_VIEW.format(1)], robots_allows_detail=False,
                                       http_get=_get)
    assert audit.conclusion == "BLOCKED_NO_BYPASS"
    assert called["n"] == 0       # robots 불허면 호출 자체를 안 함(no-bypass)


def test_no_detail_urls():
    audit = audit_dcinside_detail_body(detail_urls=[])
    assert audit.conclusion == "NO_DETAIL_URLS"

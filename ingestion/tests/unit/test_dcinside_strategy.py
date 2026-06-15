"""G2-8: dcinside 전략 — robots 허용 갤러리만 fetch, community_signal 파싱, 우회 차단 감지.

네트워크 0: http_get 주입형 + 합성 HTML(실제 list 구조 반영).
"""
from __future__ import annotations

from ingestion.orchestration.dcinside_strategy import (
    collect_dcinside,
    list_url_for,
    parse_list_rows,
)

# 실제 dcinside list 구조 축약: 공지행(gall_num='-') 1개 + 실제글 2개
_HTML = """
<table><tbody>
<tr class="ub-content">
  <td class="gall_num">-</td>
  <td class="gall_tit"><a href="/mgallery/board/notice/?id=stockus">공지글</a></td>
  <td class="gall_date" title="">26/06/15</td>
</tr>
<tr class="ub-content">
  <td class="gall_num">13794607</td>
  <td class="gall_tit"><a href="/mgallery/board/view/?id=stockus&no=13794607">엔비디아 실적 발표 주목</a><span class="reply_num">[4]</span></td>
  <td class="gall_writer">user1</td>
  <td class="gall_date" title="2026-01-20 23:34:56">26.01.20</td>
  <td class="gall_count">20542</td>
</tr>
<tr class="ub-content">
  <td class="gall_num">14507618</td>
  <td class="gall_tit"><a href="/mgallery/board/view/?id=stockus&no=14507618">연준 금리 동결 전망</a></td>
  <td class="gall_writer">user2</td>
  <td class="gall_date" title="2026-03-04 10:40:39">26.03.04</td>
  <td class="gall_count">33577</td>
</tr>
</tbody></table>
"""


def test_list_url_for_minor_gallery():
    assert list_url_for("stockus", minor=True).endswith("/mgallery/board/lists/?id=stockus")


def test_parse_skips_notice_and_builds_community_signal():
    recs = parse_list_rows(_HTML, "stockus")
    assert len(recs) == 2                                   # 공지행 제외
    r0 = recs[0]
    assert r0["record_type"] == "community_signal"
    assert r0["title_or_label"] == "엔비디아 실적 발표 주목"
    assert "/board/view/?id=stockus&no=13794607" in r0["source_url_or_evidence"]
    assert r0["source_url_or_evidence"].startswith("https://gall.dcinside.com")
    assert r0["published_at_or_observed_at"] == "2026-01-20T23:34:56+09:00"  # title ISO 정규화
    assert r0["body_state_or_signal"] == "community_signal"


def test_collect_success_with_injected_html():
    r = collect_dcinside(gallery_id="stockus", http_get=lambda u: (200, _HTML))
    assert r.success and r.verdict == "COMMUNITY_SIGNAL_ALIVE"
    assert r.item_count == 2
    assert r.attempted_url == "https://gall.dcinside.com/mgallery/board/lists/?id=stockus"


def test_robots_disallowed_does_not_fetch():
    called = {"n": 0}
    def http(u):
        called["n"] += 1
        return (200, _HTML)
    r = collect_dcinside(gallery_id="stock_new", robots_allowed=False, http_get=http)
    assert r.success is False and r.verdict == "ROBOTS_BLOCKED_NO_BYPASS"
    assert called["n"] == 0                                 # 호출 자체를 안 함


def test_cloudflare_challenge_stops_no_bypass():
    body = "<html><head><title>Just a moment...</title></head><body>cf-chl checking your browser</body></html>"
    r = collect_dcinside(gallery_id="stockus", http_get=lambda u: (200, body))
    assert r.success is False and r.verdict == "CLOUDFLARE_BLOCKED_NO_BYPASS"
    assert r.item_count == 0


def test_captcha_stops_no_bypass():
    body = "<html>kcaptcha please verify you are human</html>"
    r = collect_dcinside(gallery_id="stockus", http_get=lambda u: (200, body))
    assert r.verdict == "CAPTCHA_BLOCKED_NO_BYPASS"


def test_429_pending_resume():
    r = collect_dcinside(gallery_id="stockus", http_get=lambda u: (429, "too many requests"))
    assert r.verdict == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"

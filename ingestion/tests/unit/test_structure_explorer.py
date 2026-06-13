"""run_structure_explorer 단위 테스트 (전부 오프라인 — 네트워크 호출 없음)."""
from __future__ import annotations

_FAKE_HTML = """
<html><head><title>t</title></head><body>
<nav><a href="/1">메뉴1</a><a href="/2">메뉴2</a></nav>
<ul class="rank-list">
""" + "".join(
    f'<li class="rank-item"><a href="/kw/{i}">실시간 키워드 {i}</a></li>' for i in range(10)
) + """
</ul></body></html>"""


def test_mine_candidates_finds_repeated_structure():
    from ingestion.runners.run_structure_explorer import mine_selector_candidates
    cands = mine_selector_candidates(_FAKE_HTML, max_candidates=5)
    assert cands, "반복 li.rank-item을 찾아야 한다"
    top = cands[0]
    assert top["match_count"] >= 8
    assert any("rank-item" in c["selector"] or "rank-list" in c["selector"] for c in cands)
    assert top["sample_texts"][0].startswith("실시간 키워드")


def test_styled_component_hash_classes_marked_fragile():
    from ingestion.runners.run_structure_explorer import mine_selector_candidates
    html = "<div>" + "".join(
        f'<span class="css-1a2b3c4">kw {i}</span>' for i in range(8)) + "</div>"
    cands = mine_selector_candidates(html, max_candidates=5)
    assert cands and cands[0]["stability"] == "fragile"


def test_offline_dom_mode_no_network(tmp_path, monkeypatch):
    dom = tmp_path / "page.html"
    dom.write_text(_FAKE_HTML, encoding="utf-8")
    from ingestion.runners import run_structure_explorer as rse

    async def _boom(*a, **k):
        raise AssertionError("offline 모드에서 네트워크 호출 금지")

    monkeypatch.setattr("ingestion.tools.playwright_browser_tool.open_page", _boom)
    report = rse.explore(site_id_or_url="signal_bz", query=None, region=None,
                         wait_ms=0, offline_dom=str(dom))
    assert report["candidates"]


def test_mask_url_hides_keys():
    from ingestion.runners.run_structure_explorer import _mask_url
    assert "***" in _mask_url("https://x.com/api?serviceKey=SECRET123&a=1")
    assert "SECRET123" not in _mask_url("https://x.com/api?serviceKey=SECRET123")


def test_429_dom_not_mined_as_candidates(tmp_path):
    from ingestion.runners.run_structure_explorer import explore
    dom = tmp_path / "rl.html"
    dom.write_text("<html><body>Error 429 Too Many Requests rate limit exceeded</body></html>",
                   encoding="utf-8")
    report = explore(site_id_or_url="signal_bz", offline_dom=str(dom))
    assert report["verdict"] == "RATE_LIMITED"
    assert report["candidates"] == []


def test_network_json_candidate_summarized():
    from ingestion.runners.run_structure_explorer import _summarize_network
    entries = [
        {"url": "https://api.x.com/trending?key=SECRET", "method": "GET", "status": 200,
         "content_type": "application/json", "json_body": {"items": [1, 2, 3], "meta": "x"}},
        {"url": "https://x.com/page.html", "method": "GET", "status": 200,
         "content_type": "text/html"},
    ]
    out = _summarize_network(entries)
    assert len(out) == 1
    assert out[0]["list_lengths"] == {"items": 3}
    assert "SECRET" not in out[0]["url"]
    assert "key=***" in out[0]["url"]


def test_existing_selector_match_count():
    from ingestion.runners.run_structure_explorer import _check_existing_selectors
    from ingestion.probes.site_specs import load_site_specs
    spec = load_site_specs()["signal_bz"]
    html = '<div class="rank-tex">키워드A</div><div class="rank-tex">키워드B</div>'
    out = _check_existing_selectors(html, spec)
    rank_tex = [s for s in out if s["selector"] == ".rank-tex"]
    assert rank_tex and rank_tex[0]["match_count"] == 2

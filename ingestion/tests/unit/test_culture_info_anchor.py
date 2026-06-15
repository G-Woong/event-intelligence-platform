"""G-3: culture_info anchor — period2→detail2 실 외부 url 확보, 합성/무url 거부."""
from __future__ import annotations

from ingestion.orchestration.vendor_api_routes import (
    _CULTURE_DETAIL,
    _CULTURE_LIST,
    fetch_culture_info,
)

_ENV = {"CULTURE_INFO_API_KEY": "test_key"}

_LIST_XML = """<response><body><items>
<item><seq>315929</seq><title>전시 A</title><startDate>20250226</startDate></item>
<item><seq>315930</seq><title>전시 B</title><startDate>20250301</startDate></item>
</items></body></response>"""

_DETAIL_XML_WITH_URL = """<response><header><resultCode>00</resultCode></header><body><items><item>
<seq>315929</seq><title>전시 A</title><startDate>20250226</startDate>
<place>성북구립미술관</place>
<url>https://sma.sbculture.or.kr/sma/exhibition/current.do?mode=view&amp;articleNo=43458</url>
</item></items></body></response>"""

_DETAIL_XML_NO_URL = """<response><body><items><item>
<seq>315930</seq><title>전시 B</title><startDate>20250301</startDate><url></url>
</item></items></body></response>"""


def _get_factory(detail_xml):
    def _get(url, params=None):
        if url == _CULTURE_LIST:
            return 200, None, _LIST_XML
        if url == _CULTURE_DETAIL:
            return 200, None, detail_xml
        return 404, None, ""
    return _get


def test_real_external_url_from_detail2_promotes():
    res = fetch_culture_info(env=_ENV, http_get=_get_factory(_DETAIL_XML_WITH_URL), limit=1)
    assert res.success and res.item_count >= 1
    rec = res.records[0]
    assert rec["source_url_or_evidence"].startswith("https://sma.sbculture.or.kr/")
    assert rec["published_at_or_observed_at"] == "2025-02-26"     # startDate 시간 anchor
    assert "#seq=315929" in rec["canonical_url"]                  # seq stable id


def test_no_detail_url_stays_unpromoted():
    res = fetch_culture_info(env=_ENV, http_get=_get_factory(_DETAIL_XML_NO_URL), limit=1)
    assert res.success is False
    assert res.error == "no_detail_url"          # 실 url 없으면 합성 안 함 → 미승격


def test_missing_key_blocks(monkeypatch):
    # os.environ 실 키가 있어도 영향받지 않도록 제거 후 검증(키 없으면 호출 자체 차단).
    monkeypatch.delenv("CULTURE_INFO_API_KEY", raising=False)
    monkeypatch.delenv("CULTURE_INFO_KEY", raising=False)
    res = fetch_culture_info(env={}, http_get=_get_factory(_DETAIL_XML_WITH_URL), limit=1)
    assert res.success is False and res.error == "key_missing"

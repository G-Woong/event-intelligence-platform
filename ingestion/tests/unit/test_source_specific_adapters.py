"""E-3: 소스별 adapter가 NEEDS_PARSER source를 올바른 candidate로 흡수하는지(network 0)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ingestion.orchestration.artifact_parser import parse_artifact_text
from ingestion.orchestration.source_adapters import adapt_source_payload, adapt_source_xml


def _adapt(sid, data):
    out = adapt_source_payload(sid, data)
    assert out is not None, f"{sid} adapter returned None"
    return out[0], out[1]


def test_sec_edgar_official_record_with_title_url_date():
    data = {"hits": {"hits": [
        {"_id": "0000940400-26-020168:primary_doc.xml",
         "_source": {"display_names": ["ACME CORP (CIK 0000940400)"], "form": "8-K",
                     "adsh": "0000940400-26-020168", "ciks": ["0000940400"],
                     "file_date": "2026-06-12"}}]}}
    cands, name = _adapt("sec_edgar", data)
    assert name == "adapter:sec_edgar"
    c = cands[0]
    assert c.title and "8-K" in c.title
    assert c.source_url and c.source_url.startswith("https://www.sec.gov/Archives/edgar/data/940400/")
    assert c.published_at == "2026-06-12"


def test_twelve_data_single_structured_signal():
    data = {"meta": {"symbol": "AAPL"}, "status": "ok",
            "values": [{"datetime": "2026-06-12", "close": "200.1"},
                       {"datetime": "2026-06-11", "close": "199.0"}]}
    cands, name = _adapt("twelve_data", data)
    assert name == "adapter:twelve_data"
    assert len(cands) == 1 and cands[0].numeric_payload_exempt is True
    assert "AAPL" in cands[0].title


def test_alpha_vantage_latest_day_signal():
    data = {"Meta Data": {"2. Symbol": "MSFT"},
            "Time Series (Daily)": {"2026-06-11": {"4. close": "1"},
                                    "2026-06-12": {"4. close": "2"}}}
    cands, name = _adapt("alpha_vantage", data)
    assert cands[0].numeric_payload_exempt is True
    assert cands[0].published_at == "2026-06-12"  # 최신일 선택


def test_tour_official_record():
    data = {"response": {"body": {"items": {"item": [
        {"title": "Gyeongbokgung", "contentid": "126508", "modifiedtime": "20260601",
         "addr1": "Seoul"}]}}}}
    cands, name = _adapt("tour", data)
    assert cands[0].title == "Gyeongbokgung"
    assert "126508" in cands[0].source_url
    assert cands[0].published_at == "20260601"


def test_tmdb_constructs_url_and_date():
    data = {"results": [{"id": 1234, "title": "Synthetic Movie", "release_date": "2026-05-30"}]}
    cands, name = _adapt("tmdb", data)
    assert cands[0].source_url == "https://www.themoviedb.org/movie/1234"
    assert cands[0].published_at == "2026-05-30"


def test_serper_search_result():
    data = {"organic": [{"title": "Result", "link": "https://x.test/a", "snippet": "s",
                         "date": "2026-06-10"}]}
    cands, name = _adapt("serper", data)
    assert cands[0].source_url == "https://x.test/a"


def test_youtube_descends_into_snippet():
    data = {"items": [{"id": {"videoId": "abc123"},
                       "snippet": {"title": "Vid", "publishedAt": "2026-06-12T00:00:00Z"}}]}
    cands, name = _adapt("youtube", data)
    assert cands[0].title == "Vid"
    assert cands[0].source_url == "https://www.youtube.com/watch?v=abc123"


def test_aladin_and_kofic_official():
    a, _ = _adapt("aladin", {"item": [{"title": "Book", "link": "https://aladin.test/1",
                                       "pubDate": "2026-06-01"}]})
    assert a[0].source_url == "https://aladin.test/1"
    k, _ = _adapt("kofic", {"boxOfficeResult": {"showRange": "20260613~20260613",
        "dailyBoxOfficeList": [{"movieNm": "Film", "movieCd": "2026", "rank": "1", "salesAmt": "100"}]}})
    assert k[0].title == "Film" and k[0].published_at == "20260613"


def test_its_reduces_to_single_signal_no_inflation():
    data = {"body": {"items": [{"roadName": f"r{i}", "speed": str(i)} for i in range(5000)]}}
    cands, name = _adapt("its", data)
    assert len(cands) == 1  # 5000행 → 1 신호(인플레 금지)
    assert cands[0].numeric_payload_exempt is True


def test_product_hunt_anchor_from_slug_when_url_absent():
    # Phase G-5: url 미요청 시 slug 기반 결정적 post URL anchor 생성(NO_STABLE_URL 해소)
    data = {"data": {"posts": {"edges": [{"node": {"name": "Cool Tool", "tagline": "t"}}]}}}
    cands, name = _adapt("product_hunt", data)
    assert cands[0].title == "Cool Tool"
    assert cands[0].source_url == "https://www.producthunt.com/posts/cool-tool"


def test_product_hunt_prefers_real_url_and_date():
    data = {"data": {"posts": {"edges": [{"node": {
        "name": "Tool", "url": "https://www.producthunt.com/posts/tool",
        "createdAt": "2026-06-15T00:00:00Z", "tagline": "t"}}]}}}
    cands, name = _adapt("product_hunt", data)
    assert cands[0].source_url == "https://www.producthunt.com/posts/tool"
    assert cands[0].published_at == "2026-06-15T00:00:00Z"


def test_kopis_xml_adapter():
    xml = ("<dbs><db><mt20id>PF1</mt20id><prfnm>Show</prfnm>"
           "<prfpdfrom>2026.05.30</prfpdfrom><fcltynm>Hall</fcltynm></db></dbs>")
    root = ET.fromstring(xml)
    out = adapt_source_xml("kopis", root)
    assert out is not None
    cands, name = out
    assert name == "adapter:kopis"
    assert cands[0].title == "Show" and "PF1" in cands[0].source_url


def test_culture_info_xml_uses_startdate_not_rss():
    xml = ("<response><body><items><item><title>Expo</title>"
           "<startDate>20260601</startDate><place>Center</place></item></items></body></response>")
    cands, name, _ = parse_artifact_text(xml, source_id="culture_info", fmt="xml")
    assert name == "adapter:culture_info"  # RSS .//item 경로가 아닌 전용 adapter
    assert cands[0].title == "Expo" and cands[0].published_at == "20260601"


def test_unregistered_sources_fall_through_to_none():
    # kma(header만)/eia(route 카탈로그)/bok_ecos(catalog)는 adapter 미등록 → None(generic fallback)
    assert adapt_source_payload("kma", {"response": {"header": {"resultCode": "10"}}}) is None
    assert adapt_source_payload("eia", {"response": {"routes": [{"id": "coal"}]}}) is None
    assert adapt_source_payload("bok_ecos", {"StatisticTableList": {"row": [{"STAT_NAME": "x"}]}}) is None


def test_adapter_preempts_generic_container_no_titleless_inflation():
    # youtube는 top-level items를 갖지만 generic 분해(title-less) 대신 adapter가 선제.
    data = {"items": [{"id": {"videoId": "v"}, "snippet": {"title": "T"}}]}
    cands, name, _ = parse_artifact_text(__import__("json").dumps(data),
                                         source_id="youtube", fmt="json")
    assert name == "adapter:youtube"
    assert cands[0].title == "T"

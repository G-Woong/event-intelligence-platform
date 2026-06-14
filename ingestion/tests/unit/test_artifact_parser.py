"""Phase D-2: artifact → ArticleCandidate 파서 (synthetic fixture 기반)."""
from __future__ import annotations

from pathlib import Path

from ingestion.orchestration.artifact_parser import parse_artifact_text

_FIX = Path(__file__).parent.parent / "fixtures" / "orchestration"


def _read(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


def test_gdelt_fixture_to_candidates():
    cands, name, errors = parse_artifact_text(
        _read("gdelt_minimal.json"), source_id="gdelt", fmt="json"
    )
    assert name == "gdelt"
    assert errors == []
    assert len(cands) == 2
    c = cands[0]
    assert c.title == "Synthetic Event One"
    assert c.source_url == "https://example-news.test/world/a1?utm_source=gdelt"
    assert c.published_at == "20260613T120000Z"
    # canonical_url은 no-network 정규화로 tracking 제거
    assert c.canonical_url == "https://example-news.test/world/a1"
    assert c.body_missing is True  # GDELT는 본문 없음(헤드라인+URL)


def test_rss_fixture_to_candidates():
    cands, name, errors = parse_artifact_text(
        _read("rss_minimal.xml"), source_id="bbc", fmt="xml"
    )
    assert name == "rss"
    assert len(cands) == 2
    assert cands[0].title == "Feed Item One"
    assert cands[0].source_url == "https://feed.test/items/1?utm_medium=rss#section"
    assert cands[0].canonical_url == "https://feed.test/items/1"  # utm+fragment 제거
    assert cands[0].summary == "Short synthetic summary one."


def test_generic_json_list_to_candidates():
    cands, name, errors = parse_artifact_text(
        _read("generic_articles.json"), source_id="newsapi", fmt="json"
    )
    assert name == "generic_json_list"
    assert len(cands) == 2
    # 서로 다른 키(title/headline, link/url, description/abstract) 모두 매핑
    assert cands[0].title == "Generic List Article A"
    assert cands[0].source_url == "https://generic.test/a"
    assert cands[1].title == "Generic List Article B"
    assert cands[1].source_url == "https://generic.test/b"


def test_numeric_payload_marked_exempt():
    cands, name, errors = parse_artifact_text(
        _read("api_numeric_payload.json"), source_id="finnhub", fmt="json"
    )
    assert name == "numeric_payload"
    assert len(cands) == 1
    assert cands[0].numeric_payload_exempt is True
    assert cands[0].body_missing is True  # 본문 없음(정상)


def test_malformed_json_returns_parse_error():
    cands, name, errors = parse_artifact_text(
        _read("malformed.json"), source_id="x", fmt="json"
    )
    assert cands == []
    assert name == "json_malformed"
    assert errors and "json decode error" in errors[0]


def test_malformed_xml_returns_parse_error():
    cands, name, errors = parse_artifact_text(
        _read("malformed.xml"), source_id="x", fmt="xml"
    )
    assert cands == []
    assert name == "xml_malformed"
    assert errors and "xml parse error" in errors[0]


def test_empty_artifact_reports_empty():
    cands, name, errors = parse_artifact_text(
        _read("empty.json"), source_id="x", fmt="json"
    )
    assert cands == []
    assert name == "empty"
    assert errors == ["empty_artifact"]


def test_no_article_container_reports_unrecognized():
    cands, name, errors = parse_artifact_text(
        _read("no_articles.json"), source_id="x", fmt="json"
    )
    assert cands == []
    assert name == "json_unrecognized"
    assert errors


def test_extracted_text_fixture_parsed():
    cands, name, errors = parse_artifact_text(
        _read("snippet_only.txt"), source_id="bbc", fmt="extracted_text"
    )
    assert name == "extracted_text"
    assert len(cands) == 1
    assert cands[0].title == "Snippet Only Article"
    assert cands[0].source_url == "https://snippet.test/a"
    assert cands[0].body_text and "snippet body" in cands[0].body_text


def test_parser_never_invents_missing_fields():
    # url/title 없는 항목 → None (만들어내지 않음)
    cands, name, _ = parse_artifact_text(
        '[{"published_at": "2026-06-13"}]', source_id="x", fmt="json"
    )
    assert cands[0].title is None
    assert cands[0].source_url is None
    assert cands[0].canonical_url is None


def test_format_sniffed_when_not_given():
    cands, name, _ = parse_artifact_text(_read("rss_minimal.xml"), source_id="bbc")
    assert name == "rss"


def test_html_artifact_routed_to_unsupported_fallback():
    # HTML은 XML 파서로 오분류되지 않고 정직한 미지원 fallback으로 보고된다.
    cands, name, errors = parse_artifact_text(_read("html_page.html"), source_id="zdnet_korea")
    assert cands == []
    assert name == "html_unsupported"
    assert errors == ["html_parsing_deferred_phase_d"]


def test_extracted_text_ignores_dashes_inside_body():
    # 본문 내부의 '---'(markdown 구분선)가 헤더 경계를 깨면 안 된다.
    text = (
        "title: Real Title\n"
        "source_url: https://x.test/a\n"
        "---\n"
        "First paragraph.\n"
        "---\n"
        "Second paragraph after a divider.\n"
    )
    cands, name, _ = parse_artifact_text(text, source_id="bbc", fmt="extracted_text")
    assert name == "extracted_text"
    assert cands[0].title == "Real Title"
    assert cands[0].source_url == "https://x.test/a"
    # body는 첫 '---' 이후 전체(두 번째 '---' 포함)를 보존
    assert "First paragraph." in cands[0].body_text
    assert "Second paragraph after a divider." in cands[0].body_text


def test_extracted_text_without_header_keeps_full_body():
    # 기대 키 없는 '---'는 헤더로 오인하지 않고 전체를 body로 둔다.
    text = "Just a body line.\n---\nMore body.\n"
    cands, name, _ = parse_artifact_text(text, source_id="bbc", fmt="extracted_text")
    assert cands[0].title is None
    assert "Just a body line." in cands[0].body_text

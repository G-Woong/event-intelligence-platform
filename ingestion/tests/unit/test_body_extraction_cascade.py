"""Phase E-1: body extraction cascade + 파서 보강(content:encoded/atom/nested/error envelope)."""
from __future__ import annotations

from pathlib import Path

from ingestion.orchestration.artifact_parser import parse_artifact_text
from ingestion.orchestration.body_state import assess_body_state

_FIX = Path(__file__).parent.parent / "fixtures" / "orchestration"


def _read(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


def test_rss_content_encoded_extracted_as_body():
    cands, name, _ = parse_artifact_text(
        _read("rss_content_encoded.xml"), source_id="bbc", fmt="xml")
    assert name == "rss"
    assert len(cands) == 2
    # content:encoded가 있는 항목 → body 회수(태그 제거 후 텍스트)
    first = cands[0]
    assert first.body_text and "synthetic full article body" in first.body_text
    assert "<p>" not in first.body_text  # HTML 태그 제거됨
    st = assess_body_state(body_text=first.body_text, summary=first.summary, purpose="news")
    assert st.extraction_status == "present"


def test_rss_snippet_only_when_no_content_encoded():
    cands, _, _ = parse_artifact_text(
        _read("rss_content_encoded.xml"), source_id="bbc", fmt="xml")
    second = cands[1]
    assert second.body_text is None  # content:encoded 없음 → 본문 없음(날조 안 함)
    st = assess_body_state(body_text=second.body_text, summary=second.summary, purpose="news")
    assert st.extraction_status == "snippet_only"


def test_atom_content_extracted_as_body():
    cands, name, _ = parse_artifact_text(
        _read("atom_content.xml"), source_id="x", fmt="xml")
    assert name == "atom"
    assert len(cands) == 1
    assert cands[0].body_text and "synthetic atom content body" in cands[0].body_text
    st = assess_body_state(body_text=cands[0].body_text, purpose="news")
    assert st.extraction_status == "present"


def test_nested_hits_hits_decomposed():
    # 어댑터 미등록 source_id로 generic nested(hits.hits) 분해 메커니즘 자체를 검증한다.
    # (sec_edgar는 E-3에서 전용 adapter가 generic을 선제하므로 별도 테스트로 분리)
    cands, name, _ = parse_artifact_text(
        _read("es_nested_hits.json"), source_id="generic_es", fmt="json")
    assert name == "generic_json_nested:hits.hits"
    assert len(cands) == 2
    # _source 평탄화로 nested url 회수
    assert cands[0].source_url == "https://filings.test/0000-00-000001"


def test_nested_response_docs_with_headline_main():
    cands, name, _ = parse_artifact_text(
        _read("nyt_nested_docs.json"), source_id="nyt", fmt="json")
    assert name == "generic_json_nested:response.docs"
    assert len(cands) == 2
    # 중첩 headline.main을 title로 회수
    assert cands[0].title == "Synthetic Nested Headline One"
    assert cands[0].source_url.startswith("https://news.test/2026/06/02/synthetic-a")
    # canonical은 no-network 정규화로 utm 제거
    assert cands[0].canonical_url == "https://news.test/2026/06/02/synthetic-a"
    assert cands[0].published_at == "2026-06-02T08:00:00Z"


def test_error_envelope_status_message_classified():
    cands, name, errors = parse_artifact_text(
        _read("api_error_status.json"), source_id="opendart", fmt="json")
    assert cands == []
    assert name == "api_error_payload"
    assert errors and "api_error_envelope:status_message" in errors[0]


def test_error_envelope_result_code_classified():
    cands, name, errors = parse_artifact_text(
        _read("api_error_result.json"), source_id="bok_ecos", fmt="json")
    assert cands == []
    assert name == "api_error_payload"
    assert errors and "result_code" in errors[0]


def test_success_status_not_flagged_as_error():
    # status="000"(성공)은 에러 봉투(api_error_payload)로 오분류되지 않는다.
    # (도메인 카탈로그 컨테이너는 의도적으로 미분해 → json_unrecognized, NEEDS_PARSER)
    text = '{"status": "000", "message": "ok", "list": [{"name": "A"}, {"name": "B"}]}'
    cands, name, _ = parse_artifact_text(text, source_id="opendart", fmt="json")
    assert name == "json_unrecognized"
    assert name != "api_error_payload"


def test_numeric_payload_still_structured_signal():
    cands, name, _ = parse_artifact_text(
        _read("api_numeric_payload.json"), source_id="finnhub", fmt="json")
    assert name == "numeric_payload"
    assert cands[0].numeric_payload_exempt is True
    st = assess_body_state(numeric_payload_exempt=True, purpose="numeric")
    assert st.extraction_status == "numeric_exempt"


def test_snippet_only_not_promoted_to_present():
    # summary만 길어도 body_present로 승격되지 않는다(긍정편향 금지).
    long_summary = "x " * 300
    st = assess_body_state(body_text=None, summary=long_summary, purpose="news")
    assert st.extraction_status == "snippet_only"
    assert st.body_missing is True


def test_feed_excerpt_with_full_story_link_not_present():
    # 길이가 임계를 넘어도 "Read the full story at ..." 발췌는 full body로 승격 금지.
    excerpt = ("This is a long synthetic excerpt that exceeds two hundred characters "
               "so it would otherwise pass the length gate, but it is only a feed "
               "teaser and not the full article body, as the trailing marker shows. "
               "Read the full story at The Verge.")
    assert len(excerpt) >= 200
    st = assess_body_state(body_text=excerpt, purpose="news")
    assert st.extraction_status == "snippet_only"
    assert st.body_source == "body_excerpt"
    assert st.body_missing is True

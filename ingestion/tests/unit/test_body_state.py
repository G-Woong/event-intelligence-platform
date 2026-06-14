"""Phase D-3: BodyExtractionState cascade 판정."""
from __future__ import annotations

from ingestion.orchestration.article_candidate import ArticleCandidate
from ingestion.orchestration.body_state import (
    FULL_BODY_MIN,
    assess_body_state,
    assess_candidate_body,
)


def test_full_body_present():
    s = assess_body_state(body_text="x" * (FULL_BODY_MIN + 10), purpose="news")
    assert s.extraction_status == "present"
    assert s.body_missing is False
    assert s.body_source == "body"
    assert s.snippet_only is False


def test_body_missing_when_empty():
    s = assess_body_state(body_text="", summary=None, purpose="news")
    assert s.extraction_status == "missing"
    assert s.body_missing is True
    assert s.body_source is None


def test_whitespace_only_body_is_missing():
    s = assess_body_state(body_text="    \n\t  ", purpose="news")
    assert s.extraction_status == "missing"
    assert s.body_missing is True


def test_snippet_only_not_treated_as_full_body():
    s = assess_body_state(body_text=None, summary="short snippet", purpose="news")
    assert s.extraction_status == "snippet_only"
    assert s.snippet_only is True
    assert s.body_missing is True  # snippet은 본문 아님
    assert s.body_source == "summary"


def test_partial_body_between_thresholds():
    s = assess_body_state(body_text="y" * 80, purpose="news")  # 50<=80<200
    assert s.extraction_status == "partial"
    assert s.partial is True
    assert s.body_missing is False


def test_numeric_payload_exempt():
    s = assess_body_state(numeric_payload_exempt=True)
    assert s.extraction_status == "numeric_exempt"
    assert s.body_missing is False  # numeric은 본문 없음이 정상
    assert s.numeric_payload_exempt is True


def test_trend_purpose_exempt():
    s = assess_body_state(body_text=None, purpose="trend")
    assert s.extraction_status == "numeric_exempt"
    assert s.body_missing is False


def test_extracted_text_priority_counts_as_body():
    # 충분히 긴 추출 본문 → present (extracted/candidate body 우선)
    s = assess_body_state(body_text="z" * 300, summary="ignore me", purpose="news")
    assert s.extraction_status == "present"
    assert s.body_source == "body"


def test_parser_error_state():
    s = assess_body_state(parse_error="json decode error", artifact_present=True)
    assert s.extraction_status == "parser_error"
    assert s.body_missing is True
    assert s.reason == "json decode error"


def test_no_artifact_state():
    s = assess_body_state(artifact_present=False)
    assert s.extraction_status == "no_artifact"
    assert s.body_missing is True


def test_malformed_state():
    s = assess_body_state(malformed=True)
    assert s.extraction_status == "malformed"
    assert s.body_missing is True


def test_community_lower_threshold():
    # community는 50자면 full로 인정
    s = assess_body_state(body_text="c" * 60, purpose="community")
    assert s.extraction_status == "present"


def test_assess_candidate_body_from_candidate():
    cand = ArticleCandidate(
        source_id="finnhub", numeric_payload_exempt=True, body_missing=True,
        parser_name="numeric_payload",
    )
    s = assess_candidate_body(cand, purpose="numeric")
    assert s.extraction_status == "numeric_exempt"

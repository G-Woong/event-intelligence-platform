from __future__ import annotations

import pytest
from datetime import datetime

from ingestion.schemas.raw_document import RawDocument
from ingestion.schemas.extracted_article import ExtractedArticle
from ingestion.schemas.extracted_post import ExtractedPost
from ingestion.schemas.event_candidate import EventCandidate
from ingestion.schemas.extraction_diagnostics import ExtractionDiagnostics
from ingestion.schemas.source_report import SourceReport


def test_raw_document_valid():
    doc = RawDocument(
        source_id="bbc",
        url="https://bbc.com/news/1",
        status_code=200,
        html="<html><body>content</body></html>",
        strategy="httpx_direct",
        elapsed_sec=0.5,
        content_length=1024,
    )
    assert doc.source_id == "bbc"
    assert isinstance(doc.fetched_at, datetime)


def test_extracted_article_defaults():
    art = ExtractedArticle(
        source_id="reuters",
        url="https://reuters.com/article/1",
        strategy="readability",
    )
    assert art.quality_score == 0.0
    assert art.quality_status == "FAILED"
    assert art.body is None


def test_extracted_post_engagement():
    post = ExtractedPost(
        source_id="reddit",
        url="https://reddit.com/r/news/1",
        strategy="httpx_direct",
        title="Big news",
        engagement={"upvotes": 1000, "comments": 50},
    )
    assert post.engagement["upvotes"] == 1000


def test_event_candidate_fields():
    candidate = EventCandidate(
        source_id="bbc",
        url="https://bbc.com/news/1",
        title="Earthquake in Region X",
        summary="A 6.5 magnitude earthquake struck Region X.",
        entities=["Region X"],
        regions=["Asia"],
        sectors=["natural_disaster"],
        significance=0.8,
        confidence=0.9,
    )
    assert candidate.significance == 0.8
    assert "Region X" in candidate.entities


def test_extraction_diagnostics():
    diag = ExtractionDiagnostics(
        source_id="guardian",
        url="https://theguardian.com/1",
        attempt_no=2,
        strategy="trafilatura",
        success=True,
        quality_score=0.75,
        quality_status="SUCCESS",
        body_length=1200,
        title_present=True,
        published_at_present=True,
        strategies_tried=["httpx_direct", "trafilatura"],
    )
    assert diag.quality_status == "SUCCESS"
    assert len(diag.strategies_tried) == 2


def test_source_report_valid():
    report = SourceReport(
        source_id="bbc",
        source_name="BBC News",
        source_type="news",
        evidence_level="tier1",
        phase=1,
        status="SUCCESS",
        quality_score=0.82,
        attempts=2,
        strategy_used="readability",
        urls_crawled=5,
        articles_extracted=4,
        event_candidates_found=3,
    )
    assert report.status == "SUCCESS"
    assert report.quality_score == 0.82


def test_source_report_serialization():
    report = SourceReport(
        source_id="test",
        source_name="Test Source",
        source_type="news",
        evidence_level="tier2",
        phase=1,
        status="PARTIAL",
        quality_score=0.55,
        attempts=3,
        strategy_used=None,
        urls_crawled=2,
        articles_extracted=1,
        event_candidates_found=0,
        errors=[{"error_type": "EXTRACTION_TOO_SHORT", "attempt_no": 1, "raw_message": "too short"}],
    )
    d = report.model_dump()
    assert d["status"] == "PARTIAL"
    assert len(d["errors"]) == 1

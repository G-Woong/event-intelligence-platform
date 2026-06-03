from __future__ import annotations

import pytest

from ingestion.core.quality_score import (
    QualityMetrics,
    build_metrics_from_extraction,
    compute_quality_score,
    determine_quality_status,
)


def _full_metrics() -> QualityMetrics:
    return QualityMetrics(
        title_present=True,
        body_length=2000,
        body_text_ratio=0.85,
        published_at_present=True,
        author_present=True,
        language_detected=True,
        boilerplate_ratio=0.05,
        sentence_count=15,
        keyword_density=0.12,
        metadata_completeness=0.9,
    )


def _empty_metrics() -> QualityMetrics:
    return QualityMetrics(
        title_present=False,
        body_length=0,
        body_text_ratio=0.0,
        published_at_present=False,
        author_present=False,
        language_detected=False,
        boilerplate_ratio=1.0,
        sentence_count=0,
        keyword_density=0.0,
        metadata_completeness=0.0,
    )


def test_full_metrics_score_above_threshold():
    score = compute_quality_score(_full_metrics(), source_type="news")
    assert score >= 0.70


def test_empty_metrics_score_below_threshold():
    score = compute_quality_score(_empty_metrics(), source_type="news")
    assert score < 0.40


def test_score_bounded():
    score = compute_quality_score(_full_metrics(), source_type="news")
    assert 0.0 <= score <= 1.0


def test_determine_status_success():
    assert determine_quality_status(0.80) == "SUCCESS"


def test_determine_status_partial():
    assert determine_quality_status(0.55) == "PARTIAL"


def test_determine_status_failed():
    assert determine_quality_status(0.30) == "FAILED"


def test_determine_status_blocked():
    assert determine_quality_status(0.90, is_blocked=True) == "BLOCKED"


def test_community_source_type():
    metrics = QualityMetrics(
        title_present=True,
        body_length=100,
        body_text_ratio=0.8,
        published_at_present=False,
        author_present=False,
        language_detected=True,
        boilerplate_ratio=0.1,
        sentence_count=5,
        keyword_density=0.08,
        metadata_completeness=0.3,
    )
    score = compute_quality_score(metrics, source_type="community")
    assert score > 0.0


def test_build_metrics_from_extraction():
    metrics = build_metrics_from_extraction(
        title="Test Article",
        body="This is a test body. " * 30,
        author="John Doe",
        published_at="2024-01-01",
        language="en",
        metadata={"description": "test"},
    )
    assert metrics.title_present is True
    assert metrics.body_length > 0
    assert metrics.published_at_present is True

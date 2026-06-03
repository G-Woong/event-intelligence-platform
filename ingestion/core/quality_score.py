from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SourceType = Literal["news", "community", "official"]
QualityStatus = Literal["SUCCESS", "PARTIAL", "BLOCKED", "FAILED"]

_WEIGHTS: dict[str, float] = {
    "title_present": 0.15,
    "body_length": 0.20,
    "body_text_ratio": 0.10,
    "published_at_present": 0.10,
    "author_present": 0.05,
    "language_detected": 0.10,
    "boilerplate_ratio": 0.15,
    "sentence_count": 0.05,
    "keyword_density": 0.05,
    "metadata_completeness": 0.05,
}

_MIN_BODY = {"news": 300, "community": 50, "official": 200}
_FULL_BODY = {"news": 1500, "community": 500, "official": 1000}

SUCCESS_THRESHOLD = 0.70
PARTIAL_THRESHOLD = 0.40


@dataclass
class QualityMetrics:
    title_present: bool
    body_length: int
    body_text_ratio: float
    published_at_present: bool
    author_present: bool
    language_detected: bool
    boilerplate_ratio: float
    sentence_count: int
    keyword_density: float
    metadata_completeness: float


def _normalize_body_length(length: int, source_type: SourceType) -> float:
    min_len = _MIN_BODY[source_type]
    max_len = _FULL_BODY[source_type]
    if length >= max_len:
        return 1.0
    if length < min_len:
        return 0.0
    return (length - min_len) / (max_len - min_len)


def _normalize_sentence_count(count: int) -> float:
    return min(1.0, count / 10.0)


def compute_quality_score(
    metrics: QualityMetrics,
    source_type: SourceType = "news",
) -> float:
    raw: dict[str, float] = {
        "title_present": 1.0 if metrics.title_present else 0.0,
        "body_length": _normalize_body_length(metrics.body_length, source_type),
        "body_text_ratio": min(1.0, max(0.0, metrics.body_text_ratio)),
        "published_at_present": 1.0 if metrics.published_at_present else 0.0,
        "author_present": 1.0 if metrics.author_present else 0.0,
        "language_detected": 1.0 if metrics.language_detected else 0.0,
        "boilerplate_ratio": max(0.0, 1.0 - metrics.boilerplate_ratio),
        "sentence_count": _normalize_sentence_count(metrics.sentence_count),
        "keyword_density": min(1.0, metrics.keyword_density * 10.0),
        "metadata_completeness": min(1.0, max(0.0, metrics.metadata_completeness)),
    }
    return sum(raw[k] * _WEIGHTS[k] for k in _WEIGHTS)


def determine_quality_status(
    score: float,
    is_blocked: bool = False,
) -> QualityStatus:
    if is_blocked:
        return "BLOCKED"
    if score >= SUCCESS_THRESHOLD:
        return "SUCCESS"
    if score >= PARTIAL_THRESHOLD:
        return "PARTIAL"
    return "FAILED"


def build_metrics_from_extraction(
    title: str | None,
    body: str | None,
    author: str | None,
    published_at: str | None,
    language: str | None,
    metadata: dict,
) -> QualityMetrics:
    body_text = body or ""
    words = body_text.split()
    sentences = [s for s in body_text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    unique_words = set(w.lower() for w in words)
    keyword_density = len(unique_words) / max(len(words), 1)

    expected_meta_fields = {"title", "author", "published_at", "language", "description"}
    present_meta = sum(1 for f in expected_meta_fields if metadata.get(f))
    meta_completeness = present_meta / len(expected_meta_fields)

    return QualityMetrics(
        title_present=bool(title and title.strip()),
        body_length=len(body_text),
        body_text_ratio=min(1.0, len(body_text) / max(len(body_text) * 1.2, 1)),
        published_at_present=bool(published_at),
        author_present=bool(author),
        language_detected=bool(language),
        boilerplate_ratio=0.2 if len(body_text) < 200 else 0.05,
        sentence_count=len(sentences),
        keyword_density=keyword_density,
        metadata_completeness=meta_completeness,
    )

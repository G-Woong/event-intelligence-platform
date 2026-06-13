from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ingestion.core.error_taxonomy import ErrorType
from ingestion.core.extraction_result import ExtractionResult
from ingestion.core.fetch_result import FetchResult
from ingestion.probes.models import ProbeResult

# Type aliases matching existing vocabulary
FetchStrategy = str   # one of STRATEGY_SEQUENCE values
FailureCategory = ErrorType


@dataclass
class FetchAttempt:
    strategy: str
    success: bool
    error_type: Optional[ErrorType] = None
    delay_sec: float = 0.0
    elapsed_sec: float = 0.0
    status_code: int = 0


@dataclass
class ArtifactPaths:
    raw_html: Optional[str] = None
    raw_payload: Optional[str] = None
    extracted_payload: Optional[str] = None
    screenshot: Optional[str] = None
    rendered_dom: Optional[str] = None
    raw_signal: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in vars(self).items() if v is not None}


@dataclass
class RenderedPageFetchResult:
    """Standardised result from cloud-browser-like page rendering.

    Mirrors what cloud browser APIs return (html, markdown, screenshot,
    rendered DOM, extraction text) but fulfilled by our internal Playwright stack.
    """
    url: str
    strategy_used: str
    html: Optional[str] = None
    markdown: Optional[str] = None
    screenshot_path: Optional[str] = None
    rendered_dom_path: Optional[str] = None
    extracted_text: Optional[str] = None
    status: str = "UNKNOWN"
    error_category: Optional[ErrorType] = None
    timing: float = 0.0


@dataclass
class ExtractionBundle:
    fetch_result: Optional[FetchResult] = None
    extraction_result: Optional[ExtractionResult] = None
    rendered_page: Optional[RenderedPageFetchResult] = None
    markdown: Optional[str] = None


@dataclass
class CollectionProbeResult:
    """Top-level result returned to the Agent by run_collection_probe."""
    source_id: str
    status: str  # PROBE_STATUS value
    strategy_used: str = ""
    items_found: int = 0
    probe_result: Optional[ProbeResult] = None
    fetch_result: Optional[FetchResult] = None
    extraction: Optional[ExtractionBundle] = None
    artifact_paths: ArtifactPaths = field(default_factory=ArtifactPaths)
    error_category: Optional[str] = None
    next_action: str = ""
    attempts: list = field(default_factory=list)  # list[FetchAttempt]


@dataclass
class StrategyLoopResult:
    """Result of iterating STRATEGY_SEQUENCE for a single URL."""
    source_id: str
    url: str
    status: str  # "success" | "exhausted" | "blocked" | "rate_limited" | "cached"
    attempts: list = field(default_factory=list)  # list[FetchAttempt]
    final_html: Optional[str] = None
    final_error_type: Optional[ErrorType] = None

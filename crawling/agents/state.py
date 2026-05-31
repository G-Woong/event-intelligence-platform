from __future__ import annotations

from typing import Optional, TypedDict


class CrawlingAgentState(TypedDict):
    # source identification
    source_id: str
    source_spec: dict
    phase: int

    # attempt / strategy tracking
    attempt_no: int
    max_attempts: int
    strategy_sequence: list[str]
    current_strategy: str
    strategies_tried: list[str]

    # url / html
    entry_url: str
    candidate_urls: list[str]
    current_url: str
    raw_html: Optional[str]

    # extraction
    extraction_result: Optional[dict]
    quality_score: float
    quality_status: str  # SUCCESS / PARTIAL / BLOCKED / FAILED

    # events
    event_candidates: list[dict]

    # errors
    errors: list[dict]
    current_error: Optional[dict]

    # llm judge
    llm_judge_result: Optional[dict]

    # run metadata
    run_id: str
    url_hash: str
    query: str

    # artifact paths (str for TypedDict serialization)
    raw_html_path: Optional[str]
    dom_snapshot_path: Optional[str]
    screenshot_path: Optional[str]
    extracted_text_path: Optional[str]

    # legacy artifact lists (kept for compatibility)
    screenshots: list[str]
    dom_snapshots: list[str]

    # per-attempt history
    retry_history: list[dict]

    # control flow
    status: str  # RUNNING / SUCCESS / PARTIAL / BLOCKED / FAILED
    should_retry: bool
    retry_reason: str
    strategy_exhausted: bool

    # final
    final_report: Optional[dict]

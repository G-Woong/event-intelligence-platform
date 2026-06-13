from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

PROBE_STATUS: frozenset[str] = frozenset({
    "LIVE_SUCCESS",
    "LIVE_PARTIAL",
    "MISSING_KEY",
    "INVALID_KEY",
    "PERMISSION_DENIED",
    "RATE_LIMITED",
    "QUOTA_EXHAUSTED",
    "PLAN_RESTRICTED",
    "ENDPOINT_DEPRECATED",
    "SCHEMA_CHANGED",
    "PARSE_ERROR",
    "NETWORK_ERROR",
    "TIMEOUT",
    "BLOCKED",
    "DEFERRED",
    "UNKNOWN",
    # New API-level classifications (source repair round)
    "QUERY_ENCODING_OR_PARAM_ERROR",
    "INVALID_SYMBOL_OR_EMPTY_MARKET_DATA",
    "XML_PARAMETER_ERROR",
    "API_RETURNED_HTML_ERROR_PAGE",
    "PARAMETER_MISSING",
    "ENDPOINT_INVALID",
    "DYNAMIC_RENDER_REQUIRED",
    "SELECTOR_MATCHED_BUT_URL_EMPTY",
    "LOW_EVIDENCE_EXTERNAL_SIGNAL",
})


@dataclass
class ProbeResult:
    source_id: str
    method: str  # "api" | "playwright"
    query: Optional[str] = None
    region: Optional[str] = None
    status: str = "UNKNOWN"
    http_status: Optional[int] = None
    items_found: int = 0
    items_extracted: int = 0
    meaningful_fields: list = field(default_factory=list)
    artifact_paths: dict = field(default_factory=dict)
    error_category: Optional[str] = None
    next_action: str = ""
    # Retry / rate-limit metadata
    cooldown_seconds: Optional[int] = None
    next_retry_at: Optional[str] = None   # ISO 8601 timestamp
    retry_after_reason: Optional[str] = None
    cache_hit: bool = False
    # Network observation log (KRX XHR capture etc.)
    network_log: Optional[list] = None

    def __post_init__(self) -> None:
        if self.status not in PROBE_STATUS:
            raise ValueError(f"Invalid status: {self.status!r}. Must be one of PROBE_STATUS.")

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "method": self.method,
            "query": self.query,
            "region": self.region,
            "status": self.status,
            "http_status": self.http_status,
            "items_found": self.items_found,
            "items_extracted": self.items_extracted,
            "meaningful_fields": self.meaningful_fields,
            "artifact_paths": {k: str(v) for k, v in self.artifact_paths.items()},
            "error_category": self.error_category,
            "next_action": self.next_action,
            "cooldown_seconds": self.cooldown_seconds,
            "next_retry_at": self.next_retry_at,
            "retry_after_reason": self.retry_after_reason,
            "cache_hit": self.cache_hit,
            "network_log": self.network_log,
        }

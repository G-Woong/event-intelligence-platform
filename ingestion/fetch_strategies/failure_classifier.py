from __future__ import annotations

from typing import Union

from ingestion.core.error_taxonomy import (
    ErrorType,
    classify_content_blocker,
    classify_http_error,
)
from ingestion.core.fetch_result import FetchResult
from ingestion.probes.models import ProbeResult

_PROBE_STATUS_TO_ERROR_TYPE: dict[str, ErrorType] = {
    "RATE_LIMITED": ErrorType.RATE_LIMITED,
    "PERMISSION_DENIED": ErrorType.HTTP_4XX,
    "INVALID_KEY": ErrorType.INVALID_KEY,
    "PLAN_RESTRICTED": ErrorType.HTTP_4XX,
    "ENDPOINT_DEPRECATED": ErrorType.ENDPOINT_INVALID,
    "BLOCKED": ErrorType.LOGIN_WALL_DETECTED,
    "TIMEOUT": ErrorType.NETWORK_TIMEOUT,
    "NETWORK_ERROR": ErrorType.HTTP_5XX,
    "MISSING_KEY": ErrorType.UNKNOWN_ERROR,
    "UNKNOWN": ErrorType.UNKNOWN_ERROR,
    "PARSE_ERROR": ErrorType.DOM_PARSE_ERROR,
    "LIVE_PARTIAL": ErrorType.QUALITY_PARTIAL,
    # New classifications
    "QUERY_ENCODING_OR_PARAM_ERROR": ErrorType.QUERY_ENCODING_OR_PARAM_ERROR,
    "INVALID_SYMBOL_OR_EMPTY_MARKET_DATA": ErrorType.INVALID_SYMBOL_OR_EMPTY_MARKET_DATA,
    "XML_PARAMETER_ERROR": ErrorType.XML_PARAMETER_ERROR,
    "API_RETURNED_HTML_ERROR_PAGE": ErrorType.API_RETURNED_HTML_ERROR_PAGE,
    "PARAMETER_MISSING": ErrorType.PARAMETER_MISSING,
    "ENDPOINT_INVALID": ErrorType.ENDPOINT_INVALID,
    "DYNAMIC_RENDER_REQUIRED": ErrorType.DYNAMIC_RENDER_REQUIRED,
    "SELECTOR_MATCHED_BUT_URL_EMPTY": ErrorType.SELECTOR_MATCHED_BUT_URL_EMPTY,
    "LOW_EVIDENCE_EXTERNAL_SIGNAL": ErrorType.LOW_EVIDENCE_EXTERNAL_SIGNAL,
}


def classify_failure(
    result_or_exception: Union[FetchResult, ProbeResult, Exception, ErrorType],
) -> ErrorType:
    """Single entry: convert any failure representation to ErrorType.

    Delegates internally to classify_http_error and classify_content_blocker.
    Handles FetchResult, ProbeResult, Exception, and bare ErrorType passthrough.
    """
    if isinstance(result_or_exception, ErrorType):
        return result_or_exception

    if isinstance(result_or_exception, FetchResult) and not result_or_exception.success:
        if result_or_exception.status_code >= 400:
            return classify_http_error(result_or_exception.status_code)
        if result_or_exception.html:
            blocker = classify_content_blocker(result_or_exception.html.lower())
            if blocker:
                return blocker
        msg = (result_or_exception.error_message or "").lower()
        if "timeout" in msg:
            return ErrorType.NETWORK_TIMEOUT
        if "connection" in msg or "reset" in msg:
            return ErrorType.NETWORK_CONNECTION_RESET
        if "dns" in msg or "name resolution" in msg:
            return ErrorType.NETWORK_DNS_FAIL
        return ErrorType.UNKNOWN_ERROR

    if isinstance(result_or_exception, ProbeResult):
        return _PROBE_STATUS_TO_ERROR_TYPE.get(
            result_or_exception.status, ErrorType.UNKNOWN_ERROR
        )

    if isinstance(result_or_exception, Exception):
        cls_name = type(result_or_exception).__name__.lower()
        msg = str(result_or_exception).lower()
        if "timeout" in cls_name or "timeout" in msg:
            return ErrorType.NETWORK_TIMEOUT
        if "connection" in msg or "reset" in msg:
            return ErrorType.NETWORK_CONNECTION_RESET
        if "dns" in msg or ("name" in msg and "resolv" in msg):
            return ErrorType.NETWORK_DNS_FAIL
        if "captcha" in msg:
            return ErrorType.CAPTCHA_DETECTED
        if "login" in msg or "sign in" in msg:
            return ErrorType.LOGIN_WALL_DETECTED
        return ErrorType.UNKNOWN_ERROR

    return ErrorType.UNKNOWN_ERROR

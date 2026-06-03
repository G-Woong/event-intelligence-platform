from __future__ import annotations

import pytest

from ingestion.core.error_taxonomy import (
    ErrorRecord,
    ErrorType,
    BLOCKED_ERRORS,
    RETRYABLE_ERRORS,
    classify_content_blocker,
    classify_http_error,
)


def test_error_type_count():
    assert len(ErrorType) == 34  # +8 API-level error types added in source repair round


def test_retryable_errors_are_subset():
    assert RETRYABLE_ERRORS.issubset(set(ErrorType))


def test_blocked_errors_are_subset():
    assert BLOCKED_ERRORS.issubset(set(ErrorType))


def test_retryable_and_blocked_are_disjoint():
    assert RETRYABLE_ERRORS.isdisjoint(BLOCKED_ERRORS)


def test_error_record_retryable():
    rec = ErrorRecord(
        source_id="bbc",
        url="https://example.com",
        attempt_no=1,
        strategy="httpx_direct",
        error_type=ErrorType.NETWORK_TIMEOUT,
        raw_message="timeout",
    )
    assert rec.retryable is True
    assert rec.is_blocker is False


def test_error_record_blocker():
    rec = ErrorRecord(
        source_id="wsj",
        url="https://wsj.com/article",
        attempt_no=1,
        strategy="playwright_basic",
        error_type=ErrorType.PAYWALL_DETECTED,
        raw_message="paywall",
    )
    assert rec.retryable is False
    assert rec.is_blocker is True


def test_error_record_to_dict_keys():
    rec = ErrorRecord(
        source_id="bbc",
        url="https://example.com",
        attempt_no=2,
        strategy="readability",
        error_type=ErrorType.EXTRACTION_EMPTY,
        raw_message="empty",
    )
    d = rec.to_dict()
    assert "error_type" in d
    assert d["error_type"] == "EXTRACTION_EMPTY"
    assert "retryable" in d
    assert "is_blocker" in d


def test_classify_http_error():
    assert classify_http_error(404) == ErrorType.HTTP_4XX
    assert classify_http_error(503) == ErrorType.HTTP_5XX
    assert classify_http_error(0) == ErrorType.NETWORK_TIMEOUT


def test_classify_content_blocker_captcha():
    html = "<html><body>Please solve the captcha to continue</body></html>"
    result = classify_content_blocker(html.lower())
    assert result == ErrorType.CAPTCHA_DETECTED


def test_classify_content_blocker_cf_challenge():
    """CF challenge page body attribute should be detected."""
    html = '<html><body class="no-js" data-cf-challenge="abc123">Just a moment...</body></html>'
    result = classify_content_blocker(html.lower())
    assert result == ErrorType.CAPTCHA_DETECTED


def test_classify_content_blocker_captcha_word_only_is_none():
    """Bare word 'captcha' in a normal article must NOT trigger detection (false-positive guard)."""
    html = "<html><body>The site added a captcha last year to combat spam bots.</body></html>"
    result = classify_content_blocker(html.lower())
    assert result is None


def test_classify_content_blocker_none():
    html = "<html><body>This is a normal article about world events.</body></html>"
    result = classify_content_blocker(html.lower())
    assert result is None


def test_new_error_types_exist():
    assert ErrorType.PARAMETER_MISSING
    assert ErrorType.ENDPOINT_INVALID
    assert ErrorType.INVALID_KEY
    assert ErrorType.QUERY_ENCODING_OR_PARAM_ERROR
    assert ErrorType.INVALID_SYMBOL_OR_EMPTY_MARKET_DATA
    assert ErrorType.XML_PARAMETER_ERROR
    assert ErrorType.API_RETURNED_HTML_ERROR_PAGE
    assert ErrorType.DYNAMIC_RENDER_REQUIRED


def test_invalid_key_not_retryable():
    rec = ErrorRecord(
        source_id="test",
        url="https://example.com",
        attempt_no=1,
        strategy="api",
        error_type=ErrorType.INVALID_KEY,
        raw_message="401",
    )
    assert rec.retryable is False
    assert rec.is_blocker is False


def test_classify_http_401_is_invalid_key():
    assert classify_http_error(401) == ErrorType.INVALID_KEY


def test_new_errors_not_retryable():
    for et in (
        ErrorType.PARAMETER_MISSING,
        ErrorType.ENDPOINT_INVALID,
        ErrorType.QUERY_ENCODING_OR_PARAM_ERROR,
        ErrorType.INVALID_SYMBOL_OR_EMPTY_MARKET_DATA,
        ErrorType.XML_PARAMETER_ERROR,
        ErrorType.API_RETURNED_HTML_ERROR_PAGE,
        ErrorType.DYNAMIC_RENDER_REQUIRED,
    ):
        assert et not in RETRYABLE_ERRORS, f"{et} should not be retryable"
        assert et not in BLOCKED_ERRORS, f"{et} should not be a blocker"

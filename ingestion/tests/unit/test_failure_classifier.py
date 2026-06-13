from __future__ import annotations

import pytest

from ingestion.core.error_taxonomy import ErrorType
from ingestion.core.fetch_result import FetchResult
from ingestion.fetch_strategies.failure_classifier import classify_failure
from ingestion.probes.models import ProbeResult


# ── ErrorType passthrough ──────────────────────────────────────────────────

def test_passthrough_error_type():
    assert classify_failure(ErrorType.NETWORK_TIMEOUT) == ErrorType.NETWORK_TIMEOUT


def test_passthrough_blocked_error():
    assert classify_failure(ErrorType.CAPTCHA_DETECTED) == ErrorType.CAPTCHA_DETECTED


# ── FetchResult → ErrorType ────────────────────────────────────────────────

def test_fetch_result_http_403():
    r = FetchResult.failure("http://x.com", "httpx_direct", "403", status_code=403)
    assert classify_failure(r) == ErrorType.HTTP_4XX


def test_fetch_result_http_500():
    r = FetchResult.failure("http://x.com", "httpx_direct", "500", status_code=500)
    assert classify_failure(r) == ErrorType.HTTP_5XX


def test_fetch_result_timeout_message():
    r = FetchResult.failure("http://x.com", "httpx_direct", "timeout occurred", status_code=0)
    assert classify_failure(r) == ErrorType.NETWORK_TIMEOUT


def test_fetch_result_connection_reset():
    r = FetchResult.failure("http://x.com", "httpx_direct", "connection reset by peer", status_code=0)
    assert classify_failure(r) == ErrorType.NETWORK_CONNECTION_RESET


def test_fetch_result_captcha_html():
    r = FetchResult(
        url="http://x.com",
        strategy="httpx_direct",
        success=False,
        status_code=0,
        html="<html>just a moment...</html>",
    )
    assert classify_failure(r) == ErrorType.CAPTCHA_DETECTED


def test_fetch_result_login_wall_html():
    r = FetchResult(
        url="http://x.com",
        strategy="httpx_direct",
        success=False,
        status_code=0,
        html="<html>sign in to continue</html>",
    )
    assert classify_failure(r) == ErrorType.LOGIN_WALL_DETECTED


def test_fetch_result_unknown_error():
    r = FetchResult.failure("http://x.com", "httpx_direct", "some weird error", status_code=0)
    assert classify_failure(r) == ErrorType.UNKNOWN_ERROR


# ── ProbeResult → ErrorType ────────────────────────────────────────────────

def test_probe_result_rate_limited():
    pr = ProbeResult(source_id="gdelt", method="api", status="RATE_LIMITED")
    assert classify_failure(pr) == ErrorType.RATE_LIMITED


def test_probe_result_blocked():
    pr = ProbeResult(source_id="x", method="api", status="BLOCKED")
    assert classify_failure(pr) == ErrorType.LOGIN_WALL_DETECTED


def test_probe_result_timeout():
    pr = ProbeResult(source_id="x", method="api", status="TIMEOUT")
    assert classify_failure(pr) == ErrorType.NETWORK_TIMEOUT


def test_probe_result_network_error():
    pr = ProbeResult(source_id="x", method="api", status="NETWORK_ERROR")
    assert classify_failure(pr) == ErrorType.HTTP_5XX


def test_probe_result_parse_error():
    pr = ProbeResult(source_id="x", method="api", status="PARSE_ERROR")
    assert classify_failure(pr) == ErrorType.DOM_PARSE_ERROR


def test_probe_result_unknown():
    pr = ProbeResult(source_id="x", method="api", status="UNKNOWN")
    assert classify_failure(pr) == ErrorType.UNKNOWN_ERROR


# ── Exception → ErrorType ─────────────────────────────────────────────────

def test_exception_timeout():
    assert classify_failure(TimeoutError("request timeout")) == ErrorType.NETWORK_TIMEOUT


def test_exception_connection_reset():
    assert classify_failure(ConnectionResetError("connection reset")) == ErrorType.NETWORK_CONNECTION_RESET


def test_exception_generic():
    assert classify_failure(ValueError("unexpected")) == ErrorType.UNKNOWN_ERROR


def test_exception_captcha_message():
    exc = Exception("captcha required on this page")
    assert classify_failure(exc) == ErrorType.CAPTCHA_DETECTED


# ── Unknown type → UNKNOWN_ERROR ─────────────────────────────────────────

def test_unknown_input_type():
    assert classify_failure(None) == ErrorType.UNKNOWN_ERROR  # type: ignore[arg-type]


# ── New ErrorTypes: SELECTOR_MATCHED_BUT_URL_EMPTY / LOW_EVIDENCE_EXTERNAL_SIGNAL ──

def test_selector_matched_but_url_empty_mapping():
    pr = ProbeResult(source_id="eu_press_corner", method="playwright", status="SELECTOR_MATCHED_BUT_URL_EMPTY")
    assert classify_failure(pr) == ErrorType.SELECTOR_MATCHED_BUT_URL_EMPTY


def test_low_evidence_external_signal_mapping():
    pr = ProbeResult(source_id="loword", method="playwright", status="LOW_EVIDENCE_EXTERNAL_SIGNAL")
    assert classify_failure(pr) == ErrorType.LOW_EVIDENCE_EXTERNAL_SIGNAL

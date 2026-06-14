"""E-3: NEEDS_*를 clean terminal로 확정하는 finalize_unresolved_status — network 0."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ingestion.orchestration.full_source_revival import (
    DATA_ALIVE_STATUSES,
    TERMINAL_BLOCKED_STATUSES,
    finalize_unresolved_status,
)


@dataclass
class _Ladder:
    status: str = "NO_BODY"
    paywall_marker: bool = False
    login_marker: bool = False
    captcha_marker: bool = False
    http_status: Optional[int] = 200
    tool_unavailable: bool = False


def _fin(sid, grp, status, ladder=None):
    return finalize_unresolved_status(
        source_id=sid, source_group=grp, final_status=status,
        root_causes=("X",), next_action="x", ladder_result=ladder)


def test_already_alive_passthrough():
    fs, rc, na, cls = _fin("tmdb", "domain", "OFFICIAL_RECORD_ALIVE")
    assert fs == "OFFICIAL_RECORD_ALIVE" and cls == "data_alive"


def test_needs_parser_never_final_via_source_override():
    for sid, expected in [("kma", "EXTERNAL_API_ERROR_WITH_EVIDENCE"),
                          ("eia", "REQUIRES_VENDOR_SPECIFIC_API_CONTRACT"),
                          ("bok_ecos", "REQUIRES_VENDOR_SPECIFIC_API_CONTRACT"),
                          ("its", "NOT_SERVICE_USEFUL")]:
        fs, rc, na, cls = _fin(sid, "domain", "NEEDS_PARSER_UNRESOLVED")
        assert fs == expected and cls == "source_override"
        assert fs not in ("NEEDS_PARSER_UNRESOLVED", "NEEDS_BODY_FETCH_UNRESOLVED")


def test_body_fetch_success_becomes_article_alive():
    fs, rc, na, cls = _fin("ap_news", "news", "NEEDS_BODY_FETCH_UNRESOLVED",
                           _Ladder(status="SUCCESS"))
    assert fs == "ARTICLE_BODY_ALIVE"


def test_paywall_login_captcha_no_bypass():
    assert _fin("nyt", "news", "NEEDS_BODY_FETCH_UNRESOLVED",
                _Ladder(paywall_marker=True))[0] == "PAYWALL_BLOCKED_NO_BYPASS"
    assert _fin("x", "news", "NEEDS_BODY_FETCH_UNRESOLVED",
                _Ladder(login_marker=True))[0] == "LOGIN_BLOCKED_NO_BYPASS"
    assert _fin("x", "news", "NEEDS_BODY_FETCH_UNRESOLVED",
                _Ladder(captcha_marker=True))[0] == "CAPTCHA_BLOCKED_NO_BYPASS"


def test_http_403_anti_bot_external_error():
    fs, rc, na, cls = _fin("x", "news", "NEEDS_BODY_FETCH_UNRESOLVED",
                           _Ladder(status="HTTP_ERROR", http_status=403))
    assert fs == "EXTERNAL_API_ERROR_WITH_EVIDENCE"


def test_http_429_rate_limited():
    fs, *_ = _fin("x", "news", "NEEDS_BODY_FETCH_UNRESOLVED",
                  _Ladder(status="HTTP_ERROR", http_status=429))
    assert fs == "EXTERNAL_RATE_LIMITED_WITH_RETRY_POLICY"


def test_tool_unavailable_when_browser_needed_unavailable():
    fs, *_ = _fin("x", "news", "NEEDS_BODY_FETCH_UNRESOLVED",
                  _Ladder(status="NO_BODY", http_status=200, tool_unavailable=True))
    assert fs == "TOOL_UNAVAILABLE_FOR_REQUIRED_STRATEGY"


def test_residual_parser_without_ladder_becomes_contract():
    fs, rc, na, cls = _fin("unknown_src", "official", "NEEDS_PARSER_UNRESOLVED")
    assert fs == "REQUIRES_VENDOR_SPECIFIC_API_CONTRACT"


def test_all_terminal_outputs_are_resolved_not_needs():
    # finalize의 모든 출력은 NEEDS_*가 아니어야 한다(killer 보장).
    outs = [
        _fin("kma", "domain", "NEEDS_PARSER_UNRESOLVED")[0],
        _fin("ap_news", "news", "NEEDS_BODY_FETCH_UNRESOLVED", _Ladder(status="EXCERPT_ONLY"))[0],
        _fin("z", "news", "NEEDS_BODY_FETCH_UNRESOLVED", _Ladder(status="NO_BODY"))[0],
    ]
    for fs in outs:
        assert fs in (DATA_ALIVE_STATUSES | TERMINAL_BLOCKED_STATUSES)
        assert "NEEDS_" not in fs

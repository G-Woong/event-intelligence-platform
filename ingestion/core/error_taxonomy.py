from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ErrorType(Enum):
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    NETWORK_DNS_FAIL = "NETWORK_DNS_FAIL"
    NETWORK_CONNECTION_RESET = "NETWORK_CONNECTION_RESET"
    HTTP_4XX = "HTTP_4XX"
    RATE_LIMITED = "RATE_LIMITED"
    HTTP_5XX = "HTTP_5XX"
    HTTP_REDIRECT_LOOP = "HTTP_REDIRECT_LOOP"
    CAPTCHA_DETECTED = "CAPTCHA_DETECTED"
    LOGIN_WALL_DETECTED = "LOGIN_WALL_DETECTED"
    PAYWALL_DETECTED = "PAYWALL_DETECTED"
    ROBOTS_BLOCKED = "ROBOTS_BLOCKED"
    JS_RENDER_FAIL = "JS_RENDER_FAIL"
    DOM_PARSE_ERROR = "DOM_PARSE_ERROR"
    EXTRACTION_EMPTY = "EXTRACTION_EMPTY"
    EXTRACTION_TOO_SHORT = "EXTRACTION_TOO_SHORT"
    EXTRACTION_BOILERPLATE_ONLY = "EXTRACTION_BOILERPLATE_ONLY"
    EXTRACTION_ENCODING_ERROR = "EXTRACTION_ENCODING_ERROR"
    QUALITY_BELOW_THRESHOLD = "QUALITY_BELOW_THRESHOLD"
    QUALITY_PARTIAL = "QUALITY_PARTIAL"
    LLM_PARSE_ERROR = "LLM_PARSE_ERROR"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    SCREENSHOT_FAIL = "SCREENSHOT_FAIL"
    DOM_SNAPSHOT_FAIL = "DOM_SNAPSHOT_FAIL"
    CONFIG_ERROR = "CONFIG_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    # API-level parameter / key / format errors (non-retryable, non-blocker)
    PARAMETER_MISSING = "PARAMETER_MISSING"
    ENDPOINT_INVALID = "ENDPOINT_INVALID"
    INVALID_KEY = "INVALID_KEY"
    QUERY_ENCODING_OR_PARAM_ERROR = "QUERY_ENCODING_OR_PARAM_ERROR"
    INVALID_SYMBOL_OR_EMPTY_MARKET_DATA = "INVALID_SYMBOL_OR_EMPTY_MARKET_DATA"
    XML_PARAMETER_ERROR = "XML_PARAMETER_ERROR"
    API_RETURNED_HTML_ERROR_PAGE = "API_RETURNED_HTML_ERROR_PAGE"
    DYNAMIC_RENDER_REQUIRED = "DYNAMIC_RENDER_REQUIRED"
    # Playwright selector matched but extracted href/url was empty (selector fallback signal)
    SELECTOR_MATCHED_BUT_URL_EMPTY = "SELECTOR_MATCHED_BUT_URL_EMPTY"
    # Low-credibility external signal (official=false, evidence_level=low)
    LOW_EVIDENCE_EXTERNAL_SIGNAL = "LOW_EVIDENCE_EXTERNAL_SIGNAL"


RETRYABLE_ERRORS: frozenset[ErrorType] = frozenset({
    ErrorType.NETWORK_TIMEOUT,
    ErrorType.NETWORK_CONNECTION_RESET,
    ErrorType.HTTP_5XX,
    ErrorType.JS_RENDER_FAIL,
    ErrorType.LLM_TIMEOUT,
    ErrorType.LLM_RATE_LIMIT,
})

BLOCKED_ERRORS: frozenset[ErrorType] = frozenset({
    ErrorType.CAPTCHA_DETECTED,
    ErrorType.LOGIN_WALL_DETECTED,
    ErrorType.PAYWALL_DETECTED,
    ErrorType.ROBOTS_BLOCKED,
})


@dataclass
class ErrorRecord:
    source_id: str
    url: str
    attempt_no: int
    strategy: str
    error_type: ErrorType
    raw_message: str
    screenshot_path: Optional[str] = None
    dom_snapshot_path: Optional[str] = None
    suggested_fix: str = ""
    retryable: bool = field(init=False)
    is_blocker: bool = field(init=False)

    def __post_init__(self) -> None:
        self.retryable = self.error_type in RETRYABLE_ERRORS
        self.is_blocker = self.error_type in BLOCKED_ERRORS

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "url": self.url,
            "attempt_no": self.attempt_no,
            "strategy": self.strategy,
            "error_type": self.error_type.value,
            "raw_message": self.raw_message,
            "screenshot_path": self.screenshot_path,
            "dom_snapshot_path": self.dom_snapshot_path,
            "suggested_fix": self.suggested_fix,
            "retryable": self.retryable,
            "is_blocker": self.is_blocker,
        }


def classify_http_error(status_code: int, body: str = "") -> ErrorType:
    if status_code == 0:
        return ErrorType.NETWORK_TIMEOUT
    if status_code == 401:
        return ErrorType.INVALID_KEY
    if status_code == 429:
        return ErrorType.RATE_LIMITED
    if 400 <= status_code < 500:
        return ErrorType.HTTP_4XX
    if 500 <= status_code < 600:
        return ErrorType.HTTP_5XX
    return ErrorType.UNKNOWN_ERROR


def classify_content_blocker(html_lower: str) -> Optional[ErrorType]:
    # 실제 challenge 페이지 신호 (스크립트 포함에 의한 false positive 방지)
    captcha_challenge_signals = [
        "cf-challenge",  # Cloudflare challenge page body attribute
        "just a moment...",  # Cloudflare challenge title (with ellipsis)
        "enable javascript and cookies to continue",  # CF/bot challenge
        "hcaptcha.com/1/api.js",  # hCaptcha actual embed
        "__cf_chl_opt",  # Cloudflare challenge option
        # explicit user-action challenge phrases (false-positive risk is low)
        "solve the captcha",
        "complete the captcha",
        "verify you are human",
        "i'm not a robot",
        "i am not a robot",
        "press and hold to confirm",
    ]
    login_signals = [
        "sign in to continue",
        "log in to view",
        "login to read",
        "please log in to access",
        "you must be logged in",
    ]
    paywall_signals = ["subscribe to read", "subscription required", "구독 후 이용", "subscribe now to access"]

    if any(s in html_lower for s in captcha_challenge_signals):
        return ErrorType.CAPTCHA_DETECTED
    if any(s in html_lower for s in login_signals):
        return ErrorType.LOGIN_WALL_DETECTED
    if any(s in html_lower for s in paywall_signals):
        return ErrorType.PAYWALL_DETECTED
    return None


# 기법 10 (docs/09 §2): soft-block/429 텍스트 신호 단일 출처.
# playwright_probe·api_probe가 각자 다른 목록을 두지 않도록 여기로 승격한다.
RATE_LIMITED_SIGNALS: tuple[str, ...] = (
    "429 too many requests",
    "too many requests",
    "rate limit exceeded",
    "rate limited",
    "you have been rate limited",
    "temporarily blocked",
    "slow down",
    "quota exceeded",
    # GDELT는 soft limit을 200+평문으로 알린다 ("Please limit requests to one every 5 seconds")
    "limit requests",
)


def is_rate_limited_text(text: str) -> bool:
    """렌더된 HTML/평문 응답이 429/rate-limit 페이지인지 (대소문자 무시)."""
    lower = (text or "").lower()
    return any(sig in lower for sig in RATE_LIMITED_SIGNALS)

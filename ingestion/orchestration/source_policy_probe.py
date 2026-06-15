"""Phase G2-3 SourcePolicyProbe — "정책상 가능한가"를 추정하지 않고 검증한다.

robots.txt를 실제로 가져와 (User-agent별) allow/disallow를 파싱하고, 대상 path가
일반 크롤러(User-agent: *)에게 허용되는지, AI 크롤러(ClaudeBot/anthropic-ai 등)가
도메인 전체에서 차단되는지, 그리고 (선택적으로 가져온) 페이지 본문에 login/captcha/
paywall/rate-limit 마커가 있는지를 종합한다.

원칙:
- 우회 추정 금지. robots disallow가 확인된 path만 막힌 것으로 본다(전체 차단으로 단정 X).
- desktop이 막혀도 mobile/public path가 허용될 수 있으므로 path 단위로 판정한다.
- 네트워크는 주입형 fetcher로 추상화 → 단위 테스트 네트워크 0.
- 어떤 키/secret도 다루지 않는다.

stdlib만. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlsplit

# robots_get(robots_url) -> text | None ;  page_get(url) -> (status, text|None)
RobotsGet = Callable[[str], Optional[str]]
PageGet = Callable[[str], "tuple[Optional[int], Optional[str]]"]

# 도메인 전체 차단을 확인할 대표 AI 크롤러 토큰(소문자)
_AI_CRAWLER_TOKENS = (
    "claudebot", "anthropic-ai", "claude-web", "gptbot", "ccbot",
    "google-extended", "perplexitybot", "bytespider",
)


@dataclass(frozen=True)
class SourcePolicyProbeResult:
    source_id: str
    tested_url: str
    robots_checked: bool
    robots_allowed: Optional[bool]          # User-agent:* 기준 tested_url path 허용 여부
    ai_crawler_disallowed: bool             # AI 크롤러가 도메인 전체(Disallow: /)로 차단됐는가
    terms_notes: Optional[str]
    requires_login: bool
    captcha_detected: bool
    paywall_detected: bool
    rate_limit_detected: bool
    allowed_public_paths: tuple[str, ...]
    blocked_paths: tuple[str, ...]
    conclusion: str


# ── robots 파싱(표준 longest-match) ───────────────────────────────────────────
def _parse_groups(text: str) -> list[tuple[set, list]]:
    """robots.txt → [(agents:set[str], rules:list[(allow:bool, path:str)]), ...]."""
    groups: list[tuple[set, list]] = []
    agents: set[str] = set()
    rules: list[tuple[bool, str]] = []
    expect_agent = True
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, val = line.split(":", 1)
        field = field.strip().lower()
        val = val.strip()
        if field == "user-agent":
            if not expect_agent and agents:
                groups.append((agents, rules))
                agents, rules = set(), []
            agents.add(val.lower())
            expect_agent = True
        elif field in ("allow", "disallow"):
            expect_agent = False
            rules.append((field == "allow", val))
    if agents:
        groups.append((agents, rules))
    return groups


def _rules_for(groups: list[tuple[set, list]], agent: str) -> list[tuple[bool, str]]:
    """agent(정확 일치) → 규칙. 없으면 '*' 그룹. 둘 다 없으면 빈 규칙(=전체 허용)."""
    agent = agent.lower()
    star: Optional[list] = None
    for ags, rules in groups:
        if agent in ags:
            return rules
        if "*" in ags:
            star = rules if star is None else star
    return star or []


def _path_allowed(rules: list[tuple[bool, str]], path: str) -> bool:
    """longest-match: 가장 긴 규칙 path가 결정. 동률이면 Allow 우선. 규칙 없으면 허용."""
    best_len = -1
    best_allow = True
    for allow, rpath in rules:
        if rpath == "":
            # 빈 Disallow는 제약 없음(전체 허용 신호), 빈 Allow는 무의미
            continue
        if path.startswith(rpath):
            if len(rpath) > best_len or (len(rpath) == best_len and allow):
                best_len = len(rpath)
                best_allow = allow
    return best_allow


def _is_ai_blocked(groups: list[tuple[set, list]]) -> bool:
    """AI 크롤러 토큰 중 하나라도 도메인 전체(Disallow:/)로 차단되면 True."""
    for ags, rules in groups:
        if ags & set(_AI_CRAWLER_TOKENS):
            for allow, rpath in rules:
                if not allow and rpath == "/":
                    return True
    return False


# ── 페이지 마커 감지 ──────────────────────────────────────────────────────────
_LOGIN_MARKERS = ("login required", "please log in", "sign in to continue", "로그인이 필요")
_CAPTCHA_MARKERS = ("captcha", "kcaptcha", "verify you are human", "i'm not a robot")
_PAYWALL_MARKERS = ("subscribe to read", "subscription required", "paywall", "구독")
_CLOUDFLARE_MARKERS = ("just a moment", "attention required", "cf-chl", "checking your browser")
_RATE_MARKERS = ("rate limit", "too many requests", "one every", "limit requests")


def _has_any(text: str, markers) -> bool:
    low = text[:8000].lower()
    return any(m in low for m in markers)


def probe_source_policy(
    *,
    source_id: str,
    tested_url: str,
    robots_get: RobotsGet,
    page_get: Optional[PageGet] = None,
    candidate_paths: tuple[str, ...] = (),
) -> SourcePolicyProbeResult:
    """source의 robots/page 정책을 실제로 검증해 SourcePolicyProbeResult 산출.

    robots_get/page_get는 주입형(테스트 네트워크 0). candidate_paths를 주면 각 path의
    allow/disallow를 분류해 allowed_public_paths/blocked_paths를 채운다.
    """
    parts = urlsplit(tested_url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    target_path = parts.path + (("?" + parts.query) if parts.query else "")

    robots_text = None
    try:
        robots_text = robots_get(robots_url)
    except Exception:
        robots_text = None

    groups: list[tuple[set, list]] = []
    robots_checked = robots_text is not None
    if robots_text:
        groups = _parse_groups(robots_text)

    star_rules = _rules_for(groups, "*") if groups else []
    robots_allowed: Optional[bool]
    robots_allowed = _path_allowed(star_rules, target_path) if robots_checked else None
    ai_blocked = _is_ai_blocked(groups) if robots_checked else False

    allowed_paths: list[str] = []
    blocked_paths: list[str] = []
    for p in candidate_paths:
        (allowed_paths if _path_allowed(star_rules, p) else blocked_paths).append(p)

    requires_login = captcha = paywall = rate_limited = False
    if page_get is not None:
        try:
            status, body = page_get(tested_url)
        except Exception:
            status, body = None, None
        if body:
            requires_login = _has_any(body, _LOGIN_MARKERS)
            captcha = _has_any(body, _CAPTCHA_MARKERS) or _has_any(body, _CLOUDFLARE_MARKERS)
            paywall = _has_any(body, _PAYWALL_MARKERS)
            rate_limited = _has_any(body, _RATE_MARKERS)
        if status == 429:
            rate_limited = True

    terms_notes = None
    if ai_blocked:
        terms_notes = ("robots blocks AI crawlers site-wide (ClaudeBot/anthropic-ai/etc. "
                       "Disallow: /); general User-agent:* access is separate")

    if not robots_checked:
        conclusion = "no_robots"
    elif robots_allowed is False:
        conclusion = "robots_disallow_path"
    elif captcha:
        conclusion = "captcha_blocked"
    elif requires_login:
        conclusion = "login_blocked"
    elif paywall:
        conclusion = "paywall_blocked"
    elif rate_limited:
        conclusion = "rate_limited"
    else:
        conclusion = "public_allowed"

    return SourcePolicyProbeResult(
        source_id=source_id, tested_url=tested_url, robots_checked=robots_checked,
        robots_allowed=robots_allowed, ai_crawler_disallowed=ai_blocked,
        terms_notes=terms_notes, requires_login=requires_login, captcha_detected=captcha,
        paywall_detected=paywall, rate_limit_detected=rate_limited,
        allowed_public_paths=tuple(allowed_paths), blocked_paths=tuple(blocked_paths),
        conclusion=conclusion,
    )

"""소스별 live revival 판정 로직 (Phase E-2, 설계 02/03/04/05/08/09).

Phase E-1(replay audit)을 넘어, 각 소스가 **타입별로 실제 쓸 수 있는 정보 단위로 살아났는지**
판정한다. 이 모듈은 **순수·결정적 로직**만 담는다 — 네트워크 호출은 호출자(CLI runner)가
``run_collection_probe`` 경유로 수행하고, 본문 fetch는 주입형 ``fetch_fn``으로 격리한다
(단위 테스트는 네트워크 0). stdlib + 기존 자산만 사용. 신규 설치 0.

핵심 원칙(긍정편향 금지):
  - source called/artifact exists/candidate exists ≠ alive.
  - snippet_only를 body_present로 둔갑하지 않는다(body_state cascade가 분리).
  - numeric_exempt를 기사 본문 성공으로 섞지 않는다(StructuredSignalCandidate로 분리).
  - 분해 0/실패는 root cause를 원자 단위로 남긴다(unknown으로 끝내지 않는다).
  - no bypass: paywall/login/captcha/robots는 우회하지 않고 그대로 닫는다.
"""
from __future__ import annotations

import urllib.robotparser as _robotparser
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence
from urllib.parse import urlsplit

from ingestion.orchestration.article_candidate import ArticleCandidate
from ingestion.orchestration.body_state import (
    FULL_BODY_MIN,
    PARTIAL_MIN,
    _EXCERPT_MARKERS,
    assess_body_state,
)

# ── source_group → 기대 alive 타입(타입별로 "살아남"의 정의가 다르다, §1) ──
EXPECTED_ALIVE_BY_GROUP: dict[str, str] = {
    "news": "ARTICLE_BODY_ALIVE",
    "community": "COMMUNITY_SIGNAL_ALIVE",
    "search": "SEARCH_RESULT_ALIVE",
    "official": "OFFICIAL_RECORD_ALIVE",
    "trend": "STRUCTURED_SIGNAL_ALIVE",
    "market": "STRUCTURED_SIGNAL_ALIVE",
    "domain": "OFFICIAL_RECORD_ALIVE",
}

# group별 strategy ladder(보고/본문 fetch 결정 입력). 실제 1차 수집은 run_collection_probe.
_LADDER_ARTICLE = (
    "collection_probe", "artifact_parser_rss_atom", "content_encoded_or_atom_content",
    "canonical_url_from_item", "policy_safe_body_fetch", "html_extraction",
    "body_state_assessment",
)
_LADDER_OFFICIAL = (
    "collection_probe", "json_adapter", "nested_container_parser",
    "record_id_title_date_url_mapping", "structured_record_check", "eventqueue_record_check",
)
_LADDER_STRUCTURED = (
    "collection_probe", "numeric_payload_adapter", "timestamp_value_metric_extraction",
    "structured_signal_candidate", "numeric_exempt_body_state", "eventqueue_signal_check",
)
_LADDER_COMMUNITY = (
    "approved_api_or_feed_only", "post_thread_metadata_extraction",
    "unconfirmed_policy_preservation", "eventqueue_community_signal_check",
)
_LADDER_SEARCH = (
    "collection_probe", "search_result_parser", "result_url_evidence_mapping",
    "eventqueue_search_result_check",
)
STRATEGY_LADDER_BY_GROUP: dict[str, tuple[str, ...]] = {
    "news": _LADDER_ARTICLE,
    "community": _LADDER_COMMUNITY,
    "search": _LADDER_SEARCH,
    "official": _LADDER_OFFICIAL,
    "trend": _LADDER_STRUCTURED,
    "market": _LADDER_STRUCTURED,
    "domain": _LADDER_OFFICIAL,
}

# 사용자가 의도적으로 막은 사유 → root cause(우회 금지 대상).
_POLICY_BLOCK_ROOT_CAUSE: dict[str, str] = {
    "login_wall_no_bypass": "LOGIN_BLOCKED",
    "paywall_no_bypass": "PAYWALL_BLOCKED",
    "robots_or_policy_block": "ROBOTS_BLOCKED",
    "captcha_no_bypass": "CAPTCHA_BLOCKED",
    "disabled_by_policy": "POLICY_EXCLUDED_BY_USER",
    "user_excluded": "POLICY_EXCLUDED_BY_USER",
}

# parser_gap_reason → root cause(0분해 원인을 원자 단위로).
_GAP_ROOT_CAUSE: dict[str, str] = {
    "schema_unknown": "SCHEMA_UNKNOWN",
    "html_not_decomposed": "HTML_UNSUPPORTED",
    "empty_feed": "EMPTY_PAYLOAD",
    "empty_artifact": "EMPTY_PAYLOAD",
    "api_error_or_key_missing": "EXTERNAL_API_ERROR",
    "malformed_artifact": "EXTERNAL_API_ERROR",
    "list_without_dict_items": "SCHEMA_UNKNOWN",
    "no_candidates": "SOURCE_SPECIFIC_ADAPTER_MISSING",
    "no_artifact": "EMPTY_PAYLOAD",
    "parser_exception": "EXTERNAL_API_ERROR",
}

_NEWS_LIKE_GROUPS = frozenset({"news"})
_STRUCTURED_GROUPS = frozenset({"market", "trend"})
_RECORD_GROUPS = frozenset({"official", "domain"})

# 실제 정보 단위로 살아난(데이터를 산출한) 상태 — 정책 차단/제외와 구분.
DATA_ALIVE_STATUSES = frozenset({
    "ARTICLE_BODY_ALIVE", "ARTICLE_PARTIAL_ALIVE", "OFFICIAL_RECORD_ALIVE",
    "STRUCTURED_SIGNAL_ALIVE", "COMMUNITY_SIGNAL_ALIVE", "SEARCH_RESULT_ALIVE",
})
# E-3: NEEDS_*가 아닌 **clean하게 닫힌** terminal 상태(우회 없음/외부/도구/계약/서비스가치).
# 이들은 COMPLETE를 막지 않는다(§10·§21: NEEDS_*만 unresolved).
TERMINAL_BLOCKED_STATUSES = frozenset({
    "POLICY_BLOCKED_NO_BYPASS", "PAYWALL_BLOCKED_NO_BYPASS",
    "LOGIN_BLOCKED_NO_BYPASS", "CAPTCHA_BLOCKED_NO_BYPASS",
    "ROBOTS_BLOCKED_NO_BYPASS", "EXCLUDED_BY_USER",
    "EXTERNAL_RATE_LIMITED_WITH_RETRY_POLICY", "EXTERNAL_API_ERROR_WITH_EVIDENCE",
    "TOOL_UNAVAILABLE_FOR_REQUIRED_STRATEGY", "NOT_SERVICE_USEFUL",
    "DISABLE_RECOMMENDED", "REQUIRES_VENDOR_SPECIFIC_API_CONTRACT",
    "REQUIRES_TWO_STEP_DETAIL_FETCH", "BLOCKED_ENV_KEY",
})
# COMPLETE 판정에서 alive로 인정되는 final_status(§17): data-alive + clean terminal.
ALIVE_STATUSES = DATA_ALIVE_STATUSES | TERMINAL_BLOCKED_STATUSES | frozenset({
    # E-2 호환: 구 EXTERNAL_RATE_LIMITED 표기도 alive(차단)로 인정.
    "EXTERNAL_RATE_LIMITED",
})
# COMPLETE를 막는 미해결 상태(§10: NEEDS_*만. E-3 killer는 0으로 만든다).
UNRESOLVED_STATUSES = frozenset({
    "NEEDS_BODY_FETCH_UNRESOLVED", "NEEDS_PARSER_UNRESOLVED",
    "EXTERNAL_API_ERROR", "UNKNOWN",
})

# E-3: 어댑터로 살릴 수 없는(잘못된 endpoint/계약/서비스가치) source의 terminal 확정.
# 각 항목: (final_status, root_causes, next_action). live 재검증 후에도 NEEDS_*면 적용.
_SOURCE_RESOLUTION_OVERRIDE: dict[str, tuple[str, tuple[str, ...], str]] = {
    "kma": ("EXTERNAL_API_ERROR_WITH_EVIDENCE", ("API_RESULT_CODE_10_RANGE",),
            "fix_base_date_base_time_nx_ny_params_then_retest"),
    "eia": ("REQUIRES_VENDOR_SPECIFIC_API_CONTRACT", ("ROUTE_CATALOG_NOT_DATA",),
            "call_v2_specific_route_data_with_facets_and_key"),
    "bok_ecos": ("REQUIRES_VENDOR_SPECIFIC_API_CONTRACT", ("CATALOG_ENDPOINT_NOT_SERIES",),
                 "call_StatisticSearch_with_statcode_and_period"),
    "its": ("NOT_SERVICE_USEFUL", ("PER_LINK_TRAFFIC_TELEMETRY_NOT_EVENTS",),
            "disable_recommended_or_reduce_to_national_congestion_index"),
}

# NEEDS_* (E-3 killer가 terminal로 변환해야 하는 raw 미해결).
_NEEDS_STATUSES = frozenset({"NEEDS_BODY_FETCH_UNRESOLVED", "NEEDS_PARSER_UNRESOLVED"})


@dataclass(frozen=True)
class SourceRevivalPlan:
    source_id: str
    source_group: str
    purpose: str
    enabled: bool
    excluded: bool
    excluded_reason: Optional[str]
    requires_api_key: bool
    api_key_ready: bool
    strategy_ladder: tuple[str, ...]
    expected_alive_type: str
    max_attempts: int


@dataclass(frozen=True)
class StrategyAttemptRecord:
    source_id: str
    strategy_name: str
    attempt_index: int
    attempted: bool
    status: str  # SUCCESS|PARTIAL|NO_CANDIDATES|NO_BODY|STRUCTURED_ONLY|RATE_LIMITED|...
    items_found: Optional[int]
    items_extracted: Optional[int]
    artifact_path: Optional[str]
    candidate_count: int
    body_present_count: int
    structured_signal_count: int
    eventqueue_ready_count: int
    error_type: Optional[str]
    root_cause: Optional[str]
    next_strategy: Optional[str]


@dataclass(frozen=True)
class BodyFetchResult:
    source_id: str
    candidate_url: Optional[str]
    attempted: bool
    status: str  # SUCCESS|NO_BODY|EXCERPT_ONLY|FETCH_ERROR|HTTP_ERROR|ROBOTS_BLOCKED|SKIPPED_NO_URL
    http_status: Optional[int]
    extractor_used: Optional[str]
    body_text: Optional[str]   # internal_only — 직렬화 시 길이/상태만 노출
    body_length: int
    body_state: str
    boilerplate_risk: Optional[str]
    excerpt_marker_detected: bool
    error_type: Optional[str]


@dataclass(frozen=True)
class StructuredSignalCandidate:
    source_id: str
    signal_type: str
    title: Optional[str]
    metric_name: Optional[str]
    metric_value: Optional[object]
    observed_at: Optional[str]
    source_url: Optional[str]
    canonical_url: Optional[str]
    evidence_ref: Optional[str]
    raw_record_ref: Optional[str]
    quality_status: str


@dataclass(frozen=True)
class SourceRevivalResult:
    source_id: str
    source_group: str
    expected_alive_type: str
    final_status: str
    root_causes: tuple[str, ...]
    next_action: str
    fix_applied: Optional[str] = None
    attempts: tuple[StrategyAttemptRecord, ...] = field(default_factory=tuple)


# ── plan ───────────────────────────────────────────────────────────────────
def build_revival_plan(
    *,
    source_id: str,
    source_group: Optional[str],
    purpose: Optional[str],
    enabled: bool,
    requires_api_key: bool,
    api_key_ready: bool,
    excluded: bool,
    excluded_reason: Optional[str],
    max_attempts: int = 4,
) -> SourceRevivalPlan:
    grp = source_group or "news"
    ladder = STRATEGY_LADDER_BY_GROUP.get(grp, _LADDER_ARTICLE)
    expected = "EXCLUDED_BY_USER" if excluded else EXPECTED_ALIVE_BY_GROUP.get(grp, "ARTICLE_BODY_ALIVE")
    return SourceRevivalPlan(
        source_id=source_id, source_group=grp, purpose=purpose or "news",
        enabled=enabled, excluded=excluded, excluded_reason=excluded_reason,
        requires_api_key=requires_api_key, api_key_ready=api_key_ready,
        strategy_ladder=ladder, expected_alive_type=expected, max_attempts=max_attempts,
    )


# ── policy-safe body fetch ───────────────────────────────────────────────────
# fetch_fn(url) -> (http_status|None, html|None, error_type|None)
FetchFn = Callable[[str], "tuple[Optional[int], Optional[str], Optional[str]]"]
# extract_fn(html, url) -> (body_text|None, extractor_name)
ExtractFn = Callable[[str, str], "tuple[Optional[str], str]"]
# robots_fn(url) -> bool (True=allowed). 기본은 urllib.robotparser.
RobotsFn = Callable[[str], bool]

_BOILERPLATE_MARKERS = (
    "subscribe", "sign in", "log in", "create an account", "cookie",
    "accept all", "newsletter", "advertisement",
)


def _default_robots_allows(url: str, user_agent: str = "*") -> bool:
    """robots.txt 준수 체크(stdlib). 가져올 수 없으면 보수적으로 허용하되 호출자가 기록.

    disallow가 명시되면 False(우회 금지). 네트워크 예외 시 True(대부분 기사 경로는 허용)
    이지만, 호출자는 robots_unknown을 trace에 남긴다.
    """
    try:
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            return False
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        rp = _robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True


def _detect_boilerplate(body: str) -> str:
    low = body.lower()
    hits = sum(1 for m in _BOILERPLATE_MARKERS if m in low)
    if hits >= 3:
        return "high"
    if hits >= 1:
        return "medium"
    return "low"


def fetch_article_body(
    url: Optional[str],
    *,
    source_id: str,
    fetch_fn: Optional[FetchFn] = None,
    extract_fn: Optional[ExtractFn] = None,
    robots_fn: Optional[RobotsFn] = None,
    full_threshold: int = FULL_BODY_MIN,
) -> BodyFetchResult:
    """canonical/source url에서 policy-safe 본문 fetch+추출. 길이만으로 present 판정하지 않는다.

    no bypass: paywall/login/captcha는 우회하지 않는다(추출 실패 시 그대로 닫음).
    robots disallow면 fetch하지 않고 ROBOTS_BLOCKED. 예외를 던지지 않는다.
    """
    if not url:
        return BodyFetchResult(
            source_id=source_id, candidate_url=None, attempted=False,
            status="SKIPPED_NO_URL", http_status=None, extractor_used=None,
            body_text=None, body_length=0, body_state="missing",
            boilerplate_risk=None, excerpt_marker_detected=False,
            error_type="no_url",
        )
    robots = robots_fn or _default_robots_allows
    if not robots(url):
        return BodyFetchResult(
            source_id=source_id, candidate_url=url, attempted=False,
            status="ROBOTS_BLOCKED", http_status=None, extractor_used=None,
            body_text=None, body_length=0, body_state="missing",
            boilerplate_risk=None, excerpt_marker_detected=False,
            error_type="robots_disallow",
        )
    fetch = fetch_fn or _default_fetch_fn
    extract = extract_fn or _default_extract_fn
    try:
        http_status, html, ferr = fetch(url)
    except Exception as exc:  # 네트워크 예외 격리
        return _fetch_error(source_id, url, "FETCH_ERROR", type(exc).__name__)
    if ferr or not html:
        status = "HTTP_ERROR" if (http_status and http_status >= 400) else "FETCH_ERROR"
        return _fetch_error(source_id, url, status, ferr or "no_html", http_status)
    try:
        body, extractor = extract(html, url)
    except Exception as exc:
        return _fetch_error(source_id, url, "FETCH_ERROR", type(exc).__name__, http_status)

    body = (body or "").strip()
    blen = len(body)
    excerpt = bool(body) and any(m in body[-200:].lower() for m in _EXCERPT_MARKERS)
    boiler = _detect_boilerplate(body) if body else None
    state = assess_body_state(body_text=body, full_threshold=full_threshold)
    if not body:
        status = "NO_BODY"
    elif state.extraction_status == "snippet_only":
        status = "EXCERPT_ONLY"
    else:
        status = "SUCCESS"
    return BodyFetchResult(
        source_id=source_id, candidate_url=url, attempted=True, status=status,
        http_status=http_status, extractor_used=extractor, body_text=body,
        body_length=blen, body_state=state.extraction_status,
        boilerplate_risk=boiler, excerpt_marker_detected=excerpt,
        error_type=None,
    )


def _fetch_error(source_id, url, status, error_type, http_status=None) -> BodyFetchResult:
    return BodyFetchResult(
        source_id=source_id, candidate_url=url, attempted=True, status=status,
        http_status=http_status, extractor_used=None, body_text=None, body_length=0,
        body_state="missing", boilerplate_risk=None, excerpt_marker_detected=False,
        error_type=error_type,
    )


def _default_fetch_fn(url: str) -> "tuple[Optional[int], Optional[str], Optional[str]]":
    """기존 html_fetch_tool(httpx) 재사용. 신규 설치 0. 우회 전략 없음(httpx GET + timeout)."""
    from ingestion.tools.html_fetch_tool import fetch_html
    r = fetch_html(url, strategy="httpx_direct", timeout=15.0)
    if not r.success:
        return r.status_code or None, None, r.error_message or "fetch_failed"
    return r.status_code or None, r.html or None, None


def _default_extract_fn(html: str, url: str) -> "tuple[Optional[str], str]":
    """trafilatura → readability 순서로 본문 추출(기존 자산). 둘 다 실패면 None."""
    try:
        from ingestion.tools.trafilatura_extractor import extract_with_trafilatura
        res = extract_with_trafilatura(html, url)
        if res.success and res.body and len(res.body.strip()) >= PARTIAL_MIN:
            return res.body, "trafilatura"
    except Exception:
        pass
    try:
        from ingestion.tools.readability_extractor import extract_with_readability
        res = extract_with_readability(html, url)
        if res.success and res.body:
            return res.body, "readability"
    except Exception:
        pass
    return None, "none"


# ── structured signal 분리 ───────────────────────────────────────────────────
def to_structured_signal_candidates(
    candidates: Sequence[ArticleCandidate],
    *,
    source_id: str,
    source_group: Optional[str],
    purpose: Optional[str],
    quality_status: str = "structured_signal",
) -> list[StructuredSignalCandidate]:
    """numeric_exempt candidate를 StructuredSignalCandidate로 분리(article과 섞지 않는다).

    metric_name/value를 일반적으로 단정할 수 없으면 None으로 둔다(없는 값을 만들지 않는다).
    """
    signal_type = purpose or source_group or "signal"
    out: list[StructuredSignalCandidate] = []
    for c in candidates:
        if not c.numeric_payload_exempt:
            continue
        out.append(StructuredSignalCandidate(
            source_id=source_id, signal_type=signal_type, title=c.title,
            metric_name=None, metric_value=None, observed_at=c.published_at,
            source_url=c.source_url, canonical_url=c.canonical_url,
            evidence_ref=c.raw_artifact_path, raw_record_ref=c.extracted_text_ref,
            quality_status=quality_status,
        ))
    return out


# ── EventQueue readiness ─────────────────────────────────────────────────────
_VALID_RECORD_TYPES = frozenset({
    "article_candidate", "official_record", "structured_signal",
    "community_signal", "search_result",
})


def build_eventqueue_record(
    *,
    record_type: str,
    source_id: str,
    title_or_label: Optional[str],
    source_url_or_evidence: Optional[str],
    canonical_url: Optional[str],
    published_at_or_observed_at: Optional[str],
    body_state_or_signal: Optional[str],
    confirmation_policy: Optional[str],
    quality_pre_gate_decision: Optional[str],
) -> dict:
    """audit용 EventQueue record(별도 큐 path). 기본 큐는 건드리지 않는다."""
    return {
        "record_type": record_type,
        "source_id": source_id,
        "title_or_label": title_or_label,
        "source_url_or_evidence": source_url_or_evidence,
        "canonical_url": canonical_url,
        "published_at_or_observed_at": published_at_or_observed_at,
        "body_state_or_signal": body_state_or_signal,
        "confirmation_policy": confirmation_policy,
        "quality_pre_gate_decision": quality_pre_gate_decision,
    }


def check_eventqueue_readiness(record: dict) -> tuple[bool, tuple[str, ...]]:
    """record가 EventQueue 적재 가능한 최소 스키마를 만족하는지. (ready, schema_gaps)."""
    gaps: list[str] = []
    rt = record.get("record_type")
    if rt not in _VALID_RECORD_TYPES:
        gaps.append("invalid_record_type")
    if not record.get("source_id"):
        gaps.append("no_source_id")
    if not record.get("title_or_label"):
        gaps.append("no_title_or_label")
    if not record.get("source_url_or_evidence"):
        gaps.append("no_evidence_ref")
    # 시간은 official record의 경우 date_absent 허용(§1.3) — 경고만, ready를 막지 않는다.
    return (not gaps, tuple(gaps))


# ── final status + root cause ────────────────────────────────────────────────
@dataclass(frozen=True)
class RevivalEvidence:
    """classify 입력 — audit + body fetch 후 갱신된 본문/신호 카운트."""
    candidate_count: int = 0
    title_present: int = 0
    url_present: int = 0
    published_present: int = 0
    body_present: int = 0
    body_partial: int = 0
    snippet_only: int = 0
    body_missing: int = 0
    structured_signal: int = 0
    parser_name: Optional[str] = None
    parser_gap_reason: Optional[str] = None
    body_fetch_attempted: bool = False
    body_fetch_excerpt: bool = False


def classify_final_status(
    *,
    source_group: Optional[str],
    excluded: bool,
    excluded_reason: Optional[str],
    api_readiness_status: str,
    probe_status: str,
    artifact_exists: bool,
    evidence: RevivalEvidence,
) -> tuple[str, tuple[str, ...], str]:
    """(final_status, root_causes, next_action). root cause 없이 닫지 않는다(§15·§16)."""
    grp = source_group or "news"

    # 1) 사용자 의도적 제외 / 정책 차단(우회 금지)
    if excluded:
        rc = _POLICY_BLOCK_ROOT_CAUSE.get(excluded_reason or "", "POLICY_EXCLUDED_BY_USER")
        if rc == "POLICY_EXCLUDED_BY_USER":
            return "EXCLUDED_BY_USER", (rc,), "keep_excluded_by_user"
        return "POLICY_BLOCKED_NO_BYPASS", (rc,), "no_bypass_keep_blocked"

    # 2) 키 부재(no bypass) — alias로 동작하면 missing이 아니므로 통과
    if api_readiness_status == "missing":
        return "BLOCKED_ENV_KEY", ("KEY_MISSING",), "provide_api_key_then_retest"

    # 3) probe 단계 외부 결과
    if probe_status == "RATE_LIMITED":
        return "EXTERNAL_RATE_LIMITED", ("RATE_LIMITED",), "retry_after_cooldown"
    if probe_status == "BLOCKED":
        return "POLICY_BLOCKED_NO_BYPASS", ("ROBOTS_BLOCKED",), "no_bypass_keep_blocked"
    if not artifact_exists or probe_status in ("NETWORK_ERROR", "UNKNOWN", "DEFERRED"):
        rc = "EXTERNAL_API_ERROR" if probe_status in ("NETWORK_ERROR", "UNKNOWN") else "EMPTY_PAYLOAD"
        if probe_status == "DEFERRED":
            return "NEEDS_PARSER_UNRESOLVED", ("TWO_STEP_FETCH_REQUIRED",), "implement_two_step_fetch"
        return "EXTERNAL_API_ERROR", (rc,), "investigate_external"

    # 4) artifact는 있으나 에러 봉투
    if evidence.parser_name == "api_error_payload":
        return "EXTERNAL_API_ERROR", ("EXTERNAL_API_ERROR",), "fix_request_params_or_key"

    # 5) 0분해
    if evidence.candidate_count == 0:
        rc = _GAP_ROOT_CAUSE.get(evidence.parser_gap_reason or "", "SOURCE_SPECIFIC_ADAPTER_MISSING")
        if rc == "HTML_UNSUPPORTED":
            return "NEEDS_PARSER_UNRESOLVED", (rc,), "implement_html_extraction"
        return "NEEDS_PARSER_UNRESOLVED", (rc,), "implement_source_adapter"

    # 6) group별 alive 판정
    if grp in _STRUCTURED_GROUPS:
        if evidence.structured_signal > 0:
            return "STRUCTURED_SIGNAL_ALIVE", (), "ready_as_structured_signal"
        return "NEEDS_PARSER_UNRESOLVED", ("STRUCTURED_SIGNAL_NOT_ARTICLE",), "implement_numeric_adapter"

    if grp in _RECORD_GROUPS:
        # official/domain: 기사 본문 없어도 stable record면 alive(§1.3). 단 dedup/시간 랭킹이
        # 가능하려면 **안정 URL 또는 시간 중 최소 1개 anchor**가 필요하다(F1 루프홀 차단):
        # title만 있고 url·시간이 모두 없는 record는 실시간 인텔리전스에서 쓸 수 없다.
        if evidence.title_present == 0 and evidence.url_present == 0:
            return "NEEDS_PARSER_UNRESOLVED", ("NO_TITLE_OR_LABEL",), "map_record_fields"
        if evidence.url_present == 0 and evidence.published_present == 0:
            # anchor 둘 다 부재 → alive 자격 미달(NEEDS_PARSER로 정직하게 닫음)
            return ("NEEDS_PARSER_UNRESOLVED", ("NO_STABLE_URL", "NO_TIMESTAMP"),
                    "map_record_anchor_url_or_date")
        causes: list[str] = []
        if evidence.published_present == 0:
            causes.append("NO_TIMESTAMP")   # degraded: 시간 결손(URL anchor 보유)
        if evidence.url_present == 0:
            causes.append("NO_STABLE_URL")  # degraded: URL 결손(시간 anchor 보유)
        return "OFFICIAL_RECORD_ALIVE", tuple(causes), "ready_as_official_record"

    if grp == "community":
        # community는 unconfirmed signal — url 또는 시간 anchor가 있으면 alive(필요시 degraded).
        if evidence.url_present > 0 or evidence.published_present > 0:
            causes = []
            if evidence.url_present == 0:
                causes.append("NO_STABLE_URL")
            return "COMMUNITY_SIGNAL_ALIVE", tuple(causes), "ready_as_unconfirmed_signal"
        if evidence.title_present > 0:
            # title만(url·시간 anchor 부재) → dedup 약함 → degraded community signal로 정직 표기.
            return ("COMMUNITY_SIGNAL_ALIVE", ("NO_STABLE_URL", "NO_TIMESTAMP"),
                    "expand_query_for_url_and_date")
        return "NEEDS_PARSER_UNRESOLVED", ("NO_TITLE_OR_LABEL",), "map_post_fields"

    if grp == "search":
        if evidence.url_present > 0:
            return "SEARCH_RESULT_ALIVE", (), "ready_as_search_result"
        return "NEEDS_PARSER_UNRESOLVED", ("NO_EVIDENCE_REF",), "map_search_result_fields"

    # 7) news/article — 본문이 핵심
    if evidence.body_present > 0:
        return "ARTICLE_BODY_ALIVE", (), "ready_as_article"
    if evidence.body_partial > 0:
        return "ARTICLE_PARTIAL_ALIVE", (), "improve_extraction_optional"
    if evidence.snippet_only > 0:
        if evidence.body_fetch_attempted:
            rc = "EXCERPT_ONLY" if evidence.body_fetch_excerpt else "BODY_FETCH_FAILED"
            return "NEEDS_BODY_FETCH_UNRESOLVED", (rc,), "tune_body_fetch_or_extractor"
        return "NEEDS_BODY_FETCH_UNRESOLVED", ("BODY_FETCH_REQUIRED",), "fetch_full_body_from_canonical"
    if evidence.title_present > 0 or evidence.url_present > 0:
        return "NEEDS_BODY_FETCH_UNRESOLVED", ("BODY_FETCH_REQUIRED",), "fetch_full_body_from_canonical"
    return "NEEDS_PARSER_UNRESOLVED", ("SCHEMA_UNKNOWN",), "implement_source_adapter"


# ── E-3: unresolved → terminal finalization ──────────────────────────────────
def finalize_unresolved_status(
    *,
    source_id: str,
    source_group: Optional[str],
    final_status: str,
    root_causes: tuple[str, ...],
    next_action: str,
    ladder_result=None,
    browser_available: bool = True,
) -> tuple[str, tuple[str, ...], str, str]:
    """NEEDS_*를 clean terminal로 확정한다(§10·§21: killer 턴 이후 NEEDS_* 금지).

    반환: (final_status, root_causes, next_action, resolution_class).
    no bypass: paywall/login/captcha 마커는 우회하지 않고 *_BLOCKED_NO_BYPASS로 닫는다.
    """
    if final_status not in _NEEDS_STATUSES:
        # 이미 alive 또는 이미 terminal — 그대로 둔다.
        cls = ("data_alive" if final_status in DATA_ALIVE_STATUSES
               else "terminal" if final_status in TERMINAL_BLOCKED_STATUSES
               else "external")
        return final_status, root_causes, next_action, cls

    # 1) source별 명시 resolution override(잘못된 endpoint/계약/서비스가치)
    if source_id in _SOURCE_RESOLUTION_OVERRIDE:
        fs, rc, na = _SOURCE_RESOLUTION_OVERRIDE[source_id]
        return fs, rc, na, "source_override"

    # 2) body fetch ladder 결과 기반(뉴스/HTML)
    if ladder_result is not None:
        lr = ladder_result
        st = getattr(lr, "status", None)
        if st in ("SUCCESS",):
            return "ARTICLE_BODY_ALIVE", (), "ready_as_article", "data_alive"
        if st in ("PARTIAL",):
            return "ARTICLE_PARTIAL_ALIVE", (), "improve_extraction_optional", "data_alive"
        if getattr(lr, "captcha_marker", False):
            return ("CAPTCHA_BLOCKED_NO_BYPASS", ("CAPTCHA_DETECTED",),
                    "no_bypass_keep_blocked", "captcha")
        if getattr(lr, "login_marker", False):
            return ("LOGIN_BLOCKED_NO_BYPASS", ("LOGIN_WALL_DETECTED",),
                    "no_bypass_keep_blocked", "login")
        if getattr(lr, "paywall_marker", False):
            return ("PAYWALL_BLOCKED_NO_BYPASS", ("PAYWALL_DETECTED",),
                    "no_bypass_keep_blocked", "paywall")
        if st == "ROBOTS_BLOCKED":
            return ("ROBOTS_BLOCKED_NO_BYPASS", ("ROBOTS_DISALLOW",),
                    "no_bypass_keep_blocked", "robots")
        http = getattr(lr, "http_status", None)
        if http == 429:
            return ("EXTERNAL_RATE_LIMITED_WITH_RETRY_POLICY", ("HTTP_429",),
                    "retry_after_cooldown", "external_rate_limited")
        if http in (401, 403):
            return ("EXTERNAL_API_ERROR_WITH_EVIDENCE", (f"HTTP_{http}_ANTI_BOT",),
                    "investigate_access_or_official_api", "external_api_error")
        if getattr(lr, "tool_unavailable", False):
            return ("TOOL_UNAVAILABLE_FOR_REQUIRED_STRATEGY", ("BROWSER_RENDER_UNAVAILABLE",),
                    "install_or_configure_browser_then_retest", "tool_unavailable")
        # fetch는 됐으나 본문 추출 실패/발췌만(마커 없음) → 증거 기반 외부 에러로 닫음
        cause = "EXCERPT_ONLY_NO_FULL_BODY" if st == "EXCERPT_ONLY" else "NO_EXTRACTABLE_BODY"
        return ("EXTERNAL_API_ERROR_WITH_EVIDENCE", (cause,),
                "switch_to_official_feed_or_api", "external_api_error")

    # 3) ladder 없는 NEEDS_PARSER 잔여(어댑터 미커버 + override 미지정) → 계약 필요로 닫음
    return ("REQUIRES_VENDOR_SPECIFIC_API_CONTRACT", root_causes or ("SCHEMA_UNKNOWN",),
            "implement_source_adapter_or_vendor_contract", "needs_contract")


# ── summary ──────────────────────────────────────────────────────────────────
def summarize_revival(results: Sequence[SourceRevivalResult]) -> dict:
    """final_status/root_cause/group 분포 요약(보고용). 숫자를 쪼개서 정직하게."""
    status_dist: dict[str, int] = {}
    root_cause_dist: dict[str, int] = {}
    alive = unresolved = blocked = 0
    fully_alive = degraded_alive = 0
    degraded_sources: list[str] = []
    unresolved_sources: list[str] = []
    for r in results:
        status_dist[r.final_status] = status_dist.get(r.final_status, 0) + 1
        for rc in r.root_causes:
            root_cause_dist[rc] = root_cause_dist.get(rc, 0) + 1
        if r.final_status in ALIVE_STATUSES:
            alive += 1
        elif r.final_status in UNRESOLVED_STATUSES:
            unresolved += 1
            unresolved_sources.append(r.source_id)
        # data-alive를 fully(결손 없음) vs degraded(NO_TIMESTAMP/NO_STABLE_URL 등 보유)로
        # 분리한다(F3: alive 과대평가 방지 — 정책 차단/제외는 data-alive 아님).
        if r.final_status in DATA_ALIVE_STATUSES:
            if r.root_causes:
                degraded_alive += 1
                degraded_sources.append(r.source_id)
            else:
                fully_alive += 1
        if r.final_status in ("POLICY_BLOCKED_NO_BYPASS", "EXCLUDED_BY_USER", "BLOCKED_ENV_KEY"):
            blocked += 1
    return {
        "total": len(results),
        "alive": alive,
        "data_alive": fully_alive + degraded_alive,
        "fully_alive": fully_alive,
        "degraded_alive": degraded_alive,
        "degraded_sources": degraded_sources,
        "unresolved": unresolved,
        "blocked_or_excluded": blocked,
        "final_status_distribution": status_dist,
        "root_cause_distribution": root_cause_dist,
        "unresolved_sources": unresolved_sources,
        "complete_eligible": unresolved == 0,
    }

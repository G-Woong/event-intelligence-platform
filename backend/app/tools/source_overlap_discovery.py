"""ADR#57 — source overlap discovery (write-free·결정론·no-merge·no-DB).

RealSourceLoop(R-RealSourceLoopUnproven)의 다음 hard blocker: artificial replay 로 입증된
cross-batch adjudication substrate 를 **실 source behavior** 에서 재현할 수 있는가. 재현이 안 되면
어떤 source/data/fingerprint/coverage 조건이 부족한지 **수치로 분해**한다.

핵심 통찰(왜 단순 "더 많이 fetch"가 답이 아닌가):
  - 결정론 cross-batch identity 는 **fingerprint 정확 token-set 일치 + 같은 date bucket** 만 인정한다
    (`cross_source_dedup.semantic_identity_fingerprint`; 고정밀·저재현·false-merge 0).
  - 실제 다른 매체의 같은 사건 헤드라인은 paraphrase 되어 token-set 이 정확히 일치하기 어렵다 →
    overlap 이 **존재해도** deterministic fingerprint 의 사각지대일 수 있다.
  - 따라서 이 도구는 overlap 을 두 입도로 분해한다:
      ① `fingerprint_overlap`            = 정확 token-set 일치 → deterministic 이 `semantic_cross_batch_candidate`
                                           로 잡는다(같은 사건·다른 URL·교차배치 시).
      ② `near_match_below_fingerprint`   = title token Jaccard≥near 이나 fingerprint 불일치 → **deterministic
                                           사각지대**. 미래 semantic adjudicator(embedding/LLM/KG) 영역이며
                                           MERGE_GATE·gold 미충족이면 병합 금지(이번 턴 LLM 호출 0).

경계(불변):
  - **write-free·no-DB**: 이 모듈은 DB 에 쓰지 않는다(overlap 신호 측정만). live-db 검증은 escalation 정책에
    따라 `real_source_identity_smoke` 가 safe-target gated 로 수행한다.
  - **no-merge**: near-match 든 fingerprint 일치든 **병합하지 않는다**(no_auto_merge=True 불변). overlap pair 는
    candidate hint / report signal 일 뿐이다.
  - **본문 미저장**: title 헤드라인·canonical·published_at·source_id 만(전문/raw_payload/PII 미반영·옵션 C 계약).
  - **source role guard**: merge anchor 후보는 publishable core(official/article)만. community/market/catalog 는
    reaction/signal/enrichment 레이어로 분리(anchor 아님).
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from typing import Any, Callable, Optional

from backend.app.services.event_ingest_pipeline import _RECORD_TYPE_TO_SOURCE_TYPE
from ingestion.orchestration.cross_source_dedup import (
    _MIN_SEMANTIC_TOKENS,
    _TITLE_JACCARD_THRESHOLD,
    _date_bucket,
    _jaccard,
    _title_tokens,
    semantic_identity_fingerprint,
)

# merge anchor 자격(event_ingest_pipeline._IDENTITY_ANCHOR_SOURCE_TYPES 와 정합) — publishable core 만.
_PUBLISHABLE_SOURCE_TYPES = frozenset({"official", "article"})
# near-match 임계: fingerprint 정확일치(token-set 동치)보다 느슨하나 within-batch 약신호 결합(0.8)보다도
# 낮춰 "overlap 은 있으나 fingerprint 사각지대"인 adjudicator-zone 까지 본다(병합 아님·신호 측정만).
DEFAULT_NEAR_JACCARD = 0.5
# hard-negative band(ADR#59): publishable·same-date·cross-URL 이나 near 미만 token overlap — "헷갈릴 만하나 다른
# 사건"(different-event lean) 후보. reviewer/gold 음성 floor·calibration 용(라벨은 reviewer 가·단정 아님·near 미만만).
_HARD_NEG_FLOOR = 0.2

# GDELT DOC ArtList — key-free·다출처 집계(같은 사건이 다른 outlet·다른 URL 로 등장 → 실 cross-source overlap 생성원).
_GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_DEFAULT_MAX_RECORDS = 25      # bounded(폭주·rate-limit 차단).
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# ADR#58/B: key-free RSS 다출처 함대(이미 source_registry 등재·ingestion 수집 중·auth=none). GDELT 429 의존도를 낮추는
# 실 cross-source overlap 생성원 — 다른 매체가 같은 사건을 paraphrase 헤드라인으로 보도 → near_match_below_fingerprint.
# 같은 보도권(영문 world news)일수록 같은 사건 재보도 가능성↑. endpoint 는 registry(_SERVICE_CONFIGS)에서 읽는다(하드코딩 0).
_RSS_OVERLAP_SOURCES: tuple[str, ...] = ("bbc", "aljazeera", "the_verge", "techcrunch")
_RSS_HOST_MIN_SPACING_SECONDS = 5   # RSS 호스트 보수적 floor(shared host_rate_gate.json 참여·no-bypass).


def _rec(**kw: Any) -> dict:
    base = {
        "record_type": "article_candidate", "source_id": "unknown",
        "title_or_label": None, "source_url_or_evidence": None, "canonical_url": None,
        "published_at_or_observed_at": None, "body_state_or_signal": "missing",
    }
    base.update(kw)
    return base


def _role(rec: dict) -> str:
    return _RECORD_TYPE_TO_SOURCE_TYPE.get(rec.get("record_type"), "unknown")


def _publishable(rec: dict) -> bool:
    return _role(rec) in _PUBLISHABLE_SOURCE_TYPES


def _fingerprint(rec: dict) -> Optional[str]:
    return semantic_identity_fingerprint(
        rec.get("title_or_label"), rec.get("published_at_or_observed_at"))


# ── captured 합성 fixture(옵션 C: sanitized capture·본문 미저장·실 source behavior 아님) ────────────
def build_captured_overlap_fixture() -> list[dict]:
    """**captured/합성** GDELT 형태 fixture — 실 다출처 overlap 의 두 입도를 결정론으로 재현(network 0).

    같은 사건("port strike"):
      - outlet 2개가 **wire 헤드라인 verbatim** 재게재(같은 token-set·다른 URL) → fingerprint_overlap(deterministic 검출).
      - outlet 2개가 **paraphrase**(같은 사건·token 대부분 공유하나 정확 집합 불일치) → near_match_below_fingerprint
        (Jaccard≥near 이나 fingerprint 불일치 → adjudicator/LLM/embedding 영역·gated).
    + 무관 기사 1(overlap 0 대조군) + community 1(같은 제목이나 anchor 금지 reaction layer).
    headline≤512·canonical·published_at·source_id 만(본문 미저장). 실 source 가 아니라 **계약/입도 검증용**."""
    day = "2026-06-22"
    wire = "Major port strike halts container shipping operations nationwide"
    return [
        _rec(source_id="gdelt:wire_ap", canonical_url="https://outlet-a.test/strike",
             title_or_label=wire, published_at_or_observed_at=day),
        _rec(source_id="gdelt:wire_reuters", canonical_url="https://outlet-b.test/strike",
             title_or_label=wire, published_at_or_observed_at=day),
        # paraphrase A: wire 에서 "nationwide" 누락(token 7 ⊂ wire 8) → Jaccard 0.875·정확 집합 불일치 → near.
        _rec(source_id="gdelt:local_news", canonical_url="https://outlet-c.test/dockworkers",
             title_or_label="Major port strike halts container shipping operations",
             published_at_or_observed_at=day),
        # paraphrase B: "major"→없음·"today" 추가 → wire 와 Jaccard 0.778·정확 집합 불일치 → near.
        _rec(source_id="gdelt:biz_news", canonical_url="https://outlet-d.test/cargo",
             title_or_label="Port strike halts container shipping operations nationwide today",
             published_at_or_observed_at=day),
        _rec(source_id="gdelt:weather", canonical_url="https://outlet-e.test/heat",
             title_or_label="Record heat wave grips southern region this week",
             published_at_or_observed_at=day),
        _rec(record_type="community_signal", source_id="gdelt:forum",
             canonical_url="https://forum.test/strike-thread",
             title_or_label="Major port strike halts container shipping operations nationwide",
             published_at_or_observed_at=day),
    ]


# ── §5/A: GDELT provider governance(기존 단일 출처 honor·read-only preflight·network 0·write 0) ─────
def gdelt_provider_status(
    *, query: str = "world news", host_gate: Any = None,
    cooldown: Optional[tuple] = None, policy: Optional[dict] = None,
    state_path: Optional[str] = None,
) -> dict:
    """GDELT fetch 가 **지금 규정 준수로 가능한지** read-only preflight. network 0·write 0(decide 만, record 안 함).

    ADR#57 429 의 근인은 이 backend 도구가 기존 governance 를 우회한 raw httpx 였다(분석 §2-Q1~3). 이번 턴은
    ingestion 단일 출처를 **honor**한다:
      ① HostRateGate(gdelt host floor·shared host_rate_gate.json·cross-process) — 다른 루프가 host_min_spacing
         안에 쳤으면 host_rate_limited(호출 금지).
      ② rate_limit_policy(gdelt min_interval 60s·cooldown_on_429 900s·max_retries 1) — 정책 표면화.
      ③ 영속 429 cooldown(in_cooldown) — 진행 중이면 cooldown(호출 금지·respect cooldown·never_disable_on_single_429).
    test 주입(cooldown/host_gate/policy)으로 network·file 0 결정론. blocked → fetch 자체를 시도하지 않는다(no tight retry)."""
    rate_limit_policy_applied = policy
    # cooldown 주입은 (bool, retry_after) 2-튜플 계약 — 비정형 입력은 미주입으로 간주(ValueError 방어).
    have_cooldown = isinstance(cooldown, tuple) and len(cooldown) == 2
    cooled, retry_after = cooldown if have_cooldown else (False, None)
    host_allowed, host_reason, host_spacing = True, None, None

    if not have_cooldown or policy is None:
        try:
            from ingestion.core.rate_limit_policy import in_cooldown, load_rate_limit_policy
            if policy is None:
                pol = load_rate_limit_policy("gdelt")
                rate_limit_policy_applied = {
                    "min_interval_seconds": pol.min_interval_seconds,
                    "cooldown_on_429_seconds": pol.cooldown_on_429_seconds,
                    "max_retries_on_429": pol.max_retries_on_429,
                }
            if not have_cooldown:
                cooled, retry_after = in_cooldown("gdelt", query)
        except Exception:
            pass

    try:
        from ingestion.orchestration.host_rate_gate import (
            GDELT_HOST,
            GDELT_HOST_MIN_SPACING_SECONDS,
        )
        host_spacing = GDELT_HOST_MIN_SPACING_SECONDS
        gate = host_gate
        if gate is None:
            from pathlib import Path as _P

            from ingestion.orchestration.host_rate_gate import HostRateGate
            gate = HostRateGate(state_path=_P(state_path) if state_path
                                else _P("ingestion/outputs/state/host_rate_gate.json"))
        dec = gate.decide(GDELT_HOST, min_spacing_seconds=GDELT_HOST_MIN_SPACING_SECONDS)
        host_allowed, host_reason = dec.allowed, dec.reason
    except Exception:
        pass

    if cooled:
        status, block_reason = "cooldown", "provider_429_cooldown"
    elif not host_allowed:
        status, block_reason = "host_rate_limited", host_reason or "host_min_spacing_not_elapsed"
    else:
        status, block_reason = "ok", None
    return {
        "provider": "gdelt",
        "provider_status": status,
        "provider_block_reason": block_reason,
        "retry_after_or_cooldown": retry_after,
        "rate_limit_policy_applied": rate_limit_policy_applied,
        "host_min_spacing_seconds": host_spacing,
        "no_tight_retry": True,           # RATE_LIMITED 는 retry_policy.retry_on 밖 — 구조적 차단(분석 §2-Q4).
        "respect_cooldown": True,
    }


# ── GDELT real fetch(opt-in·bounded·key-free·본문 미저장·transport 주입 시 결정론) ───────────────
def _gdelt_url(query: str, timespan: str, maxrecords: int) -> str:
    from urllib.parse import urlencode
    return _GDELT_BASE + "?" + urlencode(
        {"query": query, "mode": "ArtList", "maxrecords": str(maxrecords),
         "format": "json", "timespan": timespan})


def parse_gdelt_articles(payload: str, *, max_records: int = _DEFAULT_MAX_RECORDS) -> Optional[list[dict]]:
    """GDELT ArtList JSON → record(canonical=art url·title·seendate=published_at·본문 미저장). 파싱 실패 None.

    같은 사건이 다른 outlet·다른 URL 로 등장하는 다출처 집계 — 실 cross-source overlap 의 핵심 생성원.
    seendate(YYYYMMDDhhmmss)는 그대로 published_at 으로 두면 normalize_time/_date_bucket 가 정규화한다."""
    try:
        data = json.loads(payload)
    except Exception:
        return None
    arts = data.get("articles")
    if not isinstance(arts, list):
        return None
    recs: list[dict] = []
    for art in arts[:max_records]:
        if not isinstance(art, dict):
            continue
        title = (art.get("title") or "").strip()
        url = (art.get("url") or "").strip()
        if not title or not url:
            continue
        recs.append(_rec(
            record_type="article_candidate", source_id="gdelt:" + (art.get("domain") or "unknown"),
            title_or_label=title[:512], canonical_url=url, source_url_or_evidence=url,
            published_at_or_observed_at=(art.get("seendate") or None),
            body_state_or_signal="present"))
    return recs


def fetch_gdelt_overlap_records(
    *, query: str = "world news", timespan: str = "1d",
    maxrecords: int = _DEFAULT_MAX_RECORDS,
    transport: Optional[Callable[[str], Optional[str]]] = None,
    provider_status: Optional[dict] = None,
) -> tuple[list[dict], Optional[str]]:
    """GDELT bounded 실 fetch(opt-in·network·CI 아님). transport 주입 시 결정론(테스트·network 0).

    provider_status(gdelt_provider_status 산출)가 'ok' 가 아니면 **network 를 시도하지 않고** block_reason 으로 즉시
    반환한다(respect cooldown·no tight retry — ADR#57 우회 재발 방지). 반환: (records, failure). 실패는 §6 분류
    (provider_429_cooldown/host_rate_limited/network_error/rate_limited/parser_error/no_records)."""
    if provider_status is not None and provider_status.get("provider_status") != "ok":
        return [], provider_status.get("provider_block_reason") or "provider_blocked"
    url = _gdelt_url(query, timespan, maxrecords)
    if transport is not None:
        payload = transport(url)
    else:
        try:
            import httpx
            r = httpx.get(url, timeout=20.0, follow_redirects=True,
                          headers={"User-Agent": _BROWSER_UA})
        except Exception:
            return [], "network_error"
        text = r.text or ""
        if r.status_code == 429 or "limit requests" in text.lower():
            return [], "rate_limited"
        if "json" not in (r.headers.get("content-type") or "").lower():
            return [], "parser_error"   # 200 이나 평문 안내(GDELT over-query) — JSON 아님.
        payload = text
    if not payload:
        return [], "network_error"
    recs = parse_gdelt_articles(payload, max_records=maxrecords)
    if recs is None:
        return [], "parser_error"
    if not recs:
        return [], "no_records"
    return recs, None


# ── §6/B: key-free RSS 다출처 real fetch(opt-in·bounded·governed·본문 미저장·transport 주입 시 결정론) ──
def _rss_endpoint(source_id: str) -> Optional[str]:
    """source_registry(_SERVICE_CONFIGS)에서 key-free(auth=none) RSS endpoint 만 읽는다(하드코딩 0·키 필요 source 거부)."""
    try:
        from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS
        cfg = _SERVICE_CONFIGS.get(source_id) or {}
        if cfg.get("auth", "none") != "none":
            return None
        return cfg.get("endpoint")
    except Exception:
        return None


def _rss_rate_limited(text: str) -> bool:
    """429/soft-limit 텍스트 판정 — error_taxonomy 단일 출처 재사용(중복 목록 금지)."""
    try:
        from ingestion.core.error_taxonomy import is_rate_limited_text
        return is_rate_limited_text(text)
    except Exception:
        return False


def _rss_host_allowed(endpoint: str, host_gate: Any) -> bool:
    """shared host gate **참여**(no-bypass). gate 미주입이면 단발 bounded GET(참여 안 함·best-effort True)."""
    if host_gate is None:
        return True
    try:
        from urllib.parse import urlparse
        host = urlparse(endpoint).netloc
        dec = host_gate.decide(host, min_spacing_seconds=_RSS_HOST_MIN_SPACING_SECONDS)
        if dec.allowed:
            host_gate.record_call(host)   # 실제 HTTP 직전 기록(다른 루프 가시화).
        return dec.allowed
    except Exception:
        return True


def _rss_pub_to_iso(pub: Optional[str]) -> Optional[str]:
    """RSS pubDate(RFC822) → YYYY-MM-DD(date bucket 호환). 실패 시 원문 유지(_date_bucket 가 ISO/seendate 처리)."""
    if not pub:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub)
        if dt is not None:
            return dt.date().isoformat()
    except Exception:
        pass
    return pub


def parse_rss_items(
    xml_text: str, *, source_id: str, max_items: int = _DEFAULT_MAX_RECORDS,
) -> Optional[list[dict]]:
    """RSS/Atom XML → record(title·link=canonical·pubDate=published_at·**본문 미저장**). 파싱 실패 None.

    다출처가 같은 사건을 paraphrase 헤드라인으로 보도 → 실 near_match_below_fingerprint(adjudicator-zone)의 핵심 생성원.
    stdlib xml.etree 만(신규 설치 0)·api_probe.py 의 item/entry 카운트와 동일 노드 모델. title≤512."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None
    _atom = "{http://www.w3.org/2005/Atom}"
    _dc = "{http://purl.org/dc/elements/1.1/}"
    items = root.findall(".//item")
    is_atom = False
    if not items:
        items = root.findall(f".//{_atom}entry")
        is_atom = bool(items)
    recs: list[dict] = []
    for it in items[:max_items]:
        if is_atom:
            title = (it.findtext(f"{_atom}title") or "").strip()
            # Atom 엔트리는 다중 <link>(rel=self/alternate/enclosure) — 기사 URL 은 rel 없음/alternate.
            # find()는 첫 요소(self 일 수 있음)만 → rel 우선순위로 canonical 오캡처 방지(feed_discovery 와 일관).
            link = ""
            for le in it.findall(f"{_atom}link"):
                if le.get("rel") in (None, "alternate"):
                    link = (le.get("href") or "").strip()
                    if link:
                        break
            pub = (it.findtext(f"{_atom}updated") or it.findtext(f"{_atom}published") or "").strip()
        else:
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or it.findtext(f"{_dc}date") or "").strip()
        if not title or not link:
            continue
        recs.append(_rec(
            record_type="article_candidate", source_id="rss:" + source_id,
            title_or_label=title[:512], canonical_url=link, source_url_or_evidence=link,
            published_at_or_observed_at=_rss_pub_to_iso(pub), body_state_or_signal="present"))
    return recs


def fetch_rss_overlap_records(
    source_ids: Optional[list[str]] = None, *, max_items: int = 10,
    transport: Optional[Callable[[str, str], Optional[str]]] = None,
    host_gate: Any = None,
) -> tuple[list[dict], dict]:
    """key-free RSS 다출처 bounded 실 fetch(opt-in·network·CI 아님). transport(source_id,endpoint)→xml 주입 시 결정론.

    GDELT 우회 실수 반복 금지: registry endpoint(key-free 만)·shared host gate 참여·bounded·timeout·본문 미저장.
    반환: (records, {source_id: status}). status=ok/rate_limited/network_error/parser_error/no_records/no_endpoint."""
    sids = list(source_ids) if source_ids else list(_RSS_OVERLAP_SOURCES)
    records: list[dict] = []
    status: dict[str, str] = {}
    for sid in sids:
        endpoint = _rss_endpoint(sid)
        if not endpoint:
            status[sid] = "no_endpoint"
            continue
        if transport is not None:
            text = transport(sid, endpoint)
            if text is None:
                status[sid] = "network_error"
                continue
        else:
            if not _rss_host_allowed(endpoint, host_gate):
                status[sid] = "host_rate_limited"
                continue
            try:
                import httpx
                r = httpx.get(endpoint, timeout=20.0, follow_redirects=True,
                              headers={"User-Agent": _BROWSER_UA})
            except Exception:
                status[sid] = "network_error"
                continue
            text = r.text or ""
            if r.status_code == 429 or _rss_rate_limited(text):
                status[sid] = "rate_limited"
                continue
        recs = parse_rss_items(text, source_id=sid, max_items=max_items)
        if recs is None:
            status[sid] = "parser_error"
            continue
        if not recs:
            status[sid] = "no_records"
            continue
        records.extend(recs)
        status[sid] = "ok"
    return records, status


# ── write-free pairwise overlap discovery(병합 없음·신호 측정만) ─────────────────────────────────
def discover_overlap(
    records: list[dict], *, discovery_mode: str = "captured_fixture",
    real_fetch: bool = False, near_jaccard: float = DEFAULT_NEAR_JACCARD,
    emit_candidate_pairs: bool = False,
) -> dict:
    """record 목록 → 다입도 pairwise overlap 수치화(write-free·no-merge·§4/§5 fields).

    overlap 을 ①fingerprint 정확일치(deterministic 검출) ②near_match_below_fingerprint(adjudicator/LLM 영역)
    로 분해해 "어디까지 deterministic 이 잡고 어디부터 adjudicator 영역인가"를 정직하게 가른다. 병합하지 않는다.

    emit_candidate_pairs(ADR#65·additive·기본 off=ADR#57/#64 frozen 불변): True 면 **near floor 와 무관하게**
    전 publishable·cross-URL·same-date pair 를 `candidate_pairs`(band 태그: fingerprint/near_match/hard_negative/
    below_floor)로 노출한다. deterministic near band 가 떨군 paraphrase 후보(ADR#64 cross_source_pair 100 중
    title-Jaccard<floor)를 **semantic candidate scorer 가 직접 점수화**하도록 입력을 제공하기 위함(병합·단정 0·점수 0)."""
    n = len(records)
    by_source: dict[str, int] = {}
    for r in records:
        sid = r.get("source_id") or "unknown"
        by_source[sid] = by_source.get(sid, 0) + 1

    canonical_overlap = 0          # 같은 canonical_url(강 anchor dup — cross-source 후보 아님·이미 병합 대상)
    date_overlap = 0               # 같은 date bucket(임의 role)
    fingerprint_overlap = 0        # 정확 fingerprint 일치·다른 URL·둘 다 publishable → deterministic 검출
    near_only = 0                  # near Jaccard≥near·fingerprint 불일치·다른 URL·둘 다 publishable → adjudicator 영역
    hard_neg_band = 0              # [_HARD_NEG_FLOOR,near) overlap·publishable·다른 URL·같은 날 → different-event lean(reviewer 음성 후보)
    possible_same_event: list[tuple[str, str, str]] = []   # (canonical_i, canonical_j, granularity)
    near_match_pairs: list[dict] = []      # near(adjudicator-zone) pair 전체 정보(reviewer route 입력·병합 아님)
    hard_negative_pairs: list[dict] = []   # hard-negative band pair(reviewer/gold 음성 floor·calibration·라벨은 reviewer)
    candidate_pairs: list[dict] = []       # ADR#65: 전 publishable cross-URL same-date pair(band 태그·scorer 입력·emit_candidate_pairs 시만)
    pair_matrix: dict[tuple[str, str], dict[str, int]] = {}
    publishable_pairs = 0
    publishable_same_date_pairs = 0
    publishable_cross_url_same_date_pairs = 0

    for a, b in combinations(range(n), 2):
        ra, rb = records[a], records[b]
        same_date = bool(_date_bucket(ra)) and _date_bucket(ra) == _date_bucket(rb)
        if same_date:
            date_overlap += 1
        ca, cb = ra.get("canonical_url"), rb.get("canonical_url")
        same_canon = bool(ca) and ca == cb
        if same_canon:
            canonical_overlap += 1
        both_pub = _publishable(ra) and _publishable(rb)
        if not both_pub:
            continue
        publishable_pairs += 1
        if same_date:
            publishable_same_date_pairs += 1
        if same_canon or not same_date:
            continue   # cross-source overlap 후보 = 다른 URL·같은 날만.
        publishable_cross_url_same_date_pairs += 1
        fa, fb = _fingerprint(ra), _fingerprint(rb)
        jac = _jaccard(_title_tokens(ra.get("title_or_label")), _title_tokens(rb.get("title_or_label")))
        pkey = tuple(sorted((ra.get("source_id") or "unknown", rb.get("source_id") or "unknown")))
        slot = pair_matrix.setdefault(pkey, {"same_date": 0, "fingerprint": 0, "near": 0, "hard_neg": 0, "possible": 0})
        slot["same_date"] += 1
        band = "below_floor"   # ADR#65 candidate band(near floor 미만 — deterministic 가 떨군 paraphrase 후보 포함)
        if fa is not None and fa == fb:
            band = "fingerprint"
            fingerprint_overlap += 1
            slot["fingerprint"] += 1
            slot["possible"] += 1
            possible_same_event.append((ca, cb, "fingerprint"))
        elif jac >= near_jaccard:
            band = "near_match"
            near_only += 1
            slot["near"] += 1
            slot["possible"] += 1
            possible_same_event.append((ca, cb, "near_match_below_fingerprint"))
            near_match_pairs.append(_near_pair_record(ra, rb, a, b, jac))
        elif jac >= _HARD_NEG_FLOOR:
            # overlap 은 있으나 near 미만 — 같은 사건 후보 아님(possible 미가산). 다른 사건이 비슷한 어휘를 쓰는
            # "헷갈릴 만한 음성"(hard negative) — reviewer/gold 음성 floor·calibration 으로만 보냄(병합·단정 0).
            band = "hard_negative"
            hard_neg_band += 1
            slot["hard_neg"] += 1
            hard_negative_pairs.append(_near_pair_record(ra, rb, a, b, jac, prefix="hn"))
        if emit_candidate_pairs:
            # band 무관·전 publishable cross-URL same-date pair → scorer 입력(점수 0·병합 0). order-invariant pair_id=cp:i-j.
            cp = _near_pair_record(ra, rb, a, b, jac, prefix="cp")
            cp["band"] = band
            candidate_pairs.append(cp)

    block_reasons = _block_reasons(
        records, possible=len(possible_same_event), fingerprint=fingerprint_overlap, near=near_only,
        publishable_pairs=publishable_pairs, pub_same_date=publishable_same_date_pairs,
        pub_cross_url_same_date=publishable_cross_url_same_date_pairs)

    return {
        "discovery_mode": discovery_mode,
        "real_fetch": real_fetch,
        "live_db": False,
        "no_auto_merge": True,
        "source_count": len(by_source),
        "records_by_source": dict(sorted(by_source.items())),
        "total_records": n,
        "body_present_count": sum(
            1 for r in records if (r.get("body_state_or_signal") or "missing") != "missing"),
        "canonical_count": sum(1 for r in records if r.get("canonical_url")),
        "published_at_count": sum(1 for r in records if r.get("published_at_or_observed_at")),
        "date_bucket_overlap_pairs": date_overlap,
        "canonical_overlap_pairs": canonical_overlap,
        "title_token_overlap_pairs": fingerprint_overlap + near_only,   # near 이상(fingerprint 포함)
        "fingerprint_overlap_pairs": fingerprint_overlap,               # deterministic 검출(→ semantic_cross_batch_candidate)
        "near_match_below_fingerprint_pairs": near_only,                # adjudicator/LLM 영역(deterministic 사각지대)
        "possible_same_event_pairs": len(possible_same_event),
        "deterministic_detectable_pairs": fingerprint_overlap,
        "adjudicator_zone_pairs": near_only,
        "near_match_pairs": near_match_pairs,        # adjudicator-zone pair 전체 정보(reviewer route 입력·병합 아님)
        "hard_negative_band_pairs": hard_neg_band,   # [floor,near) overlap·different-event lean(reviewer 음성 후보 수)
        "hard_negative_pairs": hard_negative_pairs,  # hard-negative band pair 전체 정보(reviewer/gold calibration·병합 아님)
        "candidate_pairs": candidate_pairs,          # ADR#65: 전 publishable cross-URL same-date pair(band 태그·scorer 입력·emit_candidate_pairs 시만·기본 [])
        # write-free — DB 단계는 미도달(정직). live-db escalation 시 real_source_identity_smoke 가 채운다.
        "semantic_cross_batch_candidates": None,
        "adjudications": None,
        "packet_eligible": None,
        "reviewer_packet_exportable": None,
        "overlap_potential_matrix": _overlap_potential_matrix(pair_matrix),
        "block_reasons": block_reasons,
        "near_jaccard_threshold": near_jaccard,
        "fingerprint_min_tokens": _MIN_SEMANTIC_TOKENS,
        "within_batch_weak_threshold": _TITLE_JACCARD_THRESHOLD,
    }


def _overlap_potential_matrix(pair_matrix: dict[tuple[str, str], dict[str, int]]) -> list[dict]:
    """source-pair 별 overlap 잠재력(Agent 가 어느 pair 를 어떤 목적으로 수집할지 판단할 substrate)."""
    rows: list[dict] = []
    for (sa, sb), c in sorted(pair_matrix.items()):
        if c["possible"] > 0:
            potential = "deterministic_detectable" if c["fingerprint"] > 0 else "adjudicator_zone_only"
        else:
            potential = "no_overlap"
        rows.append({
            "source_pair": [sa, sb],
            "same_date_pairs": c["same_date"],
            "fingerprint_overlap": c["fingerprint"],
            "near_match_overlap": c["near"],
            "hard_negative_overlap": c.get("hard_neg", 0),
            "possible_same_event": c["possible"],
            "overlap_potential": potential,
        })
    return rows


def _near_pair_record(ra: dict, rb: dict, ia: int, ib: int, jac: float, *, prefix: str = "nm") -> dict:
    """near_match_below_fingerprint(prefix=nm) / hard-negative band(prefix=hn) pair → reviewer-route 입력 record
    (병합 아님·predicted_status 미포함).

    order-invariant: 왼쪽=사전식 작은 source_id(결정론·pair_id 안정)."""
    left, right = ((ra, rb) if (ra.get("source_id") or "") <= (rb.get("source_id") or "")
                   else (rb, ra))
    return {
        "pair_id": f"{prefix}:{min(ia, ib)}-{max(ia, ib)}",
        "source_id_left": left.get("source_id"),
        "source_id_right": right.get("source_id"),
        "source_type_left": _role(left),
        "source_type_right": _role(right),
        "title_left": left.get("title_or_label"),
        "title_right": right.get("title_or_label"),
        "observed_at_left": left.get("published_at_or_observed_at"),
        "observed_at_right": right.get("published_at_or_observed_at"),
        "canonical_url_left": left.get("canonical_url"),
        "canonical_url_right": right.get("canonical_url"),
        "title_token_jaccard": round(jac, 4),
        "date_bucket_match": True,          # near 후보는 same-date publishable pair 에서만 생성.
        "source_role_compatible": _publishable(left) and _publishable(right),
    }


# ── §8/D: near-match reviewer candidate route(병합 0·LLM 0·gold/MERGE_GATE 필수) ─────────────────
def build_near_match_reviewer_candidates(discovery: dict) -> list[dict]:
    """near_match_below_fingerprint(paraphrase·deterministic fingerprint 사각지대) → reviewer candidate worksheet 행.

    핵심: 결정론 fingerprint 가 못 잡는 paraphrase overlap 을 **버리지도 병합하지도 않고** reviewer/gold/MERGE_GATE
    로 보내는 통로. 기존 EvalPair/LabelingPacketItem 입력 스키마와 정합(label=unlabeled·predicted_status **미포함**=bias 차단)
    + `risk_tags` 에 `"paraphrase"`(다운스트림 `assign_candidate_bucket` 이 인식하는 정확 토큰)를 실어 `build_labeling_packet`
    이 **`paraphrase` bucket 으로 분류** 가능(other 미분류 회피). 경계: publishable×publishable 만(community/market/catalog
    anchor 금지)·no_merge_without_gold(같은 사건 단정 금지)."""
    out: list[dict] = []
    for p in discovery.get("near_match_pairs") or []:
        if not p.get("source_role_compatible"):
            continue   # publishable core 만 reviewer 후보.
        out.append({
            "pair_id": p["pair_id"],
            "label": "unlabeled",                 # reviewer/gold 가 채움 — predicted_status 미입력(bias 차단).
            "language": "und",                    # 결정론 단계 미산출(언어 판정은 reviewer/calibration 영역).
            "source_type_left": p["source_type_left"],
            "source_type_right": p["source_type_right"],
            "title_left": p["title_left"],
            "title_right": p["title_right"],
            "observed_at_left": p["observed_at_left"],
            "observed_at_right": p["observed_at_right"],
            "canonical_url_left": p["canonical_url_left"],
            "canonical_url_right": p["canonical_url_right"],
            "title_token_jaccard": p["title_token_jaccard"],
            "date_bucket_match": p["date_bucket_match"],
            # "paraphrase" = 다운스트림 assign_candidate_bucket 이 인식하는 정확 bucket 토큰(other 미분류 회피).
            "risk_tags": ["near_match_below_fingerprint", "paraphrase"],
            "reason": "near_match_below_fingerprint(paraphrase overlap·deterministic fingerprint 사각지대)",
            "no_merge_without_gold": True,        # gold/MERGE_GATE 없이 병합·같은 사건 단정 금지(불변).
        })
    return out


def build_hard_negative_reviewer_candidates(discovery: dict) -> list[dict]:
    """hard_negative_pairs([_HARD_NEG_FLOOR,near) overlap·different-event lean) → reviewer candidate worksheet 행.

    near-match(near-positive)와 **분리된 음성 후보** — reviewer/gold 음성 floor·calibration(같은 사건 단정 아님·
    risk_tags=`hard_negative` → 다운스트림 `assign_candidate_bucket` 이 `hard_negative` bucket 으로 분류). 라벨은
    reviewer 가 채움(predicted_status 미포함=bias 차단). 경계: publishable×publishable 만·no_merge_without_gold."""
    out: list[dict] = []
    for p in discovery.get("hard_negative_pairs") or []:
        if not p.get("source_role_compatible"):
            continue   # publishable core 만 reviewer 후보(community/market/catalog 음성 후보도 anchor 금지).
        out.append({
            "pair_id": p["pair_id"],
            "label": "unlabeled",                 # reviewer/gold 가 채움 — predicted_status 미입력(bias 차단).
            "language": "und",                    # 결정론 단계 미산출(언어 판정은 reviewer/calibration 영역).
            "source_type_left": p["source_type_left"],
            "source_type_right": p["source_type_right"],
            "title_left": p["title_left"],
            "title_right": p["title_right"],
            "observed_at_left": p["observed_at_left"],
            "observed_at_right": p["observed_at_right"],
            "canonical_url_left": p["canonical_url_left"],
            "canonical_url_right": p["canonical_url_right"],
            "title_token_jaccard": p["title_token_jaccard"],
            "date_bucket_match": p["date_bucket_match"],
            # "hard_negative" = assign_candidate_bucket 이 인식하는 정확 음성 bucket 토큰(음성 floor 충당).
            "risk_tags": ["hard_negative"],
            "reason": "hard_negative_band(publishable·same-date·cross-URL·near 미만 — different-event lean·reviewer 확인 필요)",
            "no_merge_without_gold": True,        # gold/MERGE_GATE 없이 병합·같은 사건 단정 금지(불변).
        })
    return out


def _block_reasons(
    records: list[dict], *, possible: int, fingerprint: int, near: int,
    publishable_pairs: int, pub_same_date: int, pub_cross_url_same_date: int,
) -> list[str]:
    """possible_same_event=0(또는 fingerprint=0) 의 **정확한 원인**을 단계로 분해(source scarcity 를 모델 실패로
    뭉뚱그리지 않는다). overlap 이 near 만 있고 fingerprint 가 0 이면 deterministic 사각지대를 명시한다."""
    out: list[str] = []
    if len(records) < 2:
        out.append("insufficient_records")
        return out
    if publishable_pairs == 0:
        out.append("non_publishable_role")   # community/market/catalog only — anchor 부재.
        return out
    if possible == 0:
        if pub_same_date == 0:
            out.append("no_date_bucket_overlap")     # 같은 날 publishable pair 부재(시점 분산).
        elif pub_cross_url_same_date == 0:
            out.append("single_canonical_no_cross_source")   # 같은 URL 만(다출처 아님 → 이미 강 anchor dup).
        else:
            out.append("no_title_overlap")           # 다출처·같은 날이나 token overlap 미달(서로 다른 사건).
        return out
    if fingerprint == 0 and near > 0:
        # overlap 은 있으나 fingerprint 정확일치 0 → deterministic 미검출. adjudicator/embedding/LLM 영역(gated).
        out.append("near_match_below_fingerprint")
    return out


# ── Agent orchestration schema(§9·LLM 호출 0·merge 불가 명문화) ──────────────────────────────────
def build_agent_orchestration_schema(discovery: dict) -> dict:
    """결정론 overlap 신호 → Agent 가 다음 수집을 계획할 schema(추천·계획만·병합/공개 IU 생성 불가).

    Agent 는 overlap 가능 source pair·시점창·watch topic 을 추천할 수 있으나, MERGE_GATE·gold 없이 같은 사건이라고
    단정하거나 병합할 수 없다(no_merge_without_gate). 이번 턴 LLM 호출 0 — 다음 단계가 쓸 substrate 만 보강."""
    matrix = discovery.get("overlap_potential_matrix") or []
    recommended_pairs = [m["source_pair"] for m in matrix if m["overlap_potential"] != "no_overlap"]
    det = discovery.get("deterministic_detectable_pairs", 0) or 0
    adj = discovery.get("adjudicator_zone_pairs", 0) or 0
    if det > 0:
        reason = "fingerprint_exact_token_set_match(같은 사건·다른 URL·같은 날 — deterministic 검출)"
    elif adj > 0:
        reason = "near_match_below_fingerprint(paraphrase overlap — adjudicator/embedding/LLM 영역·gated)"
    else:
        reason = "no_overlap(source coverage/시점/다출처 부족 — block_reasons 참조)"
    return {
        "recommended_source_pairs": recommended_pairs,
        "recommended_time_windows": ["1d", "7d"],   # GDELT timespan(다출처 같은 사건 재유입 관측창).
        "recommended_watch_topics": [],              # 결정론 단계 미산출(LLM/Agent 가 채움 — 이번 턴 미배선).
        "expected_overlap_reason": reason,
        "source_role_constraints": {
            "merge_anchor_eligible": sorted(_PUBLISHABLE_SOURCE_TYPES),   # official/article 만.
            "reaction_layer_only": ["community"],
            "signal_layer_only": ["signal"],
            "enrichment_only": ["catalog"],
            "url_candidate_only": ["search"],
        },
        "evidence_requirements": ["canonical_url", "published_at", "title"],
        "expected_agent_utility": (
            "deterministic_cross_batch_candidate" if det > 0 else
            ("reviewer_gold_candidate(near-match·adjudicator-zone)" if adj > 0 else "coverage_expansion")),
        "reviewer_candidate_exportable": adj > 0,   # near-match 가 있으면 reviewer worksheet export 가능(병합 아님).
        "uncertainty": {
            "fingerprint_precision_recall": "high_precision_low_recall(정확 token-set 일치만)",
            "adjudicator_zone_unverified": adj,   # near overlap 은 gold/MERGE_GATE 없이는 미확정.
        },
        "no_merge_without_gate": True,             # MERGE_GATE·gold 없이 병합 금지(불변).
        "no_public_intelligence_unit": True,       # curated IU 생성 금지(미구축).
        "llm_invoked": False,                      # 이번 턴 LLM 호출 0.
        "next_fetch_plan": (
            "deterministic overlap 존재 → live-db escalation 으로 semantic_cross_batch_candidate 실측"
            if det > 0 else
            ("adjudicator-zone overlap 존재 → embedding/LLM adjudicator(gated)·실 gold 필요"
             if adj > 0 else "다출처/시점/topic 커버리지 확대 후 재탐색(block_reasons 분해 참조)")),
    }


# ── §7/C: acquisition planning matrix(source pair/topic/time window·Agent-ready·LLM 0·병합 0) ──────
def build_acquisition_plan(
    discovery: dict, *, candidate_source_ids: Optional[list[str]] = None,
) -> dict:
    """측정된 overlap_potential + role 호환성으로 **무작위 수집을 목적 기반 수집으로** 전환하는 계획(LLM 0·병합 0).

    Agent 는 이 plan 으로 어느 source pair 를 어떤 시점창/목적으로 수집할지 정할 수 있으나, 같은 사건 단정·병합·
    공개 IU 생성은 못 한다(no_merge_without_gate). topic/watch keyword 는 LLM/Agent 영역(이번 턴 미배선·결정론 substrate 만)."""
    matrix = discovery.get("overlap_potential_matrix") or []
    source_pair_plan: list[dict] = []
    for m in matrix:
        if m["overlap_potential"] == "no_overlap":
            continue
        sa, sb = m["source_pair"]
        source_pair_plan.append({
            "source_a": sa, "source_b": sb,
            "expected_overlap_reason": (
                "fingerprint_exact_token_set" if m["fingerprint_overlap"] > 0
                else "near_match_below_fingerprint(paraphrase·adjudicator-zone)"),
            "expected_overlap_utility": m["overlap_potential"],
            "measured_possible_same_event": m["possible_same_event"],
            "required_fetch_window": "1d",
            "max_records": _DEFAULT_MAX_RECORDS,
            "no_merge_without_gate": True,
        })
    return {
        "source_pair_plan": source_pair_plan,
        "topic_window_plan": {
            "topics": [],   # 결정론 단계 미산출 — LLM/Agent 가 채움(이번 턴 미배선).
            "note": "watch topic/keyword 는 LLM/Agent 영역(미배선) — 결정론 substrate 만 제공.",
        },
        "time_window_plan": [
            {"window": "1d", "purpose": "실시간 다출처 같은 사건 재유입(최신·최협소)"},
            {"window": "7d", "purpose": "느린 paraphrase 재보도·official↔news 확증 lag 관측"},
        ],
        "expected_overlap_utility": (
            "deterministic_detectable" if discovery.get("deterministic_detectable_pairs")
            else ("adjudicator_zone_only" if discovery.get("adjudicator_zone_pairs") else "no_overlap")),
        "candidate_source_ids": sorted(candidate_source_ids) if candidate_source_ids else [],
        "no_merge_without_gate": True,
    }


# ── §4: acquisition report 조립(provider/plan/near-match/agent 통합·필수 fields) ───────────────────
def assemble_acquisition_report(
    discovery: dict, *, provider_status: Optional[dict] = None,
    plan: Optional[dict] = None, reviewer_candidates: Optional[list[dict]] = None,
    schema: Optional[dict] = None, rss_status: Optional[dict] = None,
) -> dict:
    """§4 필수 report fields 를 단일 dict 로 조립(write-free·병합 0). 운영 의사결정/문서/테스트가 같은 표면을 본다."""
    ps = provider_status or {}
    plan = plan or {}
    schema = schema or {}
    reviewer_candidates = reviewer_candidates or []
    return {
        "provider_status": ps.get("provider_status"),
        "provider_block_reason": ps.get("provider_block_reason"),
        "retry_after_or_cooldown": ps.get("retry_after_or_cooldown"),
        "rate_limit_policy_applied": ps.get("rate_limit_policy_applied"),
        "rss_provider_status": rss_status or {},
        "source_pair_plan": plan.get("source_pair_plan", []),
        "topic_window_plan": plan.get("topic_window_plan", {}),
        "time_window_plan": plan.get("time_window_plan", []),
        "expected_overlap_utility": plan.get("expected_overlap_utility"),
        "expected_agent_utility": schema.get("expected_agent_utility"),
        "source_quality_constraints": schema.get("source_role_constraints", {}),
        "near_match_candidate_count": len(reviewer_candidates),
        "deterministic_detectable_count": discovery.get("deterministic_detectable_pairs", 0),
        "adjudicator_zone_count": discovery.get("adjudicator_zone_pairs", 0),
        "reviewer_candidate_exportable": bool(reviewer_candidates),
        "no_merge_without_gate": True,
        "no_public_intelligence_unit": True,
        "llm_invoked": False,
        "next_fetch_plan": schema.get("next_fetch_plan"),
    }


# ── CLI(기본 captured fixture·network 0; --live-gdelt / --live-rss opt-in·CI 아님) ─────────────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="source overlap discovery (write-free·no-merge; 기본 captured fixture·network 0).")
    parser.add_argument("--live-gdelt", action="store_true",
                        help="GDELT bounded 실 fetch(opt-in·network·CI 아님·key-free). 미지정=captured fixture.")
    parser.add_argument("--live-rss", action="store_true",
                        help="key-free RSS 다출처 bounded 실 fetch(opt-in·network·CI 아님·governed). 미지정=captured fixture.")
    parser.add_argument("--query", default="world news", help="GDELT query(--live-gdelt).")
    parser.add_argument("--timespan", default="1d", help="GDELT timespan 시점창(1d/7d/3m).")
    parser.add_argument("--maxrecords", type=int, default=_DEFAULT_MAX_RECORDS, help="GDELT bounded 상한.")
    parser.add_argument("--near-jaccard", type=float, default=DEFAULT_NEAR_JACCARD,
                        help="near-match Jaccard 임계(fingerprint 사각지대 관측창).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    failure: Optional[str] = None
    provider_status: Optional[dict] = None
    rss_status: Optional[dict] = None
    if ns.live_gdelt:
        provider_status = gdelt_provider_status(query=ns.query)
        print(f"- gdelt provider preflight: status={provider_status['provider_status']} "
              f"block={provider_status['provider_block_reason']} cooldown={provider_status['retry_after_or_cooldown']} "
              f"policy={provider_status['rate_limit_policy_applied']}")
        print(f"- live-gdelt fetch (opt-in·bounded·key-free·governed): query={ns.query!r} timespan={ns.timespan} max={ns.maxrecords}")
        records, failure = fetch_gdelt_overlap_records(
            query=ns.query, timespan=ns.timespan, maxrecords=ns.maxrecords, provider_status=provider_status)
        mode, real = "source_pair_live", True
        if failure:
            print(f"- live-gdelt failure: {failure} → captured fixture fallback")
            records, mode, real = build_captured_overlap_fixture(), "captured_fixture", False
    elif ns.live_rss:
        print(f"- live-rss fetch (opt-in·bounded·key-free·governed): sources={list(_RSS_OVERLAP_SOURCES)} max={ns.maxrecords}")
        host_gate = None
        try:   # shared host gate 참여(no-bypass) — GDELT 우회 교훈 적용. 미설치/오류 시 best-effort(미참여).
            from pathlib import Path as _P

            from ingestion.orchestration.host_rate_gate import HostRateGate
            host_gate = HostRateGate(state_path=_P("ingestion/outputs/state/host_rate_gate.json"))
        except Exception:
            host_gate = None
        records, rss_status = fetch_rss_overlap_records(max_items=ns.maxrecords, host_gate=host_gate)
        print(f"- live-rss provider status: {rss_status}")
        mode, real = "source_pair_live_rss", True
        if not records:
            failure = "rss_no_records"
            print(f"- live-rss failure: {rss_status} → captured fixture fallback")
            records, mode, real = build_captured_overlap_fixture(), "captured_fixture", False
    else:
        records, mode, real = build_captured_overlap_fixture(), "captured_fixture", False

    disc = discover_overlap(records, discovery_mode=mode, real_fetch=real, near_jaccard=ns.near_jaccard)
    schema = build_agent_orchestration_schema(disc)
    plan = build_acquisition_plan(disc, candidate_source_ids=list(_RSS_OVERLAP_SOURCES))
    reviewer_candidates = build_near_match_reviewer_candidates(disc)
    report = assemble_acquisition_report(
        disc, provider_status=provider_status, plan=plan,
        reviewer_candidates=reviewer_candidates, schema=schema, rss_status=rss_status)
    print(
        f"- discovery[{disc['discovery_mode']}]: real_fetch={disc['real_fetch']} "
        f"sources={disc['source_count']} records={disc['total_records']} "
        f"canonical={disc['canonical_count']} published={disc['published_at_count']}")
    print(
        f"- overlap: date_bucket={disc['date_bucket_overlap_pairs']} canonical={disc['canonical_overlap_pairs']} "
        f"fingerprint={disc['fingerprint_overlap_pairs']} near_only={disc['near_match_below_fingerprint_pairs']} "
        f"possible_same_event={disc['possible_same_event_pairs']}")
    print(
        f"- decompose: deterministic_detectable={disc['deterministic_detectable_pairs']} "
        f"adjudicator_zone={disc['adjudicator_zone_pairs']} block_reasons={disc['block_reasons']} "
        f"no_auto_merge={disc['no_auto_merge']} live_gdelt_failure={failure}")
    for m in disc["overlap_potential_matrix"]:
        print(f"  · pair {m['source_pair']}: {m['overlap_potential']} (fingerprint={m['fingerprint_overlap']}·near={m['near_match_overlap']})")
    print(f"- agent_schema: recommended_pairs={len(schema['recommended_source_pairs'])} "
          f"expected_overlap={schema['expected_overlap_reason']}")
    print(f"  · next_fetch_plan: {schema['next_fetch_plan']}")
    print(f"  · no_merge_without_gate={schema['no_merge_without_gate']} llm_invoked={schema['llm_invoked']}")
    print(f"- acquisition_plan: source_pairs={len(plan['source_pair_plan'])} "
          f"expected_overlap_utility={plan['expected_overlap_utility']} "
          f"time_windows={[w['window'] for w in plan['time_window_plan']]}")
    print(f"- near_match_reviewer_candidates: count={report['near_match_candidate_count']} "
          f"exportable={report['reviewer_candidate_exportable']} (병합 0·gold/MERGE_GATE 필수)")
    for rc in reviewer_candidates:
        print(f"  · {rc['pair_id']} [{rc['source_type_left']}×{rc['source_type_right']}] "
              f"jaccard={rc['title_token_jaccard']} no_merge_without_gold={rc['no_merge_without_gold']}")
    print(f"- report: provider_status={report['provider_status']} "
          f"deterministic_detectable={report['deterministic_detectable_count']} "
          f"adjudicator_zone={report['adjudicator_zone_count']} llm_invoked={report['llm_invoked']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

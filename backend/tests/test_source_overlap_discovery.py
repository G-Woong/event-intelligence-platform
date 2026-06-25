"""ADR#57 — source overlap discovery 테스트(§10 시나리오 1-20·36-40).

write-free·no-merge·no-DB 계약과 두 입도(fingerprint 정확일치 vs near_match_below_fingerprint) 분해,
GDELT bounded fetch 실패 분류, agent orchestration schema(LLM 호출 0·merge 불가)를 잠근다.
"""
from __future__ import annotations

import json

from backend.app.tools.source_overlap_discovery import (
    _HARD_NEG_FLOOR,
    _RSS_OVERLAP_SOURCES,
    DEFAULT_NEAR_JACCARD,
    _rec,
    assemble_acquisition_report,
    build_acquisition_plan,
    build_agent_orchestration_schema,
    build_captured_overlap_fixture,
    build_hard_negative_reviewer_candidates,
    build_near_match_reviewer_candidates,
    discover_overlap,
    fetch_gdelt_overlap_records,
    fetch_rss_overlap_records,
    gdelt_provider_status,
    parse_gdelt_articles,
    parse_rss_items,
)


# ── §10 overlap discovery (1-10) ────────────────────────────────────────────────
def test_captured_fixture_decomposes_fingerprint_vs_near():
    """possible overlap 은 존재하나 deterministic 은 verbatim 만 검출·paraphrase 는 adjudicator-zone(핵심 통찰)."""
    disc = discover_overlap(build_captured_overlap_fixture())
    assert disc["fingerprint_overlap_pairs"] == 1          # wire_ap × wire_reuters(verbatim)
    assert disc["near_match_below_fingerprint_pairs"] == 5  # paraphrase pairs
    assert disc["possible_same_event_pairs"] == 6
    assert disc["deterministic_detectable_pairs"] == 1
    assert disc["adjudicator_zone_pairs"] == 5
    assert disc["no_auto_merge"] is True
    assert disc["live_db"] is False


def test_source_pair_matrix_generated():
    disc = discover_overlap(build_captured_overlap_fixture())
    matrix = {tuple(m["source_pair"]): m for m in disc["overlap_potential_matrix"]}
    # publishable 5개 → C(5,2)=10 pair(community 는 anchor 아님 → 제외).
    assert len(matrix) == 10
    assert matrix[("gdelt:wire_ap", "gdelt:wire_reuters")]["overlap_potential"] == "deterministic_detectable"
    assert matrix[("gdelt:biz_news", "gdelt:local_news")]["overlap_potential"] == "adjudicator_zone_only"
    assert matrix[("gdelt:weather", "gdelt:wire_ap")]["overlap_potential"] == "no_overlap"


def test_title_token_and_date_and_fingerprint_overlap_computed():
    disc = discover_overlap(build_captured_overlap_fixture())
    assert disc["date_bucket_overlap_pairs"] == 15          # 6 record 모두 같은 날 → C(6,2)
    assert disc["title_token_overlap_pairs"] == 6           # near 이상(fingerprint 포함)
    assert disc["fingerprint_overlap_pairs"] == 1


def test_canonical_overlap_excluded_from_cross_source():
    """같은 canonical = 강 anchor dup(이미 병합 대상) → cross-source 후보 아님(possible 에 미포함)."""
    day = "2026-06-22"
    title = "Major port strike halts container shipping operations nationwide"
    recs = [
        _rec(source_id="a", canonical_url="https://x.test/1", title_or_label=title, published_at_or_observed_at=day),
        _rec(source_id="b", canonical_url="https://x.test/1", title_or_label=title, published_at_or_observed_at=day),
    ]
    disc = discover_overlap(recs)
    assert disc["canonical_overlap_pairs"] == 1
    assert disc["fingerprint_overlap_pairs"] == 0
    assert disc["possible_same_event_pairs"] == 0
    assert "single_canonical_no_cross_source" in disc["block_reasons"]


def test_source_role_compatibility_community_excluded_as_anchor():
    """community record 는 merge anchor 후보에서 제외(role guard) — pair matrix 에 미등장."""
    disc = discover_overlap(build_captured_overlap_fixture())
    pairs = [tuple(m["source_pair"]) for m in disc["overlap_potential_matrix"]]
    assert all("gdelt:forum" not in p for p in pairs)


def test_no_merge_occurs():
    disc = discover_overlap(build_captured_overlap_fixture())
    assert disc["no_auto_merge"] is True
    # write-free — DB 단계 미도달(정직).
    assert disc["semantic_cross_batch_candidates"] is None
    assert disc["adjudications"] is None


def test_raw_body_not_stored_in_fixture():
    for r in build_captured_overlap_fixture():
        assert "body" not in r
        assert "raw_payload" not in r
        assert set(r.keys()) <= {
            "record_type", "source_id", "title_or_label", "source_url_or_evidence",
            "canonical_url", "published_at_or_observed_at", "body_state_or_signal"}


def test_records_diagnostics_populated():
    disc = discover_overlap(build_captured_overlap_fixture())
    assert disc["total_records"] == 6
    assert disc["canonical_count"] == 6
    assert disc["published_at_count"] == 6
    assert disc["records_by_source"]["gdelt:wire_ap"] == 1


# ── §5 block_reasons 분해 ───────────────────────────────────────────────────────
def test_block_reason_insufficient_records():
    disc = discover_overlap([_rec(source_id="a", title_or_label="x", canonical_url="u")])
    assert disc["block_reasons"] == ["insufficient_records"]


def test_block_reason_non_publishable_role():
    day = "2026-06-22"
    recs = [
        _rec(record_type="community_signal", source_id="a", canonical_url="u1",
             title_or_label="Major port strike halts container shipping operations", published_at_or_observed_at=day),
        _rec(record_type="community_signal", source_id="b", canonical_url="u2",
             title_or_label="Major port strike halts container shipping operations", published_at_or_observed_at=day),
    ]
    disc = discover_overlap(recs)
    assert "non_publishable_role" in disc["block_reasons"]
    assert disc["possible_same_event_pairs"] == 0


def test_block_reason_no_date_bucket_overlap():
    recs = [
        _rec(source_id="a", canonical_url="u1",
             title_or_label="Major port strike halts container shipping operations", published_at_or_observed_at="2026-06-20"),
        _rec(source_id="b", canonical_url="u2",
             title_or_label="Major port strike halts container shipping operations", published_at_or_observed_at="2026-06-25"),
    ]
    disc = discover_overlap(recs)
    assert "no_date_bucket_overlap" in disc["block_reasons"]


def test_block_reason_no_title_overlap():
    day = "2026-06-22"
    recs = [
        _rec(source_id="a", canonical_url="u1",
             title_or_label="Major port strike halts container shipping operations", published_at_or_observed_at=day),
        _rec(source_id="b", canonical_url="u2",
             title_or_label="Record heat wave grips southern region this week today", published_at_or_observed_at=day),
    ]
    disc = discover_overlap(recs)
    assert "no_title_overlap" in disc["block_reasons"]


def test_block_reason_near_match_below_fingerprint():
    """overlap 은 있으나 fingerprint 정확일치 0 → deterministic 사각지대 명시(adjudicator/LLM 영역)."""
    day = "2026-06-22"
    recs = [
        _rec(source_id="a", canonical_url="u1",
             title_or_label="Major port strike halts container shipping operations", published_at_or_observed_at=day),
        _rec(source_id="b", canonical_url="u2",
             title_or_label="Port strike halts container shipping operations nationwide today", published_at_or_observed_at=day),
    ]
    disc = discover_overlap(recs)
    assert disc["fingerprint_overlap_pairs"] == 0
    assert disc["near_match_below_fingerprint_pairs"] == 1
    assert "near_match_below_fingerprint" in disc["block_reasons"]


def test_fingerprint_overlap_no_block():
    day = "2026-06-22"
    title = "Major port strike halts container shipping operations nationwide"
    recs = [
        _rec(source_id="a", canonical_url="u1", title_or_label=title, published_at_or_observed_at=day),
        _rec(source_id="b", canonical_url="u2", title_or_label=title, published_at_or_observed_at=day),
    ]
    disc = discover_overlap(recs)
    assert disc["fingerprint_overlap_pairs"] == 1
    assert disc["block_reasons"] == []


# ── §10 bounded real fetch (11-20) — GDELT parse + 실패 분류(transport/monkeypatch 결정론) ──────
def _gdelt_payload(articles: list[dict]) -> str:
    return json.dumps({"articles": articles})


def test_parse_gdelt_articles_maps_canonical_and_no_body():
    payload = _gdelt_payload([
        {"title": "Port strike halts shipping nationwide", "url": "https://o.test/1",
         "seendate": "20260622T120000Z", "domain": "o.test"},
    ])
    recs = parse_gdelt_articles(payload)
    assert len(recs) == 1
    assert recs[0]["canonical_url"] == "https://o.test/1"
    assert recs[0]["published_at_or_observed_at"] == "20260622T120000Z"
    assert recs[0]["record_type"] == "article_candidate"
    assert "body" not in recs[0] and "raw_payload" not in recs[0]


def test_parse_gdelt_articles_max_records_enforced():
    arts = [{"title": f"t{i} headline words here more", "url": f"https://o.test/{i}",
             "seendate": "20260622T120000Z", "domain": "o.test"} for i in range(50)]
    recs = parse_gdelt_articles(_gdelt_payload(arts), max_records=5)
    assert len(recs) == 5


def test_parse_gdelt_articles_parser_error_returns_none():
    assert parse_gdelt_articles("not json {") is None
    assert parse_gdelt_articles(json.dumps({"no_articles": []})) is None


def test_fetch_gdelt_transport_success():
    payload = _gdelt_payload([
        {"title": "Port strike halts shipping nationwide today", "url": "https://o.test/1",
         "seendate": "20260622T120000Z", "domain": "o.test"},
    ])
    recs, failure = fetch_gdelt_overlap_records(transport=lambda url: payload)
    assert failure is None
    assert len(recs) == 1


def test_fetch_gdelt_real_fetch_disabled_by_default_via_transport():
    """transport 미주입이면 실 network 경로 — 테스트는 항상 transport 주입(network 0)."""
    recs, failure = fetch_gdelt_overlap_records(transport=lambda url: None)
    assert recs == [] and failure == "network_error"


def test_fetch_gdelt_parser_error_classified():
    recs, failure = fetch_gdelt_overlap_records(transport=lambda url: "<html>over query limit</html>")
    assert recs == [] and failure == "parser_error"


def test_fetch_gdelt_no_records_classified():
    recs, failure = fetch_gdelt_overlap_records(transport=lambda url: _gdelt_payload([]))
    assert recs == [] and failure == "no_records"


def test_fetch_gdelt_rate_limited_classified(monkeypatch):
    """실 httpx 경로의 429 → rate_limited 분류(monkeypatch)."""
    class _Resp:
        status_code = 429
        text = "You have exceeded the limit requests"
        headers = {"content-type": "text/plain"}

    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())
    recs, failure = fetch_gdelt_overlap_records()
    assert recs == [] and failure == "rate_limited"


def test_fetch_gdelt_non_json_classified(monkeypatch):
    class _Resp:
        status_code = 200
        text = "plain advisory text"
        headers = {"content-type": "text/html"}

    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())
    recs, failure = fetch_gdelt_overlap_records()
    assert recs == [] and failure == "parser_error"


def test_fetch_gdelt_network_error_classified(monkeypatch):
    import httpx

    def _boom(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx, "get", _boom)
    recs, failure = fetch_gdelt_overlap_records()
    assert recs == [] and failure == "network_error"


def test_fetch_gdelt_then_discover_real_overlap():
    """GDELT 다출처 verbatim wire → fetch→discover 로 실 형태 overlap 검출(transport 결정론)."""
    wire = "Major port strike halts container shipping operations nationwide"
    payload = _gdelt_payload([
        {"title": wire, "url": "https://a.test/1", "seendate": "20260622T120000Z", "domain": "a.test"},
        {"title": wire, "url": "https://b.test/2", "seendate": "20260622T130000Z", "domain": "b.test"},
    ])
    recs, failure = fetch_gdelt_overlap_records(transport=lambda url: payload)
    assert failure is None
    disc = discover_overlap(recs, discovery_mode="source_pair_live", real_fetch=True)
    assert disc["fingerprint_overlap_pairs"] == 1
    assert disc["real_fetch"] is True


# ── §10 Agent schema (36-40) ────────────────────────────────────────────────────
def test_agent_schema_generated_no_llm_no_merge():
    disc = discover_overlap(build_captured_overlap_fixture())
    schema = build_agent_orchestration_schema(disc)
    assert schema["llm_invoked"] is False                    # 37: no LLM
    assert schema["no_public_intelligence_unit"] is True     # 38: no public IU
    assert schema["no_merge_without_gate"] is True           # 39: no merge without gate
    assert "uncertainty" in schema                           # 40: uncertainty present
    assert schema["recommended_source_pairs"]                # 36: schema generated


def test_agent_schema_role_constraints_anchor_only_publishable():
    schema = build_agent_orchestration_schema(discover_overlap(build_captured_overlap_fixture()))
    assert sorted(schema["source_role_constraints"]["merge_anchor_eligible"]) == ["article", "official"]
    assert schema["source_role_constraints"]["reaction_layer_only"] == ["community"]


def test_agent_schema_expected_reason_reflects_granularity():
    # deterministic 검출이 있으면 fingerprint reason.
    det = build_agent_orchestration_schema(discover_overlap(build_captured_overlap_fixture()))
    assert "fingerprint_exact_token_set_match" in det["expected_overlap_reason"]
    # near 만 있으면 adjudicator-zone reason.
    day = "2026-06-22"
    recs = [
        _rec(source_id="a", canonical_url="u1",
             title_or_label="Major port strike halts container shipping operations", published_at_or_observed_at=day),
        _rec(source_id="b", canonical_url="u2",
             title_or_label="Port strike halts container shipping operations nationwide today", published_at_or_observed_at=day),
    ]
    near = build_agent_orchestration_schema(discover_overlap(recs))
    assert "near_match_below_fingerprint" in near["expected_overlap_reason"]


def test_default_near_jaccard_threshold_surfaced():
    disc = discover_overlap(build_captured_overlap_fixture())
    assert disc["near_jaccard_threshold"] == DEFAULT_NEAR_JACCARD
    assert disc["fingerprint_min_tokens"] == 4


# ── discovery→escalation 연결성: deterministic_detectable 은 파이프라인과 동일 fingerprint 에 근거 ──
def test_deterministic_detectable_pair_grounded_in_pipeline_fingerprint():
    """discovery 의 fingerprint_overlap 은 파이프라인 cross-batch identity 와 **동일** semantic_identity_fingerprint
    에 근거 — 즉 deterministic_detectable pair 는 교차배치 시 실제 semantic_cross_batch_candidate 가 된다
    (실 DB 발현은 ADR#56 live-PG replay 테스트가 입증). near pair 는 fingerprint 불일치(deterministic 미검출)."""
    from ingestion.orchestration.cross_source_dedup import semantic_identity_fingerprint
    fx = build_captured_overlap_fixture()
    by_id = {r["source_id"]: r for r in fx}

    def fp(r):
        return semantic_identity_fingerprint(r["title_or_label"], r["published_at_or_observed_at"])

    # verbatim wire pair(deterministic_detectable) → 같은 fingerprint.
    assert fp(by_id["gdelt:wire_ap"]) == fp(by_id["gdelt:wire_reuters"]) is not None
    # paraphrase(adjudicator-zone) → 다른 fingerprint(deterministic 미검출).
    assert fp(by_id["gdelt:wire_ap"]) != fp(by_id["gdelt:local_news"])
    assert fp(by_id["gdelt:wire_ap"]) != fp(by_id["gdelt:biz_news"])


# ════════════════════════════════════════════════════════════════════════════════
# ADR#58 — real overlap acquisition strategy (§10 시나리오 1-32)
# ════════════════════════════════════════════════════════════════════════════════
class _AllowGate:
    """host gate fake — 항상 허용(record 호출 추적)."""

    def __init__(self):
        self.calls = []

    def decide(self, host, *, min_spacing_seconds):
        return type("D", (), {"allowed": True, "reason": None})()

    def record_call(self, host, **kw):
        self.calls.append(host)
        return "rec"


class _DenyGate:
    """host gate fake — 항상 거부(host floor 미경과)."""

    def decide(self, host, *, min_spacing_seconds):
        reason = f"host_min_spacing_not_elapsed:1<{min_spacing_seconds}"
        return type("D", (), {"allowed": False, "reason": reason})()

    def record_call(self, host, **kw):
        return "rec"


# ── A. GDELT / provider handling (1-6) ──────────────────────────────────────────
def test_gdelt_provider_status_reports_policy_and_no_tight_retry():
    """rate_limit_policy(gdelt min/cooldown/retry) 표면화 + no_tight_retry(RATE_LIMITED 는 retry_on 밖)."""
    ps = gdelt_provider_status(query="x", host_gate=_AllowGate(), cooldown=(False, None),
                               policy={"min_interval_seconds": 60})
    assert ps["provider_status"] == "ok"
    assert ps["no_tight_retry"] is True
    assert ps["respect_cooldown"] is True


def test_gdelt_provider_status_cooldown_blocks():
    """영속 429 cooldown 진행 중 → cooldown(provider_429_cooldown)·retry_after 표면화(respect cooldown)."""
    ps = gdelt_provider_status(cooldown=(True, "2026-06-25T10:00:00Z"), policy={"x": 1},
                               host_gate=_AllowGate())
    assert ps["provider_status"] == "cooldown"
    assert ps["provider_block_reason"] == "provider_429_cooldown"
    assert ps["retry_after_or_cooldown"] == "2026-06-25T10:00:00Z"


def test_gdelt_provider_status_host_floor_blocks():
    """다른 루프가 host_min_spacing 안에 쳤으면 host_rate_limited(호출 금지·single source of truth)."""
    ps = gdelt_provider_status(cooldown=(False, None), policy={"x": 1}, host_gate=_DenyGate())
    assert ps["provider_status"] == "host_rate_limited"
    assert "host_min_spacing" in ps["provider_block_reason"]


def test_gdelt_fetch_short_circuits_when_blocked_no_network():
    """provider_status≠ok → network 미시도(transport 미호출)·block_reason 반환(tight-retry/우회 재발 방지)."""
    calls = {"n": 0}

    def transport(url):
        calls["n"] += 1
        return "{}"

    ps = {"provider_status": "cooldown", "provider_block_reason": "provider_429_cooldown"}
    recs, fail = fetch_gdelt_overlap_records(provider_status=ps, transport=transport)
    assert recs == []
    assert fail == "provider_429_cooldown"
    assert calls["n"] == 0   # network 0.


def test_gdelt_fetch_proceeds_when_ok():
    """provider_status=ok → 정상 fetch(transport 호출)."""
    payload = '{"articles":[{"title":"Major port strike halts shipping nationwide today","url":"http://a.test/x","domain":"a.test","seendate":"20260622120000"}]}'
    ps = {"provider_status": "ok", "provider_block_reason": None}
    recs, fail = fetch_gdelt_overlap_records(provider_status=ps, transport=lambda u: payload)
    assert fail is None
    assert len(recs) == 1


def test_gdelt_provider_status_default_path_is_read_only():
    """주입 없이도 read-only preflight(network 0)·policy/host_min_spacing 표면화(실 governance 연결)."""
    ps = gdelt_provider_status(query="world news")
    assert ps["provider"] == "gdelt"
    assert ps["provider_status"] in ("ok", "cooldown", "host_rate_limited")
    assert ps["rate_limit_policy_applied"] is not None    # rate_limit_policy.yaml gdelt 항목 로드.
    assert ps["host_min_spacing_seconds"] == 10


# ── B. RSS allowlist / parse (7-12) ─────────────────────────────────────────────
_RSS_XML = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Major port strike halts container shipping operations nationwide</title>
<link>https://bbc.test/strike</link><pubDate>Mon, 22 Jun 2026 08:00:00 GMT</pubDate></item>
<item><title>Record heat wave grips southern region this week</title>
<link>https://bbc.test/heat</link><pubDate>Mon, 22 Jun 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""
_ATOM_XML = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Port strike halts container shipping operations nationwide today</title>
<link href="https://aljazeera.test/strike"/><updated>2026-06-22T10:00:00Z</updated></entry>
</feed>"""


def test_rss_endpoint_accepts_key_free_rejects_key_required():
    """_rss_endpoint 은 auth=none(key-free)만 endpoint 반환·키 필요 source 는 None(allowlist guard)."""
    from backend.app.tools.source_overlap_discovery import _rss_endpoint
    assert _rss_endpoint("bbc")        # key-free RSS
    assert _rss_endpoint("youtube") is None      # YOUTUBE_API_KEY 필요 → 거부
    assert _rss_endpoint("naver_news_search") is None  # NAVER 키 필요 → 거부


def test_parse_rss_items_rss_and_atom_no_body():
    """RSS(pubDate RFC822→ISO)·Atom(updated) 둘 다 파싱·title/canonical/published 만(본문 미저장)."""
    rss = parse_rss_items(_RSS_XML, source_id="bbc", max_items=10)
    atom = parse_rss_items(_ATOM_XML, source_id="aljazeera", max_items=10)
    assert len(rss) == 2 and len(atom) == 1
    assert rss[0]["published_at_or_observed_at"] == "2026-06-22"     # RFC822 → ISO date.
    assert rss[0]["source_id"] == "rss:bbc"
    assert rss[0]["canonical_url"] == "https://bbc.test/strike"
    # 본문 미저장: record 에 body/raw_payload 키 부재.
    assert "body" not in rss[0] and "raw_payload" not in rss[0]


def test_parse_rss_items_bounded_max():
    """max_items 상한 준수(폭주 차단)."""
    recs = parse_rss_items(_RSS_XML, source_id="bbc", max_items=1)
    assert len(recs) == 1


def test_parse_rss_items_parser_error_returns_none():
    """비-XML/손상 payload → None(parser_error 분류 입력)."""
    assert parse_rss_items("not xml at all", source_id="bbc", max_items=5) is None


def test_fetch_rss_overlap_records_transport_deterministic_multi_source():
    """transport 주입(network 0) 다출처 fetch → cross-source near-match 생성(실 paraphrase overlap 재현)."""
    def transport(sid, endpoint):
        return {"bbc": _RSS_XML, "aljazeera": _ATOM_XML}.get(sid)

    recs, status = fetch_rss_overlap_records(source_ids=["bbc", "aljazeera"], transport=transport)
    assert status == {"bbc": "ok", "aljazeera": "ok"}
    assert len(recs) == 3
    disc = discover_overlap(recs, discovery_mode="rss", real_fetch=True)
    assert disc["adjudicator_zone_pairs"] == 1     # bbc strike × aljazeera strike(paraphrase) → near.
    assert disc["fingerprint_overlap_pairs"] == 0  # 정확 token-set 불일치(deterministic 사각지대).


def test_fetch_rss_overlap_records_failure_classification():
    """source 별 실패 분류: network_error(transport None)·no_endpoint(키 필요)·no_records(빈 feed)."""
    def transport(sid, endpoint):
        return {"bbc": _RSS_XML, "aljazeera": None,
                "the_verge": "<rss><channel></channel></rss>"}.get(sid)

    recs, status = fetch_rss_overlap_records(
        source_ids=["bbc", "aljazeera", "the_verge", "youtube"], transport=transport)
    assert status["bbc"] == "ok"
    assert status["aljazeera"] == "network_error"
    assert status["the_verge"] == "no_records"
    assert status["youtube"] == "no_endpoint"      # 키 필요 → endpoint None.


# ── C. acquisition planning matrix (13-19) ──────────────────────────────────────
def test_acquisition_plan_generates_pairs_and_windows():
    """source_pair_plan/time_window_plan/topic_window_plan + expected_overlap_utility 생성."""
    disc = discover_overlap(build_captured_overlap_fixture())
    plan = build_acquisition_plan(disc, candidate_source_ids=list(_RSS_OVERLAP_SOURCES))
    assert plan["source_pair_plan"]                       # overlap 가능 pair 추천.
    assert {w["window"] for w in plan["time_window_plan"]} == {"1d", "7d"}
    assert "topics" in plan["topic_window_plan"]
    assert plan["expected_overlap_utility"] == "deterministic_detectable"
    assert plan["no_merge_without_gate"] is True


def test_acquisition_plan_pair_carries_utility_and_no_merge():
    """각 source_pair_plan 항목은 expected_overlap_utility·no_merge_without_gate 를 가진다."""
    disc = discover_overlap(build_captured_overlap_fixture())
    plan = build_acquisition_plan(disc)
    for p in plan["source_pair_plan"]:
        assert p["expected_overlap_utility"] in ("deterministic_detectable", "adjudicator_zone_only")
        assert p["no_merge_without_gate"] is True
        assert p["max_records"] >= 1


def test_acquisition_plan_no_overlap_empty_pairs():
    """overlap 0(단일 source) → source_pair_plan 비고 expected_overlap_utility=no_overlap."""
    recs = [_rec(source_id="rss:bbc", canonical_url="http://a", title_or_label="solo headline only here",
                 published_at_or_observed_at="2026-06-22")]
    disc = discover_overlap(recs)
    plan = build_acquisition_plan(disc)
    assert plan["source_pair_plan"] == []
    assert plan["expected_overlap_utility"] == "no_overlap"


def test_agent_schema_expected_agent_utility_and_reviewer_exportable():
    """agent schema 가 expected_agent_utility·reviewer_candidate_exportable(near 존재 시 True) 표면화."""
    disc = discover_overlap(build_captured_overlap_fixture())
    schema = build_agent_orchestration_schema(disc)
    assert schema["reviewer_candidate_exportable"] is True   # adjudicator_zone 5 > 0.
    assert "deterministic" in schema["expected_agent_utility"]


# ── D. near-match reviewer candidate route (20-24·핵심) ──────────────────────────
def test_near_match_reviewer_candidates_exported():
    """near_match_below_fingerprint → reviewer candidate worksheet 행 export(병합 아님·hint)."""
    disc = discover_overlap(build_captured_overlap_fixture())
    cands = build_near_match_reviewer_candidates(disc)
    assert len(cands) == 5                                   # paraphrase pairs.
    c = cands[0]
    assert c["label"] == "unlabeled"
    assert {"title_left", "title_right", "observed_at_left", "observed_at_right",
            "canonical_url_left", "canonical_url_right"} <= set(c)


def test_near_match_candidate_no_predicted_status_no_llm():
    """predicted_status/score/reason-verdict 미포함(bias 차단)·LLM 호출 0."""
    disc = discover_overlap(build_captured_overlap_fixture())
    cands = build_near_match_reviewer_candidates(disc)
    for c in cands:
        assert "predicted_status" not in c
        assert "score" not in c
        assert "verdict" not in c


def test_near_match_candidate_no_merge_without_gold():
    """gold/MERGE_GATE 없이 병합·같은 사건 단정 금지(no_merge_without_gold 불변)."""
    disc = discover_overlap(build_captured_overlap_fixture())
    cands = build_near_match_reviewer_candidates(disc)
    assert all(c["no_merge_without_gold"] is True for c in cands)
    assert all("near_match_below_fingerprint" in c["risk_tags"] for c in cands)


def test_near_match_candidate_role_guard_excludes_community():
    """publishable×publishable 만 reviewer 후보 — community/market/catalog anchor 금지."""
    recs = [
        _rec(record_type="community_signal", source_id="hn", canonical_url="http://a",
             title_or_label="Major port strike halts container shipping operations nationwide",
             published_at_or_observed_at="2026-06-22"),
        _rec(record_type="community_signal", source_id="dc", canonical_url="http://b",
             title_or_label="Major port strike halts container shipping operations today",
             published_at_or_observed_at="2026-06-22"),
    ]
    disc = discover_overlap(recs)
    # community pair 는 both_pub 필터로 near 자체가 0 → reviewer 후보 0.
    assert build_near_match_reviewer_candidates(disc) == []


def test_assemble_acquisition_report_required_fields():
    """§4 필수 report fields 전부 존재·no_merge_without_gate·llm_invoked=False 불변."""
    disc = discover_overlap(build_captured_overlap_fixture())
    schema = build_agent_orchestration_schema(disc)
    plan = build_acquisition_plan(disc)
    cands = build_near_match_reviewer_candidates(disc)
    ps = gdelt_provider_status(cooldown=(False, None), policy={"min_interval_seconds": 60},
                               host_gate=_AllowGate())
    report = assemble_acquisition_report(disc, provider_status=ps, plan=plan,
                                         reviewer_candidates=cands, schema=schema)
    for k in ("provider_status", "rate_limit_policy_applied", "source_pair_plan",
              "topic_window_plan", "time_window_plan", "expected_overlap_utility",
              "expected_agent_utility", "near_match_candidate_count",
              "deterministic_detectable_count", "adjudicator_zone_count",
              "reviewer_candidate_exportable", "no_merge_without_gate", "next_fetch_plan"):
        assert k in report
    assert report["no_merge_without_gate"] is True
    assert report["llm_invoked"] is False
    assert report["near_match_candidate_count"] == 5
    assert report["adjudicator_zone_count"] == 5


# ── 감사 정정(adversarial MEDIUM-1·code-review [1][2]) 회귀 잠금 ──────────────────
def test_near_match_candidate_classifies_to_paraphrase_bucket():
    """near-match candidate 가 다운스트림 `assign_candidate_bucket` 에서 `paraphrase` bucket 으로 분류(other 미분류 회피).

    adversarial MEDIUM-1: `risk_tags` 에 정확 토큰 `paraphrase` 가 있어야 `build_labeling_packet` 이 정상 분류한다.
    이것이 "EvalPair/packet 스키마 정합·소비 가능" claim 을 코드로 참이 되게 한다."""
    from backend.app.services.identity_human_labeling import assign_candidate_bucket
    disc = discover_overlap(build_captured_overlap_fixture())
    cands = build_near_match_reviewer_candidates(disc)
    assert cands
    for c in cands:
        assert "paraphrase" in c["risk_tags"]      # 다운스트림 bucket 토큰.
        bucket = assign_candidate_bucket(
            predicted_status="", reason=c["reason"], language=c["language"],
            source_type_left=c["source_type_left"], source_type_right=c["source_type_right"],
            risk_tags=tuple(c["risk_tags"]))
        assert bucket == "paraphrase"              # other_candidate 로 떨어지지 않음.


def test_parse_rss_items_atom_prefers_alternate_link():
    """code-review [1]: Atom 다중 <link>(rel=self 우선) → 기사 URL(rel=alternate) canonical 캡처(self 오캡처 방지)."""
    atom = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
    <entry><title>Port strike halts shipping nationwide today</title>
    <link rel="self" href="https://self.example/feed"/>
    <link rel="alternate" href="https://outlet.example/article/strike"/>
    <updated>2026-06-22T10:00:00Z</updated></entry></feed>"""
    recs = parse_rss_items(atom, source_id="the_verge", max_items=5)
    assert len(recs) == 1
    assert recs[0]["canonical_url"] == "https://outlet.example/article/strike"   # self 아님.


def test_gdelt_provider_status_malformed_cooldown_safe():
    """code-review [2]: cooldown 이 2-튜플이 아니어도 ValueError 없이 안전(미주입으로 간주)."""
    for bad in [(), (True,), "nope", (1, 2, 3)]:
        ps = gdelt_provider_status(cooldown=bad, policy={"x": 1}, host_gate=_AllowGate())
        assert ps["provider_status"] in ("ok", "cooldown", "host_rate_limited")


# ── ADR#59 hard-negative band 포착(near 미만 [floor,near) overlap → different-event lean) ──────────────
def _hard_neg_records() -> list[dict]:
    """publishable·same-date·cross-URL·near 미만 overlap(jaccard 0.3/0.4) — different-event lean 음성 후보."""
    day = "2026-06-22"
    return [
        _rec(source_id="news_a", canonical_url="https://a.test/summit",
             title_or_label="Global summit on climate policy opens in Geneva today",
             published_at_or_observed_at=day),
        _rec(source_id="news_b", canonical_url="https://b.test/summit",
             title_or_label="Regional summit on trade policy opens in Vienna",
             published_at_or_observed_at=day),
    ]


def test_hard_negative_band_captured_below_near():
    """[_HARD_NEG_FLOOR,near) overlap 은 hard_negative_pairs 로 분리 포착(possible_same_event 미가산·near 아님)."""
    disc = discover_overlap(_hard_neg_records())
    assert _HARD_NEG_FLOOR == 0.2 and DEFAULT_NEAR_JACCARD == 0.5
    assert disc["hard_negative_band_pairs"] == 1
    assert len(disc["hard_negative_pairs"]) == 1
    assert disc["near_match_below_fingerprint_pairs"] == 0   # near 미만.
    assert disc["possible_same_event_pairs"] == 0            # 같은 사건 후보 아님(possible 미가산).
    p = disc["hard_negative_pairs"][0]
    assert p["pair_id"].startswith("hn:")                    # near("nm:")와 분리된 prefix.
    assert p["source_role_compatible"] is True
    assert _HARD_NEG_FLOOR <= p["title_token_jaccard"] < DEFAULT_NEAR_JACCARD


def test_hard_negative_reviewer_candidates_risk_tag_and_no_predicted_status():
    """hard-negative 후보 → risk_tags=['hard_negative']·predicted_status 미포함·no_merge_without_gold."""
    disc = discover_overlap(_hard_neg_records())
    cands = build_hard_negative_reviewer_candidates(disc)
    assert len(cands) == 1
    c = cands[0]
    assert c["risk_tags"] == ["hard_negative"]
    assert c["label"] == "unlabeled"
    assert "predicted_status" not in c and "score" not in c   # bias 차단(near 후보와 동일 계약).
    assert c["no_merge_without_gold"] is True
    from backend.app.services.identity_human_labeling import assign_candidate_bucket
    bucket = assign_candidate_bucket(
        predicted_status="", reason=c["reason"], language=c["language"],
        source_type_left=c["source_type_left"], source_type_right=c["source_type_right"],
        risk_tags=tuple(c["risk_tags"]))
    assert bucket == "hard_negative"                          # 음성 floor bucket(other 미분류 회피).


def test_hard_negative_band_excludes_below_floor():
    """floor(0.2) 미만 overlap 은 hard_negative_pairs 에도 미포착(잡음 차단)."""
    day = "2026-06-22"
    recs = [
        _rec(source_id="a", canonical_url="https://a.test/1",
             title_or_label="Major port strike halts container shipping nationwide",
             published_at_or_observed_at=day),
        _rec(source_id="b", canonical_url="https://b.test/2",
             title_or_label="Sunny weather forecast brings clear skies weekend",
             published_at_or_observed_at=day),
    ]
    disc = discover_overlap(recs)
    assert disc["hard_negative_band_pairs"] == 0
    assert disc["near_match_below_fingerprint_pairs"] == 0


def test_hard_negative_community_anchor_rejected():
    """community anchor 는 hard-negative 후보에서도 거부(source role guard·publishable core 만)."""
    day = "2026-06-22"
    recs = [
        _rec(record_type="community_signal", source_id="forum_a", canonical_url="https://f.test/1",
             title_or_label="Global summit on climate policy opens in Geneva today",
             published_at_or_observed_at=day),
        _rec(source_id="news_b", canonical_url="https://b.test/2",
             title_or_label="Regional summit on trade policy opens in Vienna",
             published_at_or_observed_at=day),
    ]
    disc = discover_overlap(recs)
    # community×article 은 both_pub=False → pairwise 진입 자체가 안 됨(hard-neg 포착 0).
    assert disc["hard_negative_band_pairs"] == 0
    assert build_hard_negative_reviewer_candidates(disc) == []

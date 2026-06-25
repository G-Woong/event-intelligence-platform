"""ADR#57 — source overlap discovery 테스트(§10 시나리오 1-20·36-40).

write-free·no-merge·no-DB 계약과 두 입도(fingerprint 정확일치 vs near_match_below_fingerprint) 분해,
GDELT bounded fetch 실패 분류, agent orchestration schema(LLM 호출 0·merge 불가)를 잠근다.
"""
from __future__ import annotations

import json

from backend.app.tools.source_overlap_discovery import (
    DEFAULT_NEAR_JACCARD,
    _rec,
    build_agent_orchestration_schema,
    build_captured_overlap_fixture,
    discover_overlap,
    fetch_gdelt_overlap_records,
    parse_gdelt_articles,
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

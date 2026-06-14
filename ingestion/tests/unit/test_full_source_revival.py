"""Phase E-2: full source revival — plan/exclusion/final_status/root-cause (네트워크 0).

live 호출은 주입형 ``probe_fn``으로 격리한다(fake probe → fixture artifact). 실제 네트워크
없이 per-source 파이프라인(probe→audit→body fetch→structured signal→eventqueue→final_status)을
결정적으로 검증한다.
"""
from __future__ import annotations

from pathlib import Path

from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult
from ingestion.orchestration.audit_trace import TraceRecorder
from ingestion.orchestration.full_source_revival import (
    ALIVE_STATUSES,
    RevivalEvidence,
    build_revival_plan,
    classify_final_status,
    summarize_revival,
    SourceRevivalResult,
)
from ingestion.orchestration.source_profile import SourceProfile
from ingestion.tools.run_source_body_audit import _exclusion, _revive_one_source

_FIX = Path(__file__).parent.parent / "fixtures" / "orchestration"


def _fake_probe(artifact_path: Path | None, status: str = "LIVE_SUCCESS"):
    def probe(source_id, max_items=1, force=False):
        ap = ArtifactPaths(extracted_payload=str(artifact_path) if artifact_path else None)
        return CollectionProbeResult(source_id=source_id, status=status, items_found=2,
                                     artifact_paths=ap)
    return probe


def _profile(**kw) -> SourceProfile:
    base = dict(source_id="src", enabled=True, purpose="news", source_group="news")
    base.update(kw)
    return SourceProfile(**base)


# ── exclusion scope (behavior 1) ──
def test_excluded_source_is_detected_by_policy_reason():
    p = _profile(source_id="dcinside", source_group="community",
                 skip_reason="robots_or_policy_block")
    excluded, reason = _exclusion(p)
    assert excluded and reason == "robots_or_policy_block"


def test_disabled_source_is_excluded():
    p = _profile(source_id="reuters", enabled=False, skip_reason="paywall_no_bypass")
    assert _exclusion(p)[0] is True


def test_enabled_keyless_source_is_target():
    p = _profile(source_id="yna")
    assert _exclusion(p) == (False, None)


# ── plan (behavior 2, 3) ──
def test_revival_plan_per_group_expected_alive_type():
    assert build_revival_plan(source_id="yna", source_group="news", purpose="news",
                              enabled=True, requires_api_key=False, api_key_ready=True,
                              excluded=False, excluded_reason=None).expected_alive_type == "ARTICLE_BODY_ALIVE"
    assert build_revival_plan(source_id="binance_market", source_group="market", purpose="numeric",
                              enabled=True, requires_api_key=False, api_key_ready=True,
                              excluded=False, excluded_reason=None).expected_alive_type == "STRUCTURED_SIGNAL_ALIVE"
    assert build_revival_plan(source_id="sec_edgar", source_group="official", purpose="regulatory",
                              enabled=True, requires_api_key=False, api_key_ready=True,
                              excluded=False, excluded_reason=None).expected_alive_type == "OFFICIAL_RECORD_ALIVE"


def test_strategy_ladder_differs_by_group():
    news = build_revival_plan(source_id="a", source_group="news", purpose="news", enabled=True,
                              requires_api_key=False, api_key_ready=True, excluded=False,
                              excluded_reason=None).strategy_ladder
    market = build_revival_plan(source_id="b", source_group="market", purpose="numeric", enabled=True,
                                requires_api_key=False, api_key_ready=True, excluded=False,
                                excluded_reason=None).strategy_ladder
    assert news != market
    assert "policy_safe_body_fetch" in news
    assert "numeric_payload_adapter" in market


# ── per-source live pipeline via fake probe (behaviors 4,5,6,11,16,19) ──
def test_revive_decomposes_and_classifies_community(tmp_path):
    rec = TraceRecorder("t", jsonl_path=tmp_path / "trace.jsonl", console=False)
    p = _profile(source_id="hacker_news", source_group="community", purpose="community",
                 confirmation_policy="unconfirmed_until_corroborated")
    one = _revive_one_source(
        p, readiness=None, outputs_dir=tmp_path, recorder=rec,
        probe_fn=_fake_probe(_FIX / "hn_items.json"),
        allow_body_fetch=False, max_items=2)
    assert one["audit"].candidate_count == 2
    assert one["result"].final_status == "COMMUNITY_SIGNAL_ALIVE"
    assert one["live_attempted"] is True
    assert one["result"].attempts and one["result"].attempts[0].strategy_name == "collection_probe"


def test_revive_rate_limited_no_retry_storm(tmp_path):
    rec = TraceRecorder("t", jsonl_path=tmp_path / "trace.jsonl", console=False)
    p = _profile(source_id="gdelt", source_group="official", purpose="news")
    one = _revive_one_source(
        p, readiness=None, outputs_dir=tmp_path, recorder=rec,
        probe_fn=_fake_probe(None, status="RATE_LIMITED"),
        allow_body_fetch=False, max_items=1)
    assert one["result"].final_status == "EXTERNAL_RATE_LIMITED"
    # 단일 시도만 — rate-limit 후 무리한 재시도 없음
    assert len(one["result"].attempts) == 1


def test_revive_excluded_source_not_called(tmp_path):
    rec = TraceRecorder("t", jsonl_path=tmp_path / "trace.jsonl", console=False)
    p = _profile(source_id="dcinside", source_group="community",
                 skip_reason="robots_or_policy_block")
    called = {"n": 0}

    def probe(*a, **k):
        called["n"] += 1
        return CollectionProbeResult(source_id="dcinside", status="LIVE_SUCCESS")

    one = _revive_one_source(p, readiness=None, outputs_dir=tmp_path, recorder=rec,
                             probe_fn=probe, allow_body_fetch=True, max_items=1)
    assert called["n"] == 0  # 우회 없음 — 호출 안 함
    assert one["result"].final_status == "POLICY_BLOCKED_NO_BYPASS"
    assert one["live_attempted"] is False


# ── final_status / root_cause taxonomy (behaviors 18, 19) ──
def _evid(**kw):
    return RevivalEvidence(**kw)


def test_classify_always_returns_status_and_nonempty_for_non_alive():
    cases = [
        dict(source_group="news", excluded=False, excluded_reason=None,
             api_readiness_status="missing", probe_status="NOT_ATTEMPTED",
             artifact_exists=False, evidence=_evid()),
        dict(source_group="news", excluded=False, excluded_reason=None,
             api_readiness_status="not_required", probe_status="LIVE_SUCCESS",
             artifact_exists=True, evidence=_evid(candidate_count=0, parser_gap_reason="schema_unknown")),
        dict(source_group="official", excluded=False, excluded_reason=None,
             api_readiness_status="not_required", probe_status="LIVE_SUCCESS",
             artifact_exists=True, evidence=_evid(candidate_count=3, title_present=3, url_present=3)),
        dict(source_group="market", excluded=False, excluded_reason=None,
             api_readiness_status="not_required", probe_status="LIVE_SUCCESS",
             artifact_exists=True, evidence=_evid(candidate_count=10, structured_signal=10)),
    ]
    for c in cases:
        status, causes, action = classify_final_status(**c)
        assert status, "final_status must always exist"
        assert action
        if status not in ALIVE_STATUSES:
            assert causes, f"non-alive {status} must carry root cause"


def test_classify_news_snippet_only_is_needs_body_fetch():
    status, causes, _ = classify_final_status(
        source_group="news", excluded=False, excluded_reason=None,
        api_readiness_status="not_required", probe_status="LIVE_SUCCESS",
        artifact_exists=True,
        evidence=_evid(candidate_count=5, title_present=5, url_present=5, snippet_only=5))
    assert status == "NEEDS_BODY_FETCH_UNRESOLVED"
    assert "BODY_FETCH_REQUIRED" in causes


def test_official_record_needs_anchor_url_or_date():
    # F1 루프홀 차단: title만 있고 url·시간이 모두 없으면 OFFICIAL_RECORD_ALIVE 자격 미달
    status, causes, _ = classify_final_status(
        source_group="domain", excluded=False, excluded_reason=None,
        api_readiness_status="not_required", probe_status="LIVE_SUCCESS",
        artifact_exists=True,
        evidence=_evid(candidate_count=3, title_present=3, url_present=0, published_present=0))
    assert status == "NEEDS_PARSER_UNRESOLVED"
    assert "NO_STABLE_URL" in causes and "NO_TIMESTAMP" in causes


def test_official_record_alive_with_url_anchor_but_no_date_is_degraded():
    status, causes, _ = classify_final_status(
        source_group="official", excluded=False, excluded_reason=None,
        api_readiness_status="not_required", probe_status="LIVE_SUCCESS",
        artifact_exists=True,
        evidence=_evid(candidate_count=3, title_present=3, url_present=3, published_present=0))
    assert status == "OFFICIAL_RECORD_ALIVE"
    assert causes == ("NO_TIMESTAMP",)  # URL anchor 보유 → alive이되 degraded


def test_summarize_splits_fully_vs_degraded_alive():
    full = SourceRevivalResult(source_id="a", source_group="official",
                               expected_alive_type="OFFICIAL_RECORD_ALIVE",
                               final_status="OFFICIAL_RECORD_ALIVE", root_causes=(),
                               next_action="ready")
    degraded = SourceRevivalResult(source_id="b", source_group="official",
                                   expected_alive_type="OFFICIAL_RECORD_ALIVE",
                                   final_status="OFFICIAL_RECORD_ALIVE",
                                   root_causes=("NO_TIMESTAMP",), next_action="ready")
    s = summarize_revival([full, degraded])
    assert s["fully_alive"] == 1
    assert s["degraded_alive"] == 1
    assert "b" in s["degraded_sources"]


def test_classify_key_missing_blocks_without_call():
    status, causes, _ = classify_final_status(
        source_group="market", excluded=False, excluded_reason=None,
        api_readiness_status="missing", probe_status="NOT_ATTEMPTED",
        artifact_exists=False, evidence=_evid())
    assert status == "BLOCKED_ENV_KEY"
    assert "KEY_MISSING" in causes


# ── summary (behavior 19, complete-eligibility) ──
def test_summarize_revival_complete_eligibility():
    alive = SourceRevivalResult(source_id="a", source_group="news",
                                expected_alive_type="ARTICLE_BODY_ALIVE",
                                final_status="ARTICLE_BODY_ALIVE", root_causes=(),
                                next_action="ready")
    unresolved = SourceRevivalResult(source_id="b", source_group="news",
                                     expected_alive_type="ARTICLE_BODY_ALIVE",
                                     final_status="NEEDS_BODY_FETCH_UNRESOLVED",
                                     root_causes=("BODY_FETCH_REQUIRED",), next_action="fetch")
    s_ok = summarize_revival([alive])
    assert s_ok["complete_eligible"] is True
    s_bad = summarize_revival([alive, unresolved])
    assert s_bad["complete_eligible"] is False
    assert "b" in s_bad["unresolved_sources"]

"""Phase E-2: StrategyAttemptRecord — group별 ladder + 시도 기록의 정직성."""
from __future__ import annotations

from pathlib import Path

from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult
from ingestion.orchestration.audit_trace import TraceRecorder
from ingestion.orchestration.full_source_revival import (
    STRATEGY_LADDER_BY_GROUP,
    build_revival_plan,
)
from ingestion.orchestration.source_profile import SourceProfile
from ingestion.tools.run_source_body_audit import _revive_one_source

_FIX = Path(__file__).parent.parent / "fixtures" / "orchestration"


def test_ladders_distinct_across_all_groups():
    ladders = {g: STRATEGY_LADDER_BY_GROUP[g] for g in
               ("news", "community", "search", "official", "market", "trend", "domain")}
    # 기사형은 본문 fetch 단계, 구조형은 numeric adapter 단계를 가진다
    assert "policy_safe_body_fetch" in ladders["news"]
    assert "numeric_payload_adapter" in ladders["market"]
    assert "json_adapter" in ladders["official"]
    assert "approved_api_or_feed_only" in ladders["community"]


def test_plan_max_attempts_default_four():
    plan = build_revival_plan(source_id="x", source_group="news", purpose="news",
                              enabled=True, requires_api_key=False, api_key_ready=True,
                              excluded=False, excluded_reason=None)
    assert plan.max_attempts == 4


def test_attempt_record_captures_probe_outcome(tmp_path):
    rec = TraceRecorder("t", jsonl_path=tmp_path / "trace.jsonl", console=False)
    p = SourceProfile(source_id="hacker_news", source_group="community",
                      purpose="community",
                      confirmation_policy="unconfirmed_until_corroborated")

    def probe(source_id, max_items=1, force=False):
        return CollectionProbeResult(
            source_id=source_id, status="LIVE_SUCCESS", items_found=2,
            artifact_paths=ArtifactPaths(extracted_payload=str(_FIX / "hn_items.json")))

    one = _revive_one_source(p, readiness=None, outputs_dir=tmp_path, recorder=rec,
                             probe_fn=probe, allow_body_fetch=False, max_items=2)
    rec0 = one["result"].attempts[0]
    assert rec0.strategy_name == "collection_probe"
    assert rec0.status == "SUCCESS"
    assert rec0.items_found == 2
    assert rec0.attempted is True


def test_attempt_record_marks_non_success_status(tmp_path):
    rec = TraceRecorder("t", jsonl_path=tmp_path / "trace.jsonl", console=False)
    p = SourceProfile(source_id="gdelt", source_group="official", purpose="news")

    def probe(source_id, max_items=1, force=False):
        return CollectionProbeResult(source_id=source_id, status="RATE_LIMITED",
                                     error_category="RATE_LIMITED")

    one = _revive_one_source(p, readiness=None, outputs_dir=tmp_path, recorder=rec,
                             probe_fn=probe, allow_body_fetch=False, max_items=1)
    assert one["result"].attempts[0].status == "RATE_LIMITED"
    assert one["result"].attempts[0].error_type == "RATE_LIMITED"

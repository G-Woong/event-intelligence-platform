"""Phase D-P: SourceProfile → ... → QualityPreGate 파이프라인 연결 검증.

개별 모듈이 아니라 **끊김 없이 연결되는지**를 fake/real artifact로 검증한다.
"""
from __future__ import annotations

from pathlib import Path

from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult
from ingestion.orchestration.api_readiness import audit_api_key_readiness
from ingestion.orchestration.event_seed import to_event_seed
from ingestion.orchestration.quality_pre_gate import evaluate_pre_gate
from ingestion.orchestration.run_orchestration_cycle import run_cycle
from ingestion.orchestration.seed_expansion import expand_seed_to_article_candidates
from ingestion.orchestration.source_profile import SourceProfile, load_source_profiles
from ingestion.orchestration.strategy_router import decide_strategy
from ingestion.pipeline.event_queue import EventQueue

_FIX = Path(__file__).parent.parent / "fixtures" / "orchestration"


def _seed_with_artifact(artifact_path: str, *, source_id="gdelt",
                        status="LIVE_SUCCESS", policy=None) -> dict:
    return {
        "source_id": source_id,
        "title_or_keyword": source_id,
        "source_url": "https://endpoint.test/feed",
        "timestamp": "2026-06-14T00:00:00Z",
        "collection_status": status,
        "raw_artifact_path": artifact_path,
        "extracted_text_ref": None,
        "confirmation_policy": policy,
    }


def test_full_chain_profile_to_pre_gate(tmp_path):
    # 1) SourceProfile → StrategyDecision
    profile = SourceProfile(
        source_id="gdelt", purpose="regulatory", source_group="official",
        live_eligible="true", confirmation_policy="evidence_required",
    )
    decision = decide_strategy(profile)
    assert decision.source_id == "gdelt"

    # 2) readiness (키 불필요 → not_required, smoke 가능)
    readiness = audit_api_key_readiness([profile])
    assert readiness[0].readiness_status in ("not_required", "ready", "unknown")

    # 3) seed → artifact → candidate 분해
    art = tmp_path / "gdelt.json"
    art.write_text((_FIX / "gdelt_minimal.json").read_text(encoding="utf-8"),
                   encoding="utf-8")
    seed = _seed_with_artifact(str(art), policy=decision.confirmation_policy)
    report = expand_seed_to_article_candidates(seed)
    assert report.candidates
    assert report.fallback_used is False

    # 4) candidate → body_state/canonical → pre_gate
    results = [
        evaluate_pre_gate(c, purpose=profile.purpose,
                          source_group=profile.source_group)
        for c in report.candidates
    ]
    assert all(r.decision in ("pass", "hold", "reject") for r in results)
    assert all(r.duplicate_key is not None for r in results)  # canonical 존재 → 키 생성


def test_parser_error_does_not_kill_pipeline(tmp_path):
    art = tmp_path / "bad.json"
    art.write_text("{not valid json", encoding="utf-8")
    seed = _seed_with_artifact(str(art))
    report = expand_seed_to_article_candidates(seed)
    # 깨진 artifact라도 source-level fallback으로 사건 보존(예외 없음)
    assert report.fallback_used is True
    assert report.source_level_fallback is True
    assert report.candidates
    r = evaluate_pre_gate(report.candidates[0], purpose="news", source_group="news")
    assert r.decision in ("pass", "hold", "reject")


def test_redis_url_present_but_explicit_jsonl_queue_is_safe(tmp_path, monkeypatch):
    # .env에 REDIS_URL이 있어도 명시적 JSONL 큐는 Redis stub을 피한다(운영 리스크 방어)
    monkeypatch.setenv("REDIS_URL", "redis://should-not-be-used:6379")
    queue = EventQueue(redis_url="", fallback_dir=tmp_path)

    def fake_probe(source_id, *, query=None, max_items=5, force=False):
        return CollectionProbeResult(
            source_id=source_id, status="LIVE_SUCCESS", items_found=3,
            artifact_paths=ArtifactPaths(raw_payload=None),
        )

    report = run_cycle(sources=["gdelt"], queue=queue, probe_fn=fake_probe)
    assert report.items_enqueued == 1  # NotImplementedError 없이 적재
    assert report.sources_failed == 0


def test_community_confirmation_preserved_end_to_end(tmp_path):
    profile = SourceProfile(
        source_id="hacker_news", purpose="community", source_group="community",
        is_community=True, confirmation_policy="standard", live_eligible="true",
    )
    # community standard → unconfirmed로 보정
    decision = decide_strategy(profile)
    assert decision.confirmation_policy == "unconfirmed_until_corroborated"

    art = tmp_path / "hn.json"
    art.write_text((_FIX / "generic_articles.json").read_text(encoding="utf-8"),
                   encoding="utf-8")
    seed = _seed_with_artifact(str(art), source_id="hacker_news",
                               policy=decision.confirmation_policy)
    report = expand_seed_to_article_candidates(seed)
    assert all(
        c.confirmation_policy == "unconfirmed_until_corroborated"
        for c in report.candidates
    )


def test_full_source_profile_coverage_still_connects():
    profiles = load_source_profiles()
    assert len(profiles) == 57
    # 모든 프로필이 끊김 없이 decision + readiness를 산출한다(예외 0)
    decisions = [decide_strategy(p) for p in profiles]
    assert len(decisions) == 57
    readiness = audit_api_key_readiness(profiles)
    assert len(readiness) == 57
    # to_event_seed도 모든 소스에서 동작(없는 값은 None으로 정직하게)
    sample = CollectionProbeResult(
        source_id="gdelt", status="LIVE_SUCCESS", items_found=1,
        artifact_paths=ArtifactPaths(),
    )
    seed = to_event_seed(sample, query=None, cycle_id="c", timestamp="t")
    assert seed["source_id"] == "gdelt"
    assert seed["canonical_url"] is None

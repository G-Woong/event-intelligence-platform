"""Phase D-2/D-4: source-level seed → article-level candidate expansion 통합."""
from __future__ import annotations

import json
from pathlib import Path

from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult
from ingestion.orchestration.run_orchestration_cycle import run_cycle
from ingestion.orchestration.seed_expansion import expand_seed_to_article_candidates
from ingestion.orchestration.source_profile import SourceProfile

_FIX = Path(__file__).parent.parent / "fixtures" / "orchestration"


def _seed(artifact_path, status="LIVE_SUCCESS", **kw):
    base = {
        "source_id": "gdelt",
        "collection_status": status,
        "raw_artifact_path": str(artifact_path) if artifact_path else None,
        "title_or_keyword": "keyword",
        "source_url": "https://gdelt.test/feed",
        "timestamp": "2026-06-14T00:00:00Z",
    }
    base.update(kw)
    return base


def test_seed_expands_to_article_candidates():
    report = expand_seed_to_article_candidates(_seed(_FIX / "gdelt_minimal.json"))
    assert report.parser_name == "gdelt"
    assert report.fallback_used is False
    assert len(report.candidates) == 2
    assert report.candidates[0].source_url == "https://example-news.test/world/a1?utm_source=gdelt"
    assert report.candidates[0].canonical_url == "https://example-news.test/world/a1"


def test_no_artifact_uses_source_level_fallback():
    report = expand_seed_to_article_candidates(_seed(None))
    assert report.source_level_fallback is True
    assert report.fallback_used is True
    assert len(report.candidates) == 1
    assert report.candidates[0].parser_name == "source_level_fallback"
    assert report.candidates[0].title == "keyword"
    assert report.errors == ["no_artifact_path"]


def test_missing_artifact_file_falls_back(tmp_path):
    report = expand_seed_to_article_candidates(_seed(tmp_path / "absent.json"))
    assert report.source_level_fallback is True
    assert report.errors == ["artifact_file_missing"]


def test_malformed_artifact_falls_back_with_errors():
    report = expand_seed_to_article_candidates(_seed(_FIX / "malformed.json"))
    assert report.source_level_fallback is True
    assert report.candidates[0].parser_name == "source_level_fallback"
    assert report.errors  # parse error 보존


def test_non_success_seed_not_expanded():
    report = expand_seed_to_article_candidates(_seed(_FIX / "gdelt_minimal.json",
                                                     status="RATE_LIMITED"))
    assert report.candidates == []
    assert report.errors == ["non_success_seed_not_expanded"]


def test_community_confirmation_policy_preserved(tmp_path):
    art = tmp_path / "hn.json"
    art.write_text(json.dumps([{"title": "HN", "url": "https://hn.test/1"}]), encoding="utf-8")
    seed = _seed(art, source_id="hacker_news")
    report = expand_seed_to_article_candidates(
        seed, confirmation_policy="unconfirmed_until_corroborated"
    )
    assert all(
        c.confirmation_policy == "unconfirmed_until_corroborated"
        for c in report.candidates
    )


def test_run_cycle_expand_articles_attaches_count():
    """run_cycle expand_articles=True → outcome.article_candidates 채워짐(큐 계약 불변)."""
    class FakeQueue:
        def __init__(self):
            self.items = []

        def enqueue(self, item):
            self.items.append(item)
            return f"id-{len(self.items)}"

    def probe(sid, **kw):
        return CollectionProbeResult(
            source_id=sid, status="LIVE_SUCCESS", items_found=2,
            artifact_paths=ArtifactPaths(raw_payload=str(_FIX / "gdelt_minimal.json")),
        )

    q = FakeQueue()
    profiles = [SourceProfile(source_id="gdelt", requires_api_key=False,
                              confirmation_policy="evidence_required")]
    report = run_cycle(profiles=profiles, queue=q, probe_fn=probe, expand_articles=True)
    outcome = report.outcomes[0]
    assert outcome.enqueued is True
    assert outcome.article_candidates == 2
    # 큐에는 여전히 source-level seed 1건만(계약 불변)
    assert len(q.items) == 1


def test_run_cycle_without_expand_keeps_none():
    class FakeQueue:
        def enqueue(self, item):
            return "id-0"

    def probe(sid, **kw):
        return CollectionProbeResult(source_id=sid, status="LIVE_SUCCESS", items_found=1)

    profiles = [SourceProfile(source_id="gdelt", requires_api_key=False)]
    report = run_cycle(profiles=profiles, queue=FakeQueue(), probe_fn=probe)
    assert report.outcomes[0].article_candidates is None

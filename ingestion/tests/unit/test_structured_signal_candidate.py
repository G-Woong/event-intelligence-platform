"""Phase E-2: StructuredSignalCandidate — numeric/market 신호를 article과 섞지 않는다."""
from __future__ import annotations

from ingestion.orchestration.article_candidate import ArticleCandidate
from ingestion.orchestration.full_source_revival import to_structured_signal_candidates


def _numeric(**kw):
    base = dict(source_id="binance_market", numeric_payload_exempt=True,
                title="BTCUSDT", raw_artifact_path="/p/raw.json")
    base.update(kw)
    return ArticleCandidate(**base)


def _article():
    return ArticleCandidate(source_id="yna", title="기사", source_url="https://x/a",
                            body_text="본문", numeric_payload_exempt=False)


def test_numeric_candidate_becomes_structured_signal():
    sigs = to_structured_signal_candidates(
        [_numeric()], source_id="binance_market", source_group="market", purpose="numeric")
    assert len(sigs) == 1
    s = sigs[0]
    assert s.signal_type == "numeric"
    assert s.title == "BTCUSDT"
    assert s.evidence_ref == "/p/raw.json"
    # 없는 값을 만들지 않는다 — metric_name/value는 일반적으로 None
    assert s.metric_name is None and s.metric_value is None


def test_article_candidate_is_not_a_structured_signal():
    sigs = to_structured_signal_candidates(
        [_article()], source_id="yna", source_group="news", purpose="news")
    assert sigs == []


def test_mixed_list_separates_only_numeric():
    sigs = to_structured_signal_candidates(
        [_article(), _numeric(), _article()],
        source_id="mix", source_group="market", purpose="numeric")
    assert len(sigs) == 1  # numeric 1건만 분리, article은 섞이지 않음


def test_observed_at_uses_published_at():
    sigs = to_structured_signal_candidates(
        [_numeric(published_at="2026-06-14T00:00:00Z")],
        source_id="x", source_group="market", purpose="numeric")
    assert sigs[0].observed_at == "2026-06-14T00:00:00Z"

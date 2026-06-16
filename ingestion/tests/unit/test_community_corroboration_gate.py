"""G-4: CommunityCorroborationGate — 익명 커뮤니티 신호 publish 등급(투자권유/펌핑 차단)."""
from __future__ import annotations

from ingestion.orchestration.community_corroboration_gate import (
    PUBLISH_BLOCKED_UNTIL_CORROB,
    PUBLISH_INTERNAL_QUEUE_ONLY,
    PUBLISH_PREVIEW_CANDIDATE,
    annotate_records,
    evaluate_community_corroboration,
)


def test_financial_gallery_is_internal_queue_only():
    d = evaluate_community_corroboration(source_id="dcinside", gallery_id="stockus", title="오늘 시황 정리")
    assert d.publish_level == PUBLISH_INTERNAL_QUEUE_ONLY
    assert d.requires_external_confirmation is True
    assert "anonymous_financial_board" in d.risk_tags


def test_financial_gallery_hint_match():
    # 알려지지 않은 갤러리라도 stock/coin 힌트가 있으면 금융 게시판으로 본다.
    d = evaluate_community_corroboration(source_id="dcinside", gallery_id="newcoin_minor", title="잡담")
    assert d.publish_level == PUBLISH_INTERNAL_QUEUE_ONLY


def test_pumping_title_blocked_until_corrob():
    # 비금융 갤러리라도 펌핑/투자권유성 제목은 publish 차단.
    d = evaluate_community_corroboration(source_id="dcinside", gallery_id="baseball_gallery",
                                         title="지금 풀매수 가즈아 떡상각")
    assert d.publish_level == PUBLISH_BLOCKED_UNTIL_CORROB
    assert "investment_solicitation_or_pump" in d.risk_tags


def test_plain_community_is_preview_candidate():
    d = evaluate_community_corroboration(source_id="dcinside", gallery_id="movie_gallery",
                                         title="신작 예고편 공개")
    assert d.publish_level == PUBLISH_PREVIEW_CANDIDATE
    assert d.requires_external_confirmation is True   # 익명 source는 항상 외부확인 필수


def test_annotate_records_adds_metadata_without_mutating_original():
    recs = [{"record_type": "community_signal", "source_id": "dcinside",
             "title_or_label": "풀매수 가즈아", "source_url_or_evidence": "https://gall.dcinside.com/x",
             "published_at_or_observed_at": "2026-06-16T00:00:00+09:00"}]
    out = annotate_records(recs, source_id="dcinside", gallery_id="stockus")
    assert out[0]["publish_level"] == PUBLISH_INTERNAL_QUEUE_ONLY
    assert out[0]["requires_external_confirmation"] is True
    assert "corroboration_risk_tags" in out[0]
    assert "publish_level" not in recs[0]    # 원본 불변

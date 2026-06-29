"""ADR#86 — official×news role-bridge tests (PURE·merge 0·LLM 0·score 0·body 0·reviewer-routing only).

정책을 테스트로 잠근다: official×news 만 후보·role guard(news×news/community 거부)·date proximity + 공유 토큰
gate·freeze_eligible 은 양측 in-window 일 때만·same_event/merge/score/raw body 0·blocked_reason 정직 분해.
"""
from __future__ import annotations

import json

from backend.app.tools.official_news_role_bridge import (
    BRIDGE_TYPE,
    build_official_news_bridge,
    iter_freeze_eligible_record_pairs,
)

# official(FR) 문서 — record_type=official_record → role official.
_FR_IN = {
    "record_type": "official_record", "source_id": "federal_register",
    "title_or_label": "Final Rule on Asylum Metering at the Southern Border",
    "canonical_url": "https://www.federalregister.gov/documents/2026/06/25/x1",
    "published_at_or_observed_at": "2026-06-25", "body_state_or_signal": "present",
}
# news(guardian) 기사 — record_type=article_candidate → role article. 공유 토큰: asylum/metering/border.
_NEWS_IN = {
    "record_type": "article_candidate", "source_id": "guardian",
    "title_or_label": "Supreme Court upholds asylum metering policy at the border",
    "canonical_url": "https://www.theguardian.com/world/2026/jun/26/asylum",
    "published_at_or_observed_at": "2026-06-26", "body_state_or_signal": "present",
}
_WINDOW = ("2026-06-25", "2026-06-26")


def test_01_official_news_bridge_candidate_created():
    out = build_official_news_bridge([_FR_IN], [_NEWS_IN], date_window=_WINDOW)
    assert out["official_record_count"] == 1 and out["news_record_count"] == 1
    assert out["bridge_candidate_count"] == 1
    c = out["bridge_candidates"][0]
    assert c["bridge_type"] == BRIDGE_TYPE == "official_news"
    assert c["source_role_official"] == "official" and c["source_role_news"] == "article"
    assert c["shared_token_count"] >= 2 and "asylum" in c["shared_tokens"]
    assert c["date_proximity_days"] == 1


def test_02_freeze_eligible_requires_both_in_window():
    out = build_official_news_bridge([_FR_IN], [_NEWS_IN], date_window=_WINDOW)
    assert out["freeze_eligible_bridge_count"] == 1
    assert out["bridge_candidates"][0]["freeze_eligible"] is True
    assert out["blocked_reason"] == ""   # in-window 후보 존재 → blocked 아님.


def test_03_out_of_window_news_blocks_freeze():
    # news 가 window 밖(6/29) → bridge_candidate 일 수 있어도 freeze_eligible=False(out-of-window 동결 금지).
    news_out = dict(_NEWS_IN, published_at_or_observed_at="2026-06-29",
                    canonical_url="https://www.theguardian.com/world/2026/jun/29/asylum")
    out = build_official_news_bridge([_FR_IN], [news_out], date_window=_WINDOW)
    # date_proximity 4일 > tolerance 1 → 애초에 bridge_candidate 도 아님(정직).
    assert out["bridge_candidate_count"] == 0
    assert out["freeze_eligible_bridge_count"] == 0
    assert out["blocked_reason"] == "no_official_news_bridge_candidate"


def test_04_role_guard_news_times_news_not_official_bridge():
    # news×news 두 건은 official×news bridge 가 아니다(official_record 0) — role guard.
    news_b = dict(_NEWS_IN, source_id="nyt", canonical_url="https://www.nytimes.com/2026/06/26/asylum")
    out = build_official_news_bridge([], [_NEWS_IN, news_b], date_window=_WINDOW)
    assert out["official_record_count"] == 0 and out["news_record_count"] == 2
    assert out["bridge_candidate_count"] == 0
    assert out["blocked_reason"] == "no_official_records"


def test_05_community_record_rejected_as_anchor():
    # community_signal 은 official 도 news 도 아님 → 양쪽에서 제외(anchor 금지).
    community = {"record_type": "community_signal", "source_id": "reddit",
                "title_or_label": "asylum metering border thread",
                "canonical_url": "https://reddit.test/x", "published_at_or_observed_at": "2026-06-25"}
    out = build_official_news_bridge([_FR_IN], [community], date_window=_WINDOW)
    assert out["official_record_count"] == 1 and out["news_record_count"] == 0
    assert out["bridge_candidate_count"] == 0
    assert out["blocked_reason"] == "no_news_records"


def test_06_low_token_overlap_not_candidate():
    # 공유 토큰 < min(2) → bridge_candidate 아님(우연 1토큰으로 라우팅하지 않음).
    news_unrelated = {"record_type": "article_candidate", "source_id": "guardian",
                      "title_or_label": "Stock markets rally on technology earnings",
                      "canonical_url": "https://www.theguardian.com/business/x",
                      "published_at_or_observed_at": "2026-06-26"}
    out = build_official_news_bridge([_FR_IN], [news_unrelated], date_window=_WINDOW)
    assert out["bridge_candidate_count"] == 0
    assert out["blocked_reason"] == "no_official_news_bridge_candidate"


def test_07_invariants_no_merge_no_score_no_body():
    out = build_official_news_bridge([_FR_IN], [_NEWS_IN], date_window=_WINDOW)
    assert out["merge_allowed"] is False and out["same_event_asserted"] is False
    assert out["kg_edge_allowed"] is False and out["public_iu_allowed"] is False
    assert out["llm_invoked"] is False and out["embedding_invoked"] is False
    assert out["bridge_score_exposed"] is False and out["official_alone_as_production_candidate"] is False
    # 단일 score/predicted_status/rationale/raw title 전문이 어디에도 없음(forbidden 키 0).
    blob = json.dumps(out, ensure_ascii=False)
    for forbidden in ('"score"', '"predicted_status"', '"rationale"', '"body"', "Final Rule on Asylum"):
        assert forbidden not in blob


def test_08_no_window_means_fail_closed_freeze():
    # date_window 미제공 → in-window 미지 → freeze_eligible=False(in-window 단정 금지·fail-closed).
    out = build_official_news_bridge([_FR_IN], [_NEWS_IN], date_window=None)
    assert out["bridge_candidate_count"] == 1   # routing 후보는 가능(date proximity + token).
    assert out["freeze_eligible_bridge_count"] == 0   # window 없으면 freeze 불가.
    assert out["blocked_reason"] == "bridge_candidates_not_in_window"


def test_09_empty_inputs_blocked_reason():
    out = build_official_news_bridge([], [], date_window=_WINDOW)
    assert out["bridge_candidate_count"] == 0
    assert out["blocked_reason"] == "no_official_or_news_records"


# ── ADR#87: iter_freeze_eligible_record_pairs (freeze worklist 입력·실제 record 참조·단일 술어) ──────────────
def test_10_iter_freeze_eligible_returns_record_pairs_with_titles():
    pairs = iter_freeze_eligible_record_pairs([_FR_IN], [_NEWS_IN], date_window=_WINDOW)
    # build 의 freeze_eligible_count 와 일치(동일 술어).
    out = build_official_news_bridge([_FR_IN], [_NEWS_IN], date_window=_WINDOW)
    assert len(pairs) == out["freeze_eligible_bridge_count"] == 1
    p = pairs[0]
    assert p["pair_id"] == "oxn_0001"
    # 원본 record(title 포함) 참조 — reviewer worklist 구성용.
    assert p["official_record"]["title_or_label"].startswith("Final Rule")
    assert p["news_record"]["title_or_label"].startswith("Supreme Court")
    assert "asylum" in p["shared_tokens"]


def test_11_iter_freeze_eligible_out_of_window_empty():
    news_out = dict(_NEWS_IN, published_at_or_observed_at="2026-06-29",
                    canonical_url="https://www.theguardian.com/world/2026/jun/29/asylum")
    assert iter_freeze_eligible_record_pairs([_FR_IN], [news_out], date_window=_WINDOW) == []


def test_12_iter_freeze_eligible_no_window_fail_closed():
    # window 없으면 in-window 미지 → freeze 불가(build 와 동일·fail-closed).
    assert iter_freeze_eligible_record_pairs([_FR_IN], [_NEWS_IN], date_window=None) == []


def test_13_iter_freeze_eligible_role_guard():
    # community record 는 anchor 아님 → freeze pair 0.
    community = {"record_type": "community_signal", "source_id": "reddit",
                 "title_or_label": "asylum metering border thread",
                 "canonical_url": "https://reddit.test/x", "published_at_or_observed_at": "2026-06-25"}
    assert iter_freeze_eligible_record_pairs([_FR_IN], [community], date_window=_WINDOW) == []


# ── ADR#87: golden candidate dict (refactor byte-identity 락·_evaluate_official_news_pair 출력 shape/값 고정) ──
def test_14_candidate_dict_golden_shape_and_values():
    out = build_official_news_bridge([_FR_IN], [_NEWS_IN], date_window=_WINDOW)
    c = out["bridge_candidates"][0]
    # 전체 키 집합 고정(술어 추출 refactor 가 필드를 drop/추가/rename 하지 않음을 보장).
    assert set(c.keys()) == {
        "pair_id", "bridge_type", "source_id_official", "source_id_news",
        "source_role_official", "source_role_news", "date_official", "date_news",
        "date_proximity_days", "shared_token_count", "shared_tokens",
        "canonical_host_official", "canonical_host_news", "official_in_window", "news_in_window",
        "both_canonical_present", "both_published_present", "bridge_candidate", "freeze_eligible",
        "same_event_asserted", "reviewer_routing_only", "merge_allowed", "kg_edge_allowed",
        "public_iu_allowed"}
    # 결정적 값 고정(official-outer/news-inner·idx 1-based).
    assert c["pair_id"] == "oxn_0001"
    assert c["bridge_type"] == "official_news"
    assert c["source_id_official"] == "federal_register" and c["source_id_news"] == "guardian"
    assert c["source_role_official"] == "official" and c["source_role_news"] == "article"
    assert c["date_official"] == "2026-06-25" and c["date_news"] == "2026-06-26"
    assert c["date_proximity_days"] == 1
    assert c["canonical_host_official"] == "www.federalregister.gov"
    assert c["canonical_host_news"] == "www.theguardian.com"
    assert c["official_in_window"] is True and c["news_in_window"] is True
    assert c["both_canonical_present"] is True and c["both_published_present"] is True
    assert c["bridge_candidate"] is True and c["freeze_eligible"] is True
    assert c["same_event_asserted"] is False and c["reviewer_routing_only"] is True
    assert c["merge_allowed"] is False and c["kg_edge_allowed"] is False and c["public_iu_allowed"] is False
    # shared_tokens = 정규화 교집합(정렬·entity/action proxy). asylum/metering/border 공유.
    assert c["shared_tokens"] == sorted(c["shared_tokens"])
    assert {"asylum", "metering", "border"} <= set(c["shared_tokens"])
    assert c["shared_token_count"] == len(c["shared_tokens"])

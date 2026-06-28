"""ADR#81 — KO source path readiness 테스트(§13: 32~37·anchor guard·tokenization risk·secret-safe).

network 0 · merge 0 · LLM 0 · secret 값 0. probe_fn 주입으로 실 .env 비의존 결정론."""
from __future__ import annotations

import json

from backend.app.tools.ko_source_readiness import (
    build_ko_source_lane,
    build_ko_source_readiness,
)


def _probe_present(present):
    def fn(var):
        return {"var_name": var, "credential_present": var in present,
                "env_file_present": True, "declared_in_example": True}
    return fn


_PROBE_NONE = _probe_present(set())
_PROBE_ALL = _probe_present({
    "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "OPENDART_API_KEY", "BOK_ECOS_API_KEY"})


def _row(ko, sid):
    return next(r for r in ko["ko_sources"] if r["source_id"] == sid)


def test_ko_source_path_generated():
    """§13-32: KO source path 생성·key-free LIVE 뉴스로 path_ready."""
    ko = build_ko_source_readiness(probe_fn=_PROBE_NONE)
    assert ko["operation"] == "ko_source_readiness"
    assert len(ko["ko_sources"]) >= 10
    # yna/hankyung/maekyung 는 key-free LIVE → credential 없어도 ready.
    assert ko["ko_source_path_ready"] is True
    assert "yna" in ko["ko_live_ready_anchor_ids"]


def test_naver_and_newsapi_status_analyzed():
    """§13-33: Naver/NewsAPI 어댑터 status 분석."""
    ko = build_ko_source_readiness(probe_fn=_PROBE_NONE)
    naver = ko["naver_adapter_status"]
    assert naver["implemented"] is True
    assert naver["credential_present"] is False           # probe none → 미설정.
    assert naver["anchor_capable"] is True
    newsapi = ko["newsapi_status"]
    assert newsapi["implemented"] is True
    assert newsapi["ko_specific"] is False                # 영어권 aggregator·KO 1차 source 아님.


def test_naver_credential_present_when_probe_present():
    """credential probe present → naver credential_present True(secret-safe·값 0)."""
    ko = build_ko_source_readiness(probe_fn=_PROBE_ALL)
    assert ko["naver_adapter_status"]["credential_present"] is True
    nn = _row(ko, "naver_news_search")
    assert nn["credential_presence_secret_safe"] == {
        "NAVER_CLIENT_ID": "present", "NAVER_CLIENT_SECRET": "present"}


def test_ko_official_news_only_anchor_capable():
    """§13-34: KO official/news 만 anchor 가능."""
    ko = build_ko_source_readiness(probe_fn=_PROBE_ALL)
    assert _row(ko, "yna")["anchor_capable"] is True
    assert _row(ko, "naver_news_search")["anchor_capable"] is True
    assert _row(ko, "krx_kind")["anchor_capable"] is True     # KO official filing(publishable doc).


def test_ko_community_reaction_only():
    """§13-35: KO community 는 reaction-only·anchor 금지."""
    ko = build_ko_source_readiness(probe_fn=_PROBE_ALL)
    for sid in ("naver_blog_search", "dcinside", "fmkorea"):
        row = _row(ko, sid)
        assert row["ko_role"] == "community_reaction_only"
        assert row["anchor_capable"] is False
    assert ko["ko_community_reaction_only"] is True


def test_ko_search_url_candidate_only_policy():
    """§13-36: KO search 는 URL candidate only(policy contract)."""
    ko = build_ko_source_readiness(probe_fn=_PROBE_ALL)
    assert ko["ko_search_url_candidate_only"] is True


def test_ko_tokenization_risk_documented():
    """§13-37: KO tokenization risk 문서화(형태소/stemming/alias 부재·breadth-only)."""
    ko = build_ko_source_readiness(probe_fn=_PROBE_NONE)
    assert ko["ko_tokenization_risk_recorded"] is True
    risk = ko["ko_tokenization_risk"]
    assert risk["hangul_aware"] is True
    assert risk["has_korean_morphological_analysis"] is False
    assert risk["has_korean_stemming"] is False
    assert risk["has_korean_org_alias"] is False
    assert risk["crash_safe"] is True                     # KO 입력에서 probe 가 죽지 않음.


def test_ko_source_role_guard_preserved():
    """community/quarantine 은 anchor_capable=False 강제(role guard)."""
    ko = build_ko_source_readiness(probe_fn=_PROBE_ALL)
    assert ko["source_role_guard_preserved"] is True
    for r in ko["ko_sources"]:
        if r["ko_role"] in ("community_reaction_only", "unknown_quarantine"):
            assert r["anchor_capable"] is False


def test_missing_credentials_next_action():
    """credential 미설정 KO source → set_env next_action(이름만·값 0)."""
    ko = build_ko_source_readiness(probe_fn=_PROBE_NONE)
    nn = _row(ko, "naver_news_search")
    assert nn["credential_present"] is False
    assert "set_env:NAVER_CLIENT_ID" in nn["next_action"]
    assert nn["credential_presence_secret_safe"] == {
        "NAVER_CLIENT_ID": "missing", "NAVER_CLIENT_SECRET": "missing"}


def test_ko_floor_not_solved_gold_zero():
    """KO floor 는 실제 한국어 label 전까지 solved 금지·gold 0."""
    ko = build_ko_source_readiness(probe_fn=_PROBE_ALL)
    assert ko["ko_floor_solved"] is False
    assert ko["ko_gold_count"] == 0
    assert ko["ko_floor_target"] == 50
    assert ko["ko_floor_blocker"] == "actual_returned_korean_human_labels"
    assert ko["production_gold_count"] == 0


def test_no_secret_values_no_merge():
    ko = build_ko_source_readiness(probe_fn=_PROBE_ALL)
    assert ko["merge_allowed"] is False
    assert ko["llm_invoked"] is False
    assert ko["embedding_invoked"] is False
    assert ko["secret_values_exposed"] is False
    # credential dict value 는 present/missing 만(값 미노출).
    blob = json.dumps(ko, ensure_ascii=False)
    for r in ko["ko_sources"]:
        for v in r["credential_presence_secret_safe"].values():
            assert v in ("present", "missing")
    assert "present" in blob


# ── ADR#82 KO source lane(§8·§12: 28~33) — EN run 과 분리된 KO floor lane ─────────────────────────────────────
def test_ko_lane_status_exists_and_keyfree_anchors():
    """§12-28: KO source lane status 존재·key-free LIVE 뉴스 anchor."""
    lane = build_ko_source_lane(probe_fn=_PROBE_NONE)
    assert lane["operation"] == "ko_source_lane"
    assert lane["ko_source_lane_status"].startswith("ready_")
    for sid in ("yna", "hankyung", "maekyung", "zdnet_korea", "etnews"):
        assert sid in lane["ko_keyfree_live_anchor_ids"]
    assert "yna" in lane["ko_feed_only_sources"]
    assert lane["ko_named_seed_needed"] is True            # 한국어 named single-event seed 미존재.


def test_ko_lane_naver_status_secret_safe():
    """§12-29: Naver status secret-safe(present/missing boolean·값 0)."""
    lane = build_ko_source_lane(probe_fn=_PROBE_NONE)
    assert lane["naver_adapter_status"]["credential_present"] is False
    assert lane["naver_adapter_status"]["anchor_capable"] is True
    assert lane["newsapi_status"]["ko_specific"] is False
    blob = json.dumps(lane, ensure_ascii=False)
    assert "Users" not in blob


def test_ko_lane_floor_remains_zero():
    """§12-30: KO floor 0/50·solved 금지(실제 한국어 human label 전까지)."""
    lane = build_ko_source_lane(probe_fn=_PROBE_ALL)
    assert lane["ko_floor_current"] == 0
    assert lane["ko_floor_required"] == 50
    assert lane["ko_floor_solved"] is False
    assert lane["production_gold_count"] == 0


def test_ko_lane_tokenizer_and_alias_requirements_recorded():
    """§12-33: KO tokenizer/alias 요건 기록(형태소 분석기·org alias 미구축)."""
    lane = build_ko_source_lane(probe_fn=_PROBE_NONE)
    assert "morphological" in lane["ko_tokenizer_requirement"]
    assert "alias" in lane["ko_alias_table_requirement"]
    assert lane["ko_tokenization_risk_recorded"] is True


def test_ko_lane_role_guard_and_no_merge():
    """§12-31·32: source role guard 유지·merge/LLM 0."""
    lane = build_ko_source_lane(probe_fn=_PROBE_ALL)
    assert lane["source_role_guard_preserved"] is True
    assert lane["merge_allowed"] is False
    assert lane["llm_invoked"] is False
    assert lane["embedding_invoked"] is False
    assert lane["db_write"] is False
    assert lane["secret_values_exposed"] is False
    # query-capable KO anchor(naver_news_search·opendart 등)만 ko_query_capable_sources, community 미포함.
    assert "naver_blog_search" not in lane["ko_query_capable_sources"]

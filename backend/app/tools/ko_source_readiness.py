"""ADR#81 — Korean (KO) source path readiness (KO floor plan · anchor guard · merge 0 · LLM 0 · secret 값 0).

문제(분석 §2-Q8~Q11): R1 KO floor = 50 인데 KO gold = 0. 영어 Guardian/NYT 로는 KO floor 를 채울 수 없다.
이 모듈은 KO source path 를 **실 source_registry 와 연결**해 정직히 보고한다 — 무엇이 이미 LIVE 인지, 무엇이
credential 대기인지, KO tokenization 한계가 recall probe 에 어떤 위험인지, KO floor 를 채우려면 무엇이 먼저인지.

핵심 사실(분석 §2):
  - KO 뉴스 5종(yna·hankyung·maekyung tier1, zdnet_korea·etnews tier2) 이미 LIVE_SUCCESS·key-free·publishable.
  - Naver 어댑터(naver_news_search·naver_blog_search) 구현됨 — NAVER_CLIENT_ID/SECRET 필요(secret-safe probe).
  - recall probe 토크나이저 `[0-9A-Za-z가-힣]+` 는 한글 인식하나 형태소 분절·KO stemming·KO org alias 전무 →
    KO-KO near-match undercount(R-KOAnalyzerDependency). KO 비교는 analyzer 전까지 **breadth-only**.

절대 불변(source role guard):
  - KO official/news 만 anchor 가능(publishable·source role 검증 시) · KO community 는 reaction layer only ·
    KO search 는 URL candidate only · KO market/catalog 는 anchor 불가.
  - KO floor 는 **실제 한국어 returned human label** 전까지 solved 표기 금지(production_gold_count 0 유지).
  - merge 0 · LLM/embedding 0 · DB 0 · secret 값 0(env var 이름·present/missing boolean 만).
"""
from __future__ import annotations

import argparse
import sys
from typing import Callable, Optional

# ── KO source 큐레이트(registry id 기준·KO role 명시) ──────────────────────────────────────────────────────
# anchor=publishable KO news/official(source role 검증 시 anchor 가능) · reaction=community(anchor 금지) ·
# quarantine=trend signal(anchor 금지). credential 은 secret-safe probe 로 실측(값 0).
_KO_SOURCES: tuple[dict, ...] = (
    # ── anchor-capable KO news(publishable) ──
    {"id": "yna", "name": "연합뉴스 Yonhap", "ko_role": "ko_official_news", "anchor_capable": True,
     "query_capability": "feed_only", "env_keys": [], "tier": "tier1", "status": "live_success"},
    {"id": "hankyung", "name": "한국경제", "ko_role": "ko_official_news", "anchor_capable": True,
     "query_capability": "feed_only", "env_keys": [], "tier": "tier1", "status": "live_success"},
    {"id": "maekyung", "name": "매일경제", "ko_role": "ko_official_news", "anchor_capable": True,
     "query_capability": "feed_only", "env_keys": [], "tier": "tier1", "status": "live_success"},
    {"id": "zdnet_korea", "name": "ZDNet Korea", "ko_role": "ko_official_news", "anchor_capable": True,
     "query_capability": "feed_only", "env_keys": [], "tier": "tier2", "status": "live_success"},
    {"id": "etnews", "name": "전자신문", "ko_role": "ko_official_news", "anchor_capable": True,
     "query_capability": "feed_only", "env_keys": [], "tier": "tier2", "status": "live_success"},
    {"id": "naver_news_search", "name": "Naver News Search", "ko_role": "ko_official_news",
     "anchor_capable": True, "query_capability": "topic",
     "env_keys": ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"], "tier": "tier2",
     "status": "implemented_needs_credentials"},
    # ── KO official(filing/data — publishable doc 만 anchor·data 는 enrichment) ──
    {"id": "opendart", "name": "OpenDART 금감원", "ko_role": "official_source", "anchor_capable": True,
     "query_capability": "structured_query", "env_keys": ["OPENDART_API_KEY"], "tier": "tier1",
     "status": "implemented_needs_credentials"},
    {"id": "krx_kind", "name": "KRX KIND 공시", "ko_role": "official_source", "anchor_capable": True,
     "query_capability": "feed_only", "env_keys": [], "tier": "tier1", "status": "implemented"},
    {"id": "bok_ecos", "name": "한국은행 ECOS", "ko_role": "official_source", "anchor_capable": False,
     "query_capability": "structured_query", "env_keys": ["BOK_ECOS_API_KEY"], "tier": "tier1",
     "status": "implemented_needs_credentials", "note": "economic_data_enrichment_not_news_anchor"},
    # ── KO community(reaction layer only · anchor 금지) ──
    {"id": "naver_blog_search", "name": "Naver Blog Search", "ko_role": "community_reaction_only",
     "anchor_capable": False, "query_capability": "topic",
     "env_keys": ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"], "tier": "tier2", "status": "implemented"},
    {"id": "dcinside", "name": "DCinside", "ko_role": "community_reaction_only", "anchor_capable": False,
     "query_capability": "feed_only", "env_keys": [], "tier": "tier3", "status": "implemented"},
    {"id": "fmkorea", "name": "에펨코리아", "ko_role": "community_reaction_only", "anchor_capable": False,
     "query_capability": "feed_only", "env_keys": [], "tier": "tier3", "status": "blocked_cloudflare"},
    # ── KO trend signal(attention · anchor 금지 · fail-closed quarantine) ──
    {"id": "signal_bz", "name": "Signal.bz 한국트렌드", "ko_role": "unknown_quarantine",
     "anchor_capable": False, "query_capability": "feed_only", "env_keys": [], "tier": "tier3",
     "status": "external_signal"},
    {"id": "loword", "name": "Loword 한국트렌드", "ko_role": "unknown_quarantine", "anchor_capable": False,
     "query_capability": "feed_only", "env_keys": [], "tier": "tier3", "status": "external_signal"},
)

# recall probe 토크나이저 KO 한계(분석 §2-Q11 · R-KOAnalyzerDependency). near_match_recall_probe._TOKEN 과 정합.
_KO_TOKENIZATION_RISK = {
    "tokenizer_regex": "[0-9A-Za-z가-힣]+",
    "hangul_aware": True,                              # 한글 토큰 유지(드롭 안 됨).
    "has_korean_morphological_analysis": False,        # 형태소 분절 없음(한국은행=단일 토큰).
    "has_korean_stemming": False,                      # 조사/어미 변화(금리를/금리가/금리는) 미정규화.
    "has_korean_org_alias": False,                     # 한국은행=BOK=한은 alias 부재.
    "risk": "KO-KO near-match recall undercount — 같은 사건 KO 쌍이 0.2 routing floor 아래에 머물 수 있음",
    "impact_on_recall_probe": "deterministic recall lever 는 영어 튜닝(phrase/acronym alias 전부 영어)",
    "mitigation_deferred": "KoNLPy/Mecab/Okt 형태소 분석기(무거운 신규 의존성 — 이번 턴 deferred)",
    "until_analyzer_landed": "KO 비교는 breadth-only(recall lift lever 아님) · entity-sharing 신뢰 금지",
    "crash_safe": True,                                # KO 입력에서 probe 가 죽지 않음(동작·undercount 일 뿐).
}


def _default_probe(var: str) -> dict:
    """secret-safe 단일 키 probe — env_loader.probe_env_var 재사용(값 0·present/missing+파일존재만)."""
    try:
        from ingestion.core.env_loader import probe_env_var
        return probe_env_var(var)
    except Exception:
        return {"var_name": var, "credential_present": False,
                "env_file_present": False, "declared_in_example": False}


def _rate_limit_policy(source_id: str) -> dict:
    try:
        from ingestion.core.rate_limit_policy import load_rate_limit_policy
        pol = load_rate_limit_policy(source_id)
        return {"min_interval_seconds": pol.min_interval_seconds,
                "cooldown_on_429_seconds": pol.cooldown_on_429_seconds,
                "max_retries_on_429": pol.max_retries_on_429}
    except Exception:
        return {"min_interval_seconds": 0, "cooldown_on_429_seconds": 60, "max_retries_on_429": 1}


def _ko_row(spec: dict, *, probe_fn: Callable[[str], dict]) -> dict:
    """단일 KO source readiness row(credential secret-safe·anchor guard)."""
    env_keys = list(spec.get("env_keys") or [])
    cred = {k: probe_fn(k) for k in env_keys}
    credential_present = all(c.get("credential_present") for c in cred.values()) if env_keys else True
    missing = [k for k, c in cred.items() if not c.get("credential_present")]
    # anchor guard: community/quarantine 는 anchor_capable=False 가 강제(role guard).
    anchor_capable = bool(spec.get("anchor_capable")) and spec["ko_role"] in (
        "ko_official_news", "official_source")
    return {
        "source_id": spec["id"],
        "source_name": spec["name"],
        "ko_role": spec["ko_role"],
        "anchor_capable": anchor_capable,
        "query_capability": spec.get("query_capability"),
        "tier": spec.get("tier"),
        "status": spec.get("status"),
        "credential_required": bool(env_keys),
        "credential_present": credential_present,
        "credential_presence_secret_safe": {
            k: ("present" if c.get("credential_present") else "missing") for k, c in cred.items()},
        "missing_credentials": missing,
        "rate_limit_policy": _rate_limit_policy(spec["id"]),
        "ko_floor_contribution": (
            "anchor_publishable" if anchor_capable
            else "reaction_only" if spec["ko_role"] == "community_reaction_only"
            else "none_quarantine"),
        "note": spec.get("note"),
        "next_action": _ko_next_action(spec, anchor_capable=anchor_capable, missing=missing),
    }


def _ko_next_action(spec: dict, *, anchor_capable: bool, missing: list[str]) -> str:
    if spec.get("status") == "blocked_cloudflare":
        return "blocked — community reaction-only·anchor 금지(우회 금지)"
    if missing:
        return f"set_env:{','.join(missing)} (.env·secret 커밋 금지) 후 KO 수집 활성"
    if anchor_capable and spec.get("status") == "live_success":
        return "wire_into_comparison_pool — KO publishable anchor(KO floor 기여)"
    if anchor_capable:
        return "credential_ready_or_keyfree — comparison pool 연결 후보"
    if spec["ko_role"] == "community_reaction_only":
        return "reaction_to_verified_event_only — anchor 금지"
    if spec["ko_role"] == "official_source":
        return "official_data_enrichment_only — anchor 금지(news doc 아님)"
    return "quarantine_no_anchor — trend/attention signal"


def build_ko_source_readiness(
    *, probe_fn: Optional[Callable[[str], dict]] = None,
) -> dict:
    """KO source path readiness + Naver/NewsAPI 어댑터 status + tokenization risk + KO floor plan.

    network 0 · merge 0 · LLM 0 · secret 값 0(present/missing boolean 만). KO floor 는 실제 한국어 human label
    전까지 solved 금지(production_gold_count 0)."""
    pf = probe_fn or _default_probe
    rows = [_ko_row(s, probe_fn=pf) for s in _KO_SOURCES]

    anchor_rows = [r for r in rows if r["anchor_capable"]]
    reaction_rows = [r for r in rows if r["ko_role"] == "community_reaction_only"]
    quarantine_rows = [r for r in rows if r["ko_role"] == "unknown_quarantine"]
    # KO path ready = anchor-capable KO news 중 즉시 사용 가능(key-free LIVE 또는 credential 충족) ≥1.
    live_ready_anchors = [
        r for r in anchor_rows
        if (not r["credential_required"] or r["credential_present"]) and r["status"] in (
            "live_success", "implemented")]
    ko_official_news_anchors = [r for r in anchor_rows if r["ko_role"] == "ko_official_news"]

    naver_news = next((r for r in rows if r["source_id"] == "naver_news_search"), None)
    naver_blog = next((r for r in rows if r["source_id"] == "naver_blog_search"), None)
    ko_adapter_status = {
        "naver_news_search": {
            "implemented": True, "credential_present": bool(naver_news and naver_news["credential_present"]),
            "required_env": ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"],
            "role": "ko_official_news_query_capable", "anchor_capable": True,
            "status": naver_news["status"] if naver_news else "unknown"},
        "naver_blog_search": {
            "implemented": True, "credential_present": bool(naver_blog and naver_blog["credential_present"]),
            "role": "community_reaction_only", "anchor_capable": False},
        "newsapi": {
            "implemented": True, "ko_specific": False,
            "note": "영어권 aggregator — KO 는 query lang 으로 제한적·KO floor 의 1차 source 아님",
            "role": "query_capable_publishable", "anchor_capable": True},
        "live_korean_news_keyfree": {
            "sources": [r["source_id"] for r in ko_official_news_anchors if not r["credential_required"]],
            "status": "live_success_keyfree", "anchor_capable": True},
    }

    # KO floor plan(순서·정직: human label 이 hard blocker).
    ko_floor_plan = [
        "1. key-free LIVE KO 뉴스(yna·hankyung·maekyung·zdnet_korea·etnews) 를 comparison pool 에 연결(즉시 가능)",
        "2. NAVER_CLIENT_ID/SECRET 설정 후 naver_news_search(키워드 query)로 named-seed 타깃 KO 수집",
        "3. KO publishable pair 를 near-match reviewer worklist 로(score breadth-only·analyzer 전 entity-sharing 신뢰 금지)",
        "4. 한국어 reviewer contact → 실제 returned KO label 수집(hard blocker·코드로 못 옮김)",
        "5. KO gold 50 floor 는 실제 한국어 human label 전까지 solved 금지(production_gold_count 0 유지)",
    ]

    return {
        "operation": "ko_source_readiness",
        "ko_source_path_ready": len(live_ready_anchors) > 0,
        "ko_sources": rows,
        "ko_official_news_count": len(ko_official_news_anchors),
        "ko_anchor_capable_count": len(anchor_rows),
        "ko_reaction_only_count": len(reaction_rows),
        "ko_quarantine_count": len(quarantine_rows),
        "ko_live_ready_anchor_ids": sorted(r["source_id"] for r in live_ready_anchors),
        "ko_adapter_status": ko_adapter_status,
        "naver_adapter_status": ko_adapter_status["naver_news_search"],
        "newsapi_status": ko_adapter_status["newsapi"],
        "ko_tokenization_risk": _KO_TOKENIZATION_RISK,
        "ko_tokenization_risk_recorded": True,
        "ko_floor_plan": ko_floor_plan,
        "ko_floor_target": 50,
        "ko_gold_count": 0,
        "ko_floor_solved": False,                         # 실제 한국어 human label 전까지 False(불변).
        "ko_floor_blocker": "actual_returned_korean_human_labels",
        # ── source role guard(KO) ──
        "ko_official_news_anchor_only": True,
        "ko_community_reaction_only": True,
        "ko_search_url_candidate_only": True,
        "source_role_guard_preserved": all(
            (not r["anchor_capable"]) for r in rows
            if r["ko_role"] in ("community_reaction_only", "unknown_quarantine")),
        # ── 불변 경계 ──
        "merge_allowed": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "db_write": False,
        "production_gold_count": 0,
        "secret_values_exposed": False,
        "raw_source_body_exposed": False,
    }


def build_ko_source_lane(*, probe_fn: Optional[Callable[[str], dict]] = None) -> dict:
    """ADR#82 §8 — KO source lane(EN named-seed live run 과 *분리된* KO floor lane).

    분석 §2-Q10/Q11: KO 뉴스는 RSS feed_only(topic query 불가)라 EN Guardian/NYT named-seed cross-source query 에
    직접 섞을 수 없고(language mismatch — KO 형태소 분석기 부재), KO-KO candidate 생성에는 한국어 named single-event
    seed 가 필요(현재 미존재 → ko_named_seed_needed=True). KO floor 는 실제 한국어 human label 전까지 0/50 유지(불변).
    network 0 · merge 0 · LLM 0 · secret 값 0."""
    ko = build_ko_source_readiness(probe_fn=probe_fn)
    rows = ko["ko_sources"]
    ko_official_news = sorted(
        r["source_id"] for r in rows if r["ko_role"] == "ko_official_news" and r["anchor_capable"])
    ko_query_capable = sorted(
        r["source_id"] for r in rows
        if r.get("query_capability") in ("topic", "structured_query") and r["anchor_capable"])
    ko_feed_only = sorted(
        r["source_id"] for r in rows
        if r.get("query_capability") == "feed_only" and r["anchor_capable"])
    keyfree_live_anchors = sorted(
        r["source_id"] for r in rows
        if r["anchor_capable"] and not r["credential_required"] and r["status"] == "live_success")
    lane_status = (
        f"ready_{len(keyfree_live_anchors)}_keyfree_live_ko_news_anchors"
        if ko["ko_source_path_ready"] else "blocked_no_ko_anchor")
    ko_next_action = (
        "build_korean_named_single_event_seed (특정 한국 기관/사건+날짜) → wire key-free LIVE KO news pool "
        "(yna/hankyung/maekyung/zdnet_korea/etnews) → 한국어 reviewer contact for KO gold "
        "(KO floor 는 실제 한국어 human label 전까지 0/50)")
    return {
        "operation": "ko_source_lane",
        "ko_source_lane_status": lane_status,
        "ko_named_seed_needed": True,                 # 한국어 named single-event seed bank 미존재(EN seed 와 별개).
        "ko_query_capable_sources": ko_query_capable,
        "ko_feed_only_sources": ko_feed_only,
        "ko_official_news_sources": ko_official_news,
        "ko_keyfree_live_anchor_ids": keyfree_live_anchors,
        "naver_adapter_status": ko["naver_adapter_status"],
        "newsapi_status": ko["newsapi_status"],
        "ko_tokenizer_requirement": (
            "korean_morphological_analyzer(KoNLPy/Mecab/Okt) — deferred; analyzer 전까지 KO 비교는 breadth-only"),
        "ko_alias_table_requirement": (
            "korean_org_alias_table(한국은행=BOK=한은) — 미구축; KO entity-sharing 신뢰 금지"),
        "ko_floor_current": ko["ko_gold_count"],       # 0
        "ko_floor_required": ko["ko_floor_target"],    # 50
        "ko_floor_solved": ko["ko_floor_solved"],      # False(불변)
        "ko_floor_blocker": ko["ko_floor_blocker"],
        "ko_next_action": ko_next_action,
        "ko_tokenization_risk_recorded": ko["ko_tokenization_risk_recorded"],
        "source_role_guard_preserved": ko["source_role_guard_preserved"],
        # ── 불변 경계 ──
        "merge_allowed": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "db_write": False,
        "production_gold_count": 0,
        "secret_values_exposed": False,
        "raw_source_body_exposed": False,
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#81 Korean source path readiness (KO floor plan·anchor guard·merge 0·LLM 0·secret 값 0; "
                     "network 0)."))
    parser.add_argument("--json", action="store_true", help="full readiness JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    ko = build_ko_source_readiness()
    if ns.json:
        import json
        print(json.dumps(ko, ensure_ascii=False, indent=2))
        return 0
    print(f"- KO source readiness (ADR#81) path_ready={ko['ko_source_path_ready']} "
          f"ko_official_news={ko['ko_official_news_count']} guard={ko['source_role_guard_preserved']}")
    for r in ko["ko_sources"]:
        print(f"    {r['source_id']:<20} {r['ko_role']:<24} anchor={r['anchor_capable']!s:<5} "
              f"cred={r['credential_present']!s:<5} -> {r['next_action']}")
    print(f"- live_ready_anchors={ko['ko_live_ready_anchor_ids']}")
    print(f"- ko_tokenization_risk_recorded={ko['ko_tokenization_risk_recorded']} "
          f"(morphology={ko['ko_tokenization_risk']['has_korean_morphological_analysis']})")
    print(f"- ko_floor_solved={ko['ko_floor_solved']} ko_gold_count={ko['ko_gold_count']} "
          f"blocker={ko['ko_floor_blocker']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

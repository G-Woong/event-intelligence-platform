"""ADR#78 — R1 targeted live acquisition + near-match gap diagnostic (병합 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0).

ADR#77 이 실측한 것: broad topic("central bank rate decision"·1d) 1회 live 로 guardian×nyt **100 publishable
cross-source 비교쌍 / near-match 0**(no_title_overlap). 그 0 은 (i) 같은 사건의 cross-source paraphrase 를
결정적 near-match 가 놓침(recall 한계) 인지 (ii) broad topic 아래 서로 다른 사건/측면이라 정당하게 안 겹침 인지
**단일 broad-topic 1회로는 구분 불가**다(ADR#64 가 이미 명시). 그리고 그 100쌍 제목은 production 경로가 미보존이라
사후 검사 불가다.

이 모듈은 **재구현이 아니라** 두 가지를 더하는 얇은 layer 다:
  - **near-match gap 진단(Lane B)**: smoke 의 `emit_band_diagnostic`(band 분포·최고중첩 below-floor 샘플·공유 토큰·
    raw body 0)을 입력으로 원인을 **양가(兩價) 보존**으로 분류한다(`classify_near_match_gap`). 같은 사건/다른 사건을
    **단정하지 않는다** — 다수 가설 또는 unknown 을 낸다(§5).
  - **targeted live acquisition(Lane C)**: broad 대신 **event-specific named-entity seed**(양 매체가 다 보도할)로
    bounded·governed·secret-safe live 재실행(opt-in·승인 시만)→ 6-state 분류→ live-derived publishable 쌍이 있으면
    production-candidate freeze. freeze/6-state/R1 gap/contract 는 ADR#76 `run_r1_production_candidate_acquisition`
    를 그대로 재사용(둔갑 0·합성→production 0).
  - **acquisition strategy(Lane D)**: provider expansion plan + Korean source strategy(official/news 만 anchor·search
    URL-candidate-only·community reaction-only)를 기계적으로 산출.
  - **product bridge(Lane E)**: LLM evidence packet / RAG ingestion gate / KG edge eligibility / community reaction
    layer / public IU gate 는 **contract/문서로만** 준비 표시(runtime 0).

절대 불변(상속·상용 안전 계약):
  - **same_event 단정 0**: 진단 결과는 truth 가 아니며 production gold 를 만들지 않는다. near-match 완화는 reviewer
    라우팅 recall 만 — merge 는 여전히 fingerprint+gold+MERGE_GATE 게이트(false-merge 표면 불변).
  - **합성→production 둔갑 0 / live opt-in·secret-safe / no merge·LLM·embedding·DB·전송·secret read / public IU 0**.
  - **source role guard**: production candidate·anchor 는 publishable(official/article/news)만. community/market/
    catalog/search 는 anchor 거부. search 는 URL candidate 일 뿐 truth 아님.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Optional

from backend.app.tools.cross_source_live_overlap_smoke import (
    _DEFAULT_PROVIDER_B,
    _PROVIDER_A,
    run_cross_source_live_overlap_smoke,
)
from backend.app.tools.r1_production_candidate_acquisition import (
    PCAND_BLOCKED_STATES,
    PROD_BATCH_ID,
    run_r1_production_candidate_acquisition,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "r1_targeted_live_acquisition_and_near_match_diagnostic"

# ── ADR#77 baseline(실측·문서화 상수·날조 아님; 100쌍 제목 미보존이라 카운트만 인용) ─────────────────────────
ADR77_LIVE_CANDIDATE_COUNT = 100      # publishable cross-source same-date 비교쌍(= same-event 매치 아님).
ADR77_PUBLISHABLE_PAIR_COUNT = 0      # near-match 후보(Jaccard≥0.2 도달) 0 — 전부 below hard floor.
ADR77_TOPIC = "central bank rate decision"
ADR77_TIME_WINDOW = "1d"

# ── targeted query seeds(§6: event-specific·publishable news 친화·named entity·bounded·community/market/catalog 아님) ──
# 단일 broad topic 대신 양 매체(Guardian·NYT)가 다 보도할 named-entity 이벤트로 좁혀 공유 entity 토큰↑ → (i)/(ii) 분리.
# knowledge-cutoff 강건성을 위해 지속 기관/사안 anchor(특정 날짜 의존 0). seed 는 수집 의도일 뿐 truth 아님.
TARGETED_QUERY_SEEDS: list[dict] = [
    {"seed_id": "fed_rate", "topic": "Federal Reserve interest rate decision",
     "topic_key": "fed_rate", "time_window": "7d", "event_type": "monetary_policy",
     "rationale": "단일 기관(Fed)·FOMC 결정은 양 매체 집중 보도 — ADR#77 broad 'central bank' 대비 협소"},
    {"seed_id": "scotus_ruling", "topic": "Supreme Court ruling",
     "topic_key": "scotus", "time_window": "7d", "event_type": "judicial",
     "rationale": "이산적 사법 사건·양 매체 cross-coverage 높음"},
    {"seed_id": "ukraine_war", "topic": "Ukraine Russia war",
     "topic_key": "ukraine", "time_window": "3d", "event_type": "geopolitical",
     "rationale": "지속 고보도 분쟁(cutoff 강건)·tight window"},
]

# ── §5 root-cause classes(양가 보존·단정 0) ──────────────────────────────────────────────────────────────
RC_SAME_EVENT_MISSED = "same_event_possible_but_detector_missed"
RC_DIFFERENT_EVENTS = "broad_topic_different_events"
RC_PROVIDER_NARROW = "provider_pair_narrowness"
RC_TIME_WINDOW = "time_window_mismatch"
RC_TITLE_NORM = "title_normalization_gap"
RC_SOURCE_ROLE_META = "source_role_metadata_gap"
RC_INSUFFICIENT_ARTIFACT = "insufficient_debug_artifact"
RC_UNKNOWN = "unknown"

# near_match_gap_status
NMG_NO_CROSS_OVERLAP = "no_cross_source_overlap"
NMG_ALL_BELOW_HARD_FLOOR = "all_below_hard_floor"
NMG_CANDIDATES_PRESENT = "candidates_present"
NMG_INSUFFICIENT_ARTIFACT = "insufficient_debug_artifact"

# §11 internal ops 필수 copy(public truth 아님·정직 경계).
REQUIRED_OPS_COPY: tuple[str, ...] = (
    "Near-match 0 does not prove no same event",
    "Cause unresolved: detector miss vs different-events vs provider narrowness",
    "Production candidate requires live-derived publishable pair",
    "Production candidate is reviewer worklist, not truth",
    "R1 gold remains 0 until human labels are returned",
    "R2~R7 remain No-Go",
)

# Lane E contract 문서(이번 ADR 에서 신규/보강 — runtime 0). ready=계약 정의됨(실 runtime 아님).
CONTRACT_DOCS: dict[str, str] = {
    "llm_evidence_packet": "docs/5_REFERENCE/LLM_EVIDENCE_PACKET_CONTRACT.md",
    "rag_kg_entity_gate": "docs/5_REFERENCE/RAG_KG_ENTITY_GATE_CONTRACT.md",
    "intelligence_unit": "docs/5_REFERENCE/INTELLIGENCE_UNIT_CONTRACT.md",
    "rag_kg_agent_readiness": "docs/5_REFERENCE/RAG_KG_AGENT_READINESS.md",
}

# provider_status → network 시도 여부(live_call_count 산정·secret 0).
_NETWORK_ATTEMPT_STATUSES = frozenset({"ok", "no_records", "rate_limited", "network_error", "parser_error"})


# ── §6 targeted query seed 검증(event-specific·publishable·community/market/catalog 아님·bounded) ──────────
def validate_query_seed(seed: dict) -> dict:
    """targeted seed 가 §6 요건을 만족하는가(event-specific·named entity/event phrase·bounded window·anchor 친화).

    community/market/catalog-only 의도면 거부(anchor 금지). 검증 실패 사유를 명시(조용히 통과 0)."""
    topic = (seed.get("topic") or "").strip()
    window = (seed.get("time_window") or "").strip()
    reasons: list[str] = []
    if not topic or len(topic.split()) < 2:
        reasons.append("topic_not_event_specific")              # 단일 generic 단어는 event-specific 아님.
    if window not in ("1d", "3d", "7d", "14d"):
        reasons.append("time_window_not_bounded")               # bounded breaking-event 창만.
    low = topic.lower()
    if any(t in low for t in ("reddit", "forum", "subreddit", "twitter", "stock price",
                              "ticker", "marketplace", "catalog", "product listing")):
        reasons.append("community_market_catalog_only_topic")   # anchor 금지 표면.
    return {
        "seed_id": seed.get("seed_id"),
        "topic": topic,
        "time_window": window,
        "event_type": seed.get("event_type"),
        "valid": not reasons,
        "reject_reasons": reasons,
    }


# ── §5 near-match gap 진단 분류(양가 보존·같은/다른 사건 단정 0·metadata only) ───────────────────────────────
def classify_near_match_gap(
    band_diagnostic: Optional[dict], *, cross_source_pair_count: int,
    providers: list[str], time_window: str,
) -> dict:
    """band_diagnostic(band 분포·max Jaccard·공유 토큰 샘플) → root-cause **가설들**(단정 아님)·confidence·basis.

    §5 규칙: metadata 로 원인을 못 가르면 다수 가설 또는 unknown. 모호성을 접지 않는다(do not collapse). paraphrase
    도 different-events 도 **증거가 뒷받침할 때만** 신호를 'supporting' 으로 둔다 — 그래도 반대 가설을 'plausible' 로
    남겨 confidence=indeterminate 를 강제(단정 차단). diagnostic 결과는 truth 가 아니며 gold 를 만들지 않는다."""
    # debug artifact 부재(live 미도달·band 미산출) → 분류 불가(정직).
    if not band_diagnostic:
        return {
            "near_match_gap_status": NMG_INSUFFICIENT_ARTIFACT,
            "root_cause_hypotheses": [{
                "cause": RC_INSUFFICIENT_ARTIFACT, "signal": "supporting",
                "basis": "no band-level metadata captured (live not reached or emit_band_diagnostic off); "
                         "the 100-pair titles from ADR#77 were not persisted — a bounded live re-run with band "
                         "capture is required to inspect the gap"}],
            "root_cause_confidence": "n/a",
            "diagnostic_basis": {"band_diagnostic_present": False},
            "same_event_truth_asserted": False,
            "raw_body_stored": False,
        }
    if cross_source_pair_count <= 0:
        return {
            "near_match_gap_status": NMG_NO_CROSS_OVERLAP,
            "root_cause_hypotheses": [{
                "cause": RC_DIFFERENT_EVENTS, "signal": "plausible",
                "basis": "no publishable cross-source same-date comparison pair at all — outlets did not co-report "
                         "in-window (this is an overlap-absence problem, distinct from near-match detection)"}],
            "root_cause_confidence": "indeterminate",
            "diagnostic_basis": {"cross_source_pair_count": 0},
            "same_event_truth_asserted": False,
            "raw_body_stored": False,
        }
    dist = band_diagnostic.get("band_distribution") or {}
    detectable = int(dist.get("fingerprint", 0)) + int(dist.get("near_match", 0)) + int(dist.get("hard_negative", 0))
    if detectable > 0:
        # near/hard/fingerprint cross 쌍 존재 → 게이트 자체는 후보를 냈다(gap 아님).
        return {
            "near_match_gap_status": NMG_CANDIDATES_PRESENT,
            "root_cause_hypotheses": [{
                "cause": RC_UNKNOWN, "signal": "n/a",
                "basis": f"{detectable} cross-source pair(s) cleared the hard floor — reviewer candidates exist; "
                         "same-event remains a reviewer/gold question, not asserted here"}],
            "root_cause_confidence": "n/a",
            "diagnostic_basis": {"band_distribution": dist,
                                 "max_cross_source_title_jaccard": band_diagnostic.get("max_cross_source_title_jaccard")},
            "same_event_truth_asserted": False,
            "raw_body_stored": False,
        }

    # all below hard floor(ADR#77 / 실 case): 원인 양가 — 다수 가설 + indeterminate.
    samples = band_diagnostic.get("top_below_floor_samples") or []
    max_jac = float(band_diagnostic.get("max_cross_source_title_jaccard") or 0.0)
    hard_floor = float(band_diagnostic.get("hard_floor") or 0.2)
    norm = band_diagnostic.get("title_normalization") or {}
    shared_ge2 = sum(1 for s in samples if int(s.get("shared_token_count") or 0) >= 2)
    shared_zero = sum(1 for s in samples if int(s.get("shared_token_count") or 0) == 0)
    all_article = all(
        (s.get("source_role_left") in ("official", "article", "news")
         and s.get("source_role_right") in ("official", "article", "news"))
        for s in samples) if samples else True
    no_stemming = (norm.get("stemming") is False) or (norm.get("entity_normalization") is False)

    hyps: list[dict] = []
    # (i) same-event recall miss — **overlap 크기**(max Jaccard 가 hard floor 근처)로만 supporting. generic filler
    # 토큰 공유(예: 'it'/'over'/'day')는 same-event 증거로 승격하지 않는다(adversarial F1: shared_token_count 만으로는
    # entity vs filler 구분 불가 → machine 신호가 narrative 와 반대로 튀는 것 방지). shared_ge2 는 diagnostic_basis 의
    # 보고용 metadata 로만 남긴다(인간 감사자가 공유 토큰 구성을 직접 본다).
    hyps.append({
        "cause": RC_SAME_EVENT_MISSED,
        "signal": "supporting" if max_jac >= hard_floor / 2 else "plausible",
        "basis": f"max cross-source title Jaccard={round(max_jac, 4)} (<hard floor {hard_floor}); "
                 f"{shared_ge2} top sample(s) share >=2 normalized tokens (reported, not promoting signal) — short "
                 "headlines + no stemming/entity-alias can keep same-event pairs under threshold (deterministic "
                 "recall limit); supporting only when pairs approach the floor, not on generic-token sharing. "
                 "cannot be ruled out without reviewer labels"})
    # (ii) different events — 다수 샘플이 공유 토큰 0(서로 무관).
    hyps.append({
        "cause": RC_DIFFERENT_EVENTS,
        "signal": "supporting" if (samples and shared_zero >= max(1, len(samples) // 2)) else "plausible",
        "basis": f"{shared_zero}/{len(samples)} top sample(s) share 0 normalized tokens — a broad topic can return "
                 "genuinely different sub-events/aspects across outlets. cannot be ruled out without reviewer labels"})
    # (iii) title normalization gap — stemming/entity 정규화 부재는 구조적 recall 억제 요인.
    if no_stemming and max_jac > 0:
        hyps.append({
            "cause": RC_TITLE_NORM, "signal": "plausible",
            "basis": "deterministic tokenizer is lowercase + stopword + len>1 with NO stemming/entity normalization "
                     "(e.g. 'rates'!='rate', 'Fed'!='Federal Reserve') — this structurally suppresses cross-source "
                     "Jaccard; a KO/EN-aware light normalization could raise reviewer-routing recall without touching "
                     "merge precision"})
    # (iv) provider pair narrowness — n=2(guardian×nyt)로는 (i)/(ii) 구조적 구분 불가.
    if len([p for p in providers if p]) <= 2:
        hyps.append({
            "cause": RC_PROVIDER_NARROW, "signal": "plausible",
            "basis": "only 2 providers (guardian×nyt) — a 2-provider sample cannot structurally distinguish recall "
                     "limit from different-events; multi-outlet breadth (key-free RSS fleet / GDELT) would help"})
    # (v) time window mismatch — same-date 쌍이 존재하므로 약함(not_indicated 에 가까움).
    hyps.append({
        "cause": RC_TIME_WINDOW,
        "signal": "weak" if samples else "plausible",
        "basis": f"window={time_window}; all comparison pairs are same-date (date_bucket_match) so a window-spread "
                 "mismatch is a weak contributor here"})
    # (vi) source role metadata — 전부 publishable×publishable 이면 not_indicated.
    hyps.append({
        "cause": RC_SOURCE_ROLE_META,
        "signal": "not_indicated" if all_article else "plausible",
        "basis": "all top samples are publishable×publishable (article/official) — source-role metadata is present "
                 "and correct, so a role-metadata gap is not indicated"})
    # (vii) unknown — confidence indeterminate 의 명시.
    hyps.append({
        "cause": RC_UNKNOWN, "signal": "supporting",
        "basis": "a single bounded run cannot empirically separate the above — the gap cause is unresolved (ADR#64 "
                 "and ADR#77 both note n=2 / single broad-topic runs cannot distinguish these)"})

    plausible_or_supporting = sum(1 for h in hyps
                                  if h["signal"] in ("supporting", "plausible")
                                  and h["cause"] in (RC_SAME_EVENT_MISSED, RC_DIFFERENT_EVENTS,
                                                     RC_TITLE_NORM, RC_PROVIDER_NARROW))
    confidence = "indeterminate" if plausible_or_supporting >= 2 else "low"
    return {
        "near_match_gap_status": NMG_ALL_BELOW_HARD_FLOOR,
        "root_cause_hypotheses": hyps,
        "root_cause_confidence": confidence,
        "diagnostic_basis": {
            "band_distribution": dist,
            "max_cross_source_title_jaccard": round(max_jac, 4),
            "hard_floor": hard_floor,
            "near_floor": band_diagnostic.get("near_floor"),
            "top_below_floor_sample_count": len(samples),
            "samples_sharing_ge2_tokens": shared_ge2,
            "samples_sharing_zero_tokens": shared_zero,
            "title_normalization": norm,
            "providers": [p for p in providers if p],
            "time_window": time_window,
        },
        "same_event_truth_asserted": False,
        "raw_body_stored": False,
    }


# ── §8 provider expansion plan(official/news 만 anchor·search URL-candidate-only·community/market/catalog 거부) ──
def build_provider_expansion_plan() -> dict:
    """Guardian×NYT 가 부족할 때 official/news source role 을 유지하며 가능한 확장 경로(기계적·secret 0·network 0).

    search 는 URL candidate only(truth 아님). community/market/catalog 는 anchor 금지. credential env 이름만(값 0)."""
    providers = [
        {"provider_name": "guardian", "source_role": "news", "query_capability": "topic+time_window",
         "credential_required": "GUARDIAN_API_KEY", "readiness_status": "wired_present",
         "expected_overlap_usefulness": "high (with NYT, narrow event seed)", "rate_limit_policy": "5s/600s cooldown",
         "legal_tos_caution": "free tier ~5000/day; attribute", "integration_cost": "none (wired)",
         "next_action": "use in targeted narrow-event runs (current lane)"},
        {"provider_name": "nyt", "source_role": "news", "query_capability": "topic+time_window",
         "credential_required": "NYT_API_KEY", "readiness_status": "wired_present",
         "expected_overlap_usefulness": "high (with Guardian)", "rate_limit_policy": "12s (~5 req/min)",
         "legal_tos_caution": "free tier ~500/day; attribute", "integration_cost": "none (wired)",
         "next_action": "use in targeted narrow-event runs (current lane)"},
        {"provider_name": "gdelt", "source_role": "official", "query_capability": "topic+time_window (key-free)",
         "credential_required": None, "readiness_status": "wired_native",
         "expected_overlap_usefulness": "high (multi-outlet aggregation — real cross-source overlap generator)",
         "rate_limit_policy": "60s interval / 900s 429 cooldown / no tight retry",
         "legal_tos_caution": "429-prone; honor cooldown (no-bypass)", "integration_cost": "none (wired)",
         "next_action": "bounded use with cooldown honored; complements guardian/nyt for breadth"},
        {"provider_name": "rss_fleet", "source_role": "news",
         "query_capability": "feed-only (latest headlines; NOT arbitrary topic query)",
         "credential_required": None, "readiness_status": "wired_native",
         "expected_overlap_usefulness": "high for current breaking events (BBC/AP/AlJazeera/Verge/TechCrunch + KO outlets — multi-outlet)",
         "rate_limit_policy": "shared host gate min-spacing (no-bypass)", "legal_tos_caution": "per-outlet RSS terms",
         "integration_cost": "none (wired)",
         "next_action": "harvest latest, measure cross-outlet overlap on whatever is currently breaking (key-free lever)"},
        {"provider_name": "sec_edgar", "source_role": "official", "query_capability": "full-text search (key-free)",
         "credential_required": None, "readiness_status": "wired_native",
         "expected_overlap_usefulness": "narrow (corporate filings/regulatory events only)",
         "rate_limit_policy": "fair-use; UA required", "legal_tos_caution": "SEC fair access",
         "integration_cost": "none (wired)", "next_action": "use for corporate/regulatory event lanes"},
        {"provider_name": "federal_register", "source_role": "official", "query_capability": "topic+time_window (key-free)",
         "credential_required": None, "readiness_status": "wired_native",
         "expected_overlap_usefulness": "narrow (US rulemaking events)", "rate_limit_policy": "fair-use",
         "legal_tos_caution": "public domain", "integration_cost": "none (wired)",
         "next_action": "use for US regulatory event lanes"},
        {"provider_name": "naver_news_search", "source_role": "news", "query_capability": "topic (Korean)",
         "credential_required": "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET", "readiness_status": "cataloged_not_wired",
         "expected_overlap_usefulness": "high for Korean cross-source (KO floor lever)",
         "rate_limit_policy": "Naver OpenAPI quota", "legal_tos_caution": "Naver OpenAPI terms; attribution",
         "integration_cost": "adapter wiring + credential", "next_action": "WIRE adapter for KO topic-targeted overlap (provider expansion)"},
        {"provider_name": "newsapi / gnews", "source_role": "news", "query_capability": "topic+time_window",
         "credential_required": "NEWSAPI_API_KEY / GNEWS_API_KEY", "readiness_status": "cataloged_not_wired",
         "expected_overlap_usefulness": "medium (aggregator — resolve to publishable canonical before anchor)",
         "rate_limit_policy": "per-plan quota", "legal_tos_caution": "aggregator ToS; may require canonical resolution",
         "integration_cost": "adapter wiring + credential",
         "next_action": "evaluate ToS; wire as breadth augmenter (anchor only if canonical resolves publishable)"},
        {"provider_name": "serper / tavily / exa", "source_role": "search", "query_capability": "web/neural search",
         "credential_required": "SERPER_API_KEY / TAVILY_API_KEY / EXA_API_KEY", "readiness_status": "cataloged_not_wired",
         "expected_overlap_usefulness": "URL candidate discovery only (NOT truth, NOT an anchor)",
         "rate_limit_policy": "per-plan quota", "legal_tos_caution": "search ToS; results are pointers",
         "integration_cost": "adapter wiring + credential",
         "next_action": "URL-candidate lane only — resolve to a publishable canonical before any anchor use"},
    ]
    return {
        "providers": providers,
        "anchor_eligible_roles": ["official", "article", "news"],
        "reaction_layer_only": ["community"],
        "signal_layer_only": ["market"],
        "enrichment_only": ["catalog"],
        "url_candidate_only": ["search"],
        "wired_query_capable_publishable_besides_guardian_nyt": ["gdelt", "sec_edgar", "federal_register"],
        "wired_multi_outlet_feed_only": ["rss_fleet"],
        "rule": "do not add community/market/catalog as anchor; do not use search result as truth; do not bypass "
                "source role guard; honor provider rate/cooldown (no-bypass)",
        "ready": True,
    }


# ── §9 Korean source strategy(KO official/news anchor 가능·community reaction-only·KO floor 가시) ──────────────
def build_korean_source_strategy() -> dict:
    """R1 KO calibration floor(>=50 KO gold)용 Korean source 전략(기계적·secret 0). KO floor 는 영문 Guardian×NYT 로
    해결되지 않는다 — 별도 KO lane 필요. community 는 reaction layer only·market/catalog/search 는 anchor 금지."""
    sources = [
        {"source_name": "yonhap (yna)", "source_role": "news", "query_capability": "RSS feed-only",
         "credential_required": None, "rate_limit": "shared host gate", "canonical_url_availability": True,
         "title_availability": True, "published_at_availability": True, "body_availability": False,
         "legal_tos_caution": "Yonhap RSS terms; attribution",
         "r1_ko_floor_contribution": "multi-outlet KO overlap via RSS overlap fetcher (time-window, not topic query)"},
        {"source_name": "hankyung / maekyung", "source_role": "news", "query_capability": "RSS feed-only",
         "credential_required": None, "rate_limit": "shared host gate", "canonical_url_availability": True,
         "title_availability": True, "published_at_availability": True, "body_availability": False,
         "legal_tos_caution": "outlet RSS terms", "r1_ko_floor_contribution": "KO business-news cross-outlet overlap (feed-only)"},
        {"source_name": "zdnet_korea / etnews", "source_role": "news", "query_capability": "HTML feed-only",
         "credential_required": None, "rate_limit": "shared host gate", "canonical_url_availability": True,
         "title_availability": True, "published_at_availability": True, "body_availability": False,
         "legal_tos_caution": "outlet terms", "r1_ko_floor_contribution": "KO tech-news cross-outlet overlap (feed-only)"},
        {"source_name": "naver_news_search", "source_role": "news", "query_capability": "topic (Korean, query-capable)",
         "credential_required": "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET", "rate_limit": "Naver OpenAPI quota",
         "canonical_url_availability": True, "title_availability": True, "published_at_availability": True,
         "body_availability": False, "legal_tos_caution": "Naver OpenAPI terms; attribution",
         "r1_ko_floor_contribution": "NOT wired — wiring the adapter enables KO topic-targeted cross-source overlap (best KO floor lever)"},
    ]
    return {
        "sources": sources,
        "rules": [
            "Korean community (DCinside/FMKorea/Naver blog) is a reaction layer only — never an event anchor",
            "Korean market/catalog/search cannot anchor events",
            "Korean official/news may anchor if publishable and source role verified",
            "Korean tokenization lacks morpheme segmentation -> KO Jaccard is harder; KO-aware normalization needed",
            "KO floor (>=50 KO gold) is NOT solved by the English Guardian/NYT pair",
        ],
        "wired_ko_live_query_source": None,             # 정직: topic-query 가능 KO source 미배선(RSS feed-only만).
        "ko_floor_required_gold": 50,
        "ko_floor_current_gold": 0,
        "ko_floor_gap_visible": True,
        "ready": True,
    }


# ── Lane E: product bridge contract readiness(계약 정의됨·runtime 0) ──────────────────────────────────────
def _contract_readiness() -> dict:
    """LLM evidence packet / RAG ingestion gate / KG edge eligibility / community reaction layer / public IU gate 의
    **계약** 준비 상태(이 ADR 가 문서로 정의). ready=계약 존재 — **실 runtime 아님**(llm/embedding/merge/public IU 전부 0)."""
    return {
        "llm_evidence_packet_contract_ready": True,
        "rag_ingestion_gate_ready": True,
        "kg_edge_eligibility_contract_ready": True,
        "community_reaction_layer_contract_ready": True,
        "public_iu_gate_ready": True,
        "contract_docs": dict(CONTRACT_DOCS),
        "runtime_built": False,            # 계약만·실 runtime 미구축(R1~R7 No-Go).
    }


def _live_call_count(results: list[tuple[dict, dict]]) -> int:
    """실제 network 시도 수(provider_status 가 network-attempt 상태인 provider 합산·secret 0)."""
    n = 0
    for _seed, smoke in results:
        for st in (smoke.get("provider_status_by_provider") or {}).values():
            if st in _NETWORK_ATTEMPT_STATUSES:
                n += 1
    return n


def _select_best_smoke(results: list[tuple[dict, dict]]) -> dict:
    """production state 를 가장 멀리 끌고 간 seed 의 smoke(near/hard/fingerprint cross 쌍 → cross_pair 순)."""
    if not results:
        return run_cross_source_live_overlap_smoke(live_query=False)   # 시도 0(not_opted_in) — 안전 기본.

    def key(item: tuple[dict, dict]) -> tuple[int, int]:
        _seed, s = item
        detect = int(s.get("near_match_count") or 0) + int(s.get("hard_negative_count") or 0) \
            + int(s.get("fingerprint_overlap_count") or 0)
        return (detect, int(s.get("cross_source_pair_count") or 0))

    return max(results, key=key)[1]


def _aggregate_band_diagnostic(results: list[tuple[dict, dict]]) -> Optional[dict]:
    """seed 별 band_diagnostic 합산(band 분포 sum·max Jaccard·최고중첩 샘플 top-k·body 0). 전부 None 이면 None."""
    bds = [s.get("band_diagnostic") for _seed, s in results if s.get("band_diagnostic")]
    if not bds:
        return None
    dist = {"fingerprint": 0, "near_match": 0, "hard_negative": 0, "below_floor": 0}
    cross_pair = 0
    samples: list[dict] = []
    max_jac = 0.0
    near_floor = hard_floor = None
    norm = None
    for bd in bds:
        d = bd.get("band_distribution") or {}
        for k in dist:
            dist[k] += int(d.get(k, 0))
        cross_pair += int(bd.get("cross_source_pair_count") or 0)
        max_jac = max(max_jac, float(bd.get("max_cross_source_title_jaccard") or 0.0))
        samples.extend(bd.get("top_below_floor_samples") or [])
        near_floor = bd.get("near_floor") if near_floor is None else near_floor
        hard_floor = bd.get("hard_floor") if hard_floor is None else hard_floor
        norm = bd.get("title_normalization") if norm is None else norm
    samples.sort(key=lambda s: s.get("title_token_jaccard") or 0.0, reverse=True)
    return {
        "cross_source_pair_count": cross_pair,
        "band_distribution": dist,
        "max_cross_source_title_jaccard": round(max_jac, 4),
        "near_floor": near_floor,
        "hard_floor": hard_floor,
        "top_below_floor_samples": samples[:5],
        "title_normalization": norm or {},
        "raw_body_stored": False,
        "same_event_truth_asserted": False,
        "seed_band_diagnostic_count": len(bds),
    }


def _acquisition_strategy_next(gap: dict, production_candidate_status: str) -> dict:
    """진단 + status → 다음 acquisition 전략(기계적·LLM 0). near-match 0 을 LLM 으로 바로 점프하지 않는다."""
    status = gap.get("near_match_gap_status")
    if production_candidate_status not in PCAND_BLOCKED_STATES:
        return {
            "primary": "freeze the live-derived production-candidate worklist and recruit >=2 pseudonymous reviewers "
                       "per pair; collect returned label JSONL (no system sending); gold stays 0 until labels import",
            "levers": ["reviewer contact", "returned label intake", "calibration"],
            "next_blocker": "reviewer contact + returned labels",
        }
    if status == NMG_ALL_BELOW_HARD_FLOOR:
        return {
            "primary": "separate (i) recall-limit vs (ii) different-events empirically before any LLM: re-run bounded "
                       "narrow same-event seeds with band capture; inspect top below-floor shared tokens",
            "levers": [
                "if top pairs share entity tokens but stay <0.2 -> recall/normalization lane: KO/EN-aware light "
                "stemming + entity alias + deterministic semantic_candidate_scorer top-k reviewer triage (no LLM)",
                "if 0-shared-token pairs dominate -> different-events: add provider breadth (key-free RSS multi-outlet "
                "fleet, GDELT cooldown-honored) and/or wire Naver/NewsAPI adapter (KO/breadth)",
                "keep source role guard intact; semantic adjudicator stays deferred + MERGE_GATE-gated",
            ],
            "next_blocker": "targeted narrow-event live acquisition + provider breadth (not LLM, not credential)",
        }
    if status == NMG_NO_CROSS_OVERLAP:
        return {
            "primary": "broaden window/topic slightly or add a wired publishable provider so two outlets co-report; "
                       "the key-free RSS multi-outlet fleet is the lowest-cost breadth lever",
            "levers": ["wider time window", "provider breadth (RSS fleet / GDELT)", "narrower-but-covered event seed"],
            "next_blocker": "cross-source co-reporting (provider/window)",
        }
    return {
        "primary": "credentials/opt-in are not the blocker — the blocker is same-event candidate acquisition strategy",
        "levers": ["targeted seeds", "provider breadth", "normalization recall"],
        "next_blocker": "same-event candidate acquisition strategy",
    }


# ── §4 통합 entrypoint ───────────────────────────────────────────────────────────────────────────────────
def run_targeted_live_acquisition_and_near_match_diagnostic(
    *, directory: Optional[Any] = None, batch_id: str = PROD_BATCH_ID, as_of: Optional[str] = None,
    live_query: bool = False, seeds: Optional[list[dict]] = None,
    transport_factory: Optional[Callable[[str, str], Optional[Callable[[str], Optional[str]]]]] = None,
    env_probe_fn: Optional[Callable[[str], dict]] = None, host_gate: Any = None,
    readiness_fn: Optional[Callable[[], dict]] = None, gate_fn: Optional[Callable[..., dict]] = None,
    synthetic_batch_fn: Optional[Callable[..., dict]] = None,
) -> dict:
    """targeted live acquisition + near-match gap diagnostic(병합 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0).

    1) seed 검증(§6) → 2) bounded·governed·secret-safe targeted live(opt-in·승인 시만·emit_band_diagnostic) →
    3) near-match gap 진단(§5·양가 보존·단정 0) → 4) best seed 를 ADR#76 production candidate gate 에 통과(6-state·
    freeze·R1 gap·contract 재사용) → 5) Lane D plan(provider/Korean) + Lane E contract readiness → 6) 안전 플래그.
    어떤 경로도 입력 날조·merge·LLM·embedding·DB·전송·secret read·same_event 확정·label 생성·public IU 를 하지 않는다.

    test: transport_factory(seed_id,provider)→transport + env_probe_fn 주입 시 결정론(network 0·실 `.env` 미접촉)."""
    use_seeds = list(seeds) if seeds is not None else list(TARGETED_QUERY_SEEDS)
    seed_validations = [validate_query_seed(s) for s in use_seeds]
    valid_seeds = [s for s, v in zip(use_seeds, seed_validations, strict=True) if v["valid"]]

    providers_used = [_PROVIDER_A, _DEFAULT_PROVIDER_B]

    # ── targeted live(또는 dry) per-seed smoke(emit_band_diagnostic·secret-safe) ──
    results: list[tuple[dict, dict]] = []
    for s in valid_seeds:
        ta = transport_factory(s["seed_id"], _PROVIDER_A) if transport_factory else None
        tb = transport_factory(s["seed_id"], _DEFAULT_PROVIDER_B) if transport_factory else None
        smoke = run_cross_source_live_overlap_smoke(
            topic=s["topic"], topic_key=s.get("topic_key", s["seed_id"]),
            time_window=s.get("time_window", "1d"), live_query=live_query,
            transport_a=ta, transport_b=tb, env_probe_fn=env_probe_fn, host_gate=host_gate,
            emit_band_diagnostic=True)
        results.append((s, smoke))

    best_smoke = _select_best_smoke(results)
    live_call_count = _live_call_count(results)
    live_call_performed = any(bool(sm.get("live_query_attempted")) for _s, sm in results)
    agg_band = _aggregate_band_diagnostic(results)

    # ── near-match gap 진단(§5·양가 보존) ──
    gap = classify_near_match_gap(
        agg_band, cross_source_pair_count=int(best_smoke.get("cross_source_pair_count") or 0),
        providers=providers_used, time_window=ADR77_TIME_WINDOW if not valid_seeds else valid_seeds[0].get("time_window", "1d"))

    # ── ADR#76 production candidate gate 재사용(best seed → 6-state·freeze·R1 gap·contract·actual input) ──
    prod = run_r1_production_candidate_acquisition(
        directory=directory, batch_id=batch_id, as_of=as_of, live_query=live_query,
        acquire_fn=lambda *, live_query: best_smoke,
        readiness_fn=readiness_fn, gate_fn=gate_fn, synthetic_batch_fn=synthetic_batch_fn)

    production_candidate_status = prod["production_candidate_status"]
    blocked = production_candidate_status in PCAND_BLOCKED_STATES
    contracts = _contract_readiness()
    provider_plan = build_provider_expansion_plan()
    ko_strategy = build_korean_source_strategy()
    strategy_next = _acquisition_strategy_next(gap, production_candidate_status)

    # per-seed sanitized 요약(title 전문/score/rationale 0 — band 카운트만).
    seed_results = []
    for s, sm in results:
        bd = sm.get("band_diagnostic") or {}
        seed_results.append({
            "seed_id": s["seed_id"], "topic": s["topic"], "time_window": s.get("time_window"),
            "event_type": s.get("event_type"),
            "provider_status": sm.get("provider_status_by_provider") or {},
            "records_by_provider": sm.get("records_count_by_provider") or {},
            "cross_source_pair_count": sm.get("cross_source_pair_count") or 0,
            "band_distribution": bd.get("band_distribution"),
            "max_cross_source_title_jaccard": bd.get("max_cross_source_title_jaccard"),
            "block_reasons": sm.get("block_reasons") or [],
        })

    blocked_reason = production_candidate_status if blocked else ""
    block_reasons = list(prod.get("block_reasons") or [])
    if gap["near_match_gap_status"] in (NMG_ALL_BELOW_HARD_FLOOR, NMG_NO_CROSS_OVERLAP):
        block_reasons = list(dict.fromkeys([gap["near_match_gap_status"], *block_reasons]))
    next_actions = list(dict.fromkeys([strategy_next["primary"], *(prod.get("next_actions") or [])]))

    # §11 internal ops sanitized frontier(same_event truth·score·rationale·predicted·raw body·PII·secret 부재).
    internal_ops_acquisition_frontier = {
        "contract": "InternalOpsAcquisitionFrontier",
        "near_match_gap_status": gap["near_match_gap_status"],
        "root_cause_hypotheses": [{"cause": h["cause"], "signal": h["signal"]} for h in gap["root_cause_hypotheses"]],
        "root_cause_confidence": gap["root_cause_confidence"],
        "targeted_query_seed_count": len(valid_seeds),
        "live_attempt_count": live_call_count,
        "live_candidate_count": int(best_smoke.get("cross_source_pair_count") or 0),
        "publishable_pair_count": prod["publishable_pair_count"],
        "production_candidate_status": production_candidate_status,
        "production_candidate_batch_ready": prod["production_candidate_batch_ready"],
        "candidate_provenance": prod["candidate_provenance"],
        "provider_expansion_plan_ready": provider_plan["ready"],
        "korean_source_strategy_ready": ko_strategy["ready"],
        "blocked_reason": blocked_reason,
        "current_r1_gap": prod["current_r1_gap"],
        "production_gold_count": prod["production_gold_count"],
        "r2_r7_no_go": True,
        "required_copy": list(REQUIRED_OPS_COPY),
        "flags": {"no_public_truth": True, "no_same_event_truth": True, "no_score": True,
                  "no_rationale": True, "no_predicted_status": True, "no_raw_body": True, "no_secret": True},
    }

    result = {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        # actual input 재확인(ADR#72 gate passthrough via prod).
        "actual_input_rechecked": prod["actual_input_rechecked"],
        "actual_contact_evidence_found": prod["actual_contact_evidence_found"],
        "actual_returned_labels_found": prod["actual_returned_labels_found"],
        "actual_input_status": prod["actual_input_status"],
        # ADR#77 baseline(실측 인용·날조 0).
        "adr77_live_result_loaded": True,
        "adr77_live_candidate_count": ADR77_LIVE_CANDIDATE_COUNT,
        "adr77_publishable_pair_count": ADR77_PUBLISHABLE_PAIR_COUNT,
        "adr77_topic": ADR77_TOPIC,
        "adr77_time_window": ADR77_TIME_WINDOW,
        # near-match gap 진단(§5·양가 보존·단정 0).
        "near_match_gap_status": gap["near_match_gap_status"],
        "root_cause_hypotheses": gap["root_cause_hypotheses"],
        "root_cause_confidence": gap["root_cause_confidence"],
        "diagnostic_basis": gap["diagnostic_basis"],
        "band_diagnostic": agg_band,
        "raw_body_stored": False,
        "same_event_truth_asserted": False,
        # targeted live acquisition(§6·opt-in·governed).
        "targeted_live_query_approved": bool(live_query),
        "targeted_live_query_executed": live_call_performed,
        "targeted_query_seeds": [
            {"seed_id": s["seed_id"], "topic": s["topic"], "time_window": s.get("time_window"),
             "event_type": s.get("event_type"), "seed_rationale": s.get("rationale")} for s in use_seeds],
        "targeted_query_seed_validations": seed_validations,
        "targeted_query_seed_results": seed_results,
        "providers_used": providers_used,
        "live_call_count": live_call_count,
        "live_candidate_count": int(best_smoke.get("cross_source_pair_count") or 0),
        "publishable_pair_count": prod["publishable_pair_count"],
        # production candidate(ADR#76 gate 재사용·freeze·둔갑 0).
        "production_candidate_status": production_candidate_status,
        "production_candidate_batch_ready": prod["production_candidate_batch_ready"],
        "production_batch_id": prod["production_batch_id"],
        "production_frozen_pair_count": prod["production_frozen_pair_count"],
        "candidate_provenance": prod["candidate_provenance"],
        "ready_for_manual_launch": prod["ready_for_manual_launch"],
        "expected_label_files": prod["expected_label_files"],
        "validation_command": prod["validation_command"],
        "blocked_reason": blocked_reason,
        # acquisition strategy(Lane D).
        "acquisition_strategy_next": strategy_next,
        "provider_expansion_plan": provider_plan,
        "provider_expansion_plan_ready": provider_plan["ready"],
        "korean_source_strategy": ko_strategy,
        "korean_source_strategy_ready": ko_strategy["ready"],
        # product bridge contracts(Lane E·runtime 0).
        "llm_evidence_packet_contract_ready": contracts["llm_evidence_packet_contract_ready"],
        "rag_ingestion_gate_ready": contracts["rag_ingestion_gate_ready"],
        "kg_edge_eligibility_contract_ready": contracts["kg_edge_eligibility_contract_ready"],
        "community_reaction_layer_contract_ready": contracts["community_reaction_layer_contract_ready"],
        "public_iu_gate_ready": contracts["public_iu_gate_ready"],
        "product_bridge_runtime_built": contracts["runtime_built"],
        # R1 gap(prod passthrough).
        "production_gold_count": prod["production_gold_count"],
        "current_r1_gap": prod["current_r1_gap"],
        "r1_status": prod["r1_status"],
        "r2_r7_no_go": True,
        # 안전 경계(정직·constant + prod 파생).
        "public_truth_exposed": False,
        "same_event_truth_exposed": False,
        "score_exposed": prod["score_exposed"],
        "rationale_exposed": prod["rationale_exposed"],
        "predicted_status_exposed": prod["predicted_status_exposed"],
        "raw_pii_exposed": prod["raw_pii_exposed"],
        "raw_source_body_exposed": False,
        "no_public_intelligence_unit": True,
        "merge_allowed": prod["merge_allowed"],
        "db_write": prod["db_write"],
        "llm_invoked": prod["llm_invoked"],
        "embedding_invoked": prod["embedding_invoked"],
        "actual_sending_performed": False,
        # internal ops sanitized frontier(§11).
        "internal_ops_acquisition_frontier": internal_ops_acquisition_frontier,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·드리프트 fail-loud).
    _assert_pii_safe(result, _path="r1_targeted_live_acquisition_output")
    return result


# ── CLI(기본 시도 0·network 0·DB 0·전송 0·secret read 0; --live-query 로 opt-in bounded targeted acquisition) ──
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="R1 targeted live acquisition + near-match gap diagnostic "
                    "(ADR#78·병합 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0).")
    parser.add_argument("--batch-id", default=PROD_BATCH_ID, help="production-candidate freeze batch id.")
    parser.add_argument("--input-dir", metavar="DIR", help="실 입력 디렉터리(미지정 시 canonical). 코드가 생성하지 않음.")
    parser.add_argument("--as-of", metavar="ISO_DATE", help="overdue 산정 기준일(ISO).")
    parser.add_argument(
        "--live-query", action="store_true",
        help="명시적 opt-in: 양 provider credential present 일 때만 bounded targeted live fetch(network·CI 아님·값 미노출).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    host_gate = None
    if ns.live_query:
        try:   # shared host gate 주입 → cross-process host floor 참여(no-bypass). 실패해도 best-effort.
            from pathlib import Path as _P

            from ingestion.orchestration.host_rate_gate import HostRateGate
            host_gate = HostRateGate(state_path=_P("ingestion/outputs/state/host_rate_gate.json"))
        except Exception:
            host_gate = None

    out = run_targeted_live_acquisition_and_near_match_diagnostic(
        directory=ns.input_dir, batch_id=ns.batch_id, as_of=ns.as_of,
        live_query=ns.live_query, host_gate=host_gate)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']}")
    print(f"- actual_input: status={out['actual_input_status']} returned_labels={out['actual_returned_labels_found']}")
    print(f"- adr77_baseline: candidates={out['adr77_live_candidate_count']} publishable={out['adr77_publishable_pair_count']} "
          f"topic={out['adr77_topic']!r}")
    print(f"- targeted: approved={out['targeted_live_query_approved']} executed={out['targeted_live_query_executed']} "
          f"seeds={[s['seed_id'] for s in out['targeted_query_seeds']]} live_calls={out['live_call_count']}")
    for sr in out["targeted_query_seed_results"]:
        print(f"  · {sr['seed_id']}: provider_status={sr['provider_status']} cross_pairs={sr['cross_source_pair_count']} "
              f"band={sr['band_distribution']} max_jac={sr['max_cross_source_title_jaccard']}")
    print(f"- near_match_gap: status={out['near_match_gap_status']} confidence={out['root_cause_confidence']}")
    for h in out["root_cause_hypotheses"]:
        print(f"  · [{h['signal']}] {h['cause']}")
    print(f"- candidates: live={out['live_candidate_count']} publishable={out['publishable_pair_count']} "
          f"status={out['production_candidate_status']} provenance={out['candidate_provenance']}")
    print(f"- production_batch: ready={out['production_candidate_batch_ready']} frozen={out['production_frozen_pair_count']}")
    print(f"- strategy_next: {out['acquisition_strategy_next']['primary']}")
    print(f"  · next_blocker: {out['acquisition_strategy_next']['next_blocker']}")
    print(f"- plans: provider_expansion_ready={out['provider_expansion_plan_ready']} "
          f"korean_ready={out['korean_source_strategy_ready']} ko_floor_gap_visible={out['korean_source_strategy']['ko_floor_gap_visible']}")
    print(f"- contracts: llm_packet={out['llm_evidence_packet_contract_ready']} rag_gate={out['rag_ingestion_gate_ready']} "
          f"kg_edge={out['kg_edge_eligibility_contract_ready']} public_iu_gate={out['public_iu_gate_ready']} runtime_built={out['product_bridge_runtime_built']}")
    print(f"- r1_gap: production={out['production_gold_count']} gap={out['current_r1_gap']} r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- gates: merge={out['merge_allowed']} llm={out['llm_invoked']} embedding={out['embedding_invoked']} "
          f"db_write={out['db_write']} sending={out['actual_sending_performed']} public_iu={out['no_public_intelligence_unit']}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

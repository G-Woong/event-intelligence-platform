"""ADR#87 — official×news live acquisition (regulatory seed → FR official + news → bridge → freeze attempt).

ADR#86 가 배선한 것: Federal Register window-honoring **official** adapter + official×news role-bridge(PURE) +
FR live date-honoring 검증(live_verified). 그러나 그것들은 **분리된 부품** 이다 — operator 가 핀한 regulatory-class
event 를 official(FR) 과 news(guardian/nyt) **양쪽에서 같은 window 로 수집** 해 bridge 를 *실제 live records* 에
적용하고 production candidate freeze 를 시도하는 acquisition loop 가 없었다(R-OfficialNewsDomainMismatch: official
문서와 news 보도가 같은 subject 로 만나는 일이 드물어 ADR#86 yield 0).

이 모듈은 그 loop 다(재구현이 아니라 orchestrator):
  - seed: `regulatory_event_seed_bank.validate_regulatory_seed`(official_query≠news_query·broad reject·same_event 0).
  - official fetch: `federal_register_live_smoke.run_federal_register_live_smoke`(key-free·date-honoring 검증·raw body 0).
  - news fetch: `provider_query_adapters.run_provider_query`(guardian/nyt·**enforce_window=True**·Guardian/NYT
    date_filter_ignored hedge·in-window 만).
  - bridge: `official_news_role_bridge`(date proximity + entity/action token·title-Jaccard 미사용·reviewer-routing only).
  - freeze: `r1_production_candidate_acquisition.run_r1_production_candidate_acquisition`(freeze_eligible 의 **실제 record
    pair**(title 포함)를 official×news smoke 로 구성·publishable×publishable[official+article] 만·합성 둔갑 0·gold 0).
  - handoff: `reviewer_handoff_bridge.build_reviewer_handoff_bridge`(freeze→contact-PRE·전송 0).

절대 불변(상속·상용 안전 계약):
  - **official ≠ news role**: official(authoritative evidence)과 news(public reporting)를 같은 role 로 섞지 않는다.
    official 단독으로 cross-source production candidate 가 되지 않는다(bridge 는 official×news 양 role 있을 때만).
  - **adapter wired ≠ candidate · live_verified ≠ candidate · bridge candidate ≠ truth**: bridge candidate 는
    reviewer-routing 후보일 뿐 same_event 단정·gold 가 아니다. freeze 는 reviewer worklist(production_gold_count 0).
  - **news side enforce_window**: Guardian/NYT 는 응답이 window 를 무시할 수 있어 post-filter 강제(out-of-window 동결 금지).
  - **merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · secret read 0 · raw body 0 · public IU 0 · score 0**.
  test: transport_fr/transport_news(fake)+env_*_fn 주입 시 결정론(network 0·실 `.env` 미접촉·key 불요).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Optional

from backend.app.services.identity_human_labeling import SOURCE_LIVE
from backend.app.tools.federal_register_live_smoke import run_federal_register_live_smoke
from backend.app.tools.official_news_role_bridge import (
    _role,
    build_official_news_bridge,
    iter_freeze_eligible_record_pairs,
)
from backend.app.tools.provider_query_adapters import (
    ALL_ADAPTER_PROVIDERS,
    run_provider_query,
)
from backend.app.tools.r1_production_candidate_acquisition import (
    PROD_BATCH_ID,
    run_r1_production_candidate_acquisition,
)
from backend.app.tools.regulatory_event_seed_bank import validate_regulatory_seed
from backend.app.tools.reviewer_batch_launch import build_reviewer_instruction
from backend.app.tools.reviewer_handoff_bridge import build_reviewer_handoff_bridge
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "official_news_live_acquisition"
_NEWS_PROVIDERS_DEFAULT = ("guardian", "nyt")

# ── §9 official_news_live_status 어휘(결과 분류·둔갑 0) ─────────────────────────────────────────────────────
ONL_NOT_RUN = "not_run"
ONL_INVALID_SEED = "invalid_regulatory_seed"
ONL_BLOCKED_NO_OPT_IN = "blocked_no_live_opt_in"
ONL_PROVIDER_UNAVAILABLE = "provider_unavailable"
ONL_BLOCKED_HOST_GATE = "blocked_host_gate"
ONL_BLOCKED_RATE_LIMIT = "blocked_rate_limit"
ONL_OFFICIAL_NO_RECORDS = "official_no_records"
ONL_NEWS_NO_RECORDS = "news_no_records"
ONL_NO_IN_WINDOW_NEWS = "no_in_window_news"
ONL_NO_OVERLAP = "no_official_news_overlap"
ONL_BRIDGE_CANDIDATES_FOUND = "official_news_bridge_candidates_found"
ONL_PRODUCTION_BATCH_FROZEN = "production_batch_frozen"

_BLOCKED_STATUSES = frozenset({
    ONL_NOT_RUN, ONL_INVALID_SEED, ONL_BLOCKED_NO_OPT_IN, ONL_PROVIDER_UNAVAILABLE,
    ONL_BLOCKED_HOST_GATE, ONL_BLOCKED_RATE_LIMIT, ONL_OFFICIAL_NO_RECORDS, ONL_NEWS_NO_RECORDS,
    ONL_NO_IN_WINDOW_NEWS, ONL_NO_OVERLAP,
})

# §9 status → operator 한 줄 next action(internal ops UI·secret 0·PII 0).
_NEXT_ACTION = {
    ONL_INVALID_SEED: ("fix the regulatory seed before a live run (needs federal_register official provider, a "
                       "publishable news provider, a named agency/entity, an action phrase, an ISO date window, "
                       "and a non-broad topic)"),
    ONL_BLOCKED_NO_OPT_IN: ("approve a bounded official×news live run (live_approved=True / --live-query) — the "
                            "seed is a valid regulatory-class event shape (host/rate honored · raw body 0 · secret 0)"),
    ONL_PROVIDER_UNAVAILABLE: ("set the news provider credentials (GUARDIAN_API_KEY/NYT_API_KEY) in .env (secret "
                               "커밋 금지·값 미노출); Federal Register is key-free"),
    ONL_BLOCKED_HOST_GATE: "respect the shared host floor (no-bypass); retry after min_spacing",
    ONL_BLOCKED_RATE_LIMIT: "respect the provider cooldown (no tight retry)",
    ONL_OFFICIAL_NO_RECORDS: ("Federal Register returned no in-window official records for this seed — broaden the "
                              "official_query/window or pin a regulatory event with FR coverage"),
    ONL_NEWS_NO_RECORDS: ("news providers returned no records for this seed — broaden the news_query or pin an "
                          "event with public reporting"),
    ONL_NO_IN_WINDOW_NEWS: ("news providers returned records but none inside the pinned window — Guardian/NYT may "
                            "have ignored the date filter (enforce_window dropped them); verify the occurrence date"),
    ONL_NO_OVERLAP: ("official and news records exist but none share enough entity/action tokens within the date "
                     "tolerance — official (regulatory) and news (reporting) cover different subjects (domain "
                     "mismatch); pin an event both an FR document and a news outlet report on the same date"),
    ONL_BRIDGE_CANDIDATES_FOUND: ("official×news bridge candidates exist but none are freeze-eligible (both must be "
                                  "in-window) — verify the window or rerun; bridge is reviewer-routing, not truth"),
    ONL_PRODUCTION_BATCH_FROZEN: ("operator: manually distribute the frozen official×news production-candidate "
                                  "worklist to >=2 pseudonymous reviewers per pair (the task is: do the official "
                                  "record and the news record refer to the same regulatory event?); production gold "
                                  "stays 0 until returned labels import"),
}


def build_official_news_reviewer_instruction() -> dict:
    """§12 — official×news 전용 reviewer instruction(news×news 와 다름·official=evidence·news=reporting).

    reviewer 는 official record(authoritative evidence)와 news record(public reporting)가 **같은 실제 regulatory
    event** 를 가리키는지 판정한다. 같은 broad topic·agency 이름만으로 same_event 결정 금지(date+specific action 필요).
    label vocabulary 는 news×news 와 동일 단일 출처(build_reviewer_instruction)에서 가져온다(드리프트 0)."""
    vocab = build_reviewer_instruction().get("label_vocabulary") or []
    return {
        "purpose": ("Judge whether an OFFICIAL-source record and a NEWS record refer to the SAME real-world "
                    "regulatory event (title/metadata only · no raw body)."),
        "official_source_role": ("authoritative evidence (e.g. Federal Register rule/notice/enforcement) — high "
                                 "authority, dry regulatory text"),
        "news_source_role": ("public reporting evidence (news outlet) — public attention and narrative, may use "
                             "different wording than the official text"),
        "criteria": {
            "same_event": "both refer to the same dated regulatory action by the same agency/entity",
            "different_event": "same broad topic but a different specific regulatory action / different date",
            "unsure": "insufficient information to decide (canonical: insufficient)",
            "needs_review": "needs additional human adjudication (canonical: ambiguous)",
        },
        "forbidden": [
            "infer same_event from a shared broad topic alone",
            "treat the official source as more 'true' and auto-match to any news",
            "use title word overlap alone (official text and news headline use different wording)",
            "assert same_event from the agency name alone without the specific action and date",
            "use community/market reaction as the event anchor",
        ],
        "recommended": [
            "compare the agency/entity, the specific regulatory action, and the date window together",
            "use date proximity AND the specific action (not just the topic)",
            "leave unsure/needs_review when the specific action is unclear",
        ],
        "label_vocabulary": list(vocab),
        # §12 must not include — 구조적으로 False.
        "model_score_shown": False,
        "model_rationale_shown": False,
        "predicted_status_shown": False,
        "same_event_truth_asserted": False,
    }


def _time_window_for(start: str, end: str) -> str:
    """[start, end] span → run_provider_query time_window 토큰('1d'/'7d'). 8일+ 는 7d(현 adapter 지원 한계·정직)."""
    try:
        from datetime import datetime
        d0 = datetime.strptime(start, "%Y-%m-%d").date()
        d1 = datetime.strptime(end, "%Y-%m-%d").date()
        return "1d" if (d1 - d0).days <= 1 else "7d"
    except Exception:
        return "1d"


def _in_window(pub: Optional[str], window: tuple[str, str]) -> bool:
    """published_at(YYYY-MM-DD)가 [start, end] 안인가(ISO 사전식). 없음/형식불명/범위밖=False."""
    if not pub or len(pub) < 10:
        return False
    return window[0] <= pub[:10] <= window[1]


def _build_official_news_smoke(
    freeze_pairs: list[dict], *, providers: list[str], language: str = "en",
    reviewers: tuple[str, ...] = ("reviewer_a", "reviewer_b"),
) -> dict:
    """freeze-eligible (official, news) record pair → official×news 'smoke'(run_r1_production_candidate_acquisition
    freeze 입력). packet_rows 는 source_type_left=official·source_type_right=article(둘 다 publishable) + title(reviewer
    표시) — 기존 freeze 머신이 무수정으로 official×news 를 동결한다(_is_publishable_production_pair 통과). dataset_source=
    live_derived(합성 둔갑 0·실 live records). pair 당 reviewer ≥2(consensus capacity)."""
    packet_rows: list[dict] = []
    for fp in freeze_pairs:
        o, n = fp["official_record"], fp["news_record"]
        for rid in reviewers:
            packet_rows.append({
                "pair_id": fp["pair_id"],
                "reviewer_id": rid,            # raw → freeze 가 pseudonymize.
                "review_round": 1,
                "language": language,
                "source_type_left": _role(o),   # official.
                "source_type_right": _role(n),  # article(news).
                "title_left": o.get("title_or_label"),
                "title_right": n.get("title_or_label"),
                "observed_at_left": o.get("published_at_or_observed_at"),
                "observed_at_right": n.get("published_at_or_observed_at"),
                "canonical_url_left": o.get("canonical_url"),
                "canonical_url_right": n.get("canonical_url"),
            })
    pair_ids = sorted({fp["pair_id"] for fp in freeze_pairs})
    return {
        "live_query_attempted": True,
        "dataset_source": SOURCE_LIVE,
        "cross_source_pair_count": len(pair_ids),
        "reviewer_queue": {
            "packet_rows": packet_rows,
            "queue_pair_ids": pair_ids,
            "near_positive_count": len(pair_ids),
            "hard_negative_discovery_count": 0,
            "hard_negative_synthetic_count": 0,
        },
        "block_reasons": [],
        "next_actions": [],
        "providers": list(providers),
    }


def _fetch_news(
    *, news_providers: list[str], news_query: str, time_window: str, today: str,
    transport_news: Optional[dict], env_status_fn, host_gate,
) -> tuple[list[dict], dict, list[str]]:
    """news provider 별 in-window fetch(enforce_window=True). (combined_in_window_records, status_by_provider,
    block_reasons) 반환. 한 provider 라도 host/rate gate 면 block_reasons 에 표면화(둔갑 0)."""
    transport_news = transport_news or {}
    combined: list[dict] = []
    status_by_provider: dict[str, str] = {}
    block_reasons: list[str] = []
    for prov in news_providers:
        if prov not in ALL_ADAPTER_PROVIDERS:
            status_by_provider[prov] = "fetcher_not_wired"
            continue
        qr = run_provider_query(
            prov, topic=news_query, time_window=time_window, today=today,
            enforce_window=True,   # Guardian/NYT date_filter_ignored hedge(in-window 만·out-of-window 동결 금지).
            transport=transport_news.get(prov), env_status_fn=env_status_fn, host_gate=host_gate)
        status_by_provider[prov] = qr.status
        if qr.status == "ok":
            combined.extend(qr.records)
        elif qr.status == "host_gate_blocked":
            block_reasons.append("host_gate_blocked")
        elif qr.status == "rate_limited":
            block_reasons.append("rate_limited")
        elif qr.block_reason == "no_in_window_records":
            block_reasons.append("no_in_window_news")
    return combined, status_by_provider, block_reasons


def run_official_news_live_acquisition(
    seed: dict, *, live_approved: bool = False, today: Optional[str] = None,
    batch_id: str = PROD_BATCH_ID, directory: Optional[Any] = None,
    transport_fr: Optional[Callable[[str], Optional[str]]] = None,
    transport_news: Optional[dict] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    host_gate: Any = None,
    freeze_fn: Optional[Callable[..., dict]] = None,
    readiness_fn: Optional[Callable[[], dict]] = None,
    gate_fn: Optional[Callable[..., dict]] = None,
    synthetic_batch_fn: Optional[Callable[..., dict]] = None,
    date_tolerance_days: int = 1, min_shared_tokens: int = 2,
) -> dict:
    """regulatory seed → official(FR) + news(guardian/nyt) live acquisition → bridge → freeze attempt(§9~§12).

    기본 live_approved=False → 시도 0(blocked_no_live_opt_in·network 0). live_approved=True 일 때만 bounded governed
    fetch(FR key-free·news enforce_window=True). official×news bridge 의 freeze-eligible 후보가 있으면 그 **실제 record
    pair** 를 official×news smoke 로 묶어 production candidate freeze 를 시도(publishable×publishable·합성 둔갑 0·gold 0).
    merge 0·LLM/embedding 0·DB 0·전송 0·secret read 0·same_event 단정 0·raw body 0."""
    sv = validate_regulatory_seed(seed)
    regulatory_domain = str(seed.get("regulatory_domain") or "")
    selected_seed_id = seed.get("seed_id")
    start = str(seed.get("date_window_start") or "")
    end = str(seed.get("date_window_end") or "")
    official_query = str(seed.get("official_query") or "")
    news_query = str(seed.get("news_query") or "")
    news_providers = [p for p in (seed.get("news_providers") or _NEWS_PROVIDERS_DEFAULT)]

    fr_result: Optional[dict] = None
    bridge_result: Optional[dict] = None
    pcand: Optional[dict] = None
    official_in_window: list[dict] = []
    news_records: list[dict] = []
    news_status: dict[str, str] = {}
    freeze_pairs: list[dict] = []
    live_query_executed = False
    live_call_count = 0

    # ── ① seed 검증(fail-closed) ──
    if not sv["accepted"]:
        status = ONL_INVALID_SEED
    elif not live_approved:
        status = ONL_BLOCKED_NO_OPT_IN
    else:
        date_window = (start, end)
        anchor = today or end
        time_window = _time_window_for(start, end)

        # ── ② official fetch(FR·key-free·date-honoring 검증·raw body 0) ──
        fr_result = run_federal_register_live_smoke(
            topic=official_query, date_window=date_window, today=anchor, time_window=time_window,
            live_query=True, transport=transport_fr, env_status_fn=env_status_fn, host_gate=host_gate)
        live_call_count += int(fr_result.get("live_call_count") or 0)
        official_in_window = [
            r for r in (fr_result.get("official_records") or [])
            if _in_window(r.get("published_at_or_observed_at"), date_window)]

        # ── ③ news fetch(guardian/nyt·enforce_window=True·in-window 만) ──
        news_records, news_status, news_blocks = _fetch_news(
            news_providers=news_providers, news_query=news_query, time_window=time_window, today=anchor,
            transport_news=transport_news, env_status_fn=env_status_fn, host_gate=host_gate)
        # 실 network 시도가 일어난 status 만 카운트(ok/no_records/parser_error/network_error). credential/host/rate
        # gate 는 network 전 차단이라 미카운트(code-review NIT-4: 시도-후-실패한 HTTP 도 정직 회계).
        live_call_count += sum(
            1 for s in news_status.values() if s in ("ok", "no_records", "parser_error", "network_error"))

        # ── ④ bridge(official×news·date proximity + entity/action token·reviewer-routing only) ──
        bridge_result = build_official_news_bridge(
            official_in_window, news_records, date_window=date_window,
            date_tolerance_days=date_tolerance_days, min_shared_tokens=min_shared_tokens)
        freeze_pairs = iter_freeze_eligible_record_pairs(
            official_in_window, news_records, date_window=date_window,
            date_tolerance_days=date_tolerance_days, min_shared_tokens=min_shared_tokens)

        live_query_executed = bool(fr_result.get("live_query_executed")) or any(
            s == "ok" for s in news_status.values())

        # ── ⑤ 결과 분류(official 먼저·그다음 news·그다음 bridge·freeze) ──
        # host-gate 를 rate-limit **앞에** 검사(code-review NIT-1): federal_register_live_smoke._classify 가
        # host_gate_blocked 를 fr_live_rate_blocked 로 collapse 하므로, fr_result["host_gate_blocked"]=True 인 host-gate
        # 차단이 rate-limit 로 오분류돼 잘못된 next_action("respect cooldown")을 주는 것을 방지. host_gate_blocked 가
        # rate 와 구별자(rate-limit 은 host_gate_blocked=False) — host-gate 먼저 → 남은 fr_live_rate_blocked 는 진짜 rate.
        fr_gate = fr_result.get("fr_live_status")
        news_gate_blocked = "host_gate_blocked" in news_blocks
        news_rate_blocked = "rate_limited" in news_blocks
        if fr_result.get("host_gate_blocked") or news_gate_blocked:
            status = ONL_BLOCKED_HOST_GATE
        elif fr_gate == "fr_live_rate_blocked" or news_rate_blocked:
            status = ONL_BLOCKED_RATE_LIMIT
        elif all(s in ("missing_credentials", "fetcher_not_wired") for s in news_status.values()):
            status = ONL_PROVIDER_UNAVAILABLE
        elif not official_in_window:
            status = ONL_OFFICIAL_NO_RECORDS
        elif not news_records:
            status = ONL_NO_IN_WINDOW_NEWS if "no_in_window_news" in news_blocks else ONL_NEWS_NO_RECORDS
        elif bridge_result["bridge_candidate_count"] == 0:
            status = ONL_NO_OVERLAP
        elif not freeze_pairs:
            status = ONL_BRIDGE_CANDIDATES_FOUND
        else:
            # ── ⑥ freeze(freeze-eligible record pair → official×news smoke → production candidate freeze) ──
            providers_used = ["federal_register"] + [p for p, s in news_status.items() if s == "ok"]
            smoke = _build_official_news_smoke(freeze_pairs, providers=providers_used)
            pcand = (freeze_fn or run_r1_production_candidate_acquisition)(
                directory=directory, batch_id=batch_id, live_query=True,
                acquire_fn=lambda *, live_query: smoke,
                readiness_fn=readiness_fn, gate_fn=gate_fn, synthetic_batch_fn=synthetic_batch_fn)
            status = (ONL_PRODUCTION_BATCH_FROZEN if pcand.get("production_candidate_batch_ready")
                      else ONL_BRIDGE_CANDIDATES_FOUND)

    # ── ⑦ reviewer handoff(freeze→contact-PRE·전송 0·freeze 없으면 ready=False) ──
    handoff = build_reviewer_handoff_bridge(pcand or {}, live_run_status=status)
    official_news_instruction = build_official_news_reviewer_instruction()

    bridge_candidate_count = int((bridge_result or {}).get("bridge_candidate_count") or 0)
    freeze_eligible_count = int((bridge_result or {}).get("freeze_eligible_bridge_count") or 0)
    production_candidate_status = (pcand or {}).get("production_candidate_status") or "blocked"
    production_candidate_batch_ready = bool((pcand or {}).get("production_candidate_batch_ready"))
    production_frozen_pair_count = int((pcand or {}).get("production_frozen_pair_count") or 0)
    blocked_reason = status if status in _BLOCKED_STATUSES else ""
    next_action = _NEXT_ACTION.get(status, "investigate official×news live acquisition")

    out = {
        "operation_name": OPERATION_NAME,
        "selected_regulatory_seed_id": selected_seed_id,
        "regulatory_domain": regulatory_domain,
        "regulatory_seed_valid": bool(sv["accepted"]),
        "regulatory_seed_rejection_reasons": list(sv["rejection_reasons"]),
        "official_provider_used": "federal_register",
        "news_providers_used": sorted([p for p, s in news_status.items() if s == "ok"]),
        "news_provider_status": dict(sorted(news_status.items())),
        "official_query": official_query,
        "news_query": news_query,
        "date_window": [start, end],
        "live_query_approved": bool(live_approved),
        "live_query_executed": live_query_executed,
        "live_call_count": live_call_count,
        "official_news_live_status": status,
        # official/news/bridge aggregate(in-window·sanitized·title/url 미노출).
        "official_records_count": len(official_in_window),
        "news_records_count": len(news_records),
        "bridge_candidate_count": bridge_candidate_count,
        "freeze_eligible_count": freeze_eligible_count,
        # FR live + bridge sub-result(orchestrator/snapshot 가 ADR#86 필드로 소비·aggregate-only).
        "federal_register_live_result": fr_result,
        "official_news_bridge_result": bridge_result,
        "federal_register_live_status": (fr_result or {}).get("fr_live_status") or "not_run",
        "federal_register_date_filter_capability": (
            (fr_result or {}).get("date_filter_capability") or "documented_unverified"),
        # production candidate freeze(official×news·live-derived publishable 만·gold 0).
        "production_candidate_status": production_candidate_status,
        "production_candidate_batch_ready": production_candidate_batch_ready,
        "production_frozen_pair_count": production_frozen_pair_count,
        "candidate_provenance": (pcand or {}).get("candidate_provenance") or "none",
        # reviewer handoff(freeze→contact-PRE·전송 0) + official×news 전용 instruction.
        "reviewer_handoff_ready": bool(handoff["reviewer_handoff_ready"]),
        "official_news_label_instruction": official_news_instruction,
        "official_news_label_instruction_ready": True,
        "expected_label_files_ready": bool(handoff["expected_label_files_ready"]),
        "validation_command_ready": bool(handoff["validation_command_ready"]),
        "placement_guide_ready": bool(handoff["placement_guide_ready"]),
        "reviewer_handoff_bridge": handoff,
        # R1 / gold(passthrough·gold 0 유지).
        "production_gold_count": int((pcand or {}).get("production_gold_count") or 0),
        "current_r1_gap": int((pcand or {}).get("current_r1_gap") or 0),
        "blocked_reason": blocked_reason,
        "next_action": next_action,
        # ── 불변 경계(정직·constant + freeze 파생) ──
        "official_alone_as_production_candidate": False,
        "official_news_role_separated": True,
        "same_event_asserted": False,
        "same_event_truth_exposed": False,
        "reviewer_routing_only": True,
        "actual_sending_performed": False,
        "merge_allowed": bool((pcand or {}).get("merge_allowed")),
        "db_write": bool((pcand or {}).get("db_write")),
        "llm_invoked": bool((pcand or {}).get("llm_invoked")),
        "embedding_invoked": bool((pcand or {}).get("embedding_invoked")),
        "score_exposed": bool((pcand or {}).get("score_exposed")),
        "rationale_exposed": bool((pcand or {}).get("rationale_exposed")),
        "predicted_status_exposed": bool((pcand or {}).get("predicted_status_exposed")),
        "raw_pii_exposed": bool((pcand or {}).get("raw_pii_exposed")),
        "raw_source_body_exposed": False,
        "public_iu_allowed": False,
        "bridge_score_exposed": False,
        "r2_r7_no_go": True,
    }
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·드리프트 fail-loud).
    _assert_pii_safe(out, _path="official_news_live_acquisition_output")
    return out


def sanitized_official_news_acquisition(out: dict) -> dict:
    """snapshot/frontier 용 aggregate-only 투영(record/title/url/bridge candidate 리스트·instruction 본문 제외)."""
    return {
        "selected_regulatory_seed_id": out["selected_regulatory_seed_id"],
        "regulatory_domain": out["regulatory_domain"],
        "official_news_live_status": out["official_news_live_status"],
        "official_provider_used": out["official_provider_used"],
        "news_providers_used": list(out["news_providers_used"]),
        "official_records_count": out["official_records_count"],
        "news_records_count": out["news_records_count"],
        "bridge_candidate_count": out["bridge_candidate_count"],
        "freeze_eligible_count": out["freeze_eligible_count"],
        "production_candidate_status": out["production_candidate_status"],
        "production_candidate_batch_ready": out["production_candidate_batch_ready"],
        "production_frozen_pair_count": out["production_frozen_pair_count"],
        "reviewer_handoff_ready": out["reviewer_handoff_ready"],
        "blocked_reason": out["blocked_reason"],
        "next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#87 official×news live acquisition (regulatory seed → FR official + news → bridge → freeze; "
                     "기본 시도 0·--live-query 로 opt-in·merge 0·LLM 0·DB 0·전송 0·secret read 0)."))
    parser.add_argument("--seed-id", default=None, help="regulatory seed id(미지정 시 bank 의 selected).")
    parser.add_argument("--live-query", action="store_true",
                        help="opt-in bounded official×news live fetch(network·FR key-free·news key 필요·값 미노출).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(record/title 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank
    bank = build_regulatory_event_seed_bank(selected_seed_id=ns.seed_id)
    seed = bank["selected_seed_for_next_live_run"]
    if seed is None:
        print(f"- no selectable regulatory seed (selectable={bank['selectable_seed_ids']}) — operator must specify "
              "a named entity/date")
        return 0

    host_gate = None
    if ns.live_query:
        try:
            from pathlib import Path as _P

            from ingestion.orchestration.host_rate_gate import HostRateGate
            host_gate = HostRateGate(state_path=_P("ingestion/outputs/state/host_rate_gate.json"))
        except Exception:
            host_gate = None

    out = run_official_news_live_acquisition(seed, live_approved=ns.live_query, host_gate=host_gate)
    agg = sanitized_official_news_acquisition(out)
    if ns.json:
        print(json.dumps(agg, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} seed={out['selected_regulatory_seed_id']} "
          f"domain={out['regulatory_domain']!r}")
    print(f"- live: approved={out['live_query_approved']} executed={out['live_query_executed']} "
          f"status={out['official_news_live_status']} call_count={out['live_call_count']}")
    print(f"- records: official={out['official_records_count']} news={out['news_records_count']} "
          f"news_providers={out['news_providers_used']}")
    print(f"- bridge: candidates={out['bridge_candidate_count']} freeze_eligible={out['freeze_eligible_count']}")
    print(f"- production_candidate: status={out['production_candidate_status']} "
          f"ready={out['production_candidate_batch_ready']} frozen={out['production_frozen_pair_count']} "
          f"provenance={out['candidate_provenance']}")
    print(f"- handoff: ready={out['reviewer_handoff_ready']} instruction_ready={out['official_news_label_instruction_ready']} "
          f"actual_sending={out['actual_sending_performed']}")
    print(f"- r1: production_gold={out['production_gold_count']} gap={out['current_r1_gap']} "
          f"r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- gates: merge={out['merge_allowed']} llm={out['llm_invoked']} embedding={out['embedding_invoked']} "
          f"db_write={out['db_write']} same_event={out['same_event_asserted']}")
    print(f"- blocked_reason: {out['blocked_reason'] or '(none)'}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

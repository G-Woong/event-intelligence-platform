"""ADR#87 — regulatory-class event seed bank (official×news 동시 포착 가능 seed·candidate generation only·merge 0·LLM 0).

문제(ADR#86 실측·R-OfficialNewsDomainMismatch): Federal Register 를 window-honoring **official** source 로 배선했고
date-honoring 을 live_verified 했으나, official 규제문서와 news 보도가 **같은 subject·같은 window** 에서 만나는 일이
구조적으로 드물었다("enforcement" 25 docs vs SCOTUS asylum 보도 = 서로 다른 subject). 단순 keyword seed("enforcement")
는 official record 는 많이 반환해도 news 보도 angle 과 안 겹친다.

이 모듈은 그 간극을 좁히는 **regulatory-class event seed** 를 만든다 — official 문서(FR rule/notice/enforcement)와
news 보도가 **동시에 포착 가능한 event class** 를 구조화한다. 핵심은 seed 가 generic query 가 아니라:
  - **official_query**(FR conditions[term] — agency/action 중심 공식 어휘)와
  - **news_query**(entity/action 핵심 phrase — journalistic 보도 어휘)를 **분리** 보유하고,
  - agency + entity + action_phrase + date_window 를 **모두** 가진 named regulatory event 만 통과시킨다(broad reject).

핵심 정직성(상속·ADR#81 named seed 와 동형):
  - seed 는 **acquisition shape**(수집 의도)이지 *그 규제 사건이 일어났다*거나 *official 과 news 가 같은 사건이다* 를
    단정하지 않는다(provenance=code_proposed_regulatory_shape·event_occurrence_verified=False·same_event_asserted=False).
  - operator 가 live-run 직전 **실제 발생한 regulatory event/date 를 확인**해야 한다. entity/date 미특정 shape 는
    live_run_allowed_if_approved=False.
  - validator 는 broad/generic seed(generic enforcement·query without agency/date 등)를 **결정론으로 reject**
    (NLP 흉내 금지 — 구조 필드 + broad denylist).
  - **official source ≠ news article role**: seed 는 official×news 를 같은 role 로 섞지 않는다(source_role_policy 가
    official=evidence·news=reporting 을 명시). official 단독으로 cross-source candidate 가 되지 않는다.

절대 불변: merge 0 · LLM/embedding 0 · DB 0 · same_event 단정 0 · production gold 증가 0 · secret 0 · 전송 0.
seed 는 official×news reviewer-routing 후보 *생성* 신호이지 same-event proof 가 아니다.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

# named seed bank 단일 출처 재사용(broad denylist·정규화·ISO date·재구현 0).
from backend.app.tools.named_event_seed_bank import (
    _BROAD_SEED_DENYLIST,
    _ISO_DATE,
    _norm,
)

OPERATION_NAME = "regulatory_event_seed_bank"

# official source 는 Federal Register(ADR#86 wired·official_record role·authority 5). news 는 publishable 단일
# publisher(guardian/nyt) — aggregator/community/market/catalog 금지(§2 anchor 승격 금지).
_OFFICIAL_PROVIDER = "federal_register"
_NEWS_PROVIDERS = frozenset({"guardian", "nyt"})

# §8 allowed regulatory domains(official 문서 + news 보도가 같은 subject 로 만날 가능성이 있는 discrete regulatory class).
_ALLOWED_REGULATORY_DOMAINS: frozenset[str] = frozenset({
    "federal enforcement action",
    "agency final rule",
    "agency proposed rule",
    "major regulatory settlement",
    "public health/safety regulatory action",
    "environmental enforcement action",
    "financial regulatory enforcement action",
    "consumer protection action",
    "immigration/asylum regulatory notice",
    "trade/sanction regulatory notice",
})

# §8 reject — generic/broad regulatory 어휘(정규화). agency/entity/action/날짜 없이 단독이면 category 로 동작해
# official record 는 많아도 news 보도와 안 겹친다(ADR#86 "enforcement" 실패의 직접 교정). _BROAD_SEED_DENYLIST 와 합집합.
_GENERIC_REGULATORY_DENYLIST: frozenset[str] = frozenset({
    "generic enforcement", "generic immigration", "generic supreme court",
    "generic stock market", "generic election",
    # bare 규제 어휘(qualifier 없이 단독이면 broad).
    "enforcement", "immigration", "regulation", "rule", "settlement", "sanction",
    "sanctions", "notice", "ruling", "policy", "action",
})
_BROAD_DENYLIST = _BROAD_SEED_DENYLIST | _GENERIC_REGULATORY_DENYLIST

# community/market/catalog-only subject 거부(§8) — anchor 승격 금지(official×news 만 bridge).
_NON_ANCHOR_ROLE_HINTS: frozenset[str] = frozenset({
    "community", "market", "catalog", "search", "signal",
})


def _is_placeholder(text: str) -> bool:
    """operator 가 채워야 하는 placeholder(<Agency>/operator fills)인가 — named 아님(live 금지)."""
    return "<" in text or "operator fills" in text.lower()


def validate_regulatory_seed(seed: dict) -> dict:
    """단일 seed → regulatory-class event 여부 판정(결정론·broad reject·official×news role 보존·same_event 단정 0).

    accepted=True 는 'regulatory-class event SHAPE'(official 문서+news 보도가 같은 subject 로 만날 구조)를 뜻할 뿐
    *그 규제 사건이 일어났다/official 과 news 가 같은 사건이다* 가 아니다. has_* 플래그(§8)는 reviewer/operator 가
    seed 품질을 점검하는 진단 표면이다."""
    reasons: list[str] = []

    regulatory_domain = str(seed.get("regulatory_domain") or "").strip()
    official_provider = str(seed.get("official_provider") or "").strip()
    news_providers = seed.get("news_providers") or []
    agency = str(seed.get("agency") or "").strip()
    entity = str(seed.get("entity") or "").strip()
    action_phrase = str(seed.get("action_phrase") or "").strip()
    official_query = str(seed.get("official_query") or "").strip()
    news_query = str(seed.get("news_query") or "").strip()
    start = str(seed.get("date_window_start") or "").strip()
    end = str(seed.get("date_window_end") or "").strip()

    # ① official/news provider — FR official + publishable news(aggregator/community/market 금지).
    has_official_provider = official_provider == _OFFICIAL_PROVIDER
    news_list = list(news_providers) if isinstance(news_providers, (list, tuple)) else []
    has_news_provider = any(p in _NEWS_PROVIDERS for p in news_list)
    non_anchor_news = [p for p in news_list if p in _NON_ANCHOR_ROLE_HINTS]
    if not has_official_provider:
        reasons.append("missing_official_provider")
    if not has_news_provider:
        reasons.append("missing_news_provider")
    if non_anchor_news:
        reasons.append("non_anchor_news_provider")   # community/market/catalog 를 news anchor 로 승격 금지.

    # ② regulatory domain — allowed discrete class 만(generic/broad 거부).
    domain_norm = _norm(regulatory_domain)
    if not regulatory_domain:
        reasons.append("missing_regulatory_domain")
    elif regulatory_domain not in _ALLOWED_REGULATORY_DOMAINS:
        reasons.append("regulatory_domain_not_allowed")

    # ③ agency or entity(둘 중 하나는 named·placeholder 아님).
    has_entity_or_agency = bool(agency or entity)
    placeholder_entity = (bool(agency) and _is_placeholder(agency)) or (bool(entity) and _is_placeholder(entity))
    if not has_entity_or_agency:
        reasons.append("missing_agency_or_entity")
    elif placeholder_entity:
        reasons.append("placeholder_agency_or_entity_requires_operator_specification")

    # ④ action phrase(specific regulatory 행위).
    if not action_phrase:
        reasons.append("missing_action_phrase")

    # ⑤ official_query / news_query(분리 — official 어휘 ≠ news 어휘).
    if not official_query:
        reasons.append("missing_official_query")
    if not news_query:
        reasons.append("missing_news_query")

    # ⑥ date window(ISO start+end·operator 가 실제 발생일 확인). 미특정 = 아직 named regulatory event 아님.
    has_date_window = bool(start and end and _ISO_DATE.match(start) and _ISO_DATE.match(end) and start <= end)
    if not (start and end):
        reasons.append("missing_date_window")
    elif not (_ISO_DATE.match(start) and _ISO_DATE.match(end)):
        reasons.append("date_window_not_iso_yyyy_mm_dd")
    elif start > end:
        reasons.append("date_window_start_after_end")

    # ⑦ broad/generic topic reject(정규화 — entity/action/official_query/news_query 어느 하나라도 broad 단독이면 거부).
    broad_hits = [
        f for f, v in (
            ("entity", entity), ("agency", agency), ("action_phrase", action_phrase),
            ("official_query", official_query), ("news_query", news_query))
        if _norm(v) and _norm(v) in _BROAD_DENYLIST]
    is_not_broad_topic = not broad_hits and (domain_norm not in _BROAD_DENYLIST)
    if not is_not_broad_topic:
        reasons.append("broad_or_generic_topic")

    accepted = not reasons
    return {
        "seed_id": seed.get("seed_id"),
        "accepted": accepted,
        "rejection_reasons": reasons,
        "is_regulatory_event_shape": accepted,
        # §8 has_* 진단 플래그(operator/reviewer 가 seed 품질 점검).
        "has_official_provider": has_official_provider,
        "has_news_provider": has_news_provider,
        "has_date_window": has_date_window,
        "has_entity_or_agency": has_entity_or_agency and not placeholder_entity,
        "has_action_phrase": bool(action_phrase),
        "is_not_broad_topic": is_not_broad_topic,
        # 불변 — SHAPE 일 뿐 같은 사건/발생 단정 아님·official×news reviewer-routing only.
        "same_event_asserted": False,
        "reviewer_routing_only": True,
        "event_occurrence_verified": False,
    }


def _seed(
    seed_id: str, *, regulatory_domain: str, agency: str, entity: str, action_phrase: str,
    document_type: str, official_query: str, news_query: str, expected_overlap_tokens: list[str],
    expected_news_angle: str, risk: str, live_run_allowed_if_approved: bool,
    date_window_start: str = "", date_window_end: str = "",
    news_providers: Optional[list[str]] = None,
) -> dict:
    """regulatory-class event seed(§8 fields). official_query≠news_query(분리). source_role_policy 가 official=evidence·
    news=reporting 을 명시(같은 role 로 섞기 금지)."""
    return {
        "seed_id": seed_id,
        "regulatory_domain": regulatory_domain,
        "official_provider": _OFFICIAL_PROVIDER,
        "news_providers": list(news_providers) if news_providers is not None else ["guardian", "nyt"],
        "agency": agency,
        "entity": entity,
        "action_phrase": action_phrase,
        "document_type": document_type,
        "date_window_start": date_window_start,
        "date_window_end": date_window_end,
        "official_query": official_query,
        "news_query": news_query,
        "expected_overlap_tokens": list(expected_overlap_tokens),
        "expected_news_angle": expected_news_angle,
        "source_role_policy": "official=authoritative evidence · news=public reporting · NOT same role · bridge=reviewer-routing only",
        "risk": risk,
        "live_run_allowed_if_approved": live_run_allowed_if_approved,
        "provenance": "code_proposed_regulatory_shape",
        "event_occurrence_verified": False,
        "operator_must_confirm_actual_event": True,
        "same_event_asserted": False,
    }


def _curated_regulatory_seed_bank() -> list[dict]:
    """regulatory-class event seed 후보 — official 문서+news 보도가 같은 subject 로 만날 가능성이 높은 discrete 규제
    이벤트(named agency+action·발생 미확인·operator 가 실제 date 확인 후 bounded live-run).

    fully-specified(agency+action 명확) seed 는 live_run_allowed_if_approved=True(단 operator 가 occurrence date 확인);
    entity/date 미특정 template 은 False(operator 가 채울 때까지 live 금지). official_query 는 FR 공식 어휘(agency/action),
    news_query 는 journalistic 보도 어휘(entity/action 핵심 phrase) — 분리해 official record 와 news 보도 양쪽을 노린다."""
    return [
        _seed(
            "epa_final_rule_emissions",
            regulatory_domain="agency final rule",
            agency="Environmental Protection Agency",
            entity="EPA vehicle emissions standard",
            action_phrase="final rule on greenhouse gas emissions standards",
            document_type="Rule",
            official_query="Environmental Protection Agency greenhouse gas emissions final rule",
            news_query="EPA emissions rule",
            expected_overlap_tokens=["epa", "emissions", "rule", "standards"],
            expected_news_angle="news covers industry/political reaction to the EPA final rule",
            risk="news may frame as politics/industry impact while FR is the dry rule text — title tokens may diverge",
            # 제안 window(operator 가 실제 EPA final rule 발효일로 확인/대체 — code_proposed·발생 미확인·operator_must_confirm).
            date_window_start="2026-06-25", date_window_end="2026-06-26",
            live_run_allowed_if_approved=True),
        _seed(
            "sec_enforcement_settlement",
            regulatory_domain="financial regulatory enforcement action",
            agency="Securities and Exchange Commission",
            entity="SEC enforcement action (operator fills named respondent)",
            action_phrase="enforcement action / settled charges against a named firm",
            document_type="Notice",
            official_query="Securities and Exchange Commission enforcement settled charges",
            news_query="SEC charges settlement",
            expected_overlap_tokens=["sec", "charges", "settlement"],
            expected_news_angle="news names the firm and the penalty; FR notice is the official filing",
            risk="respondent not specified → broad; operator must fill the named firm for same-subject overlap",
            live_run_allowed_if_approved=False),   # respondent 미특정 → operator 가 named firm 채울 때까지 live 금지.
        _seed(
            "fda_safety_action",
            regulatory_domain="public health/safety regulatory action",
            agency="Food and Drug Administration",
            entity="FDA drug/device safety action (operator fills named product)",
            action_phrase="safety-related regulatory action on a named product",
            document_type="Notice",
            official_query="Food and Drug Administration safety action drug",
            news_query="FDA safety action",
            expected_overlap_tokens=["fda", "safety", "drug"],
            expected_news_angle="news covers the product recall/warning; FR is the official safety notice",
            risk="product not specified → broad; operator must fill the named product",
            live_run_allowed_if_approved=False),
        _seed(
            "ofac_sanction_notice",
            regulatory_domain="trade/sanction regulatory notice",
            agency="Office of Foreign Assets Control",
            entity="OFAC sanctions designation (operator fills named target)",
            action_phrase="sanctions designation / addition to the SDN list for a named target",
            document_type="Notice",
            official_query="Office of Foreign Assets Control sanctions designation",
            news_query="OFAC sanctions designation",
            expected_overlap_tokens=["ofac", "sanctions", "designation"],
            expected_news_angle="news names the sanctioned entity and geopolitical context; FR is the official notice",
            risk="target not specified → broad; operator must fill the named sanctioned target + date",
            live_run_allowed_if_approved=False),
    ]


def build_regulatory_event_seed_bank(
    *, seeds: Optional[list[dict]] = None, selected_seed_id: Optional[str] = None,
) -> dict:
    """regulatory-class event seed bank 구축 + broad-seed reject 자가검증 + 다음 live-run seed 선정.

    network 0 · merge 0 · LLM 0 · same_event 단정 0. broad denylist 자가검증으로 validator 가 §8 rejected 예시
    (generic enforcement·query without agency/date·community-only)를 실제로 거르는지 증명한다.
    selected_seed_for_next_live_run = accepted ∧ live_run_allowed_if_approved 인 첫 seed(없으면 None·operator 가
    named entity/date 특정 필요)."""
    bank_seeds = seeds if seeds is not None else _curated_regulatory_seed_bank()
    validated = []
    for s in bank_seeds:
        v = validate_regulatory_seed(s)
        validated.append({**s, "validation": v, "accepted": v["accepted"],
                          "rejection_reasons": v["rejection_reasons"]})
    accepted = [s for s in validated if s["accepted"]]

    # broad-seed reject 자가검증(§8 rejected 예시 — validator 가 거르는지 증명·문서 fixture).
    broad_examples = [
        {"seed_id": "broad_generic_enforcement", "regulatory_domain": "federal enforcement action",
         "official_provider": "federal_register", "news_providers": ["guardian", "nyt"],
         "agency": "", "entity": "enforcement", "action_phrase": "enforcement",
         "official_query": "enforcement", "news_query": "enforcement",
         "date_window_start": "2026-06-25", "date_window_end": "2026-06-26"},
        {"seed_id": "broad_generic_immigration", "regulatory_domain": "immigration/asylum regulatory notice",
         "official_provider": "federal_register", "news_providers": ["guardian", "nyt"],
         "agency": "", "entity": "immigration", "action_phrase": "immigration",
         "official_query": "immigration", "news_query": "immigration",
         "date_window_start": "2026-06-25", "date_window_end": "2026-06-26"},
        {"seed_id": "no_agency_or_entity", "regulatory_domain": "agency final rule",
         "official_provider": "federal_register", "news_providers": ["guardian", "nyt"],
         "agency": "", "entity": "", "action_phrase": "final rule",
         "official_query": "final rule", "news_query": "rule",
         "date_window_start": "2026-06-25", "date_window_end": "2026-06-26"},
        {"seed_id": "no_date_window", "regulatory_domain": "agency final rule",
         "official_provider": "federal_register", "news_providers": ["guardian", "nyt"],
         "agency": "Environmental Protection Agency", "entity": "EPA emissions rule",
         "action_phrase": "final rule on emissions", "official_query": "EPA emissions final rule",
         "news_query": "EPA emissions rule", "date_window_start": "", "date_window_end": ""},
        {"seed_id": "community_only_subject", "regulatory_domain": "agency final rule",
         "official_provider": "federal_register", "news_providers": ["community"],
         "agency": "EPA", "entity": "EPA rule", "action_phrase": "final rule",
         "official_query": "EPA rule", "news_query": "EPA rule",
         "date_window_start": "2026-06-25", "date_window_end": "2026-06-26"},
        {"seed_id": "domain_not_allowed", "regulatory_domain": "generic stock market",
         "official_provider": "federal_register", "news_providers": ["guardian", "nyt"],
         "agency": "SEC", "entity": "SEC market", "action_phrase": "market move",
         "official_query": "SEC market", "news_query": "stock market",
         "date_window_start": "2026-06-25", "date_window_end": "2026-06-26"},
    ]
    rejected_examples = []
    for ex in broad_examples:
        v = validate_regulatory_seed(ex)
        rejected_examples.append({"seed_id": ex["seed_id"], "accepted": v["accepted"],
                                  "rejection_reasons": v["rejection_reasons"]})
    broad_rejected = [r for r in rejected_examples if not r["accepted"]]

    # 다음 live-run seed 선정: accepted ∧ live_run_allowed_if_approved(operator 가 실제 regulatory event date 확인 전제).
    selectable = [s for s in accepted if s.get("live_run_allowed_if_approved")]
    if selected_seed_id is not None:
        selected = next((s for s in selectable if s["seed_id"] == selected_seed_id), None)
    else:
        selected = selectable[0] if selectable else None

    return {
        "operation": OPERATION_NAME,
        "regulatory_event_seed_bank_ready": len(accepted) > 0,
        "seed_bank": validated,
        "regulatory_seed_count": len(accepted),
        "selectable_seed_ids": [s["seed_id"] for s in selectable],
        "selected_seed_for_next_live_run": selected,
        "selected_seed_id": selected["seed_id"] if selected else None,
        # broad reject 증명(validator 가 §8 rejected 를 실제로 거름).
        "broad_seed_rejected_count": len(broad_rejected),
        "broad_seed_examples_tested": len(broad_examples),
        "rejected_examples": rejected_examples,
        "validator_rejects_all_broad_examples": len(broad_rejected) == len(broad_examples),
        # ── 불변 경계 ──
        "seed_is_candidate_generation_not_same_event_proof": True,
        "official_news_role_separated": True,   # official=evidence·news=reporting(같은 role 로 섞지 않음).
        "same_event_truth_asserted": False,
        "event_occurrence_verified": False,
        "merge_allowed": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "db_write": False,
        "production_gold_count": 0,
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#87 regulatory-class event seed bank (official×news candidate generation only·same_event "
                     "단정 0·merge 0·LLM 0; broad/generic seed reject·network 0)."))
    parser.add_argument("--json", action="store_true", help="full bank JSON 출력.")
    parser.add_argument("--select", default=None, help="다음 live-run seed id 강제 선택.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    bank = build_regulatory_event_seed_bank(selected_seed_id=ns.select)
    if ns.json:
        print(json.dumps(bank, ensure_ascii=False, indent=2))
        return 0
    print(f"- regulatory seed bank (ADR#87) ready={bank['regulatory_event_seed_bank_ready']} "
          f"regulatory_seed_count={bank['regulatory_seed_count']}")
    for s in bank["seed_bank"]:
        print(f"    {s['seed_id']:<28} accepted={s['accepted']!s:<5} "
              f"live_ok={s.get('live_run_allowed_if_approved')!s:<5} reasons={s['rejection_reasons']}")
    print(f"- selected_for_next_live_run={bank['selected_seed_id']}")
    print(f"- broad_rejected={bank['broad_seed_rejected_count']}/{bank['broad_seed_examples_tested']} "
          f"validator_rejects_all_broad={bank['validator_rejects_all_broad_examples']}")
    print(f"- same_event_asserted={bank['same_event_truth_asserted']} merge_allowed={bank['merge_allowed']} "
          f"official_news_role_separated={bank['official_news_role_separated']} "
          f"production_gold_count={bank['production_gold_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""ADR#81 — named single-event seed bank (candidate generation only · same_event 단정 0 · merge 0 · LLM 0).

문제(ADR#80 실측·분석 §2-Q1/Q2): SCOTUS "Supreme Court ruling" seed 는 *기관+일반 행위*라 category-lean 으로
동작했고(comparison 100·entity-sharing 0), recall lift 0 의 한 원인이 되었다. 이 모듈은 그 category seed 를
**named single-event seed** 로 교체한다 — 특정 named entity + 특정 discrete event phrase + 특정 1d window 를
가진 seed 만 통과시켜 cross-source same-event 수렴 가능성을 높인다.

핵심 정직성:
  - seed 는 **acquisition shape**(수집 의도)이지 *그 사건이 일어났다*거나 *같은 사건이다*를 단정하지 않는다
    (provenance=code_proposed_named_shape · event_occurrence_verified=False · same_event_asserted=False).
  - operator 가 live-run 직전에 **실제 발생한 event/date 를 확인**해야 한다(scheduled 기관 이벤트는 entity 가 실재·
    discrete 하나 발생 여부는 operator 확인). entity 미특정 shape 는 live_run_allowed_if_approved=False.
  - validator 는 broad/category seed 를 **결정론으로 reject**한다(NLP 흉내 금지 — 구조 필드 + broad denylist).

절대 불변: merge 0 · LLM/embedding 0 · DB 0 · same_event 단정 0 · production gold 증가 0 · secret 0.
seed 는 reviewer 후보 *생성* 신호이지 same-event proof 가 아니다.
"""
from __future__ import annotations

import argparse
import re
import sys
from typing import Optional

_TOKEN = re.compile(r"[0-9a-z]+")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# named single-event seed 필수 구조 필드(§6 accepted shape).
_REQUIRED_FIELDS: tuple[str, ...] = (
    "named_entity", "event_phrase", "date_window", "provider_coverage_hypothesis",
)

# §6 rejected broad seed(정규화). seed_text 또는 named_entity 가 이 집합과 정확히 일치하면 reject.
# bare 기관/토픽도 포함(specific qualifier 없이는 category 로 동작).
_BROAD_SEED_DENYLIST: frozenset[str] = frozenset({
    "supreme court ruling", "federal reserve", "ukraine war", "ai regulation",
    "stock market", "election", "climate change",
    # bare 기관/토픽(qualifier 없이 단독이면 broad).
    "supreme court", "european central bank", "white house", "congress",
    "government", "interest rates", "inflation", "war", "economy",
})

# specific date window: "1d"(operator 가 실제 event date 확인) 또는 정확한 ISO date.
_SPECIFIC_WINDOWS: frozenset[str] = frozenset({"1d"})


def _norm(text: Optional[str]) -> str:
    """소문자 토큰 join 정규화(broad denylist 대조용)."""
    return " ".join(_TOKEN.findall((text or "").lower()))


def _is_specific_window(window: str) -> bool:
    return window in _SPECIFIC_WINDOWS or bool(_ISO_DATE.match(window.strip()))


def validate_named_single_event_seed(seed: dict) -> dict:
    """단일 seed → named-single-event 여부 판정(결정론·broad reject·same_event 단정 0).

    reject 조건(누적): 필수 구조 필드 누락 · broad date window · seed_text/named_entity 가 broad denylist 정확 일치.
    accepted=True 는 'named single-event SHAPE' 를 뜻할 뿐 *그 사건이 일어났다/같은 사건이다* 가 아니다."""
    reasons: list[str] = []
    for f in _REQUIRED_FIELDS:
        if not str(seed.get(f) or "").strip():
            reasons.append(f"missing_{f}")

    window = str(seed.get("date_window") or "").strip()
    if window and not _is_specific_window(window):
        reasons.append("broad_or_unspecific_date_window")

    seed_text_norm = _norm(seed.get("seed_text") or seed.get("event_phrase"))
    entity_norm = _norm(seed.get("named_entity"))
    if seed_text_norm and seed_text_norm in _BROAD_SEED_DENYLIST:
        reasons.append("broad_topic_seed")
    if entity_norm and entity_norm in _BROAD_SEED_DENYLIST:
        reasons.append("bare_broad_entity")

    # placeholder 엔티티(<Party>/operator fills)는 아직 named single-event 아님 — operator 특정 전까지 reject(정직).
    entity_raw = str(seed.get("named_entity") or "")
    if "<" in entity_raw or "operator fills" in entity_raw.lower():
        reasons.append("placeholder_entity_requires_operator_specification")

    return {
        "seed_id": seed.get("seed_id"),
        "accepted": not reasons,
        "rejection_reasons": reasons,
        "is_named_single_event_shape": not reasons,
        "same_event_asserted": False,        # SHAPE 일 뿐 같은 사건 단정 아님(불변).
        "event_occurrence_verified": False,  # operator 가 live-run 직전 실제 발생 확인.
    }


# ── curated named single-event seed bank(code_proposed_named_shape · 발생 미확인 · operator 확인 필요) ────────
# scheduled 기관 이벤트(entity 실재·discrete·outlet 수렴 높음)는 live_run_allowed_if_approved=True(operator 가 실제
# 결정 date 확인). entity 미특정 shape(M&A/제재/재난/선거)는 named_entity 특정 전까지 live_run_allowed_if_approved=False.
def _seed(
    seed_id: str, seed_text: str, named_entity: str, event_phrase: str, *,
    provider_coverage_hypothesis: str, expected_overlap: str, risk: str,
    source_role_compatibility: str, live_run_allowed_if_approved: bool,
    date_window: str = "1d",
) -> dict:
    return {
        "seed_id": seed_id,
        "seed_text": seed_text,
        "named_entity": named_entity,
        "event_phrase": event_phrase,
        "date_window": date_window,
        "provider_coverage_hypothesis": provider_coverage_hypothesis,
        "expected_overlap": expected_overlap,
        "risk": risk,
        "source_role_compatibility": source_role_compatibility,
        "live_run_allowed_if_approved": live_run_allowed_if_approved,
        "provenance": "code_proposed_named_shape",
        "event_occurrence_verified": False,
        "operator_must_confirm_actual_event": True,
        "same_event_asserted": False,
    }


def _curated_seed_bank() -> list[dict]:
    """named single-event seed 후보 — scheduled 기관 discrete 이벤트 우선(cross-source 수렴 높음·entity 실재).

    ADR#80 category seed("Supreme Court ruling")의 직접 대조군: 단일 announcement 에 outlet 들이 공유 토큰으로
    수렴하는 discrete 이벤트. 발생/same_event 미단정 — operator 가 실제 date 확인 후 bounded live-run."""
    return [
        _seed(
            "fomc_rate_decision",
            "US Federal Reserve FOMC federal funds rate decision (meeting outcome)",
            "US Federal Reserve FOMC",
            "FOMC federal funds rate decision announcement",
            provider_coverage_hypothesis="guardian+nyt(news)+gdelt(key-free)+federal_register(official) 동시 보도",
            expected_overlap="high — 단일 announcement·공유 토큰(fed/rate/basis/points/%)",
            risk="같은 날 Fed 연설/회의록 등 부수 기사 dilution·named case 아님",
            source_role_compatibility="publishable_news + official",
            live_run_allowed_if_approved=True),
        _seed(
            "ecb_rate_decision",
            "European Central Bank Governing Council key interest rate decision",
            "European Central Bank Governing Council",
            "ECB key interest rate decision announcement",
            provider_coverage_hypothesis="guardian+nyt+gdelt 보도(EU press corner 보조)",
            expected_overlap="high — 단일 정책 발표·공유 토큰(ecb/rate/deposit/%)",
            risk="US 대비 영어 outlet 밀도 낮을 수 있음",
            source_role_compatibility="publishable_news + official",
            live_run_allowed_if_approved=True),
        _seed(
            "scotus_named_case_ruling",
            "US Supreme Court ruling in a specific named case (operator fills case name + date)",
            "US Supreme Court — specific named case (e.g. <Party> v. <Party>)",
            "Supreme Court issues opinion/ruling in the named case",
            provider_coverage_hypothesis="guardian+nyt+gdelt — 단, named case 로 특정해야 수렴",
            expected_overlap="high IF named case 특정(ADR#80 category 실패의 직접 교정)",
            risk="case 미특정 시 ADR#80 category 재현 — named_entity 특정 필수",
            source_role_compatibility="publishable_news",
            live_run_allowed_if_approved=False),     # case 미특정 → operator 가 named case 채울 때까지 live 금지.
        _seed(
            "company_named_acquisition",
            "Specific acquirer acquires specific target — definitive agreement (operator fills names)",
            "<Acquirer> – <Target> (operator fills specific company names)",
            "definitive merger/acquisition agreement announcement",
            provider_coverage_hypothesis="guardian+nyt+gdelt+sec_edgar(8-K filing) 수렴",
            expected_overlap="high IF 회사명 특정·sec_edgar 공식 filing 동반",
            risk="회사명 미특정 시 broad — named_entity 특정 필수",
            source_role_compatibility="publishable_news + official",
            live_run_allowed_if_approved=False),
        _seed(
            "country_sanction_package",
            "Specific issuer announces specific sanction package on specific target (operator fills)",
            "<Issuer> sanctions on <Target> (operator fills specific names)",
            "specific sanction package announcement",
            provider_coverage_hypothesis="guardian+nyt+gdelt+federal_register/eu_press_corner",
            expected_overlap="medium-high IF 발급주체·대상 특정",
            risk="주체/대상 미특정 시 broad",
            source_role_compatibility="publishable_news + official",
            live_run_allowed_if_approved=False),
    ]


def build_named_event_seed_bank(
    *, seeds: Optional[list[dict]] = None, selected_seed_id: Optional[str] = None,
) -> dict:
    """named single-event seed bank 구축 + broad-seed reject 자가검증 + 다음 live-run seed 선정.

    network 0 · merge 0 · LLM 0 · same_event 단정 0. broad denylist 자가검증으로 validator 가 §6 rejected 예시를
    실제로 거르는지 증명한다. selected_seed_for_next_live_run = accepted ∧ live_run_allowed_if_approved 인 첫 seed
    (없으면 None·operator 가 named_entity 특정 필요)."""
    bank_seeds = seeds if seeds is not None else _curated_seed_bank()
    validated = []
    for s in bank_seeds:
        v = validate_named_single_event_seed(s)
        validated.append({**s, "validation": v, "accepted": v["accepted"],
                          "rejection_reasons": v["rejection_reasons"]})
    accepted = [s for s in validated if s["accepted"]]

    # broad-seed reject 자가검증(§6 rejected 예시 — validator 가 거르는지 증명·문서 fixture).
    broad_examples = [
        {"seed_id": "broad_scotus", "seed_text": "Supreme Court ruling", "named_entity": "Supreme Court",
         "event_phrase": "ruling", "date_window": "7d", "provider_coverage_hypothesis": "broad"},
        {"seed_id": "broad_fed", "seed_text": "Federal Reserve", "named_entity": "Federal Reserve",
         "event_phrase": "policy", "date_window": "7d", "provider_coverage_hypothesis": "broad"},
        {"seed_id": "broad_election", "seed_text": "election", "named_entity": "election",
         "event_phrase": "vote", "date_window": "30d", "provider_coverage_hypothesis": "broad"},
        {"seed_id": "broad_climate", "seed_text": "climate change", "named_entity": "climate change",
         "event_phrase": "warming", "date_window": "ongoing", "provider_coverage_hypothesis": "broad"},
        {"seed_id": "broad_missing_fields", "seed_text": "Some event"},  # 필수 필드 누락.
    ]
    rejected_examples = []
    for ex in broad_examples:
        v = validate_named_single_event_seed(ex)
        rejected_examples.append({"seed_id": ex["seed_id"], "accepted": v["accepted"],
                                  "rejection_reasons": v["rejection_reasons"]})
    broad_rejected = [r for r in rejected_examples if not r["accepted"]]

    # 다음 live-run seed 선정: accepted ∧ live_run_allowed_if_approved(operator 가 실제 event date 확인 전제).
    selectable = [s for s in accepted if s.get("live_run_allowed_if_approved")]
    if selected_seed_id is not None:
        selected = next((s for s in selectable if s["seed_id"] == selected_seed_id), None)
    else:
        selected = selectable[0] if selectable else None

    return {
        "operation": "named_event_seed_bank",
        "named_single_event_seed_bank_ready": len(accepted) > 0,
        "seed_bank": validated,
        "named_seed_count": len(accepted),
        "selectable_seed_ids": [s["seed_id"] for s in selectable],
        "selected_seed_for_next_live_run": selected,
        "selected_seed_id": selected["seed_id"] if selected else None,
        # broad reject 증명(validator 가 §6 rejected 를 실제로 거름).
        "broad_seed_rejected_count": len(broad_rejected),
        "broad_seed_examples_tested": len(broad_examples),
        "rejected_examples": rejected_examples,
        "validator_rejects_all_broad_examples": len(broad_rejected) == len(broad_examples),
        # ── 불변 경계 ──
        "seed_is_candidate_generation_not_same_event_proof": True,
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
        description=("ADR#81 named single-event seed bank (candidate generation only·same_event 단정 0·merge 0·"
                     "LLM 0; broad seed reject·network 0)."))
    parser.add_argument("--json", action="store_true", help="full bank JSON 출력.")
    parser.add_argument("--select", default=None, help="다음 live-run seed id 강제 선택.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    bank = build_named_event_seed_bank(selected_seed_id=ns.select)
    if ns.json:
        import json
        print(json.dumps(bank, ensure_ascii=False, indent=2))
        return 0
    print(f"- named seed bank (ADR#81) ready={bank['named_single_event_seed_bank_ready']} "
          f"named_seed_count={bank['named_seed_count']}")
    for s in bank["seed_bank"]:
        print(f"    {s['seed_id']:<28} accepted={s['accepted']!s:<5} "
              f"live_ok={s.get('live_run_allowed_if_approved')!s:<5} reasons={s['rejection_reasons']}")
    print(f"- selected_for_next_live_run={bank['selected_seed_id']}")
    print(f"- broad_rejected={bank['broad_seed_rejected_count']}/{bank['broad_seed_examples_tested']} "
          f"validator_rejects_all_broad={bank['validator_rejects_all_broad_examples']}")
    print(f"- same_event_asserted={bank['same_event_truth_asserted']} merge_allowed={bank['merge_allowed']} "
          f"production_gold_count={bank['production_gold_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

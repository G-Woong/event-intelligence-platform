"""ADR#90 — Hot Intelligence Post contract (미래 community-style intelligence post 의 field/gate 계약·runtime 금지).

이 프로젝트의 최종 제품은 raw news feed 가 아니라, 에이전트가 전세계 사건·논쟁 중 사람이 흥미로워할 것을 찾아 공식
증거·뉴스 교차·커뮤니티 반응·시계열을 통합해 **사람이 읽고 반응·댓글할 수 있는 intelligence post** 로 게시하는
웹 인텔리전스다. 그러나 지금은 evidence/gold/MERGE_GATE pipeline 을 닦는 단계이며, public post runtime 은 No-Go 다.

이 모듈은 그 미래 제품의 **계약** 이다(runtime 0·docs/contract only):
  - field contract: post 가 가질 필드(headline·why_it_is_hot·official_evidence·news_corroboration·
    community_reaction_layer·market_signal_layer·uncertainty·public_readiness_status·reply_policy 등) — INTELLIGENCE_
    UNIT_CONTRACT §2 를 **확장**(중복 0): why_it_is_hot·headline·public_readiness_status·reply_policy 를 더한다.
  - gate rules: MERGE_GATE 전 public 0·official 증거 없으면 authoritative claim 0·community=reaction_to only·
    market=signal only·catalog/entity=context only·uncertainty 가시·human label provenance 필수.
  - runtime guard: `runtime_enabled=False`·`public_post_body_generated=False`·`reply_policy="disabled"`·LLM headline 0.

절대 불변(§12·§18): public post 0 · comment auto-reply 0 · LLM/embedding 0 · merge 0 · community/market anchor 금지 ·
search URL ≠ truth · same_event 단정 0 · score/PII/secret 미노출. **이 모듈은 게시하지 않는다 — 계약을 검증할 뿐이다.**
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "hot_intelligence_post_contract"
CONTRACT_VERSION = "hot_intelligence_post_v1"

# §12 Hot Intelligence Post field contract(IU §2 확장 — why_it_is_hot/headline/public_readiness_status/reply_policy 추가).
HOT_POST_FIELDS: tuple[str, ...] = (
    "post_id", "event_id", "post_status", "headline", "short_hook", "why_it_is_hot",
    "official_evidence", "news_corroboration", "timeline_updates", "entity_context",
    "community_reaction_layer", "market_signal_layer", "uncertainty_summary",
    "human_label_status", "merge_gate_status", "source_agreement", "source_disagreement",
    "public_readiness_status", "reply_policy", "moderation_status", "last_updated_at",
)

# §12 gate rules(계약 불변).
HOT_POST_RULES: tuple[str, ...] = (
    "no public post before MERGE_GATE",
    "no official evidence -> no authoritative claim",
    "community reaction is reaction_to only (never an evidence anchor)",
    "market signal is signal only (never an evidence anchor)",
    "catalog/entity is context only",
    "uncertainty must be visible",
    "human label provenance required for a merged event",
    "search URL candidate is not truth until fetched",
    "the agent does not publish a post body before the public-IU gate",
    "reply_policy stays disabled before the community interaction runtime gate",
)

# anchor 역할(이벤트 증거 기반이 될 수 있는 role)은 official/news 만. community/market/catalog/entity/search 는 anchor 금지.
ANCHOR_ROLES: frozenset[str] = frozenset({"official", "news"})
NON_ANCHOR_ROLES: dict[str, str] = {
    "community": "reaction_to", "market": "signal", "catalog": "context",
    "entity": "context", "search": "url_candidate",
}

# post_status 어휘.
POST_STATUS_DRAFT = "draft"
POST_STATUS_BLOCKED_PRE_MERGE_GATE = "blocked_pre_merge_gate"
POST_STATUS_RUNTIME_DISABLED = "runtime_disabled"


def is_valid_anchor_role(role: Optional[str]) -> bool:
    """이벤트 증거 anchor 가 될 수 있는 role 인가(official/news 만·community/market/catalog/search 는 False)."""
    return str(role or "") in ANCHOR_ROLES


def build_hot_intelligence_post_contract() -> dict:
    """Hot Intelligence Post field/gate 계약(runtime 0·docs/contract only). 게시하지 않는다."""
    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        # runtime guard — 이 단계에서 public post runtime 은 No-Go.
        "runtime_enabled": False,
        "public_post_body_generated": False,
        "llm_headline_generated": False,
        "reply_policy_default": "disabled",
        # post_status 어휘(계약 — 현 단계는 runtime_disabled 만 방출·draft/blocked_pre_merge_gate 는 미래 runtime 값).
        "post_status_vocabulary": [
            POST_STATUS_DRAFT, POST_STATUS_BLOCKED_PRE_MERGE_GATE, POST_STATUS_RUNTIME_DISABLED],
        # field/rule contract.
        "fields": list(HOT_POST_FIELDS),
        "field_count": len(HOT_POST_FIELDS),
        "rules": list(HOT_POST_RULES),
        "extends_intelligence_unit_contract": True,   # IU §2 확장(중복 0).
        "added_fields_over_iu": ["headline", "why_it_is_hot", "public_readiness_status", "reply_policy"],
        # anchor 정책.
        "anchor_roles": sorted(ANCHOR_ROLES),
        "non_anchor_roles": dict(NON_ANCHOR_ROLES),
        "community_is_anchor": False,
        "market_is_anchor": False,
        "search_url_is_truth": False,
        # gate 기본값.
        "public_readiness_default": False,
        "uncertainty_required": True,
        "human_label_provenance_required": True,
        # ── No-Go 경계(정직·constant) ──
        "merge_allowed": False,
        "public_iu_allowed": False,
        "comment_auto_reply_enabled": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "same_event_asserted": False,
        "r2_r7_no_go": True,
    }
    _assert_pii_safe(out, _path="hot_intelligence_post_contract_output")
    return out


def evaluate_hot_post_readiness(draft: dict) -> dict:
    """draft post → public 게시 가능 여부(runtime 전 **항상 False**) + 게이트 위반 목록. 본문 생성 0·검사만.

    public_readiness 는 merge_gate_status=passed ∧ official_evidence 존재 ∧ human_label_status 존재 ∧ uncertainty 가시일
    때만 *후보* 가 되지만, ADR#90 단계에서는 runtime_enabled=False 라 publishable=False·public_readiness_status=False 고정.
    community/market 를 anchor 로 쓰거나 search URL 을 truth 로 쓰면 위반으로 표면화한다(과대게시 0)."""
    violations: list[str] = []
    if str(draft.get("merge_gate_status") or "") != "passed":
        violations.append("no_public_post_before_merge_gate")
    if not draft.get("official_evidence"):
        violations.append("no_official_evidence_no_authoritative_claim")
    if not draft.get("human_label_status"):
        violations.append("human_label_provenance_required")
    if draft.get("uncertainty_summary") in (None, ""):
        violations.append("uncertainty_must_be_visible")
    anchor_role = str(draft.get("anchor_role") or "")
    if anchor_role and not is_valid_anchor_role(anchor_role):
        violations.append(f"non_anchor_role_used_as_anchor:{anchor_role}")
    if draft.get("community_reaction_layer") and draft.get("anchor_role") == "community":
        violations.append("community_reaction_used_as_anchor")
    if draft.get("market_signal_layer") and draft.get("anchor_role") == "market":
        violations.append("market_signal_used_as_anchor")
    if draft.get("search_url_as_truth"):
        violations.append("search_url_candidate_is_not_truth")
    out = {
        "operation_name": OPERATION_NAME,
        # ADR#90 runtime disabled — 항상 미게시.
        "publishable": False,
        "public_readiness_status": False,
        "reply_policy": "disabled",
        "runtime_enabled": False,
        "public_post_body_generated": False,
        "post_status": POST_STATUS_RUNTIME_DISABLED,
        "violations": violations,
        "violation_count": len(violations),
        "merge_allowed": False,
        "r2_r7_no_go": True,
    }
    _assert_pii_safe(out, _path="hot_post_readiness_output")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#90 Hot Intelligence Post contract (미래 community-style post 의 field/gate 계약·runtime 0·"
                     "public post 0·comment reply 0·community/market anchor 금지·MERGE_GATE 전 public 0)."))
    parser.add_argument("--json", action="store_true", help="contract JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_hot_intelligence_post_contract()
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} version={out['contract_version']} "
          f"runtime_enabled={out['runtime_enabled']}")
    print(f"- fields ({out['field_count']}): {', '.join(out['fields'])}")
    print(f"- anchor_roles={out['anchor_roles']} community_is_anchor={out['community_is_anchor']} "
          f"market_is_anchor={out['market_is_anchor']} search_url_is_truth={out['search_url_is_truth']}")
    print(f"- public_readiness_default={out['public_readiness_default']} reply_policy_default={out['reply_policy_default']} "
          f"public_post_body_generated={out['public_post_body_generated']}")
    print("- rules:")
    for r in out["rules"]:
        print(f"    - {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

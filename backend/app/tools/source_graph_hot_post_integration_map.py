"""ADR#95 §16 (option I) — Source-graph/time-series → Hot Intelligence Post field 통합 매핑 (CONTRACT-ONLY·runtime 0).

이 모듈은 "source-graph + time-series insight 계약"의 15 component 를 "Hot Intelligence Post 계약"의 21 field 에
**필드 단위로 결속**한다(new 어휘 0·compose/cite only). 두 계약을 인용(cite)해 한 곳에서 매핑만 선언할 뿐,
런타임도, public post body 도, merge 도 만들지 않는다:
  - 15 component → `source_graph_timeseries_insight_contract.build_*` 가 단일 출처(call 해서 cite).
  - 21 field / anchor 정책(official·news 만) → `hot_intelligence_post_contract` (`HOT_POST_FIELDS`/`is_valid_anchor_role`).

핵심 불변(CONTRACT-ONLY): insight 후보(insight_candidates→why_it_is_hot)는 게시 불가 · timeline update 는 merge gate
전 same_event 단정 0 · community 는 reaction_to(non-anchor) · market 는 signal(non-anchor) · public_readiness 는
R1(gold)·R2(MERGE_GATE) 요구 · anchor 가 될 수 있는 component 는 official_evidence/news_corroboration 뿐.
이 모듈은 runtime 0(merge/LLM/network/public IU 0)이며 게시하지 않는다 — 매핑을 조립·검증할 뿐(`_assert_pii_safe` 가드).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.hot_intelligence_post_contract import (
    ANCHOR_ROLES,
    HOT_POST_FIELDS,
    is_valid_anchor_role,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe
from backend.app.tools.source_graph_timeseries_insight_contract import (
    build_source_graph_timeseries_insight_contract,
)

OPERATION_NAME = "source_graph_hot_post_integration_map"
CONTRACT_VERSION = "source_graph_hot_post_integration_map_v1"
MAP_READY = "integration_map_candidate_only_runtime_disabled"

# ── field-by-field 매핑: (source_graph_component, hot_post_field, note) ───────────────────────────────────────
# anchor_eligible 은 선언하지 않고 `is_valid_anchor_role(component_role)` 로 계산한다(official_evidence/news_
# corroboration 만 True). hot_post_field=None 은 standalone field 없이 다른 anchor field 의 provenance 로만 쓰임을 뜻한다.
# source_graph_component 는 모두 15 component 의 기존 이름, hot_post_field 는 모두 21 HOT_POST_FIELDS 의 기존 이름(신규 0).
_MAPPING_SPECS: tuple[tuple[str, Optional[str], str], ...] = (
    ("event_identity", "event_id",
     "event identity → post event_id (events 테이블 식별자)"),
    ("official_evidence", "official_evidence",
     "official anchor evidence (is_valid_anchor_role True)"),
    ("news_corroboration", "news_corroboration",
     "news anchor corroboration (is_valid_anchor_role True)"),
    ("timeline_updates", "timeline_updates",
     "append-only timeline; cannot assert same_event before merge gate"),
    ("entity_nodes", "entity_context",
     "entity nodes are context only (non-anchor)"),
    ("catalog_context_layer", "entity_context",
     "catalog context is context only (non-anchor)"),
    ("community_reaction_layer", "community_reaction_layer",
     "community is reaction_to only (non-anchor)"),
    ("market_signal_layer", "market_signal_layer",
     "market is signal only (non-anchor)"),
    ("uncertainty_state", "uncertainty_summary",
     "uncertainty must stay visible in the post"),
    ("insight_candidates", "why_it_is_hot",
     "insight candidate-only — NOT publishable (suggestion, not truth)"),
    ("human_label_state", "human_label_status",
     "human label provenance"),
    ("merge_gate_state", "merge_gate_status",
     "merge gate state (blocked/eligible)"),
    ("public_readiness_state", "public_readiness_status",
     "public readiness requires R1 (gold) + R2 (MERGE_GATE)"),
    ("evidence_edges", "source_agreement",
     "cross-source agreement edge (candidate until merge gate)"),
    ("evidence_edges", "source_disagreement",
     "cross-source disagreement edge (candidate until merge gate)"),
    ("source_nodes", None,
     "provenance behind official_evidence/news_corroboration — note only, no standalone field"),
)


def _build_mappings(component_role: dict[str, str]) -> list[dict]:
    """15 component → 21 field 매핑 결속 — anchor_eligible 은 `is_valid_anchor_role` 로 계산(official/news 만 True).

    component 가 cited 15 component 밖이거나 field 가 21 HOT_POST_FIELDS 밖이면 drift → KeyError(lock 테스트가 잡음).
    """
    mappings: list[dict] = []
    for source_graph_component, hot_post_field, note in _MAPPING_SPECS:
        if source_graph_component not in component_role:
            raise KeyError(f"unknown source_graph_component (not in cited 15): {source_graph_component}")
        if hot_post_field is not None and hot_post_field not in HOT_POST_FIELDS:
            raise KeyError(f"unknown hot_post_field (not in 21 HOT_POST_FIELDS): {hot_post_field}")
        mappings.append({
            "source_graph_component": source_graph_component,
            "hot_post_field": hot_post_field,
            "anchor_eligible": is_valid_anchor_role(component_role[source_graph_component]),
            "note": note,
        })
    return mappings


def build_source_graph_hot_post_integration_map() -> dict:
    """Source-graph/time-series → Hot Intelligence Post field 통합 매핑(runtime 0·compose/cite only). 게시하지 않는다."""
    contract = build_source_graph_timeseries_insight_contract()  # 15 component 단일 출처(cite).
    component_role = {c["component"]: c["role_or_storage_class"] for c in contract["components"]}
    mappings = _build_mappings(component_role)
    mapped_hot_post_fields = sorted({m["hot_post_field"] for m in mappings if m["hot_post_field"] is not None})
    post_only_fields = sorted(set(HOT_POST_FIELDS) - set(mapped_hot_post_fields))
    anchor_components = sorted(
        component for component, role in component_role.items() if is_valid_anchor_role(role))
    non_anchor_components = sorted(
        component for component, role in component_role.items() if not is_valid_anchor_role(role))
    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "source_graph_hot_post_integration_status": MAP_READY,
        # ── field-by-field 매핑 ──
        "mappings": mappings,
        "mapping_count": len(mappings),
        # ── 21 Hot Post field / 매핑 커버리지 ──
        "hot_post_fields": list(HOT_POST_FIELDS),
        "hot_post_field_count": len(HOT_POST_FIELDS),
        "mapped_hot_post_fields": mapped_hot_post_fields,
        "post_only_fields": post_only_fields,
        # ── anchor 정책(official_evidence/news_corroboration 만 anchor) ──
        "anchor_components": anchor_components,
        "non_anchor_components": non_anchor_components,
        "anchor_roles": sorted(ANCHOR_ROLES),
        # ── 불변(정직·constant) ──
        "runtime_enabled": False,
        "public_post_body_generated": False,
        "community_is_anchor": False,
        "market_is_anchor": False,
        "insight_candidate_publishable": False,
        "timeline_update_asserts_same_event": False,
        "public_readiness_requires_r1_r2": True,
        "merge_allowed": False,
        "same_event_asserted": False,
        "llm_invoked": False,
        "network_invoked": False,
        "production_gold_count": 0,
    }
    _assert_pii_safe(out, _path="source_graph_hot_post_integration_output")
    return out


def sanitized_source_graph_hot_post_integration_map(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(status/count/runtime 경계만)."""
    return {
        "source_graph_hot_post_integration_status": out["source_graph_hot_post_integration_status"],
        "mapping_count": out["mapping_count"],
        "hot_post_field_count": out["hot_post_field_count"],
        "runtime_enabled": out["runtime_enabled"],
        "public_post_body_generated": out["public_post_body_generated"],
        "production_gold_count": out["production_gold_count"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#95 §16 Source-graph/time-series → Hot Intelligence Post field 통합 매핑 "
                     "(CONTRACT-ONLY·runtime 0·insight 게시 0·timeline same_event 단정 0·"
                     "community/market anchor 금지·public_readiness 는 R1/R2 요구)."))
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_source_graph_hot_post_integration_map()
    if ns.json:
        print(json.dumps(sanitized_source_graph_hot_post_integration_map(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} version={out['contract_version']} "
          f"status={out['source_graph_hot_post_integration_status']} runtime_enabled={out['runtime_enabled']}")
    print(f"- mappings ({out['mapping_count']}) — source_graph_component → hot_post_field:")
    for m in out["mappings"]:
        anchor = " [anchor]" if m["anchor_eligible"] else ""
        target = m["hot_post_field"] if m["hot_post_field"] is not None else "(no standalone field)"
        print(f"    - {m['source_graph_component']} -> {target}{anchor}  [{m['note']}]")
    print(f"- mapped_hot_post_fields ({len(out['mapped_hot_post_fields'])}): "
          f"{', '.join(out['mapped_hot_post_fields'])}")
    print(f"- post_only_fields ({len(out['post_only_fields'])}): {', '.join(out['post_only_fields'])}")
    print(f"- anchor_components={out['anchor_components']} non_anchor_components={out['non_anchor_components']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

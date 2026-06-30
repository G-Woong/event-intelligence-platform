"""ADR#94 — Source-graph + time-series insight 계약 (기존 게이트에 결속하는 CANDIDATE-ONLY contract·runtime 0).

이 모듈은 "여러 소스를 그래프(source/evidence/entity node + KG edge)로 잇고, 사건의 시계열(timeline update)을
누적해 insight 후보를 만든다"는 미래 제품 방향을 **새 어휘 0** 으로 기존 계약에 결속한다(compose/cite only).
재구현·신규 enum·신규 게이트를 만들지 않고, 이미 정의된 문서들의 개념을 인용(cite)해 한 곳에서 묶을 뿐이다:
  - storage class / KG edge / community 경계 → RAG_KG_ENTITY_GATE_CONTRACT.md
  - source role / catalog·market context → INTELLIGENCE_UNIT_CONTRACT.md §3
  - official/news anchor 정책 → HOT_INTELLIGENCE_POST_CONTRACT.md §3 (`is_valid_anchor_role` 재사용)
  - uncertainty / may-infer / must-NOT-assert / MERGE_GATE 의존 → LLM_EVIDENCE_PACKET_CONTRACT.md
  - timeline append-only / event identity → EVENT_SCHEMA.md
  - human label provenance / R1·R2 → RAG_KG_AGENT_READINESS.md, HOT_POST_GATE_ALIGNMENT.md

핵심 불변(CANDIDATE-ONLY): graph edge 는 MERGE_GATE 전까지 truth 아님 · community/market/catalog 는 evidence anchor 금지 ·
insight 후보는 게시 불가 · timeline update 가 same_event 를 단정하지 않음 · public_readiness 는 R1(gold)·R2(MERGE_GATE)
요구 · LLM 요약은 gate 전 비활성 · official/news 만 anchor. 이 모듈은 runtime 0(merge/LLM/embedding/network/public IU 0)
이며 게시하지 않는다 — 계약을 조립·검증할 뿐이다(`_assert_pii_safe` 재귀 가드).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.hot_intelligence_post_contract import (
    ANCHOR_ROLES,
    NON_ANCHOR_ROLES,
    is_valid_anchor_role,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "source_graph_timeseries_insight_contract"
CONTRACT_VERSION = "source_graph_timeseries_insight_v1"
CONTRACT_STATUS_CANDIDATE_ONLY = "candidate_only_runtime_disabled"

# ── 재사용 enum (신규 어휘 0 · 각 출처 문서 인용) ─────────────────────────────────────────────────────────────
# storage class 어휘 — RAG_KG_ENTITY_GATE_CONTRACT.md (§1 RAG ingestion gate / §5 Public IU gate).
STORAGE_CLASS_ENUM: tuple[str, ...] = (
    "verified", "candidate", "reaction", "signal", "enrichment", "url_candidate")
# source role 어휘 — INTELLIGENCE_UNIT_CONTRACT.md §3 Source Role Contract.
SOURCE_ROLE_ENUM: tuple[str, ...] = (
    "official", "article", "news", "community", "market", "catalog", "search", "unknown")
# retrieval 사용 허용 어휘 — LLM_EVIDENCE_PACKET_CONTRACT.md §1/§7 (allowed inputs / source-role boundary).
ALLOWED_RETRIEVAL_USE_ENUM: tuple[str, ...] = (
    "evidence", "context_only", "reaction_only", "excluded")
# KG edge 타입 — RAG_KG_ENTITY_GATE_CONTRACT.md §2 KG edge eligibility.
KG_EDGE_TYPES: tuple[str, ...] = (
    "same_event", "update_of", "reaction_to", "market_signal_for", "mentions", "caused_by")
# merge gate 상태 어휘 — LLM_EVIDENCE_PACKET_CONTRACT.md §8 MERGE_GATE dependency.
MERGE_GATE_STATUS_ENUM: tuple[str, ...] = ("blocked", "eligible")

# ── 15 components: (component, role_or_storage_class, candidate_until_merge_gate, citation) ─────────────────
# anchor_eligible 는 선언하지 않고 `is_valid_anchor_role(role_or_storage_class)` 로 계산한다
# (official/news 만 True · community/market/catalog/그 외 storage class 는 False). role_or_storage_class 값은
# 모두 STORAGE_CLASS_ENUM 또는 SOURCE_ROLE_ENUM 의 기존 어휘다(신규 0).
_COMPONENT_SPECS: tuple[tuple[str, str, bool, str], ...] = (
    ("event_identity", "verified", True,
     "EVENT_SCHEMA.md §Event (events 테이블) / event_identity_map"),
    ("source_nodes", "unknown", True,
     "INTELLIGENCE_UNIT_CONTRACT.md §3 Source Role Contract"),
    ("evidence_edges", "candidate", True,
     "RAG_KG_ENTITY_GATE_CONTRACT.md §2 KG edge eligibility"),
    ("entity_nodes", "enrichment", True,
     "RAG_KG_ENTITY_GATE_CONTRACT.md §3 Entity candidate provenance"),
    ("timeline_updates", "candidate", True,
     "EVENT_SCHEMA.md §EventUpdate (event_updates 테이블, append-only)"),
    ("official_evidence", "official", True,
     "LLM_EVIDENCE_PACKET_CONTRACT.md §7 source-role boundary; INTELLIGENCE_UNIT_CONTRACT.md §3"),
    ("news_corroboration", "news", True,
     "HOT_INTELLIGENCE_POST_CONTRACT.md §3 Anchor 정책"),
    ("community_reaction_layer", "community", True,
     "RAG_KG_ENTITY_GATE_CONTRACT.md §4 Community reaction layer"),
    ("market_signal_layer", "market", True,
     "INTELLIGENCE_UNIT_CONTRACT.md §3 Source Role Contract"),
    ("catalog_context_layer", "catalog", True,
     "INTELLIGENCE_UNIT_CONTRACT.md §3 Source Role Contract"),
    ("uncertainty_state", "candidate", True,
     "LLM_EVIDENCE_PACKET_CONTRACT.md §6 uncertainty flags"),
    ("insight_candidates", "candidate", True,
     "LLM_EVIDENCE_PACKET_CONTRACT.md §3 may infer (제안일 뿐 truth 아님)"),
    ("human_label_state", "verified", False,
     "RAG_KG_AGENT_READINESS.md §6b-R1b reviewer pilot batch"),
    ("merge_gate_state", "verified", False,
     "LLM_EVIDENCE_PACKET_CONTRACT.md §8 MERGE_GATE dependency"),
    ("public_readiness_state", "verified", False,
     "RAG_KG_ENTITY_GATE_CONTRACT.md §5 Public Intelligence Unit gate"),
)

# ── 9 rules: (rule, value, explanation, citation) — 각 bool + 짧은 설명 + 문서 인용 ───────────────────────────
_RULES: tuple[tuple[str, bool, str, str], ...] = (
    ("graph_edge_candidate_until_merge_gate", True,
     "KG edge 는 MERGE_GATE 통과 전까지 candidate (truth 아님).",
     "RAG_KG_ENTITY_GATE_CONTRACT.md §2 KG edge eligibility; LLM_EVIDENCE_PACKET_CONTRACT.md §8 MERGE_GATE dependency"),
    ("community_is_evidence_anchor", False,
     "community 반응은 reaction_to only — evidence anchor 금지.",
     "RAG_KG_ENTITY_GATE_CONTRACT.md §4 Community reaction layer; HOT_INTELLIGENCE_POST_CONTRACT.md §3 Anchor 정책"),
    ("market_is_evidence_anchor", False,
     "market 신호는 signal only — evidence anchor 금지.",
     "INTELLIGENCE_UNIT_CONTRACT.md §3 Source Role Contract; HOT_INTELLIGENCE_POST_CONTRACT.md §3 Anchor 정책"),
    ("catalog_is_evidence_anchor", False,
     "catalog/entity 는 context only — evidence anchor 금지.",
     "INTELLIGENCE_UNIT_CONTRACT.md §3 Source Role Contract"),
    ("insight_candidate_publishable", False,
     "insight 후보는 제안일 뿐 truth 아님 — 게시 불가.",
     "LLM_EVIDENCE_PACKET_CONTRACT.md §5 must NOT assert; RAG_KG_ENTITY_GATE_CONTRACT.md §5 Public Intelligence Unit gate"),
    ("timeseries_update_asserts_same_event", False,
     "timeline update 는 append-only 관측이며 same_event 를 단정하지 않는다.",
     "EVENT_SCHEMA.md §EventUpdate (append-only); LLM_EVIDENCE_PACKET_CONTRACT.md §5 must NOT assert"),
    ("public_readiness_requires_r1_r2", True,
     "public_readiness 는 R1(gold)·R2(MERGE_GATE) 를 모두 요구한다.",
     "HOT_POST_GATE_ALIGNMENT.md §1 11개 게이트 요구; RAG_KG_ENTITY_GATE_CONTRACT.md §5 Public Intelligence Unit gate"),
    ("llm_summary_enabled", False,
     "LLM 요약은 MERGE_GATE 전까지 비활성(gate 후 별도 ADR).",
     "LLM_EVIDENCE_PACKET_CONTRACT.md §8 MERGE_GATE dependency; HOT_INTELLIGENCE_POST_CONTRACT.md §4 Runtime No-Go"),
    ("official_news_only_anchor", True,
     "evidence anchor 가 될 수 있는 role 은 official/news 뿐.",
     "HOT_INTELLIGENCE_POST_CONTRACT.md §3 Anchor 정책; INTELLIGENCE_UNIT_CONTRACT.md §3 Source Role Contract"),
)


def _build_components() -> list[dict]:
    """15 component 결속 — anchor_eligible 은 `is_valid_anchor_role` 로 계산(official/news 만 True)."""
    return [
        {
            "component": component,
            "role_or_storage_class": role_or_storage_class,
            "candidate_until_merge_gate": candidate_until_merge_gate,
            "anchor_eligible": is_valid_anchor_role(role_or_storage_class),
            "citation": citation,
        }
        for component, role_or_storage_class, candidate_until_merge_gate, citation in _COMPONENT_SPECS
    ]


def _rule_value(name: str) -> bool:
    """_RULES 단일 출처에서 rule bool 을 끌어온다(top-level 평탄화와 drift 방지)."""
    for rule, value, _explanation, _citation in _RULES:
        if rule == name:
            return value
    raise KeyError(name)  # 선언 누락 = drift → lock 테스트가 잡음.


def build_source_graph_timeseries_insight_contract() -> dict:
    """Source-graph + time-series insight 의 CANDIDATE-ONLY 계약(runtime 0·compose/cite only). 게시하지 않는다."""
    components = _build_components()
    rules = [
        {"rule": rule, "value": value, "explanation": explanation, "citation": citation}
        for rule, value, explanation, citation in _RULES
    ]
    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "source_graph_timeseries_contract_status": CONTRACT_STATUS_CANDIDATE_ONLY,
        # ── runtime guard (항상) ──
        "runtime_enabled": False,
        # ── 15 components ──
        "components": components,
        "component_count": len(components),
        # ── 재사용 enum (출처는 모듈 상단 상수 주석에 인용) ──
        "storage_class_enum": list(STORAGE_CLASS_ENUM),
        "source_role_enum": list(SOURCE_ROLE_ENUM),
        "allowed_retrieval_use_enum": list(ALLOWED_RETRIEVAL_USE_ENUM),
        "kg_edge_types": list(KG_EDGE_TYPES),
        "merge_gate_status_enum": list(MERGE_GATE_STATUS_ENUM),
        # ── anchor 정책 (official/news 만) ──
        "anchor_roles": sorted(ANCHOR_ROLES),
        "non_anchor_roles": dict(NON_ANCHOR_ROLES),
        # ── 9 rules (bool + 설명 + 인용) ──
        "rules": rules,
        "rule_count": len(rules),
        # ── rule 평탄화 (top-level bool — _RULES 단일 출처) ──
        "graph_edge_candidate_until_merge_gate": _rule_value("graph_edge_candidate_until_merge_gate"),
        "community_is_evidence_anchor": _rule_value("community_is_evidence_anchor"),
        "market_is_evidence_anchor": _rule_value("market_is_evidence_anchor"),
        "catalog_is_evidence_anchor": _rule_value("catalog_is_evidence_anchor"),
        "insight_candidate_publishable": _rule_value("insight_candidate_publishable"),
        "timeseries_update_asserts_same_event": _rule_value("timeseries_update_asserts_same_event"),
        "public_readiness_requires_r1_r2": _rule_value("public_readiness_requires_r1_r2"),
        "llm_summary_enabled": _rule_value("llm_summary_enabled"),
        "official_news_only_anchor": _rule_value("official_news_only_anchor"),
        # ── No-Go 경계 (정직·constant) ──
        "merge_allowed": False,
        "same_event_asserted": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "public_iu_allowed": False,
        "network_invoked": False,
        "r2_r7_no_go": True,
    }
    _assert_pii_safe(out, _path="source_graph_timeseries_insight_contract_output")
    return out


def sanitized_source_graph_timeseries_insight_contract(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(status/count/runtime 경계만)."""
    return {
        "source_graph_timeseries_contract_status": out["source_graph_timeseries_contract_status"],
        "component_count": out["component_count"],
        "runtime_enabled": out["runtime_enabled"],
        "public_iu_allowed": out["public_iu_allowed"],
        "r2_r7_no_go": out["r2_r7_no_go"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#94 Source-graph + time-series insight 계약 (CANDIDATE-ONLY·compose/cite only·runtime 0·"
                     "graph edge 는 MERGE_GATE 전 truth 아님·community/market/catalog anchor 금지·insight 게시 0·"
                     "same_event 단정 0·official/news 만 anchor)."))
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_source_graph_timeseries_insight_contract()
    if ns.json:
        print(json.dumps(sanitized_source_graph_timeseries_insight_contract(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} version={out['contract_version']} "
          f"status={out['source_graph_timeseries_contract_status']} runtime_enabled={out['runtime_enabled']}")
    print(f"- components ({out['component_count']}): "
          f"{', '.join(c['component'] for c in out['components'])}")
    print(f"- anchor_eligible components: "
          f"{[c['component'] for c in out['components'] if c['anchor_eligible']]} "
          f"(anchor_roles={out['anchor_roles']})")
    print(f"- rules ({out['rule_count']}):")
    for r in out["rules"]:
        print(f"    - {r['rule']}={r['value']}  [{r['citation']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

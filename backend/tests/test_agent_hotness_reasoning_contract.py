"""ADR#90 §20(53~59) — agent hotness reasoning contract 테스트(criteria 정의·hotness 만으로 게시 0·요구/blocker·runtime 0)."""
from __future__ import annotations

from backend.app.tools.agent_hotness_reasoning_contract import (
    HOTNESS_CRITERIA,
    build_agent_hotness_reasoning_contract,
    evaluate_hotness_candidate,
)


# ── 53. hotness criteria defined ───────────────────────────────────────────────────────────────────────────
def test_53_criteria_defined():
    c = build_agent_hotness_reasoning_contract()
    assert c["criteria_count"] == len(HOTNESS_CRITERIA) >= 10
    for k in ("novelty", "stakes", "conflict", "controversy", "cross_source_corroboration",
              "time_sensitivity", "follow_up_potential", "safety_sensitivity"):
        assert k in c["criteria"]


# ── 54. hotness cannot publish alone ───────────────────────────────────────────────────────────────────────
def test_54_hotness_cannot_publish_alone():
    c = build_agent_hotness_reasoning_contract()
    assert c["can_publish_on_hotness_alone"] is False
    # 모든 criteria 가 강해도 게시 불가(publish_blockers 가 선행 게이트 명시).
    r = evaluate_hotness_candidate({k: "high" for k in HOTNESS_CRITERIA})
    assert r["can_publish_on_hotness_alone"] is False
    assert "hotness_alone_does_not_publish" in r["publish_blockers"]


# ── 55. evidence requirements required ─────────────────────────────────────────────────────────────────────
def test_55_evidence_requirements_required():
    r = evaluate_hotness_candidate({"novelty": 1})
    assert isinstance(r["evidence_requirements"], list) and len(r["evidence_requirements"]) >= 1
    assert any("official" in e.lower() for e in r["evidence_requirements"])


# ── 56. source requirements required ───────────────────────────────────────────────────────────────────────
def test_56_source_requirements_required():
    r = evaluate_hotness_candidate({"stakes": "high"})
    assert isinstance(r["source_requirements"], list) and len(r["source_requirements"]) >= 1
    assert any("anchor" in s.lower() for s in r["source_requirements"])


# ── 57. community layer requirements marked reaction_to only ───────────────────────────────────────────────
def test_57_community_layer_reaction_only():
    r = evaluate_hotness_candidate({"community_reaction_potential": 1})
    joined = " ".join(r["community_layer_requirements"]).lower()
    assert "reaction_to" in joined
    assert "anchor" in joined  # "never an anchor".
    assert r["community_buzz_is_evidence_anchor"] is False


# ── 58. publish blockers generated ─────────────────────────────────────────────────────────────────────────
def test_58_publish_blockers_generated():
    r = evaluate_hotness_candidate({})
    assert len(r["publish_blockers"]) >= 3
    for b in ("requires_official_evidence", "requires_human_label_provenance", "requires_merge_gate"):
        assert b in r["publish_blockers"]


# ── 59. runtime disabled ───────────────────────────────────────────────────────────────────────────────────
def test_59_runtime_disabled():
    c = build_agent_hotness_reasoning_contract()
    assert c["runtime_enabled"] is False
    assert c["llm_invoked"] is False
    r = evaluate_hotness_candidate({"novelty": 1})
    assert r["runtime_enabled"] is False
    assert r["llm_invoked"] is False


# ── hotness 후보 신호 요약(fired criteria) ─────────────────────────────────────────────────────────────────
def test_hotness_candidate_summary():
    r = evaluate_hotness_candidate({"novelty": 1, "conflict": 1})
    assert r["hotness_candidate"] is True
    assert set(r["fired_criteria"]) == {"novelty", "conflict"}
    r0 = evaluate_hotness_candidate({})
    assert r0["hotness_candidate"] is False
    assert r0["fired_criteria"] == []


# ── forbidden 명시 ─────────────────────────────────────────────────────────────────────────────────────────
def test_forbidden_listed():
    c = build_agent_hotness_reasoning_contract()
    joined = " ".join(c["forbidden"]).lower()
    assert "hotness alone" in joined
    assert "community buzz" in joined
    assert "hallucinate" in joined

"""결정론적 baseline 노드 검증 (Orchestration 하드닝, mock 상수 제거 잠금).

핵심 계약:
- entity/sector/impact/summary는 입력에서 파생된 실제 값이며 mock 상수가 아니다.
- fact_check는 fail-closed: 본문 없음/근거 없음/합성마커 → "hold"(가짜 pass 금지).
- 어떤 baseline 출력에도 `[mock` 마커가 없다.
"""
from __future__ import annotations

from datetime import datetime

from backend.app.schemas.events import RawEvent, NormalizedEvent, FinalEventCard
from agents.nodes.baselines import (
    extract_entities,
    map_sectors,
    impact_baseline,
    summary_baseline,
    structural_fact_check,
    contains_mock_sentinel,
)
from agents.nodes.entity_linking import entity_linking
from agents.nodes.sector_mapping import theme_sector_mapping
from agents.nodes.impact_analysis import impact_analysis
from agents.nodes.fact_check import fact_check
from agents.nodes.final_writer import final_card_writer
from agents.nodes.publish_or_hold import publish_or_hold

_REUTERS = "https://www.reuters.com/markets/x"


def _normalized(title: str, body: str) -> NormalizedEvent:
    return NormalizedEvent(
        source="reuters", title=title, body=body,
        occurred_at=datetime.utcnow(), hash="h1",
    )


# --- extract_entities ---

def test_extract_entities_returns_real_proper_nouns():
    ents = extract_entities(
        "OPEC and Saudi Aramco cut output",
        "The European Union responded as Brent crude rose.",
    )
    assert any("OPEC" in e for e in ents)
    assert any("Saudi Aramco" in e for e in ents)
    assert any("European Union" in e for e in ents)
    # 선두 stopword 제거 확인: "The European Union" → "European Union"
    assert "The European Union" not in ents


def test_extract_entities_no_mock_marker_and_empty_on_empty():
    assert extract_entities("", "") == []
    ents = extract_entities("lowercase only text here", "more lowercase words")
    assert all("[mock" not in e for e in ents)


# --- map_sectors ---

def test_map_sectors_keyword_derived():
    theme, sectors = map_sectors("Oil prices surge", "OPEC crude output and pipeline news")
    assert "energy" in sectors
    assert theme == "energy"


def test_map_sectors_general_when_no_keyword():
    theme, sectors = map_sectors("A quiet local festival", "People gathered peacefully today")
    assert theme == "general"
    assert sectors == []
    # 과거 고정 상수(geopolitics/energy/defense)가 더 이상 반환되지 않는다.
    assert "defense" not in sectors


def test_map_sectors_multi_sector_sorted_deterministic():
    theme, sectors = map_sectors(
        "Bank and military",
        "interest rate decision, inflation, missile, troops, weapon, army",
    )
    # defense hit 수가 finance보다 많으므로 우선.
    assert sectors[0] == "defense"
    assert "finance" in sectors


# --- impact_baseline ---

def test_impact_baseline_honest_no_fabricated_claim():
    out = impact_baseline(["energy"], "rss")
    assert "[mock" not in out
    assert "deterministic baseline" in out
    assert "energy" in out
    empty = impact_baseline([], "")
    assert "undetermined" in empty


# --- summary_baseline ---

def test_summary_baseline_extractive_not_mock():
    out = summary_baseline(
        "Title here",
        "First sentence of the body. Second sentence with more detail. Third.",
        ["EntityA"],
    )
    assert "[mock" not in out
    assert out.startswith("First sentence")


def test_summary_baseline_falls_back_to_title_when_no_body():
    assert summary_baseline("Only title", "", []) == "Only title"


# --- structural_fact_check (fail-closed) ---

def test_structural_fact_check_pass_requires_body_and_grounded_evidence():
    assert structural_fact_check("Real body text", [_REUTERS]) == "pass"


def test_structural_fact_check_holds_on_empty_body():
    assert structural_fact_check("", [_REUTERS]) == "hold"


def test_structural_fact_check_holds_without_evidence():
    assert structural_fact_check("Real body text", []) == "hold"
    assert structural_fact_check("Real body text", None) == "hold"


def test_structural_fact_check_holds_on_synthetic_marker_body():
    assert structural_fact_check("[mock summary] event details", [_REUTERS]) == "hold"


def test_structural_fact_check_rejects_synthetic_evidence_url():
    assert structural_fact_check("Real body", ["https://mock.local/x"]) == "hold"


# --- node-level (mock provider 기본) ---

def test_entity_linking_node_no_mock_constant():
    state = {"normalized": _normalized("Apple and Microsoft", "Tim Cook spoke today.")}
    out = entity_linking(state)
    assert "[mock-entity-1]" not in out["entities"]
    assert any("Apple" in e for e in out["entities"])


def test_sector_mapping_node_no_fixed_constant():
    state = {"normalized": _normalized("Vaccine approved", "FDA cleared the drug after clinical trials.")}
    out = theme_sector_mapping(state)
    assert out["theme"] == "health"
    assert out["sectors"] != ["energy", "defense"]


def test_impact_analysis_node_baseline_no_mock(monkeypatch):
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    state = {"normalized": _normalized("Oil up", "OPEC crude"), "sectors": ["energy"]}
    out = impact_analysis(state)
    assert "[mock]" not in out["impact"]
    assert "deterministic baseline" in out["impact"]


def test_fact_check_node_fail_closed_empty_body(monkeypatch):
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    state = {"normalized": _normalized("T", ""), "evidence": [_REUTERS]}
    out = fact_check(state)
    assert out["fact_check"] == "hold"


def test_fact_check_node_pass_with_body_and_evidence(monkeypatch):
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    state = {"normalized": _normalized("T", "Real grounded body."), "evidence": [_REUTERS]}
    out = fact_check(state)
    assert out["fact_check"] == "pass"


def test_fact_check_node_no_fake_pass_without_evidence(monkeypatch):
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    state = {"normalized": _normalized("T", "Real body but no evidence."), "evidence": []}
    out = fact_check(state)
    assert out["fact_check"] == "hold"


# --- contains_mock_sentinel (게이트 백스톱) ---

def test_contains_mock_sentinel_detects_bracketed_markers():
    assert contains_mock_sentinel("[fallback] medium-term supply disruption risk")
    assert contains_mock_sentinel("normal", ["[mock-entity-1]"])
    assert contains_mock_sentinel("[skip] no normalized event")


def test_contains_mock_sentinel_ignores_plain_english_words():
    # 'synthetic biology' 같은 실제 기사 단어는 오탐하지 않는다(대괄호 센티넬만).
    assert not contains_mock_sentinel("Synthetic biology breakthrough announced")
    assert not contains_mock_sentinel("placeholder discussion in parliament")
    assert not contains_mock_sentinel("Real summary about OPEC", ["OPEC", "Saudi Aramco"])


def _gate_card(summary: str, impact_path: str, entities=None) -> FinalEventCard:
    return FinalEventCard(
        title="T", summary=summary, theme="energy", sectors=["energy"],
        entities=entities or [], impact_path=impact_path, evidence=[_REUTERS],
        confidence_score=0.75, status="hold",
    )


def _gate_state(card: FinalEventCard) -> dict:
    return {
        "final_card": card,
        "normalized": _normalized("T", "Real grounded body text."),
        "fact_check": "pass",
        "evidence": [_REUTERS],
    }


def test_gate_holds_card_with_fallback_impact():
    """[fallback] impact가 evidence/fact_check 게이트를 우회해 published 되지 않는다."""
    card = _gate_card("Real summary", "[fallback] medium-term supply disruption risk")
    out = publish_or_hold(_gate_state(card))
    assert out["status"] == "hold"
    assert card.status == "hold"


def test_gate_holds_card_with_mock_summary():
    card = _gate_card("[mock summary] event details", "Relevant to energy sector(s).")
    out = publish_or_hold(_gate_state(card))
    assert out["status"] == "hold"


def test_gate_publishes_clean_baseline_card():
    """합성 마커 없는 baseline 카드는 정상 published."""
    card = _gate_card(
        "OPEC and Saudi Aramco weigh an output cut.",
        "Relevant to energy sector(s). Quantitative impact not assessed (deterministic baseline).",
        entities=["OPEC", "Saudi Aramco"],
    )
    out = publish_or_hold(_gate_state(card))
    assert out["status"] == "published"
    assert card.status == "published"


def test_impact_node_openai_fallback_constant_replaced(monkeypatch):
    """openai provider에서 analyze_impact가 [fallback] 상수를 줘도 baseline으로 대체된다."""
    from backend.app.core.config import settings
    import agents.nodes.impact_analysis as mod
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    class _R:
        impact = "[fallback] medium-term supply disruption risk"

    monkeypatch.setattr(mod, "analyze_impact", lambda **kw: _R())
    state = {"normalized": _normalized("Oil", "OPEC crude"), "sectors": ["energy"]}
    out = impact_analysis(state)
    assert "[fallback]" not in out["impact"]
    assert "deterministic baseline" in out["impact"]


def test_final_writer_openai_fallback_summary_replaced(monkeypatch):
    """openai provider에서 write_final_card가 [fallback summary]를 줘도 추출 baseline 유지."""
    from backend.app.core.config import settings
    import agents.nodes.final_writer as mod
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")

    class _S:
        summary = "[fallback summary] xyz"

    monkeypatch.setattr(mod, "write_final_card", lambda **kw: _S())
    state = {"normalized": _normalized("Title", "First real sentence. Second sentence.")}
    out = final_card_writer(state)
    assert "[fallback" not in out["final_card"].summary
    assert out["final_card"].summary.startswith("First real sentence")

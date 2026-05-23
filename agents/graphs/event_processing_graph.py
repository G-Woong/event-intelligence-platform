from __future__ import annotations

from langgraph.graph import StateGraph, END

from agents.state.event_state import EventState
from agents.nodes.parse_source import source_parse
from agents.nodes.normalize_event import normalize_event
from agents.nodes.deduplicate import deduplicate_event
from agents.nodes.entity_linking import entity_linking
from agents.nodes.sector_mapping import theme_sector_mapping
from agents.nodes.retrieve_context import retrieve_past_context
from agents.nodes.impact_analysis import impact_analysis
from agents.nodes.evidence_check import evidence_check
from agents.nodes.fact_check import fact_check
from agents.nodes.final_writer import final_card_writer
from agents.nodes.publish_or_hold import publish_or_hold
from backend.app.schemas.events import RawEvent, FinalEventCard


def _build_graph() -> StateGraph:
    g = StateGraph(EventState)
    g.add_node("source_parse", source_parse)
    g.add_node("normalize_event", normalize_event)
    g.add_node("deduplicate_event", deduplicate_event)
    g.add_node("entity_linking", entity_linking)
    g.add_node("theme_sector_mapping", theme_sector_mapping)
    g.add_node("retrieve_past_context", retrieve_past_context)
    g.add_node("impact_analysis", impact_analysis)
    g.add_node("evidence_check", evidence_check)
    g.add_node("run_fact_check", fact_check)
    g.add_node("final_card_writer", final_card_writer)
    g.add_node("publish_or_hold", publish_or_hold)

    g.set_entry_point("source_parse")
    g.add_edge("source_parse", "normalize_event")
    g.add_edge("normalize_event", "deduplicate_event")
    g.add_edge("deduplicate_event", "entity_linking")
    g.add_edge("entity_linking", "theme_sector_mapping")
    g.add_edge("theme_sector_mapping", "retrieve_past_context")
    g.add_edge("retrieve_past_context", "impact_analysis")
    g.add_edge("impact_analysis", "evidence_check")
    g.add_edge("evidence_check", "run_fact_check")
    g.add_edge("run_fact_check", "final_card_writer")
    g.add_edge("final_card_writer", "publish_or_hold")
    g.add_edge("publish_or_hold", END)
    return g


_compiled = _build_graph().compile()


def run(raw_event: RawEvent) -> FinalEventCard:
    initial: EventState = {
        "raw": raw_event,
        "normalized": None,
        "dedupe_key": None,
        "entities": [],
        "theme": "",
        "sectors": [],
        "past_context": [],
        "impact": "",
        "evidence": [],
        "fact_check": "",
        "final_card": None,
        "status": "",
    }
    final_state = _compiled.invoke(initial)
    card = final_state.get("final_card")
    if card is None:
        raise RuntimeError("EventProcessingGraph produced no final_card")
    return card

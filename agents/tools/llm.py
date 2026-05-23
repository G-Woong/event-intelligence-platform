from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from agents.prompts import load_prompt
from backend.app.services.llm_client import get_llm_client


class ImpactAnalysisOutput(BaseModel):
    impact: str
    horizon: Literal["short", "medium", "long"] = "medium"
    confidence: float = 0.5


class FactCheckOutput(BaseModel):
    status: Literal["pass", "hold"]
    reasoning: str


class SummaryOutput(BaseModel):
    summary: str
    headline: str


def analyze_impact(
    title: str,
    body: str,
    theme: str,
    sectors: list[str],
) -> ImpactAnalysisOutput:
    prompt = load_prompt("impact_analysis").format(
        title=title,
        body=body,
        theme=theme,
        sectors=", ".join(sectors) if sectors else "unknown",
    )
    result = get_llm_client().complete_json(prompt, schema=ImpactAnalysisOutput)
    if result is None:
        return ImpactAnalysisOutput(
            impact="[fallback] medium-term supply disruption risk",
            horizon="medium",
            confidence=0.5,
        )
    return result


def fact_check_claims(
    title: str,
    body: str,
    evidence: list[str],
) -> FactCheckOutput:
    prompt = load_prompt("fact_check").format(
        title=title,
        body=body,
        evidence="\n".join(evidence) if evidence else "No supporting evidence provided.",
    )
    result = get_llm_client().complete_json(prompt, schema=FactCheckOutput)
    if result is None:
        return FactCheckOutput(status="pass", reasoning="[fallback] no contradictions")
    return result


def summarize_event(title: str, body: str) -> SummaryOutput:
    prompt = load_prompt("summarize_event").format(title=title, body=body)
    result = get_llm_client().complete_json(prompt, schema=SummaryOutput)
    if result is None:
        return SummaryOutput(
            summary=f"[fallback summary] {body[:120]}",
            headline=f"[fallback] {title[:60]}",
        )
    return result


def write_final_card(state_snapshot: dict) -> SummaryOutput:
    title = state_snapshot.get("title", "")
    body = state_snapshot.get("body", "")
    entities = state_snapshot.get("entities", [])
    theme = state_snapshot.get("theme", "general")
    past_context = state_snapshot.get("past_context", [])
    prompt = load_prompt("final_card_writer").format(
        title=title,
        body=body,
        entities=", ".join(entities) if entities else "none",
        theme=theme,
        past_context="\n".join(past_context) if past_context else "none",
    )
    result = get_llm_client().complete_json(prompt, schema=SummaryOutput)
    if result is None:
        return SummaryOutput(
            summary=f"[fallback summary] {body[:120]}",
            headline=f"[fallback] {title[:60]}",
        )
    return result

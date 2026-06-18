from __future__ import annotations

"""P0 하드닝: mock/미검증 콘텐츠 카드가 published로 노출되지 않는지 그래프 레벨 보증.

좋은 완료의 핵심 불변(§16): "mock card published 차단". evidence가 실 URL로 grounding되지
않거나 본문이 비면 fail-closed로 hold 되어야 한다.
"""

from datetime import datetime

import pytest

from backend.app.services.llm_client import reset_llm_client_cache, MockLLMClient
from backend.app.schemas.events import RawEvent
from agents.graphs.event_processing_graph import run
from agents.nodes.publish_or_hold import publish_or_hold
from agents.state.event_state import EventState


def setup_function():
    reset_llm_client_cache()


def teardown_function():
    reset_llm_client_cache()


def _inject_mock():
    import backend.app.services.llm_client as llm_mod
    llm_mod._client_cache = MockLLMClient()


def _raw(url: str, text: str = "Major policy development affecting energy markets today.") -> RawEvent:
    return RawEvent(
        source="test",
        url=url,
        fetched_at=datetime.utcnow(),
        raw_text=text,
        raw_metadata={},
    )


def test_valid_source_url_publishes():
    _inject_mock()
    card = run(_raw("https://www.reuters.com/markets/article-123"))
    assert card.status == "published"


def test_synthetic_url_held_not_published():
    _inject_mock()
    card = run(_raw("https://mock.local/synthetic-1"))
    assert card.status == "hold"


def test_missing_url_held_not_published():
    _inject_mock()
    card = run(_raw(""))
    assert card.status == "hold"


def test_empty_body_held_not_published():
    _inject_mock()
    # 본문 공백 → fact_check가 pass여도 게이트가 hold
    card = run(_raw("https://www.reuters.com/x", text="   "))
    assert card.status == "hold"


# --- publish_or_hold 단위 게이트 ---

def _gate_state(fact_check: str, evidence: list[str], body: str, meta: dict | None = None) -> EventState:
    from backend.app.schemas.events import NormalizedEvent, FinalEventCard

    raw = _raw("https://x.test")
    raw.raw_metadata = meta or {}
    normalized = NormalizedEvent(
        source="s", title="t", body=body, occurred_at=datetime.utcnow(), hash="h"
    )
    card = FinalEventCard(title="t", summary="s", theme="general", status="hold")
    return {
        "raw": raw,
        "normalized": normalized,
        "fact_check": fact_check,
        "evidence": evidence,
        "final_card": card,
    }


def test_gate_publishes_when_grounded():
    state = _gate_state("pass", ["https://www.reuters.com/article"], "real body")
    out = publish_or_hold(state)
    assert out["status"] == "published"
    assert state["final_card"].status == "published"


def test_gate_holds_mock_evidence():
    state = _gate_state("pass", ["[mock-source-1]"], "real body")
    out = publish_or_hold(state)
    assert out["status"] == "hold"


def test_gate_holds_fact_check_hold():
    state = _gate_state("hold", ["https://www.reuters.com/article"], "real body")
    out = publish_or_hold(state)
    assert out["status"] == "hold"


def test_gate_holds_corroboration_required_even_if_grounded():
    state = _gate_state(
        "pass",
        ["https://www.reuters.com/article"],
        "real body",
        meta={"confirmation_policy": "unconfirmed_until_corroborated"},
    )
    out = publish_or_hold(state)
    assert out["status"] == "hold"

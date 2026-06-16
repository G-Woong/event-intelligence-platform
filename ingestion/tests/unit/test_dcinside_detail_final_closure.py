"""G-4: dcinside final closure — community preview 역할 재정의(애매한 DEGRADED 금지) + corroboration."""
from __future__ import annotations

from types import SimpleNamespace

from ingestion.orchestration.dcinside_strategy import DCInsideDetailAudit, DCInsideStrategyResult
from ingestion.orchestration.final_source_closure import PRODUCTION_READY_COMMUNITY_PREVIEW
from ingestion.orchestration.production_state import (
    PRODUCTION_READY_COMMUNITY_PREVIEW as PS_COMMUNITY_PREVIEW,
    derive_production_state,
)
from ingestion.orchestration.source_strategy_memory import SourceStrategyMemory
from ingestion.tools.run_final_source_closure import _close_dcinside

_VIEW = "https://gall.dcinside.com/mgallery/board/view/?id=stockus&no={}"


def _eq(n):
    return {"record_type": "community_signal", "source_id": "dcinside", "title_or_label": f"제목 {n}",
            "source_url_or_evidence": _VIEW.format(n), "canonical_url": _VIEW.format(n),
            "published_at_or_observed_at": "2026-06-16T10:00:00+09:00",
            "body_state_or_signal": "community_signal",
            "confirmation_policy": "unconfirmed_until_corroborated", "quality_pre_gate_decision": "pass"}


def _dc_list():
    recs = tuple(_eq(n) for n in (1, 2, 3))
    return DCInsideStrategyResult("dcinside", "stockus", "u", True, 200, None, recs, 3, "COMMUNITY_SIGNAL_ALIVE")


def _dc_audit(urls):
    return DCInsideDetailAudit("dcinside", tuple(urls), len(urls), (200,) * len(urls), None,
                               ".write_div", 0, False, "DETAIL_BODY_EMPTY_STATIC")


def _close():
    return _close_dcinside(robots_get=lambda u: "User-agent: *\nAllow: /\n",
                           dcinside_list_collect=_dc_list, dcinside_detail_audit=_dc_audit)


def test_dcinside_closed_as_community_preview_not_degraded():
    closure, records, mem, patch = _close()
    assert closure.final_status == PRODUCTION_READY_COMMUNITY_PREVIEW
    assert closure.is_community_preview() is False  # eq counts는 main에서 부여(여기선 0) → 역할만 확인
    assert closure.is_degraded() is False
    assert mem.final_status == "COMMUNITY_PREVIEW_SIGNAL_ALIVE"
    assert "community_preview_signal_is_valid_role" in mem.llm_agent_hints
    assert patch["readiness_status"] == "COMMUNITY_PREVIEW_READY"


def test_dcinside_records_get_corroboration_metadata():
    _, records, _, _ = _close()
    # stockus(금융 익명 갤러리) → internal_queue_only + 외부확인 필수
    assert all(r["publish_level"] == "internal_queue_only" for r in records)
    assert all(r["requires_external_confirmation"] is True for r in records)
    # PII(작성자 닉네임) 필드 없음(애초에 미수집)
    assert all("author" not in r and "nickname" not in r for r in records)


def test_community_preview_memory_derives_to_preview_tier_not_degraded():
    mem = {"dcinside": SourceStrategyMemory(
        source_id="dcinside", previous_status="PRODUCTION_READY_DEGRADED",
        final_status="COMMUNITY_PREVIEW_SIGNAL_ALIVE",
        root_cause_after=("LIST_PREVIEW_ONLY_NO_BODY_BY_POLICY", "TOS_AUTOMATED_USE_UNVERIFIED"),
        successful_strategy="robots_allowed_static_list_community_preview")}
    profile = SimpleNamespace(source_id="dcinside", enabled=True, source_group="community",
                              skip_reason=None, live_eligible="true", preferred_strategy=None)
    state = derive_production_state(profile, memory=mem)
    assert state.current_status == PS_COMMUNITY_PREVIEW == PRODUCTION_READY_COMMUNITY_PREVIEW
    assert state.production_ready is True       # schedulable production tier

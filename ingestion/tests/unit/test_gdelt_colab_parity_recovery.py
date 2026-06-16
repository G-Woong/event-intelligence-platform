"""G-4: GDELT recovery — 연속 pending escalation 카운터 + scheduled resume 증거(단순 pending 금지)."""
from __future__ import annotations

from ingestion.orchestration.gdelt_strategy import GdeltStrategyResult
from ingestion.orchestration.rate_limit_governor import RateLimitGovernor
from ingestion.tools.run_final_source_closure import _close_gdelt, _parse_consecutive_pending
from ingestion.orchestration.source_strategy_memory import SourceStrategyMemory


def _gdelt_429(gov):
    return GdeltStrategyResult("gdelt", False, 429, (), 0, ("broad", "single_keyword", "narrow"),
                               "EXTERNAL_RATE_LIMITED_PENDING_RESUME",
                               "2026-06-16T12:31:00Z", "2026-06-16T12:31:00Z", "provider_rate_limited")


def test_consecutive_pending_increments_and_records_evidence():
    _, _, mem, _ = _close_gdelt(governor=RateLimitGovernor(), gdelt_collect=_gdelt_429, prior_pending=0)
    assert "consecutive_pending=1" in mem.evidence
    assert "escalation=scheduled_resume" in mem.evidence
    # 단순 pending이 아니라 scheduled state 증거(재현 커맨드/쿼리 프로필/next_resume) 포함
    assert "repro_cmd=" in mem.evidence
    assert "query_profile=broad|single_keyword|narrow" in mem.evidence
    assert "next_resume_at=2026-06-16T12:31:00Z" in mem.evidence


def test_escalation_flag_at_threshold():
    # prior_pending=2 → consecutive=3 → escalation 요구 플래그
    _, _, mem, _ = _close_gdelt(governor=RateLimitGovernor(), gdelt_collect=_gdelt_429, prior_pending=2)
    assert "consecutive_pending=3" in mem.evidence
    assert "escalation=ESCALATE" in mem.evidence
    assert "ESCALATION_REQUIRED" in mem.root_cause_after


def test_parse_consecutive_pending_round_trip():
    m = SourceStrategyMemory(source_id="gdelt", previous_status="x", final_status="y",
                             evidence="attempts=broad;consecutive_pending=4;escalation=ESCALATE")
    assert _parse_consecutive_pending(m) == 4
    assert _parse_consecutive_pending(None) == 0


def test_colab_parity_note_preserved_in_pending():
    _, _, mem, _ = _close_gdelt(governor=RateLimitGovernor(), gdelt_collect=_gdelt_429, prior_pending=0)
    # 응답 레벨 parity는 정직하게 UNVERIFIED로 표기(둔갑 금지)
    assert "colab_parity:code_identical" in mem.evidence
    assert "response_diff=UNVERIFIED" in mem.evidence

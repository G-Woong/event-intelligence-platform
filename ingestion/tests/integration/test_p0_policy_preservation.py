"""P0: 정책 보존 — community corroboration hold / policy_excluded skip / 우회 금지 / secret(네트워크 0)."""
from __future__ import annotations

import json

from ingestion.integration import downstream_contracts as contracts
from ingestion.integration.p0_integration_runner import (
    _REPRESENTATIVE_RECORDS,
    _load_policy_excluded,
)


def test_corroboration_required_policies_detected():
    for p in ("unconfirmed_until_corroborated", "internal_queue_only", "publish_blocked_until_corrob"):
        assert contracts.is_corroboration_required({"confirmation_policy": p}) is True
    assert contracts.is_corroboration_required({"confirmation_policy": "official_source"}) is False
    assert contracts.is_corroboration_required({"corroboration_required": True}) is True


def test_publish_or_hold_holds_community_signal():
    from backend.app.schemas.events import RawEvent, FinalEventCard
    from agents.nodes.publish_or_hold import publish_or_hold

    raw = RawEvent(
        source="community:product_hunt", url="https://ph.test/x", raw_text="",
        raw_metadata={"confirmation_policy": "unconfirmed_until_corroborated"},
    )
    card = FinalEventCard(title="t", summary="s", theme="tech")
    state = {"raw": raw, "final_card": card, "fact_check": "pass"}
    out = publish_or_hold(state)
    # fact_check 가 pass 여도 corroboration 강제 → hold
    assert out["status"] == "hold"
    assert card.status == "hold"


def test_publish_or_hold_publishes_standard_source():
    # P0 하드닝: 표준 소스도 published는 (유효 근거 URL + 본문 + fact_check pass) 모두 충족 시에만.
    from datetime import datetime
    from backend.app.schemas.events import RawEvent, FinalEventCard, NormalizedEvent
    from agents.nodes.publish_or_hold import publish_or_hold

    raw = RawEvent(source="official:sec_edgar", url="https://www.sec.gov/x", raw_text="real body",
                   raw_metadata={"confirmation_policy": "official_source"})
    card = FinalEventCard(title="t", summary="s", theme="tech")
    normalized = NormalizedEvent(source="official:sec_edgar", title="t", body="real body",
                                 occurred_at=datetime.utcnow(), hash="h")
    out = publish_or_hold({
        "raw": raw, "final_card": card, "fact_check": "pass",
        "normalized": normalized, "evidence": ["https://www.sec.gov/x"],
    })
    assert out["status"] == "published"
    assert card.status == "published"


def test_publish_or_hold_holds_standard_source_without_grounded_evidence():
    # P0 하드닝(fail-closed): 근거 URL이 없으면 official 소스라도 hold(mock evidence 노출 차단).
    from datetime import datetime
    from backend.app.schemas.events import RawEvent, FinalEventCard, NormalizedEvent
    from agents.nodes.publish_or_hold import publish_or_hold

    raw = RawEvent(source="official:sec_edgar", url="https://www.sec.gov/x", raw_text="real body",
                   raw_metadata={"confirmation_policy": "official_source"})
    card = FinalEventCard(title="t", summary="s", theme="tech")
    normalized = NormalizedEvent(source="official:sec_edgar", title="t", body="real body",
                                 occurred_at=datetime.utcnow(), hash="h")
    out = publish_or_hold({
        "raw": raw, "final_card": card, "fact_check": "pass",
        "normalized": normalized, "evidence": ["[mock-source-1]"],
    })
    assert out["status"] == "hold"
    assert card.status == "hold"


def test_representative_records_have_no_policy_excluded_source():
    # reuters/x/blind/fmkorea 등 MVP_EXCLUDED 를 대표 record 에 넣지 않는다
    banned = {"reuters", "x", "blind", "fmkorea"}
    for r in _REPRESENTATIVE_RECORDS:
        assert r["source_id"] not in banned


def test_load_policy_excluded_from_state(tmp_path):
    state = {"sources": [
        {"source_id": "x", "current_status": "POLICY_EXCLUDED"},
        {"source_id": "blind", "current_status": "POLICY_EXCLUDED"},
        {"source_id": "bbc", "current_status": "PRODUCTION_READY"},
    ]}
    p = tmp_path / "state.json"
    p.write_text(json.dumps(state), encoding="utf-8")
    excluded = _load_policy_excluded(p)
    assert excluded == {"x", "blind"}
    assert "bbc" not in excluded


def test_gdelt_rate_limited_not_in_representative_as_fake_success():
    # gdelt 는 EXTERNAL_RATE_LIMITED — 대표 record 에 fake success 로 넣지 않는다
    for r in _REPRESENTATIVE_RECORDS:
        assert r["source_id"] != "gdelt"


def test_env_status_redaction_does_not_leak_values():
    from backend.app.core.config import settings
    status = settings.redacted_env_status()
    for k, v in status.items():
        # 값이 아니라 'set (len=..)' / 'empty' 형태만 노출
        assert v.startswith(("set", "empty"))

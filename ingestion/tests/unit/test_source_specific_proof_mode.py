"""G-4: SourceSpecificProof — 격리 dedup namespace로 source별 eq/raw contract 증명."""
from __future__ import annotations

from ingestion.orchestration.source_specific_proof import prove_source_eventqueue_contract


def _rec(sid, url, t):
    return {"record_type": "official_record", "source_id": sid, "title_or_label": "T",
            "source_url_or_evidence": url, "canonical_url": url,
            "published_at_or_observed_at": t, "body_state_or_signal": "official_record",
            "confirmation_policy": "source_confirmed", "quality_pre_gate_decision": "pass"}


def test_isolated_namespace_yields_proof_even_if_shared_index_collapsed():
    # 공유 production index에서 collapse될 record라도, 격리 namespace에선 eq/raw proof가 남는다.
    recs = [_rec("culture_info", "https://sma.sbculture.or.kr/x#seq=315929", "2025-02-26"),
            _rec("culture_info", "https://sma.sbculture.or.kr/x#seq=315930", "2025-02-27")]
    proof = prove_source_eventqueue_contract("culture_info", recs)
    assert proof.eventqueue_proof == 2
    assert proof.raw_events_proof == 2
    assert proof.bridge_contract_pass is True
    assert proof.proof_namespace == "proof:culture_info"


def test_duplicate_records_collapse_within_proof_namespace():
    # 동일 url 2건 → proof namespace 안에서 1건만 통과(duplicate-proof ledger).
    recs = [_rec("product_hunt", "https://www.producthunt.com/products/novu", "2026-06-15T07:01:00Z"),
            _rec("product_hunt", "https://www.producthunt.com/products/novu", "2026-06-15T07:01:00Z")]
    proof = prove_source_eventqueue_contract("product_hunt", recs)
    assert proof.live_records == 2
    assert proof.eventqueue_proof == 1
    assert proof.duplicates_in_proof == 1
    assert proof.bridge_contract_pass is True


def test_empty_records_no_proof():
    proof = prove_source_eventqueue_contract("gdelt", [])
    assert proof.eventqueue_proof == 0
    assert proof.raw_events_proof == 0

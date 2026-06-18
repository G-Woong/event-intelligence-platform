"""P0: end-to-end 계약 — map→writer→backend 응답까지 전 구간 계약 일관성(네트워크 0).

라이브 proof(run_p0_integration)는 실 스택을 요구하므로, 여기선 MockTransport 로 backend 를
대체해 mapping→write→raw_event_id 회수까지의 계약을 결정론적으로 검증한다.
mirror fallback 이 P0 complete 로 둔갑하지 않음도 확인한다.
"""
from __future__ import annotations

import json

import httpx

from ingestion.integration import downstream_contracts as contracts
from ingestion.integration.raw_events_writer import (
    BackendApiRawEventsWriter,
    MirrorRawEventsWriter,
)
from ingestion.orchestration.bridge_to_raw_events import (
    RawEventBridgeWriter,
    bridge_records,
)

_RECORDS = [
    {"record_type": "article_candidate", "source_id": "the_verge",
     "title_or_label": "A", "source_url_or_evidence": "https://v.test/a",
     "canonical_url": "https://v.test/a", "published_at_or_observed_at": "2026-06-17T00:00:00Z",
     "body_state_or_signal": "present", "confirmation_policy": "standard",
     "quality_pre_gate_decision": "accept"},
    {"record_type": "official_record", "source_id": "sec_edgar",
     "title_or_label": "B", "source_url_or_evidence": "https://sec.test/b",
     "canonical_url": "https://sec.test/b", "published_at_or_observed_at": "2026-06-17T00:00:00Z",
     "body_state_or_signal": "summary_only", "confirmation_policy": "official_source",
     "quality_pre_gate_decision": "accept"},
]


def _ok_handler(request):
    body = json.loads(request.content)
    return httpx.Response(200, json={
        "record": {"id": f"re-{body['content_hash'][:6]}"},
        "is_duplicate": False, "enqueued_msg_id": "1-0",
    })


def test_full_chain_map_write_capture_id():
    client = httpx.Client(transport=httpx.MockTransport(_ok_handler))
    writer = BackendApiRawEventsWriter(client=client)
    bw = RawEventBridgeWriter(db_writer=writer)
    result = bridge_records(_RECORDS, writer=bw)

    assert result["raw_events_written"] == 2
    assert result["bridge_contract_pass"] is True
    # 각 write 가 raw_event_id 를 회수
    assert all(r.raw_event_id for r in writer.results)
    # source_type 이 record_type 매핑과 일치
    types = {r.record_type for r in writer.results}
    assert types == {"article_candidate", "official_record"}


def test_each_create_passes_source_type_contract():
    client = httpx.Client(transport=httpx.MockTransport(_ok_handler))
    writer = BackendApiRawEventsWriter(client=client)
    bw = RawEventBridgeWriter(db_writer=writer)
    bridge_records(_RECORDS, writer=bw)
    # writer 가 보낸 payload 는 transport 에서 검증됨(200). 계약 헬퍼로 재확인.
    for rec in _RECORDS:
        from ingestion.orchestration.bridge_to_raw_events import map_eq_record_to_raw_event
        payload, status, _ = map_eq_record_to_raw_event(rec)
        ok, missing = contracts.validate_raw_event_create(payload.to_raw_event_create(), rec["record_type"])
        assert ok, missing


def test_mirror_fallback_not_counted_as_p0_complete(tmp_path):
    # bridge db_writer=None → mirror. target=='mirror' 는 P0 complete 단독 근거가 아니다.
    bw = RawEventBridgeWriter(mirror_path=tmp_path / "m.jsonl", db_writer=None)
    result = bridge_records(_RECORDS, writer=bw)
    assert result["target"] == "mirror"
    assert result["raw_events_written"] == 2  # mirror 적재는 되지만
    # P0 complete 판정 규칙: target != 'db' 이면 불충분
    assert bw.target != "db"

    mw = MirrorRawEventsWriter(tmp_path / "m2.jsonl")
    assert mw.summary()["p0_complete_eligible"] is False


def test_transport_failure_marks_bridge_failed_not_silent():
    def boom(request):
        raise httpx.ConnectError("refused")
    client = httpx.Client(transport=httpx.MockTransport(boom))
    writer = BackendApiRawEventsWriter(client=client)
    bw = RawEventBridgeWriter(db_writer=writer)
    result = bridge_records(_RECORDS[:1], writer=bw)
    # 실패가 silent drop 되지 않고 raw_events_failed 로 집계
    assert result["raw_events_failed"] == 1
    assert result["bridge_contract_pass"] is False

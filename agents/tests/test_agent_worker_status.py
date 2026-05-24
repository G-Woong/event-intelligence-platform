from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from backend.app.schemas.events import FinalEventCard, RawEvent
from agents.agent_worker import _notify_status, _patch_status


def _make_card() -> FinalEventCard:
    return FinalEventCard(
        id=str(uuid.uuid4()),
        title="Test Event",
        summary="Test summary",
        theme="geopolitics",
        sectors=["energy"],
        entities=["US"],
        confidence_score=0.9,
    )


_RAW_EVENT_ID = str(uuid.uuid4())
_BACKEND_URL = "http://backend:8000"


def test_notify_status_processed_sends_patch():
    card = _make_card()
    with patch("agents.agent_worker.httpx.patch") as mock_patch:
        _notify_status(_RAW_EVENT_ID, "processed", event_card_id=str(card.id))

    mock_patch.assert_called_once()
    call_kwargs = mock_patch.call_args
    assert f"/api/admin/raw-events/{_RAW_EVENT_ID}/status" in call_kwargs[0][0]
    sent_json = call_kwargs[1]["json"]
    assert sent_json["status"] == "processed"
    assert sent_json["event_card_id"] == str(card.id)


def test_notify_status_failed_sends_error_reason():
    with patch("agents.agent_worker.httpx.patch") as mock_patch:
        _notify_status(_RAW_EVENT_ID, "failed", error_reason="boom")

    mock_patch.assert_called_once()
    sent_json = mock_patch.call_args[1]["json"]
    assert sent_json["status"] == "failed"
    assert sent_json["error_reason"] == "boom"


def test_notify_status_none_raw_event_id_skips_patch():
    with patch("agents.agent_worker.httpx.patch") as mock_patch:
        _notify_status(None, "processed")

    mock_patch.assert_not_called()


def test_notify_status_patch_failure_only_warns():
    with patch("agents.agent_worker.httpx.patch", side_effect=Exception("network error")):
        # should not raise
        _notify_status(_RAW_EVENT_ID, "processed")


def test_patch_status_retries_on_transport_error_then_succeeds():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    call_count = [0]

    def side_effect(url, json, timeout):
        call_count[0] += 1
        if call_count[0] < 3:
            raise httpx.TransportError("connection reset")
        return mock_resp

    with patch("agents.agent_worker.httpx.patch", side_effect=side_effect):
        _patch_status("http://backend/status", {"status": "processed"})

    assert call_count[0] == 3


def test_patch_status_all_retries_fail_swallowed_by_notify():
    with patch(
        "agents.agent_worker.httpx.patch",
        side_effect=httpx.TransportError("timeout"),
    ):
        # _notify_status should swallow and warn, not raise
        _notify_status(_RAW_EVENT_ID, "processed")

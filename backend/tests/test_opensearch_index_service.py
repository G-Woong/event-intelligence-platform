from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.schemas.events import FinalEventCard


def _make_card(**kwargs) -> FinalEventCard:
    defaults = dict(
        title="Iran Sanctions Update",
        summary="New sanctions imposed.",
        theme="geopolitics",
        sectors=["energy", "finance"],
        entities=["Iran", "US Treasury"],
    )
    defaults.update(kwargs)
    return FinalEventCard(**defaults)


def test_try_index_card_calls_client_index():
    card = _make_card()
    mock_client = MagicMock()

    with (
        patch("backend.app.services.opensearch_index_service.opensearch_db") as mock_db,
        patch("backend.app.services.opensearch_index_service.settings") as mock_settings,
    ):
        mock_db.get_client.return_value = mock_client
        mock_settings.OPENSEARCH_EVENT_INDEX = "event_cards"
        from backend.app.services.opensearch_index_service import try_index_card
        try_index_card(card)

    mock_client.index.assert_called_once()
    call_kwargs = mock_client.index.call_args[1]
    assert call_kwargs["index"] == "event_cards"
    assert call_kwargs["id"] == str(card.id)
    body = call_kwargs["body"]
    assert body["title"] == card.title
    assert "text_all" in body


def test_try_index_card_failure_does_not_raise():
    card = _make_card()
    mock_client = MagicMock()
    mock_client.index.side_effect = Exception("opensearch down")

    with (
        patch("backend.app.services.opensearch_index_service.opensearch_db") as mock_db,
        patch("backend.app.services.opensearch_index_service.settings") as mock_settings,
    ):
        mock_db.get_client.return_value = mock_client
        mock_settings.OPENSEARCH_EVENT_INDEX = "event_cards"
        from backend.app.services.opensearch_index_service import try_index_card
        try_index_card(card)  # must not raise


def test_ensure_event_cards_index_creates_when_absent():
    mock_client = MagicMock()
    mock_client.indices.exists.return_value = False

    with (
        patch("backend.app.services.opensearch_index_service.opensearch_db") as mock_db,
        patch("backend.app.services.opensearch_index_service.settings") as mock_settings,
    ):
        mock_db.get_client.return_value = mock_client
        mock_settings.OPENSEARCH_EVENT_INDEX = "event_cards"
        from backend.app.services.opensearch_index_service import ensure_event_cards_index
        ensure_event_cards_index()

    mock_client.indices.create.assert_called_once()


def test_card_to_doc_text_all_aggregation():
    card = _make_card()
    from backend.app.services.opensearch_index_service import _card_to_doc
    doc = _card_to_doc(card)

    assert doc["title"] == card.title
    assert doc["summary"] == card.summary
    assert "Iran" in doc["text_all"]
    assert "energy" in doc["text_all"]
    assert isinstance(doc["sectors"], list)
    assert isinstance(doc["entities"], list)

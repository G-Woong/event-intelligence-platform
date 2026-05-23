from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.schemas.events import FinalEventCard


def _make_card(**kwargs) -> FinalEventCard:
    defaults = dict(
        title="Test Event",
        summary="Something happened.",
        theme="geopolitics",
        sectors=["energy"],
        entities=["org_A"],
    )
    defaults.update(kwargs)
    return FinalEventCard(**defaults)


@pytest.mark.asyncio
async def test_try_index_card_calls_insert():
    card = _make_card()
    mock_embed_client = MagicMock()
    mock_embed_client.embed_text.return_value = [0.1] * 1536

    with (
        patch("backend.app.services.vector_index_service.get_embedding_client", return_value=mock_embed_client),
        patch("backend.app.services.vector_index_service.ensure_event_embeddings_collection"),
        patch("backend.app.services.vector_index_service.insert_event_embedding") as mock_insert,
    ):
        from backend.app.services.vector_index_service import try_index_card
        await try_index_card(card)
        mock_insert.assert_called_once()


@pytest.mark.asyncio
async def test_try_index_card_milvus_failure_does_not_raise():
    """Milvus 실패해도 예외 전파 없어야 한다."""
    card = _make_card()

    with (
        patch(
            "backend.app.services.vector_index_service.ensure_event_embeddings_collection",
            side_effect=RuntimeError("milvus down"),
        ),
    ):
        from backend.app.services.vector_index_service import try_index_card
        # must not raise
        await try_index_card(card)


@pytest.mark.asyncio
async def test_upsert_card_pg_write_preserved_on_milvus_failure():
    """upsert_card는 Milvus 실패 시에도 Postgres 결과를 반환해야 한다."""
    card = _make_card()

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    with (
        patch(
            "backend.app.services.vector_index_service.ensure_event_embeddings_collection",
            side_effect=RuntimeError("milvus down"),
        ),
        patch("backend.app.services.event_service.pg_insert") as mock_pg_insert,
    ):
        mock_stmt = MagicMock()
        mock_stmt.on_conflict_do_update.return_value = mock_stmt
        mock_pg_insert.return_value = mock_stmt

        from backend.app.services import event_service
        result = await event_service.upsert_card(mock_session, card)
        assert result.id == card.id

from __future__ import annotations

"""D-2a Event 타임라인 read API — flag 게이트 · 라우트 우선순위 · 단건/목록 shape · 레거시 무영향.

`/api/events/timeline*` 은 EVENT_TIMELINE_API_ENABLED off 면 404(미노출). on 이면 events/
event_updates 를 조회한다. 핵심: `/timeline` 이 `/{event_id}` 라우트로 잡히지 않는지(우선순위) +
기존 /api/events(event_cards) 경로 무영향. 서비스 계층은 mock(여기선 라우팅/게이트만, 실 DB 는 live-PG).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.db.postgres import get_session
from backend.app.main import app
from backend.app.schemas.events import Event, EventUpdate

client = TestClient(app)
_EID = "11111111-1111-1111-1111-111111111111"


async def _fake_session():
    yield AsyncMock()


def _event(**kw) -> Event:
    # 내부 식별자(primary_entity_ids=entities FK, snapshot_card_id=event_cards FK)를 채워
    # 공개 응답에서 구조적으로 제외되는지(PublicEvent) 검증할 수 있게 한다.
    base = dict(
        id=_EID, canonical_title="호르무즈 해협 긴장", status="active",
        primary_entity_ids=["ent-iran"], snapshot_card_id="card-xyz",
    )
    base.update(kw)
    return Event(**base)


def _assert_no_internal_event_ids(event_json: dict) -> None:
    # 공개 Event 뷰는 내부 FK 를 wire 에 싣지 않는다.
    assert "primary_entity_ids" not in event_json
    assert "snapshot_card_id" not in event_json


# ── flag OFF → 미노출(404) ────────────────────────────────────────────────────────
def test_timeline_list_404_when_flag_off():
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch.object(settings, "EVENT_TIMELINE_API_ENABLED", False):
            resp = client.get("/api/events/timeline")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert resp.status_code == 404


def test_timeline_single_404_when_flag_off():
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch.object(settings, "EVENT_TIMELINE_API_ENABLED", False):
            resp = client.get(f"/api/events/timeline/{_EID}")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert resp.status_code == 404


# ── flag ON → 목록(라우트 우선순위: /timeline 이 /{event_id} 로 안 잡힘) ──────────────
def test_timeline_list_returns_events_when_flag_on():
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch.object(settings, "EVENT_TIMELINE_API_ENABLED", True), patch(
            "backend.app.services.event_timeline_service.list_events",
            new_callable=AsyncMock, return_value=[_event()],
        ) as mock_list:
            resp = client.get("/api/events/timeline")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert resp.status_code == 200
    mock_list.assert_awaited_once()        # /{event_id} 가 아니라 /timeline 라우트로 라우팅됨
    body = resp.json()
    assert len(body) == 1 and body[0]["canonical_title"] == "호르무즈 해협 긴장"
    _assert_no_internal_event_ids(body[0])  # 목록도 PublicEvent — 내부 FK 미노출


# ── flag ON → 단건(event + append-only updates); source_refs 는 공개 응답에서 제외 ──────
def test_timeline_single_returns_event_with_updates():
    app.dependency_overrides[get_session] = _fake_session
    upd = EventUpdate(
        id="22222222-2222-2222-2222-222222222222", event_id=_EID,
        observed_at=datetime(2026, 6, 18, tzinfo=timezone.utc), delta_summary="유가 +4%",
        source_refs=["raw_events:abc123", "cluster:def456"],  # 내부 식별자 — 공개 미노출 대상
    )
    try:
        with patch.object(settings, "EVENT_TIMELINE_API_ENABLED", True), patch(
            "backend.app.services.event_timeline_service.get_public_event",
            new_callable=AsyncMock, return_value=(_event(), [upd]),
        ):
            resp = client.get(f"/api/events/timeline/{_EID}")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["event"]["canonical_title"] == "호르무즈 해협 긴장"
    assert len(body["updates"]) == 1 and body["updates"][0]["delta_summary"] == "유가 +4%"
    # 내부 식별자는 화면뿐 아니라 wire 응답에도 실리지 않는다(Public* 스키마).
    assert "source_refs" not in body["updates"][0]          # PublicEventUpdate
    _assert_no_internal_event_ids(body["event"])            # PublicEvent (FK 제외)


def test_timeline_single_404_when_not_found():
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch.object(settings, "EVENT_TIMELINE_API_ENABLED", True), patch(
            "backend.app.services.event_timeline_service.get_public_event",
            new_callable=AsyncMock, return_value=None,
        ):
            resp = client.get("/api/events/timeline/99999999-9999-9999-9999-999999999999")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert resp.status_code == 404


# ── 기존 event_cards 경로 무영향(회귀) ───────────────────────────────────────────────
def test_legacy_event_cards_list_unaffected():
    app.dependency_overrides[get_session] = _fake_session
    try:
        with patch(
            "backend.app.services.event_service.list_events",
            new_callable=AsyncMock, return_value=[],
        ) as mock_cards:
            resp = client.get("/api/events")
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert resp.status_code == 200
    mock_cards.assert_awaited_once()
    assert mock_cards.await_args.kwargs.get("status") == "published"  # 기존 계약 유지(hold 차단)

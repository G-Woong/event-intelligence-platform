"""Phase A deterministic orchestration cycle 단위 테스트 (docs/07, 11).

probe_fn/queue를 주입해 네트워크 없이 결정적으로 cycle 로직을 검증한다.
실제 gdelt+yna live cycle은 CLI smoke(__main__)로 별도 실행한다(회귀 비포함).
"""
from __future__ import annotations

from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult


class FakeQueue:
    """EventQueue JSONL 동작을 흉내내는 인메모리 큐(_id/_status 부여)."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def enqueue(self, item: dict) -> str:
        item_id = f"id-{len(self.items)}"
        self.items.append({"_id": item_id, "_status": "pending", **item})
        return item_id


def _ok(source_id: str, items: int = 3) -> CollectionProbeResult:
    return CollectionProbeResult(
        source_id=source_id, status="LIVE_SUCCESS", strategy_used="api",
        items_found=items,
        artifact_paths=ArtifactPaths(raw_payload=f"/raw/{source_id}.json"),
    )


def _blocked(source_id: str) -> CollectionProbeResult:
    return CollectionProbeResult(
        source_id=source_id, status="BLOCKED", error_category="captcha",
    )


def test_cycle_enqueues_successful_sources():
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    q = FakeQueue()
    report = run_cycle(["gdelt", "yna"], queue=q, probe_fn=lambda sid, **kw: _ok(sid))

    assert report.sources_attempted == 2
    assert report.sources_succeeded == 2
    assert report.items_enqueued == 2
    assert {i["source_id"] for i in q.items} == {"gdelt", "yna"}
    # MVP 필수 5필드가 모두 채워진다
    for it in q.items:
        assert it["title_or_keyword"]
        assert it["source_id"]
        assert it["timestamp"]
        assert "source_url" in it


def test_cycle_skips_blocked_source_but_continues():
    """차단 소스는 큐에 넣지 않고, 다음 소스는 계속 수집한다."""
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    q = FakeQueue()

    def probe(sid, **kw):
        return _blocked(sid) if sid == "gdelt" else _ok(sid)

    report = run_cycle(["gdelt", "yna"], queue=q, probe_fn=probe)

    assert report.sources_succeeded == 1
    assert report.sources_failed == 1
    assert report.items_enqueued == 1
    assert [i["source_id"] for i in q.items] == ["yna"]


def test_cycle_isolates_probe_exception():
    """한 소스의 예외가 다른 소스를 막지 않는다(소스 격리)."""
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    q = FakeQueue()

    def probe(sid, **kw):
        if sid == "gdelt":
            raise RuntimeError("boom")
        return _ok(sid)

    report = run_cycle(["gdelt", "yna"], queue=q, probe_fn=probe)

    assert report.sources_failed == 1
    assert report.sources_succeeded == 1
    assert report.items_enqueued == 1
    assert any(o.status == "CYCLE_ERROR" and o.error == "boom" for o in report.outcomes)


def test_cycle_marks_body_missing_when_no_items():
    """수집 성공이지만 항목 0개면 body_missing=True (사건은 보존, 05 §2)."""
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    q = FakeQueue()

    def probe(sid, **kw):
        return CollectionProbeResult(source_id=sid, status="LIVE_SUCCESS", items_found=0)

    run_cycle(["gdelt"], queue=q, probe_fn=probe)
    assert q.items[0]["body_missing"] is True


def test_cycle_does_not_bypass_health_gate_by_default():
    """force 기본값 False가 probe_fn에 전달된다(health gate 존중, no bypass)."""
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    seen = {}

    def probe(sid, query=None, max_items=5, force=False):
        seen["force"] = force
        return _ok(sid)

    run_cycle(["gdelt"], queue=FakeQueue(), probe_fn=probe)
    assert seen["force"] is False


def test_cycle_report_to_dict_serializable():
    from ingestion.orchestration.run_orchestration_cycle import run_cycle

    report = run_cycle(["yna"], queue=FakeQueue(), probe_fn=lambda sid, **kw: _ok(sid))
    d = report.to_dict()
    assert d["sources_attempted"] == 1
    assert d["items_enqueued"] == 1
    assert isinstance(d["outcomes"], list)
    assert d["outcomes"][0]["source_id"] == "yna"


def test_to_event_seed_maps_fields():
    from ingestion.orchestration.event_seed import to_event_seed

    r = _ok("yna", items=5)
    seed = to_event_seed(r, query="삼성", cycle_id="c1", timestamp="2026-06-14T00:00:00Z")

    assert seed["title_or_keyword"] == "삼성"
    assert seed["source_id"] == "yna"
    assert seed["collection_status"] == "LIVE_SUCCESS"
    assert seed["items_found"] == 5
    assert seed["body_missing"] is False
    assert seed["raw_artifact_path"] == "/raw/yna.json"
    # source_url은 _SERVICE_CONFIGS 엔드포인트(yna RSS)
    assert "yna.co.kr" in seed["source_url"]


def test_to_event_seed_title_falls_back_to_source_id():
    from ingestion.orchestration.event_seed import to_event_seed

    seed = to_event_seed(_ok("gdelt"), query=None, cycle_id="c1", timestamp="t")
    assert seed["title_or_keyword"] == "gdelt"

"""P0 통합 proof runner — source 특성별 record 를 end-to-end 로 흘려 검증한다.

경로: EventQueue record → bridge.map_eq_record_to_raw_event → BackendApiRawEventsWriter
      → backend(POST raw-events: PG upsert + Redis XADD) → worker → agent → LangGraph
      → event_cards. backend 폴링으로 raw_event status(processed) + event_card_id 를 확인한다.

record 소스:
  - article_candidate: 기존 production_event_queue.jsonl 의 실수집 record(live_collected).
  - official/structured/search/community: 실 source_id + 실 공개 URL 기반 대표 record
    (representative). raw_text 는 싣지 않는다(preview_only). 다운스트림 전 구간은 실제로 동작한다.

정책 보존:
  - production_source_state.json 의 POLICY_EXCLUDED source 는 POST 하지 않고 skip 집계.
  - community(internal_queue_only)는 bridge 하지 않는다(내부 큐 전용). preview_candidate 만
    confirmation_policy 를 실어 bridge → B측 publish_or_hold 가 hold.
  - 외부 URL 없는 record 는 bridge 가 held(missing_url). gdelt 등 rate-limited 는 fake success 금지.

네트워크: backend(localhost) 만 호출. 외부 source 직접 probe 없음(대표 record 는 정적). secret 미출력.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from ingestion.integration import downstream_contracts as contracts
from ingestion.integration.raw_events_writer import BackendApiRawEventsWriter
from ingestion.orchestration.bridge_to_raw_events import (
    BRIDGE_STATUS_HELD,
    BRIDGE_STATUS_REJECTED,
    map_eq_record_to_raw_event,
)

_DEFAULT_QUEUE = Path("ingestion/outputs/jsonl/production_event_queue.jsonl")
_DEFAULT_STATE = Path("ingestion/outputs/state/production_source_state.json")

# 대표 record(실 source_id + 실 공개 evidence URL). preview_only(raw_text 미포함).
# article_candidate 는 실수집 큐에서 로드하므로 대표 목록엔 없다.
_REPRESENTATIVE_RECORDS: list[dict] = [
    {
        "record_type": "official_record",
        "source_id": "sec_edgar",
        "title_or_label": "SEC EDGAR — latest 8-K current report filings index",
        "source_url_or_evidence": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K",
        "canonical_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K",
        "published_at_or_observed_at": "2026-06-17T00:00:00Z",
        "body_state_or_signal": "summary_only",
        "confirmation_policy": "official_source",
        "quality_pre_gate_decision": "accept",
        "_origin": "representative",
    },
    {
        "record_type": "structured_signal",
        "source_id": "coinbase_market",
        "title_or_label": "BTC-USD spot ticker",
        "source_url_or_evidence": "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
        "canonical_url": "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
        "published_at_or_observed_at": "2026-06-17T00:00:00Z",
        "body_state_or_signal": "price",
        "confirmation_policy": "structured_source",
        "quality_pre_gate_decision": "accept",
        "_origin": "representative",
    },
    {
        "record_type": "search_result",
        "source_id": "gnews",
        "title_or_label": "Search expansion result — AI product incident coverage",
        "source_url_or_evidence": "https://gnews.io/",
        "canonical_url": "https://gnews.io/",
        "published_at_or_observed_at": "2026-06-17T00:00:00Z",
        "body_state_or_signal": "snippet",
        "confirmation_policy": "search_expansion",
        "quality_pre_gate_decision": "accept",
        "_origin": "representative",
    },
    {
        "record_type": "community_signal",
        "source_id": "product_hunt",
        "title_or_label": "New AI developer tool launch (community preview)",
        "source_url_or_evidence": "https://www.producthunt.com/",
        "canonical_url": "https://www.producthunt.com/",
        "published_at_or_observed_at": "2026-06-17T00:00:00Z",
        "body_state_or_signal": "present",
        # 외부확인 강제 → B측 publish_or_hold 가 hold(early signal, not verified)
        "confirmation_policy": "unconfirmed_until_corroborated",
        "quality_pre_gate_decision": "accept",
        "_origin": "representative",
    },
]


@dataclass
class P0RunConfig:
    base_url: str = "http://localhost:8000"
    admin_token: Optional[str] = None
    queue_path: Path = _DEFAULT_QUEUE
    state_path: Path = _DEFAULT_STATE
    max_records_per_type: int = 1
    poll_timeout_sec: float = 40.0
    poll_interval_sec: float = 1.5
    require_event_card: bool = True
    output_dir: Optional[Path] = None


@dataclass
class ProofRow:
    record_type: str
    source_id: str
    origin: str
    write_status: str
    raw_event_id: Optional[str] = None
    enqueued_msg_id: Optional[str] = None
    dedup_status: str = ""
    policy_status: str = ""
    worker_status: str = ""          # raw_event 최종 status(enqueued→processed/failed)
    langgraph_status: str = ""
    event_card_id: Optional[str] = None
    card_status: str = ""            # published / hold
    final_status: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _load_policy_excluded(state_path: Path) -> set[str]:
    if not state_path.exists():
        return set()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    rows = data.get("sources") if isinstance(data, dict) else data
    excluded: set[str] = set()
    if isinstance(rows, dict):
        rows = list(rows.values())
    for r in rows or []:
        if isinstance(r, dict) and r.get("current_status") == "POLICY_EXCLUDED":
            sid = r.get("source_id")
            if sid:
                excluded.add(sid)
    return excluded


def _load_live_article_records(queue_path: Path, limit: int) -> list[dict]:
    out: list[dict] = []
    if not queue_path.exists():
        return out
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("record_type") != "article_candidate":
            continue
        if not (r.get("source_url_or_evidence") or r.get("canonical_url")):
            continue  # URL 없는 record 는 bridge held 대상 — proof 목적상 제외
        r = dict(r)
        r["_origin"] = "live_collected"
        out.append(r)
        if len(out) >= limit:
            break
    return out


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class _BackendPoller:
    def __init__(self, base_url: str, admin_token: Optional[str], timeout: float = 10.0) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"X-Admin-Token": admin_token} if admin_token else {}
        self._timeout = timeout

    def get_raw_event(self, raw_event_id: str) -> Optional[dict]:
        try:
            with httpx.Client(timeout=self._timeout) as c:
                resp = c.get(f"{self._base}/api/admin/raw-events/{raw_event_id}", headers=self._headers)
            if resp.status_code == 200:
                return resp.json()
        except httpx.HTTPError:
            return None
        return None

    def get_event_card(self, card_id: str) -> Optional[dict]:
        try:
            with httpx.Client(timeout=self._timeout) as c:
                resp = c.get(f"{self._base}/api/events/{card_id}", headers=self._headers)
            if resp.status_code == 200:
                return resp.json()
        except httpx.HTTPError:
            return None
        return None


def run_p0_integration(config: P0RunConfig) -> dict:
    """P0 통합 proof 1회 실행. plan + ledger dict 반환."""
    policy_excluded = _load_policy_excluded(config.state_path)
    writer = BackendApiRawEventsWriter(base_url=config.base_url, admin_token=config.admin_token)
    poller = _BackendPoller(config.base_url, config.admin_token)

    # record 집합: 실수집 article + 대표(official/structured/search/community)
    records: list[dict] = []
    records += _load_live_article_records(config.queue_path, config.max_records_per_type)
    records += _REPRESENTATIVE_RECORDS

    seen_hashes: set[str] = set()
    rows: list[ProofRow] = []

    for rec in records:
        rt = rec.get("record_type", "")
        sid = rec.get("source_id", "")
        origin = rec.get("_origin", "unknown")
        row = ProofRow(record_type=rt, source_id=sid, origin=origin, write_status="")

        # 정책: POLICY_EXCLUDED source 는 호출하지 않는다
        if sid in policy_excluded:
            row.policy_status = "policy_excluded_skipped"
            row.final_status = "SKIPPED_POLICY"
            rows.append(row)
            continue
        # 정책: 내부 큐 전용 community 는 bridge 하지 않는다
        if rec.get("confirmation_policy") == "internal_queue_only":
            row.policy_status = "internal_queue_only_not_bridged"
            row.final_status = "SKIPPED_INTERNAL_QUEUE_ONLY"
            rows.append(row)
            continue

        payload, mstatus, reason = map_eq_record_to_raw_event(rec, collected_at=_iso_now())
        if payload is None:
            if mstatus == BRIDGE_STATUS_HELD:
                row.write_status = contracts.WRITE_HELD_MISSING_URL
                row.final_status = "HELD"
            else:
                row.write_status = contracts.WRITE_FAILED_SCHEMA
                row.final_status = "REJECTED"
            row.note = reason or ""
            rows.append(row)
            continue

        create = payload.to_raw_event_create()
        ok_contract, missing = contracts.validate_raw_event_create(create, rt)
        if not ok_contract:
            row.write_status = contracts.WRITE_FAILED_SCHEMA
            row.final_status = "REJECTED"
            row.note = "missing_fields:" + ",".join(missing)
            rows.append(row)
            continue

        if payload.content_hash in seen_hashes:
            row.write_status = contracts.WRITE_DUPLICATE_COLLAPSED
            row.dedup_status = "in_run_duplicate"
            row.final_status = "DUPLICATE"
            rows.append(row)
            continue
        seen_hashes.add(payload.content_hash)

        # bridge db_writer 경유(= backend POST). 예외는 transport 실패.
        try:
            created = writer(create)
        except RuntimeError as exc:
            row.write_status = contracts.WRITE_FAILED_TRANSPORT
            row.final_status = "WRITE_FAILED"
            row.note = str(exc)[:160]
            rows.append(row)
            continue

        result = writer.results[-1]
        row.raw_event_id = result.raw_event_id
        row.enqueued_msg_id = result.enqueued_msg_id
        if not created:
            row.write_status = contracts.WRITE_DUPLICATE_COLLAPSED
            row.dedup_status = "backend_on_conflict_collapsed"
            row.policy_status = _policy_label(rec)
            # 중복이라도 downstream 은 이전에 처리됐을 수 있으므로 폴링은 생략
            row.final_status = "DUPLICATE_COLLAPSED"
            rows.append(row)
            continue

        row.write_status = contracts.WRITE_CREATED
        row.dedup_status = "new"
        row.policy_status = _policy_label(rec)

        # 폴링: raw_event status processed/failed + event_card_id
        _poll_downstream(poller, row, config)
        rows.append(row)

    plan = {
        "base_url": config.base_url,
        "writer": "BackendApiRawEventsWriter",
        "redis_stream": "stream:raw_events (backend XADD) → stream:to_agent",
        "worker_entrypoint": "workers.queue.consumer.run_forever",
        "langgraph_entrypoint": "agents.graphs.event_processing_graph.run",
        "event_cards_target": "POST /api/admin/upsert-event → event_cards PG",
        "policy_excluded_count": len(policy_excluded),
        "max_records_per_type": config.max_records_per_type,
        "record_types": sorted({r.record_type for r in rows}),
    }
    result = {
        "plan": plan,
        "writer_summary": writer.summary(),
        "rows": [r.to_dict() for r in rows],
        "counts": _summarize(rows),
        "generated_at": _iso_now(),
    }
    if config.output_dir:
        _save_ledger(config.output_dir, result)
    return result


def _policy_label(rec: dict) -> str:
    if contracts.is_corroboration_required({"confirmation_policy": rec.get("confirmation_policy")}):
        return "corroboration_required"
    return "standard"


def _poll_downstream(poller: _BackendPoller, row: ProofRow, config: P0RunConfig) -> None:
    if not row.raw_event_id:
        return
    deadline = time.monotonic() + config.poll_timeout_sec
    last_status = "enqueued"
    while time.monotonic() < deadline:
        rec = poller.get_raw_event(row.raw_event_id)
        if rec:
            last_status = rec.get("status", last_status)
            card_id = rec.get("event_card_id")
            if last_status == "processed" and card_id:
                row.worker_status = "processed"
                row.langgraph_status = "completed"
                row.event_card_id = card_id
                card = poller.get_event_card(card_id)
                row.card_status = (card or {}).get("status", "") if card else "card_fetch_failed"
                row.final_status = "E2E_OK"
                return
            if last_status == "failed":
                row.worker_status = "failed"
                row.langgraph_status = "failed"
                row.note = (rec.get("error_reason") or "")[:160]
                row.final_status = "E2E_FAILED"
                return
        time.sleep(config.poll_interval_sec)
    row.worker_status = last_status
    row.langgraph_status = "timeout"
    row.final_status = "E2E_TIMEOUT"


def _summarize(rows: list[ProofRow]) -> dict:
    counts: dict = {}
    for r in rows:
        counts[r.final_status] = counts.get(r.final_status, 0) + 1
    e2e_ok_types = sorted({r.record_type for r in rows if r.final_status == "E2E_OK"})
    return {
        "by_final_status": counts,
        "e2e_ok_record_types": e2e_ok_types,
        "e2e_ok_type_count": len(e2e_ok_types),
        "cards_created": sum(1 for r in rows if r.event_card_id),
    }


def _save_ledger(output_dir: Path, result: dict) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "p0_integration_proof_ledger.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

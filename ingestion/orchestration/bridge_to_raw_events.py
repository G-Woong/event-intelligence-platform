"""Phase F-10 raw_events bridge — EventQueue record → raw_events 호환 payload.

backend의 실제 스키마(``backend/app/models/raw_event.py`` RawEventORM /
``backend/app/schemas/raw_events.py`` RawEventCreate)를 그대로 따른다. 가정하지 않는다.

raw_events 필수 컬럼: source_type, source_name, url(NOT NULL), content_hash(NOT NULL,
유니크 dedup index). 따라서 외부 URL이 없는 record는 reject/hold한다(없는 url을 지어내지
않는다). content_hash는 canonical_url(없으면 source_url, 없으면 source_id|title|time) 기반
sha256으로 결정적 산출 — backend의 on_conflict_do_nothing(content_hash)와 맞물려 재실행이
collapse된다.

writer: DB writer(주입형)가 있으면 DB로 쓰고, 없으면 local durable mirror(jsonl, gitignored)로
같은 계약을 검증한다. mirror는 EventQueue dedup 이후 record만 받는다(중복 미적재).

본문 전문은 싣지 않는다(raw_text="" 기본; preview_only 정책). 신규 설치 0(stdlib).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ingestion.orchestration.time_normalizer import normalize_record_times

# record_type → raw_events.source_type (String(32))
_RECORD_TYPE_TO_SOURCE_TYPE = {
    "article_candidate": "article",
    "official_record": "official",
    "structured_signal": "signal",
    "search_result": "search",
    "community_signal": "community",
}

BRIDGE_STATUS_WRITTEN = "written"
BRIDGE_STATUS_DUPLICATE = "duplicate_skipped"
BRIDGE_STATUS_HELD = "held"
BRIDGE_STATUS_REJECTED = "rejected"


@dataclass(frozen=True)
class RawEventPayload:
    event_id: str
    record_type: str
    source_id: str
    title: Optional[str]
    description: Optional[str]
    source_url: Optional[str]
    canonical_url: Optional[str]
    published_at: Optional[str]
    observed_at: Optional[str]
    collected_at: str
    evidence_ref: str
    body_state: Optional[str]
    structured_payload: Optional[dict]
    confirmation_policy: str
    quality_status: str
    dedup_key: str
    cluster_id: Optional[str]
    content_hash: str
    published_precision: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_raw_event_create(self) -> dict:
        """실제 RawEventCreate(backend) 계약으로 매핑. 추가 필드는 raw_metadata로."""
        source_type = _RECORD_TYPE_TO_SOURCE_TYPE.get(self.record_type, "rss")
        return {
            "source_type": source_type,
            "source_name": self.source_id,
            "external_id": self.dedup_key,
            "url": self.source_url,                 # NOT NULL — 매핑 단계에서 보장됨
            "title": self.title,
            "raw_text": "",                          # 전문 미포함(preview_only)
            "published_at": self.published_at,
            "content_hash": self.content_hash,
            "theme_hint": None,
            "raw_metadata": {
                "record_type": self.record_type,
                "canonical_url": self.canonical_url,
                "observed_at": self.observed_at,
                "published_precision": self.published_precision,
                "body_state": self.body_state,
                "structured_payload": self.structured_payload,
                "confirmation_policy": self.confirmation_policy,
                "quality_status": self.quality_status,
                "dedup_key": self.dedup_key,
                "cluster_id": self.cluster_id,
                "evidence_ref": self.evidence_ref,
                "collected_at": self.collected_at,
                "bridge": "phase_f",
            },
        }


def _external_url(record: dict) -> Optional[str]:
    val = record.get("source_url_or_evidence")
    if isinstance(val, str) and val.startswith(("http://", "https://")):
        return val
    return None


def _content_hash(*, canonical: Optional[str], url: Optional[str],
                  source_id: str, title: str, published: str) -> str:
    basis = canonical or url or f"{source_id}|{title}|{published}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()  # 64 chars == String(64)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def map_eq_record_to_raw_event(
    record: dict,
    *,
    dedup_key: Optional[str] = None,
    cluster_id: Optional[str] = None,
    collected_at: Optional[str] = None,
) -> tuple[Optional[RawEventPayload], str, Optional[str]]:
    """EventQueue record → (RawEventPayload | None, status, reason).

    status: 'ok' | 'held' | 'rejected'. 외부 url 없으면 held(missing_url). record_type 유효하지
    않으면 rejected. published_at은 precision을 잃지 않게 normalize.
    """
    rt = record.get("record_type")
    if rt not in _RECORD_TYPE_TO_SOURCE_TYPE:
        return None, BRIDGE_STATUS_REJECTED, f"invalid_record_type:{rt}"
    source_id = record.get("source_id") or ""
    if not source_id:
        return None, BRIDGE_STATUS_REJECTED, "no_source_id"

    url = _external_url(record)
    canonical = record.get("canonical_url") if isinstance(record.get("canonical_url"), str) else None
    if not url and not canonical:
        # raw_events.url NOT NULL — 외부 식별 URL이 전혀 없으면 적재 불가 → hold(정직)
        return None, BRIDGE_STATUS_HELD, "missing_external_url"
    effective_url = url or canonical

    title = record.get("title_or_label")
    times = normalize_record_times(
        published_at=record.get("published_at_or_observed_at"),
        observed_at=record.get("published_at_or_observed_at") if rt == "structured_signal" else None,
        collected_at=collected_at,
        record_type=rt,
    )
    primary = times["primary"]
    published_iso = primary.value
    observed_iso = times["observed"].value if times["observed"] else None

    dkey = dedup_key or f"{source_id}:{(canonical or effective_url)}"
    chash = _content_hash(
        canonical=canonical, url=effective_url, source_id=source_id,
        title=title or "", published=published_iso or "",
    )
    event_id = hashlib.sha1(dkey.encode("utf-8")).hexdigest()[:24]

    structured = None
    if rt == "structured_signal":
        structured = {"signal_type": record.get("body_state_or_signal")}

    payload = RawEventPayload(
        event_id=event_id, record_type=rt, source_id=source_id,
        title=title, description=None, source_url=effective_url, canonical_url=canonical,
        published_at=published_iso, observed_at=observed_iso, collected_at=collected_at or _iso_now(),
        evidence_ref=record.get("source_url_or_evidence") or "", body_state=record.get("body_state_or_signal"),
        structured_payload=structured, confirmation_policy=record.get("confirmation_policy") or "standard",
        quality_status=record.get("quality_pre_gate_decision") or "unknown",
        dedup_key=dkey, cluster_id=cluster_id, content_hash=chash,
        published_precision=primary.precision,
    )
    return payload, "ok", None


class RawEventBridgeWriter:
    """DB writer 주입 시 DB로, 없으면 local mirror(jsonl)로 같은 계약을 검증.

    db_writer(payload_dict) -> bool 형태의 콜러블을 받는다(있으면). 콜러블은 적재 성공 시
    True. 예외는 격리되어 raw_events_failed로 집계된다(critical alert 트리거).
    """

    def __init__(
        self,
        *,
        mirror_path: str | Path | None = None,
        db_writer: Optional[Any] = None,
    ) -> None:
        self._mirror_path = Path(mirror_path) if mirror_path else None
        self._db_writer = db_writer
        self._seen_hashes: set[str] = set()
        self.written = 0
        self.duplicates = 0
        self.failed = 0
        self.target = "db" if db_writer is not None else "mirror"
        if self._mirror_path:
            self._mirror_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, payload: RawEventPayload) -> str:
        """payload 1건 적재. content_hash 중복은 skip(재실행 collapse). 반환: BRIDGE_STATUS_*."""
        if payload.content_hash in self._seen_hashes:
            self.duplicates += 1
            return BRIDGE_STATUS_DUPLICATE
        try:
            if self._db_writer is not None:
                ok = bool(self._db_writer(payload.to_raw_event_create()))
                if not ok:
                    # DB 레벨 dedup(on_conflict) → 중복으로 간주
                    self.duplicates += 1
                    self._seen_hashes.add(payload.content_hash)
                    return BRIDGE_STATUS_DUPLICATE
            elif self._mirror_path is not None:
                line = json.dumps(payload.to_raw_event_create(), ensure_ascii=False)
                with open(self._mirror_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            else:
                # 타깃 없음 — 계약 검증만(메모리)
                pass
        except Exception as exc:  # 적재 실패 격리 → critical 집계
            self.failed += 1
            return f"{BRIDGE_STATUS_REJECTED}:write_error:{type(exc).__name__}"
        self._seen_hashes.add(payload.content_hash)
        self.written += 1
        return BRIDGE_STATUS_WRITTEN

    def summary(self) -> dict:
        return {
            "target": self.target,
            "raw_events_written": self.written,
            "raw_events_skipped_duplicates": self.duplicates,
            "raw_events_failed": self.failed,
        }


def bridge_records(
    records,
    *,
    writer: RawEventBridgeWriter,
    dedup_keys: Optional[dict] = None,
    cluster_ids: Optional[dict] = None,
    collected_at: Optional[str] = None,
) -> dict:
    """dedup 통과 record 목록을 raw_events로 bridge. 결과 통계 반환.

    dedup_keys/cluster_ids: record 인덱스 → 키 매핑(선택). 매핑 없으면 record에서 산출.
    """
    dedup_keys = dedup_keys or {}
    cluster_ids = cluster_ids or {}
    written = duplicates = held = rejected = 0
    schema_failures = 0
    statuses: list[dict] = []
    for i, rec in enumerate(records):
        payload, mstatus, reason = map_eq_record_to_raw_event(
            rec, dedup_key=dedup_keys.get(i), cluster_id=cluster_ids.get(i),
            collected_at=collected_at,
        )
        if payload is None:
            if mstatus == BRIDGE_STATUS_HELD:
                held += 1
            else:
                rejected += 1
                schema_failures += 1
            statuses.append({"index": i, "status": mstatus, "reason": reason,
                             "source_id": rec.get("source_id")})
            continue
        wstatus = writer.write(payload)
        if wstatus == BRIDGE_STATUS_WRITTEN:
            written += 1
        elif wstatus == BRIDGE_STATUS_DUPLICATE:
            duplicates += 1
        else:
            rejected += 1
        statuses.append({"index": i, "status": wstatus, "source_id": payload.source_id,
                         "record_type": payload.record_type})
    return {
        "target": writer.target,
        "raw_events_written": written,
        "raw_events_skipped_duplicates": duplicates,
        "raw_events_held": held,
        "raw_events_rejected": rejected,
        "schema_failures": schema_failures,
        "raw_events_failed": writer.failed,
        "bridge_contract_pass": (schema_failures == 0 and writer.failed == 0),
        "statuses": statuses,
    }

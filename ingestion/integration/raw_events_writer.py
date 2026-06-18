"""P0 raw_events writer — bridge db_writer 주입점에 꽂는 실 적재기.

bridge_to_raw_events.RawEventBridgeWriter 는 db_writer(create_dict) -> bool 콜러블을 받는다.
여기 BackendApiRawEventsWriter 가 그 콜러블이다. backend POST /api/admin/raw-events 가
PG upsert(on_conflict content_hash) + Redis XADD(stream:raw_events) 를 모두 수행하므로,
이 writer 하나로 A→B 전 구간(PG·Redis·worker·LangGraph·event_cards)이 열린다.

db_writer 계약(bridge 와 정합):
  - 반환 True  : 신규 적재(raw_events row created, stream enqueued)
  - 반환 False : content_hash 중복(backend on_conflict → is_duplicate) → bridge 가 collapse 집계
  - 예외       : 적재 실패 → bridge 가 raw_events_failed 로 격리 집계(critical alert)

writer 는 호출별 RawEventWriteResult 를 proof ledger 로 보관한다(라이브 검증/모니터링용).
신규 설치 0(httpx 는 이미 backend/agents 의존성). secret 미출력(admin token 은 헤더로만).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import httpx

from ingestion.integration import downstream_contracts as contracts


@dataclass
class RawEventWriteResult:
    content_hash: str
    record_type: Optional[str]
    source_name: Optional[str]
    status: str                       # contracts.WRITE_*
    raw_event_id: Optional[str] = None
    enqueued_msg_id: Optional[str] = None
    is_duplicate: bool = False
    http_status: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "content_hash": self.content_hash[:12],
            "record_type": self.record_type,
            "source_name": self.source_name,
            "status": self.status,
            "raw_event_id": self.raw_event_id,
            "enqueued_msg_id": self.enqueued_msg_id,
            "is_duplicate": self.is_duplicate,
            "http_status": self.http_status,
            "error": self.error,
        }


class RawEventsWriter(Protocol):
    def __call__(self, create: dict) -> bool: ...


class BackendApiRawEventsWriter:
    """backend POST /api/admin/raw-events 경유 raw_events writer(db_writer 콜러블).

    transport 주입 가능(테스트에서 httpx.MockTransport 사용). admin token 이 있으면 X-Admin-Token
    헤더로만 전달(값 로깅 금지).
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8000",
        admin_token: Optional[str] = None,
        timeout: float = 10.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._endpoint = f"{self._base_url}/api/admin/raw-events"
        self._headers: dict[str, str] = {}
        if admin_token:
            self._headers["X-Admin-Token"] = admin_token
        self._timeout = timeout
        self._client = client  # 주입 없으면 호출마다 단발 client
        self.results: list[RawEventWriteResult] = []
        self.created = 0
        self.duplicates = 0
        self.failed = 0

    # bridge db_writer 인터페이스
    def __call__(self, create: dict) -> bool:
        result = self.write_raw_event(create)
        self.results.append(result)
        if result.status == contracts.WRITE_CREATED:
            self.created += 1
            return True
        if result.status == contracts.WRITE_DUPLICATE_COLLAPSED:
            self.duplicates += 1
            return False
        # transport/schema 실패는 예외로 전파 → bridge 가 failed 집계
        self.failed += 1
        raise RuntimeError(f"raw_events write failed: {result.status}: {result.error}")

    def write_raw_event(self, create: dict) -> RawEventWriteResult:
        record_type = (create.get("raw_metadata") or {}).get("record_type")
        content_hash = create.get("content_hash") or ""
        source_name = create.get("source_name")
        try:
            if self._client is not None:
                resp = self._client.post(self._endpoint, json=create, headers=self._headers, timeout=self._timeout)
            else:
                with httpx.Client(timeout=self._timeout) as c:
                    resp = c.post(self._endpoint, json=create, headers=self._headers)
        except httpx.HTTPError as exc:
            return RawEventWriteResult(
                content_hash=content_hash, record_type=record_type, source_name=source_name,
                status=contracts.WRITE_FAILED_TRANSPORT, error=type(exc).__name__,
            )
        if resp.status_code >= 500:
            return RawEventWriteResult(
                content_hash=content_hash, record_type=record_type, source_name=source_name,
                status=contracts.WRITE_FAILED_TRANSPORT, http_status=resp.status_code,
                error=f"server_error:{resp.status_code}",
            )
        if resp.status_code >= 400:
            return RawEventWriteResult(
                content_hash=content_hash, record_type=record_type, source_name=source_name,
                status=contracts.WRITE_FAILED_SCHEMA, http_status=resp.status_code,
                error=f"client_error:{resp.status_code}:{resp.text[:200]}",
            )
        body = resp.json()
        record = body.get("record") or {}
        is_dup = bool(body.get("is_duplicate"))
        return RawEventWriteResult(
            content_hash=content_hash, record_type=record_type, source_name=source_name,
            status=(contracts.WRITE_DUPLICATE_COLLAPSED if is_dup else contracts.WRITE_CREATED),
            raw_event_id=record.get("id"),
            enqueued_msg_id=body.get("enqueued_msg_id"),
            is_duplicate=is_dup,
            http_status=resp.status_code,
        )

    def summary(self) -> dict:
        return {
            "target": "backend_api",
            "endpoint": self._endpoint,
            "created": self.created,
            "duplicates": self.duplicates,
            "failed": self.failed,
        }


class MirrorRawEventsWriter:
    """fallback 전용 — jsonl mirror 적재. P0 complete 판정 단독 근거가 될 수 없다(설계 §5.1).

    bridge 가 db_writer=None 일 때 자체 mirror 를 쓰므로 보통 직접 쓰지 않는다. 명시적으로
    'mirror 만 사용했다'는 사실을 ledger 에 남기기 위한 얇은 래퍼.
    """

    def __init__(self, mirror_path) -> None:
        from pathlib import Path
        self._path = Path(mirror_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.created = 0

    def __call__(self, create: dict) -> bool:
        import json
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(create, ensure_ascii=False) + "\n")
        self.created += 1
        return True

    def summary(self) -> dict:
        return {"target": "mirror", "p0_complete_eligible": False, "created": self.created}

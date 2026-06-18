from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


class EventQueue:
    """Async event queue with Redis Stream primary and local JSONL fallback.

    Priority: Redis Stream (REDIS_URL set) → local JSONL file.
    The JSONL fallback is fully operational and used in development/test.
    """

    _FALLBACK_DIR = Path(__file__).parent.parent / "outputs" / "jsonl"
    _FALLBACK_FILE = "event_queue.jsonl"

    # Redis Stream + consumer group (A측 durable 큐의 Redis 백엔드).
    # P0 통합 핵심 경로의 stream publish 는 backend(stream:raw_events)가 담당하며, 이 스트림은
    # A측 EventQueue 자체의 durable 백엔드다(JSONL 동치). 둘은 별개 책임이다.
    _STREAM = "stream:ingestion_eventqueue"
    _GROUP = "group:ingestion"
    _CONSUMER = "ingestion-1"

    def __init__(
        self,
        redis_url: str | None = None,
        fallback_dir: Path | None = None,
        redis_client: Any | None = None,
    ) -> None:
        # None  → read from REDIS_URL env; "" → explicit JSONL-only mode
        self._redis_url = os.environ.get("REDIS_URL", "") if redis_url is None else redis_url
        self._fallback_dir: Path = fallback_dir or self._FALLBACK_DIR
        # 주입된 client 가 있으면 우선(테스트), 없으면 REDIS_URL 유무로 결정
        self._client = redis_client
        self._use_redis = redis_client is not None or bool(self._redis_url)
        self._group_ready = False

    # ── public interface ──────────────────────────────────────────────────

    def enqueue(self, item: dict[str, Any]) -> str:
        """Enqueue an item. Returns the assigned item ID."""
        if self._use_redis:
            return self._redis_enqueue(item)
        return self._jsonl_enqueue(item)

    def dequeue(self, count: int = 1) -> list[dict[str, Any]]:
        """Dequeue up to `count` items (FIFO). Marks them as pending."""
        if self._use_redis:
            return self._redis_dequeue(count)
        return self._jsonl_dequeue(count)

    def peek(self, count: int = 5) -> list[dict[str, Any]]:
        """Return up to `count` items without removing them."""
        if self._use_redis:
            return self._redis_peek(count)
        return self._jsonl_peek(count)

    def mark_done(self, item_id: str) -> None:
        """Acknowledge an item as processed."""
        if self._use_redis:
            self._redis_mark_done(item_id)
        else:
            self._jsonl_mark_done(item_id)

    # ── JSONL fallback implementation ─────────────────────────────────────

    @property
    def _queue_path(self) -> Path:
        self._fallback_dir.mkdir(parents=True, exist_ok=True)
        return self._fallback_dir / self._FALLBACK_FILE

    def _jsonl_enqueue(self, item: dict[str, Any]) -> str:
        item_id = str(uuid.uuid4())
        record = {"_id": item_id, "_status": "pending", **item}
        with self._queue_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return item_id

    def _jsonl_dequeue(self, count: int) -> list[dict[str, Any]]:
        if not self._queue_path.exists():
            return []
        lines = self._queue_path.read_text(encoding="utf-8").splitlines()
        result: list[dict[str, Any]] = []
        updated: list[str] = []
        for line in lines:
            if not line.strip():
                continue
            record: dict[str, Any] = json.loads(line)
            if record.get("_status") == "pending" and len(result) < count:
                record["_status"] = "processing"
                result.append(record)
            updated.append(json.dumps(record, ensure_ascii=False))
        self._queue_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
        return result

    def _jsonl_peek(self, count: int) -> list[dict[str, Any]]:
        if not self._queue_path.exists():
            return []
        result: list[dict[str, Any]] = []
        for line in self._queue_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record: dict[str, Any] = json.loads(line)
            if record.get("_status") == "pending":
                result.append(record)
                if len(result) >= count:
                    break
        return result

    def _jsonl_mark_done(self, item_id: str) -> None:
        if not self._queue_path.exists():
            return
        lines = self._queue_path.read_text(encoding="utf-8").splitlines()
        updated: list[str] = []
        for line in lines:
            if not line.strip():
                continue
            record: dict[str, Any] = json.loads(line)
            if record.get("_id") == item_id:
                record["_status"] = "done"
            updated.append(json.dumps(record, ensure_ascii=False))
        self._queue_path.write_text("\n".join(updated) + "\n", encoding="utf-8")

    # ── Redis Stream implementation ───────────────────────────────────────

    def _redis(self) -> Any:
        """lazy Redis client(decode_responses=True). 주입 client 우선."""
        if self._client is None:
            import redis as _redis  # 지연 import — JSONL 전용 경로에선 의존성 불필요
            self._client = _redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def _ensure_group(self) -> None:
        if self._group_ready:
            return
        r = self._redis()
        try:
            r.xgroup_create(self._STREAM, self._GROUP, id="0", mkstream=True)
        except Exception as exc:  # BUSYGROUP(이미 존재)는 정상
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True

    def _redis_enqueue(self, item: dict[str, Any]) -> str:
        """item 을 stream 에 XADD. payload 는 data(json) 한 필드로 직렬화. 반환: stream msg id."""
        r = self._redis()
        msg_id = r.xadd(self._STREAM, {"data": json.dumps(item, ensure_ascii=False)})
        return msg_id

    def _redis_dequeue(self, count: int) -> list[dict[str, Any]]:
        """consumer group 으로 신규 메시지 최대 count 건 읽기(PEL 에 pending 등록). FIFO."""
        self._ensure_group()
        r = self._redis()
        resp = r.xreadgroup(
            groupname=self._GROUP, consumername=self._CONSUMER,
            streams={self._STREAM: ">"}, count=count, block=0,
        )
        out: list[dict[str, Any]] = []
        for _stream, entries in resp or []:
            for msg_id, fields in entries:
                item = json.loads(fields.get("data", "{}"))
                out.append({"_id": msg_id, "_status": "processing", **item})
        return out

    def _redis_peek(self, count: int) -> list[dict[str, Any]]:
        """consume 없이 stream 앞쪽 count 건 조회(XRANGE)."""
        r = self._redis()
        try:
            entries = r.xrange(self._STREAM, count=count)
        except Exception:
            return []
        out: list[dict[str, Any]] = []
        for msg_id, fields in entries:
            item = json.loads(fields.get("data", "{}"))
            out.append({"_id": msg_id, "_status": "pending", **item})
        return out

    def _redis_mark_done(self, item_id: str) -> None:
        """처리 완료 ack(XACK) — PEL 에서 제거. DLQ/회수는 XPENDING 기반(Phase 2 운영)."""
        self._ensure_group()
        r = self._redis()
        r.xack(self._STREAM, self._GROUP, item_id)

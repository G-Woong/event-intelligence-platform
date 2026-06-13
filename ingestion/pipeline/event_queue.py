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

    def __init__(self, redis_url: str | None = None, fallback_dir: Path | None = None) -> None:
        # None  → read from REDIS_URL env; "" → explicit JSONL-only mode
        self._redis_url = os.environ.get("REDIS_URL", "") if redis_url is None else redis_url
        self._fallback_dir: Path = fallback_dir or self._FALLBACK_DIR
        self._use_redis = bool(self._redis_url)
        # Redis client wired in Round 2 when REDIS_URL is set.

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

    # ── Redis stubs (wired in Round 2) ────────────────────────────────────

    def _redis_enqueue(self, item: dict[str, Any]) -> str:
        raise NotImplementedError("Redis Stream wired in Round 2")

    def _redis_dequeue(self, count: int) -> list[dict[str, Any]]:
        raise NotImplementedError("Redis Stream wired in Round 2")

    def _redis_peek(self, count: int) -> list[dict[str, Any]]:
        raise NotImplementedError("Redis Stream wired in Round 2")

    def _redis_mark_done(self, item_id: str) -> None:
        raise NotImplementedError("Redis Stream wired in Round 2")

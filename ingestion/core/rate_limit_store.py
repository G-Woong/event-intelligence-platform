from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ingestion.core.rate_limit_store")

_POLICY_PATH = Path(__file__).parent.parent / "configs" / "rate_limit_policy.yaml"
_DEFAULT_LOCAL_FILE = (
    Path(__file__).parent.parent / "outputs" / "state" / "rate_limit_cache.json"
)

STORE_STATUS_READY = "READY"
STORE_STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"
STORE_STATUS_DEGRADED_FALLBACK = "DEGRADED_FALLBACK"


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


class RateLimitStore(ABC):
    """Pluggable backing store for call-age tracking and 429 cooldown persistence.

    Celery workers (plans/012) can swap in RedisRateLimitStore without touching
    rate_limit_policy public signatures.
    """

    @abstractmethod
    def age_seconds(self, key: str) -> Optional[float]:
        """Seconds since last record(key), or None if never recorded/expired."""

    @abstractmethod
    def record(self, key: str, ttl_seconds: int = 0) -> None:
        """Record a call at 'now' for key. ttl_seconds is advisory (redis SETEX)."""

    @abstractmethod
    def get_next_retry_at(self, key: str) -> Optional[str]:
        """ISO 8601 next-retry timestamp for key, or None."""

    @abstractmethod
    def set_next_retry_at(self, key: str, iso_ts: str, reason: str = "") -> None:
        """Persist a cooldown deadline (ISO 8601) for key."""

    @abstractmethod
    def status(self) -> str:
        """READY | NOT_CONFIGURED | DEGRADED_FALLBACK"""


class InMemoryRateLimitStore(RateLimitStore):
    """Backed by an externally-owned dict (the module-level _call_cache).

    The dict object is NEVER reassigned — existing tests hold a reference to it
    and monkeypatch time.monotonic, so monotonic is evaluated at call time.
    """

    def __init__(self, backing: dict) -> None:
        self._backing = backing
        self._next_retry: dict[str, str] = {}
        self._next_retry_reason: dict[str, str] = {}

    def age_seconds(self, key: str) -> Optional[float]:
        last = self._backing.get(key)
        if last is None:
            return None
        return time.monotonic() - last

    def record(self, key: str, ttl_seconds: int = 0) -> None:
        self._backing[key] = time.monotonic()

    def get_next_retry_at(self, key: str) -> Optional[str]:
        return self._next_retry.get(key)

    def set_next_retry_at(self, key: str, iso_ts: str, reason: str = "") -> None:
        self._next_retry[key] = iso_ts
        if reason:
            self._next_retry_reason[key] = reason

    def status(self) -> str:
        return STORE_STATUS_READY


class LocalPersistentRateLimitStore(RateLimitStore):
    """JSON file store surviving process restarts.

    Wall-clock (time.time epoch + ISO 8601) only — monotonic values are
    meaningless across processes and are never written to disk.
    Atomic writes via tempfile + os.replace (PermissionError retried once
    for Windows file locking).
    """

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self._path = Path(file_path) if file_path else _DEFAULT_LOCAL_FILE
        self._state: dict = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {"calls": {}, "next_retry": {}}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("state root must be a dict")
            raw.setdefault("calls", {})
            raw.setdefault("next_retry", {})
            return raw
        except Exception as exc:
            logger.warning("rate_limit_cache.json unreadable (%s) — starting empty", exc)
            return {"calls": {}, "next_retry": {}}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(self._path.parent), suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=1)
            try:
                os.replace(tmp_name, self._path)
            except PermissionError:
                time.sleep(0.1)
                os.replace(tmp_name, self._path)
        except Exception as exc:
            logger.warning("rate_limit_cache.json save failed: %s", exc)

    def age_seconds(self, key: str) -> Optional[float]:
        entry = self._state["calls"].get(key)
        if entry is None:
            return None
        epoch = entry.get("epoch")
        if not isinstance(epoch, (int, float)):
            return None
        age = time.time() - epoch
        if age < 0:
            # Clock skew: recorded timestamp is in the future — treat as expired
            return None
        return age

    def record(self, key: str, ttl_seconds: int = 0) -> None:
        self._state["calls"][key] = {
            "epoch": time.time(),
            "recorded_at": _utc_now_iso(),
            "ttl_seconds": ttl_seconds,
        }
        self._save()

    def get_next_retry_at(self, key: str) -> Optional[str]:
        entry = self._state["next_retry"].get(key)
        return entry.get("at") if isinstance(entry, dict) else None

    def set_next_retry_at(self, key: str, iso_ts: str, reason: str = "") -> None:
        self._state["next_retry"][key] = {"at": iso_ts, "reason": reason}
        self._save()

    def status(self) -> str:
        return STORE_STATUS_READY


class RedisRateLimitStore(RateLimitStore):
    """Redis-backed store. Key pattern: rate_limit:{source_id}:{query_hash}
    (plans/012 §3 contract).

    redis is lazily imported; a client can be injected for tests. If redis is
    unavailable or the connection fails, status() is NOT_CONFIGURED and every
    operation is a safe no-op.
    """

    def __init__(self, client=None, url: Optional[str] = None) -> None:
        self._client = client
        self._status = STORE_STATUS_NOT_CONFIGURED
        if client is not None:
            self._status = STORE_STATUS_READY
            return
        if not url:
            url = os.environ.get("REDIS_URL", "")
        if not url:
            return
        try:
            import redis  # lazy import

            self._client = redis.Redis.from_url(url, socket_connect_timeout=2)
            self._client.ping()
            self._status = STORE_STATUS_READY
        except Exception as exc:
            logger.warning("Redis unavailable (%s) — store NOT_CONFIGURED", type(exc).__name__)
            self._client = None
            self._status = STORE_STATUS_NOT_CONFIGURED

    @staticmethod
    def _redis_key(key: str) -> str:
        return f"rate_limit:{key}"

    def age_seconds(self, key: str) -> Optional[float]:
        if self._client is None:
            return None
        try:
            raw = self._client.get(self._redis_key(key))
            if raw is None:
                return None
            epoch = float(raw)
            age = time.time() - epoch
            return None if age < 0 else age
        except Exception:
            return None

    def record(self, key: str, ttl_seconds: int = 0) -> None:
        if self._client is None:
            return
        try:
            rk = self._redis_key(key)
            if ttl_seconds > 0:
                self._client.setex(rk, ttl_seconds, str(time.time()))
            else:
                self._client.set(rk, str(time.time()))
        except Exception:
            pass

    def get_next_retry_at(self, key: str) -> Optional[str]:
        if self._client is None:
            return None
        try:
            raw = self._client.get(self._redis_key(f"next_retry:{key}"))
            if raw is None:
                return None
            return raw.decode() if isinstance(raw, bytes) else str(raw)
        except Exception:
            return None

    def set_next_retry_at(self, key: str, iso_ts: str, reason: str = "") -> None:
        if self._client is None:
            return
        try:
            self._client.set(self._redis_key(f"next_retry:{key}"), iso_ts)
        except Exception:
            pass

    def status(self) -> str:
        return self._status


# ── backend selection / singleton ──────────────────────────────────────────

_store_singleton: Optional[RateLimitStore] = None


def _load_backend_config() -> dict:
    try:
        import yaml

        with open(_POLICY_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        cfg = raw.get("rate_limit_backend", {})
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _build_store(backend: str, cfg: dict) -> RateLimitStore:
    from ingestion.core.rate_limit_policy import _call_cache

    if backend == "redis":
        url_env = cfg.get("redis_url_env", "REDIS_URL")
        store: RateLimitStore = RedisRateLimitStore(url=os.environ.get(url_env, ""))
        if store.status() == STORE_STATUS_READY:
            return store
        logger.warning("redis backend unavailable — falling back to local_file")
        backend = "local_file"

    if backend == "local_file":
        path = cfg.get("local_file_path") or None
        try:
            return LocalPersistentRateLimitStore(Path(path) if path else None)
        except Exception as exc:
            logger.warning("local_file backend failed (%s) — falling back to memory", exc)

    return InMemoryRateLimitStore(_call_cache)


def get_store() -> RateLimitStore:
    """Singleton store. Backend priority: env INGESTION_RATE_LIMIT_BACKEND >
    yaml rate_limit_backend.backend > 'memory' (default, no behaviour change)."""
    global _store_singleton
    if _store_singleton is not None:
        return _store_singleton
    cfg = _load_backend_config()
    backend = os.environ.get("INGESTION_RATE_LIMIT_BACKEND", "") or cfg.get("backend", "memory")
    _store_singleton = _build_store(backend, cfg)
    return _store_singleton


def reset_store_for_tests() -> None:
    global _store_singleton
    _store_singleton = None

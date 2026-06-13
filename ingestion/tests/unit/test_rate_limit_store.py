from __future__ import annotations

import inspect
import json
import time
from pathlib import Path

import pytest

from ingestion.core.rate_limit_store import (
    STORE_STATUS_NOT_CONFIGURED,
    STORE_STATUS_READY,
    InMemoryRateLimitStore,
    LocalPersistentRateLimitStore,
    RedisRateLimitStore,
    get_store,
    reset_store_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_store_for_tests()
    yield
    reset_store_for_tests()


# ── InMemoryRateLimitStore ────────────────────────────────────────────────

def test_in_memory_uses_backing_dict_object():
    backing: dict = {}
    store = InMemoryRateLimitStore(backing)
    store.record("a:q")
    assert "a:q" in backing
    # Externally written entries are visible (legacy test compatibility)
    backing["b:q"] = time.monotonic()
    assert store.age_seconds("b:q") is not None


def test_in_memory_next_retry_roundtrip():
    store = InMemoryRateLimitStore({})
    assert store.get_next_retry_at("x") is None
    store.set_next_retry_at("x", "2099-01-01T00:00:00Z", reason="429")
    assert store.get_next_retry_at("x") == "2099-01-01T00:00:00Z"
    assert store.status() == STORE_STATUS_READY


# ── LocalPersistentRateLimitStore ─────────────────────────────────────────

def test_local_store_restart_roundtrip(tmp_path: Path):
    """재기동(새 인스턴스) 후에도 호출 기록과 next_retry_at이 살아있다."""
    path = tmp_path / "state" / "rate_limit_cache.json"
    s1 = LocalPersistentRateLimitStore(path)
    s1.record("gdelt:q1", ttl_seconds=900)
    s1.set_next_retry_at("gdelt:q1", "2099-06-12T00:00:00Z", reason="429")

    s2 = LocalPersistentRateLimitStore(path)  # simulated restart
    age = s2.age_seconds("gdelt:q1")
    assert age is not None and age >= 0
    assert s2.get_next_retry_at("gdelt:q1") == "2099-06-12T00:00:00Z"


def test_local_store_corrupted_json_starts_empty(tmp_path: Path):
    path = tmp_path / "rate_limit_cache.json"
    path.write_text("{not valid json!!!", encoding="utf-8")
    store = LocalPersistentRateLimitStore(path)
    assert store.age_seconds("any") is None
    assert store.status() == STORE_STATUS_READY
    # New writes still work after corruption recovery
    store.record("a:")
    assert store.age_seconds("a:") is not None


def test_local_store_clock_skew_future_timestamp_expired(tmp_path: Path):
    """시계 역행(미래 epoch) → 만료 처리 (None 반환)."""
    path = tmp_path / "rate_limit_cache.json"
    path.write_text(
        json.dumps({
            "calls": {"a:": {"epoch": time.time() + 99999, "recorded_at": "x", "ttl_seconds": 0}},
            "next_retry": {},
        }),
        encoding="utf-8",
    )
    store = LocalPersistentRateLimitStore(path)
    assert store.age_seconds("a:") is None


def test_local_store_never_writes_monotonic(tmp_path: Path):
    """디스크에는 wall-clock(epoch/ISO)만 저장 — monotonic 값 미저장."""
    path = tmp_path / "rate_limit_cache.json"
    store = LocalPersistentRateLimitStore(path)
    store.record("a:q")
    raw = json.loads(path.read_text(encoding="utf-8"))
    entry = raw["calls"]["a:q"]
    # epoch must be wall-clock scale (>2020-01-01), not monotonic (small uptime numbers)
    assert entry["epoch"] > 1577836800
    assert "recorded_at" in entry


# ── RedisRateLimitStore ───────────────────────────────────────────────────

class _FakeRedisClient:
    """dict 기반 fake redis client (fakeredis 미설치 — 의존성 추가 금지)."""

    def __init__(self):
        self.data: dict[str, str] = {}
        self.setex_calls: list[tuple[str, int]] = []

    def get(self, k):
        v = self.data.get(k)
        return v.encode() if isinstance(v, str) else v

    def set(self, k, v):
        self.data[k] = str(v)

    def setex(self, k, ttl, v):
        self.data[k] = str(v)
        self.setex_calls.append((k, ttl))

    def exists(self, k):
        return 1 if k in self.data else 0

    def ping(self):
        return True


def test_redis_store_with_injected_client_setex_and_key_pattern():
    client = _FakeRedisClient()
    store = RedisRateLimitStore(client=client)
    assert store.status() == STORE_STATUS_READY
    store.record("gdelt:qhash", ttl_seconds=900)
    # plans/012 §3 계약: rate_limit:{source_id}:{query_hash}
    assert client.exists("rate_limit:gdelt:qhash") == 1
    assert client.setex_calls == [("rate_limit:gdelt:qhash", 900)]
    age = store.age_seconds("gdelt:qhash")
    assert age is not None and age >= 0


def test_redis_store_next_retry_roundtrip():
    store = RedisRateLimitStore(client=_FakeRedisClient())
    store.set_next_retry_at("g:q", "2099-01-01T00:00:00Z")
    assert store.get_next_retry_at("g:q") == "2099-01-01T00:00:00Z"


def test_redis_store_unreachable_is_not_configured_and_noop():
    store = RedisRateLimitStore(url="redis://127.0.0.1:1/0")  # nothing listening
    assert store.status() == STORE_STATUS_NOT_CONFIGURED
    # All ops are safe no-ops
    store.record("a:")
    store.set_next_retry_at("a:", "2099-01-01T00:00:00Z")
    assert store.age_seconds("a:") is None
    assert store.get_next_retry_at("a:") is None


# ── backend selection ─────────────────────────────────────────────────────

def test_default_backend_is_memory_backed_by_call_cache():
    from ingestion.core.rate_limit_policy import _call_cache
    store = get_store()
    assert isinstance(store, InMemoryRateLimitStore)
    assert store._backing is _call_cache  # 그 객체 — 재할당 금지 가드


def test_env_override_selects_local_file(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("INGESTION_RATE_LIMIT_BACKEND", "local_file")
    reset_store_for_tests()
    store = get_store()
    assert isinstance(store, LocalPersistentRateLimitStore)


def test_redis_backend_falls_back_when_unavailable(monkeypatch):
    monkeypatch.setenv("INGESTION_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    reset_store_for_tests()
    store = get_store()
    # redis 불가 → local_file fallback (예외 없이)
    assert isinstance(store, LocalPersistentRateLimitStore)


def test_get_store_is_singleton():
    assert get_store() is get_store()


# ── 시그니처 가드 (record_call/is_cached/cache_key 불변) ──────────────────

def test_public_signatures_unchanged():
    from ingestion.core import rate_limit_policy as rlp
    assert list(inspect.signature(rlp.cache_key).parameters) == ["source_id", "query"]
    assert list(inspect.signature(rlp.is_cached).parameters) == ["source_id", "query"]
    assert list(inspect.signature(rlp.record_call).parameters) == ["source_id", "query"]


def test_record_rate_limited_and_in_cooldown_roundtrip():
    from ingestion.core.rate_limit_policy import in_cooldown, record_rate_limited
    iso = record_rate_limited("test_src_rl", query="q", cooldown_seconds=3600)
    assert iso.endswith("Z")
    cooling, next_at = in_cooldown("test_src_rl", query="q")
    assert cooling is True
    assert next_at == iso
    # 다른 query는 cooldown 아님
    assert in_cooldown("test_src_rl", query="other") == (False, None)


def test_expired_cooldown_returns_false():
    from ingestion.core.rate_limit_policy import in_cooldown, record_rate_limited
    record_rate_limited("test_src_rl2", cooldown_seconds=-10)  # 과거 deadline
    assert in_cooldown("test_src_rl2") == (False, None)

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_POLICY_PATH = Path(__file__).parent.parent / "configs" / "rate_limit_policy.yaml"

# In-process ephemeral TTL cache: {(source_id, query_hash): last_call_monotonic}
# Volatile — cleared on process restart. Not shared across workers.
_call_cache: dict[str, float] = {}


@dataclass
class RateLimitPolicy:
    min_interval_seconds: float = 0
    max_calls_per_run: int = 1
    cooldown_on_429_seconds: int = 60
    max_retries_on_429: int = 1
    cache_ttl_seconds: int = 0


def load_rate_limit_policy(source_id: str) -> RateLimitPolicy:
    """Load rate limit policy for source_id by merging default + per_source overrides."""
    try:
        import yaml
        with open(_POLICY_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception:
        return RateLimitPolicy()

    default_cfg: dict = raw.get("default", {})
    per_source_cfg: dict = raw.get("per_source", {}).get(source_id, {})

    merged = {**default_cfg, **per_source_cfg}
    return RateLimitPolicy(
        min_interval_seconds=float(merged.get("min_interval_seconds", 0)),
        max_calls_per_run=int(merged.get("max_calls_per_run", 1)),
        cooldown_on_429_seconds=int(merged.get("cooldown_on_429_seconds", 60)),
        max_retries_on_429=int(merged.get("max_retries_on_429", 1)),
        cache_ttl_seconds=int(merged.get("cache_ttl_seconds", 0)),
    )


def cache_key(source_id: str, query: str = "") -> str:
    return f"{source_id}:{query}"


def is_cached(source_id: str, query: str = "") -> bool:
    """Return True if source+query was called within cache_ttl_seconds."""
    from ingestion.core.rate_limit_store import get_store
    policy = load_rate_limit_policy(source_id)
    if policy.cache_ttl_seconds <= 0:
        return False
    age = get_store().age_seconds(cache_key(source_id, query))
    if age is None:
        return False
    return age < policy.cache_ttl_seconds


def record_call(source_id: str, query: str = "") -> None:
    """Record a call timestamp via the configured RateLimitStore."""
    from ingestion.core.rate_limit_store import get_store
    policy = load_rate_limit_policy(source_id)
    get_store().record(cache_key(source_id, query), ttl_seconds=policy.cache_ttl_seconds)


def record_rate_limited(
    source_id: str,
    query: str = "",
    cooldown_seconds: Optional[int] = None,
) -> str:
    """Persist a 429 cooldown deadline. Returns the ISO 8601 next-retry timestamp."""
    from datetime import datetime, timedelta, timezone
    from ingestion.core.rate_limit_store import get_store

    if cooldown_seconds is None:
        cooldown_seconds = load_rate_limit_policy(source_id).cooldown_on_429_seconds
    next_dt = datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)
    iso_ts = next_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    get_store().set_next_retry_at(
        cache_key(source_id, query), iso_ts, reason="429_rate_limited"
    )
    return iso_ts


def in_cooldown(source_id: str, query: str = "") -> tuple[bool, Optional[str]]:
    """(True, next_retry_at) if a persisted 429 cooldown deadline is still in the future."""
    from datetime import datetime, timezone
    from ingestion.core.rate_limit_store import get_store

    iso_ts = get_store().get_next_retry_at(cache_key(source_id, query))
    if not iso_ts:
        return False, None
    try:
        deadline = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return False, None
    if deadline > datetime.now(timezone.utc):
        return True, iso_ts
    return False, None

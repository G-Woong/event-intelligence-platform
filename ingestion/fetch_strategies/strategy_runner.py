from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from ingestion.core.error_taxonomy import BLOCKED_ERRORS, ErrorType
from ingestion.core.rate_limit_policy import load_rate_limit_policy
from ingestion.core.retry_policy import STRATEGY_SEQUENCE, RetryPolicy, load_retry_policy
from ingestion.fetch_strategies.failure_classifier import classify_failure
from ingestion.fetch_strategies.models import FetchAttempt, StrategyLoopResult
from ingestion.fetch_strategies.strategy_selection import select_next_strategy

logger = logging.getLogger("ingestion.fetch_strategies.strategy_runner")

_POLICY_PATH = Path(__file__).parent.parent / "configs" / "retry_policy.yaml"


def _default_policy() -> RetryPolicy:
    if _POLICY_PATH.exists():
        return load_retry_policy(_POLICY_PATH)
    return RetryPolicy()


def run_fetch_strategy_loop(
    source_id: str,
    url: str,
    source_spec: Optional[dict] = None,
    strategy_budget: Optional[int] = None,
    query: str = "",
) -> StrategyLoopResult:
    """Iterate STRATEGY_SEQUENCE with backoff until success, blocked, or budget exhausted.

    Dispatch delegates to agents.graph._fetch_with_strategy for actual HTTP/Playwright calls.
    Each attempt is recorded as a FetchAttempt. BLOCKED_ERRORS stop the loop immediately.
    """
    from ingestion.agents.graph import _fetch_with_strategy
    from ingestion.core.artifact_store import new_run_id, url_hash

    if source_spec is None:
        source_spec = {}

    policy = _default_policy()
    if strategy_budget is not None:
        policy.max_strategies_per_url = strategy_budget
    else:
        policy.max_strategies_per_url = policy.budget_for(source_id)

    run_id = new_run_id(0, source_id)
    uh = url_hash(url)

    from ingestion.core.rate_limit_policy import (
        in_cooldown,
        is_cached,
        record_call,
        record_rate_limited,
    )

    rl_policy = load_rate_limit_policy(source_id)

    if is_cached(source_id, query):
        logger.info("Cache hit for %s query=%r — skipping live fetch", source_id, query)
        return StrategyLoopResult(source_id=source_id, url=url, status="cached")

    cooling, next_retry_at = in_cooldown(source_id, query)
    if cooling:
        logger.info(
            "Persisted 429 cooldown active for %s until %s — skipping live fetch",
            source_id, next_retry_at,
        )
        return StrategyLoopResult(source_id=source_id, url=url, status="rate_limited")

    _429_retries: int = 0

    attempts: list[FetchAttempt] = []
    current_strategy: Optional[str] = STRATEGY_SEQUENCE[0]
    final_html: Optional[str] = None

    while current_strategy is not None:
        if len(attempts) >= policy.max_strategies_per_url:
            break

        delay = policy.delay_for_attempt(len(attempts)) if attempts else 0.0
        if delay > 0:
            time.sleep(delay)

        t0 = time.monotonic()
        try:
            html, _ss, _dom = _fetch_with_strategy(url, current_strategy, run_id, source_id, uh)
            elapsed = time.monotonic() - t0
        except Exception as exc:
            elapsed = time.monotonic() - t0
            error_type = classify_failure(exc)
            attempts.append(FetchAttempt(
                strategy=current_strategy,
                success=False,
                error_type=error_type,
                delay_sec=delay,
                elapsed_sec=elapsed,
            ))
            if error_type in BLOCKED_ERRORS:
                return StrategyLoopResult(
                    source_id=source_id, url=url, status="blocked",
                    attempts=attempts, final_error_type=error_type,
                )
            if error_type == ErrorType.RATE_LIMITED:
                if _429_retries < rl_policy.max_retries_on_429:
                    _429_retries += 1
                    cooldown = min(rl_policy.cooldown_on_429_seconds, 300)
                    logger.info("RATE_LIMITED on %s — sleeping %ds then retrying same strategy", source_id, cooldown)
                    time.sleep(cooldown)
                    # do not advance strategy; loop continues with same current_strategy
                    continue
                record_rate_limited(source_id, query)
                return StrategyLoopResult(
                    source_id=source_id, url=url, status="rate_limited",
                    attempts=attempts, final_error_type=error_type,
                )
            _429_retries = 0
            current_strategy = select_next_strategy(source_spec, attempts, error_type, policy)
            continue

        if html:
            attempts.append(FetchAttempt(
                strategy=current_strategy,
                success=True,
                delay_sec=delay,
                elapsed_sec=elapsed,
            ))
            final_html = html
            record_call(source_id, query)
            return StrategyLoopResult(
                source_id=source_id, url=url, status="success",
                attempts=attempts, final_html=final_html,
            )

        # Empty response — treat as extraction failure, try next strategy
        attempts.append(FetchAttempt(
            strategy=current_strategy,
            success=False,
            error_type=ErrorType.EXTRACTION_EMPTY,
            delay_sec=delay,
            elapsed_sec=elapsed,
        ))
        current_strategy = select_next_strategy(
            source_spec, attempts, ErrorType.EXTRACTION_EMPTY, policy
        )

    final_error = attempts[-1].error_type if attempts else None
    return StrategyLoopResult(
        source_id=source_id, url=url, status="exhausted",
        attempts=attempts, final_error_type=final_error,
    )

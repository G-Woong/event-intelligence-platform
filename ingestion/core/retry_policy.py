from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

STRATEGY_SEQUENCE: list[str] = [
    "httpx_direct",
    "httpx_mobile_ua",
    "httpx_random_ua",
    "readability",
    "trafilatura",
    "dom_heuristic",
    "playwright_basic",
    "playwright_scroll",
    "playwright_wait_network_idle",
    "playwright_click_more",
]


@dataclass
class RetryPolicy:
    max_attempts: int = 5
    max_strategies_per_url: int = 3
    initial_delay_sec: float = 2.0
    max_delay_sec: float = 30.0
    exponential_base: float = 2.0
    retry_on: frozenset[str] = None  # type: ignore[assignment]
    per_source_budget: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.retry_on is None:
            self.retry_on = frozenset({
                "NETWORK_TIMEOUT",
                "NETWORK_CONNECTION_RESET",
                "HTTP_5XX",
                "JS_RENDER_FAIL",
                "LLM_TIMEOUT",
                "LLM_RATE_LIMIT",
            })
        if self.per_source_budget is None:
            self.per_source_budget = {}

    def budget_for(self, source_id: str) -> int:
        """Per-source strategy budget; falls back to global max_strategies_per_url."""
        return self.per_source_budget.get(source_id, self.max_strategies_per_url)

    def next_strategy(self, current: str) -> Optional[str]:
        try:
            idx = STRATEGY_SEQUENCE.index(current)
        except ValueError:
            return STRATEGY_SEQUENCE[0]
        next_idx = idx + 1
        if next_idx < len(STRATEGY_SEQUENCE):
            return STRATEGY_SEQUENCE[next_idx]
        return None

    def delay_for_attempt(self, attempt_no: int) -> float:
        delay = self.initial_delay_sec * (self.exponential_base ** max(0, attempt_no - 1))
        return min(delay, self.max_delay_sec)

    def should_retry(self, error_type: str) -> bool:
        return error_type in self.retry_on


def load_retry_policy(config_path: Path) -> RetryPolicy:
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    backoff = data.get("backoff", {})
    per_source_raw = data.get("per_source") or {}
    per_source_budget = {
        sid: cfg["max_strategies_per_url"]
        for sid, cfg in per_source_raw.items()
        if isinstance(cfg, dict) and "max_strategies_per_url" in cfg
    }
    return RetryPolicy(
        max_attempts=data.get("max_attempts", 5),
        max_strategies_per_url=data.get("max_strategies_per_url", 3),
        initial_delay_sec=backoff.get("initial_delay_sec", 2.0),
        max_delay_sec=backoff.get("max_delay_sec", 30.0),
        exponential_base=backoff.get("exponential_base", 2.0),
        retry_on=frozenset(data.get("retry_on", [])),
        per_source_budget=per_source_budget,
    )

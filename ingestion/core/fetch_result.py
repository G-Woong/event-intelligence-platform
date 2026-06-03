from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FetchResult:
    url: str
    strategy: str
    success: bool
    status_code: int = 0
    html: str = ""
    headers: dict = None  # type: ignore[assignment]
    elapsed_sec: float = 0.0
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {}

    @property
    def content_length(self) -> int:
        return len(self.html.encode("utf-8")) if self.html else 0

    @classmethod
    def failure(
        cls,
        url: str,
        strategy: str,
        error_message: str,
        status_code: int = 0,
    ) -> "FetchResult":
        return cls(
            url=url,
            strategy=strategy,
            success=False,
            status_code=status_code,
            html="",
            error_message=error_message,
        )

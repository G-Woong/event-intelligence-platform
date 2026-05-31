from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractionResult:
    url: str
    strategy: str
    success: bool
    title: Optional[str] = None
    body: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[str] = None
    language: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    error_message: Optional[str] = None

    @property
    def body_length(self) -> int:
        return len(self.body) if self.body else 0

    @classmethod
    def failure(
        cls,
        url: str,
        strategy: str,
        error_message: str,
    ) -> "ExtractionResult":
        return cls(
            url=url,
            strategy=strategy,
            success=False,
            error_message=error_message,
        )

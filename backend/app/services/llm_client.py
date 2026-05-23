from __future__ import annotations

import os
from typing import Literal


class LLMClient:
    def __init__(self, provider: Literal["mock", "openai"] = "mock") -> None:
        self.provider = provider
        if provider == "openai":
            key = os.getenv("OPENAI_API_KEY", "")
            if not key:
                raise ValueError("OPENAI_API_KEY not set (len=0)")

    def complete(self, prompt: str, **kwargs) -> str:
        if self.provider == "mock":
            return f"[mock] response for prompt length={len(prompt)}"
        raise NotImplementedError("openai provider not activated in STEP 003")

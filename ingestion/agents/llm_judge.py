from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional, Type

from pydantic import BaseModel

logger = logging.getLogger("ingestion.llm_judge")


class BaseJudgeClient(ABC):
    @abstractmethod
    def complete(self, prompt: str, *, max_tokens: int = 512, temperature: float = 0.1) -> str: ...

    def complete_json(self, prompt: str, *, schema: Type[BaseModel], **kwargs) -> Optional[BaseModel]:
        try:
            raw = self.complete(prompt, **kwargs)
            data = json.loads(raw)
            return schema.model_validate(data)
        except Exception as exc:
            logger.warning("complete_json parse error: %s", exc)
            return None


class MockJudgeClient(BaseJudgeClient):
    def complete(self, prompt: str, *, max_tokens: int = 512, temperature: float = 0.1) -> str:
        return f'[mock] response for prompt_len={len(prompt)}'

    def complete_json(self, prompt: str, *, schema: Type[BaseModel], **kwargs) -> Optional[BaseModel]:
        name = schema.__name__
        try:
            if name == "EventCandidate":
                return schema.model_validate({
                    "source_id": "mock",
                    "url": "https://example.com",
                    "title": "[mock] Event Title",
                    "summary": "[mock] A significant event occurred.",
                    "event_type": "news",
                    "entities": ["Entity A"],
                    "regions": ["Global"],
                    "sectors": ["general"],
                    "significance": 0.6,
                    "confidence": 0.7,
                    "published_at": None,
                    "extraction_strategy": "mock",
                    "llm_judged": True,
                })
            if name == "JudgeOutput":
                return schema.model_validate({
                    "is_valid": True,
                    "confidence": 0.75,
                    "reason": "[mock] looks like a valid article",
                })
        except Exception as exc:
            logger.warning("MockJudgeClient.complete_json error (schema=%s): %s", name, exc)
        return None


class OpenAIJudgeClient(BaseJudgeClient):
    def __init__(self, model: str = "gpt-4o-mini", timeout: float = 30.0) -> None:
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY is not set (len=0)")
        logger.debug("OpenAIJudgeClient initialized (key len=%d)", len(key))
        import openai
        self._client = openai.OpenAI(api_key=key)
        self._model = model
        self._timeout = timeout

    def complete(self, prompt: str, *, max_tokens: int = 512, temperature: float = 0.1) -> str:
        import openai
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_exponential(min=1, max=4),
            retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
            reraise=True,
        )
        def _call() -> str:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self._timeout,
            )
            return resp.choices[0].message.content or ""

        return _call()


def create_judge_client(provider: Optional[str] = None) -> BaseJudgeClient:
    _provider = provider or os.getenv("LLM_PROVIDER", "mock")
    if _provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            logger.warning(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is empty (len=0) — falling back to MockJudgeClient"
            )
            return MockJudgeClient()
        return OpenAIJudgeClient()
    return MockJudgeClient()

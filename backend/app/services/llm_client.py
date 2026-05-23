from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Literal, Optional, Type

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_client_cache: Optional["BaseLLMClient"] = None


class BaseLLMClient(ABC):
    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> str: ...

    def complete_json(
        self,
        prompt: str,
        *,
        schema: Type[BaseModel],
        **kwargs,
    ) -> Optional[BaseModel]:
        try:
            raw = self.complete(prompt, **kwargs)
            data = json.loads(raw)
            return schema.model_validate(data)
        except Exception:
            return None


class MockLLMClient(BaseLLMClient):
    def complete(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> str:
        p = prompt.lower()
        if "impact" in p:
            return "[mock] medium-term supply disruption risk"
        if "fact_check" in p or "fact check" in p:
            return '{"status":"pass","reasoning":"[mock] no contradictions"}'
        if "summary" in p or "summarize" in p or "headline" in p:
            return f"[mock] summary: {prompt[:40]}"
        return f"[mock] response for prompt length={len(prompt)}"

    def complete_json(
        self,
        prompt: str,
        *,
        schema: Type[BaseModel],
        **kwargs,
    ) -> Optional[BaseModel]:
        name = schema.__name__
        try:
            if name == "ImpactAnalysisOutput":
                return schema.model_validate({
                    "impact": "[mock] medium-term supply disruption risk",
                    "horizon": "medium",
                    "confidence": 0.75,
                })
            if name == "FactCheckOutput":
                return schema.model_validate({
                    "status": "pass",
                    "reasoning": "[mock] no contradictions",
                })
            if name == "SummaryOutput":
                return schema.model_validate({
                    "summary": "[mock summary] event details",
                    "headline": "[mock headline]",
                })
        except Exception:
            pass
        return None


class OpenAILLMClient(BaseLLMClient):
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        timeout: float = 30.0,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> None:
        import os
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY is not set (len=0)")
        logger.debug("OpenAILLMClient initialized (key len=%d)", len(key))
        import openai
        self._client = openai.OpenAI(api_key=key)
        self._default_model = model
        self._default_timeout = timeout
        self._default_max_tokens = max_tokens
        self._default_temperature = temperature

    def complete(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> str:
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
                model=model or self._default_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature if temperature is not None else self._default_temperature,
                max_tokens=max_tokens or self._default_max_tokens,
                timeout=timeout or self._default_timeout,
            )
            return resp.choices[0].message.content or ""

        return _call()


def create_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseLLMClient:
    from backend.app.core.config import settings
    _provider = provider or settings.LLM_PROVIDER
    _model = model or settings.LLM_MODEL
    if _provider == "openai":
        return OpenAILLMClient(
            model=_model,
            timeout=settings.LLM_TIMEOUT_SEC,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
        )
    return MockLLMClient()


def get_llm_client() -> BaseLLMClient:
    global _client_cache
    if _client_cache is None:
        _client_cache = create_llm_client()
    return _client_cache


def reset_llm_client_cache() -> None:
    global _client_cache
    _client_cache = None


class LLMClient:
    """Legacy alias for backward compatibility (ai_replies.py)."""

    def __init__(self, provider: Literal["mock", "openai"] = "mock") -> None:
        self._inner = create_llm_client(provider=provider)

    def complete(self, prompt: str, **kwargs) -> str:
        return self._inner.complete(prompt, **kwargs)

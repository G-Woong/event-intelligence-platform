from __future__ import annotations

import hashlib
import logging
import struct
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

_client_cache: Optional["BaseEmbeddingClient"] = None


class BaseEmbeddingClient(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> list[float]: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


class MockEmbeddingClient(BaseEmbeddingClient):
    """Deterministic: same text → same unit vector (stdlib-only)."""

    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    def embed_text(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        # Build dim floats from repeated hashing
        floats: list[float] = []
        seed = digest
        while len(floats) < self._dim:
            seed = hashlib.sha256(seed).digest()
            for i in range(0, len(seed) - 3, 4):
                val, = struct.unpack_from(">f", seed, i)
                if val != val or abs(val) > 1e10:  # nan/inf guard
                    val = 0.0
                floats.append(val)
        floats = floats[: self._dim]
        norm = sum(x * x for x in floats) ** 0.5 + 1e-12
        return [x / norm for x in floats]


class OpenAIEmbeddingClient(BaseEmbeddingClient):
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        timeout: float = 30.0,
    ) -> None:
        import os
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY is not set (len=0)")
        logger.debug("OpenAIEmbeddingClient initialized (key len=%d)", len(key))
        import openai
        self._client = openai.OpenAI(api_key=key)
        self._model = model
        self._timeout = timeout

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        import openai
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_exponential(min=1, max=4),
            retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
            reraise=True,
        )
        def _call() -> list[list[float]]:
            resp = self._client.embeddings.create(
                model=self._model,
                input=texts,
                timeout=self._timeout,
            )
            return [item.embedding for item in resp.data]

        return _call()


def create_embedding_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseEmbeddingClient:
    from backend.app.core.config import settings
    _provider = provider or settings.EMBEDDING_PROVIDER
    _model = model or settings.EMBEDDING_MODEL
    _dim = settings.EMBEDDING_DIM
    if _provider == "openai":
        return OpenAIEmbeddingClient(model=_model, timeout=settings.EMBEDDING_TIMEOUT_SEC)
    return MockEmbeddingClient(dim=_dim)


def get_embedding_client() -> BaseEmbeddingClient:
    global _client_cache
    if _client_cache is None:
        _client_cache = create_embedding_client()
    return _client_cache


def reset_embedding_client_cache() -> None:
    global _client_cache
    _client_cache = None

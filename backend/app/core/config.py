from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LANGSMITH_TRACING: str = ""
    LANGSMITH_ENDPOINT: str = ""
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = ""
    OPENAI_API_KEY: str = ""
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    REDIS_URL: str = "redis://localhost:6379/0"
    DATABASE_URL: str = "postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel"

    LLM_PROVIDER: Literal["mock", "openai"] = "mock"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TIMEOUT_SEC: float = 30.0
    LLM_MAX_TOKENS: int = 1024
    LLM_TEMPERATURE: float = 0.2

    EMBEDDING_PROVIDER: Literal["mock", "openai"] = "mock"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536
    EMBEDDING_TIMEOUT_SEC: float = 30.0
    MILVUS_COLLECTION: str = "event_embeddings"

    BACKEND_INTERNAL_URL: str = "http://backend:8000"
    ADMIN_API_TOKEN: str = ""

    RSS_COLLECTOR_FETCH_TIMEOUT_SEC: int = 15
    RSS_SOURCES_CONFIG_PATH: str = ""
    RSS_COLLECTOR_USER_AGENT: str = "event-intelligence/0.7 (+ei)"

    def redacted_env_status(self) -> dict[str, str]:
        fields = [
            "LANGSMITH_TRACING", "LANGSMITH_ENDPOINT", "LANGSMITH_API_KEY",
            "LANGSMITH_PROJECT", "OPENAI_API_KEY", "MILVUS_HOST",
            "MILVUS_PORT", "REDIS_URL", "DATABASE_URL",
            "LLM_PROVIDER", "LLM_MODEL",
            "EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "EMBEDDING_DIM",
            "MILVUS_COLLECTION", "BACKEND_INTERNAL_URL", "ADMIN_API_TOKEN",
            "RSS_COLLECTOR_FETCH_TIMEOUT_SEC", "RSS_SOURCES_CONFIG_PATH",
            "RSS_COLLECTOR_USER_AGENT",
        ]
        result = {}
        for f in fields:
            val = str(getattr(self, f, ""))
            if val:
                result[f] = f"set (len={len(val)})"
            else:
                result[f] = "empty"
        return result


settings = Settings()

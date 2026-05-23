from __future__ import annotations

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

    def redacted_env_status(self) -> dict[str, str]:
        fields = [
            "LANGSMITH_TRACING", "LANGSMITH_ENDPOINT", "LANGSMITH_API_KEY",
            "LANGSMITH_PROJECT", "OPENAI_API_KEY", "MILVUS_HOST",
            "MILVUS_PORT", "REDIS_URL", "DATABASE_URL",
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

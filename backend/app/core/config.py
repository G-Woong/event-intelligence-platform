from __future__ import annotations

from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _blank_env_means_default(cls, data: object) -> object:
        """`.env` 의 빈 값(`KEY=`)은 '미설정 = 코드 기본값' 으로 해석한다.

        `.env.example` 계약: 다수 키가 빈 값으로 선언되고 "empty = use DEFAULT" 다.
        그러나 float/int/bool/Literal 필드는 빈 문자열을 강제 파싱하다 실패한다
        (예: EMBEDDING_TIMEOUT_SEC='' → float_parsing 에러). 빈 문자열 키를 입력에서
        제거하면 pydantic 이 각 필드의 기본값을 사용한다 — env 선언 구조와 타입 계약을 일치시킨다.
        (CORS_ALLOW_ORIGINS 는 NoDecode + _parse_cors 로 별도 처리.)
        """
        if isinstance(data, dict):
            return {
                k: v for k, v in data.items()
                if not (isinstance(v, str) and v.strip() == "")
            }
        return data

    # 실행 환경. production/staging에서는 admin API 토큰 미설정 시 인증을 fail-closed로 강제한다.
    APP_ENV: Literal["dev", "test", "staging", "production"] = "dev"

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

    # evidence URL HTTP 도달성 검증(SSRF-safe). 네트워크 호출이므로 기본 off.
    # on 이면 evidence_check 가 구조검증 통과 URL 을 실제 HEAD/GET 으로 도달 확인하고,
    # 도달 불가 근거는 채택하지 않는다(publish_or_hold 가 hold).
    EVIDENCE_REACHABILITY_CHECK: bool = False
    EVIDENCE_REACHABILITY_TIMEOUT_SEC: float = 5.0
    EVIDENCE_REACHABILITY_MAX_REDIRECTS: int = 3

    EMBEDDING_PROVIDER: Literal["mock", "openai"] = "mock"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536
    EMBEDDING_TIMEOUT_SEC: float = 30.0
    MILVUS_COLLECTION: str = "event_embeddings"

    BACKEND_INTERNAL_URL: str = "http://backend:8000"
    ADMIN_API_TOKEN: str = ""

    # NoDecode: pydantic-settings 가 list 필드를 env 소스에서 JSON 으로 먼저 디코드하는 것을
    # 끈다. .env 는 콤마구분 문자열(예: "http://a,http://b")로 선언하고(아래 _parse_cors 가 분할),
    # 기본값/코드에서는 list[str] 로 다룬다. (env-as-CSV ↔ list[str] 계약 일치)
    CORS_ALLOW_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("CORS_ALLOW_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v  # type: ignore[return-value]

    OPENSEARCH_HOST: str = "opensearch"
    OPENSEARCH_PORT: int = 9200
    OPENSEARCH_EVENT_INDEX: str = "event_cards"

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
            "OPENSEARCH_HOST", "OPENSEARCH_PORT", "OPENSEARCH_EVENT_INDEX",
        ]
        result = {}
        for f in fields:
            val = str(getattr(self, f, ""))
            if val:
                result[f] = f"set (len={len(val)})"
            else:
                result[f] = "empty"
        result["CORS_ALLOW_ORIGINS"] = f"set ({len(self.CORS_ALLOW_ORIGINS)} origins)"
        return result


settings = Settings()

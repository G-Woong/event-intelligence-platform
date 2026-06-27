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

    # Event resolution live wiring(C, ADR#22): 수집 후보(클러스터)를 cross_source_dedup →
    # event_resolver → event_timeline_service 로 영속해 events/event_updates 타임라인을 누적한다.
    # 기본 off — on 이어도 기존 event_cards 직접 생성 경로는 그대로 병행(비파괴). off 면 Event
    # 영속 0(DB 미접근), 기존 경로만 동작. LLM 미사용(전 경로 결정론).
    EVENT_RESOLUTION_ENABLED: bool = False

    # Semantic shadow adjudication operational wiring(ADR#48, R-LiveIdentityBacklog): EVENT_RESOLUTION_ENABLED
    # 로 ② semantic 후보 link(event_links possible)가 누적된 뒤, 배치 종료 시 결정론 shadow adjudication
    # (③ semantic_identity_adjudicator)을 자동 실행해 event_identity_adjudication 백로그를 누적한다 — 그래야
    # live-derived labeling packet 이 synthetic/수동 주입 없이 운영 후보를 읽는다. **자동 병합 0**(read +
    # adjudication write only·events/updates/cluster_event_map 미변경·idempotent upsert). 기본 off — on 이어도
    # Event count 불변. off 면 ③ 미실행(기존 ①② 경로만·_FakeSession 등 in-memory 호출처 무영향).
    EVENT_SEMANTIC_ADJUDICATION_ENABLED: bool = False

    # Event 타임라인 read API(D-2a): /api/events/timeline* 공개 조회 노출 토글. 기본 off —
    # off 면 endpoint 404(미노출). write(EVENT_RESOLUTION_ENABLED)와 분리(읽기 노출 ≠ 쓰기 결선).
    # read-only·결정론(LLM/network 0). 기존 /api/events(event_cards) 경로는 무관(항상 동작).
    EVENT_TIMELINE_API_ENABLED: bool = False

    # Internal ops dashboard read API(ADR#72): /api/internal/ops/* read-only 노출 토글. 기본 off —
    # off 면 endpoint 404(미노출). admin-token(require_admin_token)과 **이중 게이트**(인증 + flag).
    # public truth 아님(workflow state 만·same_event/score/rationale/predicted_status/raw PII 0).
    # read-only·결정론(LLM/embedding/DB-write/network 0). reviewer pipeline 의 운영 상태만 노출한다.
    INTERNAL_OPS_DASHBOARD_ENABLED: bool = False

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
            s = v.strip()
            # JSON 배열 형태(`["a","b"]`)도 허용 — NoDecode 로 raw 문자열이 오므로
            # 여기서 직접 처리한다. 깨진 JSON 은 콤마분할이 아니라 fail-loud(조용한
            # garbage origin 방지, adversarial 리뷰 57a0049 반영).
            if s.startswith("["):
                import json
                try:
                    parsed = json.loads(s)
                except ValueError as exc:
                    raise ValueError(
                        f"CORS_ALLOW_ORIGINS looks like JSON but failed to parse: {exc}"
                    ) from exc
                if not isinstance(parsed, list):
                    raise ValueError("CORS_ALLOW_ORIGINS JSON must be a list of origins")
                return [str(o).strip() for o in parsed if str(o).strip()]
            return [o.strip() for o in s.split(",") if o.strip()]
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

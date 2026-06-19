"""env 파서 계약 회귀 테스트 (commit 57a0049 + adversarial 리뷰 반영).

검증 대상:
- CORS_ALLOW_ORIGINS: CSV 문자열·JSON 배열 양형식 파싱, 깨진 JSON fail-loud.
- 빈 .env 값(`KEY=`)이 float/int/Literal 필드에서 죽지 않고 기본값으로 떨어짐.
`_env_file=None` 으로 실제 `.env` 를 읽지 않고 격리한다(테스트는 .env 비의존).
"""
from __future__ import annotations

import pytest

from backend.app.core.config import Settings


def _settings(**kw) -> Settings:
    # _env_file=None: 실제 .env 미참조(격리). OS env 도 해당 키 없음 가정.
    return Settings(_env_file=None, **kw)


def test_cors_csv_single():
    s = _settings(CORS_ALLOW_ORIGINS="http://localhost:3000")
    assert s.CORS_ALLOW_ORIGINS == ["http://localhost:3000"]


def test_cors_csv_multi_with_spaces():
    s = _settings(CORS_ALLOW_ORIGINS="http://a , http://b,http://c")
    assert s.CORS_ALLOW_ORIGINS == ["http://a", "http://b", "http://c"]


def test_cors_json_array_form_is_tolerated():
    # pydantic 기본 스타일 JSON 배열도 깨진 origin 없이 파싱돼야 한다.
    s = _settings(CORS_ALLOW_ORIGINS='["http://a","http://b"]')
    assert s.CORS_ALLOW_ORIGINS == ["http://a", "http://b"]


def test_cors_malformed_json_fails_loud():
    # `[` 로 시작하는 깨진 JSON 은 조용히 콤마분할(garbage origin)하지 않고 에러.
    with pytest.raises(Exception):
        _settings(CORS_ALLOW_ORIGINS='["http://a"')


def test_cors_default_when_unset():
    assert _settings().CORS_ALLOW_ORIGINS == ["http://localhost:3000"]


def test_blank_numeric_env_falls_back_to_default():
    # `.env.example` 계약: 빈 값 = 기본값. float/int 가 빈 문자열에 죽지 않아야 한다.
    s = _settings(EMBEDDING_TIMEOUT_SEC="", MILVUS_PORT="", LLM_MAX_TOKENS="")
    assert s.EMBEDDING_TIMEOUT_SEC == 30.0
    assert s.MILVUS_PORT == 19530
    assert s.LLM_MAX_TOKENS == 1024


def test_blank_literal_env_falls_back_to_default():
    s = _settings(LLM_PROVIDER="", EMBEDDING_PROVIDER="", APP_ENV="")
    assert s.LLM_PROVIDER == "mock"
    assert s.EMBEDDING_PROVIDER == "mock"
    assert s.APP_ENV == "dev"


def test_nonblank_value_still_applied():
    # blank-drop 이 비-빈 값을 삼키지 않음을 확인.
    s = _settings(MILVUS_PORT="19531", LLM_PROVIDER="openai")
    assert s.MILVUS_PORT == 19531
    assert s.LLM_PROVIDER == "openai"

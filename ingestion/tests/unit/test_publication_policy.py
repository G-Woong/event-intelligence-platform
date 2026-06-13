from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ingestion.core.publication_policy import (
    PublicationPolicy,
    is_publication_candidate,
    load_publication_policy,
    public_preview,
    raw_artifact_is_internal,
)


def test_default_policy_is_conservative():
    policy = load_publication_policy("unknown_source_xyz")
    assert policy.allow_full_text_publication is False
    assert policy.max_public_preview_chars == 200
    assert policy.attribution_required is True
    assert policy.source_url_required is True
    assert policy.raw_artifact_visibility == "internal_only"


def test_per_source_merge_overrides_default():
    serper = load_publication_policy("serper")
    assert serper.max_public_preview_chars == 0  # 내부 시그널 전용
    # default 필드는 유지된다
    assert serper.source_url_required is True

    fed = load_publication_policy("federal_register")
    assert fed.max_public_preview_chars == 500


def test_public_preview_truncates_to_limit():
    text = "가" * 500
    preview = public_preview(text, "yna")
    assert len(preview) <= 201  # 200 + 말줄임
    assert preview.endswith("…")


def test_public_preview_short_text_unchanged():
    assert public_preview("짧은 텍스트", "yna") == "짧은 텍스트"


def test_public_preview_zero_limit_returns_empty():
    assert public_preview("어떤 검색 결과", "serper") == ""


def test_public_preview_empty_input():
    assert public_preview("", "yna") == ""


def test_candidate_requires_source_url():
    ok, reason = is_publication_candidate(
        {"source_id": "yna", "title": "t", "source_url": "https://www.yna.co.kr/view/X"}
    )
    assert ok is True

    ok, reason = is_publication_candidate({"source_id": "yna", "title": "t"})
    assert ok is False
    assert reason == "missing_source_url"


def test_raw_artifact_is_internal_only():
    assert raw_artifact_is_internal("yna") is True
    assert raw_artifact_is_internal("unknown_source") is True


def test_missing_yaml_no_exception():
    with patch(
        "ingestion.core.publication_policy._POLICY_PATH",
        Path("/nonexistent/publication_policy.yaml"),
    ):
        policy = load_publication_policy("yna")
        assert isinstance(policy, PublicationPolicy)
        assert policy.allow_full_text_publication is False
        # 절단 헬퍼도 기본값으로 동작
        assert public_preview("a" * 500, "yna").startswith("a")


def test_collection_path_not_wired():
    """publication_policy는 수집 경로(collection_probe/strategy_runner)에 연결되지 않는다."""
    import ingestion.fetch_strategies.collection_probe as cp
    import ingestion.fetch_strategies.strategy_runner as sr
    for module in (cp, sr):
        src = Path(module.__file__).read_text(encoding="utf-8")
        assert "publication_policy" not in src

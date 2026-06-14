"""Phase D-P: live artifact expansion 생산성 audit (synthetic fixture 기반).

artifact 존재 ≠ 분해 성공을 실제 지표로 검증한다. 실제 기사 전문/키 없음(합성만).
"""
from __future__ import annotations

from pathlib import Path

from ingestion.orchestration.artifact_parser import parse_artifact_text
from ingestion.orchestration.production_audit import (
    audit_artifact_file,
    audit_artifact_text,
    summarize_expansion,
)

_FIX = Path(__file__).parent.parent / "fixtures" / "orchestration"


def _read(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


def test_artifact_exists_with_candidate_count():
    a = audit_artifact_text(
        _read("gdelt_minimal.json"), source_id="gdelt", purpose="regulatory",
        source_group="official", artifact_path="x/gdelt.json", fmt="json",
    )
    assert a.artifact_exists is True
    assert a.candidate_count == 2
    assert a.title_present_count == 2
    assert a.url_present_count == 2
    assert a.canonical_url_count == 2
    assert a.production_risk is None


def test_artifact_exists_zero_candidates_is_risk():
    a = audit_artifact_text(
        _read("empty.json"), source_id="gdelt", purpose="news",
        source_group="news", artifact_path="x/empty.json", fmt="json",
    )
    assert a.candidate_count == 0
    assert a.structured_signal_count == 0
    assert "no_candidates_from_artifact" in a.risk_flags
    assert a.production_risk is not None


def test_numeric_nested_uses_structured_signal_fallback():
    # coinbase products[] 형태: 기사 컨테이너 아님 → 분해 0이지만 market이므로 본문 누락이 아님
    a = audit_artifact_text(
        _read("numeric_nested.json"), source_id="coinbase_market", purpose="numeric",
        source_group="market", artifact_path="x/coinbase.json", fmt="json",
    )
    assert a.candidate_count == 0
    assert a.structured_signal_count == 1
    assert a.fallback_used is True
    assert a.body_state_counts["numeric_exempt"] == 1
    assert a.body_state_counts["missing"] == 0  # numeric은 missing으로 오염 안 됨
    assert "no_candidates_from_artifact" not in a.risk_flags


def test_parse_error_count_is_recorded():
    a = audit_artifact_text(
        _read("malformed.json"), source_id="newsapi", purpose="search",
        source_group="search", artifact_path="x/m.json", fmt="json",
    )
    assert a.parse_error_count >= 1
    assert "parse_errors_present" in a.risk_flags


def test_rate_limit_payload_not_disguised_as_success():
    a = audit_artifact_text(
        _read("rate_limit_note.json"), source_id="alpha_vantage", purpose="numeric",
        source_group="market", artifact_path="x/av.json", fmt="json",
    )
    assert "possible_rate_limit_payload" in a.risk_flags
    # structured signal로 세더라도 risk로 정직하게 표시한다
    assert a.production_risk is not None


def test_numeric_payload_separate_from_article_body():
    a = audit_artifact_text(
        _read("api_numeric_payload.json"), source_id="finnhub", purpose="numeric",
        source_group="market", artifact_path="x/fh.json", fmt="json",
    )
    assert a.candidate_count == 1
    assert a.body_state_counts["numeric_exempt"] == 1
    assert a.body_state_counts["missing"] == 0
    assert a.production_risk is None


def test_news_titles_present_but_urls_missing_is_risk():
    xml = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<item><title>A</title></item>"
        "<item><title>B</title></item>"
        "</channel></rss>"
    )
    a = audit_artifact_text(
        xml, source_id="bbc", purpose="news", source_group="news",
        artifact_path="x/bbc.xml", fmt="xml",
    )
    assert a.candidate_count == 2
    assert a.title_present_count == 2
    assert a.url_present_count == 0
    assert "all_urls_missing" in a.risk_flags


def test_html_artifact_reported_as_not_decomposed():
    a = audit_artifact_text(
        _read("html_page.html"), source_id="cnbc", purpose="news",
        source_group="news", artifact_path="x/p.html", fmt=None,
    )
    assert a.parser_name == "html_unsupported"
    assert "html_not_decomposed" in a.risk_flags
    assert a.candidate_count == 0


def test_fed_register_url_and_time_now_mapped():
    # html_url/publication_date alias 보강 효과 — 존재하는 URL/시각을 버리지 않는다
    a = audit_artifact_text(
        _read("fed_register_results.json"), source_id="federal_register",
        purpose="regulatory", source_group="official",
        artifact_path="x/fr.json", fmt="json",
    )
    assert a.candidate_count == 2
    assert a.url_present_count == 2
    assert a.canonical_url_count == 2  # tracking 제거 후에도 유효 URL
    assert a.published_at_present_count == 2


def test_source_group_body_distribution_summary():
    audits = [
        audit_artifact_text(
            _read("fed_register_results.json"), source_id="federal_register",
            purpose="regulatory", source_group="official",
            artifact_path="x/fr.json", fmt="json",
        ),
        audit_artifact_text(
            _read("api_numeric_payload.json"), source_id="finnhub", purpose="numeric",
            source_group="market", artifact_path="x/fh.json", fmt="json",
        ),
    ]
    summary = summarize_expansion(audits)
    assert summary["totals"]["candidate_total"] == 3
    assert "official" in summary["body_state_by_group"]
    assert "market" in summary["body_state_by_group"]
    assert summary["body_state_by_group"]["market"]["numeric_exempt"] == 1


def test_missing_artifact_file_reports_artifact_missing():
    a = audit_artifact_file(
        _FIX / "does_not_exist_synthetic.json", source_id="x", purpose="news",
        source_group="news",
    )
    assert a.artifact_exists is False
    assert a.production_risk == "artifact_missing"
    assert a.evidence_path_present is False


def test_community_confirmation_policy_preserved_through_parse():
    cands, name, errors = parse_artifact_text(
        _read("generic_articles.json"), source_id="hacker_news",
        confirmation_policy="unconfirmed_until_corroborated", fmt="json",
    )
    assert cands
    assert all(c.confirmation_policy == "unconfirmed_until_corroborated" for c in cands)

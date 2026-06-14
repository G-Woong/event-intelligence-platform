"""Phase E-1: 소스별 production readiness 분류 + 요약."""
from __future__ import annotations

from pathlib import Path

from ingestion.orchestration.source_body_audit import audit_source_body
from ingestion.orchestration.source_body_report import (
    build_source_report,
    classify_production_readiness,
    summarize_reports,
)

_FIX = Path(__file__).parent.parent / "fixtures" / "orchestration"


def _read(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


def _audit(name, **kw):
    return audit_source_body(_read(name), **kw).audit


def test_numeric_source_is_structured_signal_only():
    a = _audit("api_numeric_payload.json", source_id="finnhub", purpose="numeric",
               source_group="market", fmt="json")
    readiness, _ = classify_production_readiness(a)
    assert readiness == "STRUCTURED_SIGNAL_ONLY"


def test_news_with_full_body_is_production_ready():
    a = _audit("rss_content_encoded.xml", source_id="bbc", purpose="news",
               source_group="news", fmt="xml")
    readiness, _ = classify_production_readiness(a)
    # present 1 + snippet 1 → 본문 확보로 PRODUCTION_READY
    assert readiness == "PRODUCTION_READY_SIGNAL"


def test_snippet_only_news_needs_body_fetch():
    a = audit_source_body(
        '[{"title": "T", "url": "https://x.test/1", "description": "snippet"}]',
        source_id="yna", purpose="news", source_group="news", fmt="json").audit
    readiness, action = classify_production_readiness(a)
    assert readiness == "NEEDS_BODY_FETCH"
    assert "fetch" in action.lower()


def test_error_envelope_with_key_required_is_key_missing():
    a = _audit("api_error_status.json", source_id="opendart", purpose="regulatory",
               source_group="official", fmt="json")
    readiness, _ = classify_production_readiness(
        a, requires_api_key=True, api_key_ready=False)
    assert readiness == "KEY_MISSING"


def test_unknown_schema_is_needs_parser():
    a = _audit("no_articles.json", source_id="x", purpose="news",
               source_group="news", fmt="json")
    readiness, _ = classify_production_readiness(a)
    assert readiness == "NEEDS_PARSER"


def test_html_unsupported_classified():
    a = _audit("html_page.html", source_id="zdnet_korea", purpose="news",
               source_group="news")
    readiness, _ = classify_production_readiness(a)
    assert readiness == "HTML_UNSUPPORTED"


def test_blocked_policy_no_bypass():
    a = _audit("no_articles.json", source_id="dcinside", purpose="community",
               source_group="community", fmt="json")
    readiness, _ = classify_production_readiness(a, skip_reason="robots_or_policy_block")
    assert readiness == "BLOCKED_NO_BYPASS"


def test_titles_missing_is_needs_parser():
    # 분해되나 title 미매핑(es _source에 표준 title 키 없음) → 필드 매핑 필요.
    # 어댑터 미등록 source_id로 generic nested 경로의 title-missing → NEEDS_PARSER를 검증한다
    # (sec_edgar는 E-3 전용 adapter가 display_names→title을 매핑하므로 더 이상 title-missing 아님).
    a = _audit("es_nested_hits.json", source_id="generic_official", purpose="regulatory",
               source_group="official", fmt="json")
    readiness, _ = classify_production_readiness(a)
    assert readiness == "NEEDS_PARSER"


def test_build_report_and_summary():
    a = _audit("rss_content_encoded.xml", source_id="bbc", purpose="news",
               source_group="news", fmt="xml")
    rep = build_source_report(a, enabled=True, live_eligible="true",
                              requires_api_key=False, artifact_type="xml",
                              sample_saved_count=1)
    assert rep.production_readiness == "PRODUCTION_READY_SIGNAL"
    assert rep.sample_saved_count == 1
    summ = summarize_reports([rep])
    assert summ["sources"] == 1
    assert summ["readiness_distribution"]["PRODUCTION_READY_SIGNAL"] == 1
    assert "news" in summ["readiness_by_group"]

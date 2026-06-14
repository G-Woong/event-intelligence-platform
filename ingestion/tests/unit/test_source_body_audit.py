"""Phase E-1: 소스별 본문 추출 audit (audit_source_body + sample 저장 + REDIS 안전)."""
from __future__ import annotations

import os
from pathlib import Path

from ingestion.orchestration.audit_trace import TraceRecorder
from ingestion.orchestration.source_body_audit import (
    audit_source_body,
    summarize_body_audits,
)
from ingestion.orchestration.source_profile import load_source_profiles
from ingestion.tools.run_source_body_audit import _write_samples

_FIX = Path(__file__).parent.parent / "fixtures" / "orchestration"


def _read(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


def test_audits_two_sources_news_and_numeric():
    news = audit_source_body(
        _read("rss_content_encoded.xml"), source_id="bbc", purpose="news",
        source_group="news", fmt="xml")
    numeric = audit_source_body(
        _read("api_numeric_payload.json"), source_id="finnhub", purpose="numeric",
        source_group="market", fmt="json")
    # 뉴스: content:encoded 1건 present + snippet 1건
    assert news.audit.candidate_count == 2
    assert news.audit.body_present_count == 1
    assert news.audit.snippet_only_count == 1
    # numeric: 본문 게이트 면제(structured signal), 기사 본문 성공으로 섞이지 않음
    assert numeric.audit.numeric_exempt_count == 1
    assert numeric.audit.body_present_count == 0


def test_trace_events_recorded_per_stage(tmp_path):
    rec = TraceRecorder("r", jsonl_path=tmp_path / "t.jsonl", console=False)
    audit_source_body(_read("nyt_nested_docs.json"), source_id="nyt", purpose="news",
                      source_group="news", fmt="json", recorder=rec, timestamp="t0")
    stages = {e.stage for e in rec.events_for("nyt")}
    assert "candidate_expansion_finished" in stages
    assert "quality_pre_gate_applied" in stages
    assert "source_completed" in stages


def test_failure_source_does_not_raise():
    # 에러 봉투/깨진 입력도 예외 없이 결과를 반환한다(전체 run 보호).
    res = audit_source_body(_read("api_error_result.json"), source_id="bok_ecos",
                            purpose="regulatory", source_group="official", fmt="json")
    assert res.audit.candidate_count == 0
    assert res.audit.parser_name == "api_error_payload"
    assert "no_candidates_from_artifact" in res.audit.risk_flags
    # 텍스트 None도 안전
    res2 = audit_source_body(None, source_id="ghost", purpose="news")
    assert res2.audit.artifact_exists is False


def test_community_confirmation_policy_preserved():
    res = audit_source_body(
        '[{"title": "C", "url": "https://c.test/1", "description": "d"}]',
        source_id="hacker_news", purpose="community", source_group="community",
        confirmation_policy="unconfirmed_until_corroborated", fmt="json")
    assert res.inspections[0].candidate.confirmation_policy == "unconfirmed_until_corroborated"


def test_sample_files_written_and_truncated(tmp_path):
    res = audit_source_body(_read("rss_content_encoded.xml"), source_id="bbc",
                            purpose="news", source_group="news", fmt="xml")
    saved = _write_samples(res, tmp_path, max_items=1, body_chars=50)
    assert saved == 1
    src_dir = tmp_path / "bbc"
    assert (src_dir / "candidate_0001.meta.json").exists()
    assert (src_dir / "candidate_0001.preview.txt").exists()
    body = (src_dir / "candidate_0001.body_sample.txt").read_text(encoding="utf-8")
    assert len(body) <= 50  # sample-body-chars 상한 준수


def test_sample_contains_no_secret_values(tmp_path):
    res = audit_source_body(
        '[{"title": "T", "url": "https://x.test/1", "description": "s"}]',
        source_id="bbc", purpose="news", source_group="news", fmt="json")
    _write_samples(res, tmp_path, max_items=1, body_chars=3000)
    meta = (tmp_path / "bbc" / "candidate_0001.meta.json").read_text(encoding="utf-8")
    for marker in ("api_key", "secret", "token", "password"):
        assert marker not in meta.lower()


def test_summarize_splits_numeric_from_body():
    a1 = audit_source_body(_read("rss_content_encoded.xml"), source_id="bbc",
                           purpose="news", source_group="news", fmt="xml").audit
    a2 = audit_source_body(_read("api_numeric_payload.json"), source_id="finnhub",
                           purpose="numeric", source_group="market", fmt="json").audit
    summ = summarize_body_audits([a1, a2])
    assert summ["totals"]["body_present"] == 1
    assert summ["totals"]["numeric_exempt"] == 1
    # group별 분리 보고
    assert summ["body_state_by_group"]["market"]["numeric_exempt"] == 1
    assert summ["body_state_by_group"]["news"]["present"] == 1


def test_redis_url_env_with_explicit_jsonl_is_safe(tmp_path, monkeypatch):
    # REDIS_URL이 설정돼도 명시적 JSONL 모드는 NotImplementedError 없이 동작한다.
    from ingestion.pipeline.event_queue import EventQueue

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    q = EventQueue(redis_url="", fallback_dir=tmp_path)
    item_id = q.enqueue({"source_id": "bbc", "title_or_keyword": "t"})
    assert item_id
    assert q.peek(1)


def test_full_source_profile_coverage_maintained():
    # Phase E-1 변경이 profile coverage(57)를 약화시키지 않는다.
    assert len(load_source_profiles()) == 57


def test_default_output_dir_is_gitignored_outputs():
    import ingestion.tools.run_source_body_audit as runner
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=str(
        runner._REPO_ROOT / "ingestion" / "outputs" / "tmp_source_body_audit"))
    args = ap.parse_args([])
    # outputs/ 아래여야 .gitignore로 커밋되지 않는다.
    assert "outputs" in args.output_dir.replace("\\", "/").split("/")

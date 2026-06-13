"""01~05 조건부 소스 E2E 종결 audit — 네트워크/브라우저 없는 단위 테스트.

run_conditional_sources_e2e_audit의 핵심 로직(스키마/본문 추출 분기/쿨다운 collected=false/
related_query body=not_required/RISK-T04 영속 판정/JSONL writer)을 주입형 fake로 고정한다.
실제 source 호출·httpx·trafilatura·url_resolver는 전부 monkeypatch로 차단한다.
"""
import json

import pytest

from ingestion.runners import run_conditional_sources_e2e_audit as m
from ingestion.core.extraction_result import ExtractionResult
from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult
from ingestion.probes.models import ProbeResult


@pytest.fixture(autouse=True)
def _no_record_call(monkeypatch):
    # record_call이 실제 rate_limit_cache를 건드리지 않게 한다(상태 오염 방지).
    monkeypatch.setattr(m, "record_call", lambda *a, **k: None)


def _target(tid):
    return next(t for t in m.E2E_TARGETS if t["id"] == tid)


# ── candidate schema ─────────────────────────────────────────────────────────

def test_candidate_schema_has_all_required_fields():
    sample = {"title": "헤드라인", "url": "https://apnews.com/article/x",
              "canonical_url": "https://apnews.com/article/x",
              "snippet": "요약", "published_at": "2026-06-13"}
    cand = m.build_candidate(_target("ap_news"), sample, run_id="rid1",
                             status="LIVE_SUCCESS", next_retry_at=None,
                             raw_artifact_path="raw/x.xml")
    required = {
        "run_id", "source_id", "source_role", "candidate_type", "title", "keyword",
        "url", "canonical_url", "resolved_url", "published_at", "observed_at", "snippet",
        "body_status", "body_length", "body_artifact_path", "extraction_method",
        "evidence_level", "status", "error_category", "next_retry_at", "raw_artifact_path",
    }
    assert required.issubset(cand.keys())
    assert cand["source_id"] == "ap_news"
    assert cand["body_status"] == "pending"          # body_required=True 소스
    assert cand["canonical_url"] == sample["canonical_url"]


def test_related_query_candidate_body_not_required_and_keyword_set():
    sample = {"title": "갤럭시", "url": None, "snippet": None, "published_at": None}
    cand = m.build_candidate(_target("google_trends_explore"), sample, run_id="rid2",
                             status="LIVE_SUCCESS", next_retry_at=None, raw_artifact_path=None)
    assert cand["candidate_type"] == "related_query"
    assert cand["keyword"] == "갤럭시"
    assert cand["body_status"] == "not_required"


# ── 본문 추출 분기 ───────────────────────────────────────────────────────────

def test_extract_body_success_saves_artifact(monkeypatch):
    monkeypatch.setattr(m, "extract_with_trafilatura",
                        lambda html, url: ExtractionResult(
                            url=url, strategy="trafilatura", success=True,
                            title="T", body="본문 " * 100, published_at="2026-06-13"))
    saved = {}
    monkeypatch.setattr(m, "save_extracted_text",
                        lambda rid, sid, uh, strat, fields: saved.setdefault("path", f"/tmp/{sid}.txt"))
    out = m.extract_body("newsapi", {"url": "https://site/x", "title": "T"},
                         fetch_fn=lambda u: "<html>ok</html>")
    assert out["body_status"] == "extracted"
    assert out["body_length"] >= m._BODY_MIN_CHARS
    assert out["extraction_method"] == "trafilatura"
    assert out["body_artifact_path"] == "/tmp/newsapi.txt"


def test_extract_body_blocked_not_bypassed(monkeypatch):
    monkeypatch.setattr(m, "classify_content_blocker", lambda html_lower: "PAYWALL_DETECTED")
    out = m.extract_body("newsapi", {"url": "https://site/x"},
                         fetch_fn=lambda u: "<html>subscribe to read</html>", save=False)
    assert out["body_status"] == "blocked"
    assert "content_blocker" in out["failure_reason"]


def test_extract_body_no_url():
    out = m.extract_body("newsapi", {"url": None}, fetch_fn=lambda u: "x")
    assert out["body_status"] == "no_url"


def test_extract_body_fetch_failed():
    out = m.extract_body("newsapi", {"url": "https://site/x"}, fetch_fn=lambda u: None)
    assert out["body_status"] == "failed"
    assert out["failure_reason"] == "fetch_failed_or_non_200"


def test_extract_body_too_short_is_failed(monkeypatch):
    monkeypatch.setattr(m, "extract_with_trafilatura",
                        lambda html, url: ExtractionResult(
                            url=url, strategy="trafilatura", success=False, body="짧음"))
    out = m.extract_body("gdelt", {"url": "https://site/x"},
                         fetch_fn=lambda u: "<html>x</html>", save=False)
    assert out["body_status"] == "failed"


# ── 소스별 audit 분기 ────────────────────────────────────────────────────────

def test_article_source_cooldown_is_external_rate_limit(monkeypatch):
    monkeypatch.setattr(m, "gate_check", lambda sid, q="": "cooldown_skip")
    monkeypatch.setattr(m, "in_cooldown", lambda sid, q="": (True, "2026-06-13T08:11:16Z"))
    rec = m.audit_article_source(
        _target("gdelt"), max_items=5, respect_rate_limit=True,
        probe_fn=lambda *a, **k: pytest.fail("probe must not be called on cooldown"),
        fetch_fn=lambda u: None)
    assert rec["collected"] is False
    assert rec["audit_action"] == "cooldown_skip"
    assert rec["final_status"] == "NOT_CLOSED_EXTERNAL_RATE_LIMIT"
    assert rec["next_retry_at"] == "2026-06-13T08:11:16Z"


def test_article_source_rate_limited_is_not_closed(monkeypatch):
    monkeypatch.setattr(m, "gate_check", lambda sid, q="": None)

    def fake_probe(sid, query=None, max_items=5):
        return CollectionProbeResult(
            source_id=sid, status="RATE_LIMITED", error_category="RATE_LIMITED",
            probe_result=ProbeResult(source_id=sid, method="api", status="RATE_LIMITED",
                                     next_retry_at="2026-06-13T09:00:00Z"),
            artifact_paths=ArtifactPaths(raw_payload="raw/gdelt/x.json"))

    rec = m.audit_article_source(_target("gdelt"), max_items=5, respect_rate_limit=True,
                                 probe_fn=fake_probe, fetch_fn=lambda u: None)
    assert rec["collected"] is False
    assert rec["final_status"] == "NOT_CLOSED_EXTERNAL_RATE_LIMIT"
    assert rec["next_retry_at"] == "2026-06-13T09:00:00Z"


def test_article_source_full_pass_with_body(monkeypatch):
    monkeypatch.setattr(m, "gate_check", lambda sid, q="": None)
    monkeypatch.setattr(m, "extract_sample_items", lambda *a, **k: [
        {"title": f"기사{i}", "url": f"https://apnews.com/a/{i}",
         "canonical_url": f"https://apnews.com/a/{i}", "snippet": "s",
         "published_at": "2026-06-13"} for i in range(3)
    ])
    # 첫 candidate만 본문 추출 성공으로 가정
    calls = {"n": 0}

    def fake_body(sid, cand, fetch_fn=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"body_status": "extracted", "body_length": 500,
                    "body_artifact_path": f"extracted_text/{sid}/x.txt",
                    "extraction_method": "trafilatura", "failure_reason": None,
                    "body_url": cand["url"]}
        return {"body_status": "failed", "body_length": 0, "body_artifact_path": None,
                "extraction_method": "trafilatura", "failure_reason": "body_too_short",
                "body_url": cand["url"]}

    def fake_probe(sid, query=None, max_items=5):
        return CollectionProbeResult(source_id=sid, status="LIVE_SUCCESS", items_found=3,
                                     artifact_paths=ArtifactPaths(raw_payload="raw/ap/x.xml"))

    rec = m.audit_article_source(_target("ap_news"), max_items=5, respect_rate_limit=True,
                                 probe_fn=fake_probe, fetch_fn=lambda u: "<html>x</html>",
                                 extract_body_fn=fake_body)
    assert rec["collected"] is True
    assert rec["candidates_created"] == 3
    assert rec["body_extracted"] == 1
    assert rec["final_status"] == "PASS"
    assert any(c["body_status"] == "extracted" for c in rec["candidates"])


def test_article_source_candidates_but_no_body_is_partial(monkeypatch):
    monkeypatch.setattr(m, "gate_check", lambda sid, q="": None)
    monkeypatch.setattr(m, "extract_sample_items", lambda *a, **k: [
        {"title": f"기사{i}", "url": f"https://site/{i}", "canonical_url": f"https://site/{i}",
         "snippet": "s", "published_at": "2026-06-13"} for i in range(3)
    ])
    monkeypatch.setattr(m, "extract_body", lambda sid, cand, fetch_fn=None: {
        "body_status": "blocked", "body_length": 0, "body_artifact_path": None,
        "extraction_method": "trafilatura", "failure_reason": "content_blocker:PAYWALL_DETECTED",
        "body_url": cand["url"]})

    def fake_probe(sid, query=None, max_items=5):
        return CollectionProbeResult(source_id=sid, status="LIVE_SUCCESS", items_found=3,
                                     artifact_paths=ArtifactPaths(raw_payload="raw/n/x.json"))

    rec = m.audit_article_source(_target("newsapi"), max_items=5, respect_rate_limit=True,
                                 probe_fn=fake_probe, fetch_fn=lambda u: "<html>x</html>",
                                 extract_body_fn=m.extract_body)
    assert rec["collected"] is True
    assert rec["body_extracted"] == 0
    assert rec["final_status"] == "PARTIAL_BODY_BLOCKED"


def test_related_query_source_pass_body_not_required(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "gate_check", lambda sid, q="": None)
    raw_signal = tmp_path / "trends.json"
    raw_signal.write_text(json.dumps(
        [{"keyword": f"연관어{i}", "url": None} for i in range(5)]), encoding="utf-8")

    def fake_pw(sid, query=None, region=None, max_items=5):
        return ProbeResult(source_id=sid, method="playwright", status="LIVE_SUCCESS",
                           items_found=5, artifact_paths={"raw_signal": str(raw_signal)})

    rec = m.audit_related_query_source(_target("google_trends_explore"), max_items=5,
                                       respect_rate_limit=True, playwright_fn=fake_pw)
    assert rec["collected"] is True
    assert rec["candidates_created"] == 5
    assert rec["body_extracted"] == 0
    assert all(c["body_status"] == "not_required" for c in rec["candidates"])
    assert rec["final_status"] == "PASS"


def test_related_query_rate_limited_not_closed(monkeypatch):
    monkeypatch.setattr(m, "gate_check", lambda sid, q="": None)

    def fake_pw(sid, query=None, region=None, max_items=5):
        return ProbeResult(source_id=sid, method="playwright", status="RATE_LIMITED",
                           error_category="RATE_LIMITED",
                           next_retry_at="2026-06-13T09:30:00Z", artifact_paths={})

    rec = m.audit_related_query_source(_target("google_trends_explore"), max_items=5,
                                       respect_rate_limit=True, playwright_fn=fake_pw)
    assert rec["collected"] is False
    assert rec["final_status"] == "NOT_CLOSED_EXTERNAL_RATE_LIMIT"


# ── RISK-T04 ─────────────────────────────────────────────────────────────────

class _FakeHealthStore:
    def __init__(self, state=None):
        self._state = state

    def get(self, sid):
        return self._state


def test_risk_t04_pass_when_runtime_429_persisted_and_gate_skips(monkeypatch):
    monkeypatch.setattr(m, "active_backend_name", lambda: "LocalPersistentRateLimitStore")
    monkeypatch.setattr(m, "in_cooldown", lambda sid, q="": (True, "2026-06-13T08:11:16Z"))
    monkeypatch.setattr(m, "get_health_store", lambda: _FakeHealthStore(None))
    data_records = [
        {"source_id": "gdelt", "status": "HEALTH_SKIP",
         "final_status": "NOT_CLOSED_EXTERNAL_RATE_LIMIT"},
    ]
    rec = m.audit_risk_t04(data_records)
    assert rec["final_status"] == "PASS"
    assert rec["status"] == "VERIFIED_PERSIST_AND_SKIP"
    ev = rec["rate_limit_evidence"][0]
    assert ev["rate_limit_cache_cooldown_persisted"] is True
    assert ev["gate_blocks_recall"] is True


def test_risk_t04_pass_via_unit_when_no_active_cooldown(monkeypatch):
    monkeypatch.setattr(m, "active_backend_name", lambda: "LocalPersistentRateLimitStore")
    monkeypatch.setattr(m, "in_cooldown", lambda sid, q="": (False, None))
    monkeypatch.setattr(m, "get_health_store", lambda: _FakeHealthStore(None))
    rec = m.audit_risk_t04([{"source_id": "gdelt", "status": "LIVE_SUCCESS"}])
    assert rec["final_status"] == "PASS_VIA_UNIT_AND_PRIOR_LIVE"
    assert rec["backend_is_local_file"] is True


def test_risk_t04_not_closed_when_backend_wrong(monkeypatch):
    monkeypatch.setattr(m, "active_backend_name", lambda: "InMemoryRateLimitStore")
    monkeypatch.setattr(m, "in_cooldown", lambda sid, q="": (False, None))
    monkeypatch.setattr(m, "get_health_store", lambda: _FakeHealthStore(None))
    rec = m.audit_risk_t04([])
    assert rec["final_status"] == "NOT_CLOSED_BACKEND"


# ── 통합 / JSONL ─────────────────────────────────────────────────────────────

def test_run_audit_records_all_five_including_collected_false(monkeypatch):
    monkeypatch.setattr(m, "gate_check", lambda sid, q="": None)
    monkeypatch.setattr(m, "extract_sample_items", lambda *a, **k: [])
    monkeypatch.setattr(m, "active_backend_name", lambda: "LocalPersistentRateLimitStore")
    monkeypatch.setattr(m, "in_cooldown", lambda sid, q="": (False, None))
    monkeypatch.setattr(m, "get_health_store", lambda: _FakeHealthStore(None))

    def fake_probe(sid, query=None, max_items=5):
        return CollectionProbeResult(source_id=sid, status="LIVE_SUCCESS",
                                     artifact_paths=ArtifactPaths(raw_payload="raw/x"))

    def fake_pw(sid, query=None, region=None, max_items=5):
        return ProbeResult(source_id=sid, method="playwright", status="RATE_LIMITED",
                           error_category="RATE_LIMITED", artifact_paths={})

    recs = m.run_audit(respect_rate_limit=True, probe_fn=fake_probe,
                       playwright_fn=fake_pw, fetch_fn=lambda u: None)
    ids = [r["source_id"] for r in recs]
    assert ids[0] == "RISK-T04"
    assert {"ap_news", "newsapi", "gdelt", "google_trends_explore"}.issubset(set(ids))
    assert len(recs) == 5


def test_jsonl_writer_roundtrip(tmp_path):
    from ingestion.runners._audit_common import write_audit_jsonl
    records = [{"source_id": "gdelt", "status": "RATE_LIMITED", "collected": False,
                "candidates": [{"title": "x"}]}]
    path = tmp_path / "out.jsonl"
    write_audit_jsonl(records, path)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["source_id"] == "gdelt"

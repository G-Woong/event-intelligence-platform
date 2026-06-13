"""Google Trends fallback 구조(PHASE 2/3) 단위 테스트 — 전부 네트워크 없음.

검증 대상:
  · google_trends_explore 정책 = optional_enrichment (max_retries_on_429=0)
  · extract_related_candidates 규칙 기반 추출 (영/한, 결정적, seed 제외)
  · explore 429가 optional source failure로만 기록되고 fallback chain을 막지 않음
  · fallback runner JSONL 계약(필수 필드) + body 추출 시도 + LANG_SKIP 비누락
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("INGESTION_RATE_LIMIT_BACKEND", "memory")

from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult
from ingestion.runners import run_trend_fallback_enrichment_audit as tf
from ingestion.runners._audit_common import extract_related_candidates


# ── google_trends_explore 정책 (PHASE 3) ─────────────────────────────────────

def test_google_trends_explore_policy_is_optional_no_retry():
    from ingestion.core.rate_limit_policy import load_rate_limit_policy
    p = load_rate_limit_policy("google_trends_explore")
    assert p.max_retries_on_429 == 0          # 429 무시 연속 재시도 금지
    assert p.min_interval_seconds >= 7200     # 장주기 (optional enrichment)
    assert p.cooldown_on_429_seconds >= 3600  # 장쿨다운


def test_google_trending_now_policy_matches_trends_family():
    from ingestion.core.rate_limit_policy import load_rate_limit_policy
    p = load_rate_limit_policy("google_trending_now")
    assert p.max_retries_on_429 == 0


# ── extract_related_candidates ───────────────────────────────────────────────

_EN_SAMPLES = [
    {"title": "Iran and Israel exchange strikes amid escalating conflict",
     "snippet": "Tehran warns of retaliation as Israel hits nuclear sites"},
    {"title": "Israel strikes Iran nuclear facilities, oil prices surge",
     "snippet": "Brent crude jumps as Iran conflict deepens"},
    {"title": "Oil prices surge after Israel Iran strikes",
     "snippet": "Markets react to Middle East escalation"},
]


def test_related_candidates_min_five_and_excludes_seed():
    rc = extract_related_candidates("iran israel", _EN_SAMPLES)
    assert len(rc) >= 5
    phrases = {r["phrase"].lower() for r in rc}
    assert "iran" not in phrases and "israel" not in phrases  # seed 토큰 제외
    assert "strikes" in phrases  # 3개 문서 공통 → repeated_term
    methods = {r["method"] for r in rc}
    assert "repeated_term" in methods


def test_related_candidates_korean_2gram():
    samples = [
        {"title": "최불암 막걸리 광고 화제", "snippet": "최불암 막걸리 영상 확산"},
        {"title": "막걸리 시장 막걸리 인기 급등", "snippet": "전통 막걸리 수출 증가"},
    ]
    rc = extract_related_candidates("최불암", samples)
    phrases = {r["phrase"] for r in rc}
    assert "막걸리" in phrases       # 2개 문서 공통 한글 run
    assert "최불암" not in phrases   # seed 제외


def test_related_candidates_deterministic():
    a = extract_related_candidates("iran israel", _EN_SAMPLES)
    b = extract_related_candidates("iran israel", _EN_SAMPLES)
    assert a == b  # 정렬 기반 결정적 출력


def test_related_candidates_empty_samples():
    assert extract_related_candidates("seed", []) == []


# ── explore 429 → optional failure, fallback 비차단 ──────────────────────────

def test_explore_429_records_optional_failure_not_block(tmp_path, monkeypatch):
    dom = tmp_path / "dom.html"
    dom.write_text("<title>Error 429 (Too Many Requests)!!1</title>", encoding="utf-8")
    monkeypatch.setattr(tf, "_OUT_ROOT", tmp_path)
    monkeypatch.setattr(tf, "_newest", lambda d, p: dom)
    monkeypatch.setattr(tf, "gate_check", lambda sid, q="": "cooldown_skip")
    monkeypatch.setattr(tf, "in_cooldown", lambda sid, q="": (True, "2026-06-13T10:49:28Z"))

    row = tf.explore_status_row("run1", "iran israel")
    assert row["status"] == "RATE_LIMITED_CONFIRMED"
    assert row["collected"] is False
    assert row["body_status"] == "not_required"
    assert "fallback_chain" in row["next_action"]


# ── fallback runner JSONL 계약 ───────────────────────────────────────────────

_REQUIRED_FIELDS = {
    "run_id", "seed_keyword", "source_id", "fallback_stage", "collected",
    "items_found", "candidates_created", "related_candidates_created",
    "body_extracted", "body_status", "status", "error_category",
    "artifact_path", "next_action",
}


def _fake_result(sid, raw_path):
    return CollectionProbeResult(
        source_id=sid, status="LIVE_SUCCESS", strategy_used="api", items_found=3,
        artifact_paths=ArtifactPaths(raw_payload=str(raw_path)),
        next_action="integrate_into_pipeline",
    )


def _write_payload(tmp_path):
    p = tmp_path / "payload.json"
    p.write_text(json.dumps({"results": [
        {"title": "Global conflict escalates in region",
         "url": "https://news.test/a", "description": "conflict deepens", "date": "2026-06-13"},
        {"title": "Conflict triggers oil prices surge",
         "url": "https://news.test/b", "description": "oil markets react", "date": "2026-06-13"},
        {"title": "Region conflict update on oil supply",
         "url": "https://news.test/c", "description": "supply disrupted", "date": "2026-06-13"},
    ]}, ensure_ascii=False), encoding="utf-8")
    return p


def test_fallback_runner_contract_and_no_block(tmp_path, monkeypatch):
    payload = _write_payload(tmp_path)
    out = tmp_path / "outputs"

    monkeypatch.setattr(tf, "_OUT_ROOT", out)
    monkeypatch.setattr(tf, "force_local_file_backend", lambda: None)
    monkeypatch.setattr(tf, "load_env", lambda: None)
    monkeypatch.setattr(tf, "gate_check", lambda sid, q="": None)
    monkeypatch.setattr(tf, "record_call", lambda sid, q="": None)
    monkeypatch.setattr(tf, "in_cooldown", lambda sid, q="": (False, None))
    monkeypatch.setattr(tf, "run_collection_probe",
                        lambda sid, query=None, max_items=3, **kw: _fake_result(sid, payload))
    monkeypatch.setattr(tf, "_fetch_rss_entries",
                        lambda url, n: [{"title": "Trend term", "link": "https://t.test"}])
    monkeypatch.setattr(tf, "extract_body",
                        lambda sid, s, **kw: {"body_status": "extracted",
                                              "body_artifact_path": str(tmp_path / "b.txt")})
    monkeypatch.setattr(tf, "OUTPUT_JSONL_DIR", tmp_path / "jsonl")
    monkeypatch.setattr(tf, "OUTPUT_REPORTS_DIR", tmp_path / "reports")

    rc = tf.main(["--region", "US", "--seed", "global conflict"])
    assert rc == 0

    jsonl = list((tmp_path / "jsonl").glob("trend_fallback_enrichment_audit_*.jsonl"))[0]
    rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines()]

    # 모든 row가 필수 필드 보유 (orchestration 계약)
    for r in rows:
        assert _REQUIRED_FIELDS <= set(r.keys())

    stages = {r["fallback_stage"] for r in rows}
    assert {"google_trending_now", "trends_export", "news_search", "explore_optional"} <= stages

    # fallback chain이 막히지 않음: collected source ≥2, body 추출 ≥1
    collected = [r for r in rows if r["collected"]]
    assert len(collected) >= 2
    assert any(r["body_extracted"] == 1 for r in rows)

    # stage B export 가용 → EXPORT_AVAILABLE
    b = next(r for r in rows if r["fallback_stage"] == "trends_export")
    assert b["status"] == "EXPORT_AVAILABLE"

    # explore row는 누락되지 않고 optional로 기록(en seed라 cooldown 없음 → 게이트 상태)
    explore = next(r for r in rows if r["source_id"] == "google_trends_explore")
    assert explore["collected"] is False
    assert explore["body_status"] == "not_required"

"""R-GdeltGovernorSplitBrain — host 단위 호출 간격의 단일 출처(HostRateGate) 회귀.

검증(필수 7):
  1) closure(collect_gdelt)/메인루프(run_api_live_probe) 두 *실제 HTTP 경로*가 같은 host gate
     파일을 단일 출처로 공유하는지(독립 인스턴스 = 다른 루프/프로세스)
  2) closure spaced-probe ladder가 host gate로 깨지지 않는지
  3) 메인루프의 실제 HTTP 경로(run_api_live_probe)가 host gate를 통과하는지(spacing 내면 호출 안 함)
  4) GDELT 호출 직전 host last_call_ts가 성공/실패와 무관하게 기록되는지(collect_gdelt + run_api_live_probe)
  5) spacing 경과 이전에는 두 경로 모두 실제 호출하지 않는지
  6) spacing 경과 이후에는 호출 가능한지
  7) 429가 code failure가 아니라 external/provider rate limit으로 분류되는지

네트워크 0: vendor_fetch/governor/host_gate/now 주입 + httpx monkeypatch.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.orchestration.gdelt_strategy import collect_gdelt
from ingestion.orchestration.host_rate_gate import (
    GDELT_HOST,
    HOST_GATED_SOURCES,
    HostRateGate,
)
from ingestion.orchestration.rate_limit_governor import RateLimitGovernor
from ingestion.orchestration.vendor_api_routes import VendorRouteResult
from ingestion.probes.api_probe import run_api_live_probe

_T = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _ok_record():
    return {"record_type": "official_record", "source_id": "gdelt", "title_or_label": "T",
            "source_url_or_evidence": "https://x.test/a", "canonical_url": "https://x.test/a",
            "published_at_or_observed_at": "20260615T100000Z", "body_state_or_signal": "official_record",
            "confirmation_policy": "evidence_required", "quality_pre_gate_decision": "pass"}


def _ok(**kw):
    return VendorRouteResult("gdelt", "gdelt_doc_artlist", True, 200, "official_record",
                             (_ok_record(),), None, 1)


def _rate_limited(**kw):
    return VendorRouteResult("gdelt", "gdelt_doc_artlist", False, 429, "official_record",
                             (), "provider_rate_limited", 0)


def _empty_200(**kw):
    return VendorRouteResult("gdelt", "gdelt_doc_artlist", False, 200, "official_record",
                             (), "http_200_no_articles", 0)


# ── 1) 두 실제 HTTP 경로가 같은 host gate 파일 공유(독립 인스턴스) ───────────────
def test_shared_host_gate_visible_across_independent_instances(tmp_path):
    p = tmp_path / "host_gate.json"
    a = HostRateGate(state_path=p)
    ts = a.record_call(GDELT_HOST, now=_T)
    b = HostRateGate(state_path=p)             # 독립 인스턴스 = 다른 루프/프로세스 모사
    assert b.last_call_at(GDELT_HOST) == ts
    assert b.decide(GDELT_HOST, min_spacing_seconds=10, now=_T + timedelta(seconds=5)).allowed is False
    assert b.decide(GDELT_HOST, min_spacing_seconds=10, now=_T + timedelta(seconds=15)).allowed is True
    ts2 = b.record_call(GDELT_HOST, now=_T + timedelta(seconds=20))
    assert a.last_call_at(GDELT_HOST) == ts2   # 양방향(cross-process 단일 출처)


# ── 2) closure spaced-probe ladder 안 깨짐 ──────────────────────────────────────
def test_host_gate_does_not_break_closure_spaced_probe_ladder(tmp_path):
    gate = HostRateGate(state_path=tmp_path / "hg.json")
    seq = {"n": 0}

    def vf(**kw):
        seq["n"] += 1
        return _empty_200()

    r = collect_gdelt(governor=RateLimitGovernor(), vendor_fetch=vf, max_probes=3, now=_T,
                      sleep=lambda s: None, host_gate=gate, host=GDELT_HOST, host_min_spacing_seconds=10)
    assert seq["n"] == 3 and r.attempts == ("broad", "single_keyword", "narrow")
    assert r.final_status == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
    assert gate.last_call_at(GDELT_HOST) is not None


# ── 3) 메인루프 실제 HTTP 경로(run_api_live_probe)가 host gate 통과(spacing 내 차단) ─
def test_api_live_probe_blocks_gdelt_when_host_recently_called(tmp_path, monkeypatch):
    gate = HostRateGate(state_path=tmp_path / "hg.json")
    gate.record_call(GDELT_HOST)               # 방금(real now) 다른 루프가 호스트를 침

    # httpx가 호출되면 실패하도록(네트워크 0 보장 — gate가 막으면 httpx 도달 불가)
    import httpx

    def _boom(*a, **k):
        raise AssertionError("httpx must NOT be called when host gate blocks")

    monkeypatch.setattr(httpx, "Client", _boom)
    res = run_api_live_probe("gdelt", host_gate=gate)
    assert res.status == "RATE_LIMITED"
    assert res.error_category == "HOST_RATE_LIMIT"
    assert not res.artifact_paths.get("raw_payload")


# ── 4) 호출 직전 host last_call_ts: 성공/실패 무관 기록(양 경로) ─────────────────
def test_host_last_call_recorded_regardless_of_outcome(tmp_path):
    # closure 경로 — 성공
    g1 = HostRateGate(state_path=tmp_path / "s.json")
    collect_gdelt(governor=RateLimitGovernor(), vendor_fetch=_ok, now=_T, sleep=lambda s: None,
                  host_gate=g1, host_min_spacing_seconds=10)
    assert g1.last_call_at(GDELT_HOST) is not None
    # closure 경로 — 429(실패)여도 호출 직전 기록
    g2 = HostRateGate(state_path=tmp_path / "f.json")
    collect_gdelt(governor=RateLimitGovernor(), vendor_fetch=_rate_limited, now=_T, sleep=lambda s: None,
                  host_gate=g2, host_min_spacing_seconds=10)
    assert g2.last_call_at(GDELT_HOST) is not None


def test_api_live_probe_records_host_before_http_even_on_error(tmp_path, monkeypatch):
    # 메인루프 실제 HTTP 경로 — gate 통과 후 호출 직전 기록(HTTP가 실패해도 기록은 남음)
    gate = HostRateGate(state_path=tmp_path / "hg.json")   # fresh → 허용
    import httpx

    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "Client", _boom)
    res = run_api_live_probe("gdelt", host_gate=gate)
    assert res.status in ("NETWORK_ERROR", "TIMEOUT")       # HTTP 실패
    assert gate.last_call_at(GDELT_HOST) is not None        # 그래도 호출 직전 host 기록됨


# ── 5) spacing 경과 이전: 두 경로 모두 실제 호출 안 함(같은 파일 공유) ───────────
def test_both_paths_skip_call_before_spacing_elapsed(tmp_path, monkeypatch):
    gate_file = tmp_path / "hg.json"
    # closure 경로가 (real now) 호스트를 친다 → 같은 파일에 기록
    g_close = HostRateGate(state_path=gate_file)
    called = {"n": 0}

    def vf(**kw):
        called["n"] += 1
        return _ok()

    collect_gdelt(governor=RateLimitGovernor(), vendor_fetch=vf, sleep=lambda s: None,
                  host_gate=g_close, host=GDELT_HOST, host_min_spacing_seconds=10)
    assert called["n"] == 1                                  # closure는 1회 호출

    # 메인루프 실제 HTTP 경로가 같은 파일을 보고 spacing 내라 호출 안 함
    import httpx

    def _boom(*a, **k):
        raise AssertionError("host gate must block the main-loop HTTP within spacing")

    monkeypatch.setattr(httpx, "Client", _boom)
    res = run_api_live_probe("gdelt", host_gate=HostRateGate(state_path=gate_file))
    assert res.status == "RATE_LIMITED" and res.error_category == "HOST_RATE_LIMIT"


# ── 6) spacing 경과 이후: host gate가 호출을 허용 ───────────────────────────────
def test_host_gate_allows_after_spacing_elapsed(tmp_path):
    gate = HostRateGate(state_path=tmp_path / "hg.json")
    gate.record_call(GDELT_HOST, now=_T)
    # spacing(10s) 경과 후 → 허용
    assert gate.decide(GDELT_HOST, min_spacing_seconds=10, now=_T + timedelta(seconds=15)).allowed is True
    # closure 경로도 경과 후 정상 호출
    called = {"n": 0}

    def vf(**kw):
        called["n"] += 1
        return _ok()

    r = collect_gdelt(governor=RateLimitGovernor(), vendor_fetch=vf, now=_T + timedelta(seconds=15),
                      sleep=lambda s: None, host_gate=gate, host_min_spacing_seconds=10)
    assert called["n"] >= 1 and r.success


# ── 7) 429 = external/provider rate limit (code failure 아님) ────────────────────
def test_429_with_host_gate_is_provider_rate_limit_not_failure(tmp_path):
    gate = HostRateGate(state_path=tmp_path / "hg.json")
    gov = RateLimitGovernor()
    r = collect_gdelt(governor=gov, vendor_fetch=_rate_limited, now=_T, sleep=lambda s: None,
                      host_gate=gate, host_min_spacing_seconds=10)
    assert r.success is False
    assert r.error == "provider_rate_limited"
    assert r.final_status == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
    assert r.status_code == 429
    assert gate.last_call_at(GDELT_HOST) is not None
    assert gov.cooldown_until("gdelt") == r.cooldown_until


def test_host_gated_sources_registry_contains_gdelt():
    assert "gdelt" in HOST_GATED_SOURCES
    host, spacing = HOST_GATED_SOURCES["gdelt"]
    assert host == GDELT_HOST and spacing >= 5     # 제공자 "5초당 1회"보다 보수적

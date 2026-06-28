"""ADR#64 — cross-source live overlap smoke tests (2nd publishable provider + cross-source near-match queue).

§10 시나리오 잠금(ADR#62/#63 가 잠근 adapter/queue/secret 회귀는 test_provider_query_adapters/test_guardian_live_query_smoke
가 유지; NYT adapter 1-10 은 test_provider_query_adapters Section D). 이 파일은 ADR#64 net-new 를 잠근다:
  - cross-source smoke(11-29): opt-in off 기본·provider_b 미배선/credential 부재 분기·**둘 다 성공만 cross-source**
    (single-source 둔갑 금지)·records 결합·cross_source_pair_count·no_cross_source_overlap/no_title_overlap/
    no_near_match 분해·near→queue 충원·predicted_status 숨김·live_derived 둔갑 0.
  - secret boundary(30-37): `.env` 미열람·값 숨김·이름 노출·report/URL/exception 미노출(real-network httpx monkeypatch).
  - agent contract(38-43): cross-source provider readiness·no secret fabrication·no_merge·embedding/LLM No-Go.
network 0(transport_a/transport_b/env_probe_fn/host_gate 주입). 실 `.env` 미접촉(probe 주입).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx

import backend.app.tools.cross_source_live_overlap_smoke as _cs
from backend.app.tools.cross_source_live_overlap_smoke import (
    main,
    run_cross_source_live_overlap_smoke,
)
from backend.app.tools.provider_query_adapters import ADAPTER_WIRED_PROVIDERS
from backend.app.tools.provider_readiness import (
    build_provider_readiness_agent_schema,
    build_provider_readiness_report,
    run_optional_live_query,
)

WIRE = "Federal Reserve raises benchmark interest rate by quarter point"
PARA = "Federal Reserve raises benchmark interest rate by 25 basis points"
DIFF = "Federal Reserve official comments on interest rate policy outlook"
UNREL = "Volcano erupts in Iceland forcing thousands of coastal evacuations"
DAY = "2026-06-22"

# 테스트용 가짜 key — report/URL/log 어디에도 나오면 안 됨(secret 경계 단언용 sentinel).
_SENTINEL = "ZZZ_FAKE_CROSS_KEY_must_never_appear_64"

_REQUIRED_OUTPUT_KEYS = frozenset({
    "smoke_name", "providers", "provider_a", "provider_b", "topic", "time_window",
    "live_query_requested", "live_query_attempted", "credential_status_by_provider",
    "credential_value_exposed", "env_file_read", "provider_status_by_provider",
    "host_gate_status_by_provider", "rate_limit_status_by_provider", "records_count_by_provider",
    "combined_records_count", "cross_source_pair_count", "fingerprint_overlap_count",
    "near_match_count", "hard_negative_count", "reviewer_queue_population_count",
    "labeler_prediction_hidden", "dataset_source_by_provider", "dataset_source", "provenance",
    "block_reasons", "next_actions", "production_gold_count", "merge_allowed",
    "no_merge_without_gold", "no_public_intelligence_unit", "llm_invoked", "db_write",
})


def _g_payload(items, day=DAY):
    return json.dumps({"response": {"status": "ok", "total": len(items), "results": [
        {"webTitle": t, "webUrl": u, "webPublicationDate": day + "T12:00:00Z"} for t, u in items]}})


def _n_payload(items, day=DAY):
    return json.dumps({"status": "OK", "response": {"docs": [
        {"headline": {"main": t}, "web_url": u, "pub_date": day + "T13:00:00+0000"} for t, u in items]}})


def _guardian_tr(_url):
    return _g_payload([(WIRE, "https://g.test/a"), (PARA, "https://g.test/b")])


def _nyt_tr(_url):
    return _n_payload([(WIRE, "https://nyt.test/a"), (DIFF, "https://nyt.test/b")])


def _nyt_empty_tr(_url):
    return _n_payload([])


def _boom_transport(*_a, **_k):
    raise AssertionError("transport must NOT be called when opt-in off or credential missing")


def _probe(present, file_present=True, declared=True):
    return lambda v: {"var_name": v, "credential_present": present,
                      "env_file_present": file_present, "declared_in_example": declared}


def _both_ok(**kw):
    """양 provider 성공(cross-source) 기본 호출 — near 1·hard 2·fingerprint 1·queue 3."""
    return run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=_guardian_tr, transport_b=_nyt_tr, **kw)


# ── ADR#83: today(절대 윈도우 anchor) 스레딩 — date-pin 이 실제 provider 쿼리 URL 에 반영 ─────────────────────
def test_today_anchor_threads_absolute_window_into_provider_query_url():
    """today=D+1 + time_window=1d → provider 쿼리 URL 의 날짜 범위가 [D, D+1](절대). today 미주입 시 기존 동작 보존."""
    cap: list[str] = []

    def _cap_g(url):
        cap.append(url)
        return _g_payload([(WIRE, "https://g.test/a")])

    def _cap_n(url):
        cap.append(url)
        return _n_payload([(WIRE, "https://nyt.test/a")])

    out = run_cross_source_live_overlap_smoke(
        live_query=True, today="2026-06-18", time_window="1d",
        env_status_fn=lambda ks: {k: "present" for k in ks}, env_probe_fn=_probe(True),
        transport_a=_cap_g, transport_b=_cap_n)
    assert out["live_query_attempted"] is True
    # Guardian from-date/to-date + NYT begin_date/end_date 가 [2026-06-17, 2026-06-18].
    assert any("2026-06-17" in u and "2026-06-18" in u for u in cap), cap
    # NYT date 형식 YYYYMMDD 도 확인(20260617/20260618).
    assert any("20260617" in u and "20260618" in u for u in cap), cap


# ── cross-source smoke (11-29) ───────────────────────────────────────────────────────────────────────
def test_01_output_contract_complete():
    """§4 필수 output key 전부 존재(계약 완전성)."""
    r = run_cross_source_live_overlap_smoke(env_probe_fn=_probe(False, False))
    assert _REQUIRED_OUTPUT_KEYS <= set(r)
    assert r["smoke_name"] == "cross_source_live_overlap"
    assert r["provider_a"] == "guardian" and r["provider_b"] == "nyt"


def test_02_disabled_by_default():
    """기본 live_query=False → 시도 0(not_opted_in)·transport 미호출."""
    r = run_cross_source_live_overlap_smoke(
        env_probe_fn=_probe(True), transport_a=_boom_transport, transport_b=_boom_transport)
    assert r["live_query_requested"] is False and r["live_query_attempted"] is False
    assert r["block_reasons"] == ["not_opted_in"]


def test_03_requires_explicit_opt_in():
    """opt-in flag 없이는 credential present 여도 fetch 안 함."""
    r = run_cross_source_live_overlap_smoke(
        live_query=False, env_probe_fn=_probe(True),
        transport_a=_boom_transport, transport_b=_boom_transport)
    assert r["live_query_attempted"] is False


def test_04_provider_b_not_selected_when_unwired():
    """provider_b 가 미배선 adapter → provider_b_not_selected(fetch 0)."""
    r = run_cross_source_live_overlap_smoke(
        live_query=True, provider_b="newsapi", env_probe_fn=_probe(True),
        transport_a=_boom_transport, transport_b=_boom_transport)
    assert r["block_reasons"] == ["provider_b_not_selected"]
    assert r["live_query_attempted"] is False


def test_05_provider_b_env_not_loaded_blocks_before_network():
    """`.env` 파일 부재 → env_not_loaded(per-provider·network 전·transport 미호출)."""
    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(False, file_present=False),
        transport_a=_boom_transport, transport_b=_boom_transport)
    assert "env_not_loaded:guardian" in r["block_reasons"]
    assert "env_not_loaded:nyt" in r["block_reasons"]
    assert r["live_query_attempted"] is False
    assert any("create .env" in a for a in r["next_actions"])


def test_06_missing_credentials_distinct_from_env_not_loaded():
    """`.env` 존재·키 부재 → missing_credentials(env_not_loaded 와 구분·network 전)."""
    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(False, file_present=True),
        transport_a=_boom_transport, transport_b=_boom_transport)
    assert "missing_credentials:guardian" in r["block_reasons"]
    assert "missing_credentials:nyt" in r["block_reasons"]
    assert any("NYT_API_KEY" in a for a in r["next_actions"])


def test_07_guardian_only_success_not_cross_source():
    """provider_a(guardian) 성공·provider_b 0건 → single-source success 둔갑 금지(no_records_provider_b·queue 0)."""
    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=_guardian_tr, transport_b=_nyt_empty_tr)
    assert r["provider_status_by_provider"]["guardian"] == "ok"
    assert "no_records_provider_b" in r["block_reasons"]
    assert r["live_query_attempted"] is False and r["reviewer_queue_population_count"] == 0


def test_08_provider_b_only_success_not_cross_source():
    """provider_b 성공·provider_a 0건 → cross-source 미인정(no_records_provider_a·queue 0)."""
    def g_empty(_u):
        return _g_payload([])

    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=g_empty, transport_b=_nyt_tr)
    assert "no_records_provider_a" in r["block_reasons"]
    assert r["live_query_attempted"] is False and r["reviewer_queue_population_count"] == 0


def test_09_both_succeed_records_combine():
    """둘 다 성공 → records 결합(provider 별 카운트 보존)."""
    r = _both_ok()
    assert r["records_count_by_provider"] == {"guardian": 2, "nyt": 2}
    assert r["combined_records_count"] == 4
    assert r["live_query_attempted"] is True


def test_10_cross_source_pair_count_reported():
    """cross_source_pair_count = publishable·cross-URL·same-date cross-source pair(guardian×nyt=4)."""
    r = _both_ok()
    assert r["cross_source_pair_count"] == 4


def test_11_cross_source_near_match_populates_queue():
    """cross-source near/hard/fingerprint 분류 + near→reviewer queue 충원(같은 사건 단정 0)."""
    r = _both_ok()
    assert r["fingerprint_overlap_count"] == 1   # g:WIRE × n:WIRE(정확 token-set).
    assert r["near_match_count"] == 1            # g:PARA × n:WIRE(paraphrase·adjudicator-zone).
    assert r["hard_negative_count"] == 2         # WIRE/PARA × DIFF(different-event lean).
    assert r["reviewer_queue_population_count"] == 3   # near+hard distinct pair.
    assert not r["block_reasons"]


def test_12_no_cross_source_overlap_when_dates_disjoint():
    """records 는 있으나 cross-source same-date pair 0 → no_cross_source_overlap(정직)."""
    def g_d1(_u):
        return _g_payload([(WIRE, "https://g.test/a"), (PARA, "https://g.test/b")], day="2026-06-22")

    def n_d2(_u):
        return _n_payload([(WIRE, "https://nyt.test/a")], day="2026-06-10")

    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=g_d1, transport_b=n_d2)
    assert r["combined_records_count"] == 3 and r["cross_source_pair_count"] == 0
    assert "no_cross_source_overlap" in r["block_reasons"]
    assert r["dataset_source"] == "live_derived"   # 실 records — 둔갑 0(후보만 0).


def test_13_no_title_overlap_when_cross_pair_below_floor():
    """cross-source pair 는 있으나 제목 token overlap < floor → no_title_overlap."""
    def g_one(_u):
        return _g_payload([(WIRE, "https://g.test/a")])

    def n_unrel(_u):
        return _n_payload([(UNREL, "https://nyt.test/a")])

    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=g_one, transport_b=n_unrel)
    assert r["cross_source_pair_count"] == 1
    assert r["near_match_count"] == 0 and r["hard_negative_count"] == 0
    assert r["fingerprint_overlap_count"] == 0
    assert "no_title_overlap" in r["block_reasons"]


def test_14_no_near_match_when_only_fingerprint():
    """cross-source 가 fingerprint(정확일치)만·near-positive 0 → no_near_match(queue 0)."""
    def g_one(_u):
        return _g_payload([(WIRE, "https://g.test/a")])

    def n_one(_u):
        return _n_payload([(WIRE, "https://nyt.test/a")])

    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=g_one, transport_b=n_one)
    assert r["cross_source_pair_count"] == 1 and r["fingerprint_overlap_count"] == 1
    assert r["near_match_count"] == 0
    assert "no_near_match" in r["block_reasons"]
    assert r["reviewer_queue_population_count"] == 0


def test_15_dataset_source_live_derived_only_for_real_records():
    """실 records 일 때만 dataset_source=live_derived; blocked 면 None(fixture 둔갑 0)."""
    ok = _both_ok()
    assert ok["dataset_source"] == "live_derived" and ok["provenance"] == "live_derived"
    blocked = run_cross_source_live_overlap_smoke(live_query=True, env_probe_fn=_probe(False, True))
    assert blocked["dataset_source"] is None and blocked["provenance"] == "none"
    assert all(v is None for v in blocked["dataset_source_by_provider"].values())


def test_16_per_provider_dataset_source_reflects_status():
    """provider 별 dataset_source: ok→live_derived·실패→None."""
    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=_guardian_tr, transport_b=_nyt_empty_tr)
    assert r["dataset_source_by_provider"]["guardian"] == "live_derived"
    assert r["dataset_source_by_provider"]["nyt"] is None


def test_17_predicted_status_hidden():
    """reviewer queue 충원 시 labeler prediction 숨김(predicted_status/verdict 미노출)."""
    r = _both_ok()
    assert r["labeler_prediction_hidden"] is True


def test_18_no_merge_no_llm_no_db_invariants():
    """모든 경로: production_gold 0·merge_allowed False·db_write False·llm_invoked False·no public IU."""
    for r in (_both_ok(), run_cross_source_live_overlap_smoke(env_probe_fn=_probe(False, False))):
        assert r["production_gold_count"] == 0 and r["merge_allowed"] is False
        assert r["db_write"] is False and r["llm_invoked"] is False
        assert r["no_merge_without_gold"] is True and r["no_public_intelligence_unit"] is True


def test_19_host_gate_blocked_classified():
    """host gate 차단 시 provider host_gate_status=blocked·cross-source 미성립."""
    gate = SimpleNamespace(
        decide=lambda *a, **k: SimpleNamespace(allowed=False, reason="host_min_spacing_not_elapsed"),
        record_call=lambda *a, **k: None)
    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=_guardian_tr, transport_b=_nyt_tr,
        host_gate=gate)
    assert r["host_gate_status_by_provider"]["guardian"] == "blocked"
    assert "host_gate_blocked" in r["block_reasons"]
    assert r["reviewer_queue_population_count"] == 0


# ── secret boundary (30-37) ──────────────────────────────────────────────────────────────────────────
def test_20_env_file_read_invariant_false():
    """smoke 는 `.env` 값을 report 로 미노출(env_file_read·credential_value_exposed 불변 False)."""
    r = run_cross_source_live_overlap_smoke(env_probe_fn=_probe(False, False))
    assert r["env_file_read"] is False and r["credential_value_exposed"] is False


def test_21_credential_value_exposed_false_all_paths():
    """credential_value_exposed/env_file_read 는 모든 경로에서 False 불변."""
    cases = [
        run_cross_source_live_overlap_smoke(env_probe_fn=_probe(False, False)),
        run_cross_source_live_overlap_smoke(live_query=True, env_probe_fn=_probe(False, True)),
        _both_ok(),
    ]
    for r in cases:
        assert r["credential_value_exposed"] is False and r["env_file_read"] is False


def test_22_secret_value_never_in_report(monkeypatch):
    """실 SENTINEL 값을 os.environ 에 주입해도 report 어디에도 없음(값 금지·이름 허용)."""
    monkeypatch.setenv("GUARDIAN_API_KEY", _SENTINEL)
    monkeypatch.setenv("NYT_API_KEY", _SENTINEL)
    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True),
        env_status_fn=lambda keys: {k: "present" for k in keys},
        transport_a=_guardian_tr, transport_b=_nyt_tr)
    assert _SENTINEL not in json.dumps(r, ensure_ascii=False)


def test_23_real_network_secret_only_in_params(monkeypatch):
    """실 network 분기(transport=None)를 httpx monkeypatch 로 타서 양 provider key 가 **params 전용**·URL/report 미노출 실증.

    (fake-transport sentinel 은 os.getenv 경로 미경유 near-tautology — 이 테스트가 real-network 분기[run_provider_query]를
    결정론으로 직접 커버. network 0[httpx 가짜]·실 `.env` 미접촉[probe/env_status 주입].)"""
    monkeypatch.setenv("GUARDIAN_API_KEY", _SENTINEL)
    monkeypatch.setenv("NYT_API_KEY", _SENTINEL)
    calls: list = []

    def _fake_get(url, params=None, **_kw):
        calls.append({"url": url, "params": params})
        body = _nyt_tr(url) if "nytimes" in url else _guardian_tr(url)
        return SimpleNamespace(status_code=200, headers={"content-type": "application/json"}, text=body)

    monkeypatch.setattr(httpx, "get", _fake_get)
    gate = SimpleNamespace(decide=lambda *a, **k: SimpleNamespace(allowed=True, reason=None),
                           record_call=lambda *a, **k: None)
    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True),
        env_status_fn=lambda keys: {k: "present" for k in keys}, host_gate=gate)
    assert len(calls) == 2
    for c in calls:
        assert c["params"] == {"api-key": _SENTINEL}      # key 는 params 전용.
        assert _SENTINEL not in c["url"] and "api-key" not in c["url"]   # URL 은 keyless.
    assert _SENTINEL not in json.dumps(r, ensure_ascii=False)
    assert r["dataset_source"] == "live_derived" and r["combined_records_count"] == 4


def test_24_secret_not_in_block_reasons_or_next_actions(monkeypatch):
    """block_reasons/next_actions 에 실 값이 섞이지 않는다(missing 안내에도 이름만)."""
    monkeypatch.setenv("NYT_API_KEY", _SENTINEL)
    r = run_cross_source_live_overlap_smoke(live_query=True, env_probe_fn=_probe(False, True))
    assert _SENTINEL not in json.dumps(r["block_reasons"]) + json.dumps(r["next_actions"])


def test_25_env_var_names_visible_values_hidden():
    """env var 이름은 next_action 에 노출(agent 가 무엇을 설정할지 알 수 있어야)·값은 미노출."""
    r = run_cross_source_live_overlap_smoke(live_query=True, env_probe_fn=_probe(False, True))
    blob = json.dumps(r, ensure_ascii=False)
    assert "GUARDIAN_API_KEY" in blob and "NYT_API_KEY" in blob


# ── agent contract (38-43) ───────────────────────────────────────────────────────────────────────────
def test_26_provider_readiness_includes_nyt_wired():
    """provider readiness: nyt 가 adapter-wired·fetch_implemented True·key_required(credential 따라 ready/missing)."""
    readiness = build_provider_readiness_report(
        env_status_fn=lambda keys: {k: "present" for k in keys})
    nyt = next(r for r in readiness["providers"] if r["provider_id"] == "nyt")
    assert nyt["fetch_implemented"] is True and nyt["queue_integration_status"] == "wired"
    assert "nyt" in readiness["adapter_wired_providers"]
    assert "nyt" in ADAPTER_WIRED_PROVIDERS


def test_27_agent_schema_secret_safe_and_no_go():
    """Agent schema: no_secret_fabrication·no_merge_without_gate·embedding/LLM No-Go·cross-source provider readiness."""
    readiness = build_provider_readiness_report(
        env_status_fn=lambda keys: {k: "present" for k in keys})
    live = run_optional_live_query(provider="nyt", live_query=False, readiness=readiness)
    schema = build_provider_readiness_agent_schema(readiness, live)
    assert schema["no_secret_fabrication"] is True and schema["no_merge_without_gate"] is True
    assert schema["llm_invoked"] is False
    assert schema["embedding_llm_adjudicator"]["status"].lower().startswith("no")
    assert "provider secret 추측/생성" in schema["agent_cannot"]
    assert "nyt" in schema["wired_providers"]


def test_28_nyt_single_provider_live_query_also_wired():
    """NYT 단일 provider 도 ADR#60 운영경로로 동작(adapter wired·records= 주입·둔갑 0)."""
    def n_tr(_u):
        return _n_payload([(WIRE, "https://nyt.test/a"), (PARA, "https://nyt.test/b"),
                           (DIFF, "https://nyt.test/c")])

    live = run_optional_live_query(
        provider="nyt", live_query=True, provider_transport=n_tr,
        env_status_fn=lambda keys: {k: "present" for k in keys},
        readiness=build_provider_readiness_report(
            env_status_fn=lambda keys: {k: "present" for k in keys}))
    assert live["live_query_attempted"] is True
    assert live["dataset_source"] == "live_derived"
    assert live["merge_allowed"] is False and live["llm_invoked"] is False


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────────
def test_29_cli_default_no_network_returns_zero(capsys, monkeypatch):
    """CLI 기본(no --live-query) → exit 0·값 미출력·시도 0. (probe 스텁→실 `.env` 미접촉·hermetic)"""
    monkeypatch.setattr(_cs, "_default_env_probe", lambda v: _probe(False, True)(v))
    rc = main(["--topic", "test topic"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "requested=False" in out and "attempted=False" in out
    assert _SENTINEL not in out


def test_30_cli_json_output_secret_free(monkeypatch, capsys):
    """CLI --json: §4 report JSON·credential value 미출력(이름만). (probe 스텁→실 `.env` 미접촉·hermetic)"""
    monkeypatch.setattr(_cs, "_default_env_probe", lambda v: _probe(False, True)(v))
    rc = main(["--json"])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["smoke_name"] == "cross_source_live_overlap"
    assert parsed["credential_value_exposed"] is False


# ── ADR#65 semantic scoring wiring (additive·기본 off=ADR#64 동작 보존) ───────────────────────────────
def test_31_semantic_scoring_off_by_default_preserves_adr64():
    """semantic_scoring 미지정 → semantic_scoring None·requested False(커밋 ADR#64 동작 보존)."""
    r = _both_ok()
    assert r["semantic_scoring_requested"] is False
    assert r["semantic_scoring"] is None


def test_32_semantic_scoring_wired_when_opt_in():
    """semantic_scoring=True + 양 provider ok → scorer 결과 부착(병합 0·LLM 0·embedding 실호출 0·score 숨김)."""
    r = _both_ok(semantic_scoring=True)
    assert r["semantic_scoring_requested"] is True
    s = r["semantic_scoring"]
    assert s is not None
    assert s["scorer_mode"] == "deterministic_scaffold"
    assert s["input_pair_count"] >= 1            # cross-source candidate pair 가 scorer 입력으로 들어감.
    assert s["merge_allowed"] is False and s["production_gold_count"] == 0
    assert s["llm_invoked"] is False and s["embedding_invoked"] is False
    assert s["labeler_prediction_hidden"] is True and s["score_hidden_from_labeler"] is True


def test_33_semantic_scoring_skipped_when_single_provider():
    """provider_b 실패(single-source) → cross-source 미인정 → semantic_scoring None(둔갑 0)."""
    r = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=_guardian_tr,
        transport_b=_nyt_empty_tr, semantic_scoring=True)
    assert r["semantic_scoring"] is None
    assert "no_records_provider_b" in r["block_reasons"]


def test_34_reviewer_queue_exposed_only_for_live_records():
    """ADR#76 additive: reviewer_queue 는 둘 다 ok(live_derived)일 때만 dict; 아니면 None(production freeze 소비용)."""
    not_opted = run_cross_source_live_overlap_smoke(live_query=False)
    assert "reviewer_queue" in not_opted          # 키 항상 존재(계약 안정).
    assert not_opted["reviewer_queue"] is None     # 시도 0 → 후보 worklist 없음.
    ok = _both_ok()
    assert isinstance(ok["reviewer_queue"], dict)
    assert ok["reviewer_queue"].get("packet_rows")  # live 후보 worklist 소비 가능.


def test_35_band_diagnostic_default_none_additive():
    """ADR#78 additive: band_diagnostic 키 항상 존재·기본 None(emit_band_diagnostic 미지정·기존 계약 보존)."""
    out = _both_ok()
    assert "band_diagnostic" in out
    assert out["band_diagnostic"] is None
    # not_opted 도 None.
    assert run_cross_source_live_overlap_smoke(live_query=False)["band_diagnostic"] is None


def test_36_band_diagnostic_emitted_body_free():
    """ADR#78: emit_band_diagnostic=True → band 분포·max Jaccard·공유 토큰 샘플(제목 전문/secret 0)."""
    out = _both_ok(emit_band_diagnostic=True)
    bd = out["band_diagnostic"]
    assert isinstance(bd, dict)
    # WIRE 가 양 provider 에 → fingerprint cross 쌍 ≥1(검출 band).
    assert bd["band_distribution"]["fingerprint"] >= 1
    assert bd["near_floor"] == 0.5 and bd["hard_floor"] == 0.2
    assert bd["raw_body_stored"] is False and bd["same_event_truth_asserted"] is False
    # 샘플은 공유 정규화 토큰만(제목 전문 미노출) — secret sentinel 부재.
    blob = json.dumps(bd, ensure_ascii=False)
    assert _SENTINEL not in blob
    for s in bd["top_below_floor_samples"]:
        assert set(s.keys()) >= {"shared_tokens", "title_token_jaccard", "source_role_left"}
        assert "title_left" not in s and "body" not in s   # 제목 전문/본문 키 부재.


# ── ADR#80: live cross-source pair recall probe (37-40) ──────────────────────────────────────────────────
def _g_lift(_url):
    return _g_payload([("Fed raises rates again", "https://g.test/fed")])


def _n_lift(_url):
    return _n_payload([("Federal Reserve lifts interest rates", "https://nyt.test/fed")])


def test_37_recall_probe_diagnostic_off_by_default():
    """emit_recall_probe 기본 off → recall_probe_diagnostic None(ADR#64/#78 동작 보존)."""
    out = _both_ok()
    assert "recall_probe_diagnostic" in out
    assert out["recall_probe_diagnostic"] is None
    # opt-in off + emit_recall_probe 여도 live pair 부재 → None(정직).
    assert run_cross_source_live_overlap_smoke(live_query=False, emit_recall_probe=True)["recall_probe_diagnostic"] is None


def test_38_recall_probe_lifts_below_floor_live_pair():
    """ADR#80: emit_recall_probe=True → below-floor cross-source live pair 를 reviewer-routing 으로 lift(entity 공유)."""
    out = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=_g_lift, transport_b=_n_lift,
        emit_band_diagnostic=True, emit_recall_probe=True)
    rp = out["recall_probe_diagnostic"]
    assert isinstance(rp, dict)
    assert rp["candidate_pair_count"] >= 1
    assert rp["pairs_newly_routed_by_probe"] >= 1            # baseline<0.2 → 정규화 후 routing floor 넘김.
    assert rp["pairs_newly_routed_sharing_entity"] >= 1      # federalreserve(fed≡federal reserve) 공유.
    assert rp["max_recall_probe_score"] >= 0.2


def test_39_recall_probe_never_merge_or_same_event():
    """ADR#80 불변: recall probe lift 가 있어도 merge/same_event 0(reviewer-routing only)."""
    out = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=_g_lift, transport_b=_n_lift,
        emit_recall_probe=True)
    rp = out["recall_probe_diagnostic"]
    assert rp["merge_allowed"] is False
    assert rp["recall_probe_applies_to_merge"] is False
    assert rp["same_event_asserted"] is False
    assert rp["score_exposed_to_reviewer"] is False and rp["score_exposed_to_public"] is False
    assert out["merge_allowed"] is False                     # smoke 자체도 merge 0.


def test_40_recall_probe_diagnostic_body_free():
    """ADR#80: recall_probe_diagnostic 는 제목 전문/secret/exact-score 키 미노출(공유 정규화 토큰·feature 만)."""
    out = run_cross_source_live_overlap_smoke(
        live_query=True, env_probe_fn=_probe(True), transport_a=_g_lift, transport_b=_n_lift,
        emit_recall_probe=True)
    blob = json.dumps(out["recall_probe_diagnostic"], ensure_ascii=False)
    assert _SENTINEL not in blob
    assert '"score":' not in blob              # exact forbidden key 부재(recall_probe_score 는 별 키·통과).
    for s in out["recall_probe_diagnostic"]["top_lift_samples"]:
        assert "title_left" not in s and "body" not in s and "raw_body" not in s

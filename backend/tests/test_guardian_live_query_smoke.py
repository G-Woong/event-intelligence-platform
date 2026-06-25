"""ADR#63 — secret-safe Guardian live query smoke + live-derived near-match queue population tests.

§10 시나리오 잠금(ADR#62 가 이미 잠근 adapter/queue/agent 회귀는 test_provider_query_adapters/test_provider_readiness 가
유지). 이 파일은 ADR#63 net-new 를 잠근다:
  - secret boundary(1-8): `.env` 미열람(env_file_read 불변)·`.env.example` 이름만·값 숨김·이름 노출·값 미노출.
  - guardian live smoke(9-19): opt-in 기본 off·credential 부재 network 전 차단(env_not_loaded vs missing_credentials)
    ·fake transport 성공·no_records/no_overlap/network_error 분류.
  - queue integration(20-30): live records→records= path→live_derived·near/hard/queue 충원·production_gold 0·merge False·db_write False.
  - agent contract(31-36): no secret fabrication·no `.env` read·no_merge_without_gate·embedding/LLM No-Go.
network 0(provider_transport/env_probe_fn/host_gate 주입). 실 `.env` 미접촉(probe 주입 또는 tmp path).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx

import backend.app.tools.guardian_live_query_smoke as _glq
from backend.app.tools.guardian_live_query_smoke import (
    main,
    run_guardian_live_query_smoke,
)
from backend.app.tools.provider_readiness import (
    build_provider_readiness_agent_schema,
    build_provider_readiness_report,
)
from ingestion.core.env_loader import env_example_declares, probe_env_var

WIRE = "Federal Reserve raises benchmark interest rate by quarter point"
PARA = "Federal Reserve raises benchmark interest rate by 25 basis points"
DIFF = "Federal Reserve official comments on interest rate policy outlook"

# 테스트용 가짜 key — report/URL/log 어디에도 나오면 안 됨(secret 경계 단언용 sentinel).
_SENTINEL = "ZZZ_FAKE_GUARDIAN_KEY_must_never_appear_42"

_REQUIRED_OUTPUT_KEYS = frozenset({
    "smoke_name", "live_query_requested", "live_query_attempted", "env_var_name",
    "credential_present", "credential_value_exposed", "env_file_read", "env_example_checked",
    "provider_status", "host_gate_status", "rate_limit_status", "records_count",
    "candidate_count", "near_match_count", "hard_negative_count", "fingerprint_overlap_count",
    "reviewer_queue_population_count",
    "dataset_source", "provenance", "block_reasons", "next_actions", "production_gold_count",
    "merge_allowed", "no_merge_without_gold", "no_public_intelligence_unit", "llm_invoked", "db_write",
})


def _payload(results):
    return json.dumps({"response": {"status": "ok", "total": len(results), "results": results}})


def _wire_para_transport(_url):
    return _payload([
        {"webTitle": WIRE, "webUrl": "https://g.test/a", "webPublicationDate": "2026-06-22T12:00:00Z"},
        {"webTitle": WIRE, "webUrl": "https://g.test/b", "webPublicationDate": "2026-06-22T13:00:00Z"},
        {"webTitle": PARA, "webUrl": "https://g.test/c", "webPublicationDate": "2026-06-22T14:00:00Z"},
        {"webTitle": DIFF, "webUrl": "https://g.test/d", "webPublicationDate": "2026-06-22T15:00:00Z"},
    ])


def _no_overlap_transport(_url):
    return _payload([
        {"webTitle": f"Distinct unrelated event number {i} on a separate topic entirely",
         "webUrl": f"https://g.test/{i}", "webPublicationDate": "2026-06-22T12:00:00Z"}
        for i in range(4)])


def _none_transport(_url):
    return None   # network_error 모사.


def _boom_transport(*_a, **_k):
    raise AssertionError("transport must NOT be called when opt-in off or credential missing")


def _probe(present, file_present, declared=True):
    return lambda v: {"var_name": v, "credential_present": present,
                      "env_file_present": file_present, "declared_in_example": declared}


# ── secret boundary (1-8) ────────────────────────────────────────────────────────────────────────────
def test_01_env_file_read_invariant_false():
    """smoke 는 `.env` 내용을 직접 열람하지 않는다(env_file_read 불변 False)."""
    r = run_guardian_live_query_smoke(env_probe_fn=_probe(False, False))
    assert r["env_file_read"] is False
    assert r["credential_value_exposed"] is False


def test_02_env_example_names_only_declared(tmp_path):
    """`.env.example` 이름 선언만 확인(값 미반환). 선언 있으면 True·없으면 False."""
    ex = tmp_path / ".env.example"
    ex.write_text("# template\nGUARDIAN_API_KEY=\nOTHER_KEY=\n", encoding="utf-8")
    assert env_example_declares("GUARDIAN_API_KEY", example_path=ex) is True
    assert env_example_declares("NOT_DECLARED_KEY", example_path=ex) is False


def test_03_secret_value_never_in_report(monkeypatch):
    """실 SENTINEL 값을 os.environ 에 주입해도 report 어디에도 안 나타난다(값 금지·이름 허용)."""
    monkeypatch.setenv("GUARDIAN_API_KEY", _SENTINEL)
    r = run_guardian_live_query_smoke(
        live_query=True, env_probe_fn=_probe(True, True), provider_transport=_wire_para_transport)
    blob = json.dumps(r, ensure_ascii=False)
    assert _SENTINEL not in blob


def test_04_env_var_name_visible():
    """env var 이름은 노출(허용) — agent/사람이 무엇을 설정해야 하는지 알 수 있어야."""
    r = run_guardian_live_query_smoke(env_probe_fn=_probe(False, True))
    assert r["env_var_name"] == "GUARDIAN_API_KEY"
    assert "GUARDIAN_API_KEY" in json.dumps(r, ensure_ascii=False)


def test_05_secret_not_in_block_reasons_or_next_actions(monkeypatch):
    """block_reasons/next_actions 에 실 값이 섞이지 않는다(missing 안내에도 이름만)."""
    monkeypatch.setenv("GUARDIAN_API_KEY", _SENTINEL)
    r = run_guardian_live_query_smoke(live_query=True, env_probe_fn=_probe(False, True))
    assert _SENTINEL not in json.dumps(r["block_reasons"]) + json.dumps(r["next_actions"])


def test_06_no_secret_on_network_error(monkeypatch):
    """network_error 분류 시에도 값 미노출(예외/result 어디에도)."""
    monkeypatch.setenv("GUARDIAN_API_KEY", _SENTINEL)
    r = run_guardian_live_query_smoke(
        live_query=True, env_probe_fn=_probe(True, True), provider_transport=_none_transport)
    assert _SENTINEL not in json.dumps(r, ensure_ascii=False)
    assert "network_error" in r["block_reasons"]


def test_07_output_contract_complete():
    """§4 필수 output key 전부 존재(계약 완전성)."""
    r = run_guardian_live_query_smoke(env_probe_fn=_probe(False, False))
    assert _REQUIRED_OUTPUT_KEYS <= set(r)
    assert r["smoke_name"] == "guardian_live_query"


def test_08_credential_value_exposed_invariant():
    """credential_value_exposed 는 모든 경로에서 False 불변."""
    for lq, present, fp in [(False, True, True), (True, False, False), (True, False, True), (True, True, True)]:
        r = run_guardian_live_query_smoke(
            live_query=lq, env_probe_fn=_probe(present, fp), provider_transport=_wire_para_transport)
        assert r["credential_value_exposed"] is False and r["env_file_read"] is False


# ── guardian live smoke (9-19) ───────────────────────────────────────────────────────────────────────
def test_09_disabled_by_default():
    """기본 live_query=False → 시도 0(not_opted_in)·transport 미호출."""
    r = run_guardian_live_query_smoke(env_probe_fn=_probe(True, True), provider_transport=_boom_transport)
    assert r["live_query_requested"] is False and r["live_query_attempted"] is False
    assert r["block_reasons"] == ["not_opted_in"]


def test_10_requires_explicit_opt_in():
    """opt-in flag 없이는 credential present 여도 실행 안 함."""
    r = run_guardian_live_query_smoke(live_query=False, env_probe_fn=_probe(True, True),
                                      provider_transport=_boom_transport)
    assert r["live_query_attempted"] is False
    assert r["host_gate_status"] == "not_attempted" and r["rate_limit_status"] == "not_attempted"


def test_11_env_not_loaded_blocks_before_network():
    """opt-in + credential 부재 + `.env` 파일 부재 → env_not_loaded(network 전·transport 미호출)."""
    r = run_guardian_live_query_smoke(live_query=True, env_probe_fn=_probe(False, False),
                                      provider_transport=_boom_transport)
    assert r["block_reasons"] == ["env_not_loaded"] and r["live_query_attempted"] is False
    assert any("create .env" in a for a in r["next_actions"])


def test_12_missing_credentials_distinct_from_env_not_loaded():
    """opt-in + credential 부재 + `.env` 파일 **존재** → missing_credentials(env_not_loaded 와 구분)."""
    r = run_guardian_live_query_smoke(live_query=True, env_probe_fn=_probe(False, True),
                                      provider_transport=_boom_transport)
    assert r["block_reasons"] == ["missing_credentials"] and r["live_query_attempted"] is False


def test_13_fake_transport_success_returns_records():
    """opt-in + credential present + fake transport → status ok·records 정규화."""
    r = run_guardian_live_query_smoke(live_query=True, env_probe_fn=_probe(True, True),
                                      provider_transport=_wire_para_transport)
    assert r["live_query_attempted"] is True and r["records_count"] == 4
    assert r["host_gate_status"] == "passed" and r["rate_limit_status"] == "ok"


def test_14_network_error_classified(monkeypatch):
    """transport None → network_error 분류(fixture 둔갑 0)."""
    r = run_guardian_live_query_smoke(live_query=True, env_probe_fn=_probe(True, True),
                                      provider_transport=_none_transport)
    assert "network_error" in r["block_reasons"] and r["dataset_source"] is None


def test_15_no_overlap_honest_no_candidate():
    """records 는 있으나 same-event overlap 0 → 정직한 no-overlap block(둔갑 0)·records>0·live_derived."""
    r = run_guardian_live_query_smoke(live_query=True, env_probe_fn=_probe(True, True),
                                      provider_transport=_no_overlap_transport)
    assert r["records_count"] == 4 and r["candidate_count"] == 0
    assert r["block_reasons"] and r["near_match_count"] == 0
    # 실 호출(ADR#63 evidence)과 동형: no-overlap → cross-source(2nd provider) 가이드.
    assert any("second publishable provider" in a for a in r["next_actions"])


def test_16_host_gate_blocked_no_tight_retry():
    """host gate 차단 시 host_gate_status=blocked·시도 차단(governed no-bypass)."""
    gate = SimpleNamespace(
        decide=lambda *a, **k: SimpleNamespace(allowed=False, reason="host_min_spacing_not_elapsed"),
        record_call=lambda *a, **k: None)
    r = run_guardian_live_query_smoke(live_query=True, env_probe_fn=_probe(True, True),
                                      provider_transport=_wire_para_transport, host_gate=gate)
    assert r["host_gate_status"] == "blocked" and r["dataset_source"] is None


# ── queue integration (20-30) ────────────────────────────────────────────────────────────────────────
def test_17_live_records_populate_reviewer_queue():
    """live records → ADR#60 records= path → near-match reviewer queue 충원(queue_pop>0)."""
    r = run_guardian_live_query_smoke(live_query=True, env_probe_fn=_probe(True, True),
                                      provider_transport=_wire_para_transport)
    assert r["near_match_count"] >= 1 and r["hard_negative_count"] >= 1
    assert r["reviewer_queue_population_count"] > 0


def test_18_dataset_source_live_derived_only_for_real_records():
    """실 records 일 때만 dataset_source=live_derived(fixture 둔갑 0)."""
    ok = run_guardian_live_query_smoke(live_query=True, env_probe_fn=_probe(True, True),
                                       provider_transport=_wire_para_transport)
    assert ok["dataset_source"] == "live_derived" and ok["provenance"] == "live_derived"
    blocked = run_guardian_live_query_smoke(live_query=True, env_probe_fn=_probe(False, True))
    assert blocked["dataset_source"] is None and blocked["provenance"] == "none"


def test_19_no_merge_no_llm_no_db_invariants():
    """모든 경로: production_gold 0·merge_allowed False·db_write False·llm_invoked False·no public IU."""
    r = run_guardian_live_query_smoke(live_query=True, env_probe_fn=_probe(True, True),
                                      provider_transport=_wire_para_transport)
    assert r["production_gold_count"] == 0 and r["merge_allowed"] is False
    assert r["db_write"] is False and r["llm_invoked"] is False
    assert r["no_merge_without_gold"] is True and r["no_public_intelligence_unit"] is True


# ── probe_env_var helper (secret-safe readiness) ─────────────────────────────────────────────────────
def test_20_probe_present(monkeypatch, tmp_path):
    """env var present + `.env` 존재 → credential_present True·env_file_present True(값 미반환)."""
    monkeypatch.setenv("GUARDIAN_API_KEY", _SENTINEL)
    envf = tmp_path / ".env"
    envf.write_text("OTHER=1\n", encoding="utf-8")
    p = probe_env_var("GUARDIAN_API_KEY", env_path=envf, example_path=tmp_path / ".env.example")
    assert p["credential_present"] is True and p["env_file_present"] is True
    assert _SENTINEL not in json.dumps(p)   # 값은 절대 probe 결과에 없음


def test_21_probe_key_missing_file_present(monkeypatch, tmp_path):
    """env var 미설정 + `.env` 존재 → credential_present False·env_file_present True(missing_credentials 신호)."""
    monkeypatch.delenv("GUARDIAN_API_KEY", raising=False)
    envf = tmp_path / ".env"
    envf.write_text("OTHER=1\n", encoding="utf-8")
    p = probe_env_var("GUARDIAN_API_KEY", env_path=envf)
    assert p["credential_present"] is False and p["env_file_present"] is True


def test_22_probe_env_file_absent(monkeypatch, tmp_path):
    """env var 미설정 + `.env` 부재 → credential_present False·env_file_present False(env_not_loaded 신호)."""
    monkeypatch.delenv("GUARDIAN_API_KEY", raising=False)
    p = probe_env_var("GUARDIAN_API_KEY", env_path=tmp_path / "does_not_exist.env")
    assert p["credential_present"] is False and p["env_file_present"] is False


# ── agent contract (31-36) + CLI ─────────────────────────────────────────────────────────────────────
def test_23_agent_schema_secret_safe_and_no_go(monkeypatch):
    """Agent schema: no_secret_fabrication·no_merge_without_gate·embedding/LLM No-Go·llm_invoked False."""
    monkeypatch.delenv("GUARDIAN_API_KEY", raising=False)
    readiness = build_provider_readiness_report(env_status_fn=lambda keys: {k: "missing" for k in keys})
    live = run_guardian_live_query_smoke(env_probe_fn=_probe(False, False))
    schema = build_provider_readiness_agent_schema(readiness, {
        "live_query_allowed": False, "live_query_attempted": False, "candidate_count": 0,
        "reviewer_queue_population_count": 0, "block_reasons": live["block_reasons"], "dataset_source": None})
    assert schema["no_secret_fabrication"] is True and schema["no_merge_without_gate"] is True
    assert schema["llm_invoked"] is False
    assert schema["embedding_llm_adjudicator"]["status"].lower().startswith("no")
    assert "provider secret 추측/생성" in schema["agent_cannot"]


def test_24_cli_default_no_network_returns_zero(capsys, monkeypatch):
    """CLI 기본(no --live-query) → exit 0·값 미출력·시도 0. (probe 스텁→실 `.env` 미접촉·hermetic)"""
    monkeypatch.setattr(_glq, "_default_env_probe", lambda v: _probe(False, True)(v))
    rc = main(["--topic", "test topic"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "requested=False" in out and "attempted=False" in out
    assert _SENTINEL not in out


def test_25_cli_json_output_secret_free(monkeypatch, capsys):
    """CLI --json: §4 report JSON·credential value 미출력(이름만). (probe 스텁→실 `.env` 미접촉·hermetic)"""
    monkeypatch.setattr(_glq, "_default_env_probe", lambda v: _probe(False, True)(v))
    rc = main(["--json"])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["smoke_name"] == "guardian_live_query"
    assert parsed["credential_value_exposed"] is False


def test_26_real_network_path_key_only_in_params(monkeypatch):
    """실 network 분기(transport=None)를 httpx monkeypatch 로 타서 key 가 **params 전용**·URL/report 에 미노출임을 실증.

    (code-review: fake-transport sentinel 테스트는 os.getenv 경로를 안 타 near-tautology — 이 테스트가 실 key
    핸들링[`run_provider_query` real-network branch]을 결정론으로 직접 커버. network 0[httpx 가짜]·실 `.env` 미접촉[probe/env_status 주입].)"""
    monkeypatch.setenv("GUARDIAN_API_KEY", _SENTINEL)
    captured: dict = {}

    class _Resp:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = _payload([
            {"webTitle": WIRE, "webUrl": "https://g.test/a", "webPublicationDate": "2026-06-22T12:00:00Z"},
            {"webTitle": WIRE, "webUrl": "https://g.test/b", "webPublicationDate": "2026-06-22T13:00:00Z"},
            {"webTitle": PARA, "webUrl": "https://g.test/c", "webPublicationDate": "2026-06-22T14:00:00Z"},
            {"webTitle": DIFF, "webUrl": "https://g.test/d", "webPublicationDate": "2026-06-22T15:00:00Z"},
        ])

    def _fake_get(url, params=None, **_kw):
        captured["url"] = url
        captured["params"] = params
        return _Resp()

    monkeypatch.setattr(httpx, "get", _fake_get)
    gate = SimpleNamespace(decide=lambda *a, **k: SimpleNamespace(allowed=True, reason=None),
                           record_call=lambda *a, **k: None)
    r = run_guardian_live_query_smoke(
        live_query=True, env_probe_fn=_probe(True, True),
        env_status_fn=lambda keys: {k: "present" for k in keys}, host_gate=gate)
    # key 는 httpx params 로만·URL 엔 절대 없음(secret not in URL)
    assert captured["params"] == {"api-key": _SENTINEL}
    assert _SENTINEL not in captured["url"] and "api-key" not in captured["url"]
    # report 어디에도 값 없음·실 fetch 정규화(live_derived)
    assert _SENTINEL not in json.dumps(r, ensure_ascii=False)
    assert r["dataset_source"] == "live_derived" and r["records_count"] == 4
    assert r["credential_value_exposed"] is False

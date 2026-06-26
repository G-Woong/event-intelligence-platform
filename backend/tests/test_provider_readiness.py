"""ADR#61 — query-capable provider acquisition readiness gate tests.

§10 시나리오(provider readiness 1-10·optional live query 11-20·live candidate queue 21-28·runbook/env 29-33·
Agent contract 34-39) + 회귀. 정책을 테스트로 잠근다: secret 미노출·fixture 둔갑 금지·no merge·no LLM·
synthetic↔live 봉인·production_gold 0. network 0(transport/env_status/gdelt_status 주입 결정론).
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from backend.app.services.identity_human_labeling import (
    _PACKET_FORBIDDEN_VERDICT_KEYS,
    SOURCE_LIVE,
    SOURCE_SYNTHETIC,
)
from backend.app.tools.provider_query_adapters import run_provider_query
from backend.app.tools.provider_readiness import (
    _PROVIDER_CATALOG,
    CLASS_BLOCKED_RATE_LIMITED,
    CLASS_KEY_FREE_NON_QUERY,
    CLASS_KEY_FREE_QUERY,
    CLASS_KEY_REQUIRED_QUERY,
    CLASS_UNKNOWN_POLICY,
    LQ_FETCHER_NOT_IMPLEMENTED,
    LQ_HOST_GATE_BLOCKED,
    LQ_MISSING_CREDENTIALS,
    LQ_NO_QUERY_CAPABLE_PROVIDER,
    LQ_NOT_OPTED_IN,
    LQ_PROVIDER_RATE_LIMITED,
    build_provider_readiness_agent_schema,
    build_provider_readiness_report,
    run_optional_live_query,
    run_provider_acquisition_readiness,
)
from backend.app.tools.targeted_same_event_acquisition import (
    run_targeted_same_event_operating_readiness,
)

# ── deterministic fixtures(주입 — 실 .env/state/network 비의존) ──────────────────────────────────────────
GDELT_OK = {"provider_status": "ok", "provider_block_reason": None}
GDELT_COOLDOWN = {"provider_status": "cooldown", "provider_block_reason": "provider_429_cooldown",
                  "retry_after_or_cooldown": "2026-06-25T01:00:00Z"}
GDELT_HOSTBLOCK = {"provider_status": "host_rate_limited",
                   "provider_block_reason": "host_min_spacing_not_elapsed:3<10"}

WIRE = "Federal Reserve raises benchmark interest rate by quarter point"
PARA = "Federal Reserve raises benchmark interest rate by 25 basis points"
DIFF = "Federal Reserve official comments on interest rate policy outlook"


def env_missing(keys):
    return {k: "missing" for k in keys}


def env_present(keys):
    return {k: "present" for k in keys}


def _boom_transport(*_a, **_k):
    raise AssertionError("transport must NOT be called when live query is gated/blocked")


def _gdelt_payload(articles):
    return json.dumps({"articles": articles})


def _same_event_payload():
    """ADR#60 fixture 와 동일 wire/para/diff — 다른 domain(=다른 source)으로 live cross-source overlap 재현."""
    return _gdelt_payload([
        {"title": WIRE, "url": "https://bbc.test/a", "domain": "bbc.com", "seendate": "20260622T120000Z"},
        {"title": WIRE, "url": "https://aljazeera.test/b", "domain": "aljazeera.com",
         "seendate": "20260622T130000Z"},
        {"title": PARA, "url": "https://tc.test/c", "domain": "techcrunch.com",
         "seendate": "20260622T140000Z"},
        {"title": DIFF, "url": "https://verge.test/d", "domain": "theverge.com",
         "seendate": "20260622T150000Z"},
    ])


def _same_event_transport(_url):
    return _same_event_payload()


def _empty_transport(_url):
    return _gdelt_payload([])


def _ok_report(**kw):
    return build_provider_readiness_report(
        env_status_fn=kw.pop("env_status_fn", env_missing), gdelt_status=kw.pop("gdelt_status", GDELT_OK),
        **kw)


def _row(report, pid):
    return next(r for r in report["providers"] if r["provider_id"] == pid)


# ══ Section A — provider readiness (§10 1-10) ════════════════════════════════════════════════════════════
def test_01_key_free_query_provider_ready():
    rep = _ok_report()
    g = _row(rep, "gdelt")
    assert g["classification"] == CLASS_KEY_FREE_QUERY
    assert g["auth_required"] is False and g["credential_ready"] is True
    assert g["safe_to_live_query"] is True
    assert "gdelt" in rep["key_free_ready"]


def test_02_key_required_provider_missing_credentials():
    rep = _ok_report(env_status_fn=env_missing)
    n = _row(rep, "newsapi")
    assert n["classification"] == CLASS_KEY_REQUIRED_QUERY
    assert n["credential_ready"] is False
    assert "newsapi" in rep["key_required_missing"]
    assert n["next_action"].startswith("set_env:NEWSAPI_API_KEY")


def test_03_blocked_provider_due_cooldown():
    rep = _ok_report(gdelt_status=GDELT_COOLDOWN)
    g = _row(rep, "gdelt")
    assert g["classification"] == CLASS_BLOCKED_RATE_LIMITED
    assert g["safe_to_live_query"] is False
    assert "gdelt" in rep["provider_blocked"]
    assert "respect_cooldown" in g["next_action"]


def test_04_rss_fleet_classified_non_query():
    rep = _ok_report()
    rss = _row(rep, "rss_fleet")
    assert rss["classification"] == CLASS_KEY_FREE_NON_QUERY
    assert rss["query_capability"] == "time_window+source_pair"
    assert "topic query 불가" in rss["next_action"]


def test_05_unknown_provider_fail_closed():
    rep = build_provider_readiness_report(
        providers=["gdelt", "totally_unknown_provider"], env_status_fn=env_missing,
        gdelt_status=GDELT_OK)
    u = _row(rep, "totally_unknown_provider")
    assert u["classification"] == CLASS_UNKNOWN_POLICY
    assert u["safe_to_live_query"] is False
    assert "totally_unknown_provider" in rep["provider_unknown"]


def test_06_env_var_names_shown_values_hidden():
    rep = _ok_report(env_status_fn=env_missing)
    n = _row(rep, "newsapi")
    assert n["required_env_vars"] == ["NEWSAPI_API_KEY"]
    # 값이 아니라 present/missing boolean 만.
    assert set(n["env_present"].values()) <= {"present", "missing"}
    assert n["env_present"]["NEWSAPI_API_KEY"] == "missing"


def test_07_raw_secret_never_in_report():
    # 전 provider 의 env_present 값은 present/missing 뿐 — 어떤 secret 값도 보고에 실리지 않는다.
    rep = build_provider_readiness_report(
        env_status_fn=lambda ks: {k: "present" for k in ks}, gdelt_status=GDELT_OK)
    for r in rep["providers"]:
        assert set(r["env_present"].values()) <= {"present", "missing"}
        for var in r["required_env_vars"]:
            assert var.isupper() or "_" in var   # 이름만(대문자 env 컨벤션)


def test_08_host_gate_status_included():
    rep = _ok_report()
    assert "gdelt" in rep["host_gate_status"]
    assert rep["host_gate_status"]["gdelt"] == "ok"
    # 비 host-gated provider 는 host_gate_status 집계에 없음(개별 row 에는 not_host_gated).
    assert _row(rep, "newsapi")["host_gate_status"] == "not_host_gated"


def test_09_rate_limit_policy_included():
    rep = _ok_report()
    assert "gdelt" in rep["rate_limit_policy"]
    # GDELT 강화 정책(cooldown_on_429 900s) 표면화.
    assert rep["rate_limit_policy"]["gdelt"]["cooldown_on_429_seconds"] == 900
    assert _row(rep, "gdelt")["rate_limit_policy_present"] is True


def test_10_next_action_generated_for_every_provider():
    rep = _ok_report(env_status_fn=env_missing)
    for r in rep["providers"]:
        assert isinstance(r["next_action"], str) and r["next_action"].strip()


# ══ Section B — optional live query (§10 11-20) ══════════════════════════════════════════════════════════
def test_11_live_query_disabled_by_default():
    rep = _ok_report()
    lq = run_optional_live_query(provider="gdelt", live_query=False, readiness=rep,
                                 gdelt_transport=_boom_transport)
    assert lq["live_query_allowed"] is False
    assert lq["live_query_attempted"] is False
    assert lq["skipped_reason"] == LQ_NOT_OPTED_IN


def test_12_live_query_requires_explicit_flag_even_if_safe():
    rep = _ok_report()
    assert _row(rep, "gdelt")["safe_to_live_query"] is True
    lq = run_optional_live_query(provider="gdelt", live_query=False, readiness=rep)
    assert lq["live_query_allowed"] is False   # safe 여도 flag 없으면 불가.


def test_13_missing_credentials_blocks():
    rep = _ok_report(env_status_fn=env_missing)
    lq = run_optional_live_query(provider="newsapi", live_query=True, readiness=rep,
                                 env_status_fn=env_missing)
    assert lq["live_query_allowed"] is False
    assert lq["skipped_reason"] == LQ_MISSING_CREDENTIALS
    assert lq["live_query_attempted"] is False


def test_14_rate_limited_provider_blocks_no_fetch():
    rep = _ok_report(gdelt_status=GDELT_COOLDOWN)
    lq = run_optional_live_query(provider="gdelt", live_query=True, readiness=rep,
                                 gdelt_transport=_boom_transport)   # 호출되면 AssertionError.
    assert lq["live_query_allowed"] is False
    assert lq["skipped_reason"] == LQ_PROVIDER_RATE_LIMITED
    assert lq["live_query_attempted"] is False


def test_15_host_gate_blocked_does_not_fetch():
    rep = _ok_report(gdelt_status=GDELT_HOSTBLOCK)
    lq = run_optional_live_query(provider="gdelt", live_query=True, readiness=rep,
                                 gdelt_transport=_boom_transport)
    assert lq["live_query_allowed"] is False
    assert lq["skipped_reason"] in (LQ_HOST_GATE_BLOCKED, LQ_PROVIDER_RATE_LIMITED)
    assert lq["live_query_attempted"] is False


def test_16_bounded_max_records_enforced():
    arts = [{"title": f"World event number {i} reported today", "url": f"https://d{i % 5}.test/{i}",
             "domain": f"d{i % 5}.com", "seendate": "20260622T120000Z"} for i in range(40)]

    def big_transport(_url):
        return _gdelt_payload(arts)

    rep = _ok_report()
    lq = run_optional_live_query(provider="gdelt", live_query=True, readiness=rep,
                                 gdelt_transport=big_transport)
    # parse_gdelt_articles _DEFAULT_MAX_RECORDS=25 → 40 입력이 25 로 bounded.
    assert lq["live_query_result"]["records_count"] == 25


def test_17_raw_body_not_stored_on_live_path():
    out = run_targeted_same_event_operating_readiness(
        provider="gdelt", live_network=True, gdelt_transport=_same_event_transport)
    forbidden = {"body", "content", "raw_payload", "text", "author", "email"}
    for row in out["queue"].get("worksheet_rows") or []:
        assert not (set(row) & forbidden)
    for row in out["queue"].get("packet_rows") or []:
        assert not (set(row) & forbidden)


def test_18_no_db_session_parameter():
    # DB write 경로 부재 — session 인자 자체가 없다(운영 DB 무접촉).
    for fn in (run_optional_live_query, run_provider_acquisition_readiness):
        assert "session" not in inspect.signature(fn).parameters


def test_19_no_merge_anywhere():
    out = run_provider_acquisition_readiness(
        provider="gdelt", live_query=True, gdelt_transport=_same_event_transport)
    assert out["no_merge_without_gold"] is True
    assert out["live_query_result"]["merge_allowed"] is False


def test_20_no_llm_invoked():
    out = run_provider_acquisition_readiness(provider="gdelt", live_query=False)
    assert out["agent_schema"]["llm_invoked"] is False
    assert out["provider_readiness_report"]["llm_invoked"] is False


# ══ Section C — live candidate queue (§10 21-28) ═════════════════════════════════════════════════════════
def test_21_live_candidates_populate_queue():
    rep = _ok_report()
    lq = run_optional_live_query(provider="gdelt", live_query=True, readiness=rep,
                                 gdelt_transport=_same_event_transport)
    assert lq["live_query_attempted"] is True
    assert lq["candidate_count"] >= 1
    assert lq["reviewer_queue_population_count"] >= 1
    assert lq["near_match_count"] >= 1


def test_22_empty_live_result_reports_no_candidate():
    rep = _ok_report()
    lq = run_optional_live_query(provider="gdelt", live_query=True, readiness=rep,
                                 gdelt_transport=_empty_transport)
    assert lq["candidate_count"] == 0
    assert lq["reviewer_queue_population_count"] == 0
    assert lq["block_reasons"]            # no_records/no_near_match 등 정직 노출.


def test_23_dataset_source_live_derived_preserved():
    rep = _ok_report()
    lq = run_optional_live_query(provider="gdelt", live_query=True, readiness=rep,
                                 gdelt_transport=_same_event_transport)
    assert lq["dataset_source"] == SOURCE_LIVE      # "live_derived"
    assert lq["provenance"] == SOURCE_LIVE


def test_24_no_fixture_substitution_when_not_opted_in():
    # live query 미허용 시 fixture 둔갑 금지 — dataset_source None(synthetic 으로도 위장 안 함).
    rep = _ok_report()
    lq = run_optional_live_query(provider="gdelt", live_query=False, readiness=rep)
    assert lq["dataset_source"] is None
    assert lq["provenance"] == "none"
    # ADR#60 fixture 경로는 별도로 여전히 synthetic_fixture 로 정직 표기.
    fx = run_targeted_same_event_operating_readiness(provider="fixture")
    assert fx["report"]["dataset_source"] == SOURCE_SYNTHETIC


def test_25_production_gold_count_zero():
    out = run_provider_acquisition_readiness(
        provider="gdelt", live_query=True, gdelt_transport=_same_event_transport)
    assert out["live_query_result"]["production_gold_count"] == 0


def test_26_merge_allowed_false_with_candidates():
    rep = _ok_report()
    lq = run_optional_live_query(provider="gdelt", live_query=True, readiness=rep,
                                 gdelt_transport=_same_event_transport)
    assert lq["merge_allowed"] is False


def test_27_predicted_status_hidden_on_live_path():
    out = run_targeted_same_event_operating_readiness(
        provider="gdelt", live_network=True, gdelt_transport=_same_event_transport)
    for row in out["queue"].get("labeler_view") or []:
        assert not (set(row) & _PACKET_FORBIDDEN_VERDICT_KEYS)
        assert "sampling_bucket" not in row


def test_28_packet_exportable_when_candidates_exist():
    rep = _ok_report()
    lq = run_optional_live_query(provider="gdelt", live_query=True, readiness=rep,
                                 gdelt_transport=_same_event_transport)
    assert lq["live_query_result"]["packet_exportable"] is True


# ══ Section D — runbook / env (§10 29, 32-33) ════════════════════════════════════════════════════════════
def test_29_provider_env_placeholders_documented():
    # catalog 의 모든 required_env_var 는 .env.example(안전 템플릿)에 placeholder 가 존재해야 한다(drift 차단).
    env_example = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    for spec in _PROVIDER_CATALOG.values():
        for var in spec.get("required_env_vars") or []:
            assert var in env_example, f"{var} missing from .env.example"


def test_32_tests_pass_without_secrets():
    # 전 경로가 env_status_fn 주입으로 동작 — 실 secret 없이 readiness/ live gate 완결.
    rep = build_provider_readiness_report(env_status_fn=env_missing, gdelt_status=GDELT_OK)
    assert rep["key_required_missing"]          # secret 없이도 정직히 missing 보고.


def test_33_live_blocked_honestly_without_secrets():
    rep = _ok_report(env_status_fn=env_missing)
    lq = run_optional_live_query(provider="guardian", live_query=True, readiness=rep,
                                 env_status_fn=env_missing)
    assert lq["skipped_reason"] == LQ_MISSING_CREDENTIALS    # crash 아니라 정직 block.


# ══ Section E — Agent contract (§10 34-39) ═══════════════════════════════════════════════════════════════
def test_34_agent_schema_includes_provider_readiness():
    out = run_provider_acquisition_readiness(provider="gdelt", live_query=False)
    sch = out["agent_schema"]
    assert "provider_readiness" in sch
    assert "provider_readiness_review" in sch["agent_can_plan"]


def test_35_agent_schema_no_secret_fabrication():
    sch = build_provider_readiness_agent_schema(_ok_report(), run_optional_live_query(
        provider="gdelt", live_query=False, readiness=_ok_report()))
    assert sch["no_secret_fabrication"] is True
    assert any("secret" in c for c in sch["agent_cannot"])


def test_36_agent_schema_no_merge_without_gate():
    out = run_provider_acquisition_readiness(provider="gdelt", live_query=False)
    assert out["agent_schema"]["no_merge_without_gate"] is True
    assert "merge 실행" in out["agent_schema"]["agent_cannot"]


def test_37_agent_schema_no_public_intelligence_unit():
    out = run_provider_acquisition_readiness(provider="gdelt", live_query=False)
    assert out["agent_schema"]["no_public_intelligence_unit"] is True
    assert out["no_public_intelligence_unit"] is True


def test_38_llm_not_invoked():
    out = run_provider_acquisition_readiness(
        provider="gdelt", live_query=True, gdelt_transport=_same_event_transport)
    assert out["agent_schema"]["llm_invoked"] is False


def test_39_embedding_llm_adjudicator_no_go():
    out = run_provider_acquisition_readiness(provider="gdelt", live_query=False)
    adj = out["agent_schema"]["embedding_llm_adjudicator"]
    assert str(adj.get("status", "")).startswith("No-Go")


# ══ Section F — integration / regression (§10 40-41) ═════════════════════════════════════════════════════
def test_40_integrated_report_has_required_section4_keys():
    out = run_provider_acquisition_readiness(provider="gdelt", live_query=False)
    for key in ("provider_readiness_report", "query_capable_providers", "key_free_ready",
                "key_required_missing", "provider_blocked", "provider_unknown",
                "env_var_requirements", "rate_limit_policy", "host_gate_status",
                "credential_status", "live_query_allowed", "live_query_attempted",
                "live_query_result", "candidate_count", "near_match_count",
                "reviewer_queue_population_count", "dataset_source", "provenance",
                "block_reasons", "next_actions", "no_merge_without_gold",
                "no_public_intelligence_unit"):
        assert key in out, f"missing required output key {key}"


def test_41_adr60_targeted_default_still_synthetic():
    # ADR#60 frozen 회귀 — provider_readiness 추가가 targeted 기본 경로를 바꾸지 않는다.
    out = run_targeted_same_event_operating_readiness()
    assert out["report"]["dataset_source"] == SOURCE_SYNTHETIC
    assert out["report"]["real_fetch"] is False
    assert out["report"]["merge_allowed"] is False


def test_42_unknown_provider_live_query_no_query_capable():
    rep = build_provider_readiness_report(
        providers=["foobar"], env_status_fn=env_missing, gdelt_status=GDELT_OK)
    lq = run_optional_live_query(provider="foobar", live_query=True, readiness=rep,
                                 env_status_fn=env_missing)
    assert lq["skipped_reason"] == LQ_NO_QUERY_CAPABLE_PROVIDER


def test_43_fetcher_not_wired_blocks_credentialed_provider():
    # newsapi 키가 있어도(present) 실 fetcher 미배선이면 live query 차단 — fixture 둔갑 금지.
    rep = _ok_report(env_status_fn=env_present)
    lq = run_optional_live_query(provider="newsapi", live_query=True, readiness=rep,
                                 env_status_fn=env_present)
    assert lq["skipped_reason"] == LQ_FETCHER_NOT_IMPLEMENTED
    assert lq["dataset_source"] is None


def test_44_rss_fleet_live_query_maps_to_real_rss_not_fixture():
    # 회귀(code-review/adversarial MEDIUM): rss_fleet 은 ADR#60 가 인식하는 'rss' 로 정규화돼 **실 RSS 경로**를
    # 타야 한다(fixture 둔갑 금지). transport 주입=network 0; endpoint 유무와 무관하게 used_real=True 라
    # dataset_source=live_derived(synthetic_fixture 둔갑 0). 정규화 누락 시 fixture 로 떨어져 이 테스트가 잡는다.
    rep = _ok_report()

    def rss_t(_sid, _endpoint):
        return None   # per-source network_error → 0 records·그러나 실 fetch 시도(used_real=True)

    lq = run_optional_live_query(provider="rss_fleet", live_query=True, readiness=rep,
                                 rss_transport=rss_t)
    assert lq["live_query_allowed"] is True
    assert lq["live_query_attempted"] is True
    assert lq["dataset_source"] == SOURCE_LIVE                      # 실 fetch 경로(fixture 아님)
    assert lq["dataset_source"] != SOURCE_SYNTHETIC
    assert "real_fetch_not_attempted_fixture_substituted" not in lq["block_reasons"]


def test_45_rss_fleet_source_ids_match_real_fetch_fleet():
    # 회귀(code-review SIMPLIFICATION): readiness 가 광고하는 rss_fleet source_ids 는 실 fetch 가 쓰는
    # ADR#60 _DEFAULT_TARGET_SOURCES 와 정확히 일치해야 한다(광고-미fetch 발산 0).
    from backend.app.tools.targeted_same_event_acquisition import _DEFAULT_TARGET_SOURCES
    rss = _row(_ok_report(), "rss_fleet")
    assert rss["source_ids"] == list(_DEFAULT_TARGET_SOURCES)


# ══ Section G — ADR#62 guardian adapter wiring + adapter-to-queue (§12 21-35) ════════════════════════════
def _guardian_payload():
    """Guardian Content API 형태(공식 shape) — 같은 사건 wire/para/diff 다른 URL·같은 날(live cross-source overlap)."""
    return json.dumps({"response": {"status": "ok", "results": [
        {"webTitle": WIRE, "webUrl": "https://www.theguardian.com/a",
         "webPublicationDate": "2026-06-22T12:00:00Z"},
        {"webTitle": WIRE, "webUrl": "https://www.theguardian.com/b",
         "webPublicationDate": "2026-06-22T13:00:00Z"},
        {"webTitle": PARA, "webUrl": "https://www.theguardian.com/c",
         "webPublicationDate": "2026-06-22T14:00:00Z"},
        {"webTitle": DIFF, "webUrl": "https://www.theguardian.com/d",
         "webPublicationDate": "2026-06-22T15:00:00Z"},
    ]}})


def _guardian_transport(_url):
    return _guardian_payload()


def test_46_guardian_adapter_live_query_live_derived_to_queue():
    # §12 21-25: adapter records → discover → near-match reviewer queue, dataset_source live_derived(실 fetch 만).
    rep = _ok_report(env_status_fn=env_present)
    lq = run_optional_live_query(provider="guardian", live_query=True, readiness=rep,
                                 env_status_fn=env_present, provider_transport=_guardian_transport)
    assert lq["live_query_allowed"] is True and lq["live_query_attempted"] is True
    assert lq["dataset_source"] == SOURCE_LIVE                      # 실 adapter fetch → live_derived(fixture 둔갑 0).
    assert lq["dataset_source"] != SOURCE_SYNTHETIC
    assert lq["near_match_count"] >= 1
    assert lq["reviewer_queue_population_count"] >= 1               # 후보가 queue 로 연결.
    assert lq["live_query_result"]["provider_status"] == "live_derived"
    assert lq["live_query_result"]["production_gold_count"] == 0    # §12 28.
    assert lq["live_query_result"]["merge_allowed"] is False        # §12 29.


def test_47_guardian_fetch_implemented_adapter_fields():
    # §12 30·33-34: fetch_implemented True 는 adapter+test 존재 시에만 + adapter contract/queue 필드 표면.
    row = _row(_ok_report(env_status_fn=env_present), "guardian")
    assert row["fetch_implemented"] is True
    assert row["adapter_contract_version"] == "1.0"
    assert row["adapter_module"].endswith(":guardian")
    assert row["tested_with_fake_transport"] is True
    assert row["queue_integration_status"] == "wired"
    assert row["live_query_capable_if_credentials_present"] is True


def test_48_newsapi_credentialed_but_fetcher_not_wired():
    # §12 32: credential-ready 여도 fetcher 미배선이면 not_wired(fixture 둔갑 0·차단).
    row = _row(_ok_report(env_status_fn=env_present), "newsapi")
    assert row["credential_ready"] is True
    assert row["fetch_implemented"] is False
    assert row["queue_integration_status"] == "not_wired"
    assert row["live_query_capable_if_credentials_present"] is False


def test_49_wired_providers_includes_guardian_and_nyt_among_key_required():
    # ADR#64: NYT 2nd adapter wired(cross-source pair with Guardian). newsapi/gnews 는 여전히 미배선.
    rep = _ok_report(env_status_fn=env_present)
    assert "guardian" in rep["wired_providers"] and "nyt" in rep["wired_providers"]
    assert "gdelt" in rep["wired_providers"] and "rss_fleet" in rep["wired_providers"]
    assert "newsapi" not in rep["wired_providers"] and "gnews" not in rep["wired_providers"]
    assert rep["adapter_wired_providers"] == ["guardian", "nyt"]


def test_50_agent_schema_includes_adapter_contract():
    # §12 41: Agent schema 가 adapter readiness/contract 를 포함.
    out = run_provider_acquisition_readiness(provider="guardian", live_query=False,
                                             env_status_fn=env_present)
    sch = out["agent_schema"]
    assert "provider_adapter_contract" in sch
    assert "provider_adapter_readiness_review" in sch["agent_can_plan"]
    assert "guardian" in sch["wired_providers"]
    assert out["provider_adapter_contract"]["contract_version"] == "1.0"


def test_51_guardian_adapter_to_queue_hides_prediction_no_body():
    # §12 27·4: adapter records → ADR#60 queue → reviewer packet 은 predicted_status 숨김·raw body 부재.
    qr = run_provider_query("guardian", topic="fed", transport=_guardian_transport,
                            env_status_fn=env_present, today="2026-06-22")
    assert qr.status == "ok"
    out = run_targeted_same_event_operating_readiness(
        records=list(qr.records), real_fetch=True, provider="guardian")
    assert out["report"]["dataset_source"] == SOURCE_LIVE          # §12 25.
    chk = out["reviewer_operating_checklist"]
    assert chk["hidden_prediction_verified"] is True
    assert chk["raw_body_absent_verified"] is True
    # packet row 에 verdict 누출 0(predicted_status 숨김의 구조적 확인).
    for r in out["queue"].get("packet_rows") or []:
        assert not (set(r) & _PACKET_FORBIDDEN_VERDICT_KEYS)


def test_52_guardian_missing_creds_dataset_source_none():
    # §12 26: fixture 둔갑 0 — credential 없으면 dataset_source None(synthetic 으로 안 떨어짐).
    rep = _ok_report(env_status_fn=env_missing)
    lq = run_optional_live_query(provider="guardian", live_query=True, readiness=rep,
                                 env_status_fn=env_missing, provider_transport=_boom_transport)
    assert lq["skipped_reason"] == LQ_MISSING_CREDENTIALS
    assert lq["dataset_source"] is None
    assert lq["provenance"] == "none"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

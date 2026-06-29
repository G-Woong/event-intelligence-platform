"""ADR#62 — provider query adapter contract + first wired adapter(Guardian) tests.

§12 시나리오(adapter contract 1-8·key-required provider 9-16·governance 17-20). 정책을 테스트로 잠근다:
secret 값 미노출·raw body 미저장·no DB/merge/LLM·fixture 둔갑 금지·credential 없으면 정직 block·governed(host gate).
network 0(transport/env_status/host_gate 주입 결정론). 실 parser 를 그대로 통과(skeleton 아님 — 공식 Guardian shape).
"""
from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest

from backend.app.tools.provider_query_adapters import (
    ADAPTER_CONTRACT_VERSION,
    ADAPTER_WIRED_PROVIDERS,
    ALL_ADAPTER_PROVIDERS,
    ProviderQueryResult,
    _federal_register_url,
    _guardian_url,
    _nyt_url,
    adapter_descriptor,
    parse_federal_register_items,
    parse_guardian_items,
    parse_nyt_items,
    provider_adapter_contract,
    run_provider_query,
)

WIRE = "Federal Reserve raises benchmark interest rate by quarter point"
PARA = "Federal Reserve raises benchmark interest rate by 25 basis points"
DIFF = "Federal Reserve official comments on interest rate policy outlook"

_SECRET = "sk_live_should_never_appear_anywhere"   # 테스트용 가짜 key — result/URL 어디에도 나오면 안 됨.


def env_present(keys):
    return {k: "present" for k in keys}


def env_missing(keys):
    return {k: "missing" for k in keys}


def _guardian_payload(results=None):
    if results is None:
        results = [
            {"webTitle": WIRE, "webUrl": "https://www.theguardian.com/a",
             "webPublicationDate": "2026-06-22T12:00:00Z"},
            {"webTitle": WIRE, "webUrl": "https://www.theguardian.com/b",
             "webPublicationDate": "2026-06-22T13:00:00Z"},
            {"webTitle": PARA, "webUrl": "https://www.theguardian.com/c",
             "webPublicationDate": "2026-06-22T14:00:00Z"},
            {"webTitle": DIFF, "webUrl": "https://www.theguardian.com/d",
             "webPublicationDate": "2026-06-22T15:00:00Z"},
        ]
    return json.dumps({"response": {"status": "ok", "total": len(results), "results": results}})


def _guardian_transport(_url):
    return _guardian_payload()


def _boom_transport(*_a, **_k):
    raise AssertionError("transport must NOT be called when adapter is gated/blocked")


class _FakeGate:
    """shared HostRateGate 대역(network 0). allowed=False 면 host floor 미경과."""

    def __init__(self, allowed=True):
        self._allowed = allowed
        self.calls = []

    def decide(self, host, *, min_spacing_seconds):
        return SimpleNamespace(
            allowed=self._allowed,
            reason=None if self._allowed else f"host_min_spacing_not_elapsed:1<{min_spacing_seconds}")

    def record_call(self, host):
        self.calls.append(host)


# ══ Section A — provider adapter contract (§12 1-8) ══════════════════════════════════════════════════════
def test_01_adapter_contract_exists():
    c = provider_adapter_contract()
    assert c["contract_version"] == ADAPTER_CONTRACT_VERSION
    assert "guardian" in c["wired_providers"]
    for f in ("adapter_fields", "result_fields", "record_fields", "status_vocabulary", "forbidden"):
        assert c[f], f"contract missing {f}"


def test_02_result_schema_validated():
    qr = run_provider_query("guardian", topic="fed", transport=_guardian_transport,
                            env_status_fn=env_present, today="2026-06-22")
    assert isinstance(qr, ProviderQueryResult)
    for attr in ("provider_id", "status", "records", "records_count", "raw_body_stored",
                 "secret_exposed", "provenance", "block_reason", "next_action"):
        assert hasattr(qr, attr), f"result missing {attr}"


def test_03_records_normalized_rec_shape():
    recs = parse_guardian_items(_guardian_payload())
    assert len(recs) == 4
    r = recs[0]
    for k in ("record_type", "source_id", "title_or_label", "canonical_url",
              "published_at_or_observed_at", "body_state_or_signal"):
        assert k in r, f"record missing {k}"
    assert r["source_id"] == "guardian"
    assert r["published_at_or_observed_at"] == "2026-06-22"   # ISO→date bucket 정규화.


def test_04_raw_body_not_stored():
    qr = run_provider_query("guardian", topic="fed", transport=_guardian_transport,
                            env_status_fn=env_present)
    assert qr.raw_body_stored is False
    for r in qr.records:
        assert not ({"body", "content", "raw_payload", "text"} & set(r)), "raw body leaked into record"


def test_05_secret_value_not_exposed():
    captured = {}

    def cap_transport(url):
        captured["url"] = url
        return _guardian_payload()

    qr = run_provider_query("guardian", topic="fed", transport=cap_transport,
                            env_status_fn=env_present, today="2026-06-22")
    assert qr.secret_exposed is False
    # transport(fake) 경로는 key 없이 URL 구성 — request URL 에 api-key 누출 0.
    assert "api-key" not in captured["url"]
    # result 의 어떤 문자열 필드에도 secret 미포함.
    blob = json.dumps(qr.records) + str(qr.block_reason) + str(qr.next_action)
    assert _SECRET not in blob


def test_06_no_db_write_no_session_param():
    # 구조적 보장: adapter fetch 는 DB session/conn 인자를 받지 않는다(쓰기 경로 부재).
    params = set(inspect.signature(run_provider_query).parameters)
    assert not (params & {"session", "db", "conn", "engine"})


def test_07_contract_no_merge():
    c = provider_adapter_contract()
    assert c["no_merge_without_gold"] is True
    assert "merge" in c["forbidden"]


def test_08_contract_no_llm():
    c = provider_adapter_contract()
    assert c["llm_invoked"] is False
    assert "llm_call" in c["forbidden"]


# ══ Section B — key-required provider (§12 9-16) ═════════════════════════════════════════════════════════
def test_09_missing_credentials_returns_missing_credentials():
    qr = run_provider_query("guardian", topic="x", transport=_boom_transport, env_status_fn=env_missing)
    assert qr.status == "missing_credentials"
    assert qr.records_count == 0
    assert qr.provenance == "none"


def test_10_env_var_name_reported():
    qr = run_provider_query("guardian", topic="x", env_status_fn=env_missing)
    assert "GUARDIAN_API_KEY" in (qr.next_action or "")


def test_11_env_value_hidden():
    # next_action 은 env var **이름**만 — present/missing boolean 외 어떤 값도 노출하지 않는다.
    qr = run_provider_query("guardian", topic="x", env_status_fn=env_missing)
    assert _SECRET not in (qr.next_action or "")
    assert "present" not in (qr.next_action or "") and "missing" not in (qr.next_action or "")


def test_12_fake_transport_success_returns_records():
    qr = run_provider_query("guardian", topic="fed", transport=_guardian_transport,
                            env_status_fn=env_present, today="2026-06-22")
    assert qr.status == "ok"
    assert qr.records_count == 4
    assert qr.provenance == "live_derived"
    # content 검증(tautology 방지·code-review): 파서가 webTitle/webUrl 을 올바른 필드로 매핑.
    assert [r["title_or_label"] for r in qr.records] == [WIRE, WIRE, PARA, DIFF]
    assert qr.records[0]["canonical_url"] == "https://www.theguardian.com/a"
    assert all(r["source_id"] == "guardian" for r in qr.records)


def test_13_parser_error_classified():
    qr = run_provider_query("guardian", topic="x", transport=lambda _u: "not json at all",
                            env_status_fn=env_present)
    assert qr.status == "parser_error"


def test_14_network_error_classified():
    qr = run_provider_query("guardian", topic="x", transport=lambda _u: None,
                            env_status_fn=env_present)
    assert qr.status == "network_error"


def test_15_no_records_classified():
    qr = run_provider_query("guardian", topic="x",
                            transport=lambda _u: _guardian_payload(results=[]),
                            env_status_fn=env_present)
    assert qr.status == "no_records"


def test_16_max_records_bounded():
    many = [{"webTitle": f"t{i}", "webUrl": f"https://g.test/{i}",
             "webPublicationDate": "2026-06-22T12:00:00Z"} for i in range(30)]
    qr = run_provider_query("guardian", topic="x", max_records=3,
                            transport=lambda _u: _guardian_payload(results=many),
                            env_status_fn=env_present)
    assert qr.status == "ok"
    assert qr.records_count == 3   # parser 가 max_records 로 cap.


# ══ Section C — governance / wiring (§12 17-20) ══════════════════════════════════════════════════════════
def test_17_host_gate_blocks_fetch():
    gate = _FakeGate(allowed=False)
    qr = run_provider_query("guardian", topic="x", transport=_boom_transport,
                            env_status_fn=env_present, host_gate=gate)
    assert qr.status == "host_gate_blocked"
    assert gate.calls == []   # 차단 시 record_call 0(no-bypass).


def test_18_host_gate_allowed_records_call():
    gate = _FakeGate(allowed=True)
    qr = run_provider_query("guardian", topic="x", transport=_guardian_transport,
                            env_status_fn=env_present, host_gate=gate)
    assert qr.status == "ok"
    assert gate.calls == ["content.guardianapis.com"]   # 실 HTTP 직전 기록(공유 가시화).


def test_19_unwired_provider_fetcher_not_wired():
    # adapter 미배선 provider 는 fetcher_not_wired(fixture 둔갑 0).
    qr = run_provider_query("newsapi", topic="x", env_status_fn=env_present)
    assert qr.status == "fetcher_not_wired"


def test_20_guardian_error_status_is_parser_error():
    # response.status != ok → None → parser_error(잘못된 결과를 records 로 둔갑 안 함).
    bad = json.dumps({"response": {"status": "error", "message": "bad key"}})
    qr = run_provider_query("guardian", topic="x", transport=lambda _u: bad, env_status_fn=env_present)
    assert qr.status == "parser_error"


def test_21_adapter_descriptor_wired_only():
    d = adapter_descriptor("guardian")
    assert d["fetch_implemented"] is True
    assert d["queue_integration_status"] == "wired"
    assert d["parser_contract_status"] == "implemented"
    assert adapter_descriptor("newsapi") is None   # 미배선 → descriptor 없음.
    assert sorted(ADAPTER_WIRED_PROVIDERS) == ["guardian", "nyt"]   # ADR#64: NYT 2nd adapter wired.


def test_22_max_records_zero_respected_not_default():
    # code-review(falsy-zero): max_records=0 은 명시적 0 으로 존중(adapter 기본 25 로 치환 금지)→0 records→no_records.
    many = [{"webTitle": f"t{i}", "webUrl": f"https://g.test/{i}",
             "webPublicationDate": "2026-06-22T12:00:00Z"} for i in range(5)]
    qr = run_provider_query("guardian", topic="x", max_records=0,
                            transport=lambda _u: _guardian_payload(results=many),
                            env_status_fn=env_present)
    assert qr.records_count == 0
    assert qr.status == "no_records"


# ══ Section D — NYT 2nd adapter (ADR#64 · cross-source pair with Guardian) ════════════════════════════════
def _nyt_payload(results=None):
    if results is None:
        results = [
            {"headline": {"main": WIRE}, "web_url": "https://www.nytimes.com/a",
             "pub_date": "2026-06-22T12:00:00+0000"},
            {"headline": {"main": PARA}, "web_url": "https://www.nytimes.com/b",
             "pub_date": "2026-06-22T13:00:00+0000"},
            {"headline": {"main": DIFF}, "web_url": "https://www.nytimes.com/c",
             "pub_date": "2026-06-22T14:00:00+0000"},
        ]
    return json.dumps({"status": "OK", "response": {"docs": results}})


def _nyt_transport(_url):
    return _nyt_payload()


def test_23_nyt_adapter_wired():
    d = adapter_descriptor("nyt")
    assert d is not None and d["fetch_implemented"] is True
    assert d["queue_integration_status"] == "wired" and d["parser_contract_status"] == "implemented"
    assert "nyt" in ADAPTER_WIRED_PROVIDERS


def test_24_nyt_records_normalized_rec_shape():
    recs = parse_nyt_items(_nyt_payload())
    assert len(recs) == 3
    r = recs[0]
    for k in ("record_type", "source_id", "title_or_label", "canonical_url",
              "published_at_or_observed_at", "body_state_or_signal"):
        assert k in r, f"record missing {k}"
    assert r["source_id"] == "nyt"
    assert r["title_or_label"] == WIRE
    assert r["canonical_url"] == "https://www.nytimes.com/a"
    assert r["published_at_or_observed_at"] == "2026-06-22"   # pub_date ISO→date bucket 정규화.
    assert not ({"body", "content", "raw_payload", "text", "abstract", "lead_paragraph"} & set(r))


def test_25_nyt_missing_credentials_before_network():
    qr = run_provider_query("nyt", topic="x", transport=_boom_transport, env_status_fn=env_missing)
    assert qr.status == "missing_credentials" and qr.records_count == 0
    assert "NYT_API_KEY" in (qr.next_action or "")
    assert _SECRET not in (qr.next_action or "")


def test_26_nyt_fake_transport_success_returns_records():
    qr = run_provider_query("nyt", topic="fed", transport=_nyt_transport,
                            env_status_fn=env_present, today="2026-06-22")
    assert qr.status == "ok" and qr.records_count == 3 and qr.provenance == "live_derived"
    assert [r["title_or_label"] for r in qr.records] == [WIRE, PARA, DIFF]
    assert all(r["source_id"] == "nyt" for r in qr.records)
    assert qr.raw_body_stored is False


def test_27_nyt_parser_error_on_bad_status():
    # status != OK → None → parser_error(잘못된 결과를 records 로 둔갑 안 함).
    bad = json.dumps({"status": "ERROR", "response": {"docs": []}})
    qr = run_provider_query("nyt", topic="x", transport=lambda _u: bad, env_status_fn=env_present)
    assert qr.status == "parser_error"
    qr2 = run_provider_query("nyt", topic="x", transport=lambda _u: "not json", env_status_fn=env_present)
    assert qr2.status == "parser_error"


def test_28_nyt_network_error_and_no_records():
    assert run_provider_query("nyt", topic="x", transport=lambda _u: None,
                              env_status_fn=env_present).status == "network_error"
    empty = json.dumps({"status": "OK", "response": {"docs": []}})
    assert run_provider_query("nyt", topic="x", transport=lambda _u: empty,
                              env_status_fn=env_present).status == "no_records"


def test_29_nyt_max_records_bounded():
    many = [{"headline": {"main": f"t{i}"}, "web_url": f"https://nyt.test/{i}",
             "pub_date": "2026-06-22T12:00:00+0000"} for i in range(30)]
    qr = run_provider_query("nyt", topic="x", max_records=3,
                            transport=lambda _u: _nyt_payload(results=many), env_status_fn=env_present)
    assert qr.status == "ok" and qr.records_count == 3


def test_30_nyt_url_keyless_and_date_yyyymmdd():
    # NYT date 형식 YYYYMMDD(대시 제거)·api-key 는 URL 에 절대 없음(keyless·httpx params 전용).
    captured = {}

    def cap_transport(url):
        captured["url"] = url
        return _nyt_payload()

    qr = run_provider_query("nyt", topic="fed rate", transport=cap_transport,
                            env_status_fn=env_present, time_window="7d", today="2026-06-22")
    assert qr.status == "ok" and qr.secret_exposed is False
    url = captured["url"]
    assert "api-key" not in url and _SECRET not in url
    assert "begin_date=20260615" in url and "end_date=20260622" in url   # YYYYMMDD·대시 제거.
    assert "q=fed+rate" in url or "q=fed%20rate" in url


def test_31_nyt_headline_string_or_missing_or_malformed_handled():
    # headline 이 문자열/누락/**malformed(list·숫자)**여도 크래시 없이 안전(빈 title 은 skip).
    # code-review MEDIUM: headline 이 list/int 면 `.strip()` AttributeError 가 run_provider_query 까지 전파되던 것 방지.
    results = [
        {"headline": "Plain string headline form", "web_url": "https://nyt.test/s",
         "pub_date": "2026-06-22T00:00:00+0000"},
        {"headline": {"main": ""}, "web_url": "https://nyt.test/empty", "pub_date": "2026-06-22"},
        {"web_url": "https://nyt.test/nohl", "pub_date": "2026-06-22"},
        {"headline": ["a", "b"], "web_url": "https://nyt.test/list", "pub_date": "2026-06-22"},
        {"headline": 123, "web_url": "https://nyt.test/int", "pub_date": "2026-06-22"},
    ]
    recs = parse_nyt_items(_nyt_payload(results=results))   # malformed 도 예외 없이 skip.
    assert len(recs) == 1 and recs[0]["title_or_label"] == "Plain string headline form"
    # run_provider_query 경로에서도 malformed doc 이 전체 쿼리를 깨지 않음(graceful).
    qr = run_provider_query("nyt", topic="x", transport=lambda _u: _nyt_payload(results=results),
                            env_status_fn=env_present)
    assert qr.status == "ok" and qr.records_count == 1


# ══ Section D — ADR#84 date-pin window enforcement (enforce_window·opt-in·additive) ══════════════════════
def _guardian_mixed_window_payload():
    # window [2026-06-25, 2026-06-26]: in-window 2 + out-of-window 2(6/28 최신 — provider 가 date 필터 무시 시 반환).
    return _guardian_payload(results=[
        {"webTitle": WIRE, "webUrl": "https://www.theguardian.com/in1",
         "webPublicationDate": "2026-06-25T09:00:00Z"},
        {"webTitle": PARA, "webUrl": "https://www.theguardian.com/in2",
         "webPublicationDate": "2026-06-26T10:00:00Z"},
        {"webTitle": DIFF, "webUrl": "https://www.theguardian.com/out1",
         "webPublicationDate": "2026-06-28T11:00:00Z"},
        {"webTitle": "Unrelated newest world cup live blog", "webUrl": "https://www.theguardian.com/out2",
         "webPublicationDate": "2026-06-28T12:00:00Z"},
    ])


def test_32_enforce_window_false_keeps_all_records():
    # 기본 enforce_window=False → ADR#62~#82 동작 보존(provider 반환 전체 유지·필터 0).
    qr = run_provider_query("guardian", topic="x", transport=lambda _u: _guardian_mixed_window_payload(),
                            env_status_fn=env_present, today="2026-06-26")
    assert qr.status == "ok" and qr.records_count == 4


def test_33_enforce_window_drops_out_of_window_records():
    # enforce_window=True → [2026-06-25, 2026-06-26] 밖(6/28) record drop(provider 가 window 무시해도 adapter 강제).
    qr = run_provider_query("guardian", topic="x", transport=lambda _u: _guardian_mixed_window_payload(),
                            env_status_fn=env_present, today="2026-06-26", enforce_window=True)
    assert qr.status == "ok" and qr.records_count == 2
    for r in qr.records:
        assert r["published_at_or_observed_at"] in ("2026-06-25", "2026-06-26")


def test_34_enforce_window_all_out_of_window_distinct_block_reason():
    # provider 가 window 밖(최신) 기사만 반환 → enforce_window 가 전부 drop → no_in_window_records(진짜 0 과 구분).
    out_only = _guardian_payload(results=[
        {"webTitle": WIRE, "webUrl": "https://www.theguardian.com/o1", "webPublicationDate": "2026-06-28T09:00:00Z"},
        {"webTitle": DIFF, "webUrl": "https://www.theguardian.com/o2", "webPublicationDate": "2026-06-29T10:00:00Z"},
    ])
    qr = run_provider_query("guardian", topic="x", transport=lambda _u: out_only,
                            env_status_fn=env_present, today="2026-06-26", enforce_window=True)
    assert qr.status == "no_records" and qr.block_reason == "no_in_window_records"
    # 진짜 0 records(provider 빈 응답)는 일반 no_records — block_reason 으로 두 사유를 정직 구분.
    qr2 = run_provider_query("guardian", topic="x", transport=lambda _u: _guardian_payload(results=[]),
                             env_status_fn=env_present, today="2026-06-26", enforce_window=True)
    assert qr2.status == "no_records" and qr2.block_reason == "no_records"


# ── ADR#85 통제실험 가산 knob(omit_date_window·order) — default byte-identity 보존 + variant 구성 ──────────────
def test_35_guardian_url_default_byte_identical():
    # default(knob 미사용) URL 은 ADR#62~#84 와 param 순서·값이 동일(date param 포함·order-by=newest).
    u = _guardian_url("https://e", topic="q x", from_date="2026-06-25", to_date="2026-06-26", max_records=25)
    assert u == "https://e?q=q+x&from-date=2026-06-25&to-date=2026-06-26&page-size=25&order-by=newest"


def test_36_guardian_url_omit_date_window_drops_date_params():
    # omit_date_window=True → from-date/to-date 가 URL 에서 빠진다(date-param 유/무 대조군). order-by 는 유지.
    u = _guardian_url("https://e", topic="q", from_date="2026-06-25", to_date="2026-06-26",
                      max_records=25, omit_date_window=True)
    assert "from-date=" not in u and "to-date=" not in u and "order-by=newest" in u


def test_37_guardian_url_order_override():
    # order='relevance' → order-by=relevance(newest-지배 가설 분리). date param 은 그대로.
    u = _guardian_url("https://e", topic="q", from_date="2026-06-25", to_date="2026-06-26",
                      max_records=25, order="relevance")
    assert "order-by=relevance" in u and "from-date=2026-06-25" in u


def test_38_nyt_url_default_and_knobs():
    # NYT default byte-identical(begin/end·sort=newest); omit_date_window 는 begin/end 제외; order override.
    d = _nyt_url("https://e", topic="q x", from_date="2026-06-25", to_date="2026-06-26", max_records=25)
    assert d == "https://e?q=q+x&begin_date=20260625&end_date=20260626&sort=newest"
    nod = _nyt_url("https://e", topic="q", from_date="2026-06-25", to_date="2026-06-26",
                   max_records=25, omit_date_window=True)
    assert "begin_date=" not in nod and "end_date=" not in nod and "sort=newest" in nod
    rel = _nyt_url("https://e", topic="q", from_date="2026-06-25", to_date="2026-06-26",
                   max_records=25, order="relevance")
    assert "sort=relevance" in rel


def test_39_run_provider_query_forwards_knobs_to_request_url():
    # run_provider_query 가 knob 을 실제 요청 URL(transport 가 받는 url)로 전달하는지 — secret 0·키 불요.
    seen = {}

    def cap(u):
        seen["url"] = u
        return _guardian_payload(results=[])

    run_provider_query("guardian", topic="x y", transport=cap, env_status_fn=env_present,
                       today="2026-06-26", omit_date_window=True, order="relevance")
    assert "from-date=" not in seen["url"] and "to-date=" not in seen["url"]
    assert "order-by=relevance" in seen["url"]
    assert _SECRET not in seen["url"]   # key 값은 url 에 절대 미포함(keyless·secret hygiene).


# ══ Section E — Federal Register 3rd adapter (ADR#86 · key-free official · window-honoring date filter) ══════
def _fr_payload(results=None, count=None):
    if results is None:
        results = [
            {"title": "Rule on Asylum Eligibility and Border Procedures",
             "html_url": "https://www.federalregister.gov/documents/2026/06/25/x1",
             "publication_date": "2026-06-25", "abstract": "SHOULD NOT BE STORED",
             "document_number": "2026-13001"},
            {"title": "Notice of Final Agency Action on Metering",
             "html_url": "https://www.federalregister.gov/documents/2026/06/26/x2",
             "publication_date": "2026-06-26", "abstract": "SHOULD NOT BE STORED",
             "document_number": "2026-13002"},
        ]
    return json.dumps({"count": count if count is not None else len(results), "results": results})


def test_40_federal_register_adapter_dispatch_and_role_separation():
    # FR 은 dispatch 전체(ALL_ADAPTER_PROVIDERS)에는 있으나 news 페어링(ADAPTER_WIRED_PROVIDERS)엔 없다(§9 role 분리).
    assert "federal_register" in ALL_ADAPTER_PROVIDERS
    assert "federal_register" not in ADAPTER_WIRED_PROVIDERS
    assert sorted(ADAPTER_WIRED_PROVIDERS) == ["guardian", "nyt"]   # news 페어링 set 불변(byte-보존).
    d = adapter_descriptor("federal_register")
    assert d is not None and d["fetch_implemented"] is True   # _ADAPTERS 등재 → descriptor 존재.


def test_41_federal_register_url_has_explicit_date_range_filter():
    from urllib.parse import unquote
    u = _federal_register_url("https://e", topic="scotus asylum metering",
                              from_date="2026-06-25", to_date="2026-06-26", max_records=5)
    dec = unquote(u)
    assert "conditions[term]=scotus" in dec
    assert "conditions[publication_date][gte]=2026-06-25" in dec   # 명시적 official 범위 필터(gte/lte).
    assert "conditions[publication_date][lte]=2026-06-26" in dec
    assert "per_page=5" in dec and "order=newest" in dec
    assert "fields[]=title" in dec and "fields[]=html_url" in dec   # 본문 미요청 — 메타 필드만.
    assert _SECRET not in u   # key-free — url 에 secret 없음(애초에 key 불요).


def test_42_federal_register_url_knobs_omit_date_and_order():
    from urllib.parse import unquote
    nod = unquote(_federal_register_url("https://e", topic="q", from_date="2026-06-25",
                                        to_date="2026-06-26", max_records=5, omit_date_window=True))
    # date 필터([gte]/[lte])만 빠진다 — fields[]=publication_date(요청 메타 필드)는 그대로(대조군은 필터 유/무).
    assert "[gte]" not in nod and "[lte]" not in nod and "order=newest" in nod
    rel = unquote(_federal_register_url("https://e", topic="q", from_date="2026-06-25",
                                        to_date="2026-06-26", max_records=5, order="relevance"))
    assert "order=relevance" in rel and "conditions[publication_date][gte]=2026-06-25" in rel


def test_43_federal_register_parser_official_role_no_body_stored():
    recs = parse_federal_register_items(_fr_payload())
    assert len(recs) == 2
    for r in recs:
        assert r["record_type"] == "official_record"   # → source_type 'official'(authority 5·anchor-eligible).
        assert r["source_id"] == "federal_register"
        assert r["canonical_url"].startswith("https://www.federalregister.gov/")
        assert r["published_at_or_observed_at"] in ("2026-06-25", "2026-06-26")
        # abstract/본문은 _rec 에 저장 필드가 없음 — raw body 미저장 불변(값이 어디에도 안 새는지).
        assert "SHOULD NOT BE STORED" not in json.dumps(r, ensure_ascii=False)


def test_44_federal_register_key_free_no_credentials_required():
    # FR 은 auth_required=False — env_missing(키 없음)이어도 missing_credentials 로 막히지 않고 fetch 한다(key-free).
    qr = run_provider_query("federal_register", topic="x", transport=lambda _u: _fr_payload(),
                            env_status_fn=env_missing, today="2026-06-26")
    assert qr.status == "ok" and qr.records_count == 2
    assert qr.secret_exposed is False and qr.raw_body_stored is False
    assert qr.provenance == "live_derived"


def test_45_federal_register_enforce_window_drops_out_of_window():
    # provider 가 window 밖 문서를 섞어 반환해도 enforce_window=True 면 [2026-06-25, 2026-06-26] 밖은 drop.
    mixed = _fr_payload(results=[
        {"title": "in-window rule", "html_url": "https://www.federalregister.gov/d/in",
         "publication_date": "2026-06-25", "document_number": "a"},
        {"title": "out-of-window notice", "html_url": "https://www.federalregister.gov/d/out",
         "publication_date": "2026-06-29", "document_number": "b"},
    ])
    qr = run_provider_query("federal_register", topic="x", transport=lambda _u: mixed,
                            env_status_fn=env_missing, today="2026-06-26", enforce_window=True)
    assert qr.status == "ok" and qr.records_count == 1
    assert qr.records[0]["published_at_or_observed_at"] == "2026-06-25"


def test_46_federal_register_parser_error_and_no_records():
    # count 도 results 도 없는 진짜 unexpected shape → None → parser_error(둔갑 0).
    bad = run_provider_query("federal_register", topic="x", transport=lambda _u: json.dumps({"x": 1}),
                             env_status_fn=env_missing)
    assert bad.status == "parser_error"
    # 빈 results → no_records(정직).
    empty = run_provider_query("federal_register", topic="x", transport=lambda _u: _fr_payload(results=[]),
                               env_status_fn=env_missing)
    assert empty.status == "no_records"


def test_47_federal_register_count_zero_omits_results_key_is_no_records():
    # FR 실측(ADR#86 live): count==0 이면 "results" 키를 **생략**하고 {count, description} 만 반환 → parser_error 가
    # 아니라 no_records(정직 분리). count 키 존재가 정상 빈 응답의 신호.
    zero = json.dumps({"count": 0, "description": "Documents matching your search"})
    assert parse_federal_register_items(zero) == []
    qr = run_provider_query("federal_register", topic="x", transport=lambda _u: zero,
                            env_status_fn=env_missing)
    assert qr.status == "no_records" and qr.block_reason == "no_records"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

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
    ProviderQueryResult,
    adapter_descriptor,
    parse_guardian_items,
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
    assert sorted(ADAPTER_WIRED_PROVIDERS) == ["guardian"]


def test_22_max_records_zero_respected_not_default():
    # code-review(falsy-zero): max_records=0 은 명시적 0 으로 존중(adapter 기본 25 로 치환 금지)→0 records→no_records.
    many = [{"webTitle": f"t{i}", "webUrl": f"https://g.test/{i}",
             "webPublicationDate": "2026-06-22T12:00:00Z"} for i in range(5)]
    qr = run_provider_query("guardian", topic="x", max_records=0,
                            transport=lambda _u: _guardian_payload(results=many),
                            env_status_fn=env_present)
    assert qr.records_count == 0
    assert qr.status == "no_records"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

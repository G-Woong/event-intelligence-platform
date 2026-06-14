"""Phase E-2: source artifact 선택 — 가장 많이 분해되는 artifact를 고른다(0분해 회피).

소스마다 decompose 가능한 artifact가 raw vs extracted로 다른 문제(예: HN raw=id리스트 vs
extracted={items})를 source-agnostic하게 해결한다.
"""
from __future__ import annotations

from ingestion.tools.run_source_body_audit import _select_best_artifact


def test_picks_decomposable_artifact_over_id_list(tmp_path):
    id_list = tmp_path / "raw_idlist.json"
    id_list.write_text("[1, 2, 3, 4, 5]", encoding="utf-8")  # topstories id 리스트 → 0분해
    items = tmp_path / "extracted_items.json"
    items.write_text(
        '{"items": [{"title": "a", "url": "https://x/a"}, {"title": "b", "url": "https://x/b"}]}',
        encoding="utf-8")
    text, path, fmt = _select_best_artifact(
        [(id_list, "json"), (items, "json")],
        source_id="hacker_news", confirmation_policy="unconfirmed_until_corroborated")
    assert path == items  # 분해되는 쪽 선택
    assert "items" in text


def test_all_zero_returns_first_readable(tmp_path):
    a = tmp_path / "a.json"
    a.write_text("[1,2,3]", encoding="utf-8")
    b = tmp_path / "b.json"
    b.write_text("[4,5,6]", encoding="utf-8")
    text, path, fmt = _select_best_artifact(
        [(a, "json"), (b, "json")], source_id="x", confirmation_policy=None)
    # 모두 0분해 → 첫 readable 반환(audit가 0분해 사유를 정직하게 기록하도록)
    assert path == a


def test_empty_candidates_returns_none(tmp_path):
    text, path, fmt = _select_best_artifact([], source_id="x", confirmation_policy=None)
    assert text is None and path is None


# ── source-scoped adapters (E2-12): 전역 인플레 없이 특정 소스만 매핑 ──
def test_opendart_adapter_maps_disclosure_records():
    from ingestion.orchestration.artifact_parser import parse_artifact_text
    payload = ('{"list": [{"corp_name": "테스트", "report_nm": "분기보고서", '
               '"rcept_no": "20260101000001", "rcept_dt": "20260101"}], "total_count": 1}')
    cands, parser, _ = parse_artifact_text(
        payload, source_id="opendart", fmt="json", confirmation_policy="evidence_required")
    assert parser == "adapter:opendart"
    assert len(cands) == 1
    assert cands[0].title == "테스트 분기보고서"
    assert "rcpNo=20260101000001" in cands[0].source_url
    assert cands[0].published_at == "20260101"
    assert cands[0].numeric_payload_exempt is False  # 공식 record는 numeric 아님


def test_coinbase_adapter_reduces_to_single_numeric_signal():
    from ingestion.orchestration.artifact_parser import parse_artifact_text
    payload = '{"products": [{"id": "BTC-USD"}, {"id": "ETH-USD"}, {"id": "SOL-USD"}]}'
    cands, parser, _ = parse_artifact_text(
        payload, source_id="coinbase_market", fmt="json")
    assert parser == "adapter:coinbase_market"
    # 인플레 금지: 3 products → 단일 신호 1건
    assert len(cands) == 1
    assert cands[0].numeric_payload_exempt is True
    assert "n=3" in cands[0].title


def test_adapter_not_applied_to_other_sources():
    # opendart 어댑터는 opendart에만 — 다른 소스의 {"list":...}는 generic 처리(전역 인플레 방지)
    from ingestion.orchestration.source_adapters import adapt_source_payload
    assert adapt_source_payload("its", {"list": [{"a": 1}]}) is None
    assert adapt_source_payload("unknown_src", {"products": [{"id": "x"}]}) is None


def test_binance_list_reduced_to_single_signal():
    # 거래소 ticker 수천 행([{...}]) → 단일 numeric 신호(인플레 금지, coinbase와 동일 원칙)
    from ingestion.orchestration.artifact_parser import parse_artifact_text
    payload = ('[{"symbol": "BTCUSDT", "lastPrice": "64000"}, '
               '{"symbol": "ETHUSDT", "lastPrice": "3400"}, '
               '{"symbol": "SOLUSDT", "lastPrice": "150"}]')
    cands, parser, _ = parse_artifact_text(payload, source_id="binance_market", fmt="json")
    assert parser == "adapter:binance_market"
    assert len(cands) == 1          # 3 ticker → 단일 신호
    assert cands[0].numeric_payload_exempt is True
    assert "n=3" in cands[0].title


def test_other_list_source_not_reduced():
    # binance 외 list 소스는 generic_json_list 유지(전역 환원 아님)
    from ingestion.orchestration.artifact_parser import parse_artifact_text
    payload = '[{"title": "a", "url": "https://x/a"}, {"title": "b", "url": "https://x/b"}]'
    cands, parser, _ = parse_artifact_text(payload, source_id="some_news", fmt="json")
    assert parser == "generic_json_list"
    assert len(cands) == 2

"""E-3: unresolved killer 통합 보증 — NEEDS_*가 final로 남지 않음(network 0).

killer가 조합하는 핵심 경로(parse adapter → classify → finalize)를 합성 payload로 검증한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from ingestion.orchestration.artifact_parser import parse_artifact_text
from ingestion.orchestration.full_source_revival import (
    DATA_ALIVE_STATUSES,
    RevivalEvidence,
    TERMINAL_BLOCKED_STATUSES,
    classify_final_status,
    finalize_unresolved_status,
)
from ingestion.tools.run_source_body_audit import _load_unresolved_before


@dataclass
class _Ladder:
    status: str = "NO_BODY"
    paywall_marker: bool = False
    login_marker: bool = False
    captcha_marker: bool = False
    http_status: Optional[int] = 200
    tool_unavailable: bool = False


def _evidence_from(cands):
    return RevivalEvidence(
        candidate_count=len(cands),
        title_present=sum(1 for c in cands if c.title),
        url_present=sum(1 for c in cands if c.source_url),
        published_present=sum(1 for c in cands if c.published_at),
        structured_signal=sum(1 for c in cands if c.numeric_payload_exempt),
        parser_name=(cands[0].parser_name if cands else None),
    )


def _resolve(source_id, group, payload, *, fmt="json", ladder=None):
    """killer가 source별로 수행하는 parse→classify→finalize를 재현."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    cands, _name, _errs = parse_artifact_text(text, source_id=source_id, fmt=fmt)
    ev = _evidence_from(cands)
    fs, rc, na = classify_final_status(
        source_group=group, excluded=False, excluded_reason=None,
        api_readiness_status="present", probe_status="LIVE_SUCCESS",
        artifact_exists=True, evidence=ev)
    fs, rc, na, cls = finalize_unresolved_status(
        source_id=source_id, source_group=group, final_status=fs,
        root_causes=rc, next_action=na, ladder_result=ladder)
    return fs, cls


def test_sec_edgar_resolves_to_official_alive():
    payload = {"hits": {"hits": [{"_id": "a:b", "_source": {
        "display_names": ["X"], "form": "8-K", "adsh": "0000-00-000001",
        "ciks": ["1"], "file_date": "2026-06-12"}}]}}
    fs, cls = _resolve("sec_edgar", "official", payload)
    assert fs == "OFFICIAL_RECORD_ALIVE"


def test_its_resolves_to_not_service_useful():
    payload = {"body": {"items": [{"roadName": "r", "speed": "1"} for _ in range(100)]}}
    fs, cls = _resolve("its", "domain", payload)
    assert fs == "NOT_SERVICE_USEFUL" and cls == "source_override"


def test_twelve_data_resolves_to_structured_signal():
    payload = {"meta": {"symbol": "A"}, "values": [{"datetime": "2026-06-12", "close": "1"}]}
    fs, cls = _resolve("twelve_data", "market", payload)
    assert fs == "STRUCTURED_SIGNAL_ALIVE"


def test_serper_resolves_to_search_result():
    payload = {"organic": [{"title": "t", "link": "https://x.test/a"}]}
    fs, cls = _resolve("serper", "search", payload)
    assert fs == "SEARCH_RESULT_ALIVE"


def test_news_paywall_resolves_to_blocked_no_bypass():
    # 본문이 안 풀리고 paywall 마커 → no bypass terminal
    payload = {"items": []}  # 0 candidate → 뉴스 NEEDS, ladder가 결정
    fs, cls = _resolve("nyt", "news", payload, ladder=_Ladder(paywall_marker=True))
    assert fs == "PAYWALL_BLOCKED_NO_BYPASS"


def test_kma_eia_bok_resolve_to_terminal_not_needs():
    for sid, payload, expected in [
        ("kma", {"response": {"header": {"resultCode": "10"}}}, "EXTERNAL_API_ERROR_WITH_EVIDENCE"),
        ("eia", {"response": {"routes": [{"id": "coal"}]}}, "REQUIRES_VENDOR_SPECIFIC_API_CONTRACT"),
        ("bok_ecos", {"StatisticTableList": {"row": [{"STAT_NAME": "x"}]}}, "REQUIRES_VENDOR_SPECIFIC_API_CONTRACT"),
    ]:
        fs, cls = _resolve(sid, "official", payload)
        assert fs == expected
        assert "NEEDS_" not in fs


def test_no_category_remains_needs_after_killer():
    cases = [
        ("sec_edgar", "official", {"hits": {"hits": [{"_id": "a", "_source": {
            "display_names": ["X"], "form": "8-K", "adsh": "0-0-1", "ciks": ["1"],
            "file_date": "2026-06-12"}}]}}, None),
        ("its", "domain", {"body": {"items": [{"a": 1}]}}, None),
        ("kma", "official", {"response": {"header": {"resultCode": "10"}}}, None),
        ("nyt", "news", {"items": []}, _Ladder(status="HTTP_ERROR", http_status=403)),
        ("ap_news", "news", {"items": []}, _Ladder(status="SUCCESS")),
    ]
    for sid, grp, payload, ladder in cases:
        fs, _cls = _resolve(sid, grp, payload, ladder=ladder)
        assert "NEEDS_" not in fs, f"{sid} still NEEDS: {fs}"
        assert fs in (DATA_ALIVE_STATUSES | TERMINAL_BLOCKED_STATUSES)


def test_load_unresolved_before_shape():
    # 실제 직전 full_source_revival run에서 unresolved-before를 읽는다(있으면 형태 검증).
    before, path = _load_unresolved_before()
    assert isinstance(before, dict)
    for sid, info in before.items():
        assert "previous_status" in info
        assert ("UNRESOLVED" in info["previous_status"]
                or "RATE_LIMITED" in info["previous_status"])

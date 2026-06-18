from __future__ import annotations

from datetime import datetime

from backend.app.schemas.events import RawEvent
from agents.nodes.evidence_check import evidence_check
from agents.nodes.evidence_rules import is_valid_evidence_url, has_grounded_evidence


def _state(url: str) -> dict:
    raw = RawEvent(
        source="test",
        url=url,
        fetched_at=datetime.utcnow(),
        raw_text="body",
        raw_metadata={},
    )
    return {"raw": raw}


def test_real_https_url_becomes_evidence():
    result = evidence_check(_state("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"))
    assert result["evidence"] == ["https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"]
    assert has_grounded_evidence(result["evidence"]) is True


def test_missing_url_yields_empty_evidence():
    result = evidence_check(_state(""))
    assert result["evidence"] == []
    assert has_grounded_evidence(result["evidence"]) is False


def test_mock_marker_rejected():
    assert is_valid_evidence_url("[mock-source-1]") is False
    assert is_valid_evidence_url("mock://source") is False
    assert is_valid_evidence_url("https://mock.local/x") is False


def test_local_and_synthetic_rejected():
    assert is_valid_evidence_url("http://localhost:8000/x") is False
    assert is_valid_evidence_url("http://127.0.0.1/x") is False
    assert is_valid_evidence_url("file:///etc/passwd") is False
    assert is_valid_evidence_url("/tmp/local/path") is False


def test_non_http_scheme_rejected():
    assert is_valid_evidence_url("ftp://data.org/feed") is False
    assert is_valid_evidence_url("javascript:alert(1)") is False
    assert is_valid_evidence_url("data:text/html,<b>x</b>") is False


def test_private_and_metadata_ips_rejected():
    # SSRF/메타데이터/사설/loopback IP는 검증된 근거로 인정 금지
    assert is_valid_evidence_url("http://10.0.0.1/x") is False
    assert is_valid_evidence_url("http://192.168.1.1/x") is False
    assert is_valid_evidence_url("http://172.16.0.5/x") is False
    assert is_valid_evidence_url("http://169.254.169.254/latest/meta-data") is False
    assert is_valid_evidence_url("http://[::1]/x") is False
    assert is_valid_evidence_url("http://0.0.0.0/x") is False


def test_reserved_placeholder_domains_rejected():
    # RFC2606 예약 도메인/TLD는 문서/예시용 — 근거 부적격
    assert is_valid_evidence_url("https://example.com/a") is False
    assert is_valid_evidence_url("https://example.org/a") is False
    assert is_valid_evidence_url("https://foo.test/a") is False
    assert is_valid_evidence_url("https://bar.invalid/a") is False
    assert is_valid_evidence_url("https://real.example/article") is False


def test_public_domain_accepted():
    # 공개 실 도메인은 정상 인정
    assert is_valid_evidence_url("https://www.reuters.com/markets/x") is True
    assert is_valid_evidence_url("https://www.sec.gov/x") is True
    assert is_valid_evidence_url("http://8.8.8.8/x") is True  # 공개 IP는 허용


def test_old_mock_markers_no_longer_grounded():
    # 회귀: 과거 evidence_check 고정 mock은 더 이상 근거로 인정되지 않는다.
    assert has_grounded_evidence(["[mock-source-1]", "[mock-source-2]"]) is False

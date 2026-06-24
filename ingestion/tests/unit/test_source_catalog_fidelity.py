"""R-SourceCatalogFidelity(ADR#40) — catalog 메타데이터 소스가 official_record 로 새지 않음을 잠근다.

문제: `run_production_orchestration._GROUP_TO_RECORD_TYPE` 가 domain→official_record 라,
catalog 6종(전부 source_group="domain")이 official_record→publishable "official" Event 로 발행될 수 있었다.
수정: source_content_type(콘텐츠 분류 단일 출처)이 catalog_metadata 로 분류하는 소스는 group 매핑보다
우선해 비-publishable catalog_metadata record_type 으로 둔다. non-catalog domain 소스는 무변경.
"""
from __future__ import annotations

import pytest

from ingestion.orchestration.full_source_revival import _VALID_RECORD_TYPES, check_eventqueue_readiness
from ingestion.orchestration.source_content_type import content_type
from ingestion.orchestration.source_profile import SourceProfile
from ingestion.tools.run_production_orchestration import _record_type_for

_CATALOG = ("aladin", "tmdb", "kofic", "kopis", "tour", "igdb")


class _Cand:
    """_record_type_for 가 보는 최소 candidate(numeric_payload_exempt 만 확인)."""
    numeric_payload_exempt = False


@pytest.mark.parametrize("sid", _CATALOG)
def test_catalog_source_maps_to_catalog_metadata_not_official_record(sid):
    # 핵심 회귀 잠금: catalog(domain) → catalog_metadata, **official_record 아님**.
    p = SourceProfile(source_id=sid, source_group="domain")
    rt = _record_type_for(p, _Cand())
    assert rt == "catalog_metadata"
    assert rt != "official_record"


def test_non_catalog_domain_keeps_group_mapping():
    # culture_info(domain, _DETAIL=detail)는 catalog 아님 → group 매핑(official_record) 유지(회귀 0).
    assert content_type("culture_info", "domain") != "catalog_metadata"
    p = SourceProfile(source_id="culture_info", source_group="domain")
    assert _record_type_for(p, _Cand()) == "official_record"


def test_other_groups_record_type_unchanged():
    assert _record_type_for(SourceProfile(source_id="bbc", source_group="news"), _Cand()) == "article_candidate"
    assert _record_type_for(SourceProfile(source_id="sec_edgar", source_group="official"), _Cand()) == "official_record"
    assert _record_type_for(SourceProfile(source_id="coinbase", source_group="market"), _Cand()) == "structured_signal"
    assert _record_type_for(SourceProfile(source_id="hacker_news", source_group="community"), _Cand()) == "community_signal"


def test_numeric_exempt_still_structured_signal():
    class _NumCand:
        numeric_payload_exempt = True
    # catalog 라도 numeric_payload_exempt 면 structured_signal(기존 우선순위 보존).
    p = SourceProfile(source_id="tmdb", source_group="domain")
    assert _record_type_for(p, _NumCand()) == "structured_signal"


def test_catalog_metadata_is_valid_record_type():
    # full_source_revival allowlist — catalog_metadata 가 invalid 로 거부되지 않음.
    assert "catalog_metadata" in _VALID_RECORD_TYPES
    ready, gaps = check_eventqueue_readiness({
        "record_type": "catalog_metadata", "source_id": "tmdb",
        "title_or_label": "Some Movie", "source_url_or_evidence": "https://tmdb/x",
        "published_at_or_observed_at": "2026-06-01",
    })
    assert "invalid_record_type" not in gaps

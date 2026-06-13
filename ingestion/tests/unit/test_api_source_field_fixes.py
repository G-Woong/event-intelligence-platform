"""08 API 소스 보강 단위 테스트 — federal_register/igdb/culture_info/hacker_news/
bok_ecos/eia/its/numeric signal. fixture payload는 실제 raw artifact 최소 발췌(네트워크 0회).
"""
import os

os.environ.setdefault("INGESTION_RATE_LIMIT_BACKEND", "memory")


# ── §1 federal_register fields[] ─────────────────────────────────────────────

def test_federal_register_requests_five_fields():
    from ingestion.probes.api_probe import _PROBE_SPEC
    fields = _PROBE_SPEC["federal_register"]["extra_params"]["fields[]"]
    assert isinstance(fields, list)
    for f in ("title", "html_url", "publication_date", "abstract", "document_number"):
        assert f in fields


def test_federal_register_sample_maps_url_and_date():
    from ingestion.runners._audit_common import _sample_from_json
    parsed = {"count": 3, "results": [
        {"title": "Arms Sales Notification",
         "html_url": "https://www.federalregister.gov/documents/2026/06/15/x",
         "publication_date": "2026-06-15", "document_number": "2026-119"},
    ]}
    samples = _sample_from_json("federal_register", parsed, 3)
    assert samples[0]["title"] == "Arms Sales Notification"
    assert samples[0]["url"].startswith("https://www.federalregister.gov")
    assert samples[0]["published_at"] == "2026-06-15"


# ── §2 igdb $root + epoch ────────────────────────────────────────────────────

def test_igdb_requests_url_field():
    from ingestion.probes.api_probe import _PROBE_SPEC
    assert "url" in _PROBE_SPEC["igdb"]["apicalypse_body"]


def test_igdb_root_list_sample_mapping():
    from ingestion.runners._audit_common import _sample_from_json
    parsed = [
        {"id": 10631, "first_release_date": 1236038400,
         "name": "Picross 3D", "rating": 80.4, "url": "https://www.igdb.com/games/picross-3d"},
    ]
    samples = _sample_from_json("igdb", parsed, 3)
    assert len(samples) == 1
    assert samples[0]["title"] == "Picross 3D"
    assert samples[0]["url"] == "https://www.igdb.com/games/picross-3d"
    assert samples[0]["published_at"] == "2009-03-03"  # epoch → ISO


def test_normalize_epoch_converts_only_large_ints():
    from ingestion.runners._audit_common import _normalize_epoch
    assert _normalize_epoch(1236038400) == "2009-03-03"
    assert _normalize_epoch(5) == 5  # 작은 값은 변환하지 않음
    assert _normalize_epoch("2026-06-15") == "2026-06-15"  # 이미 문자열


# ── §3 culture_info XML 필드맵 ───────────────────────────────────────────────

def test_culture_info_xml_field_map():
    from ingestion.runners._audit_common import _sample_from_xml
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><response><body><items>'
        '<item><serviceName>전시</serviceName><seq>375825</seq>'
        '<title>안소니 맥콜 개인전</title><startDate>20260205</startDate>'
        '<endDate>20260614</endDate><place>울산시립미술관</place>'
        '<realmName>전시</realmName></item>'
        '</items></body></response>'
    )
    samples = _sample_from_xml("culture_info", xml, 3)
    assert samples[0]["title"] == "안소니 맥콜 개인전"
    assert samples[0]["published_at"] == "20260205"  # startDate 매핑
    assert samples[0]["snippet"] == "울산시립미술관"  # place 매핑


def test_kopis_xml_regression_unchanged():
    """kopis 기존 거동(.//db, prfpdfrom) 회귀 고정."""
    from ingestion.runners._audit_common import _sample_from_xml
    xml = (
        '<?xml version="1.0"?><dbs>'
        '<db><prfnm>오페라 카르멘</prfnm><prfpdfrom>2026-06-10</prfpdfrom></db>'
        '</dbs>'
    )
    samples = _sample_from_xml("kopis", xml, 3)
    assert samples[0]["title"] == "오페라 카르멘"
    assert samples[0]["published_at"] == "2026-06-10"


# ── §4 hacker_news detail 2차 호출 ───────────────────────────────────────────

class _HNFakeResponse:
    def __init__(self, status_code, json_data, text="[]"):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.headers = {}

    def json(self):
        return self._json


class _HNFakeClient:
    """URL에 /item/ 포함 시 item detail, 아니면 topstories id 목록 반환."""
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, *a, **k):
        if "/item/" in url:
            return _HNFakeResponse(200, {
                "id": 1, "title": "Some HN Story",
                "url": "https://example.com/story", "time": 1718000000, "score": 42,
            }, text='{"id":1}')
        return _HNFakeResponse(200, [101, 102, 103, 104], text="[101,102,103,104]")


def test_hacker_news_detail_fetch_e2e(monkeypatch):
    import httpx
    from ingestion.probes.api_probe import run_api_live_probe
    monkeypatch.setattr(httpx, "Client", lambda **kw: _HNFakeClient(**kw))
    result = run_api_live_probe("hacker_news")
    assert result.status == "LIVE_SUCCESS"
    assert result.items_found == 3  # detail_limit=3
    ep = result.artifact_paths.get("extracted_payload")
    assert ep
    from ingestion.runners._audit_common import extract_sample_items
    samples = extract_sample_items("hacker_news", ep, 3)
    assert samples[0]["title"] == "Some HN Story"
    assert samples[0]["url"] == "https://example.com/story"
    assert samples[0]["published_at"]  # epoch time 변환됨


def test_hacker_news_spec_has_detail_template():
    from ingestion.probes.api_probe import _PROBE_SPEC
    spec = _PROBE_SPEC["hacker_news"]
    assert spec["detail_endpoint_template"].endswith("/item/{id}.json")
    assert spec["detail_limit"] == 3


def test_collect_samples_falls_back_to_extracted_payload(tmp_path):
    """raw가 비면 extracted_payload에서 sample 추출 (hacker_news 경로)."""
    import json
    from ingestion.fetch_strategies.models import ArtifactPaths
    ep = tmp_path / "hn.json"
    ep.write_text(json.dumps({"items": [
        {"title": "HN A", "url": "https://a", "time": 1718000000, "score": 9},
    ]}), encoding="utf-8")

    class _R:
        source_id = "hacker_news"
        artifact_paths = ArtifactPaths(raw_payload=None, extracted_payload=str(ep))
        extraction = None

    from ingestion.runners._audit_common import collect_samples
    samples = collect_samples(_R(), 3)
    assert samples and samples[0]["title"] == "HN A"


# ── §5 bok_ecos / eia / its ──────────────────────────────────────────────────

def test_bok_ecos_sample_mapping():
    from ingestion.runners._audit_common import _sample_from_json
    parsed = {"StatisticTableList": {"list_total_count": 2, "row": [
        {"STAT_CODE": "102Y004", "STAT_NAME": "본원통화 구성내역", "CYCLE": "M"},
        {"STAT_CODE": "0000000001", "STAT_NAME": "통화/금융", "CYCLE": None},
    ]}}
    samples = _sample_from_json("bok_ecos", parsed, 3)
    assert len(samples) == 2
    assert samples[0]["title"] == "본원통화 구성내역"
    assert samples[0]["snippet"] == "M"


def test_eia_sample_mapping():
    from ingestion.runners._audit_common import _sample_from_json
    parsed = {"response": {"routes": [
        {"id": "coal", "name": "Coal", "description": "EIA coal energy data"},
    ]}}
    samples = _sample_from_json("eia", parsed, 3)
    assert samples[0]["title"] == "Coal"
    assert samples[0]["snippet"] == "EIA coal energy data"


def test_its_sample_mapping_and_truncation():
    from ingestion.runners._audit_common import _sample_from_json
    rows = [{"roadName": f"road{i}", "speed": str(i), "createdDate": "20260613023000"}
            for i in range(50)]
    parsed = {"header": {"resultCode": 0}, "body": {"totalCount": 31578, "items": rows}}
    samples = _sample_from_json("its", parsed, 3)
    assert len(samples) == 3  # 3만건이어도 [:max_samples] 절단
    assert samples[0]["title"] == "road0"
    assert samples[0]["published_at"] == "20260613023000"


# ── §6 numeric signal 라벨 ───────────────────────────────────────────────────

def test_numeric_signal_label_for_finnhub():
    from ingestion.runners._audit_common import seed_ready_label_for
    assert seed_ready_label_for("finnhub", 0, 1) == "signal_ready"
    assert seed_ready_label_for("finnhub", 0, 0) == "no"


def test_seed_label_for_news_source_unchanged():
    """비-numeric 소스는 기존 seed_ready_label과 동일 (회귀)."""
    from ingestion.runners._audit_common import seed_ready_label_for, seed_ready_label
    assert seed_ready_label_for("yna", 3, 3) == seed_ready_label(3) == "yes"
    assert seed_ready_label_for("yna", 2, 2) == "partial"
    assert seed_ready_label_for("yna", 1, 1) == "no"


def test_evaluate_seed_uses_probe_items_found_for_flat_numeric():
    """finnhub flat quote는 sample 0건이어도 probe items_found>0이면 signal_ready."""
    from ingestion.runners.run_primary_seed_live_audit import _evaluate_seed
    label, _ = _evaluate_seed("finnhub", [], items_found=1)  # collect_samples 0건
    assert label == "signal_ready"
    label_zero, _ = _evaluate_seed("finnhub", [], items_found=0)
    assert label_zero == "no"

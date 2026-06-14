"""F-9: 시간 정규화 — precision/confidence/warning 정직성(네트워크 0)."""
from __future__ import annotations

from ingestion.orchestration.time_normalizer import (
    normalize_record_times,
    normalize_time,
    summarize_precision,
)


def test_iso8601_datetime_with_tz_high_confidence():
    r = normalize_time("2026-06-14T09:30:00+00:00")
    assert r.precision == "datetime" and r.confidence == "high"
    assert r.value.startswith("2026-06-14T09:30:00")
    assert r.warning is None


def test_iso8601_z_suffix():
    r = normalize_time("2026-06-14T09:30:00Z")
    assert r.precision == "datetime" and r.value.endswith("+00:00")


def test_rfc2822_rss_pubdate():
    r = normalize_time("Mon, 02 Jun 2025 10:00:00 GMT", source_field="published_at")
    assert r.precision == "datetime"
    assert r.source_field == "published_at"
    assert r.value.startswith("2025-06-02T10:00:00")


def test_date_only_keeps_precision_date_not_datetime():
    # 날짜만은 datetime으로 둔갑하지 않는다 — precision=date + warning
    r = normalize_time("2025-06-02")
    assert r.precision == "date"
    assert r.warning == "precision_lost_date_only"
    assert r.confidence == "medium"


def test_month_only_precision_month():
    r = normalize_time("2025-06")
    assert r.precision == "month"
    assert r.warning == "precision_month_only"


def test_timezone_offset_parsed():
    r = normalize_time("2026-06-14T09:30:00+09:00")
    assert r.precision == "datetime"
    # KST 09:30 → UTC 00:30
    assert "00:30:00" in r.value


def test_gdelt_seendate():
    r = normalize_time("20250602T100000Z")
    assert r.precision == "datetime"
    assert r.value.startswith("2025-06-02T10:00:00")


def test_korean_date_pattern():
    r = normalize_time("2025년 6월 2일")
    assert r.precision == "date"
    assert r.value.startswith("2025-06-02")


def test_slash_date_pattern():
    r = normalize_time("2025.06.02")
    assert r.precision == "date" and r.value.startswith("2025-06-02")


def test_bad_date_unrecognized_warning():
    r = normalize_time("not a date at all")
    assert r.value is None and r.precision == "unknown"
    assert r.warning == "unrecognized_format"


def test_missing_date_distinct_from_collected():
    r = normalize_time(None)
    assert r.value is None and r.precision == "unknown" and r.warning == "absent"


def test_structured_signal_prefers_observed_at():
    out = normalize_record_times(
        published_at=None, observed_at="2026-06-14T09:00:00Z",
        collected_at="2026-06-14T12:00:00Z", record_type="structured_signal")
    assert out["primary_kind"] == "observed_at"
    assert out["primary"].value.startswith("2026-06-14T09:00:00")
    # collected_at은 별도로 분리 보관(둔갑 금지)
    assert out["collected"].value.startswith("2026-06-14T12:00:00")


def test_article_prefers_published_at():
    out = normalize_record_times(
        published_at="2026-06-14T08:00:00Z", observed_at=None,
        record_type="article_candidate")
    assert out["primary_kind"] == "published_at"


def test_no_event_time_marked_unknown_not_collected():
    out = normalize_record_times(
        published_at=None, observed_at=None,
        collected_at="2026-06-14T12:00:00Z", record_type="article_candidate")
    assert out["primary"].value is None
    assert out["primary"].warning == "no_event_time"
    assert out["collected"].value is not None  # collected은 별개로 존재


def test_summarize_precision_counts():
    times = [normalize_time("2026-06-14T09:00:00Z"), normalize_time("2025-06-02"),
             normalize_time("bad")]
    s = summarize_precision(times)
    assert s["precision"]["datetime"] == 1
    assert s["precision"]["date"] == 1
    assert s["precision"]["unknown"] == 1
    assert s["warning_count"] >= 2

"""Phase F-9 시간 정규화 (published_at / observed_at / collected_at).

설계 09(품질 게이트) + 05(저장 스키마)의 시간 정밀도 정직성 원칙을 구현한다.
``quality_pre_gate.normalize_published_at``은 ISO/RFC822/GDELT/날짜만을 ISO-8601 UTC로
변환하지만 **정밀도(precision)를 잃는다**(날짜만을 00:00으로 몰래 만든다). 이 모듈은
그 위에 precision/confidence/warning을 얹어 "날짜만"을 datetime으로 둔갑시키지 않는다.

원칙(정직성):
- 날짜만(YYYY-MM-DD)은 value를 자정 UTC ISO로 두되 precision="date"로 명시한다.
- YYYY-MM은 precision="month".
- 파싱 불가/부재는 value=None, precision="unknown"으로 두고 collected_at과 섞지 않는다.
- structured signal은 observed_at, article은 published_at, official record는 filing/report/
  document date를 우선 필드로 본다(어떤 필드에서 왔는지 source_field로 기록).

stdlib만 사용. 신규 설치 0.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

# 시:분(초)까지 있는지 판별 — datetime precision 판정용(콜론 구분/compact 둘 다)
_HAS_TIME = re.compile(r"[T ]\d{2}:?\d{2}")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_ONLY = re.compile(r"^\d{4}-\d{2}$")
_GDELT_SEENDATE = re.compile(r"^(\d{8})T?(\d{6})Z?$")
_GDELT_DATEONLY = re.compile(r"^(\d{8})$")
# 한국식: 2026년 6월 14일 / 2026.06.14 / 2026/06/14
_KO_YMD = re.compile(r"^(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D*$")
_YMD_SLASH = re.compile(r"^(\d{4})[./](\d{1,2})[./](\d{1,2})$")

PRECISION_DATETIME = "datetime"
PRECISION_DATE = "date"
PRECISION_MONTH = "month"
PRECISION_UNKNOWN = "unknown"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"


@dataclass(frozen=True)
class NormalizedTime:
    value: Optional[str]            # ISO-8601 UTC (precision에 따라 자정 포함될 수 있음)
    precision: str                 # datetime | date | month | unknown
    source_field: Optional[str]    # published_at | observed_at | filing_date | ... (입력 필드명)
    confidence: str                # high | medium | low
    warning: Optional[str] = None  # precision_lost_date_only | unrecognized_format | tz_assumed_utc | ...


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def normalize_time(
    raw: Optional[str],
    *,
    source_field: Optional[str] = None,
) -> NormalizedTime:
    """단일 시각 문자열 → NormalizedTime. 없는 값을 지어내지 않고 precision을 정직하게 기록.

    지원: ISO-8601(±tz/Z), RFC822(RSS pubDate), GDELT(YYYYMMDDhhmmss/YYYYMMDD),
    날짜만(YYYY-MM-DD), 월만(YYYY-MM), 한국식/슬래시 날짜(YYYY.MM.DD, YYYY년 M월 D일).
    미지원/빈값은 precision=unknown.
    """
    if raw is None:
        return NormalizedTime(None, PRECISION_UNKNOWN, source_field, CONFIDENCE_LOW, "absent")
    s = str(raw).strip()
    if not s:
        return NormalizedTime(None, PRECISION_UNKNOWN, source_field, CONFIDENCE_LOW, "empty")

    # 월만 (YYYY-MM) — datetime.fromisoformat보다 먼저 판정 (3.11은 YYYY-MM 거부하지만 방어적으로)
    if _MONTH_ONLY.match(s):
        try:
            dt = datetime.strptime(s, "%Y-%m").replace(tzinfo=timezone.utc)
            return NormalizedTime(_utc_iso(dt), PRECISION_MONTH, source_field,
                                  CONFIDENCE_LOW, "precision_month_only")
        except ValueError:
            pass

    # ISO-8601 (Z 허용)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        has_time = bool(_HAS_TIME.search(s))
        precision = PRECISION_DATETIME if has_time else PRECISION_DATE
        tz_warn = None if dt.tzinfo else "tz_assumed_utc"
        warning = tz_warn if has_time else "precision_lost_date_only"
        conf = CONFIDENCE_HIGH if (has_time and dt.tzinfo) else CONFIDENCE_MEDIUM
        return NormalizedTime(_utc_iso(dt), precision, source_field, conf, warning)
    except ValueError:
        pass

    # RFC822 (RSS pubDate) — 항상 시각 포함
    try:
        dt = parsedate_to_datetime(s)
        if dt is not None:
            tz_warn = None if dt.tzinfo else "tz_assumed_utc"
            conf = CONFIDENCE_HIGH if dt.tzinfo else CONFIDENCE_MEDIUM
            return NormalizedTime(_utc_iso(dt), PRECISION_DATETIME, source_field, conf, tz_warn)
    except (TypeError, ValueError):
        pass

    # GDELT seendate (YYYYMMDDhhmmss)
    m = _GDELT_SEENDATE.match(s)
    if m:
        try:
            dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return NormalizedTime(_utc_iso(dt), PRECISION_DATETIME, source_field, CONFIDENCE_HIGH, None)
        except ValueError:
            pass

    # GDELT date only (YYYYMMDD)
    m = _GDELT_DATEONLY.match(s)
    if m:
        try:
            dt = datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
            return NormalizedTime(_utc_iso(dt), PRECISION_DATE, source_field,
                                  CONFIDENCE_MEDIUM, "precision_lost_date_only")
        except ValueError:
            pass

    # 날짜만 (YYYY-MM-DD)
    if _DATE_ONLY.match(s):
        try:
            dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return NormalizedTime(_utc_iso(dt), PRECISION_DATE, source_field,
                                  CONFIDENCE_MEDIUM, "precision_lost_date_only")
        except ValueError:
            pass

    # 슬래시/점 날짜 (YYYY/MM/DD, YYYY.MM.DD) + 한국식 (YYYY년 M월 D일)
    for pat in (_YMD_SLASH, _KO_YMD):
        km = pat.match(s)
        if km:
            try:
                y, mo, d = int(km.group(1)), int(km.group(2)), int(km.group(3))
                dt = datetime(y, mo, d, tzinfo=timezone.utc)
                return NormalizedTime(_utc_iso(dt), PRECISION_DATE, source_field,
                                      CONFIDENCE_MEDIUM, "precision_lost_date_only")
            except (ValueError, OverflowError):
                pass

    return NormalizedTime(None, PRECISION_UNKNOWN, source_field, CONFIDENCE_LOW, "unrecognized_format")


def normalize_record_times(
    *,
    published_at: Optional[str] = None,
    observed_at: Optional[str] = None,
    collected_at: Optional[str] = None,
    record_type: str = "article_candidate",
) -> dict:
    """record_type별 우선 시각 필드를 골라 정규화. published/observed/collected를 분리 반환.

    - structured_signal → observed_at 우선
    - article/official/community/search → published_at 우선
    - 둘 다 없으면 primary=None(unknown)이며 collected_at은 별도로 둔다(둔갑 금지).
    반환: {"primary": NormalizedTime, "primary_kind": str, "published": NT|None,
           "observed": NT|None, "collected": NT|None}
    """
    pub = normalize_time(published_at, source_field="published_at") if published_at is not None else None
    obs = normalize_time(observed_at, source_field="observed_at") if observed_at is not None else None
    col = normalize_time(collected_at, source_field="collected_at") if collected_at is not None else None

    if record_type == "structured_signal":
        primary, kind = (obs or pub), ("observed_at" if obs else "published_at")
    else:
        primary, kind = (pub or obs), ("published_at" if pub else "observed_at")

    if primary is None:
        primary = NormalizedTime(None, PRECISION_UNKNOWN, None, CONFIDENCE_LOW, "no_event_time")
        kind = "none"
    return {
        "primary": primary,
        "primary_kind": kind,
        "published": pub,
        "observed": obs,
        "collected": col,
    }


def summarize_precision(times) -> dict:
    """NormalizedTime 목록 → precision 분포 + warning 카운트(모니터링/보고용)."""
    dist = {PRECISION_DATETIME: 0, PRECISION_DATE: 0, PRECISION_MONTH: 0, PRECISION_UNKNOWN: 0}
    warnings = 0
    for t in times:
        if t is None:
            continue
        dist[t.precision] = dist.get(t.precision, 0) + 1
        if t.warning and t.warning not in ("absent",):
            warnings += 1
    return {"precision": dist, "warning_count": warnings}

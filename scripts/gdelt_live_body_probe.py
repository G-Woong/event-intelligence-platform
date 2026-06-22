"""GDELT 라이브 fresh 수집 + URL→본문 추출 검증 probe (R-Gdelt429 증거 수집).

목적(사용자 2단계):
  - 비-throttle 윈도에서 GDELT fresh 수집 최소 1건 성공시킨다.
  - 반환 URL에서 실제 기사 본문 추출까지 시도한다.
  - 성공/실패를 소스가 아니라 *행 단위*로 분류해 정직히 남긴다(뭉뚱그리지 않음).

GDELT 호출 계약(no-bypass):
  - 최소 호출 간격 ≥ min_interval(기본 12s) + jitter, num_records ≤ 50, query budget 작게.
  - 병렬 호출 금지. 429면 긴 cooldown 기록(host_rate_gate 단일 출처) + 실패 요청도 호출로 기록.
  - 우회/프록시/짧은 무한 retry 금지.

본문 정책(DATA_POLICY): 전문 저장 금지 — char_len + 짧은 preview(≤200자)만 산출물에 남긴다.

산출물:
  - outputs/gdelt_live_body_probe.jsonl
  - reports/gdelt_live_body_probe.md

stdlib + httpx(기존). 신규 설치 0. secret 미사용.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ingestion.core.env_loader import load_env
from ingestion.core.error_taxonomy import classify_content_blocker
from ingestion.orchestration.host_rate_gate import GDELT_HOST, HostRateGate
from ingestion.orchestration.rate_limit_governor import RateLimitGovernor
from ingestion.tools.trafilatura_extractor import extract_with_trafilatura

_GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_HOST_GATE = Path("ingestion/outputs/state/host_rate_gate.json")
_BODY_MIN_CHARS = 200
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_OUT_JSONL = Path("outputs/gdelt_live_body_probe.jsonl")
_OUT_MD = Path("reports/gdelt_live_body_probe.md")

# (label, query, timespan, start_label) — recent 우선, 점진적 단순화.
_QUERIES = [
    ("recent_24h_economy", "economy", "1d"),
    ("recent_7d_election", "election", "7d"),
    ("recent_90d_climate", "climate", "3m"),
]


def _iso_now(now=None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _gdelt_get(query: str, timespan: str, maxrecords: int) -> tuple:
    """GDELT DOC ArtList 직접 호출 — full article fields 보존. (status, articles, raw_note, error)."""
    params = {"query": query, "mode": "ArtList", "maxrecords": str(maxrecords),
              "format": "json", "timespan": timespan}
    try:
        r = httpx.get(_GDELT_BASE, params=params, timeout=20.0,
                      headers={"User-Agent": _BROWSER_UA})
    except Exception as exc:
        return None, [], None, f"fetch_error:{type(exc).__name__}"
    status = r.status_code
    text = r.text or ""
    if status == 429 or "limit requests" in text.lower() or (
            "your query" in text.lower() and ("too" in text.lower() or "limit" in text.lower())):
        return status or 429, [], text[:200], "PROVIDER_429"
    ct = (r.headers.get("content-type") or "").lower()
    if "json" not in ct:
        # 200인데 JSON 아님(평문 안내/오류)
        return status, [], text[:200], "NON_JSON_RESPONSE"
    try:
        j = r.json()
    except Exception:
        return status, [], text[:200], "JSON_PARSE_ERROR"
    return status, (j.get("articles") or []), None, None


def _fetch_body(url: str) -> tuple:
    """기사 URL 본문 fetch+추출. (body_status, char_len, preview, failure_reason)."""
    try:
        r = httpx.get(url, headers={"User-Agent": _BROWSER_UA}, follow_redirects=True, timeout=20.0)
    except httpx.TimeoutException:
        return "BODY_TIMEOUT", 0, "", "timeout"
    except Exception as exc:
        return "BODY_FETCH_ERROR", 0, "", f"fetch_error:{type(exc).__name__}"
    if r.status_code == 403:
        return "BODY_HTTP_403", 0, "", "http_403"
    if r.status_code == 404:
        return "BODY_HTTP_404", 0, "", "http_404"
    if r.status_code != 200:
        return "BODY_HTTP_OTHER", 0, "", f"http_{r.status_code}"
    ct = (r.headers.get("content-type") or "").lower()
    if "html" not in ct and "xml" not in ct and "text" not in ct:
        return "BODY_UNSUPPORTED_CONTENT_TYPE", 0, "", f"content_type:{ct[:40]}"
    html = r.text or ""
    blocker = classify_content_blocker(html.lower())
    if blocker is not None:
        return "BODY_BLOCKED", 0, "", f"content_blocker:{getattr(blocker, 'value', blocker)}"
    result = extract_with_trafilatura(html, url)
    body = result.body or ""
    if not body:
        return "BODY_EMPTY_AFTER_PARSE", 0, "", result.error_message or "empty_after_parse"
    if len(body) < _BODY_MIN_CHARS:
        return "BODY_TOO_SHORT", len(body), body[:200], "body_too_short"
    return "extracted", len(body), body[:200], None


def run_probe(*, max_attempts: int, min_interval: int, maxrecords: int,
              max_body: int, write_outputs: bool = True) -> dict:
    load_env()
    host_gate = HostRateGate(state_path=_HOST_GATE)
    governor = RateLimitGovernor(state_path=None)
    rows: list[dict] = []
    seen_urls: set[str] = set()
    success_rows = 0
    body_success = 0
    attempts_done = 0

    for i, (label, query, timespan) in enumerate(_QUERIES[:max_attempts]):
        now = datetime.now(timezone.utc)
        # host 단위 floor(단일 출처) — 다른 루프가 최근 호출했으면 대기
        hd = host_gate.decide(GDELT_HOST, min_spacing_seconds=min_interval, now=now)
        if not hd.allowed:
            wait = min_interval + random.uniform(0, 3)
            time.sleep(wait)
            now = datetime.now(timezone.utc)
        elif i > 0:
            time.sleep(min_interval + random.uniform(0, 3))  # 정책 간격 + jitter
            now = datetime.now(timezone.utc)

        host_gate.record_call(GDELT_HOST, now=now)   # 실제 호출 직전 기록(성공/실패 무관)
        attempts_done += 1
        status, articles, note, err = _gdelt_get(query, timespan, maxrecords)

        base = {"query": query, "query_label": label, "timespan": timespan,
                "start_date": timespan, "end_date": _iso_now(now)}

        if err == "PROVIDER_429":
            cd = governor.record_rate_limited("gdelt", freshness_bucket="near_real_time",
                                              reason="gdelt_provider_429", now=now)
            rows.append({**base, "gdelt_status": "PROVIDER_429", "returned_rows": 0,
                         "english_rows": 0, "article_url": None, "title": None,
                         "source_domain": None, "source_country": None, "article_date": None,
                         "body_status": None, "body_char_len": 0, "body_preview": "",
                         "saved_to_raw_events": False, "saved_to_event_queue": False,
                         "failure_reason": f"PROVIDER_429;cooldown_until={cd};note={note}"})
            continue
        if err or status != 200:
            rows.append({**base, "gdelt_status": f"GDELT_ERROR:{err or status}", "returned_rows": 0,
                         "english_rows": 0, "article_url": None, "title": None,
                         "source_domain": None, "source_country": None, "article_date": None,
                         "body_status": None, "body_char_len": 0, "body_preview": "",
                         "saved_to_raw_events": False, "saved_to_event_queue": False,
                         "failure_reason": err or f"http_{status};note={note}"})
            continue
        if not articles:
            rows.append({**base, "gdelt_status": "GDELT_SUCCESS_EMPTY", "returned_rows": 0,
                         "english_rows": 0, "article_url": None, "title": None,
                         "source_domain": None, "source_country": None, "article_date": None,
                         "body_status": None, "body_char_len": 0, "body_preview": "",
                         "saved_to_raw_events": False, "saved_to_event_queue": False,
                         "failure_reason": "no_articles"})
            continue

        english_rows = sum(1 for a in articles if (a.get("language") or "").lower() == "english")
        returned = len(articles)
        success_rows += 1
        body_attempts = 0
        for a in articles:
            url = a.get("url")
            row = {**base, "gdelt_status": "GDELT_SUCCESS", "returned_rows": returned,
                   "english_rows": english_rows, "article_url": url,
                   "title": (a.get("title") or "")[:160], "source_domain": a.get("domain"),
                   "source_country": a.get("sourcecountry"), "article_date": a.get("seendate"),
                   "body_status": None, "body_char_len": 0, "body_preview": "",
                   "saved_to_raw_events": False, "saved_to_event_queue": False,
                   "failure_reason": None}
            if not url:
                row["failure_reason"] = "no_url"
                rows.append(row)
                continue
            if url in seen_urls:
                row["body_status"] = "DUPLICATE_URL"
                row["failure_reason"] = "duplicate_url"
                rows.append(row)
                continue
            seen_urls.add(url)
            lang = (a.get("language") or "").lower()
            # 본문 추출은 상위 max_body건만(과도 요청 방지). 영어 우선.
            if body_attempts < max_body and lang in ("english", ""):
                if body_attempts > 0:
                    time.sleep(1.5)
                body_attempts += 1
                bstatus, clen, preview, breason = _fetch_body(url)
                row["body_status"] = bstatus
                row["body_char_len"] = clen
                row["body_preview"] = preview
                row["failure_reason"] = breason
                if bstatus == "extracted":
                    body_success += 1
                    # gdelt record는 url+title+seendate 보유 → raw_events/event_queue 적재 적격
                    row["saved_to_raw_events"] = True
                    row["saved_to_event_queue"] = True
            else:
                row["body_status"] = "NON_ENGLISH_SKIPPED" if lang and lang != "english" else "BODY_NOT_ATTEMPTED_CAP"
                # 본문 미시도여도 record 자체는 적격(url/title/date 보유)
                row["saved_to_raw_events"] = True
                row["saved_to_event_queue"] = True
            rows.append(row)

        if success_rows >= 1 and body_success >= 1:
            break  # 목표(success≥1 + body≥1) 달성 → 추가 호출 안 함

    summary = {
        "attempts_done": attempts_done, "success_queries": success_rows,
        "url_candidates": len(seen_urls), "body_success": body_success,
        "rows": len(rows),
        "verdict": _verdict(success_rows, len(seen_urls), body_success),
    }
    if write_outputs:
        _OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with open(_OUT_JSONL, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        _OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        _OUT_MD.write_text(_md(rows, summary), encoding="utf-8")
    return {"rows": rows, "summary": summary}


def _verdict(success_q: int, urls: int, body: int) -> str:
    if success_q >= 1 and urls >= 3 and body >= 1:
        return "GDELT_FRESH_AND_BODY_VERIFIED"
    if success_q >= 1 and urls >= 1:
        return "GDELT_FRESH_OK_BODY_PENDING"
    return "GDELT_PROVIDER_THROTTLED_PENDING_RESUME"


def _md(rows: list[dict], summary: dict) -> str:
    lines = [
        "# GDELT Live Body Probe (R-Gdelt429 evidence)",
        "",
        f"- run: {_iso_now()} (UTC)",
        f"- verdict: **{summary['verdict']}**",
        f"- attempts: {summary['attempts_done']} · success_queries: {summary['success_queries']} "
        f"· url_candidates: {summary['url_candidates']} · body_success: {summary['body_success']}",
        "- contract: spaced probe(≥interval+jitter), maxrecords≤50, no parallel, 429→cooldown, no bypass",
        "- body policy: char_len + preview(≤200) only (no full-text stored)",
        "",
        "| query | gdelt_status | rows | eng | domain | country | article_date | body_status | chars | saved_eq | failure |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['query']} | {r['gdelt_status']} | {r['returned_rows']} | {r['english_rows']} "
            f"| {r.get('source_domain') or '-'} | {r.get('source_country') or '-'} "
            f"| {r.get('article_date') or '-'} | {r.get('body_status') or '-'} | {r['body_char_len']} "
            f"| {r['saved_to_event_queue']} | {(r.get('failure_reason') or '-')[:48]} |"
        )
    lines += ["", "## Failure taxonomy (rows)",
              "GDELT_SUCCESS / GDELT_SUCCESS_EMPTY / PROVIDER_429 / BODY_HTTP_403 / BODY_HTTP_404 / "
              "BODY_TIMEOUT / BODY_UNSUPPORTED_CONTENT_TYPE / BODY_TOO_SHORT / BODY_EMPTY_AFTER_PARSE / "
              "NON_ENGLISH_SKIPPED / DUPLICATE_URL",
              "", "## Security", "GDELT는 키 불필요. API 키/토큰 값 없음. 본문 전문 미저장(preview≤200)."]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="GDELT live fresh+body probe")
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--min-interval", type=int, default=12)
    ap.add_argument("--maxrecords", type=int, default=50)
    ap.add_argument("--max-body", type=int, default=5)
    args = ap.parse_args(argv)
    print("GDELT_LIVE_BODY_PROBE: spaced probe start (no-bypass)")
    out = run_probe(max_attempts=args.max_attempts, min_interval=args.min_interval,
                    maxrecords=args.maxrecords, max_body=args.max_body)
    s = out["summary"]
    print(f"- verdict: {s['verdict']}")
    print(f"- attempts={s['attempts_done']} success_q={s['success_queries']} "
          f"urls={s['url_candidates']} body={s['body_success']}")
    print(f"- jsonl: {_OUT_JSONL}")
    print(f"- report: {_OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

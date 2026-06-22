"""오케스트레이션 본문 추출 감사 (사용자 5단계).

source probe가 title/url만 저장하는지, 실제 본문까지 들어가는지 소스별로 분리 집계한다:
  - 기사형/공식/커뮤니티: body present / snippet_only / missing + extracted_text 아티팩트
  - 검색/벤더 라우트: URL 후보 확보와 downstream body fetch를 분리 기록
  - 구조화/숫자형: body missing을 실패로 치지 않음(schema/record 수집 성공으로 판정)

데이터원: production_event_queue.jsonl(body_state_or_signal) + extracted_text/ 아티팩트.

산출물:
  - reports/orchestration_body_extraction_audit.md
  - outputs/body_extraction_matrix.csv
"""
from __future__ import annotations

import csv
import json
import collections
from pathlib import Path

_QUEUE = Path("ingestion/outputs/jsonl/production_event_queue.jsonl")
_EXTRACTED = Path("ingestion/outputs/extracted_text")
_OUT_CSV = Path("outputs/body_extraction_matrix.csv")
_OUT_MD = Path("reports/orchestration_body_extraction_audit.md")

# record_type별 본문 기대/판정 규칙
_STRUCTURED_TYPES = {"structured_signal"}          # 본문 비대상(numeric/trend) — missing != 실패
_URL_CANDIDATE_TYPES = {"search_result"}           # URL 후보형 — downstream body 별도
_BODY_TYPES = {"article_candidate", "official_record", "community_signal"}

_COLUMNS = [
    "source_id", "record_type", "body_expected", "queue_records",
    "body_present", "body_snippet_only", "body_missing", "extracted_text_artifacts",
    "body_success_total", "primary_failure_mode", "classification", "notes",
]


def _load_jsonl(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _classify(rtype, present, snippet, missing, extracted) -> tuple:
    body_success = present + extracted
    if rtype in _STRUCTURED_TYPES:
        return "STRUCTURED_NO_BODY_EXPECTED", "n/a_structured", body_success
    if rtype in _URL_CANDIDATE_TYPES:
        return "URL_CANDIDATE_DOWNSTREAM_SEPARATE", ("snippet_only" if snippet else "url_only"), body_success
    # body 기대형
    if body_success > 0:
        return "BODY_OK", "-", body_success
    if snippet > 0 and missing == 0:
        return "SNIPPET_ONLY", "snippet_only_no_fulltext", body_success
    if missing > 0:
        return "BODY_MISSING", "body_missing", body_success
    return "NO_RECORDS", "no_records", body_success


def build() -> dict:
    queue = _load_jsonl(_QUEUE)
    # (source_id, record_type) → body_state Counter
    grid = collections.defaultdict(collections.Counter)
    for r in queue:
        grid[(r.get("source_id"), r.get("record_type"))][r.get("body_state_or_signal")] += 1
    extracted = {}
    if _EXTRACTED.exists():
        for d in _EXTRACTED.iterdir():
            if d.is_dir():
                extracted[d.name] = len(list(d.glob("*.txt")))

    rows = []
    for (sid, rtype), bs in sorted(grid.items()):
        present = bs.get("present", 0)
        snippet = bs.get("snippet_only", 0)
        missing = bs.get("missing", 0)
        structured = sum(v for k, v in bs.items() if k in ("numeric", "trend", "official_record",
                                                           "community_signal", "economic_indicator",
                                                           "energy_price", "weather_observation"))
        ex = extracted.get(sid, 0)
        body_expected = rtype in _BODY_TYPES
        classification, fail, body_success = _classify(rtype, present, snippet, missing, ex)
        total = present + snippet + missing + structured
        rows.append({
            "source_id": sid, "record_type": rtype, "body_expected": body_expected,
            "queue_records": total, "body_present": present, "body_snippet_only": snippet,
            "body_missing": missing, "extracted_text_artifacts": ex,
            "body_success_total": body_success, "primary_failure_mode": fail,
            "classification": classification,
            "notes": ("structured schema collected" if classification == "STRUCTURED_NO_BODY_EXPECTED"
                      else ("url candidate; body fetched downstream" if classification == "URL_CANDIDATE_DOWNSTREAM_SEPARATE"
                            else f"present={present} snippet={snippet} missing={missing} extracted_artifacts={ex}")),
        })
    # extracted_text만 있고 queue엔 없는 소스(본문 추출 레이어 전용 실적)도 보고
    queue_srcs = {sid for (sid, _rt) in grid.keys()}
    extra_only = {s: n for s, n in extracted.items() if s not in queue_srcs and s != "_dummy"}

    cls_counts = collections.Counter(r["classification"] for r in rows)
    return {"rows": rows, "extracted_only": extra_only, "class_counts": dict(cls_counts),
            "extracted_total": sum(extracted.values())}


def _md(data: dict) -> str:
    rows = data["rows"]
    lines = [
        "# Orchestration Body Extraction Audit (5단계)",
        "",
        f"- (source, record_type) rows: {len(rows)} · classification: {data['class_counts']}",
        f"- extracted_text artifacts total: {data['extracted_total']}",
        "",
        "## 판정 규칙",
        "- article_candidate/official_record/community_signal → 본문 기대(present/extracted=성공, snippet_only/missing=미달)",
        "- search_result → URL 후보형(downstream body fetch 별도, snippet_only는 설계상 정상)",
        "- structured_signal(numeric/trend) → 본문 비대상(schema/record 수집 성공으로 판정)",
        "",
        "| source | record_type | body_exp | queue | present | snippet | missing | extracted | success | class |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda x: (-x["queue_records"], x["source_id"])):
        lines.append(
            f"| {r['source_id']} | {r['record_type']} | {r['body_expected']} | {r['queue_records']} "
            f"| {r['body_present']} | {r['body_snippet_only']} | {r['body_missing']} "
            f"| {r['extracted_text_artifacts']} | {r['body_success_total']} | {r['classification']} |")
    if data["extracted_only"]:
        lines += ["", "## extracted_text 전용(큐 미적재) 소스 — 본문 추출 레이어 실적", "",
                  "| source | extracted_artifacts |", "|---|---|"]
        for s, n in sorted(data["extracted_only"].items(), key=lambda x: -x[1]):
            lines.append(f"| {s} | {n} |")
    lines += [
        "",
        "## 핵심 결론(소스별 분리, 뭉뚱그리지 않음)",
        "- 대부분 article_candidate는 **snippet_only**(RSS/검색 메타) — EventQueue 레이어는 URL+요약을 싣고, "
        "전문은 **extracted_text/ 본문 추출 레이어**가 별도 적재(둔갑 아님). 두 레이어를 분리 집계.",
        "- structured_signal은 본문 비대상 — numeric/trend schema 수집 자체가 성공(missing을 실패로 치지 않음).",
        "- search_result는 URL 후보 확보가 1차 성공, 본문은 downstream 기사 fetch에서 별도 판정.",
        "",
        "## Security",
        "본문 전문은 보고서에 미포함(아티팩트 카운트/상태만). API 키/토큰 값 없음.",
    ]
    return "\n".join(lines)


def main() -> int:
    data = build()
    _OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS)
        w.writeheader()
        for r in data["rows"]:
            w.writerow(r)
    _OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    _OUT_MD.write_text(_md(data), encoding="utf-8")
    print(f"BODY_EXTRACTION_AUDIT: rows={len(data['rows'])} classes={data['class_counts']}")
    print(f"- csv: {_OUT_CSV}")
    print(f"- report: {_OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

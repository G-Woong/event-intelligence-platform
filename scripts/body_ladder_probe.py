"""산문형 소스(nyt/opendart/culture_info)에 body ladder 연결 검증 (사용자 2·3단계).

content type이 article/document/detail인 소스만 대상으로, 큐에 적재된 record URL에 실제 body
ladder(`rescue_news_body` = httpx→trafilatura→readability→bs4→browser)를 적용해 본문 추출
가능 여부를 정직하게 판정한다. 카탈로그형(aladin/tmdb/kofic/kopis/tour/igdb)은 대상이 아니다
(metadata-complete — body_extraction_audit 참조).

no-bypass: robots disallow→ROBOTS_BLOCKED, paywall/login/captcha 마커→*_BLOCKED_NO_BYPASS.
본문 정책: body_length(숫자)만 기록, 전문/preview 미저장(no-fulltext).

산출물:
  - reports/body_ladder_probe.md
  - outputs/body_ladder_probe.jsonl
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ingestion.orchestration.body_rescue_ladder import rescue_news_body
from ingestion.orchestration.source_content_type import body_ladder_eligible, content_type

_QUEUE = Path("ingestion/outputs/jsonl/production_event_queue.jsonl")
_PROFILES = "ingestion/configs/source_profiles.yaml"
_TARGETS = ("nyt", "opendart", "culture_info")   # body_ladder_eligible 산문형(검증 대상)
_OUT_JSONL = Path("outputs/body_ladder_probe.jsonl")
_OUT_MD = Path("reports/body_ladder_probe.md")


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _group_map():
    try:
        from ingestion.orchestration.source_profile import load_source_profiles
        return {p.source_id: p.source_group for p in load_source_profiles(_PROFILES)}
    except Exception:
        return {}


def run_probe(*, max_per_source: int = 3, allow_browser: bool = False,
              write_outputs: bool = True) -> dict:
    queue = _load_jsonl(_QUEUE)
    groups = _group_map()
    # 소스별 (url, title) 후보 수집
    cands_by_src: dict[str, list] = {sid: [] for sid in _TARGETS}
    for r in queue:
        sid = r.get("source_id")
        if sid in cands_by_src:
            url = r.get("source_url_or_evidence") or r.get("canonical_url")
            if url and str(url).startswith("http"):
                cands_by_src[sid].append((url, r.get("title_or_label")))

    rows = []
    for sid in _TARGETS:
        grp = groups.get(sid)
        eligible = body_ladder_eligible(sid, grp)
        cands = cands_by_src.get(sid, [])[:max_per_source]
        row = {"source_id": sid, "content_type": content_type(sid, grp),
               "body_ladder_eligible": eligible, "attempted_urls": 0,
               "best_status": None, "readiness_verdict": None, "body_length": 0,
               "paywall": False, "login": False, "captcha": False,
               "sample_urls": [u for u, _t in cands]}
        if not eligible:
            row["readiness_verdict"] = "NOT_ELIGIBLE_METADATA_COMPLETE"
            rows.append(row)
            continue
        if not cands:
            row["readiness_verdict"] = "NO_QUEUE_URL"
            rows.append(row)
            continue
        res = rescue_news_body(cands, source_id=sid, max_candidates=max_per_source,
                               allow_browser=allow_browser)
        row.update(attempted_urls=res.attempted_urls, best_status=res.best_status,
                   readiness_verdict=res.readiness_verdict, body_length=res.body_length,
                   paywall=res.paywall_marker, login=res.login_marker, captcha=res.captcha_marker)
        rows.append(row)

    summary = {
        "targets": list(_TARGETS),
        "body_alive": sum(1 for r in rows if r["readiness_verdict"] in ("ARTICLE_BODY_ALIVE", "ARTICLE_PARTIAL_ALIVE")),
        "blocked_no_bypass": sum(1 for r in rows if r["readiness_verdict"] and "BLOCKED_NO_BYPASS" in r["readiness_verdict"]),
        "no_body": sum(1 for r in rows if r["readiness_verdict"] == "NO_BODY"),
    }
    if write_outputs:
        _OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with open(_OUT_JSONL, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        _OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        _OUT_MD.write_text(_md(rows, summary), encoding="utf-8")
    return {"rows": rows, "summary": summary}


def _md(rows, summary) -> str:
    lines = [
        "# Body Ladder Probe — 산문형 소스(nyt/opendart/culture_info)",
        "",
        f"- run: {_iso_now()} (UTC)",
        f"- body_alive: {summary['body_alive']} · blocked_no_bypass: {summary['blocked_no_bypass']} "
        f"· no_body: {summary['no_body']}",
        "- ladder: httpx→trafilatura→readability→bs4→(browser off). no-bypass(robots/paywall/login/captcha 차단).",
        "- body policy: body_length(숫자)만 기록, 전문/preview 미저장.",
        "",
        "| source | content_type | eligible | urls | best_status | verdict | body_len | paywall | login | captcha |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['source_id']} | {r['content_type']} | {r['body_ladder_eligible']} | {r['attempted_urls']} "
            f"| {r['best_status'] or '-'} | {r['readiness_verdict'] or '-'} | {r['body_length']} "
            f"| {r['paywall']} | {r['login']} | {r['captcha']} |")
    lines += [
        "",
        "## 판정",
        "- ARTICLE_BODY_ALIVE / ARTICLE_PARTIAL_ALIVE: 산문 본문 추출 성공(ladder 연결 효과 확인).",
        "- PAYWALL/LOGIN/CAPTCHA_BLOCKED_NO_BYPASS: 정책상 우회 금지 → 본문 미수집(정직 보고).",
        "- NO_BODY: 본문 컨테이너 없음(구조 변경/JS 렌더). NOT_ELIGIBLE_METADATA_COMPLETE: 카탈로그형(대상 아님).",
        "",
        "## 참고",
        "카탈로그형(aladin·tmdb·kofic·kopis·tour·igdb)은 body ladder 대상이 아니다 — metadata-complete.",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="body ladder probe for prose sources")
    ap.add_argument("--max-per-source", type=int, default=3)
    ap.add_argument("--allow-browser", action="store_true")
    args = ap.parse_args(argv)
    print("BODY_LADDER_PROBE: connect rescue_news_body to nyt/opendart/culture_info (no-bypass)")
    out = run_probe(max_per_source=args.max_per_source, allow_browser=args.allow_browser)
    for r in out["rows"]:
        print(f"- {r['source_id']}: verdict={r['readiness_verdict']} status={r['best_status']} "
              f"body_len={r['body_length']} urls={r['attempted_urls']}")
    print(f"- jsonl: {_OUT_JSONL} · report: {_OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

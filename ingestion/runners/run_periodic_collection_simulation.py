"""주기 수집 시뮬레이션 runner — docs/85 Step 6.

짧은 in-process 시뮬레이션 (Celery/Redis/production scheduler 아님).
cycle × source로 gate_check → run_collection_probe → record_call을 반복하고,
cache_skip(중복 수집 방지)/cooldown/health 누적/rate_limit_cache.json 영속을 검증한다.
backend는 store 첫 사용 전 INGESTION_RATE_LIMIT_BACKEND=local_file을
process env로만 설정한다 (.env 미수정).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# store 첫 사용 전에 backend 지정 (모듈 import 시점 — main()보다 먼저 보장)
os.environ.setdefault("INGESTION_RATE_LIMIT_BACKEND", "local_file")

from ingestion.core.env_loader import load_env
from ingestion.core.rate_limit_policy import cache_key, record_call
from ingestion.core.rate_limit_store import get_store
from ingestion.fetch_strategies.collection_probe import run_collection_probe
from ingestion.runners._audit_common import (
    OUTPUT_JSONL_DIR,
    OUTPUT_REPORTS_DIR,
    audit_timestamp,
    enforce_min_interval,
    gate_check,
    safe_print,
    utc_now_iso,
    write_audit_jsonl,
    write_audit_md,
)

# 기본 subset 8개 (docs/85 Step 6) — alpha_vantage(25/day)는 finnhub로 대체,
# google_trends 계열 제외 (429 이력)
_DEFAULT_SOURCES = [
    "signal_bz", "loword", "serper", "naver_news_search",
    "gdelt", "federal_register", "finnhub", "kma",
]

_OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"
_STATE_FILE = _OUTPUTS_DIR / "state" / "rate_limit_cache.json"


def _artifact_count(source_id: str) -> int:
    n = 0
    for sub in ("raw_payload", "rendered_dom", "extracted_payload"):
        d = _OUTPUTS_DIR / sub / source_id
        if d.exists():
            n += sum(1 for p in d.iterdir() if p.is_file())
    return n


def _health_state(source_id: str) -> Optional[str]:
    try:
        from ingestion.core.source_health import get_health_store
        state = get_health_store().get(source_id)
        return state.state if state else None
    except Exception:
        return None


def simulate_cycle(
    cycle: int,
    sources: list[str],
    respect_rate_limit: bool,
    dry_run: bool,
    last_called: dict,
) -> list[dict]:
    records: list[dict] = []
    for sid in sources:
        record: dict = {
            "cycle": cycle,
            "source_id": sid,
            "audited_at": utc_now_iso(),
            "audit_action": "called",
            "status": None,
            "items_found": 0,
            "artifacts_new": 0,
            "health_state": None,
            "error_category": None,
            "next_action": None,
            "elapsed_sec": 0.0,
        }
        if dry_run:
            record["audit_action"] = "dry_run"
            records.append(record)
            continue
        if respect_rate_limit:
            skip = gate_check(sid, "")
            if skip:
                record["audit_action"] = skip
                record["health_state"] = _health_state(sid)
                record["next_action"] = "skipped_no_network_call"
                records.append(record)
                safe_print(f"  [{cycle}] {sid}: {skip}")
                continue
            enforce_min_interval(sid, last_called.get(sid))

        before = _artifact_count(sid)
        t0 = time.monotonic()
        result = run_collection_probe(sid)
        record["elapsed_sec"] = round(time.monotonic() - t0, 2)
        record_call(sid, "")
        last_called[sid] = time.monotonic()

        record.update({
            "status": result.status,
            "items_found": result.items_found,
            "artifacts_new": _artifact_count(sid) - before,
            "health_state": _health_state(sid),
            "error_category": result.error_category,
            "next_action": result.next_action,
        })
        records.append(record)
        safe_print(
            f"  [{cycle}] {sid}: called status={result.status} "
            f"artifacts_new={record['artifacts_new']} health={record['health_state']}"
        )
    return records


def verify_simulation(records: list[dict], sources: list[str]) -> dict:
    """종료 후 검증 5종 — PASS / FAIL / N_A."""
    checks: dict[str, dict] = {}

    cache_skips = [r for r in records if r["audit_action"] == "cache_skip"]
    if cache_skips:
        ok = all(r["artifacts_new"] == 0 for r in cache_skips)
        checks["1_cache_skip_no_duplicate_artifacts"] = {
            "result": "PASS" if ok else "FAIL",
            "observed": f"cache_skip {len(cache_skips)}건, artifacts_new 전부 0: {ok}",
        }
    else:
        checks["1_cache_skip_no_duplicate_artifacts"] = {
            "result": "N_A", "observed": "cache_skip 발생 없음 (cache_ttl 보유 소스 미포함/만료)",
        }

    rate_limited = [(r["cycle"], r["source_id"]) for r in records
                    if r.get("status") == "RATE_LIMITED" and r["audit_action"] == "called"]
    followups = []
    for cycle, sid in rate_limited:
        nxt = [r for r in records if r["source_id"] == sid and r["cycle"] == cycle + 1]
        if nxt:
            followups.append(nxt[0]["audit_action"] in ("cooldown_skip", "health_skip"))
    if followups:
        checks["2_rate_limited_skipped_next_cycle"] = {
            "result": "PASS" if all(followups) else "FAIL",
            "observed": f"RATE_LIMITED {len(rate_limited)}건 중 다음 cycle skip {sum(followups)}건",
        }
    else:
        checks["2_rate_limited_skipped_next_cycle"] = {
            "result": "N_A",
            "observed": "RATE_LIMITED 발생 없음 (또는 마지막 cycle에서만 발생)",
        }

    called_ids = {r["source_id"] for r in records if r["audit_action"] == "called"}
    try:
        state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        calls = state.get("calls", {})
        missing = [sid for sid in called_ids if cache_key(sid, "") not in calls]
        checks["3_rate_limit_cache_persisted"] = {
            "result": "PASS" if not missing else "FAIL",
            "observed": f"{_STATE_FILE.name}에 호출 키 {len(called_ids) - len(missing)}/{len(called_ids)} 존재"
                        + (f", 누락: {missing}" if missing else ""),
        }
    except Exception as exc:
        checks["3_rate_limit_cache_persisted"] = {
            "result": "FAIL", "observed": f"{_STATE_FILE} 읽기 실패: {type(exc).__name__}",
        }

    missing_health = [sid for sid in called_ids if _health_state(sid) is None]
    checks["4_health_state_accumulated"] = {
        "result": "PASS" if called_ids and not missing_health else ("N_A" if not called_ids else "FAIL"),
        "observed": f"health 기록 {len(called_ids) - len(missing_health)}/{len(called_ids)}"
                    + (f", 누락: {missing_health}" if missing_health else ""),
    }

    failed = [r for r in records if r["audit_action"] == "called"
              and r.get("status") not in ("LIVE_SUCCESS", "LIVE_PARTIAL")]
    if failed:
        ok = all(r.get("next_action") for r in failed)
        checks["5_failed_sources_have_next_action"] = {
            "result": "PASS" if ok else "FAIL",
            "observed": f"실패 {len(failed)}건 전부 next_action 보유: {ok}",
        }
    else:
        checks["5_failed_sources_have_next_action"] = {
            "result": "N_A", "observed": "실패 소스 없음",
        }
    return checks


def _md_report(records: list[dict], checks: dict, ts: str, cycles: int) -> str:
    lines = [
        "# Periodic Collection Simulation",
        "",
        f"- run: {ts} (UTC), cycles: {cycles}, backend: "
        f"{os.environ.get('INGESTION_RATE_LIMIT_BACKEND', 'memory')}",
        "",
        "| cycle | source_id | audit_action | status | items_found | artifacts_new | health_state | elapsed_sec | next_action |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['cycle']} | {r['source_id']} | {r['audit_action']} | {r['status'] or '-'} "
            f"| {r['items_found']} | {r['artifacts_new']} | {r['health_state'] or '-'} "
            f"| {r['elapsed_sec']} | {r['next_action'] or '-'} |"
        )
    lines += ["", "## 검증 항목 판정", ""]
    for name, c in checks.items():
        lines.append(f"- **{name}**: {c['result']} — {c['observed']}")
    lines += [
        "",
        "## Security Note",
        "API 키/토큰 값 없음.",
    ]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Periodic collection simulation (in-process)")
    parser.add_argument("--sources", nargs="*", default=None)
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--sleep-seconds", type=float, default=10.0)
    parser.add_argument("--respect-rate-limit", action="store_true", default=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cycles = min(max(args.cycles, 1), 3)
    sources = args.sources if args.sources else list(_DEFAULT_SOURCES)

    load_env()

    records: list[dict] = []
    last_called: dict[str, float] = {}
    for cycle in range(1, cycles + 1):
        safe_print(f"cycle {cycle}/{cycles}")
        records.extend(
            simulate_cycle(cycle, sources, args.respect_rate_limit, args.dry_run, last_called)
        )
        if cycle < cycles and not args.dry_run:
            time.sleep(args.sleep_seconds)

    checks = verify_simulation(records, sources) if not args.dry_run else {}

    ts = audit_timestamp()
    jsonl_path = write_audit_jsonl(
        records, OUTPUT_JSONL_DIR / f"periodic_collection_simulation_{ts}.jsonl")
    md_path = write_audit_md(
        _md_report(records, checks, ts, cycles),
        OUTPUT_REPORTS_DIR / f"periodic_collection_simulation_{ts}.md")
    safe_print(f"jsonl : {jsonl_path}")
    safe_print(f"report: {md_path}")
    for name, c in checks.items():
        safe_print(f"{name}: {c['result']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

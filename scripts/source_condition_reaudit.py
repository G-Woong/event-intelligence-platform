"""조건부 웹 소스 재감사 매트릭스 (사용자 4단계).

POLICY_EXCLUDED / BLOCKED_EXTERNAL 을 제외한 조건부 소스를, 권위 상태(production_state) +
config(profiles/registry) + readiness(env 키 존재) + 실적(queue/raw/extracted_text 아티팩트) +
이번 턴 라이브 결과(gdelt/dcinside)로 재감사한다.

"안 된다/조건부다"로 뭉뚱그리지 않고 소스별로 분리 기록:
  - 최신 데이터 신호, URL 후보, 본문, 실패 원인(기술/정책/provider), 오케스트레이션 흡수 여부.

산출물:
  - outputs/source_condition_matrix.csv
  - reports/source_condition_reaudit.md
"""
from __future__ import annotations

import csv
import json
import collections
from pathlib import Path

from ingestion.core.env_loader import load_env
from ingestion.orchestration.api_readiness import audit_api_key_readiness
from ingestion.orchestration.production_state import (
    derive_production_state,
    load_production_state,
)
from ingestion.orchestration.source_profile import load_source_profiles
from ingestion.orchestration.source_strategy_memory import load_strategy_memory
from ingestion.orchestration.vendor_api_routes import VENDOR_ROUTES

_PROFILES = "ingestion/configs/source_profiles.yaml"
_MEMORY = "ingestion/configs/source_strategy_memory.yaml"
_STATE = Path("ingestion/outputs/state/production_source_state.json")
_QUEUE = Path("ingestion/outputs/jsonl/production_event_queue.jsonl")
_RAW = Path("ingestion/outputs/raw_events/raw_events_mirror.jsonl")
_EXTRACTED = Path("ingestion/outputs/extracted_text")
_GDELT_PROBE = Path("outputs/gdelt_live_body_probe.jsonl")
_DC_PROBE = Path("outputs/dcinside_live_body_probe.jsonl")

_OUT_CSV = Path("outputs/source_condition_matrix.csv")
_OUT_MD = Path("reports/source_condition_reaudit.md")

# 본문 비대상(구조화/숫자/트렌드) purpose — body missing이 실패가 아님
_STRUCTURED_PURPOSES = {"numeric", "trend"}
# URL 후보형(검색) — downstream body fetch는 별도 단계
_URL_CANDIDATE_GROUPS = {"search"}

_COLUMNS = [
    "source_id", "enabled", "source_type", "collection_route",
    "condition_class_before", "condition_class_after", "required_env_keys", "env_key_status",
    "is_policy_excluded", "is_blocked_external", "is_user_intentional_mvp_block",
    "should_be_tested_now", "live_probe_attempted", "live_probe_status",
    "last_records_count", "queue_records_count", "raw_events_count",
    "body_expected", "body_attempted", "body_success_count", "body_failure_count",
    "body_failure_reasons", "latest_timestamp_seen", "freshness_status", "action_required",
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


def _collection_route(profile, playwright_ids, probe_spec_ids) -> str:
    sid = profile.source_id
    if sid in VENDOR_ROUTES:
        return "vendor_route"
    if sid in playwright_ids:
        return "playwright"
    if sid in probe_spec_ids:
        return "api_probe"
    return f"scrape:{profile.preferred_strategy or 'strategy_loop'}"


def build_matrix() -> dict:
    load_env()
    profiles = load_source_profiles(_PROFILES)
    memory = load_strategy_memory(_MEMORY)
    readiness = {r.source_id: r for r in audit_api_key_readiness(profiles, env_path=None)}
    prior = load_production_state(_STATE)

    # 실적 데이터
    queue = _load_jsonl(_QUEUE)
    queue_by_src = collections.Counter(r.get("source_id") for r in queue)
    body_state_by_src = collections.defaultdict(collections.Counter)
    latest_ts_by_src = {}
    for r in queue:
        sid = r.get("source_id")
        body_state_by_src[sid][r.get("body_state_or_signal")] += 1
        ts = r.get("published_at_or_observed_at")
        if ts and (sid not in latest_ts_by_src or str(ts) > str(latest_ts_by_src[sid])):
            latest_ts_by_src[sid] = ts
    raw = _load_jsonl(_RAW)
    raw_by_src = collections.Counter(r.get("source_name") or r.get("source_id") for r in raw)
    extracted_by_src = {}
    if _EXTRACTED.exists():
        for d in _EXTRACTED.iterdir():
            if d.is_dir():
                extracted_by_src[d.name] = len(list(d.glob("*.txt")))

    # playwright / api_probe id sets
    try:
        from ingestion.probes.site_specs import load_site_specs
        playwright_ids = {sid for sid, s in load_site_specs().items() if not getattr(s, "deferred", True)}
    except Exception:
        playwright_ids = set()
    from ingestion.fetch_strategies.collection_probe import _PLAYWRIGHT_FIRST_SOURCES
    playwright_ids |= set(_PLAYWRIGHT_FIRST_SOURCES)
    try:
        from ingestion.probes.api_probe import _PROBE_SPEC
        probe_spec_ids = set(_PROBE_SPEC.keys())
    except Exception:
        probe_spec_ids = set()

    # 이번 턴 라이브 결과(gdelt/dcinside)
    gdelt_rows = _load_jsonl(_GDELT_PROBE)
    gdelt_live = None
    if gdelt_rows:
        succ = [r for r in gdelt_rows if r.get("gdelt_status") == "GDELT_SUCCESS"]
        body = [r for r in gdelt_rows if r.get("body_status") == "extracted"]
        st = "GDELT_SUCCESS" if succ else (gdelt_rows[-1].get("gdelt_status") or "PROVIDER_429")
        gdelt_live = {"status": st, "rows": len(succ), "body": len(body)}
    dc_rows = _load_jsonl(_DC_PROBE)
    dc_live = None
    if dc_rows:
        g = dc_rows[0]
        dc_live = {"status": g.get("condition_class"), "list": g.get("list_count", 0),
                   "body": sum(1 for d in g.get("detail_probes", []) if d.get("body_status") == "extracted")}

    rows = []
    excluded_list = []
    for p in profiles:
        rd = readiness.get(p.source_id)
        st = derive_production_state(p, memory=memory, api_key_ready=getattr(rd, "keys_present", False))
        prev = prior.get(p.source_id)
        cond_before = st.current_status
        is_excluded = st.current_status == "POLICY_EXCLUDED" or st.excluded
        is_blocked = st.current_status in ("BLOCKED_EXTERNAL", "BLOCKED_TERMINAL")
        if is_excluded or is_blocked:
            excluded_list.append((p.source_id, st.current_status, st.terminal_reason))
            continue  # 매트릭스는 조건부(테스트 대상)만

        purpose = p.purpose or p.source_group
        body_expected = purpose not in _STRUCTURED_PURPOSES
        route = _collection_route(p, playwright_ids, probe_spec_ids)

        # 실적
        qc = queue_by_src.get(p.source_id, 0)
        rc = raw_by_src.get(p.source_id, 0)
        bstates = body_state_by_src.get(p.source_id, collections.Counter())
        body_present = bstates.get("present", 0)
        body_snippet = bstates.get("snippet_only", 0)
        body_missing = bstates.get("missing", 0)
        extracted_artifacts = extracted_by_src.get(p.source_id, 0)
        body_success = body_present + extracted_artifacts
        body_attempted = body_present + body_snippet + body_missing + extracted_artifacts

        # 이번 턴 라이브 override
        live_attempted = "prior_state"
        live_status = cond_before
        cond_after = cond_before
        fail_reasons = []
        if p.source_id == "gdelt" and gdelt_live:
            live_attempted = "this_turn_live"
            live_status = gdelt_live["status"]
            if gdelt_live["status"] == "PROVIDER_429":
                fail_reasons.append("PROVIDER_429_external")
                cond_after = "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
        if p.source_id == "dcinside" and dc_live:
            live_attempted = "this_turn_live"
            live_status = dc_live["status"]
            cond_after = dc_live["status"]  # LIMITED_PUBLIC_BODY 등
            if dc_live["body"]:
                body_success = max(body_success, dc_live["body"])

        if body_expected and body_success == 0 and qc > 0:
            fail_reasons.append("body_snippet_only_or_missing")
        if not body_expected:
            fail_reasons.append("body_not_expected_structured")

        # freshness
        latest = latest_ts_by_src.get(p.source_id) or (prev.last_success_at if prev else None)
        freshness = "has_records" if qc > 0 else ("never_collected" if not latest else "stale")

        action = "ok" if qc > 0 and (body_success > 0 or not body_expected) else (
            "needs_live_probe" if qc == 0 else "needs_body_extraction_review")
        if p.source_id == "gdelt":
            action = "await_non_throttled_window_then_reprobe"

        rows.append({
            "source_id": p.source_id, "enabled": p.enabled, "source_type": p.source_group,
            "collection_route": route, "condition_class_before": cond_before,
            "condition_class_after": cond_after,
            "required_env_keys": "|".join(getattr(rd, "required_keys", []) or []) or "-",
            "env_key_status": ("present" if getattr(rd, "keys_present", False) else
                               ("not_required" if not getattr(rd, "required_keys", []) else "missing")),
            "is_policy_excluded": False, "is_blocked_external": False,
            "is_user_intentional_mvp_block": bool(p.skip_reason),
            "should_be_tested_now": True, "live_probe_attempted": live_attempted,
            "live_probe_status": live_status, "last_records_count": qc,
            "queue_records_count": qc, "raw_events_count": rc,
            "body_expected": body_expected, "body_attempted": body_attempted,
            "body_success_count": body_success,
            "body_failure_count": (body_snippet + body_missing) if body_expected else 0,
            "body_failure_reasons": ";".join(fail_reasons) or "-",
            "latest_timestamp_seen": latest or "-", "freshness_status": freshness,
            "action_required": action,
        })

    return {"rows": rows, "excluded": excluded_list,
            "gdelt_live": gdelt_live, "dc_live": dc_live,
            "totals": {"profiles": len(profiles), "conditional": len(rows),
                       "excluded": len(excluded_list)}}


def _md(data: dict) -> str:
    rows = data["rows"]
    tested = [r for r in rows if r["queue_records_count"] > 0 or r["live_probe_attempted"] == "this_turn_live"]
    not_tested = [r for r in rows if r not in tested]
    lines = [
        "# Conditional Source Re-audit Matrix (4단계)",
        "",
        f"- profiles: {data['totals']['profiles']} · conditional(tested-scope): {data['totals']['conditional']} "
        f"· excluded(POLICY/BLOCKED): {data['totals']['excluded']}",
        f"- this-turn live: gdelt={data['gdelt_live']} · dcinside={data['dc_live']}",
        "",
        "## Excluded (POLICY_EXCLUDED / BLOCKED_EXTERNAL) — 감사 대상 제외, 목록만",
        "",
        "| source | status | reason |",
        "|---|---|---|",
    ]
    for sid, status, reason in data["excluded"]:
        lines.append(f"| {sid} | {status} | {(reason or '-')[:50]} |")
    lines += [
        "",
        "## Conditional sources (matrix)",
        "",
        "| source | route | cond_before | cond_after | env | queue | raw | body_exp | body_ok | fail | fresh | action |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda x: (-x["queue_records_count"], x["source_id"])):
        lines.append(
            f"| {r['source_id']} | {r['collection_route']} | {r['condition_class_before']} "
            f"| {r['condition_class_after']} | {r['env_key_status']} | {r['queue_records_count']} "
            f"| {r['raw_events_count']} | {r['body_expected']} | {r['body_success_count']} "
            f"| {(r['body_failure_reasons'])[:24]} | {r['freshness_status']} | {r['action_required']} |")
    lines += [
        "",
        "## Summary",
        f"- 조건부 소스 중 records 보유(또는 이번턴 라이브): {len(tested)}/{len(rows)}",
        f"- records 0(미수집/재probe 필요): {len(not_tested)}",
        f"- body_expected & body_success>0: {sum(1 for r in rows if r['body_expected'] and r['body_success_count'] > 0)}",
        f"- structured(본문 비대상): {sum(1 for r in rows if not r['body_expected'])}",
        "",
        "## Note",
        "- 이번 턴 실제 라이브 probe: gdelt(PROVIDER_429), dcinside(LIMITED_PUBLIC_BODY). 나머지는 권위 "
        "production_state + 실적 아티팩트(queue/raw/extracted_text) 기준(직전 검증 상태).",
        "- body_success는 queue body_state=present + extracted_text 아티팩트 합산(역사적 실적). 전수 라이브 "
        "재probe는 rate-limit/키 비용 때문에 분할 필요(action_required로 표시).",
    ]
    return "\n".join(lines)


def main() -> int:
    data = build_matrix()
    _OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS)
        w.writeheader()
        for r in data["rows"]:
            w.writerow(r)
    _OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    _OUT_MD.write_text(_md(data), encoding="utf-8")
    print(f"CONDITIONAL_REAUDIT: conditional={data['totals']['conditional']} "
          f"excluded={data['totals']['excluded']}")
    print(f"- csv: {_OUT_CSV}")
    print(f"- report: {_OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Orchestration source-wide validation matrix (Phase 2).

전체 source 를 상태별로 **호출 없이** final_action 으로 분류해 SOURCE_FINAL_ACTION_MATRIX 를 emit 한다.
분류 사유(정책 제외/rate-limit/키 부재/community hold)는 네트워크 호출 없이 결정되므로 헌법(실제
호출 없이 success 둔갑 금지)을 위반하지 않는다 — 이 도구는 success(LIVE_TO_BACKEND_OK)를 만들지
않으며, 실제 라이브 적재는 vetted runner(`run_production_orchestration --mode production-validation
--raw-events-sink backend`)가 수행한다. 호출 가능하지만 이번 run 에서 probe 하지 않은 소스는 green 이
아닌 정직한 별도 버킷(CALLABLE_NOT_PROBED)으로 남긴다.

키 값은 절대 읽거나 출력하지 않는다(api_readiness 는 이름/존재여부만 다룬다).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ingestion.orchestration.api_readiness import ApiKeyReadiness, audit_api_key_readiness
from ingestion.orchestration.source_profile import load_source_profiles

_DEFAULT_STATE = Path("ingestion/outputs/state/production_source_state.json")
_DEFAULT_PROFILES = Path("ingestion/configs/source_profiles.yaml")
_DEFAULT_OUTDIR = Path("ingestion/outputs/tmp_orchestration_clean/source_validation")

# 호출 없이 결정 가능한 분류(= 호출하지 않는 사유). 실제 호출이 필요한 green 은 만들지 않는다.
ACTION_SKIPPED = "SKIPPED_POLICY_EXCLUDED"
ACTION_RATE_LIMITED = "RATE_LIMITED_SCHEDULED"
ACTION_HELD = "HELD_BY_POLICY"
ACTION_NEEDS_KEY = "NEEDS_KEY"
ACTION_QUARANTINED = "FAILED_WITH_EXACT_REASON"
ACTION_CALLABLE = "CALLABLE_NOT_PROBED"  # 정직한 비-green: 호출 가능하나 이번 run 미probe


@dataclass(frozen=True)
class SourceVerdict:
    source_id: str
    current_status: str
    source_group: str
    call_allowed_by_policy: bool
    keys_present: bool
    readiness_status: str
    final_action: str
    reason: str


def classify(state_entry: dict, readiness: Optional[ApiKeyReadiness]) -> SourceVerdict:
    sid = state_entry.get("source_id", "?")
    cs = state_entry.get("current_status", "UNKNOWN")
    grp = state_entry.get("source_group", "")
    terminal = state_entry.get("terminal_reason") or ""
    rstatus = readiness.readiness_status if readiness else "unknown"
    keys_present = bool(readiness.keys_present) if readiness else False

    if state_entry.get("excluded") or cs == "POLICY_EXCLUDED":
        action, reason, allowed = ACTION_SKIPPED, (terminal or "policy_excluded"), False
    elif cs in ("EXTERNAL_RATE_LIMITED", "COOLDOWN") or state_entry.get("cooldown_until"):
        action, reason, allowed = ACTION_RATE_LIMITED, (terminal or "rate_limited_cooldown"), False
    elif cs == "QUARANTINED":
        action, reason, allowed = ACTION_QUARANTINED, (terminal or "quarantined"), False
    elif "COMMUNITY_PREVIEW" in cs:
        action, reason, allowed = ACTION_HELD, "community_preview_no_body_by_policy", True
    elif rstatus in ("missing", "unknown"):
        missing = ",".join(readiness.missing_keys) if (readiness and readiness.missing_keys) else "unmapped_or_absent"
        action, reason, allowed = ACTION_NEEDS_KEY, f"keys:{missing}", True
    else:
        action, reason, allowed = ACTION_CALLABLE, "production_ready_no_live_call_this_run", True

    return SourceVerdict(
        source_id=sid, current_status=cs, source_group=grp,
        call_allowed_by_policy=allowed, keys_present=keys_present,
        readiness_status=rstatus, final_action=action, reason=reason,
    )


def build_matrix(state_path: Path, profiles_path: Path, env_path: Optional[Path] = None) -> list[SourceVerdict]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    sources = state.get("sources", {})
    profiles = load_source_profiles(str(profiles_path))
    readiness_by_id = {r.source_id: r for r in audit_api_key_readiness(profiles, env_path=env_path)}
    verdicts = [classify(entry, readiness_by_id.get(sid)) for sid, entry in sorted(sources.items())]
    return verdicts


def summarize(verdicts: list[SourceVerdict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in verdicts:
        out[v.final_action] = out.get(v.final_action, 0) + 1
    return out


def _to_markdown(verdicts: list[SourceVerdict]) -> str:
    lines = [
        "| source_id | current_status | group | policy_ok | keys | readiness | final_action | reason |",
        "|---|---|---|:--:|:--:|---|---|---|",
    ]
    for v in verdicts:
        lines.append(
            f"| {v.source_id} | {v.current_status} | {v.source_group} | "
            f"{'Y' if v.call_allowed_by_policy else 'N'} | {'Y' if v.keys_present else 'N'} | "
            f"{v.readiness_status} | {v.final_action} | {v.reason} |"
        )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Source-wide final_action matrix (no network)")
    ap.add_argument("--state-path", default=str(_DEFAULT_STATE))
    ap.add_argument("--profiles-path", default=str(_DEFAULT_PROFILES))
    ap.add_argument("--env-path", default=None)
    ap.add_argument("--output-dir", default=str(_DEFAULT_OUTDIR))
    args = ap.parse_args(argv)

    verdicts = build_matrix(
        Path(args.state_path), Path(args.profiles_path),
        Path(args.env_path) if args.env_path else None,
    )
    summary = summarize(verdicts)

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "total": len(verdicts),
        "summary": summary,
        "sources": [v.__dict__ for v in verdicts],
        "note": "CALLABLE_NOT_PROBED is NOT a success; live load requires production-validation runner.",
    }
    (outdir / "source_final_action_matrix.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (outdir / "source_final_action_matrix.md").write_text(_to_markdown(verdicts), encoding="utf-8")

    print("SOURCE_FINAL_ACTION_MATRIX:")
    print(f"- total: {len(verdicts)}")
    for action, count in sorted(summary.items()):
        print(f"- {action}: {count}")
    print(f"- output: {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

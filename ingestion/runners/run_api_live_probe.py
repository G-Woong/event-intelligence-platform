from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ingestion.core.env_loader import load_env
from ingestion.probes.api_probe import run_api_live_probe
from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS

def _generate_report(results: list, report_dir: Path, jsonl_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    jsonl_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = jsonl_dir / "api_live_probe_results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    md_path = report_dir / "api_live_probe_report.md"
    lines = [
        "# API Live Probe Report",
        "",
        f"Services probed: {len(results)}",
        "",
        "| Service | Status | HTTP | Items | Fields | Next Action |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        http = str(r.get("http_status") or "-")
        fields = ", ".join(r.get("meaningful_fields", []))[:40]
        lines.append(
            f"| {r['source_id']} | {r['status']} | {http} "
            f"| {r['items_found']} | {fields} | {r['next_action']} |"
        )

    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1

    lines += [
        "",
        "## Summary",
        "",
    ]
    for status, count in sorted(summary.items()):
        lines.append(f"- `{status}`: {count}")

    lines += [
        "",
        "## Security Note",
        "NO API keys, tokens, or secret values in this report.",
        "Artifacts contain response bodies only (no request headers or URL query params with keys).",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, jsonl_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Live API probe for ingestion sources")
    parser.add_argument("--service", default=None, help="Single service ID to probe")
    parser.add_argument("--all-safe", action="store_true", help="Probe all non-blocked services")
    parser.add_argument("--max-calls", type=int, default=1, help="Max calls for single-service mode")
    parser.add_argument("--max-calls-per-service", type=int, default=1, help="Max calls per service in --all-safe")
    parser.add_argument("--env-path", default=None, help="Path to .env file")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Key presence check only")
    args = parser.parse_args()

    env_path = Path(args.env_path) if args.env_path else None
    if env_path:
        load_env(env_path)
    else:
        load_env()

    if args.service and args.all_safe:
        print("ERROR: --service and --all-safe are mutually exclusive")
        sys.exit(1)

    if not args.service and not args.all_safe:
        print("ERROR: specify --service <id> or --all-safe")
        sys.exit(1)

    if args.service:
        if args.service not in _SERVICE_CONFIGS:
            print(f"ERROR: unknown service '{args.service}'")
            sys.exit(1)
        services = {args.service: args.max_calls}
    else:
        _EXCLUDED_STATUSES = {"DEPRECATED_OR_EXCLUDED", "MVP_EXCLUDED"}
        services = {
            sid: args.max_calls_per_service
            for sid, cfg in _SERVICE_CONFIGS.items()
            if cfg.get("status_override") not in _EXCLUDED_STATUSES
        }

    results = []
    for service_id, max_calls in services.items():
        result = run_api_live_probe(
            service_id,
            max_calls=max_calls,
            env_path=env_path,
            dry_run=args.dry_run,
        )
        r = result.to_dict()
        results.append(r)
        icon = "OK" if r["status"] in ("LIVE_SUCCESS", "LIVE_PARTIAL") else "--"
        print(f"{icon} {service_id:30s}  {r['status']:20s}  http={r['http_status'] or '-':>4}  items={r['items_found']}")

    report_dir = _REPO_ROOT / "ingestion" / "outputs" / "reports"
    jsonl_dir = _REPO_ROOT / "ingestion" / "outputs" / "jsonl"
    md_path, jsonl_path = _generate_report(results, report_dir, jsonl_dir)
    print(f"\nReport : {md_path}")
    print(f"JSONL  : {jsonl_path}")

    success = sum(1 for r in results if r["status"] in ("LIVE_SUCCESS", "LIVE_PARTIAL"))
    missing = sum(1 for r in results if r["status"] == "MISSING_KEY")
    blocked = sum(1 for r in results if r["status"] == "BLOCKED")
    deferred = sum(1 for r in results if r["status"] == "DEFERRED")
    failed = len(results) - success - missing - blocked - deferred
    print(
        f"\nTotal: {len(results)}  Success: {success}  MissingKey: {missing}"
        f"  Blocked: {blocked}  Deferred: {deferred}  Other: {failed}"
    )


if __name__ == "__main__":
    print(
        "[DEPRECATED] This runner is kept for legacy API-probe compatibility.\n"
        "Canonical API connectivity: python -m ingestion.runners.run_api_connectivity_check\n"
        "Canonical orchestration: python -m ingestion.tools.run_production_orchestration",
        file=sys.stderr,
    )
    main()

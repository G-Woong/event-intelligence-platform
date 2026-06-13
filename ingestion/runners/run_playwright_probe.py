from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ingestion.probes.playwright_probe import run_playwright_probe
from ingestion.probes.site_specs import load_site_specs


def _generate_report(results: list, report_dir: Path, jsonl_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    jsonl_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = jsonl_dir / "playwright_probe_results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    md_path = report_dir / "playwright_probe_report.md"
    lines = [
        "# Playwright Probe Report",
        "",
        f"Sites probed: {len(results)}",
        "",
        "| Site | Status | Items Found | Items Extracted | Error | Next Action |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        err = r.get("error_category") or "-"
        lines.append(
            f"| {r['source_id']} | {r['status']} | {r['items_found']} "
            f"| {r['items_extracted']} | {err} | {r['next_action']} |"
        )

    lines += [
        "",
        "## Artifact Paths",
        "",
    ]
    for r in results:
        if r.get("artifact_paths"):
            lines.append(f"### {r['source_id']}")
            for k, v in r["artifact_paths"].items():
                lines.append(f"- {k}: `{v}`")
            lines.append("")

    lines += [
        "## Compliance",
        "No login/CAPTCHA/paywall bypass attempted.",
        "Challenge pages recorded as BLOCKED.",
        "Honest UA: event-intelligence/0.7 (+ei)",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, jsonl_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Playwright probe for ingestion sites")
    parser.add_argument("--site", required=True, help="Site ID from playwright_probe_sites.yaml")
    parser.add_argument("--query", default=None, help="Search query (for keyword-input sites)")
    parser.add_argument("--region", default=None, help="Region code (e.g. KR)")
    parser.add_argument("--max-items", type=int, default=10, help="Max items to extract")
    args = parser.parse_args()

    site_specs = load_site_specs()
    if args.site not in site_specs:
        known = ", ".join(sorted(site_specs.keys()))
        print(f"ERROR: unknown site '{args.site}'. Known: {known}")
        sys.exit(1)

    print(f"Probing site: {args.site}  query={args.query}  region={args.region}  max_items={args.max_items}")

    result = run_playwright_probe(
        args.site,
        query=args.query,
        region=args.region,
        max_items=args.max_items,
    )
    r = result.to_dict()
    results = [r]

    icon = "OK" if r["status"] in ("LIVE_SUCCESS", "LIVE_PARTIAL") else "--"
    print(f"{icon} {r['source_id']:20s}  {r['status']:20s}  items={r['items_found']}  extracted={r['items_extracted']}")

    if r.get("artifact_paths"):
        for k, v in r["artifact_paths"].items():
            print(f"   {k}: {v}")

    report_dir = _REPO_ROOT / "ingestion" / "outputs" / "reports"
    jsonl_dir = _REPO_ROOT / "ingestion" / "outputs" / "jsonl"
    md_path, jsonl_path = _generate_report(results, report_dir, jsonl_dir)
    print(f"\nReport : {md_path}")
    print(f"JSONL  : {jsonl_path}")


if __name__ == "__main__":
    main()

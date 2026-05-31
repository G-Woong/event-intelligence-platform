from __future__ import annotations

import json
from pathlib import Path

from crawling.schemas.source_report import SourceReport


def write_source_report(report: SourceReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / f"{report.source_id}_report.md"
    md_path.write_text(_render_report(report), encoding="utf-8")

    jsonl_path = output_dir / f"{report.source_id}_report.jsonl"
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report.model_dump(), ensure_ascii=False, default=str) + "\n")

    return md_path


def _render_report(r: SourceReport) -> str:
    lines = [
        f"# Source Report: {r.source_name} ({r.source_id})",
        "",
        f"**Phase**: {r.phase}  **Type**: {r.source_type}  **Evidence Level**: {r.evidence_level}",
        f"**Run at**: {r.run_at}",
        "",
        "## Result",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Status | `{r.status}` |",
        f"| Quality Score | {r.quality_score:.3f} |",
        f"| Attempts | {r.attempts} |",
        f"| Strategy Used | `{r.strategy_used or 'N/A'}` |",
        f"| URLs Crawled | {r.urls_crawled} |",
        f"| Articles Extracted | {r.articles_extracted} |",
        f"| Event Candidates | {r.event_candidates_found} |",
        "",
        "## Errors",
        "",
    ]

    if r.errors:
        for e in r.errors:
            etype = e.get("error_type", "UNKNOWN")
            attempt = e.get("attempt_no", "?")
            msg = (e.get("raw_message") or "")[:120]
            lines.append(f"- `{etype}` (attempt={attempt}): {msg}")
    else:
        lines.append("_No errors_")

    lines += [
        "",
        "## Known Blockers Hit",
        "",
    ]
    if r.known_blockers_hit:
        for b in r.known_blockers_hit:
            lines.append(f"- {b}")
    else:
        lines.append("_None_")

    lines += [
        "",
        "## Recommended Action",
        "",
        r.recommended_action or "_None_",
        "",
        "## Notes",
        "",
        r.notes or "_None_",
    ]
    return "\n".join(lines)


def write_phase_summary(
    phase: int,
    reports: list[SourceReport],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / f"phase{phase}_summary.md"

    lines = [
        f"# Phase {phase} Summary",
        "",
        "| Source | Status | Score | Strategy | Attempts |",
        "|---|---|---|---|---|",
    ]
    for r in reports:
        lines.append(
            f"| {r.source_name} | `{r.status}` | {r.quality_score:.3f} | `{r.strategy_used or 'N/A'}` | {r.attempts} |"
        )

    success = sum(1 for r in reports if r.status == "SUCCESS")
    partial = sum(1 for r in reports if r.status == "PARTIAL")
    blocked = sum(1 for r in reports if r.status == "BLOCKED")
    failed = sum(1 for r in reports if r.status == "FAILED")

    lines += [
        "",
        f"**Total**: {len(reports)}  **SUCCESS**: {success}  **PARTIAL**: {partial}  **BLOCKED**: {blocked}  **FAILED**: {failed}",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path

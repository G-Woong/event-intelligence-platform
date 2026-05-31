from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

_REPORTS_DIR = Path(__file__).parent.parent / "outputs" / "reports"


def summarize_reports(phase: int | None = None) -> None:
    pattern = "*.jsonl"
    files = sorted(_REPORTS_DIR.glob(pattern))

    rows = []
    for fpath in files:
        lines = fpath.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            continue
        report = json.loads(lines[-1])
        if phase is not None and report.get("phase") != phase:
            continue
        rows.append(report)

    if not rows:
        print("No reports found.")
        return

    print(f"\n{'Source':<20} {'Status':<10} {'Score':>6} {'Attempts':>8} {'Strategy':<25}")
    print("-" * 75)
    for r in rows:
        print(
            f"{r.get('source_id', ''):<20} "
            f"{r.get('status', ''):<10} "
            f"{r.get('quality_score', 0.0):>6.3f} "
            f"{r.get('attempts', 0):>8} "
            f"{r.get('strategy_used') or 'N/A':<25}"
        )
    print(f"\nTotal: {len(rows)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize crawling reports")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], default=None)
    args = parser.parse_args()
    summarize_reports(args.phase)


if __name__ == "__main__":
    main()

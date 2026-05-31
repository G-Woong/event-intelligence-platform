from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from crawling.core.source_registry import load_registry
from crawling.runners.run_one_source import run_source


def run_phase(phase: int) -> list[dict]:
    registry = load_registry()
    sources = registry.get_by_phase(phase)
    if not sources:
        print(f"No sources found for phase {phase}")
        return []

    results = []
    for spec in sources:
        print(f"[phase{phase}] Running: {spec.id}")
        try:
            final_state = run_source(spec.id)
            results.append(final_state)
        except Exception as exc:
            print(f"[phase{phase}] ERROR {spec.id}: {exc}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run crawling pipeline for all sources in a phase")
    parser.add_argument("--phase", type=int, required=True, choices=[1, 2, 3])
    args = parser.parse_args()
    results = run_phase(args.phase)
    print(f"\nPhase {args.phase} done: {len(results)} sources processed")


if __name__ == "__main__":
    main()

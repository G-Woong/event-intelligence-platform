from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from ingestion.runners.run_phase import run_phase


def main() -> None:
    all_results = []
    for phase in (1, 2, 3):
        print(f"\n{'='*40}")
        print(f" Phase {phase}")
        print(f"{'='*40}")
        results = run_phase(phase)
        all_results.extend(results)
    print(f"\nAll phases done: {len(all_results)} total sources processed")


if __name__ == "__main__":
    main()

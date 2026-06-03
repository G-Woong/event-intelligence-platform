from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

_LOG_DIR = Path(__file__).parent.parent / "logs"


def inspect_last_failure(source_id: str) -> None:
    errors_dir = _LOG_DIR / "errors"
    pattern = f"{source_id}_errors.jsonl" if source_id != "all" else "*.jsonl"
    files = list(errors_dir.glob(pattern))

    if not files:
        print(f"No error logs found for: {source_id}")
        return

    for fpath in sorted(files):
        lines = fpath.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            continue
        last = json.loads(lines[-1])
        print(f"\n[{fpath.name}] Last error:")
        print(json.dumps(last, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect last failure for a source")
    parser.add_argument("--source", default="all", help="Source ID or 'all'")
    args = parser.parse_args()
    inspect_last_failure(args.source)


if __name__ == "__main__":
    main()

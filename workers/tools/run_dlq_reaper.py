from __future__ import annotations

"""PEL reaper CLI (P0 하드닝, Phase 3).

worker crash 등으로 PEL에 delivered-but-unacked 상태로 잔류한 메시지를 XAUTOCLAIM으로 회수해
재시도(사본 재발행) 또는 max_retries 초과 시 DLQ로 격리한다. 우회/삭제 없음 — 보존+재처리.

예:
  .venv\\Scripts\\python.exe -m workers.tools.run_dlq_reaper \\
    --stream stream:raw_events --group group:ingest \\
    --min-idle-ms 60000 --max-retries 3 --dlq-stream stream:raw_events:dlq
"""

import argparse

from backend.app.db import redis as redis_db
from workers.queue import dlq


def main() -> int:
    parser = argparse.ArgumentParser(description="Redis PEL reaper → retry/DLQ")
    parser.add_argument("--stream", default="stream:raw_events")
    parser.add_argument("--group", default="group:ingest")
    parser.add_argument("--consumer", default="reaper-1")
    parser.add_argument("--min-idle-ms", type=int, default=60000)
    parser.add_argument("--max-retries", type=int, default=dlq.DEFAULT_MAX_RETRIES)
    parser.add_argument("--dlq-stream", default="stream:raw_events:dlq")
    args = parser.parse_args()

    redis_db.ensure_group(args.stream, args.group)
    client = redis_db.get_redis()
    stats = dlq.reap_pending(
        client,
        args.stream,
        args.group,
        args.consumer,
        args.min_idle_ms,
        args.dlq_stream,
        max_retries=args.max_retries,
    )
    print(
        f"DLQ_REAPER stream={args.stream} group={args.group} "
        f"claimed={stats['claimed']} retried={stats['retried']} "
        f"dead_lettered={stats['dead_lettered']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

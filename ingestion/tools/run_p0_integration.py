"""P0 통합 proof CLI — ingestion record 를 raw_events→Redis→worker→LangGraph→event_cards 로 흘린다.

사용:
  .venv\\Scripts\\python.exe -m ingestion.tools.run_p0_integration --mode proof \\
    --base-url http://localhost:8000 --max-records-per-type 1 \\
    --output-dir ingestion/outputs/tmp_p0_integration --save-proof-ledger

backend(및 redis/worker/agent-worker)가 떠 있어야 라이브 proof 가 가능하다. 미가동 시 write 가
transport 실패로 집계되며, 그 사실을 정직하게 보고한다(fake success 금지).
admin token 값은 env(ADMIN_API_TOKEN)에서만 읽고 출력하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional

from ingestion.integration.p0_integration_runner import P0RunConfig, run_p0_integration


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="P0 ingestion→downstream integration proof")
    ap.add_argument("--mode", default="proof", choices=["proof"])
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--max-records-per-type", type=int, default=1)
    ap.add_argument("--poll-timeout", type=float, default=40.0)
    ap.add_argument("--output-dir", default="ingestion/outputs/tmp_p0_integration")
    ap.add_argument("--save-proof-ledger", action="store_true")
    ap.add_argument("--require-event-card", default="true")
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    admin_token = os.getenv("ADMIN_API_TOKEN") or None
    config = P0RunConfig(
        base_url=args.base_url,
        admin_token=admin_token,
        max_records_per_type=args.max_records_per_type,
        poll_timeout_sec=args.poll_timeout,
        require_event_card=str(args.require_event_card).lower() == "true",
        output_dir=Path(args.output_dir) if args.save_proof_ledger else None,
    )

    print("P0_INTEGRATION_PLAN:")
    print(f"- base_url: {config.base_url}")
    print(f"- admin_token: {'set' if admin_token else 'empty(dev bypass)'}")
    print(f"- writer: BackendApiRawEventsWriter")
    print(f"- max_records_per_type: {config.max_records_per_type}")

    result = run_p0_integration(config)

    plan = result["plan"]
    print(f"- redis_stream: {plan['redis_stream']}")
    print(f"- worker_entrypoint: {plan['worker_entrypoint']}")
    print(f"- langgraph_entrypoint: {plan['langgraph_entrypoint']}")
    print(f"- event_cards_target: {plan['event_cards_target']}")
    print(f"- policy_excluded_count: {plan['policy_excluded_count']}")
    print(f"- record_types: {plan['record_types']}")

    print("\nP0_INTEGRATION_RESULT:")
    hdr = ("record_type", "source_id", "origin", "write", "raw_event_id",
           "redis_msg", "worker", "langgraph", "event_card", "card", "dedup", "policy", "final")
    print("| " + " | ".join(hdr) + " |")
    for r in result["rows"]:
        print("| " + " | ".join(str(x) for x in (
            r["record_type"], r["source_id"], r["origin"], r["write_status"],
            (r["raw_event_id"] or "")[:8], (r["enqueued_msg_id"] or "")[:14],
            r["worker_status"], r["langgraph_status"],
            (r["event_card_id"] or "")[:8], r["card_status"],
            r["dedup_status"], r["policy_status"], r["final_status"],
        )) + " |")

    counts = result["counts"]
    print("\nCOUNTS:", json.dumps(counts, ensure_ascii=False))
    print("WRITER:", json.dumps(result["writer_summary"], ensure_ascii=False))

    # exit code: e2e 성공 타입이 1개 이상이면 0(부분), 0이면 2(블로커)
    return 0 if counts["e2e_ok_type_count"] >= 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())

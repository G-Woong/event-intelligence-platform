from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from crawling.core.artifact_store import new_run_id, url_hash as make_url_hash
from crawling.core.logging_setup import configure_crawling_logging, get_crawling_logger
from crawling.core.retry_policy import STRATEGY_SEQUENCE
from crawling.core.source_registry import load_registry


def _build_initial_state(source_id: str) -> dict:
    registry = load_registry()
    spec = registry.get(source_id)
    if spec is None:
        raise ValueError(f"Source '{source_id}' not found in registry")

    rid = new_run_id(spec.phase, source_id)
    uh = make_url_hash(spec.base_url)

    return {
        "source_id": source_id,
        "source_spec": spec.to_dict(),
        "phase": spec.phase,
        "run_id": rid,
        "url_hash": uh,
        "query": "",
        "attempt_no": 0,
        "max_attempts": 3,
        "strategy_sequence": STRATEGY_SEQUENCE[:],
        "current_strategy": STRATEGY_SEQUENCE[0],
        "strategies_tried": [],
        "entry_url": spec.base_url,
        "candidate_urls": [],
        "current_url": spec.base_url,
        "raw_html": None,
        "raw_html_path": None,
        "dom_snapshot_path": None,
        "screenshot_path": None,
        "extracted_text_path": None,
        "extraction_result": None,
        "quality_score": 0.0,
        "quality_status": "FAILED",
        "event_candidates": [],
        "errors": [],
        "current_error": None,
        "llm_judge_result": None,
        "screenshots": [],
        "dom_snapshots": [],
        "retry_history": [],
        "status": "RUNNING",
        "should_retry": False,
        "retry_reason": "",
        "strategy_exhausted": False,
        "final_report": None,
    }


def run_source(source_id: str) -> dict:
    log_dir = Path(__file__).parent.parent / "logs"
    configure_crawling_logging(log_dir, source_id=source_id)
    logger = get_crawling_logger("runners.run_one_source")

    logger.info("=== run_one_source: %s ===", source_id)

    from crawling.agents.graph import get_compiled_graph
    graph = get_compiled_graph()

    initial_state = _build_initial_state(source_id)
    final_state = graph.invoke(initial_state)

    status = final_state.get("status", "UNKNOWN")
    score = final_state.get("quality_score", 0.0)
    logger.info("=== DONE: %s  status=%s  score=%.3f ===", source_id, status, score)
    return final_state


def main() -> None:
    parser = argparse.ArgumentParser(description="Run crawling pipeline for one source")
    parser.add_argument("--source", required=True, help="Source ID (e.g. _dummy, bbc)")
    args = parser.parse_args()

    final_state = run_source(args.source)
    report = final_state.get("final_report")
    if report:
        print(f"\nStatus  : {report.get('status')}")
        print(f"Score   : {report.get('quality_score', 0.0):.3f}")
        print(f"Strategy: {report.get('strategy_used')}")
        print(f"Attempts: {report.get('attempts')}")
        print(f"Report  : crawling/outputs/reports/{args.source}_report.md")
    else:
        print(f"No report generated. Final status: {final_state.get('status')}")


if __name__ == "__main__":
    main()

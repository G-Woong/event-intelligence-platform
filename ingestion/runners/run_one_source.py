from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from ingestion.core.artifact_store import new_run_id, url_hash as make_url_hash
from ingestion.core.env_loader import load_env
from ingestion.core.logging_setup import configure_ingestion_logging, get_ingestion_logger
from ingestion.core.retry_policy import STRATEGY_SEQUENCE
from ingestion.core.source_registry import load_registry


def _handle_precheck(source_id: str, status: str, reason: str) -> dict:
    from ingestion.schemas.source_report import SourceReport
    from ingestion.core.report_writer import write_source_report
    from pathlib import Path

    registry = load_registry()
    spec = registry.get(source_id)
    if spec is None:
        return {"status": status, "quality_status": status, "quality_score": 0.0, "final_report": None}

    report = SourceReport(
        source_id=source_id,
        source_name=spec.name,
        source_type=spec.type,
        evidence_level=spec.evidence_level,
        phase=spec.phase,
        status=status,
        quality_score=0.0,
        attempts=0,
        strategy_used=None,
        urls_crawled=0,
        articles_extracted=0,
        event_candidates_found=0,
        notes=reason,
    )
    output_dir = Path(__file__).parent.parent / "outputs" / "reports"
    write_source_report(report, output_dir)

    from ingestion.core.artifact_store import append_result_row
    rid = new_run_id(spec.phase, source_id)
    row = {
        "run_id": rid,
        "source_id": source_id,
        "phase": spec.phase,
        "status": status,
        "quality_score": 0.0,
        "attempts": 0,
        "strategy_used": None,
        "url": spec.base_url,
        "title": None,
        "body_char_count": 0,
        "artifact_paths": {},
        "retry_history": [],
        "errors": [{"reason": reason}] if reason else [],
    }
    append_result_row(spec.phase, source_id, row)

    return {
        "status": status,
        "quality_status": status,
        "quality_score": 0.0,
        "final_report": report.model_dump(mode="json"),
    }


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
        "raw_payload_path": None,
        "extracted_payload_path": None,
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
    configure_ingestion_logging(log_dir, source_id=source_id)
    logger = get_ingestion_logger("runners.run_one_source")

    logger.info("=== run_one_source: %s ===", source_id)

    # R-EnvLoadAsymmetry: run_source() is the shared funnel for the run_one_source /
    # run_phase / run_all_phases entrypoints. Load .env into os.environ (idempotent
    # setdefault) BEFORE precheck so key-required sources' precheck_status() (os.getenv)
    # sees keys that exist in .env — aligning these entrypoints with the production
    # orchestration path's env contract. Values are never read or printed here.
    load_env()

    from ingestion.sources._registry import get_source_instance
    src = get_source_instance(source_id)
    if src:
        try:
            precheck = src.precheck_status()
        except Exception as _exc:
            logger.warning("[%s] precheck_status error: %s", source_id, _exc)
            precheck = None
        if precheck is not None:
            status = precheck.get("status", "NEEDS_API")
            reason = precheck.get("reason", "")
            logger.info("[%s] precheck_status: %s — %s", source_id, status, reason)
            return _handle_precheck(source_id, status, reason)

    from ingestion.agents.graph import get_compiled_graph
    graph = get_compiled_graph()

    initial_state = _build_initial_state(source_id)
    final_state = graph.invoke(initial_state)

    status = final_state.get("status", "UNKNOWN")
    score = final_state.get("quality_score", 0.0)
    logger.info("=== DONE: %s  status=%s  score=%.3f ===", source_id, status, score)
    return final_state


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ingestion pipeline for one source")
    parser.add_argument("--source", required=True, help="Source ID (e.g. _dummy, bbc)")
    args = parser.parse_args()

    final_state = run_source(args.source)
    report = final_state.get("final_report")
    if report:
        print(f"\nStatus  : {report.get('status')}")
        print(f"Score   : {report.get('quality_score', 0.0):.3f}")
        print(f"Strategy: {report.get('strategy_used')}")
        print(f"Attempts: {report.get('attempts')}")
        print(f"Report  : ingestion/outputs/reports/{args.source}_report.md")
    else:
        print(f"No report generated. Final status: {final_state.get('status')}")


if __name__ == "__main__":
    main()

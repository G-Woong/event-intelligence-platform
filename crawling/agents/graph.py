from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from langgraph.graph import StateGraph, END

from crawling.agents.state import CrawlingAgentState
from crawling.core.retry_policy import STRATEGY_SEQUENCE

logger = logging.getLogger("crawling.agents.graph")

_HTTPX_STRATEGIES = {"httpx_direct", "httpx_mobile_ua", "httpx_random_ua"}
_PLAYWRIGHT_STRATEGIES = {
    "playwright_basic", "playwright_scroll",
    "playwright_wait_network_idle", "playwright_click_more",
}
_EXTRACT_ONLY_STRATEGIES = {"readability", "trafilatura", "dom_heuristic"}


# ──────────────────────── helpers ────────────────────────

def _fetch_with_strategy(url: str, strategy: str, run_id: str, source_id: str, uh: str) -> tuple[Optional[str], Optional[Path], Optional[Path]]:
    """
    strategy에 따라 HTML 페칭. (html, screenshot_path, dom_path) 반환.
    screenshot/dom_path는 playwright에서만 값이 있다.
    """
    from crawling.core.artifact_store import get_screenshot_path, save_dom_snapshot, build_dom_snapshot_dict

    if strategy in _PLAYWRIGHT_STRATEGIES:
        ss_path = get_screenshot_path(run_id, source_id, uh)
        dom_dir = ss_path.parent.parent.parent / "dom_snapshots" / source_id
        dom_dir.mkdir(parents=True, exist_ok=True)
        dom_file = dom_dir / f"{run_id}_{uh}_{strategy}.json"

        from crawling.tools.playwright_browser_tool import fetch_with_playwright_sync
        html = fetch_with_playwright_sync(
            url,
            strategy=strategy,
            screenshot_dir=ss_path.parent,
            dom_dir=dom_dir,
        )
        snapshot_path: Optional[Path] = None
        if html:
            snap = build_dom_snapshot_dict(url, html, strategy)
            snapshot_path = save_dom_snapshot(run_id, source_id, uh, strategy, snap)
        return html, ss_path, snapshot_path
    else:
        from crawling.tools.html_fetch_tool import fetch_html
        result = fetch_html(url, strategy=strategy)
        if result.success:
            return result.html, None, None
        return None, None, None


def _best_extraction(html: str, url: str, source_id: str) -> Optional[dict]:
    """readability → trafilatura → dom_heuristic 순서로 cascade 추출, 최고 quality 반환."""
    from crawling.tools.readability_extractor import extract_with_readability
    from crawling.tools.trafilatura_extractor import extract_with_trafilatura
    from crawling.tools.dom_candidate_extractor import extract_with_dom_heuristic

    candidates = []
    for fn in (extract_with_readability, extract_with_trafilatura, extract_with_dom_heuristic):
        r = fn(html, url)
        if r.success and r.body and len(r.body) > 50:
            candidates.append(r)

    if not candidates:
        return None

    best = max(candidates, key=lambda r: len(r.body or ""))
    return {
        "title": best.title,
        "body": best.body,
        "author": best.author,
        "published_at": best.published_at,
        "language": best.language,
        "metadata": best.metadata,
        "strategy": best.strategy,
        "url": url,
        "source_id": source_id,
    }


def _specific_extraction(html: str, url: str, source_id: str, strategy: str) -> Optional[dict]:
    """지정 단일 extractor만 사용."""
    from crawling.tools.readability_extractor import extract_with_readability
    from crawling.tools.trafilatura_extractor import extract_with_trafilatura
    from crawling.tools.dom_candidate_extractor import extract_with_dom_heuristic

    fn_map = {
        "readability": extract_with_readability,
        "trafilatura": extract_with_trafilatura,
        "dom_heuristic": extract_with_dom_heuristic,
    }
    fn = fn_map.get(strategy)
    if fn is None:
        return None
    r = fn(html, url)
    if not r.success or not r.body:
        return None
    return {
        "title": r.title,
        "body": r.body,
        "author": r.author,
        "published_at": r.published_at,
        "language": r.language,
        "metadata": r.metadata,
        "strategy": r.strategy,
        "url": url,
        "source_id": source_id,
    }


# ──────────────────────── Node implementations ────────────────────────

def _node_initialize(state: CrawlingAgentState) -> dict:
    logger.info("[%s] initialize: phase=%d run_id=%s", state["source_id"], state["phase"], state.get("run_id", ""))
    return {
        "attempt_no": 0,
        "strategies_tried": [],
        "current_strategy": STRATEGY_SEQUENCE[0],
        "candidate_urls": [],
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


def _node_build_search_query(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    spec = state["source_spec"]
    logger.info("[%s] build_search_query", source_id)

    from crawling.sources._registry import get_source_instance
    src = get_source_instance(source_id)
    if src is not None:
        entry_url = src.get_entry_url()
        query = src.build_search_query()
    else:
        entry_url = spec.get("base_url", "")
        query = ""

    return {"entry_url": entry_url, "query": query}


def _node_fetch_entry_url(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    url = state["entry_url"]
    strategy = "httpx_direct"
    run_id = state.get("run_id", "unknown")
    uh = state.get("url_hash", "00000000")
    logger.info("[%s] fetch_entry_url: %s", source_id, url)

    from crawling.core.artifact_store import save_raw_html

    html, ss_path, snap_path = _fetch_with_strategy(url, strategy, run_id, source_id, uh)
    if html:
        rp = save_raw_html(run_id, source_id, uh, f"entry_{strategy}", html)
        return {
            "raw_html": html,
            "current_url": url,
            "raw_html_path": str(rp),
        }

    return {
        "raw_html": None,
        "current_url": url,
        "current_error": {
            "source_id": source_id,
            "url": url,
            "attempt_no": state["attempt_no"],
            "strategy": strategy,
            "error_type": "NETWORK_TIMEOUT",
            "raw_message": "fetch_entry_url: no HTML obtained",
            "retryable": False,
        },
    }


def _node_extract_candidate_urls(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    logger.info("[%s] extract_candidate_urls", source_id)

    from crawling.sources._registry import get_source_instance
    from crawling.core.artifact_store import url_hash as make_uh

    src = get_source_instance(source_id)
    html = state.get("raw_html") or ""
    urls: list[str] = []
    if src is not None:
        urls = src.extract_candidate_urls(html)

    if not urls:
        urls = [state["current_url"]]

    # 상위 3개만 사용 (smoke 실행)
    urls = urls[:3]
    first_url = urls[0] if urls else state["current_url"]
    uh = make_uh(first_url)

    return {
        "candidate_urls": urls,
        "current_url": first_url,
        "url_hash": uh,
    }


def _node_fetch_target_page(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    url = state["current_url"]
    strategy = state["current_strategy"]
    run_id = state.get("run_id", "unknown")
    uh = state.get("url_hash", "00000000")
    logger.info("[%s] fetch_target_page: strategy=%s url=%s", source_id, strategy, url)

    from crawling.core.artifact_store import save_raw_html

    html, ss_path, snap_path = _fetch_with_strategy(url, strategy, run_id, source_id, uh)
    if html:
        rp = save_raw_html(run_id, source_id, uh, strategy, html)
        updates: dict = {
            "raw_html": html,
            "current_url": url,
            "raw_html_path": str(rp),
        }
        if ss_path:
            updates["screenshot_path"] = str(ss_path)
            updates["screenshots"] = list(state.get("screenshots", [])) + [str(ss_path)]
        if snap_path:
            updates["dom_snapshot_path"] = str(snap_path)
            updates["dom_snapshots"] = list(state.get("dom_snapshots", [])) + [str(snap_path)]
        return updates

    return {
        "raw_html": None,
        "current_error": {
            "source_id": source_id,
            "url": url,
            "attempt_no": state["attempt_no"],
            "strategy": strategy,
            "error_type": "NETWORK_TIMEOUT",
            "raw_message": f"fetch_target_page: no HTML (strategy={strategy})",
            "retryable": True,
        },
    }


def _node_select_extraction_strategy(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    tried = state["strategies_tried"]
    seq = state["strategy_sequence"]
    remaining = [s for s in seq if s not in tried]
    if remaining:
        strategy = remaining[0]
    else:
        strategy = state["current_strategy"]
    logger.info("[%s] select_extraction_strategy: %s", source_id, strategy)
    return {
        "current_strategy": strategy,
        "strategy_exhausted": len(remaining) <= 1,
    }


def _node_extract_content(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    strategy = state["current_strategy"]
    url = state["current_url"]
    run_id = state.get("run_id", "unknown")
    uh = state.get("url_hash", "00000000")
    logger.info("[%s] extract_content: strategy=%s", source_id, strategy)

    from crawling.core.artifact_store import save_raw_html, save_extracted_text
    from crawling.core.error_taxonomy import classify_content_blocker

    html = state.get("raw_html") or ""

    # playwright_* or re-fetch httpx_* strategies need a new fetch
    attempt = state.get("attempt_no", 0)
    need_refetch = (
        (strategy in _PLAYWRIGHT_STRATEGIES)
        or (strategy in _HTTPX_STRATEGIES and attempt > 0 and strategy != STRATEGY_SEQUENCE[0])
    )

    if need_refetch:
        logger.info("[%s] extract_content: re-fetching with strategy=%s", source_id, strategy)
        from crawling.core.artifact_store import save_dom_snapshot, get_screenshot_path, build_dom_snapshot_dict
        new_html, ss_path, snap_path = _fetch_with_strategy(url, strategy, run_id, source_id, uh)
        if new_html:
            html = new_html
            rp = save_raw_html(run_id, source_id, uh, strategy, html)
            state_updates_for_fetch: dict = {"raw_html": html, "raw_html_path": str(rp)}
            if ss_path:
                state_updates_for_fetch["screenshot_path"] = str(ss_path)
            if snap_path:
                state_updates_for_fetch["dom_snapshot_path"] = str(snap_path)

    if not html:
        tried = list(state["strategies_tried"]) + [strategy]
        return {
            "extraction_result": None,
            "strategies_tried": tried,
            "current_error": {
                "source_id": source_id,
                "url": url,
                "attempt_no": attempt,
                "strategy": strategy,
                "error_type": "EXTRACTION_EMPTY",
                "raw_message": "extract_content: no HTML available",
                "retryable": True,
            },
        }

    # blocker detection
    blocker = classify_content_blocker(html.lower())
    if blocker:
        tried = list(state["strategies_tried"]) + [strategy]
        return {
            "extraction_result": None,
            "strategies_tried": tried,
            "current_error": {
                "source_id": source_id,
                "url": url,
                "attempt_no": attempt,
                "strategy": strategy,
                "error_type": blocker.value,
                "raw_message": f"blocker detected: {blocker.value}",
                "retryable": False,
            },
        }

    # source-specific hints (selector override 등)
    from crawling.sources._registry import get_source_instance
    src = get_source_instance(source_id)
    hints = src.extract_source_specific_hints(html) if src else {}

    # extraction
    result: Optional[dict] = None
    if strategy in _EXTRACT_ONLY_STRATEGIES:
        result = _specific_extraction(html, url, source_id, strategy)
    else:
        result = _best_extraction(html, url, source_id)

    # apply hints: selector-based override if cascade failed or hints override
    if (result is None or not result.get("body")) and hints.get("selectors"):
        result = _dom_with_hints(html, url, source_id, hints)

    if result is None:
        tried = list(state["strategies_tried"]) + [strategy]
        return {
            "extraction_result": None,
            "strategies_tried": tried,
            "current_error": {
                "source_id": source_id,
                "url": url,
                "attempt_no": attempt,
                "strategy": strategy,
                "error_type": "EXTRACTION_EMPTY",
                "raw_message": "extract_content: all extractors returned empty",
                "retryable": True,
            },
        }

    # save extracted text artifact
    result.setdefault("url", url)
    txt_path = save_extracted_text(run_id, source_id, uh, strategy, result)
    tried = list(state["strategies_tried"]) + [strategy]
    return {
        "extraction_result": result,
        "strategies_tried": tried,
        "extracted_text_path": str(txt_path),
    }


def _dom_with_hints(html: str, url: str, source_id: str, hints: dict) -> Optional[dict]:
    """source-specific selectors를 우선 적용한 DOM 추출."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        selectors = hints.get("selectors", [])
        body = None
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 100:
                    body = text
                    break
        if not body:
            return None
        from crawling.tools.metadata_extractor import extract_metadata, detect_language_hint
        meta = extract_metadata(html, url)
        return {
            "title": meta.get("og_title") or meta.get("title"),
            "body": body,
            "author": meta.get("author"),
            "published_at": meta.get("published_at"),
            "language": detect_language_hint(body),
            "metadata": meta,
            "strategy": "source_specific",
            "url": url,
            "source_id": source_id,
        }
    except Exception as exc:
        logger.warning("_dom_with_hints error: %s", exc)
        return None


def _node_score_quality(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    result = state.get("extraction_result") or {}
    spec = state["source_spec"]
    source_type = spec.get("type", "news")
    logger.info("[%s] score_quality", source_id)

    from crawling.core.quality_score import build_metrics_from_extraction, compute_quality_score, determine_quality_status
    from crawling.core.error_taxonomy import classify_content_blocker

    html = state.get("raw_html") or ""
    blocker = classify_content_blocker(html.lower())
    is_blocked = blocker is not None

    metrics = build_metrics_from_extraction(
        title=result.get("title"),
        body=result.get("body"),
        author=result.get("author"),
        published_at=result.get("published_at"),
        language=result.get("language"),
        metadata=result.get("metadata", {}),
    )
    score = compute_quality_score(metrics, source_type=source_type)  # type: ignore[arg-type]
    status = determine_quality_status(score, is_blocked=is_blocked)

    logger.info(
        "[PHASE%d][%s][attempt=%d][%s] %s score=%.3f",
        state["phase"],
        source_id,
        state["attempt_no"],
        state["current_strategy"],
        status,
        score,
    )

    attempt_record = {
        "attempt_no": state["attempt_no"],
        "strategy": state["current_strategy"],
        "status": status,
        "quality_score": round(score, 4),
        "error_type": (state.get("current_error") or {}).get("error_type"),
        "artifact_paths": {
            "raw_html": state.get("raw_html_path"),
            "screenshot": state.get("screenshot_path"),
            "dom_snapshot": state.get("dom_snapshot_path"),
            "extracted_text": state.get("extracted_text_path"),
        },
    }
    retry_history = list(state.get("retry_history", [])) + [attempt_record]

    return {
        "quality_score": score,
        "quality_status": status,
        "retry_history": retry_history,
    }


def _node_retry_decision(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    status = state["quality_status"]
    attempt = state["attempt_no"]
    max_att = state["max_attempts"]
    exhausted = state["strategy_exhausted"]
    err = state.get("current_error")

    logger.info("[%s] retry_decision: status=%s attempt=%d/%d exhausted=%s",
                source_id, status, attempt, max_att, exhausted)

    errors = list(state["errors"])
    if err:
        errors.append(err)

    should_retry = False
    retry_reason = ""

    if status in ("SUCCESS", "PARTIAL"):
        should_retry = False
    elif exhausted or attempt >= max_att:
        should_retry = False
    elif err and err.get("retryable", False):
        should_retry = True
        retry_reason = err.get("error_type", "")
    elif status == "FAILED":
        should_retry = not exhausted and attempt < max_att
        retry_reason = "quality_below_threshold"

    return {
        "should_retry": should_retry,
        "retry_reason": retry_reason,
        "attempt_no": attempt + 1,
        "errors": errors,
        "current_error": None,
    }


def _node_error_analysis(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    err = state.get("current_error") or {}
    error_type = err.get("error_type", "UNKNOWN_ERROR")
    logger.warning("[%s] error_analysis: %s - %s", source_id, error_type, err.get("raw_message", ""))

    from crawling.core.error_taxonomy import ErrorType, BLOCKED_ERRORS, RETRYABLE_ERRORS

    try:
        et = ErrorType(error_type)
        is_blocked = et in BLOCKED_ERRORS
        retryable = et in RETRYABLE_ERRORS
    except ValueError:
        is_blocked = False
        retryable = False

    if is_blocked:
        quality_status = "BLOCKED"
        should_retry = False
    else:
        quality_status = state.get("quality_status", "FAILED")
        should_retry = retryable

    updated_err = {**err, "retryable": retryable, "is_blocker": is_blocked}
    return {
        "current_error": updated_err,
        "quality_status": quality_status,
        "should_retry": should_retry,
    }


def _node_extract_event_candidates(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    result = state.get("extraction_result") or {}
    logger.info("[%s] extract_event_candidates", source_id)

    from crawling.agents.llm_judge import create_judge_client
    from crawling.schemas.event_candidate import EventCandidate

    judge = create_judge_client()
    title = result.get("title", "")
    body_snippet = (result.get("body") or "")[:500]
    url = state["current_url"]

    prompt = (
        f"Extract structured event information.\n"
        f"title: {title}\n"
        f"snippet: {body_snippet}\n"
        f"url: {url}\n"
        f"source_id: {source_id}\n"
        f"Return JSON matching EventCandidate schema. "
        f"Do NOT include investment advice or buy/sell recommendations."
    )
    candidate = judge.complete_json(prompt, schema=EventCandidate)
    candidates = []
    if candidate:
        d = candidate.model_dump()
        d["source_id"] = source_id
        d["url"] = url
        d["extraction_strategy"] = state["current_strategy"]
        d["llm_judged"] = True
        candidates = [d]

    return {"event_candidates": candidates}


def _node_llm_quality_judge(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    result = state.get("extraction_result") or {}
    logger.info("[%s] llm_quality_judge", source_id)

    from crawling.agents.llm_judge import create_judge_client
    from pydantic import BaseModel

    class JudgeOutput(BaseModel):
        is_valid: bool
        confidence: float
        reason: str

    judge = create_judge_client()
    title = result.get("title", "")
    snippet = (result.get("body") or "")[:300]
    prompt = (
        f"Assess extraction quality.\n"
        f"title: {title}\n"
        f"snippet: {snippet}\n"
        f"Return JSON: {{\"is_valid\": bool, \"confidence\": float, \"reason\": str}}"
    )
    output = judge.complete_json(prompt, schema=JudgeOutput)
    return {"llm_judge_result": output.model_dump() if output else None}


def _node_strategy_reflection(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    tried = state.get("strategies_tried", [])
    status = state["quality_status"]
    score = state["quality_score"]
    logger.info("[%s] strategy_reflection: status=%s score=%.3f tried=%s",
                source_id, status, score, tried)
    reflection = {
        "strategies_tried": tried,
        "final_status": status,
        "final_score": score,
        "winning_strategy": state.get("current_strategy") if status in ("SUCCESS", "PARTIAL") else None,
    }
    return {"final_report": {**(state.get("final_report") or {}), "reflection": reflection}}


def _node_write_source_report(state: CrawlingAgentState) -> dict:
    source_id = state["source_id"]
    spec = state["source_spec"]
    logger.info("[%s] write_source_report", source_id)

    from pathlib import Path
    from crawling.schemas.source_report import SourceReport
    from crawling.core.report_writer import write_source_report
    from crawling.core.artifact_store import append_result_row

    report = SourceReport(
        source_id=source_id,
        source_name=spec.get("name", source_id),
        source_type=spec.get("type", "news"),
        evidence_level=spec.get("evidence_level", "tier3"),
        phase=state["phase"],
        status=state["quality_status"],
        quality_score=state["quality_score"],
        attempts=state["attempt_no"],
        strategy_used=state.get("current_strategy"),
        urls_crawled=len(state.get("candidate_urls", [])),
        articles_extracted=1 if state.get("extraction_result") else 0,
        event_candidates_found=len(state.get("event_candidates", [])),
        errors=state.get("errors", []),
        known_blockers_hit=[
            e["error_type"] for e in state.get("errors", [])
            if e.get("is_blocker")
        ],
    )

    output_dir = Path(__file__).parent.parent / "outputs" / "reports"
    report_path = write_source_report(report, output_dir)
    logger.info("[%s] report written: %s", source_id, report_path)

    result = state.get("extraction_result") or {}
    body = result.get("body") or ""
    row = {
        "run_id": state.get("run_id"),
        "source_id": source_id,
        "phase": state["phase"],
        "status": state["quality_status"],
        "quality_score": round(state["quality_score"], 4),
        "attempts": state["attempt_no"],
        "strategy_used": state.get("current_strategy"),
        "url": state.get("current_url"),
        "title": result.get("title"),
        "body_char_count": len(body),
        "artifact_paths": {
            "raw_html": state.get("raw_html_path"),
            "screenshot": state.get("screenshot_path"),
            "dom_snapshot": state.get("dom_snapshot_path"),
            "extracted_text": state.get("extracted_text_path"),
        },
        "retry_history": state.get("retry_history", []),
        "errors": state.get("errors", []),
    }
    append_result_row(state["phase"], source_id, row)

    return {
        "status": state["quality_status"],
        "final_report": report.model_dump(mode="json"),
    }


# ──────────────────────── Routing functions ────────────────────────

def _route_fetch_entry(state: CrawlingAgentState) -> str:
    if state.get("raw_html") and not state.get("current_error"):
        return "success"
    return "error"


def _route_fetch_target(state: CrawlingAgentState) -> str:
    if state.get("raw_html") and not state.get("current_error"):
        return "success"
    return "error"


def _route_extract_content(state: CrawlingAgentState) -> str:
    if state.get("extraction_result") and not state.get("current_error"):
        return "success"
    return "error"


def _route_retry_decision(state: CrawlingAgentState) -> str:
    if state["quality_status"] in ("SUCCESS", "PARTIAL"):
        return "pass"
    if state["should_retry"] and not state["strategy_exhausted"]:
        return "retry"
    return "exhaust"


# ──────────────────────── Graph builder ────────────────────────

def build_graph() -> StateGraph:
    g: StateGraph = StateGraph(CrawlingAgentState)

    g.add_node("initialize", _node_initialize)
    g.add_node("build_search_query", _node_build_search_query)
    g.add_node("fetch_entry_url", _node_fetch_entry_url)
    g.add_node("extract_candidate_urls", _node_extract_candidate_urls)
    g.add_node("fetch_target_page", _node_fetch_target_page)
    g.add_node("select_extraction_strategy", _node_select_extraction_strategy)
    g.add_node("extract_content", _node_extract_content)
    g.add_node("score_quality", _node_score_quality)
    g.add_node("retry_decision", _node_retry_decision)
    g.add_node("error_analysis", _node_error_analysis)
    g.add_node("extract_event_candidates", _node_extract_event_candidates)
    g.add_node("llm_quality_judge", _node_llm_quality_judge)
    g.add_node("strategy_reflection", _node_strategy_reflection)
    g.add_node("write_source_report", _node_write_source_report)

    g.set_entry_point("initialize")
    g.add_edge("initialize", "build_search_query")
    g.add_edge("build_search_query", "fetch_entry_url")

    g.add_conditional_edges(
        "fetch_entry_url",
        _route_fetch_entry,
        {"success": "extract_candidate_urls", "error": "error_analysis"},
    )
    g.add_edge("extract_candidate_urls", "fetch_target_page")

    g.add_conditional_edges(
        "fetch_target_page",
        _route_fetch_target,
        {"success": "select_extraction_strategy", "error": "error_analysis"},
    )
    g.add_edge("select_extraction_strategy", "extract_content")

    g.add_conditional_edges(
        "extract_content",
        _route_extract_content,
        {"success": "score_quality", "error": "error_analysis"},
    )
    g.add_edge("score_quality", "retry_decision")
    g.add_edge("error_analysis", "retry_decision")

    g.add_conditional_edges(
        "retry_decision",
        _route_retry_decision,
        {
            "pass": "extract_event_candidates",
            "retry": "select_extraction_strategy",
            "exhaust": "strategy_reflection",
        },
    )

    g.add_edge("extract_event_candidates", "llm_quality_judge")
    g.add_edge("llm_quality_judge", "strategy_reflection")
    g.add_edge("strategy_reflection", "write_source_report")
    g.add_edge("write_source_report", END)

    return g


_compiled = None


def get_compiled_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph().compile()
    return _compiled

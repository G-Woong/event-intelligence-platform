from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("crawling.core.artifact_store")

_OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"


def new_run_id(phase: int, source_id: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}_phase{phase}_{source_id}"


def url_hash(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:8]


def save_raw_html(run_id: str, source_id: str, uh: str, strategy: str, html: str) -> Path:
    path = _OUTPUTS_DIR / "raw_html" / source_id / f"{run_id}_{uh}_{strategy}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    logger.debug("raw_html saved: %s", path)
    return path


def save_dom_snapshot(run_id: str, source_id: str, uh: str, strategy: str, snapshot: dict) -> Path:
    path = _OUTPUTS_DIR / "dom_snapshots" / source_id / f"{run_id}_{uh}_{strategy}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug("dom_snapshot saved: %s", path)
    return path


def get_screenshot_path(run_id: str, source_id: str, uh: str) -> Path:
    path = _OUTPUTS_DIR / "screenshots" / source_id / f"{run_id}_{uh}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_extracted_text(
    run_id: str,
    source_id: str,
    uh: str,
    strategy: str,
    fields: dict,
) -> Path:
    path = _OUTPUTS_DIR / "extracted_text" / source_id / f"{run_id}_{uh}_{strategy}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)

    header_lines = [
        f"title: {fields.get('title', '')}",
        f"published_at: {fields.get('published_at', '')}",
        f"source_url: {fields.get('url', '')}",
        f"selected_strategy: {strategy}",
        f"quality_score: {fields.get('quality_score', '')}",
        "---",
    ]
    body = fields.get("body") or ""
    content = "\n".join(header_lines) + "\n" + body
    path.write_text(content, encoding="utf-8")
    logger.debug("extracted_text saved: %s", path)
    return path


def append_result_row(phase: int, source_id: str, row: dict) -> None:
    for jsonl_path in [
        _OUTPUTS_DIR / "jsonl" / f"phase{phase}_results.jsonl",
        _OUTPUTS_DIR / "jsonl" / f"{source_id}_results.jsonl",
    ]:
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def build_dom_snapshot_dict(
    url: str,
    html: str,
    strategy: str,
    *,
    extra: Optional[dict] = None,
) -> dict:
    """HTML에서 진단용 DOM 스냅샷 dict 생성 (LLM 전달 없이 사람이 읽는 용)."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        h1_tags = [t.get_text(strip=True) for t in soup.find_all("h1")][:5]
        h2_tags = [t.get_text(strip=True) for t in soup.find_all("h2")][:5]
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 30]
        link_count = len(soup.find_all("a"))
        para_count = len(paragraphs)

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        article_selectors = ["article", '[role="main"]', ".article-body", ".post-content",
                              ".entry-content", ".story-body", "#article-content", ".news-body", "main"]
        selector_hits = []
        for sel in article_selectors:
            el = soup.select_one(sel)
            if el:
                text_len = len(el.get_text(strip=True))
                selector_hits.append({"selector": sel, "text_length": text_len})

        visible_blocks = paragraphs[:10]

    except Exception as exc:
        return {"url": url, "strategy": strategy, "error": str(exc)}

    snapshot = {
        "url": url,
        "strategy": strategy,
        "title": title,
        "h1_headings": h1_tags,
        "h2_headings": h2_tags,
        "link_count": link_count,
        "paragraph_count": para_count,
        "article_selector_hits": selector_hits,
        "visible_text_blocks": visible_blocks,
    }
    if extra:
        snapshot.update(extra)
    return snapshot

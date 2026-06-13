from __future__ import annotations

import logging

from ingestion.core.artifact_store import (
    new_run_id,
    save_raw_html,
    save_raw_signal,
    save_rendered_dom,
    url_hash,
)
from ingestion.fetch_strategies.models import ArtifactPaths, CollectionProbeResult

logger = logging.getLogger("ingestion.fetch_strategies.artifact_writer")


def write_collection_artifacts(result: CollectionProbeResult) -> ArtifactPaths:
    """Persist html / markdown / screenshot / signal from a CollectionProbeResult once.

    Delegates to existing save_* functions in artifact_store.
    Propagates already-saved paths from probe_result.artifact_paths.
    """
    source_id = result.source_id
    run_id = new_run_id(0, source_id)

    url = ""
    if result.extraction and result.extraction.rendered_page:
        url = result.extraction.rendered_page.url
    elif result.probe_result:
        url = ""  # api probes save their own artifacts; URL not needed here

    uh = url_hash(url) if url else "nohash"
    paths = ArtifactPaths()

    rendered_page = result.extraction and result.extraction.rendered_page

    if rendered_page and rendered_page.html:
        try:
            p = save_raw_html(run_id, source_id, uh, rendered_page.strategy_used, rendered_page.html)
            paths.raw_html = str(p)
        except Exception as exc:
            logger.warning("save_raw_html failed for %s: %s", source_id, exc)

        try:
            p = save_rendered_dom(run_id, source_id, uh, rendered_page.html)
            paths.rendered_dom = str(p)
        except Exception as exc:
            logger.warning("save_rendered_dom failed for %s: %s", source_id, exc)

    if result.extraction and result.extraction.markdown:
        try:
            p = save_raw_signal(run_id, source_id, uh, result.extraction.markdown)
            paths.raw_signal = str(p)
        except Exception as exc:
            logger.warning("save_raw_signal failed for %s: %s", source_id, exc)

    # Propagate pre-saved paths from api probe
    existing = result.artifact_paths
    paths.raw_payload = paths.raw_payload or existing.raw_payload
    paths.extracted_payload = paths.extracted_payload or existing.extracted_payload
    paths.screenshot = paths.screenshot or existing.screenshot

    return paths

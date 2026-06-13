from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ingestion.core.env_loader import load_env
from ingestion.fetch_strategies.collection_probe import run_collection_probe


def _enrich_from_raw_payload(result) -> dict:
    """Route 1 결과 보강: raw_payload에서 items/sample_title/sample_url 산출.

    xml 소스 → 첫 <item>의 title/link. html 소스 → 소스 구현체의
    extract_candidate_urls. 0건이어도 실패가 아니라 next_action='update_selector'.
    """
    enrichment: dict = {
        "items_found": result.items_found,
        "sample_title": None,
        "sample_url": None,
    }
    raw_path = result.artifact_paths.raw_payload
    if not raw_path or not Path(raw_path).exists():
        return enrichment
    try:
        text = Path(raw_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return enrichment

    stripped = text.lstrip()
    if stripped.startswith("<?xml") or "<rss" in stripped[:500] or "<feed" in stripped[:500]:
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(text)
            items = root.findall(".//item") or root.findall(
                ".//{http://www.w3.org/2005/Atom}entry"
            )
            enrichment["items_found"] = len(items)
            if items:
                first = items[0]
                # ET Element는 자식이 없으면 falsy — `or` 체인 대신 None 비교
                title_el = first.find("title")
                if title_el is None:
                    title_el = first.find("{http://www.w3.org/2005/Atom}title")
                link_el = first.find("link")
                if link_el is None:
                    link_el = first.find("{http://www.w3.org/2005/Atom}link")
                if title_el is not None and title_el.text:
                    enrichment["sample_title"] = title_el.text.strip()[:120]
                if link_el is not None:
                    enrichment["sample_url"] = (
                        link_el.text.strip() if link_el.text
                        else link_el.get("href", "")
                    )
        except Exception:
            pass
    else:
        # HTML 소스: 소스 구현체의 selector로 후보 URL 추출
        try:
            from ingestion.sources._registry import get_source_instance
            instance = get_source_instance(result.source_id)
            if instance is not None:
                urls = instance.extract_candidate_urls(text)
                enrichment["items_found"] = len(urls)
                if urls:
                    enrichment["sample_url"] = urls[0]
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(text, "lxml")
                    if soup.title and soup.title.string:
                        enrichment["sample_title"] = soup.title.string.strip()[:120]
                except Exception:
                    pass
        except Exception:
            pass

    if enrichment["items_found"] == 0 and result.status in ("LIVE_SUCCESS", "LIVE_PARTIAL"):
        enrichment["next_action"] = "update_selector"
    return enrichment


def _attempts_dump(result) -> list[dict]:
    return [
        {
            "strategy": a.strategy,
            "success": a.success,
            "error_type": a.error_type.value if a.error_type else None,
            "elapsed_sec": round(a.elapsed_sec, 2),
        }
        for a in result.attempts
    ]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a single collection probe for one source (1 live call)."
    )
    parser.add_argument("--source", required=True, help="source_id")
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--query", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="Bypass the health gate (수동 unquarantine 점검)")
    args = parser.parse_args(argv)

    load_env()

    # Health gate 사전 안내 (실제 gate는 run_collection_probe 내부에서 적용)
    try:
        from ingestion.core.source_health import get_health_store, should_skip
        state = get_health_store().get(args.source)
        skip, reason = should_skip(state)
        if skip and not args.force:
            print(f"NOTE: health gate will skip this source ({reason}). "
                  f"Use --force to bypass.")
    except Exception:
        pass

    result = run_collection_probe(
        args.source, query=args.query, max_items=args.max_items, force=args.force
    )
    enrichment = _enrich_from_raw_payload(result)

    report = {
        "source_id": result.source_id,
        "status": result.status,
        "strategy_used": result.strategy_used,
        "items_found": enrichment["items_found"],
        "sample_title": enrichment["sample_title"],
        "sample_url": enrichment["sample_url"],
        "error_category": result.error_category,
        "next_action": enrichment.get("next_action", result.next_action),
        "artifact_paths": result.artifact_paths.to_dict(),
        "attempts": _attempts_dump(result),
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for k in ("source_id", "status", "strategy_used", "items_found",
                  "sample_title", "sample_url", "error_category", "next_action"):
            try:
                print(f"{k}: {report[k]}")
            except UnicodeEncodeError:
                print(f"{k}: {str(report[k]).encode('ascii', errors='replace').decode('ascii')}")
        for name, path in report["artifact_paths"].items():
            print(f"artifact.{name}: {path}")

    return 0 if result.status in ("LIVE_SUCCESS", "LIVE_PARTIAL", "RATE_LIMITED") else 1


if __name__ == "__main__":
    sys.exit(main())

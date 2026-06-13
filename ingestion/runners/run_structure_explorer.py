"""페이지 구조 탐색 툴킷 — selector 복구 표준 절차 (docs/06).

탐색 루프 (selector 복구 표준 절차):
1. run_structure_explorer --site X            → live 1회, DOM·network·후보 확보
2. 보고서의 YAML 패치를 playwright_probe_sites.yaml에 적용
3. run_playwright_probe --site X              → items_found ≥ 기대치 검증
4. 실패 시 run_structure_explorer --offline-dom <1의 DOM 경로> --max-candidates 20
   으로 재채굴 (live 재호출 없이) → 2로
5. Hidden API가 발견되면 selector 대신 Route 1(API probe) 전환을 우선 검토
   — JSON API > CSS selector (안정성 서열).

출력은 사람이 읽는 보고서가 아니라 그대로 YAML에 붙일 수 있는 selector 제안 패치다.
원문 장문은 보고서에 싣지 않는다 (sample_texts 120자 절단, network body 미수록).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urlparse

_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import ingestion.tools.playwright_browser_tool as _pbt
from ingestion.core.artifact_store import (
    get_screenshot_path,
    new_run_id,
    save_rendered_dom,
    url_hash,
)
from ingestion.core.error_taxonomy import classify_content_blocker
from ingestion.probes.playwright_probe import _detect_429
from ingestion.probes.site_specs import load_site_specs
from ingestion.runners._audit_common import (
    OUTPUT_JSONL_DIR,
    OUTPUT_REPORTS_DIR,
    audit_timestamp,
    gate_check,
    safe_print,
)

logger = logging.getLogger("ingestion.runners.run_structure_explorer")

_OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"
_MIN_GROUP_SIZE = 5
_MIN_TEXT_LEN = 3
_SAMPLE_TEXT_MAX = 120


def _mask_url(url: str) -> str:
    """URL query string의 key/token 류 파라미터를 *** 로 마스킹."""
    return re.sub(
        r"(key|token|apikey|api_key|serviceKey)=[^&]+",
        r"\1=***",
        url or "",
        flags=re.I,
    )


def _is_hash_class(cls: str) -> bool:
    """styled-components / CSS-in-JS 해시 클래스 패턴 감지 (재빌드에 깨짐)."""
    if cls.startswith(("css-", "sc-", "jss")):
        return True
    # 하이픈/언더스코어 없는 6자 이상 영숫자 혼합 = 무작위 해시일 확률 높음
    if len(cls) >= 6 and re.fullmatch(r"[A-Za-z0-9]+", cls) and re.search(r"\d", cls):
        return True
    return False


def _serialize_selector(tag: str, classes: frozenset, sample_el) -> str:
    if classes:
        return tag + "".join(f".{c}" for c in sorted(classes))
    parent = sample_el.parent if sample_el is not None else None
    if parent is not None and parent.get("class"):
        psel = parent.name + "".join(f".{c}" for c in sorted(parent.get("class")))
        return f"{psel} > {tag}"
    if parent is not None and parent.name:
        return f"{parent.name} > {tag}"
    return tag


def mine_selector_candidates(html: str, max_candidates: int = 10) -> list[dict]:
    """반복 DOM 구조를 탐지해 selector 후보를 점수순으로 반환.

    반환 item: {selector, match_count, sample_texts(≤3, 120자), has_links, stability}.
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "lxml")
    except Exception as exc:
        logger.warning("mine_selector_candidates parse failed: %s", exc)
        return []

    # (tag, class frozenset) 시그니처별 그룹화
    groups: dict[tuple, list] = {}
    for el in soup.find_all(True):
        text = el.get_text(strip=True)
        if len(text) < _MIN_TEXT_LEN:
            continue
        sig = (el.name, frozenset(el.get("class") or []))
        groups.setdefault(sig, []).append(el)

    candidates: list[dict] = []
    for (tag, classes), els in groups.items():
        if len(els) < _MIN_GROUP_SIZE:
            continue
        texts = [e.get_text(strip=True) for e in els]
        avg_len = sum(len(t) for t in texts) / len(texts)
        links = sum(1 for e in els if e.name == "a" or e.find("a", href=True))
        has_links_ratio = links / len(els)
        is_hash = any(_is_hash_class(c) for c in classes)
        mc = len(els)

        # 점수화: 매칭수(5~30 최적) + 텍스트 길이 + 링크 비율 + class 보유 - 해시 감점
        if 5 <= mc <= 30:
            count_score = 30.0
        else:
            count_score = max(0.0, 30.0 - (mc - 30))
        score = count_score
        score += min(avg_len, 80.0) * 0.3
        score += has_links_ratio * 15.0
        if classes:
            score += 20.0
        if is_hash:
            score -= 25.0

        candidates.append({
            "selector": _serialize_selector(tag, classes, els[0]),
            "match_count": mc,
            "sample_texts": [t[:_SAMPLE_TEXT_MAX] for t in texts[:3]],
            "has_links": has_links_ratio > 0.5,
            "stability": "fragile" if is_hash else "stable",
            "_score": round(score, 2),
        })

    candidates.sort(key=lambda c: c["_score"], reverse=True)
    return candidates[:max_candidates]


def _check_existing_selectors(html: str, spec) -> list[dict]:
    """site spec의 기존 list selector별 매칭 수 + 첫 매칭 텍스트(120자)."""
    out: list[dict] = []
    if spec is None or not spec.selectors:
        return out
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "lxml")
    except Exception:
        return out
    for sel in spec.selectors.get("list", []):
        try:
            found = soup.select(sel)
        except Exception:
            out.append({"selector": sel, "match_count": -1, "first_text": "(invalid selector)"})
            continue
        first = found[0].get_text(strip=True)[:_SAMPLE_TEXT_MAX] if found else ""
        out.append({"selector": sel, "match_count": len(found), "first_text": first})
    return out


def _summarize_network(entries: list[dict]) -> list[dict]:
    """network log에서 JSON 응답(200, list/dict body) 후보만 요약. body 전문 미수록."""
    out: list[dict] = []
    for e in entries or []:
        ct = (e.get("content_type") or "").lower()
        if "json" not in ct or e.get("status") != 200:
            continue
        body = e.get("json_body")
        summary: dict = {
            "url": _mask_url(e.get("url", "")),
            "method": e.get("method"),
        }
        if isinstance(body, dict):
            summary["json_keys"] = list(body.keys())[:20]
            summary["list_lengths"] = {
                k: len(v) for k, v in body.items() if isinstance(v, list)
            }
        elif isinstance(body, list):
            summary["json_keys"] = ["<root list>"]
            summary["list_lengths"] = {"<root>": len(body)}
        else:
            continue
        out.append(summary)
    return out


def _build_url(spec, query: Optional[str], region: Optional[str]) -> str:
    url = spec.start_url
    if region:
        url = url.replace("{region}", region)
    elif "{region}" in url:
        url = url.replace("{region}", "KR")
    search_url = getattr(spec, "search_url", "")
    if query and search_url:
        url = search_url
        if region:
            url = url.replace("{region}", region)
        elif "{region}" in url:
            url = url.replace("{region}", "KR")
    if query:
        url = url.replace("{query}", quote_plus(query))
    elif "{query}" in url:
        url = url.replace("{query}", "samsung")
    return url


def _latest_rendered_dom(site_id: str) -> Optional[Path]:
    folder = _OUTPUTS_DIR / "rendered_dom" / site_id
    if not folder.exists():
        return None
    files = sorted(folder.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


async def _fetch(url: str, wait_ms: int, scroll: bool, wait_selector: Optional[str],
                 ss_path: Path):
    html = await _pbt.open_page(
        url,
        wait_until="networkidle",
        timeout_ms=45000,
        scroll=scroll,
        wait_after_ms=wait_ms,
        wait_selector=wait_selector,
        screenshot_path=ss_path,
        capture_network=True,
    )
    network = list(_pbt.last_network_log)
    return html, network


def explore(
    site_id_or_url: str,
    query: Optional[str] = None,
    region: Optional[str] = None,
    wait_ms: int = 3000,
    offline_dom: Optional[str] = None,
    max_candidates: int = 10,
) -> dict:
    """사이트/URL을 탐색해 selector 후보·network API·기존 selector 진단을 반환."""
    specs = load_site_specs()
    spec = specs.get(site_id_or_url)
    if spec is not None:
        site_id = site_id_or_url
        url = _build_url(spec, query, region)
    else:
        site_id = urlparse(site_id_or_url).netloc.replace(".", "_") or "adhoc"
        url = site_id_or_url

    report: dict = {
        "site": site_id,
        "url": _mask_url(url),
        "verdict": "OK",
        "source": "offline" if offline_dom else "live",
        "existing_selectors": [],
        "network_api_candidates": [],
        "candidates": [],
    }

    network: list[dict] = []
    if offline_dom:
        try:
            html = Path(offline_dom).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            report["verdict"] = "OFFLINE_DOM_READ_ERROR"
            report["error"] = str(exc)
            return report
    else:
        if spec is not None:
            skip = gate_check(site_id)
            if skip:
                latest = _latest_rendered_dom(site_id)
                if latest is not None:
                    report["source"] = f"offline_fallback({skip})"
                    html = latest.read_text(encoding="utf-8", errors="replace")
                else:
                    report["verdict"] = f"GATE_SKIP:{skip}"
                    return report
            else:
                html = _run_live(spec, site_id, url, wait_ms, report)
                network = report.pop("_network", [])
        else:
            html = _run_live(spec, site_id, url, wait_ms, report)
            network = report.pop("_network", [])

    if not html:
        report["verdict"] = "NO_HTML"
        return report

    # 전처리: 차단 페이지의 DOM에서 selector 제안 금지
    if _detect_429(html):
        report["verdict"] = "RATE_LIMITED"
        return report
    blocker = classify_content_blocker(html.lower())
    if blocker is not None:
        report["verdict"] = f"BLOCKED:{blocker.value}"
        return report

    report["network_api_candidates"] = _summarize_network(network)
    report["existing_selectors"] = _check_existing_selectors(html, spec)
    report["candidates"] = mine_selector_candidates(html, max_candidates)
    return report


def _run_live(spec, site_id: str, url: str, wait_ms: int, report: dict) -> Optional[str]:
    run_id = new_run_id(0, site_id)
    uh = url_hash(url)
    ss_path = get_screenshot_path(run_id, site_id, uh)
    scroll = True
    wait_selector = None
    if spec is not None and spec.selectors:
        wait_selector = spec.selectors.get("wait_for")
        scroll = spec.search_strategy in ("page_load_scroll", "page_load_wait_js")
    html, network = asyncio.run(_fetch(url, wait_ms, scroll, wait_selector, ss_path))
    report["_network"] = network
    report["screenshot"] = str(ss_path)
    if html:
        try:
            dom_path = save_rendered_dom(run_id, site_id, uh, html)
            report["rendered_dom"] = str(dom_path)
        except Exception as exc:
            logger.warning("rendered_dom save failed: %s", exc)
    return html


def _render_report_md(report: dict) -> str:
    lines = [
        f"# Structure Explorer — {report['site']}",
        "",
        f"- url: `{report['url']}`",
        f"- source: {report['source']}",
        f"- verdict: **{report['verdict']}**",
        "",
        "## Existing selectors (match count)",
        "",
    ]
    for s in report.get("existing_selectors", []):
        lines.append(f"- `{s['selector']}` → {s['match_count']} (`{s['first_text']}`)")
    lines += ["", "## Mined selector candidates", ""]
    for c in report.get("candidates", []):
        lines.append(
            f"- `{c['selector']}` → match={c['match_count']} "
            f"links={c['has_links']} stability={c['stability']} score={c['_score']}"
        )
        for t in c["sample_texts"]:
            lines.append(f"    - {t}")
    # YAML 패치 제안
    top = [c for c in report.get("candidates", []) if c["stability"] == "stable"][:2]
    top = top or report.get("candidates", [])[:2]
    if top:
        lines += ["", "## Proposed YAML patch (playwright_probe_sites.yaml)", "", "```yaml",
                  f"{report['site']}:", "  selectors:", "    list:"]
        for c in top:
            lines.append(f'      - "{c["selector"]}"')
        lines.append(f'    wait_for: "{top[0]["selector"]}"')
        lines.append("```")
    apis = report.get("network_api_candidates", [])
    if apis:
        lines += ["", "## Hidden API candidates", ""]
        for a in apis:
            lines.append(f"- {a['url']} — keys: {a.get('json_keys')} lengths: {a.get('list_lengths')}")
    return "\n".join(lines) + "\n"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Page structure explorer (selector recovery).")
    parser.add_argument("--site", default=None, help="site_id in playwright_probe_sites.yaml")
    parser.add_argument("--url", default=None, help="direct URL (alternative to --site)")
    parser.add_argument("--query", default=None)
    parser.add_argument("--region", default=None)
    parser.add_argument("--wait-ms", type=int, default=3000)
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--offline-dom", default=None, help="analyze a saved rendered_dom file (no network)")
    args = parser.parse_args(argv)

    target = args.site or args.url
    if not target:
        parser.error("one of --site or --url is required")

    report = explore(
        target, query=args.query, region=args.region, wait_ms=args.wait_ms,
        offline_dom=args.offline_dom, max_candidates=args.max_candidates,
    )

    ts = audit_timestamp()
    jsonl_path = OUTPUT_JSONL_DIR / f"structure_explorer_{report['site']}_{ts}.jsonl"
    md_path = OUTPUT_REPORTS_DIR / f"structure_explorer_{report['site']}_{ts}.md"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False, default=str) + "\n")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_render_report_md(report), encoding="utf-8")

    safe_print(f"verdict={report['verdict']} candidates={len(report['candidates'])} "
               f"apis={len(report['network_api_candidates'])}")
    safe_print(f"jsonl: {jsonl_path}")
    safe_print(f"report: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

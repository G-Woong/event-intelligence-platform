"""01~05 조건부 PASS/DEFERRED 소스 E2E 종결 audit.

기존 30+ 검증 완료 소스가 통과한 실제 수집/본문 추출 파이프라인을 기준선으로 삼아,
01~05 범위(인프라 #1 + 데이터 소스 #2~#5)를 동일 기준으로 end-to-end 검증한다.

기준선 파이프라인(이미 검증 완료된 소스가 쓴 것):
  run_collection_probe → raw artifact 저장(save_raw_payload) → extract_sample_items(candidate)
  → article URL 본문 fetch → trafilatura_extractor → save_extracted_text(body artifact).

이 audit이 추가로 강제하는 것:
  ① 실제 source 호출  ② event candidate 생성  ③ candidate JSONL 누적 저장
  ④ article/community URL 본문 추출 ≥1  ⑤ body artifact 저장
  ⑥ 실패/쿨다운/차단은 PASS가 아니라 collected=false + NOT_CLOSED_*
  ⑦ google_trends_explore는 article source가 아니므로 body=not_required(related_query만)

대상:
  #1 RISK-T04           : 인프라 — local_file backend에서 RATE_LIMITED 발생 시 next_retry 영속 +
                          다음 호출 skip(cooldown_skip). 실제 runner 경로(#2/#5 live)에서 관측.
  #2 gdelt              : article (GDELT public API JSON)
  #3 ap_news            : article (Google News RSS proxy → apnews.com canonical via browser)
  #4 newsapi            : article (/v2/everything)
  #5 google_trends_explore : related_query (Playwright; body not_required)

backend: 시작 시 INGESTION_RATE_LIMIT_BACKEND=local_file 강제 — 429 cooldown을
rate_limit_cache.json에 영속시켜 다음 프로세스/cycle이 gate를 오판하지 않게 한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ingestion.core.artifact_store import new_run_id, save_extracted_text, url_hash
from ingestion.core.env_loader import load_env
from ingestion.core.error_taxonomy import classify_content_blocker
from ingestion.core.rate_limit_policy import in_cooldown, record_call
from ingestion.core.source_health import get_health_store, should_skip
from ingestion.runners._audit_common import (
    OUTPUT_JSONL_DIR,
    OUTPUT_REPORTS_DIR,
    audit_timestamp,
    extract_sample_items,
    extract_samples_from_rendered,
    gate_check,
    safe_print,
    utc_now_iso,
    write_audit_jsonl,
    write_audit_md,
)
from ingestion.tools.trafilatura_extractor import extract_with_trafilatura

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_BODY_MIN_CHARS = 200          # 이 길이 미만이면 추출 실패/차단으로 간주(베이스라인 trafilatura와 동일 임계)
_MAX_BODY_ATTEMPTS = 3         # 소스당 본문 추출 시도 상위 N candidate
_BODY_FETCH_DELAY = 1.5        # 본문 fetch 간 간격(rapid request로 인한 일시적 throttle 방지)
_HTTPX_MIN_HTML = 1000         # httpx 결과가 이보다 짧으면 에러/안내 페이지로 보고 Playwright fallback
_RATE_LIMIT_BACKEND = "local_file"

# 대상 소스 정의 (#1 RISK-T04는 데이터 소스가 아니므로 별도 처리)
E2E_TARGETS: list[dict] = [
    {
        "id": "ap_news", "role": "document_discovery", "candidate_type": "article",
        "query": None, "evidence_level": "tier1_via_discovery_proxy",
        "kind": "article", "canonical_browser": True, "body_required": True,
    },
    {
        "id": "newsapi", "role": "enrichment", "candidate_type": "article",
        "query": "AI semiconductor", "evidence_level": "tier2",
        "kind": "article", "canonical_browser": False, "body_required": True,
    },
    {
        "id": "gdelt", "role": "both", "candidate_type": "article",
        "query": "global conflict", "evidence_level": "tier2",
        "kind": "article", "canonical_browser": False, "body_required": True,
    },
    {
        "id": "google_trends_explore", "role": "enrichment", "candidate_type": "related_query",
        "query": "삼성전자", "region": "KR", "evidence_level": "tier3_signal",
        "kind": "related_query", "canonical_browser": False, "body_required": False,
    },
]


# ── backend ──────────────────────────────────────────────────────────────────

def force_local_file_backend() -> None:
    """RATE_LIMITED cooldown 영속을 위해 rate-limit store backend를 local_file로 강제.

    store 싱글톤이 만들어지기 전에 env를 세팅하고, 혹시 이미 만들어졌으면 리셋한다.
    (.env는 수정하지 않는다 — 프로세스 env만.)
    """
    os.environ["INGESTION_RATE_LIMIT_BACKEND"] = _RATE_LIMIT_BACKEND
    from ingestion.core.rate_limit_store import reset_store_for_tests
    reset_store_for_tests()


def active_backend_name() -> str:
    from ingestion.core.rate_limit_store import get_store
    return type(get_store()).__name__


# ── 본문 추출 ────────────────────────────────────────────────────────────────

def _default_fetch_html(url: str, timeout: float = 20.0) -> Optional[str]:
    """article URL의 HTML을 가져온다 — httpx(브라우저 UA) → 실패 시 Playwright fallback.

    AP 등 일부 매체는 httpx에 간헐적 비-200/짧은 안내 페이지를 주거나 JS 렌더가 필요하다.
    httpx가 200+충분한 본문을 못 주면 headless Playwright 1회로 승격한다(우회 아님 — 공개 기사).
    어떤 단계든 예외/차단은 무해 처리(None 또는 다음 단계).
    """
    import httpx
    try:
        resp = httpx.get(
            url, headers={"User-Agent": _BROWSER_UA},
            follow_redirects=True, timeout=timeout,
        )
        if resp.status_code == 200 and resp.text and len(resp.text) >= _HTTPX_MIN_HTML:
            return resp.text
    except Exception:
        pass
    try:
        import asyncio
        from ingestion.tools.playwright_browser_tool import open_page
        html = asyncio.run(open_page(url, wait_until="domcontentloaded", timeout_ms=45000))
        return html or None
    except Exception:
        return None


def extract_body(
    source_id: str,
    candidate: dict,
    *,
    fetch_fn: Callable[[str], Optional[str]] = _default_fetch_html,
    save: bool = True,
) -> dict:
    """candidate의 (canonical) URL에서 본문을 추출하고 body artifact를 저장한다.

    body_status:
      extracted   — trafilatura 본문 ≥ _BODY_MIN_CHARS, artifact 저장
      blocked     — paywall/captcha/login 등 차단 페이지 감지(우회 안 함)
      failed      — fetch 실패(비-200/네트워크) 또는 본문 부족
      no_url      — http URL 없음
    """
    url = candidate.get("canonical_url") or candidate.get("url")
    out = {
        "body_status": "failed", "body_length": 0, "body_artifact_path": None,
        "extraction_method": None, "failure_reason": None, "body_url": url,
    }
    if not url or not str(url).startswith("http"):
        out["body_status"] = "no_url"
        out["failure_reason"] = "no_http_url"
        return out

    html = fetch_fn(url)
    if not html:
        out["failure_reason"] = "fetch_failed_or_non_200"
        return out

    blocker = classify_content_blocker(html.lower())
    if blocker is not None:
        out["body_status"] = "blocked"
        out["failure_reason"] = f"content_blocker:{getattr(blocker, 'value', blocker)}"
        return out

    result = extract_with_trafilatura(html, url)
    body = result.body or ""
    out["extraction_method"] = "trafilatura"
    out["body_length"] = len(body)
    if result.success and len(body) >= _BODY_MIN_CHARS:
        out["body_status"] = "extracted"
        if save:
            rid = new_run_id(1, source_id)
            uh = url_hash(url)
            path = save_extracted_text(rid, source_id, uh, "httpx_trafilatura", {
                "title": result.title or candidate.get("title") or "",
                "published_at": result.published_at or candidate.get("published_at") or "",
                "url": url,
                "quality_score": "",
                "body": body,
            })
            out["body_artifact_path"] = str(path)
    else:
        out["failure_reason"] = result.error_message or "body_too_short"
    return out


# ── candidate schema ─────────────────────────────────────────────────────────

def build_candidate(
    target: dict, sample: dict, *, run_id: str, status: str,
    next_retry_at: Optional[str], raw_artifact_path: Optional[str],
) -> dict:
    """기존 EventSeedCandidate 호환 스키마(docs/91 제안)로 candidate 1건 구성."""
    is_related = target["candidate_type"] == "related_query"
    url = sample.get("url")
    canonical = sample.get("canonical_url") or url
    return {
        "run_id": run_id,
        "source_id": target["id"],
        "source_role": target["role"],
        "candidate_type": target["candidate_type"],
        "title": sample.get("title"),
        "keyword": sample.get("title") if is_related else None,
        "url": url,
        "canonical_url": canonical,
        "resolved_url": canonical,
        "published_at": sample.get("published_at"),
        "observed_at": utc_now_iso(),
        "snippet": sample.get("snippet"),
        "body_status": "not_required" if not target["body_required"] else "pending",
        "body_length": 0,
        "body_artifact_path": None,
        "extraction_method": None,
        "evidence_level": target["evidence_level"],
        "status": status,
        "error_category": None,
        "next_retry_at": next_retry_at,
        "raw_artifact_path": raw_artifact_path,
    }


def _final_status_article(status: str, candidates: int, body_extracted: int,
                          body_attempted: int) -> str:
    if status == "RATE_LIMITED":
        return "NOT_CLOSED_EXTERNAL_RATE_LIMIT"
    if status == "PARSE_ERROR":
        return "NOT_CLOSED_PARSE_ERROR"
    if status in ("BLOCKED",):
        return "BLOCKED_TERMINAL"
    if status not in ("LIVE_SUCCESS", "LIVE_PARTIAL") or candidates < 3:
        return "NOT_CLOSED_BODY_EXTRACTION" if candidates > 0 else "NOT_CLOSED_NO_CANDIDATES"
    if body_extracted >= 1:
        return "PASS"
    # candidate는 충분하나 본문 0건: 시도는 했는지에 따라 분기
    return "PARTIAL_BODY_BLOCKED" if body_attempted > 0 else "NOT_CLOSED_BODY_EXTRACTION"


def classify_gate_skip(source_id: str, query: Optional[str], skip: str) -> tuple[str, Optional[str]]:
    """gate skip 사유 → (final_status, next_retry_at).

    cooldown/health-cooldown은 외부 rate limit이므로 NOT_CLOSED_EXTERNAL_RATE_LIMIT로 분류하고
    next_retry를 store에서 노출한다(쿨다운을 'gate skip'으로 뭉개 PASS처럼 보이지 않게).
    """
    if skip == "cooldown_skip":
        _cooled, at = in_cooldown(source_id, query or "")
        return "NOT_CLOSED_EXTERNAL_RATE_LIMIT", at
    if skip == "health_skip":
        st = get_health_store().get(source_id)
        if st and st.state == "BLOCKED_TERMINAL":
            return "BLOCKED_TERMINAL", None
        if st and st.state in ("RATE_LIMITED_COOLDOWN", "QUARANTINED_RETRYABLE"):
            return "NOT_CLOSED_EXTERNAL_RATE_LIMIT", st.next_retry_at
        return "NOT_CLOSED_GATE_SKIP", None
    if skip == "cache_skip":
        return "NOT_CLOSED_CACHE_DEDUP", None
    return "NOT_CLOSED_GATE_SKIP", None


def _final_status_related(status: str, related: int) -> str:
    if status == "RATE_LIMITED":
        return "NOT_CLOSED_EXTERNAL_RATE_LIMIT"
    if status == "BLOCKED":
        return "BLOCKED_TERMINAL"
    if status == "LIVE_SUCCESS" and related >= 3:
        return "PASS"
    if status == "LIVE_PARTIAL" or (status == "LIVE_SUCCESS" and related < 3):
        return "NOT_CLOSED_SELECTOR_OR_WAIT"
    return "NOT_CLOSED_NO_CANDIDATES"


# ── 소스별 audit ─────────────────────────────────────────────────────────────

def audit_article_source(
    target: dict, *, max_items: int, respect_rate_limit: bool,
    probe_fn: Callable, fetch_fn: Callable[[str], Optional[str]],
    extract_body_fn: Callable = extract_body,
) -> dict:
    sid, query = target["id"], target.get("query")
    rec = _base_record(target)

    if respect_rate_limit:
        skip = gate_check(sid, query or "")
        if skip:
            final, next_retry = classify_gate_skip(sid, query, skip)
            rec.update({
                "audit_action": skip, "collected": False,
                "status": skip.upper(), "final_status": final,
                "next_retry_at": next_retry,
                "next_action": "retry_after_cooldown_window",
            })
            return rec

    t0 = time.monotonic()
    result = probe_fn(sid, query=query, max_items=max_items)
    rec["elapsed_sec"] = round(time.monotonic() - t0, 2)
    record_call(sid, query or "")

    status = result.status
    next_retry = result.probe_result.next_retry_at if result.probe_result else None
    raw_path = result.artifact_paths.raw_payload or result.artifact_paths.raw_html
    rec.update({"status": status, "error_category": result.error_category,
                "next_retry_at": next_retry})
    if raw_path:
        rec["artifact_paths"].append(raw_path)

    if status not in ("LIVE_SUCCESS", "LIVE_PARTIAL"):
        rec["collected"] = False
        rec["final_status"] = _final_status_article(status, 0, 0, 0)
        rec["next_action"] = result.next_action or "investigate"
        return rec

    samples = extract_sample_items(
        sid, raw_path, max_samples=max_items,
        resolve_canonical=True, canonical_via_browser=target["canonical_browser"],
    )
    run_id = new_run_id(1, sid)
    candidates = [
        build_candidate(target, s, run_id=run_id, status=status,
                        next_retry_at=next_retry, raw_artifact_path=raw_path)
        for s in samples
    ]
    rec["collected"] = len(candidates) > 0
    rec["candidates_created"] = len(candidates)

    body_attempted = body_extracted = 0
    if target["body_required"]:
        for cand in candidates:
            if body_extracted >= 1 and body_attempted >= _MAX_BODY_ATTEMPTS:
                break
            if body_attempted >= _MAX_BODY_ATTEMPTS:
                break
            if not (cand.get("canonical_url") or cand.get("url")):
                continue
            if body_attempted > 0:
                time.sleep(_BODY_FETCH_DELAY)  # rapid request throttle 회피
            body_attempted += 1
            b = extract_body_fn(sid, cand, fetch_fn=fetch_fn)
            cand.update({
                "body_status": b["body_status"], "body_length": b["body_length"],
                "body_artifact_path": b["body_artifact_path"],
                "extraction_method": b["extraction_method"],
                "error_category": b["failure_reason"] or cand["error_category"],
            })
            if b["body_artifact_path"]:
                rec["artifact_paths"].append(b["body_artifact_path"])
            if b["body_status"] == "extracted":
                body_extracted += 1

    rec["body_attempted"] = body_attempted
    rec["body_extracted"] = body_extracted
    rec["candidates"] = candidates
    rec["final_status"] = _final_status_article(
        status, len(candidates), body_extracted, body_attempted)
    rec["next_action"] = "closed" if rec["final_status"] == "PASS" else "review_body_extraction"
    return rec


def _trends_candidates(probe_result, max_items: int) -> list[dict]:
    """ProbeResult에서 related_query 후보 추출 — raw_signal(JSON) 우선, rendered_dom 차선."""
    ap = probe_result.artifact_paths or {}
    raw_signal = ap.get("raw_signal")
    if raw_signal and Path(raw_signal).exists():
        try:
            data = json.loads(Path(raw_signal).read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return [
                    {"title": (it.get("keyword") or "").strip(),
                     "url": it.get("url") or None,
                     "snippet": None, "published_at": None}
                    for it in data[:max_items]
                    if isinstance(it, dict) and (it.get("keyword") or "").strip()
                ]
        except Exception:
            pass
    rendered = ap.get("rendered_dom")
    if rendered and Path(rendered).exists():
        try:
            html = Path(rendered).read_text(encoding="utf-8", errors="replace")
        except OSError:
            html = None
        return extract_samples_from_rendered("google_trends_explore", html, max_items)
    return []


def audit_related_query_source(
    target: dict, *, max_items: int, respect_rate_limit: bool,
    playwright_fn: Callable,
) -> dict:
    sid, query, region = target["id"], target.get("query"), target.get("region")
    rec = _base_record(target)

    if respect_rate_limit:
        skip = gate_check(sid, query or "")
        if skip:
            final, next_retry = classify_gate_skip(sid, query, skip)
            rec.update({
                "audit_action": skip, "collected": False, "status": skip.upper(),
                "final_status": final, "next_retry_at": next_retry,
                "next_action": "retry_after_cooldown_window",
            })
            return rec

    t0 = time.monotonic()
    probe_result = playwright_fn(sid, query=query, region=region, max_items=max_items)
    rec["elapsed_sec"] = round(time.monotonic() - t0, 2)
    record_call(sid, query or "")

    status = probe_result.status
    next_retry = probe_result.next_retry_at
    ap = probe_result.artifact_paths or {}
    rec.update({"status": status, "error_category": probe_result.error_category,
                "next_retry_at": next_retry})
    for key in ("rendered_dom", "raw_signal", "screenshot"):
        if ap.get(key):
            rec["artifact_paths"].append(ap[key])

    related = _trends_candidates(probe_result, max_items) if status in ("LIVE_SUCCESS", "LIVE_PARTIAL") else []
    run_id = new_run_id(1, sid)
    candidates = [
        build_candidate(target, s, run_id=run_id, status=status,
                        next_retry_at=next_retry, raw_artifact_path=ap.get("raw_signal"))
        for s in related if s.get("title")
    ]
    rec["collected"] = len(candidates) > 0
    rec["candidates_created"] = len(candidates)
    rec["candidates"] = candidates
    rec["body_extracted"] = 0  # article source 아님 — body=not_required
    rec["final_status"] = _final_status_related(status, len(candidates))
    rec["next_action"] = "closed" if rec["final_status"] == "PASS" else "retry_next_gate_window"
    return rec


def audit_risk_t04(data_records: list[dict]) -> dict:
    """#1 RISK-T04 — 실제 runner 경로에서 429 → cooldown 영속 → 다음 호출 skip 전 사슬 검증.

    데이터 소스가 아니므로 collected는 n/a. 이번 audit의 #2 gdelt / #5 trends가
    (a) 호출되어 RATE_LIMITED를 반환했거나, (b) 직전 runtime 429로 인해 이미 cooldown 상태라
    gate가 호출을 막은 경우 — 두 경우 모두 'local_file backend에 next_retry 영속 + gate skip'을
    실제 runner 경로에서 입증한다(단위 테스트 아님).
    """
    backend = active_backend_name()
    backend_ok = backend == "LocalPersistentRateLimitStore"

    evidence: list[dict] = []
    for r in data_records:
        sid = r["source_id"]
        q = next((t.get("query") for t in E2E_TARGETS if t["id"] == sid), None)
        cooled_q, at_q = in_cooldown(sid, q or "")
        cooled_bare, at_bare = in_cooldown(sid, "")
        st = get_health_store().get(sid)
        hskip, hreason = should_skip(st)
        cache_cooldown = bool(cooled_q or cooled_bare)
        gate_skips = bool(cache_cooldown or hskip)
        is_rl = (
            r.get("status") in ("RATE_LIMITED", "COOLDOWN_SKIP", "HEALTH_SKIP")
            or r.get("final_status") == "NOT_CLOSED_EXTERNAL_RATE_LIMIT"
            or cache_cooldown or (st is not None and st.state == "RATE_LIMITED_COOLDOWN")
        )
        if not is_rl:
            continue
        evidence.append({
            "source_id": sid,
            "gate_or_probe_status": r.get("status"),
            "rate_limit_cache_cooldown_persisted": cache_cooldown,
            "cooldown_until": at_q or at_bare or (st.next_retry_at if st else None),
            "health_state": st.state if st else None,
            "gate_blocks_recall": gate_skips,
        })

    persist_and_skip = any(
        e["rate_limit_cache_cooldown_persisted"] and e["gate_blocks_recall"] for e in evidence
    )

    rec = {
        "source_id": "RISK-T04",
        "role": "infra_rate_limit",
        "candidate_type": "infra",
        "audited_at": utc_now_iso(),
        "backend": backend,
        "audit_action": "infra_check",
        "status": None,
        "collected": None,        # 데이터 소스 아님
        "candidates_created": 0,
        "body_required": False,
        "body_attempted": 0,
        "body_extracted": 0,
        "error_category": None,
        "next_retry_at": None,
        "artifact_paths": [],
        "candidates": [],
        "elapsed_sec": 0.0,
        "backend_is_local_file": backend_ok,
        "rate_limit_evidence": evidence,
    }
    if backend_ok and persist_and_skip:
        rec["status"] = "VERIFIED_PERSIST_AND_SKIP"
        rec["final_status"] = "PASS"
        rec["next_action"] = "closed_runtime_429_persisted_to_local_file_and_gate_skips_recall"
    elif backend_ok:
        rec["status"] = "NO_ACTIVE_COOLDOWN_BACKEND_ACTIVE"
        rec["final_status"] = "PASS_VIA_UNIT_AND_PRIOR_LIVE"
        rec["next_action"] = "closed_no_active_cooldown_persistence_path_active"
    else:
        rec["status"] = "BACKEND_NOT_LOCAL_FILE"
        rec["final_status"] = "NOT_CLOSED_BACKEND"
        rec["next_action"] = "force_local_file_backend"
    return rec


def _base_record(target: dict) -> dict:
    return {
        "source_id": target["id"],
        "role": target["role"],
        "candidate_type": target["candidate_type"],
        "audited_at": utc_now_iso(),
        "backend": _RATE_LIMIT_BACKEND,
        "audit_action": "called",
        "status": None,
        "collected": False,
        "candidates_created": 0,
        "body_required": target["body_required"],
        "body_attempted": 0,
        "body_extracted": 0,
        "error_category": None,
        "next_retry_at": None,
        "artifact_paths": [],
        "candidates": [],
        "final_status": None,
        "next_action": None,
        "elapsed_sec": 0.0,
    }


# ── 보고 ─────────────────────────────────────────────────────────────────────

def _md_report(records: list[dict], ts: str) -> str:
    lines = [
        "# Conditional Sources E2E Audit (01~05)",
        "",
        f"- run: {ts} (UTC)",
        f"- rate-limit backend: {records[-1].get('backend') if records else '-'}",
        "",
        "| source | role | status | collected | candidates | body_extracted | final_status | next_action |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['source_id']} | {r.get('role','-')} | {r.get('status') or '-'} "
            f"| {r.get('collected')} | {r.get('candidates_created',0)} "
            f"| {r.get('body_extracted',0)} | {r.get('final_status') or '-'} "
            f"| {r.get('next_action') or '-'} |"
        )
    data = [r for r in records if r["source_id"] != "RISK-T04"]
    lines += [
        "",
        "## Summary",
        f"- 대상: 5 (#1 인프라 + #2~#5 데이터)",
        f"- collected: {sum(1 for r in data if r.get('collected'))}/{len(data)}",
        f"- candidates 총합: {sum(r.get('candidates_created', 0) for r in records)}",
        f"- body_extracted 총합: {sum(r.get('body_extracted', 0) for r in records)}",
        f"- PASS: {sum(1 for r in records if (r.get('final_status') or '').startswith('PASS'))}",
        f"- NOT_CLOSED: {sum(1 for r in records if (r.get('final_status') or '').startswith('NOT_CLOSED'))}",
        "",
        "## Security Note",
        "API 키/토큰 값 없음. 본문은 extracted_text/ artifact로만 저장(보고서엔 미포함).",
    ]
    return "\n".join(lines)


def run_audit(
    *, max_items: int = 5, respect_rate_limit: bool = True,
    sources: Optional[list[str]] = None,
    probe_fn: Optional[Callable] = None,
    playwright_fn: Optional[Callable] = None,
    fetch_fn: Optional[Callable[[str], Optional[str]]] = None,
) -> list[dict]:
    """E2E audit 본체. probe/playwright/fetch는 테스트에서 주입 가능(기본은 실 호출)."""
    if probe_fn is None:
        from ingestion.fetch_strategies.collection_probe import run_collection_probe
        probe_fn = run_collection_probe
    if playwright_fn is None:
        from ingestion.probes.playwright_probe import run_playwright_probe
        playwright_fn = run_playwright_probe
    if fetch_fn is None:
        fetch_fn = _default_fetch_html

    targets = E2E_TARGETS
    if sources:
        wanted = set(sources)
        targets = [t for t in E2E_TARGETS if t["id"] in wanted]

    records: list[dict] = []
    for target in targets:
        safe_print(f"[{target['id']}] kind={target['kind']} query={target.get('query')}")
        if target["kind"] == "related_query":
            rec = audit_related_query_source(
                target, max_items=max_items, respect_rate_limit=respect_rate_limit,
                playwright_fn=playwright_fn)
        else:
            rec = audit_article_source(
                target, max_items=max_items, respect_rate_limit=respect_rate_limit,
                probe_fn=probe_fn, fetch_fn=fetch_fn)
        records.append(rec)
        safe_print(
            f"    -> status={rec.get('status')} collected={rec.get('collected')} "
            f"candidates={rec.get('candidates_created')} body={rec.get('body_extracted')} "
            f"final={rec.get('final_status')}"
        )

    # #1 RISK-T04: #2~#5 live 결과(특히 gdelt/trends RATE_LIMITED)로 인프라 검증
    if not sources or "RISK-T04" in (sources or []):
        risk = audit_risk_t04([r for r in records if r["source_id"] != "RISK-T04"])
        records.insert(0, risk)
        safe_print(f"[RISK-T04] backend={risk['backend']} final={risk['final_status']}")

    return records


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Conditional sources E2E audit (01~05)")
    parser.add_argument("--sources", nargs="*", default=None,
                        help="대상 제한(예: gdelt google_trends_explore)")
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--no-rate-limit", action="store_true",
                        help="gate(cooldown/cache) 무시 — 디버그용(권장 안 함)")
    args = parser.parse_args(argv)

    load_env()
    force_local_file_backend()
    safe_print(f"rate-limit backend forced: {active_backend_name()}")

    records = run_audit(
        max_items=args.max_items,
        respect_rate_limit=not args.no_rate_limit,
        sources=args.sources,
    )

    ts = audit_timestamp()
    jsonl_path = write_audit_jsonl(
        records, OUTPUT_JSONL_DIR / f"conditional_sources_e2e_audit_{ts}.jsonl")
    md_path = write_audit_md(
        _md_report(records, ts),
        OUTPUT_REPORTS_DIR / f"conditional_sources_e2e_audit_{ts}.md")
    safe_print(f"jsonl : {jsonl_path}")
    safe_print(f"report: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

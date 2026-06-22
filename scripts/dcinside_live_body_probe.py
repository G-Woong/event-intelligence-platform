"""dcinside 공개 수집 범위 재검증 probe (list / detail / body).

목적(사용자 3단계): dcinside를 무조건 list-preview로 고정하지 말고, 공개 접근 가능한 범위에서
실제 수집 가능성(목록 최신글 / 상세 URL / 공개 본문 텍스트)을 재검증한다. 우회성 접근 금지.

no-bypass(절대): robots disallow 갤러리 비호출 · Cloudflare/captcha/login 마커 보이면 중단 ·
성인/anti-bot/CAPTCHA 우회 금지 · 댓글 대량/이미지/PII(닉네임) 미수집 · 과도 반복 금지.

본문 정책: 공개 본문은 char_len + preview(≤200)만 산출물에 남긴다(전문 미저장).

산출물:
  - outputs/dcinside_live_body_probe.jsonl
  - reports/dcinside_live_body_probe.md
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from ingestion.core.error_taxonomy import classify_content_blocker
from ingestion.orchestration.dcinside_strategy import (
    collect_dcinside,
    detail_urls_from_records,
    list_url_for,
)
from ingestion.orchestration.source_policy_probe import probe_source_policy
from ingestion.tools.trafilatura_extractor import extract_with_trafilatura

import re

_UA = "Mozilla/5.0 (compatible; eventintel-collector/1.0)"
_GALLERIES = [("stockus", True)]   # robots(User-agent:*) 허용 확인된 갤러리(주식 미국장)
_BODY_MIN_CHARS = 120

# BF-2(adversarial): static selector가 게시글 본문 컨테이너 안의 UI 크롬(추천/스크랩/신고 버튼바,
# 첨부파일명, 장 시간 안내)까지 긁어 char_len만 채우는 false-positive를 막는다. 아래 토큰/파일명을
# 제거한 뒤 '의미있는 본문' 길이로 재측정해 정직하게 분류한다(둔갑 방지).
_DC_BOILERPLATE = (
    "추천검색", "추천", "비추천", "개념글", "개념", "실베추", "공유", "스크랩", "신고",
    "원본", "첨부파일", "본문 이미지", "이미지", "다운로드", "댓글", "갤러리",
    "프리장", "데이터장", "본장", "애프터장", "마감", "휴장", "서머타임",
    "들어가는 말", "맺음말", "목록", "자문자답",
)
# 일반 이미지 파일명(001.png / 한글명.jpg / UUID.jpg 등) — 첨부 캡션이지 산문 본문이 아님.
_FILENAME_RE = re.compile(r"\S*\.(?:jpg|jpeg|png|gif|webp)\b", re.I)
# 숫자/카운터 잔재("추천 251,521" → "251,521", 목차 번호 "1." "2.") — 산문 본문 신호 아님.
_NUM_NOISE_RE = re.compile(r"\b[\d][\d,.\s]*\b")
# 링크 나열(고정 공지/목차성 게시글의 반복 URL) — 산문 본문 신호 아님.
_URL_RE = re.compile(r"https?://\S+")


def _meaningful_body(txt: str) -> str:
    """UI 보일러플레이트/첨부파일명/숫자/URL 노이즈를 제거한 '의미있는 산문 본문'만 남긴다.

    BF-2(adversarial 재검증 2차): UUID.jpg뿐 아니라 일반 이미지 파일명·목차 번호·추천 카운터 숫자·
    반복 링크(공지/목차성 게시글)까지 제거해, UI/캡션/링크나열이 meaningful 본문으로 새어드는
    false-positive를 막는다(보수적 = 과소측정 = 둔갑 방지).
    """
    txt = _URL_RE.sub(" ", txt)
    txt = _FILENAME_RE.sub(" ", txt)
    for tok in _DC_BOILERPLATE:
        txt = txt.replace(tok, " ")
    txt = _NUM_NOISE_RE.sub(" ", txt)
    return re.sub(r"\s+", " ", txt).strip()
_OUT_JSONL = Path("outputs/dcinside_live_body_probe.jsonl")
_OUT_MD = Path("reports/dcinside_live_body_probe.md")


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _robots_get(url: str) -> Optional[str]:
    try:
        r = httpx.get(url, timeout=15.0, follow_redirects=True, headers={"User-Agent": _UA})
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


def _page_get(url: str):
    try:
        r = httpx.get(url, timeout=20.0, follow_redirects=True, headers={"User-Agent": _UA})
        return r.status_code, r.text
    except Exception:
        return None, None


def _probe_detail_body(url: str) -> dict:
    """detail URL 본문 추출 시도(static selectors + trafilatura, 우회 0)."""
    out = {"detail_url": url, "detail_status": None, "body_status": None,
           "body_char_len": 0, "meaningful_char_len": 0, "body_preview": "", "failure_reason": None}
    try:
        r = httpx.get(url, timeout=20.0, follow_redirects=True, headers={"User-Agent": _UA})
    except httpx.TimeoutException:
        out["body_status"] = "DETAIL_TIMEOUT"; out["failure_reason"] = "timeout"; return out
    except Exception as exc:
        out["body_status"] = "DETAIL_FETCH_ERROR"; out["failure_reason"] = f"fetch_error:{type(exc).__name__}"; return out
    out["detail_status"] = r.status_code
    if r.status_code == 403:
        out["body_status"] = "DETAIL_HTTP_403"; out["failure_reason"] = "http_403"; return out
    if r.status_code != 200 or not r.text:
        out["body_status"] = "DETAIL_HTTP_OTHER"; out["failure_reason"] = f"http_{r.status_code}"; return out
    html = r.text
    blocker = classify_content_blocker(html.lower())
    if blocker is not None:
        out["body_status"] = "LIST_OK_DETAIL_BLOCKED"
        out["failure_reason"] = f"content_blocker:{getattr(blocker, 'value', blocker)}"
        return out
    # static selectors
    best_chars, best_txt = 0, ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for sel in (".write_div", ".writing_view_box", ".gallview_contents", "div[itemprop=articleBody]"):
            el = soup.select_one(sel)
            if el is not None:
                txt = el.get_text(" ", strip=True)
                if len(txt) > best_chars:
                    best_chars, best_txt = len(txt), txt
    except Exception:
        pass
    # trafilatura(보강)
    try:
        tr = extract_with_trafilatura(html, url)
        if tr.body and len(tr.body) > best_chars:
            best_chars, best_txt = len(tr.body), tr.body
    except Exception:
        pass
    # BF-2: raw char_len이 아니라 '의미있는 본문' 길이로 분류(UI 크롬 false-positive 제거).
    meaningful = _meaningful_body(best_txt)
    out["body_char_len"] = best_chars
    out["meaningful_char_len"] = len(meaningful)
    out["body_preview"] = meaningful[:200]
    if best_chars == 0:
        out["body_status"] = "DETAIL_PARSE_EMPTY"; out["failure_reason"] = "no_body_text_static_render"; return out
    if len(meaningful) < _BODY_MIN_CHARS:
        # static 컨테이너에 텍스트는 있으나 의미있는 본문은 UI 크롬뿐 → preview-only/detail-probe만 지원
        out["body_status"] = "BODY_BOILERPLATE_ONLY" if best_chars >= _BODY_MIN_CHARS else "BODY_TOO_SHORT"
        out["failure_reason"] = f"meaningful_body_too_short:{len(meaningful)}<{_BODY_MIN_CHARS}(raw={best_chars})"
        return out
    out["body_status"] = "extracted"
    return out


def _condition_class(list_ok: bool, detail_reachable: bool, body_ok: bool) -> str:
    if body_ok:
        return "LIMITED_PUBLIC_BODY"
    if detail_reachable:
        return "PUBLIC_DETAIL_PROBE_SUPPORTED"
    if list_ok:
        return "PREVIEW_ONLY"
    return "BLOCKED_OR_UNAVAILABLE"


def run_probe(*, max_detail: int = 3, write_outputs: bool = True) -> dict:
    rows: list[dict] = []
    overall = {"list_records": 0, "detail_attempted": 0, "body_extracted": 0,
               "galleries": [], "condition_class": "PREVIEW_ONLY"}
    for gallery, minor in _GALLERIES:
        url = list_url_for(gallery, minor=minor)
        policy = probe_source_policy(source_id="dcinside", tested_url=url,
                                     robots_get=_robots_get, page_get=_page_get)
        robots_allowed = bool(policy.robots_allowed)
        res = collect_dcinside(gallery_id=gallery, minor=minor, robots_allowed=robots_allowed)
        list_records = list(res.records) if res.success else []
        overall["list_records"] += len(list_records)

        grow = {"gallery": gallery, "robots_allowed": robots_allowed,
                "ai_crawler_disallowed": policy.ai_crawler_disallowed,
                "policy_conclusion": policy.conclusion, "list_verdict": res.verdict,
                "list_count": len(list_records),
                "sample_titles": [(r.get("title_or_label") or "")[:60] for r in list_records[:5]],
                "sample_times": [r.get("published_at_or_observed_at") for r in list_records[:5]],
                "detail_probes": []}

        detail_urls = detail_urls_from_records(list_records)[:max_detail]
        detail_reachable = False
        body_ok = False
        for du in detail_urls:
            overall["detail_attempted"] += 1
            if grow["detail_probes"]:
                time.sleep(1.5)  # 과도 반복 회피
            d = _probe_detail_body(du)
            grow["detail_probes"].append(d)
            if d["detail_status"] == 200 and d["body_status"] not in ("LIST_OK_DETAIL_BLOCKED",):
                detail_reachable = True
            if d["body_status"] == "extracted":
                body_ok = True
                overall["body_extracted"] += 1
        grow["condition_class"] = _condition_class(len(list_records) >= 5, detail_reachable, body_ok)
        overall["galleries"].append(grow)
        rows.append(grow)

    # 종합 condition_class(가장 높은 등급 채택)
    classes = [g["condition_class"] for g in overall["galleries"]]
    for tier in ("LIMITED_PUBLIC_BODY", "PUBLIC_DETAIL_PROBE_SUPPORTED", "PREVIEW_ONLY", "BLOCKED_OR_UNAVAILABLE"):
        if tier in classes:
            overall["condition_class"] = tier
            break

    if write_outputs:
        _OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with open(_OUT_JSONL, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        _OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        _OUT_MD.write_text(_md(overall), encoding="utf-8")
    return overall


def _md(overall: dict) -> str:
    lines = [
        "# dcinside Live Body Probe (list / detail / body)",
        "",
        f"- run: {_iso_now()} (UTC)",
        f"- overall condition_class: **{overall['condition_class']}**",
        f"- list_records: {overall['list_records']} · detail_attempted: {overall['detail_attempted']} "
        f"· body_extracted: {overall['body_extracted']}",
        "- no-bypass: robots-allowed gallery only; Cloudflare/captcha/login → stop; no PII/comments/images",
        "- body policy: char_len + preview(≤200) only",
        "",
    ]
    for g in overall["galleries"]:
        lines += [
            f"## gallery: {g['gallery']}",
            f"- robots_allowed: {g['robots_allowed']} · ai_crawler_disallowed: {g['ai_crawler_disallowed']} "
            f"· policy: {g['policy_conclusion']}",
            f"- list_verdict: {g['list_verdict']} · list_count: {g['list_count']} · condition_class: **{g['condition_class']}**",
            f"- sample_titles: {g['sample_titles']}",
            f"- sample_times: {g['sample_times']}",
            "",
            "| detail_url | status | body_status | raw_chars | meaningful_chars | failure |",
            "|---|---|---|---|---|---|",
        ]
        for d in g["detail_probes"]:
            lines.append(
                f"| {(d['detail_url'] or '-')[:50]} | {d['detail_status']} | {d['body_status']} "
                f"| {d['body_char_len']} | {d.get('meaningful_char_len', 0)} "
                f"| {(d.get('failure_reason') or '-')[:36]} |")
        lines.append("")
    lines += [
        "## Failure taxonomy",
        "LIST_OK_DETAIL_BLOCKED / DETAIL_HTTP_403 / DETAIL_TIMEOUT / DETAIL_PARSE_EMPTY / "
        "BODY_TOO_SHORT / BODY_BOILERPLATE_ONLY / POLICY_LIMITED / STRUCTURE_CHANGED",
        "",
        "> BF-2(adversarial 반영): body_status=extracted는 **UI 크롬(추천/스크랩/신고 버튼·첨부파일명·장 "
        "시간 안내) 제거 후 의미있는 본문 길이 ≥120자**일 때만 부여한다. raw_chars만 넘고 meaningful이 "
        "부족하면 BODY_BOILERPLATE_ONLY(=본문 추출 실패로 분류, 둔갑 금지).",
        "",
        "## condition_class 세분",
        "- PREVIEW_ONLY: list 메타만(상세 본문 정적 부재/차단)",
        "- PUBLIC_DETAIL_PROBE_SUPPORTED: 상세 페이지 접근 가능하나 정적 본문 미추출(JS/이미지 렌더)",
        "- LIMITED_PUBLIC_BODY: 공개 본문 소량 추출 성공(대량 승격은 정책/ToS 검토 후 별도)",
        "",
        "## 정책 보정 note",
        "공개 본문 소량 검증 결과와 ToS/저작권 리스크는 분리 기록. full body 대량 수집으로 즉시 승격 금지.",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="dcinside live list/detail/body probe")
    ap.add_argument("--max-detail", type=int, default=3)
    args = ap.parse_args(argv)
    print("DCINSIDE_LIVE_BODY_PROBE: start (no-bypass)")
    overall = run_probe(max_detail=args.max_detail)
    print(f"- condition_class: {overall['condition_class']}")
    print(f"- list_records={overall['list_records']} detail_attempted={overall['detail_attempted']} "
          f"body_extracted={overall['body_extracted']}")
    print(f"- jsonl: {_OUT_JSONL}")
    print(f"- report: {_OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

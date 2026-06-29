"""ADR#86 — official×news role-bridge (PURE·deterministic·reviewer-routing only·merge 0·LLM 0·embedding 0·DB 0).

ADR#86 은 Federal Register 를 window-honoring **official** source 로 배선했다. 그러나 official 문서(rule/notice)와
news 기사는 **role 이 다르다** — 둘을 같은 "article pair" 처럼 title-Jaccard 로 묶어 같은 사건으로 단정하면 안 된다
(official 규제문서 title 과 journalistic news title 은 token 이 거의 안 겹쳐 그 자체로 부적합하기도 하다). 이 모듈은
그 둘을 **role 을 보존한 채** 잇는 정책이다 — official record 와 news record 가 같은 regulatory/event subject 를
가리킬 *가능성* 이 있으면(date 근접 + entity/action token 공유) **reviewer-routing candidate** 로만 분류한다.

절대 불변(§9 role-bridge 계약):
  - **bridge_candidate = reviewer-routing only**: same_event 단정 0·merge 0·KG edge 0·public IU 0. 사람 reviewer 가
    official 증거 vs news 보도를 직접 판정할 worklist 후보일 뿐, 코드가 같은 사건이라고 말하지 않는다.
  - **official 단독 production candidate 금지**: official record 하나만으로 cross-source production candidate 가 될 수
    없다. bridge 는 official×news 두 role 이 함께 있을 때만 후보를 만든다.
  - **score 미노출**: 단일 composite bridge score 를 만들지 않는다(reviewer/public 편향 차단·§9 forbidden). 라우팅
    결정은 feature(date_proximity_days·shared_token_count) 위의 **결정적 boolean gate** 이며, 노출은 feature 만(점수 0).
  - **raw body 0**: title 전문/abstract/본문 미저장 — 정규화 **공유 토큰**(entity/action proxy·band_diagnostic 과 동일
    표면)·canonical host·published date 만. snapshot 은 aggregate count 만(이 모듈의 candidate 리스트는 snapshot 에 안 감).
  - **role guard**: official(official_record)×news(article/news)만. community/market/catalog/search anchor 금지.
  - **LLM/embedding 0**: 모든 판정은 결정적(token 집합·날짜 차)·실호출 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Optional

from backend.app.services.event_ingest_pipeline import _RECORD_TYPE_TO_SOURCE_TYPE
from ingestion.orchestration.cross_source_dedup import _title_tokens

OPERATION_NAME = "official_news_role_bridge"
BRIDGE_TYPE = "official_news"

# role 어휘(event_ingest_pipeline 단일 출처와 정합). official=공식 증거(authority 5)·news/article=보도 증거.
_OFFICIAL_ROLES = frozenset({"official"})
_NEWS_ROLES = frozenset({"news", "article"})

# 라우팅 gate 기본값(merge 임계가 아니라 "reviewer 가 볼 만한가" 의 보수적 floor·§9).
_DEFAULT_DATE_TOLERANCE_DAYS = 1     # official 발행일과 news 보도일의 근접 허용(공식 발표 ±1일에 보도 수렴).
_DEFAULT_MIN_SHARED_TOKENS = 2       # entity/action token 최소 공유(같은 subject 가능성·1개는 우연 과다).


def _role(rec: dict) -> str:
    return _RECORD_TYPE_TO_SOURCE_TYPE.get(rec.get("record_type"), "unknown")


def _host(url: Optional[str]) -> Optional[str]:
    """canonical_url → host(netloc)만(경로/쿼리 미노출·본문 0). 파싱 실패 None."""
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc or None
    except Exception:
        return None


def _iso(d: Optional[str]) -> Optional[datetime]:
    if not d or len(d) < 10:
        return None
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d")
    except Exception:
        return None


def _in_window(date_str: Optional[str], window: Optional[tuple[str, str]]) -> Optional[bool]:
    """record published date 가 [start, end] 안인가. window 미제공 시 None(미지·in-window 단정 금지)."""
    if not window:
        return None
    d = _iso(date_str)
    s, e = _iso(window[0]), _iso(window[1])
    if d is None or s is None or e is None:
        return False
    return s <= d <= e


def build_official_news_bridge(
    official_records: Optional[list[dict]], news_records: Optional[list[dict]], *,
    date_window: Optional[tuple[str, str]] = None,
    date_tolerance_days: int = _DEFAULT_DATE_TOLERANCE_DAYS,
    min_shared_tokens: int = _DEFAULT_MIN_SHARED_TOKENS,
) -> dict:
    """official record × news record → reviewer-routing bridge candidates(PURE·merge 0·LLM 0·score 0·body 0).

    각 (official, news) 쌍에 대해 ① role 이 official×news 인지, ② 둘 다 canonical+published 보유, ③ date proximity
    ≤ tolerance, ④ title 정규화 공유 토큰(entity/action proxy) ≥ min_shared_tokens 이면 bridge_candidate=True. 이는
    **같은 사건 단정이 아니라** 사람 reviewer 에게 보낼 후보 표식이다. freeze_eligible 은 추가로 date_window 안에서
    양쪽 in-window 일 때만(§9 freeze 계약) — date_window 미제공 시 in-window 미지라 freeze_eligible=False(fail-closed).

    노출: feature(date_proximity_days·shared_token_count·shared_tokens·canonical host·in-window flag)만. 단일 score·
    predicted_status·rationale·raw title 전문 0. candidate 리스트는 reviewer worklist 잠재 입력일 뿐 snapshot 미포함."""
    officials = [r for r in (official_records or []) if _role(r) in _OFFICIAL_ROLES]
    news = [r for r in (news_records or []) if _role(r) in _NEWS_ROLES]

    candidates: list[dict] = []
    idx = 0
    for o in officials:
        o_role = _role(o)
        o_pub = o.get("published_at_or_observed_at")
        o_url = o.get("canonical_url")
        o_tokens = _title_tokens(o.get("title_or_label"))
        o_in = _in_window(o_pub, date_window)
        for n in news:
            n_role = _role(n)
            n_pub = n.get("published_at_or_observed_at")
            n_url = n.get("canonical_url")
            shared = sorted(o_tokens & _title_tokens(n.get("title_or_label")))
            both_canonical = bool(o_url) and bool(n_url)
            both_published = bool(o_pub) and bool(n_pub)
            od, nd = _iso(o_pub), _iso(n_pub)
            proximity = abs((od - nd).days) if (od is not None and nd is not None) else None
            n_in = _in_window(n_pub, date_window)
            date_close = proximity is not None and proximity <= max(0, date_tolerance_days)
            is_candidate = bool(
                both_canonical and both_published and date_close
                and len(shared) >= max(1, min_shared_tokens))
            # §9 freeze 계약: bridge_candidate ∧ official in-window ∧ news in-window(date-compatible) ∧ canonical 양측.
            freeze_eligible = bool(
                is_candidate and o_in is True and n_in is True and both_canonical)
            idx += 1
            candidates.append({
                "pair_id": f"oxn_{idx:04d}",
                "bridge_type": BRIDGE_TYPE,
                "source_id_official": o.get("source_id"),
                "source_id_news": n.get("source_id"),
                "source_role_official": o_role,
                "source_role_news": n_role,
                "date_official": o_pub,
                "date_news": n_pub,
                "date_proximity_days": proximity,
                "shared_token_count": len(shared),
                "shared_tokens": shared,            # 정규화 entity/action 교집합(제목 전문 아님·body 0).
                "canonical_host_official": _host(o_url),
                "canonical_host_news": _host(n_url),
                "official_in_window": o_in,
                "news_in_window": n_in,
                "both_canonical_present": both_canonical,
                "both_published_present": both_published,
                "bridge_candidate": is_candidate,
                "freeze_eligible": freeze_eligible,
                # 불변 — bridge 는 routing 표식이지 truth 가 아니다.
                "same_event_asserted": False,
                "reviewer_routing_only": True,
                "merge_allowed": False,
                "kg_edge_allowed": False,
                "public_iu_allowed": False,
            })

    bridge_candidates = [c for c in candidates if c["bridge_candidate"]]
    freeze_eligible = [c for c in bridge_candidates if c["freeze_eligible"]]
    blocked_reason, next_action = _bridge_blocked_reason(
        official_count=len(officials), news_count=len(news),
        bridge_count=len(bridge_candidates), freeze_count=len(freeze_eligible),
        date_window=date_window)

    return {
        "operation_name": OPERATION_NAME,
        "bridge_type": BRIDGE_TYPE,
        "official_record_count": len(officials),
        "news_record_count": len(news),
        "pair_count_evaluated": len(candidates),
        "bridge_candidate_count": len(bridge_candidates),
        "freeze_eligible_bridge_count": len(freeze_eligible),
        "date_window_applied": bool(date_window),
        "date_tolerance_days": max(0, date_tolerance_days),
        "min_shared_tokens": max(1, min_shared_tokens),
        # reviewer worklist 잠재 입력(feature 만·score/predicted_status/raw title 0). snapshot 엔 안 들어간다(§12 aggregate).
        "bridge_candidates": bridge_candidates,
        "blocked_reason": blocked_reason,
        "next_action": next_action,
        # ── 불변 경계(§9·§16) ──
        "official_alone_as_production_candidate": False,
        "same_event_asserted": False,
        "reviewer_routing_only": True,
        "merge_allowed": False,
        "kg_edge_allowed": False,
        "public_iu_allowed": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "db_write": False,
        "bridge_score_exposed": False,      # 단일 composite score 자체를 만들지 않음(feature 만).
        "raw_source_body_exposed": False,
    }


def _bridge_blocked_reason(
    *, official_count: int, news_count: int, bridge_count: int, freeze_count: int,
    date_window: Optional[tuple[str, str]],
) -> tuple[str, str]:
    """bridge 결과 → (blocked_reason, next_action). freeze 가능 후보가 있으면 blocked 아님(빈 reason)."""
    if official_count == 0 and news_count == 0:
        return ("no_official_or_news_records",
                "acquire both official (federal_register) and news (guardian/nyt) in-window records first")
    if official_count == 0:
        return ("no_official_records",
                "no Federal Register official records — broaden the FR query/window or pin a regulatory-class event")
    if news_count == 0:
        return ("no_news_records",
                "no news records to bridge against — run the news providers for the same window")
    if bridge_count == 0:
        return ("no_official_news_bridge_candidate",
                "official and news records exist but none share enough entity/action tokens within the date "
                "tolerance — reviewer-routing requires a plausible shared subject (not a same-event assertion)")
    if freeze_count == 0:
        return ("bridge_candidates_not_in_window",
                "official×news bridge candidates exist but none have BOTH records inside the pinned window — "
                "freeze requires in-window official AND in-window/date-compatible news (out-of-window cannot freeze)")
    return ("", "official×news bridge candidates are in-window — eligible for a reviewer-routing worklist freeze "
                "(reviewer worklist only · NOT same-event truth · production gold stays 0 until returned labels)")


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#86 official×news role-bridge (PURE·network 0·merge 0·LLM 0·score 0; official record × news "
                     "record → reviewer-routing candidate only·same_event 단정 0). 입력 records 는 JSON stdin."))
    parser.add_argument("--json", action="store_true", help="bridge 결과 JSON 출력(candidate feature 포함·score 0).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    payload = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    try:
        data = json.loads(payload or "{}")
    except Exception:
        data = {}
    dw = data.get("date_window")
    # 길이-2 [start, end]만 허용(code-review NIT-3: malformed 1-element → _in_window IndexError 방지·fail-closed None).
    date_window = (dw[0], dw[1]) if isinstance(dw, (list, tuple)) and len(dw) == 2 else None
    out = build_official_news_bridge(
        data.get("official_records") or [], data.get("news_records") or [], date_window=date_window)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} bridge_type={out['bridge_type']}")
    print(f"- official={out['official_record_count']} news={out['news_record_count']} "
          f"evaluated={out['pair_count_evaluated']} bridge_candidates={out['bridge_candidate_count']} "
          f"freeze_eligible={out['freeze_eligible_bridge_count']}")
    print(f"- merge={out['merge_allowed']} same_event={out['same_event_asserted']} "
          f"reviewer_routing_only={out['reviewer_routing_only']} score_exposed={out['bridge_score_exposed']}")
    print(f"- blocked_reason: {out['blocked_reason'] or '(none — freeze-eligible candidates)'}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""ADR#57 — source overlap discovery (write-free·결정론·no-merge·no-DB).

RealSourceLoop(R-RealSourceLoopUnproven)의 다음 hard blocker: artificial replay 로 입증된
cross-batch adjudication substrate 를 **실 source behavior** 에서 재현할 수 있는가. 재현이 안 되면
어떤 source/data/fingerprint/coverage 조건이 부족한지 **수치로 분해**한다.

핵심 통찰(왜 단순 "더 많이 fetch"가 답이 아닌가):
  - 결정론 cross-batch identity 는 **fingerprint 정확 token-set 일치 + 같은 date bucket** 만 인정한다
    (`cross_source_dedup.semantic_identity_fingerprint`; 고정밀·저재현·false-merge 0).
  - 실제 다른 매체의 같은 사건 헤드라인은 paraphrase 되어 token-set 이 정확히 일치하기 어렵다 →
    overlap 이 **존재해도** deterministic fingerprint 의 사각지대일 수 있다.
  - 따라서 이 도구는 overlap 을 두 입도로 분해한다:
      ① `fingerprint_overlap`            = 정확 token-set 일치 → deterministic 이 `semantic_cross_batch_candidate`
                                           로 잡는다(같은 사건·다른 URL·교차배치 시).
      ② `near_match_below_fingerprint`   = title token Jaccard≥near 이나 fingerprint 불일치 → **deterministic
                                           사각지대**. 미래 semantic adjudicator(embedding/LLM/KG) 영역이며
                                           MERGE_GATE·gold 미충족이면 병합 금지(이번 턴 LLM 호출 0).

경계(불변):
  - **write-free·no-DB**: 이 모듈은 DB 에 쓰지 않는다(overlap 신호 측정만). live-db 검증은 escalation 정책에
    따라 `real_source_identity_smoke` 가 safe-target gated 로 수행한다.
  - **no-merge**: near-match 든 fingerprint 일치든 **병합하지 않는다**(no_auto_merge=True 불변). overlap pair 는
    candidate hint / report signal 일 뿐이다.
  - **본문 미저장**: title 헤드라인·canonical·published_at·source_id 만(전문/raw_payload/PII 미반영·옵션 C 계약).
  - **source role guard**: merge anchor 후보는 publishable core(official/article)만. community/market/catalog 는
    reaction/signal/enrichment 레이어로 분리(anchor 아님).
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from typing import Any, Callable, Optional

from backend.app.services.event_ingest_pipeline import _RECORD_TYPE_TO_SOURCE_TYPE
from ingestion.orchestration.cross_source_dedup import (
    _MIN_SEMANTIC_TOKENS,
    _TITLE_JACCARD_THRESHOLD,
    _date_bucket,
    _jaccard,
    _title_tokens,
    semantic_identity_fingerprint,
)

# merge anchor 자격(event_ingest_pipeline._IDENTITY_ANCHOR_SOURCE_TYPES 와 정합) — publishable core 만.
_PUBLISHABLE_SOURCE_TYPES = frozenset({"official", "article"})
# near-match 임계: fingerprint 정확일치(token-set 동치)보다 느슨하나 within-batch 약신호 결합(0.8)보다도
# 낮춰 "overlap 은 있으나 fingerprint 사각지대"인 adjudicator-zone 까지 본다(병합 아님·신호 측정만).
DEFAULT_NEAR_JACCARD = 0.5

# GDELT DOC ArtList — key-free·다출처 집계(같은 사건이 다른 outlet·다른 URL 로 등장 → 실 cross-source overlap 생성원).
_GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_DEFAULT_MAX_RECORDS = 25      # bounded(폭주·rate-limit 차단).
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _rec(**kw: Any) -> dict:
    base = {
        "record_type": "article_candidate", "source_id": "unknown",
        "title_or_label": None, "source_url_or_evidence": None, "canonical_url": None,
        "published_at_or_observed_at": None, "body_state_or_signal": "missing",
    }
    base.update(kw)
    return base


def _role(rec: dict) -> str:
    return _RECORD_TYPE_TO_SOURCE_TYPE.get(rec.get("record_type"), "unknown")


def _publishable(rec: dict) -> bool:
    return _role(rec) in _PUBLISHABLE_SOURCE_TYPES


def _fingerprint(rec: dict) -> Optional[str]:
    return semantic_identity_fingerprint(
        rec.get("title_or_label"), rec.get("published_at_or_observed_at"))


# ── captured 합성 fixture(옵션 C: sanitized capture·본문 미저장·실 source behavior 아님) ────────────
def build_captured_overlap_fixture() -> list[dict]:
    """**captured/합성** GDELT 형태 fixture — 실 다출처 overlap 의 두 입도를 결정론으로 재현(network 0).

    같은 사건("port strike"):
      - outlet 2개가 **wire 헤드라인 verbatim** 재게재(같은 token-set·다른 URL) → fingerprint_overlap(deterministic 검출).
      - outlet 2개가 **paraphrase**(같은 사건·token 대부분 공유하나 정확 집합 불일치) → near_match_below_fingerprint
        (Jaccard≥near 이나 fingerprint 불일치 → adjudicator/LLM/embedding 영역·gated).
    + 무관 기사 1(overlap 0 대조군) + community 1(같은 제목이나 anchor 금지 reaction layer).
    headline≤512·canonical·published_at·source_id 만(본문 미저장). 실 source 가 아니라 **계약/입도 검증용**."""
    day = "2026-06-22"
    wire = "Major port strike halts container shipping operations nationwide"
    return [
        _rec(source_id="gdelt:wire_ap", canonical_url="https://outlet-a.test/strike",
             title_or_label=wire, published_at_or_observed_at=day),
        _rec(source_id="gdelt:wire_reuters", canonical_url="https://outlet-b.test/strike",
             title_or_label=wire, published_at_or_observed_at=day),
        # paraphrase A: wire 에서 "nationwide" 누락(token 7 ⊂ wire 8) → Jaccard 0.875·정확 집합 불일치 → near.
        _rec(source_id="gdelt:local_news", canonical_url="https://outlet-c.test/dockworkers",
             title_or_label="Major port strike halts container shipping operations",
             published_at_or_observed_at=day),
        # paraphrase B: "major"→없음·"today" 추가 → wire 와 Jaccard 0.778·정확 집합 불일치 → near.
        _rec(source_id="gdelt:biz_news", canonical_url="https://outlet-d.test/cargo",
             title_or_label="Port strike halts container shipping operations nationwide today",
             published_at_or_observed_at=day),
        _rec(source_id="gdelt:weather", canonical_url="https://outlet-e.test/heat",
             title_or_label="Record heat wave grips southern region this week",
             published_at_or_observed_at=day),
        _rec(record_type="community_signal", source_id="gdelt:forum",
             canonical_url="https://forum.test/strike-thread",
             title_or_label="Major port strike halts container shipping operations nationwide",
             published_at_or_observed_at=day),
    ]


# ── GDELT real fetch(opt-in·bounded·key-free·본문 미저장·transport 주입 시 결정론) ───────────────
def _gdelt_url(query: str, timespan: str, maxrecords: int) -> str:
    from urllib.parse import urlencode
    return _GDELT_BASE + "?" + urlencode(
        {"query": query, "mode": "ArtList", "maxrecords": str(maxrecords),
         "format": "json", "timespan": timespan})


def parse_gdelt_articles(payload: str, *, max_records: int = _DEFAULT_MAX_RECORDS) -> Optional[list[dict]]:
    """GDELT ArtList JSON → record(canonical=art url·title·seendate=published_at·본문 미저장). 파싱 실패 None.

    같은 사건이 다른 outlet·다른 URL 로 등장하는 다출처 집계 — 실 cross-source overlap 의 핵심 생성원.
    seendate(YYYYMMDDhhmmss)는 그대로 published_at 으로 두면 normalize_time/_date_bucket 가 정규화한다."""
    try:
        data = json.loads(payload)
    except Exception:
        return None
    arts = data.get("articles")
    if not isinstance(arts, list):
        return None
    recs: list[dict] = []
    for art in arts[:max_records]:
        if not isinstance(art, dict):
            continue
        title = (art.get("title") or "").strip()
        url = (art.get("url") or "").strip()
        if not title or not url:
            continue
        recs.append(_rec(
            record_type="article_candidate", source_id="gdelt:" + (art.get("domain") or "unknown"),
            title_or_label=title[:512], canonical_url=url, source_url_or_evidence=url,
            published_at_or_observed_at=(art.get("seendate") or None),
            body_state_or_signal="present"))
    return recs


def fetch_gdelt_overlap_records(
    *, query: str = "world news", timespan: str = "1d",
    maxrecords: int = _DEFAULT_MAX_RECORDS,
    transport: Optional[Callable[[str], Optional[str]]] = None,
) -> tuple[list[dict], Optional[str]]:
    """GDELT bounded 실 fetch(opt-in·network·CI 아님). transport 주입 시 결정론(테스트·network 0).

    반환: (records, failure). 실패는 §6 분류(network_error/rate_limited/parser_error/no_records)."""
    url = _gdelt_url(query, timespan, maxrecords)
    if transport is not None:
        payload = transport(url)
    else:
        try:
            import httpx
            r = httpx.get(url, timeout=20.0, follow_redirects=True,
                          headers={"User-Agent": _BROWSER_UA})
        except Exception:
            return [], "network_error"
        text = r.text or ""
        if r.status_code == 429 or "limit requests" in text.lower():
            return [], "rate_limited"
        if "json" not in (r.headers.get("content-type") or "").lower():
            return [], "parser_error"   # 200 이나 평문 안내(GDELT over-query) — JSON 아님.
        payload = text
    if not payload:
        return [], "network_error"
    recs = parse_gdelt_articles(payload, max_records=maxrecords)
    if recs is None:
        return [], "parser_error"
    if not recs:
        return [], "no_records"
    return recs, None


# ── write-free pairwise overlap discovery(병합 없음·신호 측정만) ─────────────────────────────────
def discover_overlap(
    records: list[dict], *, discovery_mode: str = "captured_fixture",
    real_fetch: bool = False, near_jaccard: float = DEFAULT_NEAR_JACCARD,
) -> dict:
    """record 목록 → 다입도 pairwise overlap 수치화(write-free·no-merge·§4/§5 fields).

    overlap 을 ①fingerprint 정확일치(deterministic 검출) ②near_match_below_fingerprint(adjudicator/LLM 영역)
    로 분해해 "어디까지 deterministic 이 잡고 어디부터 adjudicator 영역인가"를 정직하게 가른다. 병합하지 않는다."""
    n = len(records)
    by_source: dict[str, int] = {}
    for r in records:
        sid = r.get("source_id") or "unknown"
        by_source[sid] = by_source.get(sid, 0) + 1

    canonical_overlap = 0          # 같은 canonical_url(강 anchor dup — cross-source 후보 아님·이미 병합 대상)
    date_overlap = 0               # 같은 date bucket(임의 role)
    fingerprint_overlap = 0        # 정확 fingerprint 일치·다른 URL·둘 다 publishable → deterministic 검출
    near_only = 0                  # near Jaccard≥near·fingerprint 불일치·다른 URL·둘 다 publishable → adjudicator 영역
    possible_same_event: list[tuple[str, str, str]] = []   # (canonical_i, canonical_j, granularity)
    pair_matrix: dict[tuple[str, str], dict[str, int]] = {}
    publishable_pairs = 0
    publishable_same_date_pairs = 0
    publishable_cross_url_same_date_pairs = 0

    for a, b in combinations(range(n), 2):
        ra, rb = records[a], records[b]
        same_date = bool(_date_bucket(ra)) and _date_bucket(ra) == _date_bucket(rb)
        if same_date:
            date_overlap += 1
        ca, cb = ra.get("canonical_url"), rb.get("canonical_url")
        same_canon = bool(ca) and ca == cb
        if same_canon:
            canonical_overlap += 1
        both_pub = _publishable(ra) and _publishable(rb)
        if not both_pub:
            continue
        publishable_pairs += 1
        if same_date:
            publishable_same_date_pairs += 1
        if same_canon or not same_date:
            continue   # cross-source overlap 후보 = 다른 URL·같은 날만.
        publishable_cross_url_same_date_pairs += 1
        fa, fb = _fingerprint(ra), _fingerprint(rb)
        jac = _jaccard(_title_tokens(ra.get("title_or_label")), _title_tokens(rb.get("title_or_label")))
        pkey = tuple(sorted((ra.get("source_id") or "unknown", rb.get("source_id") or "unknown")))
        slot = pair_matrix.setdefault(pkey, {"same_date": 0, "fingerprint": 0, "near": 0, "possible": 0})
        slot["same_date"] += 1
        if fa is not None and fa == fb:
            fingerprint_overlap += 1
            slot["fingerprint"] += 1
            slot["possible"] += 1
            possible_same_event.append((ca, cb, "fingerprint"))
        elif jac >= near_jaccard:
            near_only += 1
            slot["near"] += 1
            slot["possible"] += 1
            possible_same_event.append((ca, cb, "near_match_below_fingerprint"))

    block_reasons = _block_reasons(
        records, possible=len(possible_same_event), fingerprint=fingerprint_overlap, near=near_only,
        publishable_pairs=publishable_pairs, pub_same_date=publishable_same_date_pairs,
        pub_cross_url_same_date=publishable_cross_url_same_date_pairs)

    return {
        "discovery_mode": discovery_mode,
        "real_fetch": real_fetch,
        "live_db": False,
        "no_auto_merge": True,
        "source_count": len(by_source),
        "records_by_source": dict(sorted(by_source.items())),
        "total_records": n,
        "body_present_count": sum(
            1 for r in records if (r.get("body_state_or_signal") or "missing") != "missing"),
        "canonical_count": sum(1 for r in records if r.get("canonical_url")),
        "published_at_count": sum(1 for r in records if r.get("published_at_or_observed_at")),
        "date_bucket_overlap_pairs": date_overlap,
        "canonical_overlap_pairs": canonical_overlap,
        "title_token_overlap_pairs": fingerprint_overlap + near_only,   # near 이상(fingerprint 포함)
        "fingerprint_overlap_pairs": fingerprint_overlap,               # deterministic 검출(→ semantic_cross_batch_candidate)
        "near_match_below_fingerprint_pairs": near_only,                # adjudicator/LLM 영역(deterministic 사각지대)
        "possible_same_event_pairs": len(possible_same_event),
        "deterministic_detectable_pairs": fingerprint_overlap,
        "adjudicator_zone_pairs": near_only,
        # write-free — DB 단계는 미도달(정직). live-db escalation 시 real_source_identity_smoke 가 채운다.
        "semantic_cross_batch_candidates": None,
        "adjudications": None,
        "packet_eligible": None,
        "reviewer_packet_exportable": None,
        "overlap_potential_matrix": _overlap_potential_matrix(pair_matrix),
        "block_reasons": block_reasons,
        "near_jaccard_threshold": near_jaccard,
        "fingerprint_min_tokens": _MIN_SEMANTIC_TOKENS,
        "within_batch_weak_threshold": _TITLE_JACCARD_THRESHOLD,
    }


def _overlap_potential_matrix(pair_matrix: dict[tuple[str, str], dict[str, int]]) -> list[dict]:
    """source-pair 별 overlap 잠재력(Agent 가 어느 pair 를 어떤 목적으로 수집할지 판단할 substrate)."""
    rows: list[dict] = []
    for (sa, sb), c in sorted(pair_matrix.items()):
        if c["possible"] > 0:
            potential = "deterministic_detectable" if c["fingerprint"] > 0 else "adjudicator_zone_only"
        else:
            potential = "no_overlap"
        rows.append({
            "source_pair": [sa, sb],
            "same_date_pairs": c["same_date"],
            "fingerprint_overlap": c["fingerprint"],
            "near_match_overlap": c["near"],
            "possible_same_event": c["possible"],
            "overlap_potential": potential,
        })
    return rows


def _block_reasons(
    records: list[dict], *, possible: int, fingerprint: int, near: int,
    publishable_pairs: int, pub_same_date: int, pub_cross_url_same_date: int,
) -> list[str]:
    """possible_same_event=0(또는 fingerprint=0) 의 **정확한 원인**을 단계로 분해(source scarcity 를 모델 실패로
    뭉뚱그리지 않는다). overlap 이 near 만 있고 fingerprint 가 0 이면 deterministic 사각지대를 명시한다."""
    out: list[str] = []
    if len(records) < 2:
        out.append("insufficient_records")
        return out
    if publishable_pairs == 0:
        out.append("non_publishable_role")   # community/market/catalog only — anchor 부재.
        return out
    if possible == 0:
        if pub_same_date == 0:
            out.append("no_date_bucket_overlap")     # 같은 날 publishable pair 부재(시점 분산).
        elif pub_cross_url_same_date == 0:
            out.append("single_canonical_no_cross_source")   # 같은 URL 만(다출처 아님 → 이미 강 anchor dup).
        else:
            out.append("no_title_overlap")           # 다출처·같은 날이나 token overlap 미달(서로 다른 사건).
        return out
    if fingerprint == 0 and near > 0:
        # overlap 은 있으나 fingerprint 정확일치 0 → deterministic 미검출. adjudicator/embedding/LLM 영역(gated).
        out.append("near_match_below_fingerprint")
    return out


# ── Agent orchestration schema(§9·LLM 호출 0·merge 불가 명문화) ──────────────────────────────────
def build_agent_orchestration_schema(discovery: dict) -> dict:
    """결정론 overlap 신호 → Agent 가 다음 수집을 계획할 schema(추천·계획만·병합/공개 IU 생성 불가).

    Agent 는 overlap 가능 source pair·시점창·watch topic 을 추천할 수 있으나, MERGE_GATE·gold 없이 같은 사건이라고
    단정하거나 병합할 수 없다(no_merge_without_gate). 이번 턴 LLM 호출 0 — 다음 단계가 쓸 substrate 만 보강."""
    matrix = discovery.get("overlap_potential_matrix") or []
    recommended_pairs = [m["source_pair"] for m in matrix if m["overlap_potential"] != "no_overlap"]
    det = discovery.get("deterministic_detectable_pairs", 0) or 0
    adj = discovery.get("adjudicator_zone_pairs", 0) or 0
    if det > 0:
        reason = "fingerprint_exact_token_set_match(같은 사건·다른 URL·같은 날 — deterministic 검출)"
    elif adj > 0:
        reason = "near_match_below_fingerprint(paraphrase overlap — adjudicator/embedding/LLM 영역·gated)"
    else:
        reason = "no_overlap(source coverage/시점/다출처 부족 — block_reasons 참조)"
    return {
        "recommended_source_pairs": recommended_pairs,
        "recommended_time_windows": ["1d", "7d"],   # GDELT timespan(다출처 같은 사건 재유입 관측창).
        "recommended_watch_topics": [],              # 결정론 단계 미산출(LLM/Agent 가 채움 — 이번 턴 미배선).
        "expected_overlap_reason": reason,
        "source_role_constraints": {
            "merge_anchor_eligible": sorted(_PUBLISHABLE_SOURCE_TYPES),   # official/article 만.
            "reaction_layer_only": ["community"],
            "signal_layer_only": ["signal"],
            "enrichment_only": ["catalog"],
            "url_candidate_only": ["search"],
        },
        "evidence_requirements": ["canonical_url", "published_at", "title"],
        "uncertainty": {
            "fingerprint_precision_recall": "high_precision_low_recall(정확 token-set 일치만)",
            "adjudicator_zone_unverified": adj,   # near overlap 은 gold/MERGE_GATE 없이는 미확정.
        },
        "no_merge_without_gate": True,             # MERGE_GATE·gold 없이 병합 금지(불변).
        "no_public_intelligence_unit": True,       # curated IU 생성 금지(미구축).
        "llm_invoked": False,                      # 이번 턴 LLM 호출 0.
        "next_fetch_plan": (
            "deterministic overlap 존재 → live-db escalation 으로 semantic_cross_batch_candidate 실측"
            if det > 0 else
            ("adjudicator-zone overlap 존재 → embedding/LLM adjudicator(gated)·실 gold 필요"
             if adj > 0 else "다출처/시점/topic 커버리지 확대 후 재탐색(block_reasons 분해 참조)")),
    }


# ── CLI(기본 captured fixture·network 0; --live-gdelt opt-in·CI 아님) ────────────────────────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="source overlap discovery (write-free·no-merge; 기본 captured fixture·network 0).")
    parser.add_argument("--live-gdelt", action="store_true",
                        help="GDELT bounded 실 fetch(opt-in·network·CI 아님·key-free). 미지정=captured fixture.")
    parser.add_argument("--query", default="world news", help="GDELT query(--live-gdelt).")
    parser.add_argument("--timespan", default="1d", help="GDELT timespan 시점창(1d/7d/3m).")
    parser.add_argument("--maxrecords", type=int, default=_DEFAULT_MAX_RECORDS, help="GDELT bounded 상한.")
    parser.add_argument("--near-jaccard", type=float, default=DEFAULT_NEAR_JACCARD,
                        help="near-match Jaccard 임계(fingerprint 사각지대 관측창).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    failure: Optional[str] = None
    if ns.live_gdelt:
        print(f"- live-gdelt fetch (opt-in·bounded·key-free): query={ns.query!r} timespan={ns.timespan} max={ns.maxrecords}")
        records, failure = fetch_gdelt_overlap_records(
            query=ns.query, timespan=ns.timespan, maxrecords=ns.maxrecords)
        mode, real = "source_pair_live", True
        if failure:
            print(f"- live-gdelt failure: {failure} → captured fixture fallback")
            records, mode, real = build_captured_overlap_fixture(), "captured_fixture", False
    else:
        records, mode, real = build_captured_overlap_fixture(), "captured_fixture", False

    disc = discover_overlap(records, discovery_mode=mode, real_fetch=real, near_jaccard=ns.near_jaccard)
    schema = build_agent_orchestration_schema(disc)
    print(
        f"- discovery[{disc['discovery_mode']}]: real_fetch={disc['real_fetch']} "
        f"sources={disc['source_count']} records={disc['total_records']} "
        f"canonical={disc['canonical_count']} published={disc['published_at_count']}")
    print(
        f"- overlap: date_bucket={disc['date_bucket_overlap_pairs']} canonical={disc['canonical_overlap_pairs']} "
        f"fingerprint={disc['fingerprint_overlap_pairs']} near_only={disc['near_match_below_fingerprint_pairs']} "
        f"possible_same_event={disc['possible_same_event_pairs']}")
    print(
        f"- decompose: deterministic_detectable={disc['deterministic_detectable_pairs']} "
        f"adjudicator_zone={disc['adjudicator_zone_pairs']} block_reasons={disc['block_reasons']} "
        f"no_auto_merge={disc['no_auto_merge']} live_gdelt_failure={failure}")
    for m in disc["overlap_potential_matrix"]:
        print(f"  · pair {m['source_pair']}: {m['overlap_potential']} (fingerprint={m['fingerprint_overlap']}·near={m['near_match_overlap']})")
    print(f"- agent_schema: recommended_pairs={len(schema['recommended_source_pairs'])} "
          f"expected_overlap={schema['expected_overlap_reason']}")
    print(f"  · next_fetch_plan: {schema['next_fetch_plan']}")
    print(f"  · no_merge_without_gate={schema['no_merge_without_gate']} llm_invoked={schema['llm_invoked']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

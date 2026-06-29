"""ADR#85 — provider date-window fidelity control experiment (mechanism decomposition · merge 0 · LLM 0 · secret 0).

ADR#84 가 정직하게 남긴 미확정: date-pinned 첫 실 live run 에서 **URL 의 date param 은 정확했으나**(오프라인 검증)
응답은 window 밖·주제 무관 기사였다 — *요청 window 가 응답을 제약하지 못함은 확정, 메커니즘은 미확정*. 이 모듈은
그 메커니즘을 **통제실험으로 분해**한다(둔갑 0·overclaim 0). 같은 query/window 를 variant 로 바꿔가며 실측한다:

  - original         : date param + order=newest (현행)            — baseline.
  - no_date          : date param 제외 + order=newest              — date-param 한계효과 분리.
  - relevance_order  : date param + order=relevance                — newest 지배 가설 분리.
  - exact_phrase     : named_entity 를 exact phrase 로 + date param — 느슨한 q 가설 분리.
  - enforce_window   : date param + order=newest + post-filter      — 반환셋에 in-window record 가 실재하는지.

분해 결과는 **단정하지 않고 confidence(low/medium·절대 high 금지)** 와 함께 가설 목록으로 낸다. 출력은
aggregate-only(counts/dates/float·status) — 제목 전문·raw body·secret·per-pair score·same_event truth 미노출.
query_token_overlap 은 record 제목 토큰과 query 토큰의 Jaccard(약한 lexical relevance·reviewer-routing 진단)이지
같은 사건 truth 가 아니다. live 호출은 opt-in(live_query=True)·transport 주입 시 결정론(network 0·key 불요)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Callable, Optional

from backend.app.tools.provider_query_adapters import run_provider_query

OPERATION_NAME = "provider_date_window_fidelity"

# ── variant 이름(§8.2) ─────────────────────────────────────────────────────────────────────────────────────
V_ORIGINAL = "original"
V_NO_DATE = "no_date"
V_RELEVANCE = "relevance_order"
V_EXACT = "exact_phrase"
V_ENFORCE = "enforce_window"
DEFAULT_VARIANTS: tuple[str, ...] = (V_ORIGINAL, V_NO_DATE, V_RELEVANCE, V_EXACT, V_ENFORCE)

# ── result class(per variant) ──────────────────────────────────────────────────────────────────────────────
RC_IN_WINDOW_RELATED = "in_window_related"       # in-window record 존재 + query 와 lexical relevance(약).
RC_IN_WINDOW_UNRELATED = "in_window_unrelated"   # in-window record 존재하나 query 와 무관(ADR#84 핵심 증상).
RC_OUT_OF_WINDOW_ONLY = "out_of_window_only"     # 반환 record 가 전부 window 밖.
RC_NO_RECORDS = "no_records"                     # provider 가 0 records 반환(진짜 빈 응답).
RC_GATED = "gated"                               # credential/host/rate/network/parser — fetch 미성공.
RC_NOT_RUN = "not_run"                           # opt-in 아님/선행 게이트로 미실행.

# ── mechanism hypotheses(§8.3) ─────────────────────────────────────────────────────────────────────────────
H_DATE_IGNORED = "date_filter_ignored"
H_NEWEST = "order_by_newest_dominance"
H_LOOSE_Q = "loose_query_relevance"
H_ZERO_COV = "zero_in_window_coverage"
H_INDET = "indeterminate"

_REL_FLOOR = 0.15   # 약한 lexical relevance floor(같은 사건 truth 아님·reviewer-routing 진단 신호).
_GATED_STATUSES = frozenset({
    "missing_credentials", "host_gate_blocked", "rate_limited", "network_error",
    "parser_error", "fetcher_not_wired", "disabled", "unknown",
})
# 이후 variant 도 동일하게 막히는 hard 게이트(불필요 호출 0·나머지 not_run).
_HARD_GATE_STATUSES = frozenset({"missing_credentials", "host_gate_blocked", "rate_limited"})


def _qtokens(text: Optional[str]) -> set:
    """제목/query → 정규화 토큰 집합(cross_source 와 동일 정규화 재사용·실패 시 보수적 split)."""
    try:
        from ingestion.orchestration.cross_source_dedup import _title_tokens
        return set(_title_tokens(text or ""))
    except Exception:
        return set((text or "").lower().split())


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return round(len(a & b) / union, 4) if union else 0.0


def _variant_args(name: str, target: dict) -> dict:
    """variant → run_provider_query knob(topic/omit_date_window/order/enforce_window). exact_phrase 는
    named_entity 를 따옴표로 묶어 exact phrase 강제(느슨한 OR-매칭 분리)."""
    qt = target.get("query_text") or ""
    ne = (target.get("named_entity") or "").strip()
    ep = (target.get("event_phrase") or "").strip()
    exact_q = (f'"{ne}" {ep}'.strip() if (ne and ep) else (f'"{ne}"' if ne else qt))
    table = {
        V_ORIGINAL: dict(topic=qt, omit_date_window=False, order=None, enforce_window=False),
        V_NO_DATE: dict(topic=qt, omit_date_window=True, order=None, enforce_window=False),
        V_RELEVANCE: dict(topic=qt, omit_date_window=False, order="relevance", enforce_window=False),
        V_EXACT: dict(topic=exact_q, omit_date_window=False, order=None, enforce_window=False),
        V_ENFORCE: dict(topic=qt, omit_date_window=False, order=None, enforce_window=True),
    }
    return table[name]


def _aggregate_variant(name: str, qr: Any, *, start_date: Optional[str], end_date: Optional[str],
                       query_tokens: set, enforce: bool) -> dict:
    """ProviderQueryResult → aggregate-only variant row(제목 전문·raw body 미노출). in/out-of-window 카운트는
    record published date(YYYY-MM-DD) 로 직접 계산(provider 무시 가능성 때문에 adapter 측 신뢰 안 함)."""
    status = qr.status
    block = qr.block_reason
    base = {
        "variant": name, "status": status, "block_reason": block,
        "records_returned": 0, "in_window_count": 0, "out_of_window_count": 0,
        "returned_date_min": None, "returned_date_max": None,
        "query_token_overlap_max": 0.0,
    }
    if status in _GATED_STATUSES:
        return {**base, "result_class": RC_GATED}
    recs = list(qr.records or [])
    in_w = out_w = 0
    dmin = dmax = None
    ov_max = 0.0
    for r in recs:
        pub = r.get("published_at_or_observed_at")
        d = pub[:10] if (pub and len(pub) >= 10) else None
        if d:
            dmin = d if (dmin is None or d < dmin) else dmin
            dmax = d if (dmax is None or d > dmax) else dmax
            if start_date and end_date and start_date <= d <= end_date:
                in_w += 1
            else:
                out_w += 1
        else:
            out_w += 1   # 날짜 불명 → 보수적으로 out-of-window 취급(date-pin 후보 아님).
        ov = _jaccard(_qtokens(r.get("title_or_label")), query_tokens)
        ov_max = ov if ov > ov_max else ov_max
    # result class.
    if enforce and status == "no_records" and block == "no_in_window_records":
        rc = RC_OUT_OF_WINDOW_ONLY     # enforce 가 out-of-window 를 전부 drop(반환셋에 in-window 0).
    elif status == "no_records":
        rc = RC_NO_RECORDS
    elif in_w > 0:
        rc = RC_IN_WINDOW_RELATED if ov_max >= _REL_FLOOR else RC_IN_WINDOW_UNRELATED
    else:
        rc = RC_OUT_OF_WINDOW_ONLY
    return {
        **base, "records_returned": len(recs), "in_window_count": in_w, "out_of_window_count": out_w,
        "returned_date_min": dmin, "returned_date_max": dmax,
        "query_token_overlap_max": ov_max, "result_class": rc,
    }


def _not_run_row(name: str, reason: str) -> dict:
    return {"variant": name, "status": "not_run", "block_reason": reason,
            "records_returned": 0, "in_window_count": 0, "out_of_window_count": 0,
            "returned_date_min": None, "returned_date_max": None,
            "query_token_overlap_max": 0.0, "result_class": RC_NOT_RUN}


def _ran(a: Optional[dict]) -> bool:
    """variant 가 실제 실행돼 분류 가능한 결과를 냈는가(not_run/gated 제외)."""
    return bool(a) and a["status"] != "not_run" and a["result_class"] != RC_GATED


def _by(results: list[dict], name: str) -> Optional[dict]:
    return next((r for r in results if r["variant"] == name), None)


def _date_param_effect(o: Optional[dict], nd: Optional[dict]) -> tuple[str, str]:
    if not (_ran(o) and _ran(nd)):
        return ("untested", "date-param 유/무 비교 미실행")
    if o["in_window_count"] > 0 and nd["in_window_count"] == 0:
        return ("strong", "date-param 제거 시 in-window 가 사라짐 → date filter 가 실제로 작동")
    if o["in_window_count"] == nd["in_window_count"] and o["out_of_window_count"] == nd["out_of_window_count"]:
        return ("weak", "date-param 유/무가 반환셋을 바꾸지 않음 → date filter 무시 정황")
    if o["in_window_count"] == 0 and nd["in_window_count"] == 0:
        return ("indeterminate", "양쪽 in-window 0 → 이 쌍만으로 date filter 효과 분리 불가(coverage 0 가능)")
    return ("partial", "date-param 이 반환셋을 일부만 변경")


def _order_effect(o: Optional[dict], rel: Optional[dict]) -> tuple[str, str]:
    if not (_ran(o) and _ran(rel)):
        return ("untested", "order=relevance 비교 미실행")
    o_related = o["result_class"] == RC_IN_WINDOW_RELATED
    r_related = rel["result_class"] == RC_IN_WINDOW_RELATED
    if rel["in_window_count"] > o["in_window_count"] or (r_related and not o_related):
        return ("strong", "relevance 정렬이 newest 보다 in-window/related 결과를 더 끌어옴 → newest 지배")
    if rel["in_window_count"] == o["in_window_count"] and rel["result_class"] == o["result_class"]:
        return ("weak", "relevance 정렬도 동일 결과 → newest 지배 정황 약함")
    return ("partial", "relevance 정렬이 결과를 일부 변경")


def _query_effect(o: Optional[dict], ex: Optional[dict]) -> tuple[str, str]:
    if not (_ran(o) and _ran(ex)):
        return ("untested", "exact_phrase 비교 미실행")
    o_related = o["result_class"] == RC_IN_WINDOW_RELATED
    e_related = ex["result_class"] == RC_IN_WINDOW_RELATED
    if ex["query_token_overlap_max"] > o["query_token_overlap_max"] + 0.1 or (e_related and not o_related):
        return ("strong", "exact phrase 가 더 관련된(높은 overlap) 결과 → 느슨한 q 가 원인")
    if ex["result_class"] == o["result_class"]:
        return ("weak", "exact phrase 도 동일 결과 → q 느슨함이 주원인 아님")
    return ("partial", "exact phrase 가 결과를 일부 변경")


def _coverage_effect(en: Optional[dict]) -> tuple[str, str]:
    if not _ran(en):
        return ("untested", "enforce_window variant 미실행/gated")
    if en["result_class"] == RC_OUT_OF_WINDOW_ONLY or en["block_reason"] == "no_in_window_records":
        return ("zero_in_returned", "enforce_window 가 반환셋의 out-of-window 를 전부 drop → in-window record 0")
    if en["in_window_count"] > 0:
        return ("in_window_present", "enforce_window 후에도 in-window record 생존(in-window coverage 존재)")
    return ("untested", "enforce_window 결과 불명")


def _classify_mechanism(results: list[dict]) -> dict:
    """variant 집합 → 메커니즘 가설 + confidence(절대 단정/overclaim 금지). 단일 bounded run 은 최대 medium."""
    o, nd = _by(results, V_ORIGINAL), _by(results, V_NO_DATE)
    rel, ex, en = _by(results, V_RELEVANCE), _by(results, V_EXACT), _by(results, V_ENFORCE)
    de, de_sig = _date_param_effect(o, nd)
    oe, oe_sig = _order_effect(o, rel)
    qe, qe_sig = _query_effect(o, ex)
    ce, ce_sig = _coverage_effect(en)

    hypotheses: list[dict] = []
    if oe == "strong":
        hypotheses.append({"hypothesis": H_NEWEST, "confidence": "medium", "signal": oe_sig})
    if qe == "strong":
        hypotheses.append({"hypothesis": H_LOOSE_Q, "confidence": "medium", "signal": qe_sig})
    if de == "weak":
        hypotheses.append({"hypothesis": H_DATE_IGNORED,
                           "confidence": "medium" if ce == "zero_in_returned" else "low", "signal": de_sig})
    if ce == "zero_in_returned" and de in ("weak", "indeterminate"):
        hypotheses.append({"hypothesis": H_ZERO_COV, "confidence": "low", "signal": ce_sig})

    # primary 선택(가장 강한 lever 우선). 분리 불가하면 indeterminate(정직).
    if oe == "strong":
        primary, confidence = H_NEWEST, "medium"
    elif qe == "strong":
        primary, confidence = H_LOOSE_Q, "medium"
    elif de == "weak":
        # original==no_date(in/out split 동일) → date param 이 응답을 제약하지 못함을 **직접** 시사(date_filter_ignored).
        # 이는 'date filter 작동 + zero coverage' 가설을 반증한다(작동했다면 original 은 [from,to] 로 제약돼 no_date 의
        # newest 와 달라야 함). 따라서 coverage 0 가 같이 관측돼도 primary 는 date_filter_ignored(medium·단정 high 아님).
        primary, confidence = H_DATE_IGNORED, "medium"
    elif ce == "zero_in_returned":
        # date-param 비교(no_date) 없이 enforce 만 전부 drop → coverage 0 정황(단 date_filter_ignored 와 미분리·low).
        primary, confidence = H_ZERO_COV, "low"
    else:
        primary, confidence = H_INDET, "low"
    return {
        "date_param_effect": de, "date_param_effect_signal": de_sig,
        "order_by_newest_effect": oe, "order_by_newest_effect_signal": oe_sig,
        "query_relevance_effect": qe, "query_relevance_effect_signal": qe_sig,
        "in_window_coverage_effect": ce, "in_window_coverage_effect_signal": ce_sig,
        "date_filter_mechanism_hypotheses": hypotheses,
        "mechanism_primary_hypothesis": primary,
        "mechanism_confidence": confidence,   # 절대 high 아님(단일 bounded run).
    }


def _provider_window_status(results: list[dict]) -> str:
    """provider 의 date-window 준수 상태 한 줄(operator 가독·aggregate)."""
    o = _by(results, V_ORIGINAL)
    if not o or o["status"] == "not_run":
        return "not_run"
    if o["result_class"] == RC_GATED:
        return f"gated:{o['block_reason']}"
    if o["result_class"] == RC_IN_WINDOW_RELATED:
        return "honors_window_related"
    if o["result_class"] == RC_IN_WINDOW_UNRELATED:
        return "in_window_but_unrelated"
    if o["result_class"] == RC_OUT_OF_WINDOW_ONLY:
        return "returns_out_of_window"
    return "no_records"


def run_date_window_fidelity_probe(
    target: dict, *, provider: str = "guardian", variants: tuple[str, ...] = DEFAULT_VARIANTS,
    transport: Optional[Callable[[str], Optional[str]]] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    host_gate: Any = None, live_query: bool = False,
    pace_seconds: float = 0.0, sleep_fn: Optional[Callable[[float], None]] = None,
) -> dict:
    """date-pinned target(build_live_query_target) → provider date-window fidelity 통제실험(§8).

    live_query=False(기본) → 호출 0(variant 전부 not_run). True → variant 별 run_provider_query(bounded·governed).
    hard 게이트(credential/host/rate) 발생 시 나머지 variant 는 not_run(불필요 호출 0). 출력은 aggregate-only·
    메커니즘 가설+confidence(단정 0). transport 주입 시 결정론(network 0·key 불요).

    pace_seconds>0 이면 live 시 variant 호출 전 그만큼 **사전 대기**(host min_spacing 을 bypass 가 아니라 정직히 준수
    — shared gate 의 host_min_spacing_not_elapsed 로 variant 가 줄줄이 막혀 메커니즘 분해가 무산되는 것을 방지·no
    tight retry). sleep_fn 주입 시 결정론(테스트는 실제 sleep 0). 기본 0=현행(테스트·offline)."""
    start = target.get("start_date")
    end = target.get("end_date")
    today = target.get("as_of_anchor")
    tw = target.get("time_window") or "1d"
    query_tokens = _qtokens(target.get("query_text"))

    variant_results: list[dict] = []
    gated_reason: Optional[str] = None
    if not live_query:
        variant_results = [_not_run_row(v, "not_opted_in") for v in variants]
    else:
        stopped = False
        _sleep = sleep_fn or time.sleep
        for i, v in enumerate(variants):
            if stopped:
                variant_results.append(_not_run_row(v, gated_reason or "skipped_after_gate"))
                continue
            if pace_seconds > 0 and i > 0:
                _sleep(pace_seconds)   # host min_spacing 사전 대기(gate bypass 아님·정직 준수·no tight retry).
            args = _variant_args(v, target)
            qr = run_provider_query(
                provider, time_window=tw, today=today, transport=transport,
                env_status_fn=env_status_fn, host_gate=host_gate, **args)
            agg = _aggregate_variant(v, qr, start_date=start, end_date=end,
                                     query_tokens=query_tokens, enforce=args["enforce_window"])
            variant_results.append(agg)
            if agg["result_class"] == RC_GATED:
                gated_reason = gated_reason or agg["block_reason"]
                if qr.status in _HARD_GATE_STATUSES:
                    stopped = True   # 이후 variant 도 동일 게이트 → 중단.

    executed = any(r["status"] != "not_run" for r in variant_results)
    non_enforce = [r for r in variant_results if r["variant"] != V_ENFORCE and _ran(r)]
    in_window_records_found = max((r["in_window_count"] for r in non_enforce), default=0)
    out_of_window_records_dropped = max((r["out_of_window_count"] for r in non_enforce), default=0)
    any_records = any(r["records_returned"] > 0 for r in non_enforce)
    no_in_window_records = bool(executed and any_records and in_window_records_found == 0)
    classification = _classify_mechanism(variant_results)

    return {
        "operation_name": OPERATION_NAME,
        "provider": provider,
        "date_window": [start, end],
        "live_query_executed": executed,
        "control_experiment_variants": [r["variant"] for r in variant_results],
        "control_experiment_variants_count": len([r for r in variant_results if _ran(r)]),
        "variant_results": variant_results,            # aggregate-only(제목 전문·raw body 미노출).
        "provider_date_window_status": _provider_window_status(variant_results),
        "in_window_records_found": in_window_records_found,
        "out_of_window_records_dropped": out_of_window_records_dropped,
        "no_in_window_records": no_in_window_records,
        "gated_reason": gated_reason,
        **classification,
        # 경계(정직·constant).
        "raw_source_body_exposed": False,
        "secret_value_exposed": False,
        "same_event_truth_exposed": False,
        "per_pair_score_exposed": False,
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#85 provider date-window fidelity control experiment (merge 0·LLM 0·secret 0; 기본 호출 0·"
                     "--live-query 로 opt-in bounded governed variant fetch·aggregate-only·값 미노출)."))
    parser.add_argument("--named-entity", default="", help="operator named entity.")
    parser.add_argument("--event-phrase", default="", help="operator event 행위.")
    parser.add_argument("--occurrence-date", default="", help="발생일 ISO YYYY-MM-DD(operator 확인).")
    parser.add_argument("--provider", default="guardian", help="probe 대상 provider(기본 guardian).")
    parser.add_argument("--live-query", action="store_true",
                        help="실 governed variant fetch opt-in(network·CI 아님·credential 필요·값 미노출).")
    parser.add_argument("--pace-seconds", type=float, default=0.0,
                        help="variant 호출 전 사전 대기(s·host floor 정직 준수·gate bypass 아님; guardian≥6·nyt≥13 권장). "
                             "0 이면 host_min_spacing 으로 variant 가 줄줄이 막혀 분해 무산 가능(R-ControlExperimentRateBudget).")
    parser.add_argument("--json", action="store_true", help="full probe report JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    from backend.app.tools.live_query_target import build_live_query_target
    operator_event = None
    if ns.named_entity or ns.event_phrase or ns.occurrence_date:
        operator_event = {"named_entity": ns.named_entity, "event_phrase": ns.event_phrase,
                          "occurrence_date": ns.occurrence_date}
    target = build_live_query_target(operator_event)

    host_gate = None
    if ns.live_query:
        try:
            from pathlib import Path as _P

            from ingestion.orchestration.host_rate_gate import HostRateGate
            host_gate = HostRateGate(state_path=_P("ingestion/outputs/state/host_rate_gate.json"))
        except Exception:
            host_gate = None

    out = run_date_window_fidelity_probe(
        target, provider=ns.provider, live_query=ns.live_query, host_gate=host_gate,
        pace_seconds=ns.pace_seconds)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} provider={out['provider']} window={out['date_window']}")
    print(f"- executed={out['live_query_executed']} provider_status={out['provider_date_window_status']}")
    for r in out["variant_results"]:
        print(f"    {r['variant']:<16} status={r['status']:<18} class={r['result_class']:<20} "
              f"in={r['in_window_count']} out={r['out_of_window_count']} "
              f"date=[{r['returned_date_min']},{r['returned_date_max']}] ov={r['query_token_overlap_max']}")
    print(f"- effects: date_param={out['date_param_effect']} order_newest={out['order_by_newest_effect']} "
          f"query={out['query_relevance_effect']} coverage={out['in_window_coverage_effect']}")
    print(f"- mechanism: primary={out['mechanism_primary_hypothesis']} confidence={out['mechanism_confidence']}")
    for h in out["date_filter_mechanism_hypotheses"]:
        print(f"    hyp={h['hypothesis']} conf={h['confidence']} :: {h['signal']}")
    print(f"- in_window_found={out['in_window_records_found']} out_dropped={out['out_of_window_records_dropped']} "
          f"no_in_window_records={out['no_in_window_records']} gated={out['gated_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

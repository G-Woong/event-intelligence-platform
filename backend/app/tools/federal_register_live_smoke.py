"""ADR#86 — Federal Register bounded live smoke (key-free·governed·raw body 0·merge 0·LLM 0·DB 0·secret 0).

ADR#84/#85 가 입증한 핵심: 검색 API 가 from-date/to-date 를 URL 에 정확히 받고도 응답이 그 window 를 무시할 수
있다(Guardian/NYT: date_filter_ignored leading). ADR#86 은 그 hedge 로 **명시적 publication_date[gte/lte] 범위 필터**를
문서화한 official source(Federal Register)를 배선했다 — 그러나 *문서 지원 ≠ 응답 제약* 이므로 이 모듈이 bounded
live smoke 로 **실제 date-honoring 을 검증**한다(이번 턴 핵심·option C).

이 smoke 는 **단일 official source** 쿼리다(news 페어링 아님). 반환된 record 의 published_at 을 pinned window 에
대조해:
  - 전부 in-window → date_filter live_verified(FR 이 실제로 window 를 존중),
  - 일부 out-of-window → live_weak(문서 spec 에도 불구 응답 미제약 — Guardian/NYT 와 같은 증상),
  - records 0 → live_no_records(검증 불가·broaden).
이 결과는 ADR#85 의 date_filter_ignored vs zero_in_window_coverage 를 **window-honoring control 로 부분 분리**한다:
FR 이 같은 window 에서 in-window official record 를 반환하면, 적어도 그 window 에 in-window 보도(공식)가 *존재* 한다는
뜻이라 Guardian/NYT 0 in-window 가 "전역 zero coverage" 가 아니라 "(news 측) date_filter_ignored" 쪽임을 강화한다
(단 FR=regulatory 도메인 ≠ news 도메인이라 직접 증명 아닌 보강 신호로만·정직).

정직한 한계(adversarial M-2): 이 smoke 는 **date 필터 1회 호출**(enforce_window=False 로 raw 수신)의 in-window 비율로
live_verified/live_weak 를 도출한다. "필터가 응답을 제약한다"의 **결정적 with/without-date 대조**(omit_date_window 유/무
동일 쿼리 비교)는 in-harness 산출이 아니라 수동 관찰이다(asylum metering 31→0 은 scratchpad·다른 topic). 단 *과거*
window 의 newest-order 25/25 in-window 자체가 강한 정황(필터 무시 시 today 기사가 반환돼야 함)이다. omit_date_window
knob 은 어댑터에 있어 향후 paired-variant 를 in-harness 로 추가 가능(이연).

경계(불변): raw body 미저장(title+canonical+published 만)·secret 0(key-free·애초에 키 없음)·host/rate governed
(no-bypass)·snapshot aggregate-only·same_event 단정 0·merge 0·public IU 0. transport 주입 시 결정론(network 0)."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Optional

from backend.app.tools.provider_query_adapters import run_provider_query

OPERATION_NAME = "federal_register_live_smoke"
PROVIDER = "federal_register"

# ── §10 status 어휘 ────────────────────────────────────────────────────────────────────────────────────────
FR_LIVE_NOT_RUN = "fr_live_not_run"
FR_LIVE_OK_IN_WINDOW = "fr_live_ok_in_window"
FR_LIVE_OK_NO_RECORDS = "fr_live_ok_no_records"
FR_LIVE_OUT_OF_WINDOW = "fr_live_out_of_window"
FR_LIVE_PARSE_ERROR = "fr_live_parse_error"
FR_LIVE_HTTP_ERROR = "fr_live_http_error"
FR_LIVE_RATE_BLOCKED = "fr_live_rate_blocked"

# ── date_filter_capability(documented → live 전환) ─────────────────────────────────────────────────────────
DFC_DOCUMENTED_UNVERIFIED = "documented_unverified"   # 미실행(문서 근거만).
DFC_LIVE_VERIFIED = "live_verified"                   # records 반환 ∧ 전부 in-window.
DFC_LIVE_WEAK = "live_weak"                           # records 반환 ∧ 일부 out-of-window(응답 미제약).
DFC_LIVE_NO_RECORDS = "live_no_records"               # records 0 — 검증 불가.


def _date_in_window(pub: Optional[str], window: tuple[str, str]) -> bool:
    """published_at(YYYY-MM-DD)가 [start, end] 안인가(ISO 사전식=날짜 비교). 없음/형식불명/범위밖=False."""
    if not pub or len(pub) < 10:
        return False
    return window[0] <= pub[:10] <= window[1]


def _classify(*, qstatus: str, records: list[dict], window: tuple[str, str]) -> tuple[str, str, int, int]:
    """run_provider_query 결과 → (fr_live_status, date_filter_capability, in_window, out_of_window).

    enforce_window=False 로 raw 를 받아 직접 분류(필터가 실제로 작동했는지 보려면 raw 응답이 필요). status==ok 면
    in/out 카운트로 live_verified vs live_weak; no_records 면 no_records; 그 외(parser/rate/network)는 각 status."""
    if qstatus in ("rate_limited", "host_gate_blocked"):
        # host/rate gate 차단 = governance event(실 network 0) — empty result(no_records)로 둔갑 금지(code-review NIT-1).
        return FR_LIVE_RATE_BLOCKED, DFC_DOCUMENTED_UNVERIFIED, 0, 0
    if qstatus == "parser_error":
        return FR_LIVE_PARSE_ERROR, DFC_DOCUMENTED_UNVERIFIED, 0, 0
    if qstatus == "network_error":
        return FR_LIVE_HTTP_ERROR, DFC_DOCUMENTED_UNVERIFIED, 0, 0
    if qstatus == "no_records" or not records:
        return FR_LIVE_OK_NO_RECORDS, DFC_LIVE_NO_RECORDS, 0, 0
    in_window = sum(1 for r in records if _date_in_window(r.get("published_at_or_observed_at"), window))
    out_window = len(records) - in_window
    if out_window == 0:
        return FR_LIVE_OK_IN_WINDOW, DFC_LIVE_VERIFIED, in_window, out_window
    if in_window == 0:
        return FR_LIVE_OUT_OF_WINDOW, DFC_LIVE_WEAK, in_window, out_window
    # 혼재(일부 in·일부 out) — 필터가 부분적으로만 작동 → live_weak(정직).
    return FR_LIVE_OUT_OF_WINDOW, DFC_LIVE_WEAK, in_window, out_window


def run_federal_register_live_smoke(
    *, topic: str, date_window: tuple[str, str], today: Optional[str] = None,
    time_window: str = "1d", live_query: bool = False, max_records: Optional[int] = None,
    transport: Optional[Callable[[str], Optional[str]]] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    host_gate: Any = None,
) -> dict:
    """Federal Register bounded live smoke(§10). 기본 live_query=False → 시도 0(fr_live_not_run·network 0).

    live_query=True 일 때만 단일 governed FR 쿼리(enforce_window=False 로 raw 수신 → window 직접 대조). key-free 라
    credential gate 0. host/rate governed. raw body 미저장(title+canonical+published 만)·secret 0. records 는
    official×news bridge 입력으로 반환(record_type=official_record). transport 주입 시 결정론(network 0).

    today 미주입 시 date_window[1](end=D+1)을 anchor 로 사용 — run_provider_query 가 [D, D+1] 범위 필터를 구성."""
    anchor = today or date_window[1]
    if not live_query:
        return _result(
            status=FR_LIVE_NOT_RUN, date_filter_capability=DFC_DOCUMENTED_UNVERIFIED, records=[],
            in_window=0, out_window=0, topic=topic, date_window=date_window,
            block_reason="not_opted_in",
            next_action="rerun with live_query=True (bounded·key-free·host/rate governed·raw body 0)")

    qr = run_provider_query(
        PROVIDER, topic=topic, time_window=time_window, today=anchor, max_records=max_records,
        enforce_window=False,   # raw 수신 — 필터가 실제 작동했는지 보려면 응답 원형이 필요(직접 in/out 분류).
        transport=transport, env_status_fn=env_status_fn, host_gate=host_gate)
    records = list(qr.records)
    status, dfc, in_w, out_w = _classify(qstatus=qr.status, records=records, window=date_window)
    block_reason = None if status in (FR_LIVE_OK_IN_WINDOW,) else _status_block(status, qr)
    gate_blocked = qr.status == "host_gate_blocked"
    return _result(
        status=status, date_filter_capability=dfc, records=records, in_window=in_w, out_window=out_w,
        topic=topic, date_window=date_window, block_reason=block_reason,
        next_action=_next_action(status),
        live_call_count=0 if gate_blocked else 1,   # gate 차단=실 network 0(code-review NIT-1·live 회계 둔갑 금지).
        host_gate_blocked=gate_blocked)


def _status_block(status: str, qr: Any) -> str:
    return {
        FR_LIVE_OK_NO_RECORDS: "fr_no_records",
        FR_LIVE_OUT_OF_WINDOW: "fr_returned_out_of_window_records",
        FR_LIVE_PARSE_ERROR: "fr_parser_error",
        FR_LIVE_HTTP_ERROR: "fr_http_error",
        FR_LIVE_RATE_BLOCKED: "fr_rate_blocked",
    }.get(status, qr.block_reason or status)


def _next_action(status: str) -> str:
    return {
        FR_LIVE_OK_IN_WINDOW: ("FR honored the pinned window — feed official records to official_news_role_bridge "
                               "against in-window news (bridge is reviewer-routing only · not same-event truth)"),
        FR_LIVE_OK_NO_RECORDS: "broaden the FR topic/window or pin a regulatory-class event with FR coverage",
        FR_LIVE_OUT_OF_WINDOW: ("FR returned out-of-window records despite the explicit publication_date[gte/lte] "
                                "filter — date_filter live_weak (same symptom class as Guardian/NYT); do not freeze "
                                "out-of-window official records"),
        FR_LIVE_PARSE_ERROR: "inspect FR response shape (no secret in logs)",
        FR_LIVE_HTTP_ERROR: "retry later (transient FR network)",
        FR_LIVE_RATE_BLOCKED: "respect FR rate/host floor (no-bypass)",
        FR_LIVE_NOT_RUN: "opt in to the bounded FR live smoke",
    }.get(status, "investigate FR live smoke")


def _result(
    *, status: str, date_filter_capability: str, records: list[dict], in_window: int, out_window: int,
    topic: str, date_window: tuple[str, str], block_reason: Optional[str], next_action: str,
    live_call_count: int = 0, host_gate_blocked: bool = False,
) -> dict:
    """aggregate + records(bridge 입력) 산출. snapshot 은 aggregate 만 소비(records/title 미포함)."""
    return {
        "operation_name": OPERATION_NAME,
        "provider": PROVIDER,
        "fr_live_status": status,
        "date_filter_capability": date_filter_capability,
        "live_query_executed": bool(live_call_count),
        "live_call_count": live_call_count,
        "topic": topic,
        "date_window": list(date_window),
        "records_returned": len(records),
        "in_window_records": in_window,
        "out_of_window_records": out_window,
        # official record(record_type=official_record) — official_news_role_bridge 입력. snapshot 미포함(aggregate only).
        "official_records": records,
        "host_gate_blocked": host_gate_blocked,
        "block_reason": block_reason,
        "next_action": next_action,
        # ── 불변 경계 ──
        "raw_body_stored": False,
        "secret_exposed": False,
        "credential_required": False,   # key-free.
        "merge_allowed": False,
        "llm_invoked": False,
        "db_write": False,
        "public_iu_allowed": False,
        "same_event_asserted": False,
    }


def sanitized_fr_live(out: dict) -> dict:
    """snapshot/frontier 용 aggregate-only 투영(official_records/raw title 제외·count 만)."""
    return {
        "fr_live_status": out["fr_live_status"],
        "date_filter_capability": out["date_filter_capability"],
        "live_query_executed": out["live_query_executed"],
        "records_returned": out["records_returned"],
        "in_window_records": out["in_window_records"],
        "out_of_window_records": out["out_of_window_records"],
        "block_reason": out["block_reason"] or "",
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#86 Federal Register bounded live smoke (key-free·governed·raw body 0·merge 0; 기본 시도 0·"
                     "--live-query 로 opt-in 단일 official 쿼리·date-honoring 검증)."))
    parser.add_argument("--topic", required=True, help="FR conditions[term] 검색어(operator event subject).")
    parser.add_argument("--start-date", required=True, help="pinned window start ISO(D).")
    parser.add_argument("--end-date", required=True, help="pinned window end ISO(D+1).")
    parser.add_argument("--live-query", action="store_true", help="opt-in bounded FR live fetch(network·key 불요).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(official_records 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    host_gate = None
    if ns.live_query:
        try:
            from pathlib import Path as _P

            from ingestion.orchestration.host_rate_gate import HostRateGate
            host_gate = HostRateGate(state_path=_P("ingestion/outputs/state/host_rate_gate.json"))
        except Exception:
            host_gate = None

    out = run_federal_register_live_smoke(
        topic=ns.topic, date_window=(ns.start_date, ns.end_date), today=ns.end_date,
        live_query=ns.live_query, host_gate=host_gate)
    agg = sanitized_fr_live(out)
    if ns.json:
        print(json.dumps(agg, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} provider={out['provider']}")
    print(f"- fr_live_status={agg['fr_live_status']} date_filter_capability={agg['date_filter_capability']} "
          f"executed={agg['live_query_executed']}")
    print(f"- records_returned={agg['records_returned']} in_window={agg['in_window_records']} "
          f"out_of_window={agg['out_of_window_records']}")
    print(f"- block_reason={agg['block_reason'] or '(none)'}")
    print(f"- next_action={out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

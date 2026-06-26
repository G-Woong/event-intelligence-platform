"""ADR#64 — cross-source live overlap smoke (2nd publishable provider + cross-source near-match queue).

ADR#63 가 실 key 로 입증한 한계: Guardian **단일 source** same-event overlap 0(no_title_overlap·구조적 — 단일
매체는 같은 사건을 1회/다른 제목으로 보도). 다음 hard blocker 는 cross-source — Guardian 과 같은 영문 quality 단일
publisher(NYT·ADR#64 wired)를 붙여 **다출처가 같은 사건을 보도**할 때 비로소 cross-source near-match 후보가 생긴다.

이 모듈은 **얇은 composition layer** 다(재구현 0):
  - fetch/parse: ADR#62 `run_provider_query`(guardian·nyt adapter·secret-safe).
  - overlap 분해: ADR#57 `discover_overlap`(fingerprint vs near vs hard band·pair_matrix 로 source-pair 식별).
  - reviewer queue: ADR#59 `build_near_match_reviewer_queue`/`build_gold_seed_report`(predicted_status 숨김·validate fail-loud).
추가하는 것은 ① §4 cross-source smoke 출력 계약, ② **양 provider 동시 성공만 cross-source 인정**(single-source 둔갑
금지), ③ near/hard pair 를 **cross-source(source_id 상이)만** 필터해 queue 충원(same-source 오염 구조적 차단)이다.

경계(불변·상속 — 상용 안전 계약):
  - **secret 값 0**: credential 은 `probe_env_var`(present/missing + `.env` Path.exists + `.env.example` 이름 — 전부
    값 미열람)로만 확인. API key 값은 ADR#62 adapter 내부 `os.getenv` 가 실 network 경로에서만 읽어 httpx params 로
    전달(url keyless·로그/result/report 미기록). `credential_value_exposed=False`·`env_file_read=False` 불변.
  - **opt-in only**: 기본 live_query=False → 시도 0(not_opted_in). CI 금지(network/key/rate-limit 의존 → flaky).
  - **cross-source 진정성**: provider_a(guardian)만 성공·provider_b 실패면 single-source success 로 포장 금지
    (no_records_provider_b 등 정직 노출). 둘 다 성공·overlap 0 이면 no_cross_source_overlap/no_title_overlap/
    no_near_match 로 분해. fixture 둔갑 0(dataset_source 는 실 records 일 때만 live_derived).
  - **no merge·no LLM·no DB write·no public IU**: records 는 reviewer queue 충원까지만. 같은 사건 단정은 gold/MERGE_GATE 전까지 0.
  - **source role guard**: publishable×publishable(article)만 near-match 후보. community/market/catalog anchor 금지(discover 가 강제).
  test: transport_a/transport_b(fake)+env_probe_fn 주입 시 결정론(network 0·실 `.env` 미접촉·key 불요).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Optional

from backend.app.tools.near_match_reviewer_queue import (
    build_gold_seed_report,
    build_near_match_reviewer_queue,
)
from backend.app.tools.provider_query_adapters import (
    ADAPTER_WIRED_PROVIDERS,
    GUARDIAN_ADAPTER,
    NYT_ADAPTER,
    run_provider_query,
)
from backend.app.tools.source_overlap_discovery import discover_overlap

_SMOKE_NAME = "cross_source_live_overlap"
_PROVIDER_A = "guardian"
_DEFAULT_PROVIDER_B = "nyt"

# provider_id → adapter(env var 이름 조회용·secret 0). 신규 adapter wiring 시 여기 등재.
_ADAPTER_BY_PROVIDER = {"guardian": GUARDIAN_ADAPTER, "nyt": NYT_ADAPTER}


def _default_env_probe(var_name: str) -> dict:
    """secret-safe env probe(없으면 fail-closed: present 추측 금지 — 미설정·파일부재로 간주)."""
    try:
        from ingestion.core.env_loader import probe_env_var
        return probe_env_var(var_name)
    except Exception:
        return {"var_name": var_name, "credential_present": False,
                "env_file_present": False, "declared_in_example": False}


def _cred_state(probe: dict) -> str:
    """probe → credential 상태(secret 0). present / missing_credentials(.env 있음·키 없음) / env_not_loaded(.env 부재)."""
    if probe.get("credential_present"):
        return "present"
    return "missing_credentials" if probe.get("env_file_present") else "env_not_loaded"


# adapter ProviderQueryResult.status → smoke block reason 정규화(ok 는 호출부에서 제외).
_QSTATUS_BLOCK = {
    "missing_credentials": "missing_credentials",
    "host_gate_blocked": "host_gate_blocked",
    "rate_limited": "rate_limited",
    "network_error": "network_error",
    "parser_error": "parser_error",
    "fetcher_not_wired": "fetcher_not_wired",
}

_NEXT_ACTION = {
    "not_opted_in": "rerun with --live-query (explicit opt-in; network·CI 아님)",
    # colonless missing_credentials(=run_provider_query 내부 env_status 가 probe 와 불일치한 드문 경로) 도
    # 구체 안내(code-review LOW: 'investigate:' fallthrough 방지). per-provider 형식은 위 colon 분기가 처리.
    "missing_credentials": "set the provider env var in .env (secret 커밋 금지; provider internal credential check failed)",
    "provider_b_not_selected": "select a wired publishable provider_b (see ADAPTER_WIRED_PROVIDERS·현재 guardian/nyt)",
    "no_cross_source_overlap": "broaden window/topic — publishable cross-source same-date pair 부재(두 매체 보도 시점 분산)",
    "no_title_overlap": ("cross-source pair 는 있으나 제목 token overlap < floor — embedding/LLM adjudicator(deferred·"
                         "paraphrase 영역) 또는 topic/window 확대"),
    "no_near_match": "cross-source 가 hard-negative/fingerprint 만·near-positive 0 — adjudicator-zone overlap 위해 topic 확대",
    "no_records_provider_a": "broaden topic/time_window for provider_a (returned 0 records)",
    "no_records_provider_b": "broaden topic/time_window for provider_b (returned 0 records)",
    "host_gate_blocked": "respect shared host floor (no-bypass); retry after min_spacing",
    "rate_limited": "respect provider cooldown (no tight retry)",
    "network_error": "retry later (transient network)",
    "parser_error": "inspect provider response shape (no secret in logs)",
    "fetcher_not_wired": "provider adapter not wired (ADR#62/#64 scope)",
}


def _next_action_for(reason: str, env_var_by_provider: dict) -> str:
    """block reason → 다음 행동(secret 값 0·env var 이름만). per-provider credential 은 'state:provider' 형식."""
    if ":" in reason:
        state, _, prov = reason.partition(":")
        env_var = env_var_by_provider.get(prov, "<ENV>")
        if state == "missing_credentials":
            return f"set {env_var}=<key> in .env (secret 커밋 금지) — provider_b={prov}"
        if state == "env_not_loaded":
            return (f"create .env at repo root from .env.example and set {env_var}=<key> "
                    f"(.env 는 커밋 금지) — provider={prov}")
    return _NEXT_ACTION.get(reason, f"investigate: {reason}")


def _is_cross_source(pair: dict) -> bool:
    """near/hard pair 가 cross-source 인가(source_id 상이). discover 가 sorted source_id 로 left/right 부여."""
    return bool(pair.get("source_id_left")) and pair.get("source_id_left") != pair.get("source_id_right")


def _cross_source_stats(disc: dict) -> dict:
    """overlap_potential_matrix 에서 cross-source(서로 다른 source) row 만 합산 → pair/fingerprint 카운트.

    matrix row 의 same_date_pairs 는 **publishable·cross-URL·same-date** pair 수(discover 가 그 필터 통과분만 slot 생성).
    cross row = source_pair[0] != source_pair[1](guardian↔nyt). near/hard 는 호출부가 filtered pair 리스트로 직접 계수."""
    matrix = disc.get("overlap_potential_matrix") or []
    pair = fp = 0
    for m in matrix:
        sp = m.get("source_pair") or []
        if len(sp) == 2 and sp[0] != sp[1]:
            pair += m.get("same_date_pairs", 0)
            fp += m.get("fingerprint_overlap", 0)
    return {"cross_source_pair_count": pair, "cross_fingerprint": fp}


def run_cross_source_live_overlap_smoke(
    *, provider_b: str = _DEFAULT_PROVIDER_B,
    topic: str = "central bank rate decision", topic_key: str = "central_bank_rate",
    time_window: str = "1d", live_query: bool = False,
    transport_a: Optional[Callable[[str], Optional[str]]] = None,
    transport_b: Optional[Callable[[str], Optional[str]]] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    env_probe_fn: Optional[Callable[[str], dict]] = None,
    host_gate: Any = None, reviewers: Optional[list[str]] = None,
    packet_id: str = "cross_source_near_match_pkt",
) -> dict:
    """opt-in secret-safe cross-source live overlap smoke(§4 계약). 기본 live_query=False → 시도 0.

    gate(fail-closed): opt-in 아님→not_opted_in; provider_b 미배선→provider_b_not_selected; 각 provider credential
    부재→env_not_loaded(.env 부재)/missing_credentials(키 부재)(network 전·값 미열람); **둘 다 present + opt-in** 일
    때만 양 provider governed fetch → 둘 다 ok 면 combined records 를 discover→cross-source 필터→near-match queue 로
    연결. 한쪽만 ok 면 cross-source 미인정(정직 block). 병합·LLM·DB write·public IU 0.

    test: transport_a/transport_b(fake)+env_probe_fn 주입 시 결정론(network 0·실 `.env` 미접촉·key 불요)."""
    provider_a = _PROVIDER_A
    probe = env_probe_fn or _default_env_probe
    adapter_a = _ADAPTER_BY_PROVIDER.get(provider_a)
    adapter_b = _ADAPTER_BY_PROVIDER.get(provider_b)
    env_var_a = adapter_a.required_env_vars[0]
    env_var_b = adapter_b.required_env_vars[0] if adapter_b else None
    env_var_by_provider = {provider_a: env_var_a}
    if env_var_b:
        env_var_by_provider[provider_b] = env_var_b

    block_reasons: list[str] = []
    credential_status: dict[str, str] = {}
    provider_status: dict[str, str] = {}
    host_gate_status: dict[str, str] = {}
    rate_limit_status: dict[str, str] = {}
    records_count: dict[str, int] = {}
    dataset_source_by_provider: dict[str, Optional[str]] = {}
    combined_records: list[dict] = []
    cross_pair = cross_near = cross_hard = cross_fp = 0
    queue_pop = 0
    dataset_source: Optional[str] = None
    labeler_prediction_hidden = True
    live_query_attempted = False

    # ── gate ──
    if not live_query:
        block_reasons.append("not_opted_in")
    elif adapter_b is None or provider_b not in ADAPTER_WIRED_PROVIDERS:
        block_reasons.append("provider_b_not_selected")
    else:
        # per-provider secret-safe credential probe(network 전·값 미열람). 둘 다 검사해 누락분 한 번에 안내.
        sa = _cred_state(probe(env_var_a))
        sb = _cred_state(probe(env_var_b))
        credential_status = {provider_a: sa, provider_b: sb}
        if sa != "present":
            block_reasons.append(f"{sa}:{provider_a}")
        if sb != "present":
            block_reasons.append(f"{sb}:{provider_b}")

        if sa == "present" and sb == "present":
            qa = run_provider_query(provider_a, topic=topic, time_window=time_window,
                                    transport=transport_a, env_status_fn=env_status_fn, host_gate=host_gate)
            qb = run_provider_query(provider_b, topic=topic, time_window=time_window,
                                    transport=transport_b, env_status_fn=env_status_fn, host_gate=host_gate)
            provider_status = {provider_a: qa.status, provider_b: qb.status}
            records_count = {provider_a: qa.records_count, provider_b: qb.records_count}
            for prov, q in ((provider_a, qa), (provider_b, qb)):
                host_gate_status[prov] = "blocked" if q.status == "host_gate_blocked" else "passed"
                rate_limit_status[prov] = "rate_limited" if q.status == "rate_limited" else "ok"
                dataset_source_by_provider[prov] = "live_derived" if q.status == "ok" else None
            # cross-source 는 **둘 다 ok** 만 인정(single-source 둔갑 금지). 한쪽 실패는 provider 접미사로 정직 노출.
            if qa.status != "ok":
                block_reasons.append("no_records_provider_a" if qa.status == "no_records"
                                     else _QSTATUS_BLOCK.get(qa.status, qa.status))
            if qb.status != "ok":
                block_reasons.append("no_records_provider_b" if qb.status == "no_records"
                                     else _QSTATUS_BLOCK.get(qb.status, qb.status))

            if qa.status == "ok" and qb.status == "ok":
                live_query_attempted = True
                combined_records = list(qa.records) + list(qb.records)
                dataset_source = "live_derived"   # 실 records — fixture 둔갑 0(records 0/실패면 None 유지).
                disc = discover_overlap(
                    combined_records, discovery_mode="cross_source_live", real_fetch=True)
                stats = _cross_source_stats(disc)
                cross_pair, cross_fp = stats["cross_source_pair_count"], stats["cross_fingerprint"]
                # near/hard pair 를 **cross-source(source_id 상이)만** 남긴 discovery 로 queue 충원
                # (same-source guardian↔guardian/nyt↔nyt pair 제외 — cross-source 진정성). real_fetch 보존=live_derived.
                cross_disc = dict(disc)
                cross_disc["near_match_pairs"] = [
                    p for p in (disc.get("near_match_pairs") or []) if _is_cross_source(p)]
                cross_disc["hard_negative_pairs"] = [
                    p for p in (disc.get("hard_negative_pairs") or []) if _is_cross_source(p)]
                # scalar fingerprint/near 카운트도 cross-source 기준으로 재설정(adversarial MEDIUM-1: gold_seed 등
                # cross_disc 소비자가 same-source fingerprint 를 cross-source 통계로 오인하지 않게 출처 통일).
                cross_disc["fingerprint_overlap_pairs"] = cross_fp
                cross_disc["near_match_below_fingerprint_pairs"] = len(cross_disc["near_match_pairs"])
                queue = build_near_match_reviewer_queue(
                    cross_disc, packet_id=packet_id, reviewers=reviewers)
                gold_seed = build_gold_seed_report(cross_disc, queue)
                cross_near = queue["near_positive_count"]
                cross_hard = queue["hard_negative_discovery_count"]
                queue_pop = len(queue.get("queue_pair_ids") or [])
                labeler_prediction_hidden = bool(gold_seed["labeler_prediction_hidden"])
                # cross-source candidate 0 분해(정직 — source scarcity 를 모델 실패로 뭉뚱그리지 않음).
                if cross_pair == 0:
                    block_reasons.append("no_cross_source_overlap")
                elif (cross_near + cross_hard + cross_fp) == 0:
                    block_reasons.append("no_title_overlap")
                elif cross_near == 0:
                    block_reasons.append("no_near_match")

    next_actions = [_next_action_for(br, env_var_by_provider) for br in block_reasons]
    return {
        "smoke_name": _SMOKE_NAME,
        "providers": [provider_a, provider_b],
        "provider_a": provider_a,
        "provider_b": provider_b,
        "topic": topic,
        "time_window": time_window,
        "live_query_requested": bool(live_query),
        "live_query_attempted": live_query_attempted,
        "credential_status_by_provider": credential_status,
        "credential_value_exposed": False,   # 불변 — key 값 미열람·미기록.
        # 불변 — `.env` **값을 report/log 로 미노출**(직접 cat/파싱 0). 파일 I/O 부재가 아니라 값 미노출의 뜻:
        # env_loader 는 present/missing 판정 위해 `.env` 를 os.environ 에 적재하나 **값을 caller 로 미반환**.
        "env_file_read": False,
        "provider_status_by_provider": provider_status,
        "host_gate_status_by_provider": host_gate_status,
        "rate_limit_status_by_provider": rate_limit_status,
        "records_count_by_provider": records_count,
        "combined_records_count": len(combined_records),
        "cross_source_pair_count": cross_pair,
        "fingerprint_overlap_count": cross_fp,
        "near_match_count": cross_near,
        "hard_negative_count": cross_hard,
        "reviewer_queue_population_count": queue_pop,
        "labeler_prediction_hidden": labeler_prediction_hidden,
        "dataset_source_by_provider": dataset_source_by_provider,
        "dataset_source": dataset_source,
        "provenance": dataset_source or "none",   # cross-source 후보/records 0이면 fixture 둔갑 금지 — provenance 없음.
        "block_reasons": block_reasons,
        "next_actions": next_actions,
        "production_gold_count": 0,
        "merge_allowed": False,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "llm_invoked": False,
        "db_write": False,
    }


# ── CLI(기본 시도 0·network 0; --live-query 로 opt-in bounded governed cross-source fetch·값 미노출) ──────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#64 cross-source live overlap smoke (병합 0·LLM 0·DB write 0; 기본 시도 0·network 0; "
                     "--live-query 로 opt-in guardian+provider_b bounded governed fetch·key 값 미노출)."))
    parser.add_argument("--provider-b", default=_DEFAULT_PROVIDER_B,
                        help="2nd publishable provider(기본 nyt). provider_a 는 guardian 고정.")
    parser.add_argument("--topic", default="central bank rate decision", help="targeted topic(수집 의도).")
    parser.add_argument("--time-window", default="1d", help="time window(1d/7d).")
    parser.add_argument("--live-query", action="store_true",
                        help="실 governed fetch opt-in(network·CI 아님). 양 provider credential 필요. key 값 미노출.")
    parser.add_argument("--json", action="store_true", help="§4 smoke report 를 JSON 으로 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    host_gate = None
    if ns.live_query:
        # shared host gate 주입 → cross-process host floor 참여(no-bypass). 실패해도 단발 best-effort.
        try:
            from pathlib import Path as _P

            from ingestion.orchestration.host_rate_gate import HostRateGate
            host_gate = HostRateGate(state_path=_P("ingestion/outputs/state/host_rate_gate.json"))
        except Exception:
            host_gate = None

    out = run_cross_source_live_overlap_smoke(
        provider_b=ns.provider_b, topic=ns.topic, time_window=ns.time_window,
        live_query=ns.live_query, host_gate=host_gate)

    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    # 사람 가독 요약 — credential 은 state(present/missing/env_not_loaded)만(값 절대 미출력).
    print(f"- smoke={out['smoke_name']} providers={out['providers']} "
          f"requested={out['live_query_requested']} attempted={out['live_query_attempted']}")
    print(f"- credential_status={out['credential_status_by_provider']} "
          f"value_exposed={out['credential_value_exposed']} env_file_read={out['env_file_read']}")
    print(f"- provider_status={out['provider_status_by_provider']} "
          f"host_gate={out['host_gate_status_by_provider']} rate_limit={out['rate_limit_status_by_provider']}")
    print(f"- records_by_provider={out['records_count_by_provider']} "
          f"combined={out['combined_records_count']} cross_source_pairs={out['cross_source_pair_count']}")
    print(f"- cross-source: fingerprint={out['fingerprint_overlap_count']} near={out['near_match_count']} "
          f"hard={out['hard_negative_count']} queue_pop={out['reviewer_queue_population_count']}")
    print(f"- dataset_source={out['dataset_source']} provenance={out['provenance']}")
    print(f"- block_reasons={out['block_reasons']}")
    print(f"- next_actions={out['next_actions']}")
    print(f"- production_gold={out['production_gold_count']} merge_allowed={out['merge_allowed']} "
          f"db_write={out['db_write']} llm_invoked={out['llm_invoked']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

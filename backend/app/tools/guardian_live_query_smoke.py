"""ADR#63 — secret-safe Guardian live query smoke + live-derived near-match queue population gate.

ADR#62 가 wire 한 Guardian adapter 의 **실 network 직전 마지막 경계**를 검증한다 — credential 이 secret-safe 하게
준비된 경우에만 bounded governed live query 를 opt-in 으로 수행하고, 산출 records 를 ADR#60 운영 경로
(discover→near-match reviewer/gold queue)로 연결한다. credential 이 없거나 `.env` 가 로드되지 않았으면 실패가
아니라 **env_not_loaded / missing_credentials / blocked_with_next_action** 으로 정직히 보고한다(fixture 둔갑 0).

이 모듈은 **얇은 composition layer** 다 — fetch/parse 는 ADR#62(`run_provider_query`), discover/queue 는 ADR#57/#59/#60
(`run_optional_live_query`)을 그대로 재사용한다(재구현 0). 추가하는 것은 ① §4 smoke 출력 계약, ② credential 부재
시 env_not_loaded vs missing_credentials 구분, ③ secret 경계 단언(값 미열람·미기록)이다.

경계(불변·상속):
  - **secret 값 0**: credential 은 `probe_env_var`(env_status present/missing + `.env` Path.exists + `.env.example`
    이름 선언 — **전부 값 미열람**)로만 확인. API key 값은 ADR#62 adapter 내부 `os.getenv` 가 실 network 경로에서만
    읽어 httpx params 로 전달(url keyless·로그/result/report 미기록). `credential_value_exposed=False`·`env_file_read=False` 불변.
  - **opt-in only**: 기본 live_query=False → 시도 0(not_opted_in). CI 금지(network/key/rate-limit 의존 → flaky).
  - **no merge·no LLM·no DB write·no public IU**: records 는 reviewer/gold queue 충원까지만. 같은 사건 단정은 gold/MERGE_GATE 전까지 0.
  - **fixture 둔갑 금지**: 실 fetch 0/실패면 status+block_reason 으로 정직 노출(synthetic 으로 떨어지지 않음).
    test 는 `provider_transport`(fake)·`env_probe_fn`(주입)으로 완전 hermetic(network 0·실 `.env` 미접촉).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Optional

from backend.app.tools.provider_query_adapters import GUARDIAN_ADAPTER
from backend.app.tools.provider_readiness import run_optional_live_query

_SMOKE_NAME = "guardian_live_query"
_PROVIDER = "guardian"


def _default_env_probe(var_name: str) -> dict:
    """secret-safe env probe(없으면 fail-closed: present 추측 금지 — 미설정·파일부재로 간주)."""
    try:
        from ingestion.core.env_loader import probe_env_var
        return probe_env_var(var_name)
    except Exception:
        return {"var_name": var_name, "credential_present": False,
                "env_file_present": False, "declared_in_example": False}


def _governance_status(block_reasons: list[str], *, engaged: bool) -> tuple[str, str]:
    """block_reasons → (host_gate_status, rate_limit_status) 정직 도출. 시도 전이면 not_attempted."""
    if not engaged:
        return "not_attempted", "not_attempted"
    host = "blocked" if "host_gate_blocked" in block_reasons else "passed"
    rate = ("rate_limited"
            if ("provider_rate_limited" in block_reasons or "rate_limited" in block_reasons)
            else "ok")
    return host, rate


def _next_action_for(reason: str, env_var: str) -> str:
    # no_title_overlap / no_candidate: 실 호출(Guardian 10 records×2 topic)에서 candidate 0 — 측정된 사실은
    # "같은 날 기사 쌍의 제목 Jaccard<near 임계" 이다(= 10건이 서로 다른 사건/측면; near-dup recall 한계도 포함).
    # 단일 소스 same-event overlap 이 이 토픽/윈도우에서 미관측 → cross-source(2nd provider) 가 실 unblock.
    return {
        "no_title_overlap": "add a second publishable provider for cross-source same-event overlap "
                            "(single-source same-event overlap not observed for this topic/window — ADR#63 live evidence)",
        "no_candidate": "broaden window or add a second publishable provider — no same-event overlap among fetched records",
        "no_near_match": "broaden topic/time_window or add a second publishable source for same-event overlap",
        "insufficient_records": "broaden topic/time_window (too few records for a same-event pair)",
        "no_query_capable_provider": "select a query-capable wired provider (see provider readiness)",
        "no_records": "broaden topic/time_window (provider returned 0 records)",
        "host_gate_blocked": "respect shared host floor (no-bypass); retry after min_spacing",
        "provider_rate_limited": "respect provider cooldown (no tight retry)",
        "rate_limited": "respect provider cooldown (no tight retry)",
        "network_error": "retry later (transient network)",
        "parser_error": "inspect provider response shape (no secret in logs)",
        "missing_credentials": f"set {env_var}=<key> in .env (secret 커밋 금지)",
        "fetcher_not_wired": "provider adapter not wired (ADR#62 scope)",
    }.get(reason, f"investigate: {reason}")


def run_guardian_live_query_smoke(
    *, topic: str = "central bank rate decision",
    topic_key: str = "central_bank_rate", time_window: str = "1d",
    live_query: bool = False,
    provider_transport: Optional[Callable[[str], Optional[str]]] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    env_probe_fn: Optional[Callable[[str], dict]] = None,
    host_gate: Any = None, reviewers: Optional[list[str]] = None,
    readiness: Optional[dict] = None,
) -> dict:
    """opt-in secret-safe Guardian live query smoke(§4 계약). 기본 live_query=False → 시도 0.

    gate(fail-closed): opt-in 아님→not_opted_in; credential 부재→`.env` 파일 부재면 env_not_loaded·있으면
    missing_credentials(둘 다 network 전·값 미열람); credential present + opt-in 일 때만 ADR#60 운영경로 위임
    (run_optional_live_query → fetch→discover→near-match queue). 병합·LLM·DB write·public IU 0.

    test: provider_transport(fake)+env_probe_fn 주입 시 결정론(network 0·실 `.env` 미접촉·key 불요)."""
    env_var = GUARDIAN_ADAPTER.required_env_vars[0]
    probe = (env_probe_fn or _default_env_probe)(env_var)
    credential_present = bool(probe.get("credential_present"))
    env_file_present = bool(probe.get("env_file_present"))
    env_example_checked = bool(probe.get("declared_in_example"))

    block_reasons: list[str] = []
    next_actions: list[str] = []
    live_query_attempted = False
    records_count = candidate_count = near = hard = fp = queue_pop = 0
    dataset_source: Optional[str] = None
    provider_status: Optional[str] = None
    engaged = False   # readiness gate 를 통과해 실 fetch 경로에 진입했는가(host/rate status 도출용).

    if not live_query:
        block_reasons.append("not_opted_in")
        next_actions.append("rerun with --live-query (explicit opt-in; network·CI 아님)")
    elif not credential_present:
        # network 전 차단 — env_not_loaded(.env 파일 부재) vs missing_credentials(키 미설정) 구분(§6 taxonomy).
        if not env_file_present:
            block_reasons.append("env_not_loaded")
            next_actions.append(
                f"create .env at repo root from .env.example and set {env_var}=<key> (.env 는 커밋 금지)")
        else:
            block_reasons.append("missing_credentials")
            next_actions.append(_next_action_for("missing_credentials", env_var))
    else:
        # credential present + opt-in → ADR#60 운영경로 위임(재구현 0). transport 주입 시 network 0.
        engaged = True
        live = run_optional_live_query(
            provider=_PROVIDER, topic=topic, topic_key=topic_key, time_window=time_window,
            live_query=True, readiness=readiness, env_status_fn=env_status_fn,
            provider_transport=provider_transport, host_gate=host_gate, reviewers=reviewers)
        live_query_attempted = bool(live["live_query_attempted"])
        lr = live.get("live_query_result") or {}
        records_count = lr.get("records_count", 0)
        candidate_count = live["candidate_count"]
        near = live["near_match_count"]
        hard = live["hard_negative_count"]
        fp = live["fingerprint_overlap_count"]
        queue_pop = live["reviewer_queue_population_count"]
        dataset_source = live["dataset_source"]
        provider_status = lr.get("provider_status")
        block_reasons.extend(live["block_reasons"])
        next_actions.extend(_next_action_for(br, env_var) for br in live["block_reasons"])

    host_gate_status, rate_limit_status = _governance_status(block_reasons, engaged=engaged)
    return {
        "smoke_name": _SMOKE_NAME,
        "live_query_requested": bool(live_query),
        "live_query_attempted": live_query_attempted,
        "env_var_name": env_var,
        "credential_present": credential_present,
        "credential_value_exposed": False,   # 불변 — key 값 미열람·미기록.
        # 불변 — smoke 가 `.env` **값을 report/log 로 미노출**(직접 cat/파싱 0). 파일 I/O 부재가 아니라 값 미노출의 뜻:
        # env_loader.load_env 는 present/missing 판정 위해 `.env` 를 os.environ 에 적재하나 **값을 caller 로 미반환**.
        "env_file_read": False,
        "env_example_checked": env_example_checked,
        "provider_status": provider_status,
        "host_gate_status": host_gate_status,
        "rate_limit_status": rate_limit_status,
        "records_count": records_count,
        "candidate_count": candidate_count,
        "near_match_count": near,
        "hard_negative_count": hard,
        "fingerprint_overlap_count": fp,
        "reviewer_queue_population_count": queue_pop,
        "dataset_source": dataset_source,
        "provenance": dataset_source or "none",   # 후보 0이면 fixture 둔갑 금지 — provenance 없음.
        "block_reasons": block_reasons,
        "next_actions": next_actions,
        "production_gold_count": 0,
        "merge_allowed": False,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "llm_invoked": False,
        "db_write": False,
    }


# ── CLI(기본 시도 0·network 0; --live-query 로 opt-in bounded governed fetch·값 미노출) ───────────────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#63 secret-safe Guardian live query smoke (병합 0·LLM 0·DB write 0; 기본 시도 0·"
                     "network 0; --live-query 로 opt-in bounded governed fetch·key 값 미노출)."))
    parser.add_argument("--topic", default="central bank rate decision", help="targeted topic(수집 의도).")
    parser.add_argument("--time-window", default="1d", help="time window(1d/7d).")
    parser.add_argument("--live-query", action="store_true",
                        help="실 governed fetch opt-in(network·CI 아님). credential 필요. key 값 미노출.")
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

    out = run_guardian_live_query_smoke(
        topic=ns.topic, time_window=ns.time_window, live_query=ns.live_query, host_gate=host_gate)

    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    # 사람 가독 요약 — credential_present 는 boolean 만(값 절대 미출력).
    print(f"- smoke={out['smoke_name']} requested={out['live_query_requested']} "
          f"attempted={out['live_query_attempted']}")
    print(f"- env_var={out['env_var_name']} credential_present={out['credential_present']} "
          f"value_exposed={out['credential_value_exposed']} env_file_read={out['env_file_read']} "
          f"example_checked={out['env_example_checked']}")
    print(f"- provider_status={out['provider_status']} host_gate={out['host_gate_status']} "
          f"rate_limit={out['rate_limit_status']}")
    print(f"- records={out['records_count']} candidate={out['candidate_count']} "
          f"near={out['near_match_count']} hard={out['hard_negative_count']} "
          f"queue_pop={out['reviewer_queue_population_count']}")
    print(f"- dataset_source={out['dataset_source']} provenance={out['provenance']}")
    print(f"- block_reasons={out['block_reasons']}")
    print(f"- next_actions={out['next_actions']}")
    print(f"- production_gold={out['production_gold_count']} merge_allowed={out['merge_allowed']} "
          f"db_write={out['db_write']} llm_invoked={out['llm_invoked']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

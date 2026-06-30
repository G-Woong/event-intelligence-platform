"""ADR#93 §10 — operator live command pack (validate-only / dry-run / live-run 을 모호함 없이 분리·명령 문자열만 EMIT).

문제(§10): operator 가 "지금 무엇을 실행하면 network 0 검증이고, 무엇이 진짜 live 호출인지" 를 한눈에 구분할 단일
출처가 없었다. validate-only / dry-run 은 절대 network 를 부르지 않고, live-run 은 valid ∧ live_approved payload 를
요구하며 실행 *전에* bounded provider 수 + provider 목록을 보여줘야 한다. 이 모듈은 그 세 명령을 **문자열로만** 묶는다
— **live 를 실행하지 않고 network 를 부르지 않는다**(string builder).

재구현 0(reuse only): provider 목록/검증은 `build_live_query_target`(PURE), provider 집합은 ALL_ADAPTER_PROVIDERS/
ADAPTER_WIRED_PROVIDERS/_NEWS_PROVIDERS_DEFAULT, host spacing 은 `adapter_descriptor`(하드코딩 0), intake 경로는
`build_intake_plan`, PII 가드는 `reviewer_pilot_handoff._assert_pii_safe` 를 그대로 쓴다.

절대 불변(상속·상용 안전 계약):
  - **network 0 · live 실행 0**: 이 모듈은 명령 문자열만 만든다(validate_only_calls_network=False·dry_run_calls_live_network=False).
  - **live 명령은 approval-gated runner 만**: payload-gated `operator_confirmed_live_runner`(또는 official_news
    --live-query)만 가리킨다. `provider_date_window_fidelity`(payload-gated 아님·key-free FR 를 승인 없이 호출 가능)로
    **라우팅하지 않는다**(routes_through_ungated_fidelity_probe=False).
  - validate-only / dry-run 명령에는 --live-query(live flag)가 없다. live 명령만 live opt-in 을 가진다.
  - **secret 0 · raw payload 본문 0**: 명령에 key 값/payload 원문을 싣지 않는다(_assert_pii_safe 재귀 가드).
  - output 경로는 gitignored root(outputs/reviewer_batch/·outputs/live_snapshots/·ingestion/outputs/)만 참조.
  - merge 0 · 전송 0 · production gold 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from backend.app.tools.live_query_target import build_live_query_target
from backend.app.tools.official_news_live_acquisition import _NEWS_PROVIDERS_DEFAULT
from backend.app.tools.operator_regulatory_event_payload import (
    PAYLOAD_NOT_PROVIDED,
    REAL_PAYLOAD_PATH,
)
from backend.app.tools.provider_query_adapters import (
    ADAPTER_WIRED_PROVIDERS,
    ALL_ADAPTER_PROVIDERS,
    adapter_descriptor,
)

# DEFAULT_BATCH_ID(="operator_regulatory_live")는 r1_label_return_operational_bridge 에서 가져온다 — 값은
# operator_confirmed_live_runner.DEFAULT_BATCH_ID 와 동일하나, read-API 안전(GET 경로 import 그래프에 live runner 미편입)
# 을 위해 live runner 를 import 하지 않는 bridge 의 local-mirror 상수를 쓴다(live_run_command 는 문자열로만 runner 참조).
from backend.app.tools.r1_label_return_operational_bridge import DEFAULT_BATCH_ID
from backend.app.tools.r1_production_candidate_acquisition import PROD_BATCH_ID
from backend.app.tools.reviewer_batch_launch import build_intake_plan
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "operator_live_command_pack"

# ── operator_live_command_pack_status(operator-facing) ─────────────────────────────────────────────────────
OLC_READY = "command_pack_ready"                                  # operator_event(date-pinned) 제공 → preview 가능.
OLC_PAYLOAD_PRESENT = "command_pack_ready_real_payload_present"   # event 없음·real payload 파일 존재 → 검증/승인으로.
OLC_NO_EVENT = "command_pack_ready_no_event_template_only"        # event 없음·real payload 없음 → 템플릿만(author 먼저).

# venv 인터프리터 리터럴(reviewer_batch_launch.build_intake_plan 의 validation_command 와 동형·하드코딩 단일 출처).
_PY = ".\\.venv\\Scripts\\python.exe"

# 운영 pacing floor 권고(adapter min_spacing 위 보수적 운영 가이드 — spacing 자체는 adapter_descriptor 에서 읽음).
_OPERATOR_PACING_FLOOR = "guardian≥6·nyt≥13 권장"

# 이 모듈이 참조 가능한 gitignored output root(단일 출처·.gitignore 와 일치).
_LIVE_SNAPSHOTS_DIR = "outputs/live_snapshots/"


# ── 명령 문자열(string only·실행 0) ───────────────────────────────────────────────────────────────────────
def _validate_payload_command(real_payload_path: str) -> str:
    """validate-only(network 0): real payload 를 §8 로드/검증만. --live-query 없음(live flag 0)."""
    return (f"{_PY} -m backend.app.tools.operator_regulatory_event_payload "
            f"--event-json {real_payload_path} --json")


def _date_pinned_dry_run_command(named_entity: str, event_phrase: str, occurrence_date: str) -> str:
    """dry-run(date-pinned·network 0): PURE target builder 로 query/window/provider 미리보기. --live-query 없음."""
    return (f"{_PY} -m backend.app.tools.live_query_target "
            f"--named-entity \"{named_entity}\" --event-phrase \"{event_phrase}\" "
            f"--occurrence-date {occurrence_date} --json")


def _seed_dry_run_command() -> str:
    """dry-run(regulatory seed·network 0): --live-query 없음 ⇒ blocked_no_live_opt_in(시도 0)."""
    return f"{_PY} -m backend.app.tools.official_news_live_acquisition --json"


def _live_run_command(real_payload_path: str, batch_id: str) -> str:
    """live-run(valid ∧ live_approved 요구): payload-gated approval runner. ungated fidelity probe 로 라우팅하지 않음."""
    return (f"{_PY} -m backend.app.tools.operator_confirmed_live_runner "
            f"--event-json {real_payload_path} --batch-id {batch_id} --json")


def _rate_limit_notes(provider_list: list[str]) -> dict:
    """provider 별 host min_spacing/policy/max_records(adapter_descriptor 단일 출처·spacing 하드코딩 0) + 운영 pacing floor."""
    notes: dict[str, str] = {}
    for prov in provider_list:
        desc = adapter_descriptor(prov)
        if desc is None:
            continue
        notes[prov] = (
            f"host={desc['host_gate_key']} · min_spacing={desc['host_min_spacing_seconds']}s "
            f"(shared host gate · no-bypass) · policy={desc['rate_limit_policy_id']} · "
            f"max_records={desc['max_records']}")
    notes["operator_pacing_floor"] = _OPERATOR_PACING_FLOOR
    return notes


def _next_action(status: str, *, date_pinned_valid: bool) -> str:
    """status → operator 한 줄 다음 행동(validate→dry-run→(valid∧approved)→live; network 경계·enforce_window 명시)."""
    if status == OLC_READY:
        pre = ("" if date_pinned_valid else
               "the operator_event is not yet a valid date-pinned named event (fix named_entity / event_phrase / "
               "ISO occurrence_date); ")
        return (pre + "run the validate-only command, then the date-pinned dry-run (both network 0) to preview the "
                "exact query, the [D,D+1] window, and the provider list; the news side enforces the date window "
                "(enforce_window=True). only after a valid AND live_approved real payload, run the live command "
                "(operator_confirmed_live_runner) — validate-only and dry-run never call the network.")
    if status == OLC_PAYLOAD_PRESENT:
        return ("a real payload is present — run the validate-only command first; if it is valid AND live_approved, "
                "run the live command (operator_confirmed_live_runner). the news side enforces the date window "
                "(enforce_window=True). validate-only and dry-run never call the network.")
    return ("no date-pinned operator_event and no real payload — author a payload at the gitignored real path "
            "(or pass a date-pinned operator_event), run validate-only, set operator_confirmed=true ∧ "
            "live_approved=true, then run the live command. the news side enforces the date window "
            "(enforce_window=True). validate-only and dry-run never call the network.")


def build_operator_live_command_pack(
    *, operator_event: Optional[dict] = None, real_payload_path: Optional[str] = None,
    batch_id: str = DEFAULT_BATCH_ID, operator_payload_status: Optional[str] = None,
) -> dict:
    """operator 에게 validate-only / dry-run / live-run 을 분리한 명령 묶음을 EMIT(network 0·live 실행 0·string only).

    real_payload_path 미지정 시 REAL_PAYLOAD_PATH(gitignored). operator_event(named_entity/event_phrase/occurrence_date)
    가 있으면 **date-pinned 경로** — `build_live_query_target`(PURE)로 provider_list/expected_provider_calls/검증 verdict
    를 얻고 dry-run 은 live_query_target preview(network 0). 없으면 **regulatory seed 경로** — provider_list 는 official×
    news(federal_register + guardian/nyt), dry-run 은 official_news_live_acquisition(--live-query 없음 ⇒ 시도 0). live-run
    은 어느 경로든 payload-gated `operator_confirmed_live_runner`(valid ∧ live_approved 요구)만 가리킨다 —
    `provider_date_window_fidelity`(payload-gated 아님)로 라우팅하지 않는다. secret/payload 원문 0·_assert_pii_safe 재귀 가드.

    real payload 존재 판정: operator_payload_status 가 주입되면 그 status 로 판정한다(파일시스템 미접근·read-API
    결정론·orchestrator GET 경로). 미주입(standalone CLI)이면 real_payload_path **파일 존재(stat)만** 본다
    (본문 미독·secret 미접근)."""
    path = real_payload_path or REAL_PAYLOAD_PATH

    date_pinned_valid = False
    target_wired = False
    if operator_event:
        # date-pinned 경로 — PURE target builder 가 provider_list/검증을 단일 출처로 제공(network 0).
        target = build_live_query_target(operator_event)
        provider_list = list(target["providers"])
        expected_provider_calls = len(target["providers"])   # =2(guardian + second).
        date_pinned_valid = bool(target["date_pinned_named_event_valid"])
        target_wired = bool(target["wired"])
        dry_run_command = _date_pinned_dry_run_command(
            str(operator_event.get("named_entity") or ""),
            str(operator_event.get("event_phrase") or ""),
            str(operator_event.get("occurrence_date") or ""))
        status = OLC_READY
        provider_calls_basis = "date-pinned news cross-source (guardian + second provider)"
    else:
        # regulatory seed 경로 — official(=ALL_ADAPTER - news-pairing wired) + news(_NEWS_PROVIDERS_DEFAULT).
        official_providers = sorted(ALL_ADAPTER_PROVIDERS - ADAPTER_WIRED_PROVIDERS)
        provider_list = sorted(set(official_providers) | set(_NEWS_PROVIDERS_DEFAULT))
        expected_provider_calls = len(provider_list)          # =3(federal_register + guardian + nyt).
        dry_run_command = _seed_dry_run_command()
        if operator_payload_status is not None:
            # orchestrator 주입 status 로 판정(파일시스템 미접근·read-API 결정론).
            payload_present = operator_payload_status not in ("", PAYLOAD_NOT_PROVIDED)
        else:
            # standalone CLI: real path 파일 존재(stat)만(본문 미독).
            payload_present = Path(path).exists()
        status = OLC_PAYLOAD_PRESENT if payload_present else OLC_NO_EVENT
        provider_calls_basis = "official×news (federal_register + guardian/nyt)"

    output_paths = {
        # operator_confirmed_live_runner --batch-id <batch_id> 의 returned-label dropbox/worklist intake.
        "operator_dropbox_intake_dir": build_intake_plan(batch_id, pseudonyms=[])["intake_directory"],
        # 하류 production-candidate freeze 기본 batch 의 intake(둘 다 gitignored outputs/reviewer_batch/).
        "production_candidate_intake_dir": build_intake_plan(PROD_BATCH_ID, pseudonyms=[])["intake_directory"],
        "live_snapshots_dir": _LIVE_SNAPSHOTS_DIR,
    }

    out = {
        "operation_name": OPERATION_NAME,
        "operator_live_command_pack_status": status,
        # ── 세 명령(분리·string only·실행 0) ──
        "validate_payload_command": _validate_payload_command(path),
        "dry_run_command": dry_run_command,
        "live_run_command": _live_run_command(path, batch_id),
        # ── bounded provider 표면(live 실행 *전* 공개) ──
        "expected_provider_calls": expected_provider_calls,
        "provider_list": provider_list,
        "provider_calls_basis": provider_calls_basis,
        "news_enforce_window_noted": True,
        "rate_limit_notes": _rate_limit_notes(provider_list),
        # ── date-pin 검증 verdict(date-pinned 경로만 의미·seed 경로 False) ──
        "date_pinned_named_event_valid": date_pinned_valid,
        "live_query_target_wired": target_wired,
        # ── 경로/롤백/다음 행동 ──
        "output_paths": output_paths,
        "gitignore_notes": (
            "outputs/reviewer_batch/, outputs/live_snapshots/, and ingestion/outputs/ are gitignored; the real "
            "payload (inputs/operator_events/) is gitignored — do not commit outputs, snapshots, or the real payload."),
        "rollback_notes": (
            "this pack only emits command strings — it executes nothing. validate-only and dry-run are read-only "
            "(no network, no writes); a live run via operator_confirmed_live_runner performs no merge, no DB write, "
            "and no sending — it only writes a reviewer worklist under the gitignored intake dir. to undo, the "
            "operator removes the gitignored batch intake directory (this module never deletes)."),
        "next_action": _next_action(status, date_pinned_valid=date_pinned_valid),
        # ── 정직 불변(hardcoded honesty invariants) ──
        "validate_only_calls_network": False,
        "dry_run_calls_live_network": False,
        "live_run_requires_approved_payload": True,
        "secret_in_command_pack": False,
        "raw_payload_text_in_pack": False,
        "routes_through_ungated_fidelity_probe": False,
        "actual_sending_performed": False,
        "merge_allowed": False,
        "production_gold_count": 0,
    }
    # CARDINAL: validate-only/dry-run 은 live flag 0 · live 는 approval-gated runner 만(ungated fidelity probe 0).
    assert "--live-query" not in out["validate_payload_command"]
    assert "--live-query" not in out["dry_run_command"]
    assert "operator_confirmed_live_runner" in out["live_run_command"]
    assert "provider_date_window_fidelity" not in out["live_run_command"]
    _assert_pii_safe(out, _path="operator_live_command_pack_output")
    return out


def sanitized_operator_live_command_pack(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(명령 본문 외 status/provider/honesty flag/next_action 만)."""
    return {
        "operator_live_command_pack_status": out["operator_live_command_pack_status"],
        "expected_provider_calls": out["expected_provider_calls"],
        "provider_list": list(out["provider_list"]),
        "news_enforce_window_noted": out["news_enforce_window_noted"],
        "validate_only_calls_network": out["validate_only_calls_network"],
        "dry_run_calls_live_network": out["dry_run_calls_live_network"],
        "live_run_requires_approved_payload": out["live_run_requires_approved_payload"],
        "routes_through_ungated_fidelity_probe": out["routes_through_ungated_fidelity_probe"],
        "operator_live_command_pack_next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#93 operator live command pack (validate-only / dry-run / live-run 분리·명령 문자열만 EMIT; "
                     "network 0·live 실행 0·live 는 approval-gated runner 만·ungated fidelity probe 라우팅 0)."))
    parser.add_argument("--named-entity", default="", help="operator named entity(date-pinned dry-run preview용).")
    parser.add_argument("--event-phrase", default="", help="operator event 행위(date-pinned dry-run preview용).")
    parser.add_argument("--occurrence-date", default="", help="실제 발생일 ISO YYYY-MM-DD(operator 확인).")
    parser.add_argument("--event-json", metavar="PATH", default=None,
                        help=f"real operator payload JSON 경로(미지정 시 {REAL_PAYLOAD_PATH}·gitignored).")
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID, help="live-run batch id.")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    operator_event = None
    if ns.named_entity or ns.event_phrase or ns.occurrence_date:
        operator_event = {
            "named_entity": ns.named_entity, "event_phrase": ns.event_phrase,
            "occurrence_date": ns.occurrence_date,
        }
    out = build_operator_live_command_pack(
        operator_event=operator_event, real_payload_path=ns.event_json, batch_id=ns.batch_id)
    if ns.json:
        print(json.dumps(sanitized_operator_live_command_pack(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['operator_live_command_pack_status']}")
    print(f"- providers: expected_calls={out['expected_provider_calls']} list={out['provider_list']} "
          f"basis={out['provider_calls_basis']}")
    print(f"- validate_only (network 0): {out['validate_payload_command']}")
    print(f"- dry_run (network 0): {out['dry_run_command']}")
    print(f"- live_run (valid∧approved): {out['live_run_command']}")
    print(f"- news_enforce_window_noted={out['news_enforce_window_noted']} "
          f"date_pinned_valid={out['date_pinned_named_event_valid']} wired={out['live_query_target_wired']}")
    print(f"- rate_limit_notes: {out['rate_limit_notes']}")
    print(f"- output_paths: {out['output_paths']}")
    print(f"- gitignore_notes: {out['gitignore_notes']}")
    print(f"- rollback_notes: {out['rollback_notes']}")
    print(f"- invariants: validate_only_calls_network={out['validate_only_calls_network']} "
          f"dry_run_calls_live_network={out['dry_run_calls_live_network']} "
          f"live_run_requires_approved_payload={out['live_run_requires_approved_payload']} "
          f"routes_through_ungated_fidelity_probe={out['routes_through_ungated_fidelity_probe']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

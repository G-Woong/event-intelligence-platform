"""ADR#90 — official×news live no-yield taxonomy (왜 candidate 가 안 나왔는가를 세분 분류·operator/engineer 양면 next action).

문제(§11): live 를 실행했는데 production candidate 가 0 일 때 "no candidates" 한 마디는 operator 가 **다음에 무엇을
바꿔야 하는지** 를 알려주지 못한다. ADR#87 engine 은 이미 `official_news_live_status`(12-state)+`_NEXT_ACTION` 을 갖지만,
(a) payload-stage 실패(missing/invalid/not-approved)를 engine status 와 한 어휘로 합치지 않았고, (b) overlap 실패를
**entity vs action vs date 근접** 으로 나누지 않았다(현 bridge 는 단일 shared-token gate).

이 모듈은 그 두 간극을 메우는 **분류 레이어** 다(재구현 0·진단 only):
  - **registry**: 각 no-yield 원인에 operator_facing_explanation·engineer_facing_cause·next_action·
    recommended_payload_adjustment·recommended_source_adjustment 5필드를 단일 출처로 고정한다.
  - **classify_live_no_yield**: payload entrypoint status + engine `official_news_live_status` 를 registry 키로 매핑한다.
  - **classify_overlap_failure**: entity/action/date 근접 3진단으로 no_entity_overlap / no_action_overlap /
    date_proximity_failed 를 가린다 — **정직성**: 현 engine 은 ONL_NO_OVERLAP(umbrella)만 방출하므로, 이 finer 분류는
    richer diagnostic(seed entity/action 토큰 ∩ shared_tokens)이 주어질 때만 단정하고, 없으면 umbrella 의 sub-cause 후보로
    노출한다(과대단정 0).

절대 불변: same_event 단정 0 · score/rationale/predicted_status 0 · merge 0 · network 0 · 진단 텍스트 only.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.official_news_live_acquisition import (
    ONL_BLOCKED_HOST_GATE,
    ONL_BLOCKED_NO_OPT_IN,
    ONL_BLOCKED_RATE_LIMIT,
    ONL_BRIDGE_CANDIDATES_FOUND,
    ONL_INVALID_SEED,
    ONL_NEWS_NO_RECORDS,
    ONL_NO_IN_WINDOW_NEWS,
    ONL_NO_OVERLAP,
    ONL_NOT_RUN,
    ONL_OFFICIAL_NO_RECORDS,
    ONL_PRODUCTION_BATCH_FROZEN,
    ONL_PROVIDER_UNAVAILABLE,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "live_no_yield_taxonomy"

# ── taxonomy 키(stage 별·세분) ────────────────────────────────────────────────────────────────────────────
TX_NOT_RUN = "not_run"
TX_MISSING_PAYLOAD = "missing_payload"
TX_INVALID_PAYLOAD = "invalid_payload"
TX_PAYLOAD_SECRET_OR_PII = "payload_secret_or_pii_blocked"
TX_EXAMPLE_DETECTED = "operator_payload_example_detected"
TX_PAYLOAD_NOT_APPROVED = "payload_not_approved"
TX_INVALID_SEED = "invalid_regulatory_seed"
TX_PROVIDER_UNAVAILABLE = "provider_unavailable"
TX_HOST_GATE_BLOCKED = "host_gate_blocked"
TX_RATE_LIMITED = "rate_limited"
TX_OFFICIAL_NO_RECORDS = "official_no_records"
TX_OFFICIAL_OUT_OF_WINDOW = "official_out_of_window"
TX_NEWS_NO_RECORDS = "news_no_records"
TX_NEWS_OUT_OF_WINDOW = "news_out_of_window"
TX_NO_IN_WINDOW_NEWS = "no_in_window_news"
TX_NO_OVERLAP = "no_official_news_overlap"
TX_NO_ENTITY_OVERLAP = "no_entity_overlap"
TX_NO_ACTION_OVERLAP = "no_action_overlap"
TX_DATE_PROXIMITY_FAILED = "date_proximity_failed"
TX_FREEZE_UNSAFE = "bridge_candidate_found_but_freeze_unsafe"
TX_FREEZE_SUCCEEDED = "freeze_succeeded"

# overlap umbrella 가 품는 sub-cause 후보(현 engine 이 분리 못 함·finer classifier 로만 단정).
_OVERLAP_SUB_CAUSES = [TX_NO_ENTITY_OVERLAP, TX_NO_ACTION_OVERLAP, TX_DATE_PROXIMITY_FAILED]

# 각 키 → 5필드(operator/engineer 양면·payload/source 조정안). 단일 출처(드리프트 0).
_TAXONOMY: dict[str, dict] = {
    TX_NOT_RUN: {
        "stage": "not_run",
        "operator_facing_explanation": "The official×news live run has not been executed yet.",
        "engineer_facing_cause": "no acquisition output (read-only path or live not opted in)",
        "next_action": "provide an approved operator payload and opt in to a bounded live run",
        "recommended_payload_adjustment": "supply a confirmed, approved operator payload",
        "recommended_source_adjustment": "none",
    },
    TX_MISSING_PAYLOAD: {
        "stage": "payload",
        "operator_facing_explanation": "No real operator-confirmed regulatory event payload was provided.",
        "engineer_facing_cause": "inputs/operator_events real payload absent (operator_payload_status=not_provided)",
        "next_action": "author and drop a real operator payload (use the authoring helper), then approve a live run",
        "recommended_payload_adjustment": "fill the authoring template (operator_confirmed=true, live_approved=true)",
        "recommended_source_adjustment": "none",
    },
    TX_INVALID_PAYLOAD: {
        "stage": "payload",
        "operator_facing_explanation": "The operator payload is present but invalid (bad JSON or failed §8 validation).",
        "engineer_facing_cause": "payload parse/validation rejected (operator_not_confirmed / placeholder / missing field)",
        "next_action": "fix the payload fields the validator flagged, then re-run",
        "recommended_payload_adjustment": "name the agency/entity + action, set an ISO occurrence window, confirm the event",
        "recommended_source_adjustment": "none",
    },
    TX_PAYLOAD_SECRET_OR_PII: {
        "stage": "payload",
        "operator_facing_explanation": "The operator payload was rejected because it contained secret/PII-like keys.",
        "engineer_facing_cause": "forbidden-key scan tripped (fail-closed discard · key names only · values never read)",
        "next_action": "remove the secret/PII fields from the payload (never put API keys or reviewer PII in the payload)",
        "recommended_payload_adjustment": "strip score/secret/api_key/reviewer_email/raw_body keys",
        "recommended_source_adjustment": "none",
    },
    TX_EXAMPLE_DETECTED: {
        "stage": "payload",
        "operator_facing_explanation": "The example dummy payload was detected in the real path — it is a template, not a real event.",
        "engineer_facing_cause": "payload_is_example_dummy (seed_id=operator_filled_example, operator_confirmed!=true)",
        "next_action": "replace the example dummy with a real operator-confirmed payload (use the authoring helper)",
        "recommended_payload_adjustment": "fill a real confirmed event (operator_confirmed=true, live_approved=true, named entity)",
        "recommended_source_adjustment": "none",
    },
    TX_PAYLOAD_NOT_APPROVED: {
        "stage": "opt_in",
        "operator_facing_explanation": "The payload is valid but the operator has not approved a live run.",
        "engineer_facing_cause": "live_approved=false (blocked_no_live_opt_in) — fail-closed, no network",
        "next_action": "set live_approved=true (or pass --live-query) to approve a bounded official×news live run",
        "recommended_payload_adjustment": "set live_approved=true after confirming the event occurred",
        "recommended_source_adjustment": "none",
    },
    TX_INVALID_SEED: {
        "stage": "seed",
        "operator_facing_explanation": "The regulatory seed shape is invalid (not a discrete official×news event).",
        "engineer_facing_cause": "validate_regulatory_seed rejected (broad/generic, missing agency/action/window)",
        "next_action": "pin a named regulatory event with an agency/entity, a specific action, and an ISO date window",
        "recommended_payload_adjustment": "replace broad topics with a named agency + specific action + date",
        "recommended_source_adjustment": "keep federal_register official + a publishable news provider",
    },
    TX_PROVIDER_UNAVAILABLE: {
        "stage": "provider",
        "operator_facing_explanation": "The news providers are not available (missing credentials or not wired).",
        "engineer_facing_cause": "all news providers returned missing_credentials/fetcher_not_wired",
        "next_action": "set the news provider credentials in .env (values never committed/printed); FR is key-free",
        "recommended_payload_adjustment": "none",
        "recommended_source_adjustment": "configure GUARDIAN_API_KEY/NYT_API_KEY or add a wired news provider",
    },
    TX_HOST_GATE_BLOCKED: {
        "stage": "gate",
        "operator_facing_explanation": "A shared host floor blocked the request (no-bypass politeness gate).",
        "engineer_facing_cause": "host_rate_gate min-spacing not elapsed",
        "next_action": "respect the shared host floor; retry after the minimum spacing",
        "recommended_payload_adjustment": "none",
        "recommended_source_adjustment": "none (do not bypass the host gate)",
    },
    TX_RATE_LIMITED: {
        "stage": "gate",
        "operator_facing_explanation": "A provider rate limit/cooldown blocked the request.",
        "engineer_facing_cause": "provider cooldown active (rate_limited)",
        "next_action": "respect the provider cooldown; do not tight-retry",
        "recommended_payload_adjustment": "none",
        "recommended_source_adjustment": "spread requests; stay within the provider rate budget",
    },
    TX_OFFICIAL_NO_RECORDS: {
        "stage": "official",
        "operator_facing_explanation": "Federal Register returned no in-window official records for this query.",
        "engineer_facing_cause": "FR official_records empty within the pinned window",
        "next_action": "broaden the official_query or window, or pin an event with Federal Register coverage",
        "recommended_payload_adjustment": "widen official_query to the agency's official action vocabulary",
        "recommended_source_adjustment": "confirm the event actually has an FR document",
    },
    TX_OFFICIAL_OUT_OF_WINDOW: {
        "stage": "official",
        "operator_facing_explanation": "Official records exist but all fall outside the pinned window.",
        "engineer_facing_cause": "FR records present but none in [start, end] after window filter",
        "next_action": "verify the actual occurrence/publication date and adjust the date window",
        "recommended_payload_adjustment": "set date_window to the real FR publication date",
        "recommended_source_adjustment": "none",
    },
    TX_NEWS_NO_RECORDS: {
        "stage": "news",
        "operator_facing_explanation": "News providers returned no records for the news query.",
        "engineer_facing_cause": "news combined records empty (no provider returned ok records)",
        "next_action": "narrow/adjust news_query, expand the news provider, or pin an event with public reporting",
        "recommended_payload_adjustment": "use journalistic wording in news_query (entity + action), not official text",
        "recommended_source_adjustment": "add a publishable news provider with coverage of this beat",
    },
    TX_NEWS_OUT_OF_WINDOW: {
        "stage": "news",
        "operator_facing_explanation": "News records exist but all fall outside the pinned window.",
        "engineer_facing_cause": "news records present but dropped by enforce_window (published_at outside [start, end])",
        "next_action": "verify the occurrence date; the providers may have ignored the date filter",
        "recommended_payload_adjustment": "set date_window to the real reporting date",
        "recommended_source_adjustment": "prefer a window-honoring news source if available",
    },
    TX_NO_IN_WINDOW_NEWS: {
        "stage": "news",
        "operator_facing_explanation": "News providers returned records but none inside the pinned window.",
        "engineer_facing_cause": "no_in_window_news (Guardian/NYT may have ignored the date filter; enforce_window dropped them)",
        "next_action": "verify the occurrence date and re-run; a window-honoring source reduces this",
        "recommended_payload_adjustment": "confirm the real occurrence window",
        "recommended_source_adjustment": "use a window-honoring news provider",
    },
    TX_NO_OVERLAP: {
        "stage": "overlap",
        "operator_facing_explanation": "Official and news records exist but none share enough subject within the date tolerance.",
        "engineer_facing_cause": "bridge_candidate_count=0 (combined entity/action token gate not met within date proximity)",
        "next_action": "pin an event both an FR document and a news outlet report on the same date (sub-cause: entity/action/date)",
        "recommended_payload_adjustment": "choose an event where the official action and the news headline share named tokens",
        "recommended_source_adjustment": "ensure official and news cover the SAME named subject, not the same broad topic",
    },
    TX_NO_ENTITY_OVERLAP: {
        "stage": "overlap",
        "operator_facing_explanation": "Official and news records do not share the named entity/agency.",
        "engineer_facing_cause": "entity tokens (agency/respondent/target) absent from the shared-token intersection",
        "next_action": "pin an event whose official record and news report name the SAME entity",
        "recommended_payload_adjustment": "name the specific respondent/target/product (not just the agency)",
        "recommended_source_adjustment": "choose news that names the same entity as the official record",
    },
    TX_NO_ACTION_OVERLAP: {
        "stage": "overlap",
        "operator_facing_explanation": "Official and news records share the entity but not the specific action.",
        "engineer_facing_cause": "action tokens (specific regulatory action) absent from the shared-token intersection",
        "next_action": "pin an event where both cover the SAME specific action (not just the same agency)",
        "recommended_payload_adjustment": "use the specific action phrase in both official_query and news_query",
        "recommended_source_adjustment": "choose reporting on the specific action, not general agency coverage",
    },
    TX_DATE_PROXIMITY_FAILED: {
        "stage": "overlap",
        "operator_facing_explanation": "Official and news records are about the same subject but too far apart in date.",
        "engineer_facing_cause": "date_proximity_days > tolerance (official publication and news report not within tolerance)",
        "next_action": "widen the date tolerance only if justified, or pin an event with same-day reporting",
        "recommended_payload_adjustment": "set the window to the publication date the news actually reports on",
        "recommended_source_adjustment": "choose timely reporting close to the official publication date",
    },
    TX_FREEZE_UNSAFE: {
        "stage": "freeze",
        "operator_facing_explanation": "Bridge candidates exist but none are freeze-eligible (both must be in-window).",
        "engineer_facing_cause": "bridge_candidate_count>0 but freeze_eligible_count=0 (one side out-of-window)",
        "next_action": "verify the window so BOTH the official and the news record fall inside it, then re-run",
        "recommended_payload_adjustment": "tighten the date window to where both records fall in-window",
        "recommended_source_adjustment": "none (bridge is reviewer-routing, not truth)",
    },
    TX_FREEZE_SUCCEEDED: {
        "stage": "freeze",
        "operator_facing_explanation": "Freeze succeeded: a reviewer worklist of official×news candidate pairs was frozen.",
        "engineer_facing_cause": "production_candidate_batch_ready=true (live-derived publishable pairs)",
        "next_action": "manually distribute the frozen worklist to >=2 reviewers; production gold stays 0 until returned labels",
        "recommended_payload_adjustment": "none",
        "recommended_source_adjustment": "none",
    },
}

# engine official_news_live_status → taxonomy 키(payload-stage 는 classify 에서 우선 처리).
_ENGINE_STATUS_TO_TAXONOMY: dict[str, str] = {
    ONL_NOT_RUN: TX_NOT_RUN,
    ONL_INVALID_SEED: TX_INVALID_SEED,
    ONL_BLOCKED_NO_OPT_IN: TX_PAYLOAD_NOT_APPROVED,
    ONL_PROVIDER_UNAVAILABLE: TX_PROVIDER_UNAVAILABLE,
    ONL_BLOCKED_HOST_GATE: TX_HOST_GATE_BLOCKED,
    ONL_BLOCKED_RATE_LIMIT: TX_RATE_LIMITED,
    ONL_OFFICIAL_NO_RECORDS: TX_OFFICIAL_NO_RECORDS,
    ONL_NEWS_NO_RECORDS: TX_NEWS_NO_RECORDS,
    ONL_NO_IN_WINDOW_NEWS: TX_NO_IN_WINDOW_NEWS,
    ONL_NO_OVERLAP: TX_NO_OVERLAP,
    ONL_BRIDGE_CANDIDATES_FOUND: TX_FREEZE_UNSAFE,
    ONL_PRODUCTION_BATCH_FROZEN: TX_FREEZE_SUCCEEDED,
}

# payload entrypoint operator_payload_status → taxonomy 키(payload-stage 우선).
_PAYLOAD_STATUS_TO_TAXONOMY: dict[str, str] = {
    "not_provided": TX_MISSING_PAYLOAD,
    "present_invalid_json": TX_INVALID_PAYLOAD,
    "present_rejected_pii_or_secret": TX_PAYLOAD_SECRET_OR_PII,
}

# ADR#88 intake gate 의 operator-gate blocked status(official_news_live_acquisition 에는 없는 토큰·literal 매핑).
_INTAKE_BLOCKED_TO_TAXONOMY: dict[str, str] = {
    "blocked_operator_not_confirmed": TX_INVALID_PAYLOAD,
    "blocked_invalid_confirmation": TX_INVALID_PAYLOAD,
}


def taxonomy_entry(key: str) -> dict:
    """taxonomy 키 → 5필드 entry(+key·sub-cause 후보). 미등록 키는 not_run 으로 fail-closed."""
    base = _TAXONOMY.get(key) or _TAXONOMY[TX_NOT_RUN]
    entry = {"taxonomy_key": key if key in _TAXONOMY else TX_NOT_RUN, **base}
    entry["is_yield"] = entry["taxonomy_key"] == TX_FREEZE_SUCCEEDED
    if entry["taxonomy_key"] == TX_NO_OVERLAP:
        entry["candidate_sub_causes"] = list(_OVERLAP_SUB_CAUSES)
    else:
        entry["candidate_sub_causes"] = []
    return entry


def classify_overlap_failure(*, entity_overlap: bool, action_overlap: bool, date_close: bool) -> dict:
    """entity/action/date 근접 3진단 → overlap 실패 sub-cause(finer·단정 가능).

    우선순위: date_close 실패 → date_proximity_failed; entity 미공유 → no_entity_overlap; action 미공유 →
    no_action_overlap. 셋 다 충족이면 overlap 존재(no_yield 아님 → 호출측은 freeze 단계로). 현 engine 은 이 분리를
    방출하지 않으므로 richer diagnostic(seed entity/action 토큰)이 있을 때만 이 함수를 호출한다(과대단정 0)."""
    if not date_close:
        return taxonomy_entry(TX_DATE_PROXIMITY_FAILED)
    if not entity_overlap:
        return taxonomy_entry(TX_NO_ENTITY_OVERLAP)
    if not action_overlap:
        return taxonomy_entry(TX_NO_ACTION_OVERLAP)
    # overlap 성립 — no-yield 아님(상위가 freeze 단계로 진행).
    return taxonomy_entry(TX_FREEZE_SUCCEEDED)


def classify_live_no_yield(
    acquisition_out: Optional[dict] = None, *, payload_entrypoint_out: Optional[dict] = None,
    is_example_payload: bool = False,
) -> dict:
    """payload entrypoint status + engine official_news_live_status → taxonomy entry(세분·진단 only).

    payload-stage 실패(missing/invalid/secret-PII/example-detected)가 있으면 그것을 우선한다(live 가 그 단계에서 막힘).
    그 외에는 engine status(+ intake gate blocked status)를 registry 키로 매핑한다. acquisition 도 payload 도 없으면
    not_run. official_out_of_window/news_out_of_window/no_entity_overlap/no_action_overlap/date_proximity_failed 같은
    finer 키는 engine 이 직접 방출하지 않으므로 umbrella(official_no_records/news_no_records/no_official_news_overlap)로
    매핑하고, sub-cause 는 candidate 로만 노출한다(과대단정 0)."""
    # payload-stage 우선.
    if payload_entrypoint_out is not None:
        ps = str(payload_entrypoint_out.get("operator_payload_status") or "")
        # example dummy 가 real 경로에 놓인 경우(valid JSON 이지만 real event 아님) → example-detected 우선.
        if is_example_payload or bool(payload_entrypoint_out.get("payload_is_example_dummy")):
            if ps not in ("not_provided", "present_invalid_json", "present_rejected_pii_or_secret"):
                return taxonomy_entry(TX_EXAMPLE_DETECTED)
        if ps in _PAYLOAD_STATUS_TO_TAXONOMY:
            return taxonomy_entry(_PAYLOAD_STATUS_TO_TAXONOMY[ps])
    if acquisition_out is None:
        return taxonomy_entry(TX_NOT_RUN)
    status = str(acquisition_out.get("official_news_live_status") or ONL_NOT_RUN)
    if status in _ENGINE_STATUS_TO_TAXONOMY:
        return taxonomy_entry(_ENGINE_STATUS_TO_TAXONOMY[status])
    return taxonomy_entry(_INTAKE_BLOCKED_TO_TAXONOMY.get(status, TX_NOT_RUN))


def build_live_no_yield_taxonomy(
    acquisition_out: Optional[dict] = None, *, payload_entrypoint_out: Optional[dict] = None,
) -> dict:
    """현재 분류 + 전체 registry(operator 가 가능한 모든 원인과 next action 을 한눈에)·aggregate-only.

    live_no_yield_taxonomy_status = 현재 분류 키. registry 는 모든 키의 5필드를 노출(reviewer/public truth 아님·진단)."""
    current = classify_live_no_yield(acquisition_out, payload_entrypoint_out=payload_entrypoint_out)
    out = {
        "operation_name": OPERATION_NAME,
        "live_no_yield_taxonomy_status": current["taxonomy_key"],
        "is_yield": current["is_yield"],
        "current": current,
        "taxonomy_registry": {k: taxonomy_entry(k) for k in _TAXONOMY},
        "taxonomy_key_count": len(_TAXONOMY),
        # 불변 경계.
        "same_event_asserted": False,
        "score_exposed": False,
        "reviewer_routing_only": True,
        "merge_allowed": False,
    }
    _assert_pii_safe(out, _path="live_no_yield_taxonomy_output")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#90 official×news live no-yield taxonomy (왜 candidate 0 인지 세분 분류·operator/engineer 양면 "
                     "next action·진단 only·same_event 0·score 0·network 0)."))
    parser.add_argument("--json", action="store_true", help="full taxonomy registry JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_live_no_yield_taxonomy()
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['live_no_yield_taxonomy_status']} "
          f"keys={out['taxonomy_key_count']}")
    for k, e in out["taxonomy_registry"].items():
        print(f"    {k:<42} [{e['stage']}] {e['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

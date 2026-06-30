"""ADR#89 — operator regulatory event payload entrypoint (real↔example 분리·gitignored real path·PII fail-closed).

ADR#88 의 `operator_regulatory_event_intake` 는 payload 를 받으면 §8 을 검증해 live 를 게이트했고 `_load_payload`/
CLI(`--event-json`)로 gitignored JSON 을 읽을 수 있었으나, **real payload 경로 관례(example 과의 분리·gitignore
등록·PII/secret fail-closed)가 모듈 계약으로 고정되어 있지 않았다**. 이 모듈은 그 **product-critical 경계** 다:
  - committed **example**(`examples/operator_regulatory_event_payload.example.json`·dummy·operator_confirmed=false)와
    **real payload**(`inputs/operator_events/...`·gitignored·operator 가 직접 drop)를 경로로 분리하고,
  - real payload 로드 시 secret/API key/reviewer PII-like 키를 **fail-closed scan**(발견 시 payload 폐기·값 미노출·
    키명 카운트만)하며,
  - §8 검증은 단일 출처(`validate_operator_confirmed_event`)에 위임하고, live 실행은 intake gate
    (`run_operator_regulatory_event_intake`)에 위임한다 — 이 모듈은 engine/gate 를 재구현하지 않는다.

절대 불변(상속·상용 안전 계약):
  - **코드가 payload 를 생성하지 않는다**(example 은 committed 템플릿일 뿐 real event 아님·`code_generated_payload=False`).
  - **example ≠ real**: example dummy 가 real 경로에 잘못 놓여도 operator_confirmed=false 라 gate 가 live 를 차단.
  - **live_approved=false → network 0**: gate 가 confirmation_valid ∧ live_approved 일 때만 engine 호출(이중 차단).
  - **operator confirmation ≠ same_event truth**(intake gate 가 보장·불변 passthrough).
  - secret/PII/score/rationale/predicted_status 어떤 depth 도 출력 0(`_assert_pii_safe` 재귀 가드).
  test: payload 파일 주입 + acquisition_fn(fake) 주입 시 결정론(network 0·실 `.env` 미접촉).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from backend.app.tools.operator_regulatory_event_intake import (
    run_operator_regulatory_event_intake,
    validate_operator_confirmed_event,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "operator_regulatory_event_payload"

# ── real(gitignored)↔example(committed) 경로 분리(§8.1·§8.2) ────────────────────────────────────────────────
REAL_PAYLOAD_PATH = "inputs/operator_events/operator_regulatory_event_payload.json"
REAL_PAYLOAD_GITIGNORE_PREFIX = "inputs/operator_events/"   # .gitignore 에 등록(test-lock).
EXAMPLE_PAYLOAD_PATH = "examples/operator_regulatory_event_payload.example.json"

# ── operator_payload_status(real 파일 present/validity 축·operator_event_status 와 직교) ─────────────────────
PAYLOAD_NOT_PROVIDED = "not_provided"                       # real 파일 없음(이번 턴 기본·정직).
PAYLOAD_PRESENT_VALID = "present_valid_json"                # real 파일 있음·JSON dict·forbidden 키 없음.
PAYLOAD_PRESENT_INVALID_JSON = "present_invalid_json"       # real 파일 있음·JSON 파싱 실패/비-dict.
PAYLOAD_PRESENT_PII_OR_SECRET = "present_rejected_pii_or_secret"   # forbidden 키 발견 → fail-closed 폐기.
PAYLOAD_STATES = frozenset({
    PAYLOAD_NOT_PROVIDED, PAYLOAD_PRESENT_VALID, PAYLOAD_PRESENT_INVALID_JSON, PAYLOAD_PRESENT_PII_OR_SECRET,
})

# ── operator_payload_path_status(operator-facing "지금 어디에 둘지") ──────────────────────────────────────────
PATH_EXAMPLE_ONLY = "example_only_no_real_payload"         # real 경로 비어있음 → example 참조해 채워 drop.
PATH_REAL_PRESENT = "real_payload_present"                  # real 경로에 파일 존재(유효성과 무관).

# committed example — dummy/placeholder(operator_confirmed=false·live_approved=false). **real event 아님**.
EXAMPLE_OPERATOR_REGULATORY_EVENT_PAYLOAD: dict = {
    "seed_id": "operator_filled_example",
    "operator_confirmed": False,
    "confirmed_by": "operator_name_or_role",
    "confirmed_at": "YYYY-MM-DD",
    "agency_or_entity": "NAMED_AGENCY_OR_ENTITY",
    "action_phrase": "SPECIFIC_REGULATORY_ACTION",
    "date_window_start": "YYYY-MM-DD",
    "date_window_end": "YYYY-MM-DD",
    "official_query": "FEDERAL_REGISTER_QUERY",
    "news_query": "NEWS_QUERY",
    "expected_news_angle": "WHY_NEWS_SHOULD_COVER_THIS",
    "live_approved": False,
}

# payload 에 절대 실리면 안 되는 secret/PII/score-like 키(fail-closed·정확명). _assert_pii_safe 와 병행하되 이 스캔은
# **로드 단계**에서 payload 자체를 폐기하기 위한 사전 방어(R-OperatorPayloadPIILeakage).
_PAYLOAD_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "secret", "api_key", "apikey", "provider_secret", "password", "passwd", "token", "access_token",
    "guardian_api_key", "nyt_api_key", "openai_api_key", "langsmith_api_key",
    "reviewer_name", "reviewer_email", "email", "phone",
    "score", "model_score", "rationale", "predicted_status", "raw_body", "body",
})


def _scan_forbidden_keys(payload: dict) -> list[str]:
    """payload 의 **모든 depth**(dict/list 재귀)에서 forbidden(secret/PII/score) 키를 탐지(키명만·값 미접근).

    출력단 `_assert_pii_safe`(정확명 재귀 가드)와 같은 어휘를 입력단에서 fail-closed 로 선적용한다 — 깊이 한계 없음
    (adversarial Finding 3: 1-depth 한계 제거). 값은 매칭에 쓰지 않으며(키 집합 ∩ forbidden) 노출하지 않는다."""
    found: set[str] = set()

    def _walk(obj: object) -> None:
        if isinstance(obj, dict):
            found.update(set(obj) & _PAYLOAD_FORBIDDEN_KEYS)
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(payload)
    return sorted(found)


def load_operator_regulatory_event_payload(path: Optional[str] = None) -> dict:
    """real payload(gitignored JSON)를 읽어 status 와 함께 반환. 코드가 payload 를 생성하지 않는다.

    path=None → REAL_PAYLOAD_PATH. 없음/빈파일 → not_provided. JSON 파싱 실패/비-dict → present_invalid_json.
    forbidden(secret/PII/score) 키 발견 → present_rejected_pii_or_secret + payload 폐기(fail-closed·값 미노출).
    반환: {payload(or None), operator_payload_status, operator_payload_path_status, forbidden_keys_found(키명만)}."""
    p = Path(path) if path else Path(REAL_PAYLOAD_PATH)
    if not p.exists():
        return {"payload": None, "operator_payload_status": PAYLOAD_NOT_PROVIDED,
                "operator_payload_path_status": PATH_EXAMPLE_ONLY, "forbidden_keys_found": []}
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        return {"payload": None, "operator_payload_status": PAYLOAD_NOT_PROVIDED,
                "operator_payload_path_status": PATH_REAL_PRESENT, "forbidden_keys_found": []}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"payload": None, "operator_payload_status": PAYLOAD_PRESENT_INVALID_JSON,
                "operator_payload_path_status": PATH_REAL_PRESENT, "forbidden_keys_found": []}
    if not isinstance(data, dict):
        return {"payload": None, "operator_payload_status": PAYLOAD_PRESENT_INVALID_JSON,
                "operator_payload_path_status": PATH_REAL_PRESENT, "forbidden_keys_found": []}
    forbidden = _scan_forbidden_keys(data)
    if forbidden:
        return {"payload": None, "operator_payload_status": PAYLOAD_PRESENT_PII_OR_SECRET,
                "operator_payload_path_status": PATH_REAL_PRESENT, "forbidden_keys_found": forbidden}
    return {"payload": data, "operator_payload_status": PAYLOAD_PRESENT_VALID,
            "operator_payload_path_status": PATH_REAL_PRESENT, "forbidden_keys_found": []}


def validate_operator_regulatory_event_payload(payload: dict) -> dict:
    """§8 검증을 단일 출처(`validate_operator_confirmed_event`)에 위임(재구현 0)."""
    return validate_operator_confirmed_event(payload)


def is_example_payload(payload: Optional[dict]) -> bool:
    """example dummy(seed_id==operator_filled_example ∧ operator_confirmed≠true)를 real payload 로 오인 방지."""
    if not isinstance(payload, dict):
        return False
    return (payload.get("seed_id") == EXAMPLE_OPERATOR_REGULATORY_EVENT_PAYLOAD["seed_id"]
            and payload.get("operator_confirmed") is not True)


def run_operator_confirmed_live_if_allowed(
    payload: Optional[dict] = None, *, acquisition_fn: Optional[Callable[..., dict]] = None,
    today: Optional[str] = None, **acquisition_kwargs: Any,
) -> dict:
    """payload(real·load 결과) → intake gate. payload None → not_provided(engine 미호출). valid ∧ live_approved 일
    때만 gate 가 engine 을 호출한다(gate 가 차단·이 모듈은 재구현 0). acquisition_fn/transports 는 결정론 테스트용."""
    return run_operator_regulatory_event_intake(
        payload, acquisition_fn=acquisition_fn, today=today, **acquisition_kwargs)


def resolve_operator_payload_entrypoint(
    path: Optional[str] = None, *, acquisition_fn: Optional[Callable[..., dict]] = None,
    today: Optional[str] = None, **acquisition_kwargs: Any,
) -> dict:
    """load(real·gitignored) → intake gate 를 한 번에. real payload 없으면 not_provided 로 정직 산출(network 0).

    operator raw payload 본문은 출력에 재임베드하지 않는다(§14·status/count/aggregate 만). live 실행은 gate 가
    confirmation_valid ∧ live_approved 일 때만 — example 이 real 경로에 잘못 놓여도 operator_confirmed=false 라 차단."""
    loaded = load_operator_regulatory_event_payload(path)
    payload = loaded["payload"]
    intake = run_operator_confirmed_live_if_allowed(
        payload, acquisition_fn=acquisition_fn, today=today, **acquisition_kwargs)
    out = {
        "operation_name": OPERATION_NAME,
        # payload 경계(real↔example·gitignored·코드 생성 0).
        "operator_payload_status": loaded["operator_payload_status"],
        "operator_payload_path_status": loaded["operator_payload_path_status"],
        "real_payload_path": REAL_PAYLOAD_PATH,
        "real_payload_gitignored": True,
        "example_payload_path": EXAMPLE_PAYLOAD_PATH,
        "example_payload_committed": True,
        "payload_forbidden_keys_count": len(loaded["forbidden_keys_found"]),
        "code_generated_payload": False,
        "payload_is_example_dummy": is_example_payload(payload),
        # intake gate passthrough(aggregate·secret/score/PII 0·raw payload 미노출).
        "operator_event_status": intake["operator_event_status"],
        "operator_confirmed": intake["operator_confirmed"],
        "confirmation_valid": intake["confirmation_valid"],
        "confirmation_blocked_reason": intake["confirmation_blocked_reason"],
        "selected_seed_id": intake["selected_seed_id"],
        "seed_provenance": intake["seed_provenance"],
        "official_news_live_status": intake["official_news_live_status"],
        "live_query_executed": bool(intake["live_query_executed"]),
        "bridge_candidate_count": int(intake["bridge_candidate_count"]),
        "production_candidate_status": intake["production_candidate_status"],
        "production_frozen_pair_count": int(intake["production_frozen_pair_count"]),
        "reviewer_handoff_ready": bool(intake["reviewer_handoff_ready"]),
        "production_gold_count": int(intake["production_gold_count"]),
        "current_r1_gap": int(intake["current_r1_gap"]),
        # ── 불변 경계(정직·constant) ──
        "operator_confirmation_as_same_event_truth": False,
        "actual_sending_performed": False,
        "merge_allowed": bool(intake["merge_allowed"]),
        "public_iu_allowed": False,
        "r2_r7_no_go": True,
        "blocked_reason": intake["blocked_reason"],
        "next_action": intake["next_action"],
        "operator_intake_result": intake,
    }
    _assert_pii_safe(out, _path="operator_regulatory_event_payload_output")
    return out


def sanitized_operator_payload(out: dict) -> dict:
    """snapshot/frontier 용 aggregate-only 투영(raw payload·intake 전체 제외·status/path/count 만)."""
    return {
        "operator_payload_status": out["operator_payload_status"],
        "operator_payload_path_status": out["operator_payload_path_status"],
        "real_payload_gitignored": out["real_payload_gitignored"],
        "operator_event_status": out["operator_event_status"],
        "confirmation_valid": out["confirmation_valid"],
        "official_news_live_status": out["official_news_live_status"],
        "production_candidate_status": out["production_candidate_status"],
        "blocked_reason": out["blocked_reason"],
        "next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#89 operator regulatory event payload entrypoint (real↔example 분리·gitignored real path·"
                     "PII/secret fail-closed; operator 확인 없이 live 차단·코드가 payload 생성 0·merge 0·secret read 0)."))
    parser.add_argument("--event-json", metavar="PATH", default=None,
                        help=f"real operator payload JSON(미지정 시 {REAL_PAYLOAD_PATH}·gitignored). 코드 생성 0.")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = resolve_operator_payload_entrypoint(ns.event_json)
    agg = sanitized_operator_payload(out)
    if ns.json:
        print(json.dumps(agg, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']}")
    print(f"- payload: status={out['operator_payload_status']} path_status={out['operator_payload_path_status']} "
          f"forbidden_keys={out['payload_forbidden_keys_count']} is_example_dummy={out['payload_is_example_dummy']}")
    print(f"- paths: real={out['real_payload_path']} (gitignored={out['real_payload_gitignored']}) "
          f"example={out['example_payload_path']}")
    print(f"- operator_event: status={out['operator_event_status']} confirmation_valid={out['confirmation_valid']} "
          f"live_status={out['official_news_live_status']}")
    print(f"- production_candidate: status={out['production_candidate_status']} "
          f"frozen={out['production_frozen_pair_count']} handoff_ready={out['reviewer_handoff_ready']}")
    print(f"- r1: production_gold={out['production_gold_count']} gap={out['current_r1_gap']} "
          f"sending={out['actual_sending_performed']} r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- blocked_reason: {out['blocked_reason'] or '(none)'}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

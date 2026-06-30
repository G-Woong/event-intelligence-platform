"""ADR#92 §11 — first freeze package hardening (첫 freeze artifact 가 reviewer-facing safe 한지 강하게 검증·truth/gold 0).

문제(ADR#84~#87): 첫 production-candidate freeze 가 성공하면 그 결과는 사람 reviewer 에게 가는 **worklist** 다.
reviewer 는 official 증거 title vs news 보도 title 을 봐야 same-event 를 판정하지만(title 필요), 그 artifact 에
score/rationale/predicted_status/same_event 단정/raw body/reviewer PII/secret 이 섞이면 편향·유출이다. freeze 는
reviewer worklist 일 뿐 truth/gold 가 아니다 — 그 경계를 freeze 직전 강하게 검사해야 한다.

이 모듈은 freeze-eligible reviewer worklist pair(official_record × news_record)를 받아 **reviewer-facing 안전성**을
검사한다(`_assert_pii_safe` 는 key명 전용 재귀 가드이므로, 그 위에 (1)forbidden-key 부재 (2)same_event/merge 미단정
(3)official/news role 설명·canonical·published_at·source_role 존재 (4)production_gold_count 불변을 **모두** 검사한다):
  - score/rationale/predicted_status/raw_body/reviewer PII/secret 키가 어떤 depth 든 있으면 unsafe(blocked_reason).
  - same_event/merge/kg_edge/public_iu 가 truthy 면 unsafe(freeze ≠ truth ≠ merge).
  - official/news 두 record 가 각각 canonical_url·published_at·role 표식을 가져야 한다(증거 불완전 → unsafe).
  - production_gold_count 는 freeze 전후 불변(freeze 가 gold 를 만들지 않는다).
  불변: same_event 단정 0 · merge 0 · production_gold_count 불변 · network 0 · 출력 PII/secret 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.reviewer_pilot_handoff import _HANDOFF_FORBIDDEN_KEYS, _assert_pii_safe

OPERATION_NAME = "first_freeze_package_hardening"

# freeze_package_hardening_status.
FH_SAFE = "freeze_artifact_reviewer_safe"
FH_UNSAFE = "freeze_artifact_unsafe_blocked"
FH_NO_ARTIFACT = "no_freeze_artifact_to_harden"

# same_event/merge truth 단정으로 간주하는 키(어떤 depth 든 truthy 면 unsafe).
_SAME_EVENT_KEYS = frozenset({"same_event_asserted", "same_event"})
_MERGE_KEYS = frozenset({"merge_allowed", "kg_edge_allowed", "public_iu_allowed"})

# reviewer worklist record 가 담아도 되는 키(양성 allowlist·adversarial Finding A). forbidden-key 가드는 key명 전용이라
# non-forbidden 키 아래 값-레벨 PII/secret(예: {"note": "reviewer@x.com"})을 못 잡는다 — 이 allowlist 는 reviewer 가
# 판정에 필요한 안전 필드만 허용하고 그 외 키를 unsafe 로 표면화한다(operator 가 handoff 전 record 를 줄여야 함).
_RECORD_ALLOWLIST = frozenset({
    "record_type", "source_id", "source_role", "canonical_url",
    "published_at_or_observed_at", "published_at", "title_or_label",
    "shared_tokens",
})


def _record_extra_keys(rec: dict) -> list[str]:
    """record 의 allowlist 밖 키(값-레벨 PII/secret 운반 가능·reviewer-facing 부적합)."""
    return sorted(set(rec) - _RECORD_ALLOWLIST)


def _scan_forbidden_keys(obj: object) -> list[str]:
    """artifact 의 어떤 depth 든 forbidden-key(score/rationale/predicted_status/raw body/PII/secret)를 수집(raise 0·진단)."""
    found: set[str] = set()

    def walk(o: object) -> None:
        if isinstance(o, dict):
            found.update(set(o) & _HANDOFF_FORBIDDEN_KEYS)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return sorted(found)


def _scan_truthy_key(obj: object, keys: frozenset[str]) -> bool:
    """artifact 의 어떤 depth 든 keys 중 하나가 truthy 값으로 있으면 True(same_event/merge 단정 탐지)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and bool(v):
                return True
            if _scan_truthy_key(v, keys):
                return True
    elif isinstance(obj, list):
        for v in obj:
            if _scan_truthy_key(v, keys):
                return True
    return False


def _role_indicator(rec: dict) -> str:
    return str(rec.get("record_type") or rec.get("source_role") or "").strip()


def _canonical(rec: dict) -> str:
    return str(rec.get("canonical_url") or "").strip()


def _published(rec: dict) -> str:
    return str(rec.get("published_at_or_observed_at") or rec.get("published_at") or "").strip()


def build_first_freeze_package_hardening(
    *, artifact: Optional[dict] = None,
    production_gold_count_before: int = 0, production_gold_count_after: int = 0,
) -> dict:
    """freeze-eligible reviewer worklist pair → reviewer-facing 안전성 검사(PURE·network 0·gold 불변).

    artifact = {pair_id, official_record, news_record, shared_tokens, date_proximity_days}(iter_freeze_eligible_record_pairs
    형태). artifact 미제공(아직 freeze 0)이면 FH_NO_ARTIFACT(정직). 검사는 출력에 artifact 본문을 echo 하지 않는다
    (검사 결과 flag/count 만) — 따라서 출력은 forbidden-key 0 으로 `_assert_pii_safe` 통과."""
    pgc_before = int(production_gold_count_before)
    pgc_after = int(production_gold_count_after)
    production_gold_count_unchanged = pgc_before == pgc_after

    art = artifact if isinstance(artifact, dict) else None
    official = art.get("official_record") if (art and isinstance(art.get("official_record"), dict)) else {}
    news = art.get("news_record") if (art and isinstance(art.get("news_record"), dict)) else {}
    has_both_records = bool(official) and bool(news)

    leaked = _scan_forbidden_keys(art) if art is not None else []
    artifact_asserts_same_event = _scan_truthy_key(art, _SAME_EVENT_KEYS) if art is not None else False
    artifact_allows_merge = _scan_truthy_key(art, _MERGE_KEYS) if art is not None else False

    source_role_present = bool(_role_indicator(official)) and bool(_role_indicator(news))
    canonical_present = bool(_canonical(official)) and bool(_canonical(news))
    published_at_present = bool(_published(official)) and bool(_published(news))
    official_news_role_explanation_present = has_both_records and source_role_present
    # 양성 allowlist(Finding A) — record 가 reviewer-safe 필드만 담는지(임의 키 아래 값-레벨 PII/secret 차단).
    official_extra = _record_extra_keys(official) if has_both_records else []
    news_extra = _record_extra_keys(news) if has_both_records else []
    record_schema_clean = has_both_records and not official_extra and not news_extra

    # per-category hidden flags(forbidden-key 부재).
    score_hidden = not ({"score", "model_score"} & set(leaked))
    rationale_hidden = "rationale" not in leaked
    predicted_status_hidden = "predicted_status" not in leaked
    raw_body_hidden = not ({"raw_body", "body"} & set(leaked))
    reviewer_pii_hidden = not ({"reviewer_name", "name", "email", "phone"} & set(leaked))
    secret_hidden = not ({"secret", "api_key", "provider_secret"} & set(leaked))

    reasons: list[str] = []
    if art is None or not has_both_records:
        status = FH_NO_ARTIFACT
        reasons.append("no official/news freeze worklist pair to harden")
        if leaked:   # Finding B — 불완전 artifact 의 leak 도 진단에 명시(safe 아님은 NO_ARTIFACT 가 이미 보장).
            reasons.append(f"forbidden keys present in the partial artifact: {leaked}")
    else:
        if leaked:
            reasons.append(f"forbidden keys leaked in artifact: {leaked}")
        if not record_schema_clean:
            reasons.append("non-allowlisted record fields (may carry PII/secret values): "
                           f"official={official_extra} news={news_extra}")
        if artifact_asserts_same_event:
            reasons.append("artifact asserts same_event (freeze is reviewer worklist, not truth)")
        if artifact_allows_merge:
            reasons.append("artifact allows merge/kg_edge/public_iu (forbidden before MERGE_GATE)")
        if not official_news_role_explanation_present:
            reasons.append("official/news role explanation missing (need both records with a role indicator)")
        if not canonical_present:
            reasons.append("canonical_url missing on the official or news record")
        if not published_at_present:
            reasons.append("published_at missing on the official or news record")
        if not source_role_present:
            reasons.append("source_role/record_type missing on the official or news record")
        if not production_gold_count_unchanged:
            reasons.append("production_gold_count changed during freeze (freeze must not create gold)")
        status = FH_SAFE if not reasons else FH_UNSAFE

    freeze_artifact_safe = status == FH_SAFE
    blocked_reason = reasons[0] if reasons else ""
    if freeze_artifact_safe:
        operator_next_action = (
            "the freeze worklist is reviewer-safe — manually distribute it to >=2 pseudonymous reviewers per pair and "
            "collect returned labels (no system sending); production gold stays 0 until those human labels pass agreement")
    elif status == FH_NO_ARTIFACT:
        operator_next_action = (
            "no freeze artifact yet — acquire in-window official×news publishable pairs and freeze a production candidate "
            "before hardening")
    else:
        operator_next_action = f"fix the freeze artifact before reviewer contact: {blocked_reason}"

    out = {
        "operation_name": OPERATION_NAME,
        "freeze_package_hardening_status": status,
        "freeze_artifact_safe": freeze_artifact_safe,
        "blocked_reason": blocked_reason,
        "all_blockers": reasons,
        "operator_next_action": operator_next_action,
        "reviewer_instruction_ready": freeze_artifact_safe,
        # 개별 검사 결과(투명·테스트).
        "freeze_is_reviewer_worklist_only": True,
        "official_news_role_explanation_present": official_news_role_explanation_present,
        "canonical_present": canonical_present,
        "published_at_present": published_at_present,
        "source_role_present": source_role_present,
        "record_schema_clean": record_schema_clean,
        "non_allowlisted_record_fields": {"official": official_extra, "news": news_extra},
        "score_hidden": score_hidden,
        "rationale_hidden": rationale_hidden,
        "predicted_status_hidden": predicted_status_hidden,
        "raw_body_hidden": raw_body_hidden,
        "reviewer_pii_hidden": reviewer_pii_hidden,
        "secret_hidden": secret_hidden,
        "leaked_forbidden_keys": leaked,
        "artifact_asserts_same_event": artifact_asserts_same_event,
        "artifact_allows_merge": artifact_allows_merge,
        "production_gold_count_unchanged": production_gold_count_unchanged,
        # ── 불변 경계(정직·constant·모듈은 truth/merge/gold 를 만들지 않는다) ──
        "same_event_asserted": False,
        "merge_allowed": False,
        "production_gold_count": pgc_after,
        "network_invoked": False,
    }
    _assert_pii_safe(out, _path="first_freeze_package_hardening_output")
    return out


def sanitized_first_freeze_package_hardening(out: dict) -> dict:
    """frontier 용 aggregate-only 투영(status + safe flag + blocker 만)."""
    return {
        "freeze_package_hardening_status": out["freeze_package_hardening_status"],
        "freeze_artifact_safe": out["freeze_artifact_safe"],
        "blocked_reason": out["blocked_reason"],
        "production_gold_count_unchanged": out["production_gold_count_unchanged"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#92 first freeze package hardening (freeze worklist pair reviewer-facing 안전성 검사; "
                     "score/rationale/predicted/same_event/raw body/PII/secret 차단·gold 불변·network 0)."))
    parser.add_argument("--artifact-json", metavar="PATH", help="freeze worklist pair JSON 파일 경로(미지정 시 stdin).")
    parser.add_argument("--gold-before", type=int, default=0)
    parser.add_argument("--gold-after", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    artifact: Optional[dict] = None
    if ns.artifact_json:
        with open(ns.artifact_json, encoding="utf-8") as f:
            artifact = json.load(f)
    else:
        data = sys.stdin.read().strip()
        artifact = json.loads(data) if data else None
    out = build_first_freeze_package_hardening(
        artifact=artifact, production_gold_count_before=ns.gold_before, production_gold_count_after=ns.gold_after)
    if ns.json:
        print(json.dumps(sanitized_first_freeze_package_hardening(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['freeze_package_hardening_status']} "
          f"safe={out['freeze_artifact_safe']}")
    print(f"- official_news_role_explanation_present={out['official_news_role_explanation_present']} "
          f"canonical={out['canonical_present']} published_at={out['published_at_present']} "
          f"source_role={out['source_role_present']}")
    print(f"- score_hidden={out['score_hidden']} rationale_hidden={out['rationale_hidden']} "
          f"raw_body_hidden={out['raw_body_hidden']} reviewer_pii_hidden={out['reviewer_pii_hidden']} "
          f"secret_hidden={out['secret_hidden']}")
    print(f"- production_gold_count_unchanged={out['production_gold_count_unchanged']} "
          f"production_gold_count={out['production_gold_count']}")
    print(f"- blocked_reason: {out['blocked_reason']}")
    print(f"- operator_next_action: {out['operator_next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

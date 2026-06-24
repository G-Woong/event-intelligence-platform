"""Export semantic adjudication pairs → internal JSONL (ADR#43, R-IdentityEvalDataset / adjudication 소비처).

ADR#42 `event_identity_adjudication` 테이블은 저장만 되고 소비처가 0(report 휘발성=dead-data 잔여). 이 도구는
그 테이블을 소비해 **human-labeling 워크시트 JSONL**을 만든다 — 사람이 gold label 을 달아 `identity_eval_pairs.jsonl`
(R-IdentityEvalDataset)로 승격할 입력. **internal-only**(public API 미노출)·**raw body/PII 금지**(제목 헤드라인만)·
결정론(정렬 link_id). 자동 병합 0(read-only).

worksheet schema = eval pair 키 + `predicted_status`/`score`/`reason`(검토 보조) + `label="unlabeled"`. label 이
gold(GOLD_LABELS)가 아니라서 `load_eval_pairs` 가 그대로 로드하지 않는다 — 사람이 label 을 채우고 보조 키를
제거해야 gold set 이 된다(의도된 분리: 워크시트 ≠ gold).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.event_resolution import (
    EventIdentityAdjudicationORM,
    EventLinkORM,
)
from backend.app.models.event_timeline import EventORM, EventUpdateORM
from backend.app.services.identity_eval_dataset import SOURCE_TYPES
from backend.app.services.semantic_identity_adjudicator import SEMANTIC_LINK_REASON, _language_hint

# worksheet 행 허용 키 — body/raw_text/content/author 등은 구조적으로 제외(raw≠eval, PII 차단).
_WORKSHEET_KEYS = frozenset({
    "pair_id", "label", "language", "source_type_left", "source_type_right",
    "title_left", "title_right", "observed_at_left", "observed_at_right",
    "predicted_status", "score", "reason", "risk_tags",
})
# _language_hint 는 **script** 라벨(latin/ko/mixed/unknown)을 주는데, eval dataset 의 language enum 은
# **언어**(en/ko/mixed/unknown)다. 워크시트가 gold(identity_eval_pairs.jsonl)로 승격될 때 enum 검증을
# 통과하도록 script→language 정규화(latin→en). 이게 없으면 영어 워크시트가 `invalid language 'latin'`로 거부됨.
_SCRIPT_TO_EVAL_LANGUAGE = {"latin": "en"}

# evidence 레이어 source_type → identity eval enum(SOURCE_TYPES) 정규화. evidence/adjudicator 는 market 신호를
# 'signal' 로 저장하나 eval enum 은 'market' 을 쓴다(언어 정규화와 동형 경계 변환). 이게 없으면 라이브 market/혼합
# 후보가 gold/reviewer/packet 승격 시 `invalid source_type 'signal'` 로 **전량 거부**(market_guard bucket 라이브 0).
_EVIDENCE_TO_EVAL_SOURCE_TYPE = {"signal": "market"}


def _to_eval_source_type(raw: str) -> str:
    """evidence source_type → eval enum(SOURCE_TYPES) 보장값. 미지/미매핑은 'unknown'(fail-closed·enum 위반 0)."""
    st = _EVIDENCE_TO_EVAL_SOURCE_TYPE.get(raw, raw)
    return st if st in SOURCE_TYPES else "unknown"


async def _event_brief(session: AsyncSession, event_id) -> Optional[dict]:
    """event_id → {title, observed_at, source_type}(read-only·본문/PII 비포함). 없으면 None."""
    row = (
        await session.execute(
            select(EventORM.canonical_title, EventORM.first_seen_at).where(EventORM.id == event_id)
        )
    ).first()
    if row is None:
        return None
    ev_rows = (
        await session.execute(
            select(EventUpdateORM.evidence).where(EventUpdateORM.event_id == event_id)
        )
    ).scalars().all()
    stype = ""
    for evidence in ev_rows:
        for node in evidence or ():
            if isinstance(node, dict) and isinstance(node.get("source_type"), str) and node["source_type"]:
                stype = node["source_type"]
                break
        if stype:
            break
    return {
        "title": (row[0] or "")[:512],
        "observed_at": row[1].isoformat() if row[1] is not None else "",
        "source_type": stype or "unknown",
    }


async def collect_adjudication_eval_pairs(session: AsyncSession) -> list[dict]:
    """semantic 후보 link 의 adjudication 행 → human-labeling 워크시트 dict 목록(소비처). 결정론(link_id 정렬).

    raw body/PII 미포함(제목 헤드라인·source_type·시점만). label='unlabeled'(사람이 채움). Event 소실 link skip."""
    rows = (
        await session.execute(
            select(
                EventIdentityAdjudicationORM.link_id,
                EventIdentityAdjudicationORM.status,
                EventIdentityAdjudicationORM.score,
                EventIdentityAdjudicationORM.reason,
                EventLinkORM.event_id,
                EventLinkORM.linked_event_id,
            )
            .join(EventLinkORM, EventLinkORM.id == EventIdentityAdjudicationORM.link_id)
            .where(EventLinkORM.reason == SEMANTIC_LINK_REASON)
            .order_by(EventIdentityAdjudicationORM.link_id.asc())
        )
    ).all()
    out: list[dict] = []
    for link_id, status, score, reason, cand_id, exist_id in rows:
        left = await _event_brief(session, cand_id)
        right = await _event_brief(session, exist_id)
        if left is None or right is None:
            continue
        _lang = _language_hint(left["title"], right["title"])
        out.append({
            "pair_id": str(link_id),
            "label": "unlabeled",
            "language": _SCRIPT_TO_EVAL_LANGUAGE.get(_lang, _lang),   # script→eval language(latin→en)
            "source_type_left": _to_eval_source_type(left["source_type"]),    # signal→market(enum 보장)
            "source_type_right": _to_eval_source_type(right["source_type"]),
            "title_left": left["title"],
            "title_right": right["title"],
            "observed_at_left": left["observed_at"],
            "observed_at_right": right["observed_at"],
            "predicted_status": status,
            "score": score,
            "reason": reason,
            "risk_tags": [],
        })
    return out


def _assert_no_pii(rows: list[dict]) -> None:
    """worksheet 행이 allowlist 키만 갖는지(raw body/PII 차단) 방어 검증."""
    for r in rows:
        extra = set(r) - _WORKSHEET_KEYS
        if extra:
            raise ValueError(f"worksheet row has disallowed keys (PII/body 차단): {sorted(extra)}")


def write_worksheet_jsonl(rows: list[dict], path: Any) -> int:
    """워크시트 행 → JSONL(internal artifact). 반환=행 수. allowlist 키 검증 후 기록."""
    _assert_no_pii(rows)
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows]
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(rows)


def summarize_adjudication_backlog(rows: list[dict]) -> dict:
    """워크시트 backlog 분포(by predicted_status·by_language) — internal 모니터링(소비처)."""
    by_status: dict[str, int] = {}
    by_language: dict[str, int] = {}
    for r in rows:
        by_status[r["predicted_status"]] = by_status.get(r["predicted_status"], 0) + 1
        by_language[r["language"]] = by_language.get(r["language"], 0) + 1
    return {"total": len(rows), "by_status": by_status, "by_language": by_language, "auto_merged": 0}

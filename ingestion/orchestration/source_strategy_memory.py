"""소스별 수집 전략 메모리 (Phase E-3, 설계 03/08).

unresolved killer 루프가 각 source에 대해 **어떤 전략이 살렸고 어떤 전략이 실패했는지**를
학습해 저장한다. 단순 보고서가 아니라, 다음 실행에서 StrategyRouter/runner가
``preferred_strategy_for(source_id)``로 참조해 무의미한 전략 반복을 피한다.

  - canonical config: ``ingestion/configs/source_strategy_memory.yaml`` (커밋, secret 없음)
  - run output    : ``ingestion/outputs/tmp_source_strategy_learning/<run_id>/...`` (gitignored)

원칙: secret 값을 저장하지 않는다(키 이름/값 금지). stdlib + pyyaml(기설치)만. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass(frozen=True)
class SourceStrategyMemory:
    source_id: str
    previous_status: str
    final_status: str
    root_cause_before: tuple[str, ...] = ()
    root_cause_after: tuple[str, ...] = ()
    successful_strategy: Optional[str] = None
    failed_strategies: tuple[str, ...] = ()
    preferred_next_strategy: Optional[str] = None
    adapter_name: Optional[str] = None
    body_fetch_strategy: Optional[str] = None
    browser_strategy: Optional[str] = None
    parser_notes: Optional[str] = None
    cooldown_policy: Optional[str] = None
    safety_policy: str = "no_bypass"
    evidence: Optional[str] = None
    # G-4: 추후 LLM SourceSupervisor가 재사용할 전략 힌트(예: never_disable_on_single_429).
    # 사실/정책 힌트만, secret/키 금지. 비어 있으면 YAML 직렬화에서 생략(기존 entry 무변경).
    llm_agent_hints: tuple[str, ...] = ()


def _to_plain(m: SourceStrategyMemory) -> dict:
    d = asdict(m)
    # tuple → list(YAML 가독성). None은 그대로.
    for k, v in list(d.items()):
        if isinstance(v, tuple):
            d[k] = list(v)
    # 비어 있는 llm_agent_hints는 생략 — 힌트 없는 기존 entry의 diff noise 방지.
    if not d.get("llm_agent_hints"):
        d.pop("llm_agent_hints", None)
    return d


def _from_plain(d: dict) -> SourceStrategyMemory:
    def tup(k):
        v = d.get(k) or []
        return tuple(v) if isinstance(v, (list, tuple)) else (v,)
    return SourceStrategyMemory(
        source_id=d["source_id"],
        previous_status=d.get("previous_status", ""),
        final_status=d.get("final_status", ""),
        root_cause_before=tup("root_cause_before"),
        root_cause_after=tup("root_cause_after"),
        successful_strategy=d.get("successful_strategy"),
        failed_strategies=tup("failed_strategies"),
        preferred_next_strategy=d.get("preferred_next_strategy"),
        adapter_name=d.get("adapter_name"),
        body_fetch_strategy=d.get("body_fetch_strategy"),
        browser_strategy=d.get("browser_strategy"),
        parser_notes=d.get("parser_notes"),
        cooldown_policy=d.get("cooldown_policy"),
        safety_policy=d.get("safety_policy", "no_bypass"),
        evidence=d.get("evidence"),
        llm_agent_hints=tup("llm_agent_hints"),
    )


def save_strategy_memory(entries: list[SourceStrategyMemory], path: Path, *,
                         run_id: Optional[str] = None) -> Path:
    """memory entries를 YAML로 저장(source_id 정렬). 디렉터리 자동 생성."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": 1,
        "run_id": run_id,
        "entries": [_to_plain(m) for m in sorted(entries, key=lambda x: x.source_id)],
    }
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def load_strategy_memory(path: Path) -> dict[str, SourceStrategyMemory]:
    """YAML memory를 {source_id: SourceStrategyMemory}로 로드. 없으면 빈 dict."""
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    out: dict[str, SourceStrategyMemory] = {}
    for d in doc.get("entries", []) or []:
        if isinstance(d, dict) and d.get("source_id"):
            out[d["source_id"]] = _from_plain(d)
    return out


def preferred_strategy_for(source_id: str, memory: dict[str, SourceStrategyMemory]) -> Optional[str]:
    """다음 실행에서 우선 적용할 전략(없으면 None). StrategyRouter/runner consumer 진입점.

    - 성공한 전략이 있으면 그것을 우선(같은 전략을 자동 선택).
    - 없으면 preferred_next_strategy(실패 학습 기반 다음 후보).
    """
    m = memory.get(source_id)
    if m is None:
        return None
    return m.successful_strategy or m.preferred_next_strategy


def is_known_dead_end(source_id: str, memory: dict[str, SourceStrategyMemory]) -> bool:
    """이전에 정책/외부/도구/계약/서비스가치로 닫힌 source인지(무의미 전략 반복 회피)."""
    from ingestion.orchestration.full_source_revival import (
        DATA_ALIVE_STATUSES,
    )
    m = memory.get(source_id)
    if m is None:
        return False
    # data-alive가 아니고 terminal로 닫힌 경우 = 같은 전략 재시도 무의미.
    return m.final_status not in DATA_ALIVE_STATUSES and m.successful_strategy is None

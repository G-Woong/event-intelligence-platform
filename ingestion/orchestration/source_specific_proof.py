"""Phase G-4 SourceSpecificProof — source별 EventQueue/raw_events contract 통과 증명.

문제: production dedup index는 영속·공유되므로, 재실행 시 동일 content_hash가 collapse되어
culture_info/product_hunt의 eq/raw가 0으로 보일 수 있다(= dedup된 것이지 contract 실패 아님).

해법: **격리된(fresh) dedup namespace**로 해당 source의 live record만 EventQueue→raw_events
bridge에 통과시켜, "이 source의 record가 contract를 통과한다"는 source-specific proof를 남긴다.
production dedup 정책은 건드리지 않는다(proof namespace는 별도 path/메모리).

네트워크 0(주입된 record만 사용). stdlib + 기존 orchestration 모듈. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from ingestion.orchestration.bridge_to_raw_events import RawEventBridgeWriter, bridge_records
from ingestion.orchestration.eventqueue_dedup import DedupIndex


@dataclass(frozen=True)
class SourceProofResult:
    source_id: str
    live_records: int
    eventqueue_proof: int
    duplicates_in_proof: int
    raw_events_proof: int
    bridge_contract_pass: bool
    proof_namespace: str

    def to_dict(self) -> dict:
        return asdict(self)


def prove_source_eventqueue_contract(
    source_id: str,
    records: list,
    *,
    dedup_path: Optional[str | Path] = None,
    mirror_path: Optional[str | Path] = None,
    collected_at: Optional[str] = None,
) -> SourceProofResult:
    """source의 live record를 격리 dedup namespace로 EventQueue→raw_events에 적재해 contract 증명.

    dedup_path=None이면 메모리상 fresh index(공유 production index와 분리). mirror_path가 있으면
    proof mirror JSONL을 별도 파일로 기록(gitignored outputs). production index/mirror는 건드리지 않는다.
    """
    namespace = f"proof:{source_id}"
    index = DedupIndex(path=dedup_path)   # path=None → fresh 격리 namespace
    written: list[dict] = []
    duplicates = 0
    for i, rec in enumerate(records):
        d = index.decide(rec, ref=f"{namespace}:{i}")
        if d.is_duplicate:
            duplicates += 1
            continue
        rec = dict(rec)
        rec["_dedup_key"] = d.record_key
        written.append(rec)
    if dedup_path is not None:
        index.save()
    writer = RawEventBridgeWriter(mirror_path=mirror_path)
    bridge = bridge_records(written, writer=writer, collected_at=collected_at)
    return SourceProofResult(
        source_id=source_id,
        live_records=len(records),
        eventqueue_proof=len(written),
        duplicates_in_proof=duplicates,
        raw_events_proof=bridge.get("raw_events_written", 0),
        bridge_contract_pass=bool(bridge.get("bridge_contract_pass", False)),
        proof_namespace=namespace,
    )

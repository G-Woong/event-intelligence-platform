from __future__ import annotations

from typing import Any, Optional

from ingestion.fetch_strategies.models import CollectionProbeResult

# 수집 성공으로 간주해 사건 후보(seed)로 큐에 적재하는 상태.
# 실패/차단/쿨다운 상태는 큐에 넣지 않고 CycleReport에만 기록한다(다운스트림 오염 방지).
SUCCESS_STATUSES = frozenset({"LIVE_SUCCESS", "LIVE_PARTIAL"})


def _endpoint_for(source_id: str) -> str:
    """소스 엔드포인트(RSS/API URL)를 반환. 미등록/오류 시 빈 문자열.

    collection_probe.py와 동일한 _SERVICE_CONFIGS를 출처로 쓴다(일관성).
    """
    try:
        from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS
        return (_SERVICE_CONFIGS.get(source_id) or {}).get("endpoint", "")
    except Exception:
        return ""


def to_event_seed(
    result: CollectionProbeResult,
    *,
    query: Optional[str],
    cycle_id: str,
    timestamp: str,
) -> dict[str, Any]:
    """CollectionProbeResult → EventSeedCandidate dict (docs 05 §2).

    주의(코드 실측): probe 결과는 ``items_found``(개수)와 ``artifact_paths``(디스크 참조)만
    담고 개별 기사 항목 리스트를 담지 않는다. 따라서 ``source_url``은 개별 기사 URL이 아니라
    이 수집 결과의 출처(소스 엔드포인트)이며, 개별 사건 분해는 다운스트림/Phase D에서
    artifact를 파싱해 수행한다. seed는 "이 소스를 이 시각에 수집했고 N개를 찾았으며
    원문 artifact는 여기 있다"는 사건 후보 신호다.

    ``_id``/``_status``는 EventQueue가 부여하므로 여기서 넣지 않는다.
    """
    ap = result.artifact_paths
    pr = result.probe_result
    # items_extracted는 ProbeResult에만 존재(CollectionProbeResult에는 없음). 없으면 None.
    items_extracted = pr.items_extracted if pr is not None else None
    body_missing = result.items_found == 0
    return {
        # ── MVP 필수 5필드 (Phase A — 이것만으로 큐 동작) ──
        "title_or_keyword": query or result.source_id,
        "source_url": _endpoint_for(result.source_id),
        "timestamp": timestamp,
        "source_id": result.source_id,
        # ── 권장 확장 (근거추적/품질/디버깅) ──
        "cycle_id": cycle_id,
        "collection_status": result.status,
        "items_found": result.items_found,
        "items_extracted": items_extracted,
        "strategy_used": result.strategy_used,
        "error_type": result.error_category,
        "body_missing": body_missing,
        # raw/extracted artifact가 없으면 None(없는 데이터를 만들지 않는다).
        "raw_artifact_path": ap.raw_payload or ap.raw_html or ap.raw_signal,
        "extracted_text_ref": ap.extracted_payload,
        # 개별 기사 URL은 source-level seed 단계에서 미상 → None.
        # url_resolver 연결은 Phase C/D(개별 사건 분해 시).
        "canonical_url": None,
    }

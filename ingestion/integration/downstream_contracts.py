"""P0 통합 계약 단일 출처 — record_type ↔ raw_events ↔ stream payload.

bridge_to_raw_events(매핑) / backend raw_events(스키마) / workers producer(stream)의 계약을
한 곳에서 재확인한다. 가정하지 않고 실제 코드 계약을 그대로 따른다.

  - RawEventCreate(backend/app/schemas/raw_events.py): source_type, source_name, url(필수),
    content_hash(필수), external_id, title, raw_text(""), published_at, raw_metadata.
  - stream:raw_events payload(workers/queue/producer.py): source, url, fetched_at, raw_text,
    raw_metadata(json), raw_event_id. record_type/dedup_key/corroboration 은 raw_metadata 안.

source 특성별 필수 필드는 raw_metadata 까지 포함해 검증한다(article/official/structured/
community/search). 네트워크 0, stdlib 만.
"""
from __future__ import annotations

from typing import Any

from ingestion.orchestration.bridge_to_raw_events import _RECORD_TYPE_TO_SOURCE_TYPE

# record_type ↔ source_type (bridge 단일 출처 재노출)
RECORD_TYPE_TO_SOURCE_TYPE: dict[str, str] = dict(_RECORD_TYPE_TO_SOURCE_TYPE)
SUPPORTED_RECORD_TYPES = frozenset(RECORD_TYPE_TO_SOURCE_TYPE.keys())

# write 결과 상태(설계 §8)
WRITE_CREATED = "WRITE_CREATED"
WRITE_DUPLICATE_COLLAPSED = "WRITE_DUPLICATE_COLLAPSED"
WRITE_HELD_MISSING_URL = "WRITE_HELD_MISSING_URL"
WRITE_REJECTED_POLICY = "WRITE_REJECTED_POLICY"
WRITE_FAILED_SCHEMA = "WRITE_FAILED_SCHEMA"
WRITE_FAILED_TRANSPORT = "WRITE_FAILED_TRANSPORT"

PUBLISH_SUCCEEDED = "PUBLISH_SUCCEEDED"
PUBLISH_FAILED_RETRYABLE = "PUBLISH_FAILED_RETRYABLE"
PUBLISH_FAILED_FATAL = "PUBLISH_FAILED_FATAL"

# community(익명 커뮤니티) 신호는 verified article 이 아니라 early signal.
# confirmation_policy 가 아래 값이면 외부 교차확인 전 publish 차단(B측 publish_or_hold 가 소비).
CORROBORATION_REQUIRED_POLICIES = frozenset(
    {"unconfirmed_until_corroborated", "internal_queue_only", "publish_blocked_until_corrob"}
)

# RawEventCreate top-level("top") 또는 raw_metadata("meta")에 반드시 있어야 하는 필드.
# url/content_hash/source_name 은 모든 타입 공통(스키마 필수).
_COMMON_TOP = ("source_type", "source_name", "url", "content_hash")
RECORD_TYPE_REQUIRED_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    "article_candidate": {"top": _COMMON_TOP + ("title", "published_at"),
                          "meta": ("record_type", "dedup_key", "evidence_ref")},
    "official_record": {"top": _COMMON_TOP + ("title",),
                        "meta": ("record_type", "dedup_key", "evidence_ref")},
    "structured_signal": {"top": _COMMON_TOP,
                          "meta": ("record_type", "dedup_key", "structured_payload", "observed_at")},
    "community_signal": {"top": _COMMON_TOP + ("title",),
                        "meta": ("record_type", "dedup_key", "confirmation_policy")},
    "search_result": {"top": _COMMON_TOP,
                      "meta": ("record_type", "dedup_key", "evidence_ref")},
}


def validate_raw_event_create(create: dict, record_type: str) -> tuple[bool, list[str]]:
    """RawEventCreate dict(+raw_metadata)가 record_type 별 필수 필드를 갖췄는지 검증.

    반환: (ok, missing). missing 은 "top:field" 또는 "meta:field" 형태. 값이 None/빈 문자열이면
    누락으로 본다(raw_text 는 의도적 빈 문자열이라 예외). structured_payload 는 dict 존재만 확인.
    """
    spec = RECORD_TYPE_REQUIRED_FIELDS.get(record_type)
    if spec is None:
        return False, [f"unsupported_record_type:{record_type}"]
    meta = create.get("raw_metadata") or {}
    missing: list[str] = []
    for f in spec["top"]:
        v = create.get(f)
        if v is None or (isinstance(v, str) and v == ""):
            missing.append(f"top:{f}")
    for f in spec["meta"]:
        v = meta.get(f)
        if v is None or (isinstance(v, str) and v == ""):
            missing.append(f"meta:{f}")
    # source_type 이 record_type 매핑과 일치하는지(둔갑 방지)
    expected_st = RECORD_TYPE_TO_SOURCE_TYPE.get(record_type)
    if expected_st and create.get("source_type") != expected_st:
        missing.append(f"top:source_type!={expected_st}")
    return (not missing), missing


def is_corroboration_required(raw_metadata: dict[str, Any] | None) -> bool:
    """raw_metadata 의 confirmation_policy 가 외부확인 강제 정책이면 True(publish 차단 대상)."""
    if not raw_metadata:
        return False
    policy = raw_metadata.get("confirmation_policy")
    if policy in CORROBORATION_REQUIRED_POLICIES:
        return True
    # bridge 가 community → source_type=community 로 매핑. 명시 플래그도 인정.
    if raw_metadata.get("corroboration_required") is True:
        return True
    return False


# stream:raw_events payload 필수 키(workers/queue/producer.py 계약)
STREAM_PAYLOAD_REQUIRED_KEYS = ("source", "url", "fetched_at", "raw_text", "raw_metadata", "raw_event_id")


def validate_stream_payload(payload: dict) -> tuple[bool, list[str]]:
    """downstream worker 가 소비하는 stream payload 계약 검증(producer 와 동일 키셋)."""
    missing = [k for k in STREAM_PAYLOAD_REQUIRED_KEYS if k not in payload]
    return (not missing), missing

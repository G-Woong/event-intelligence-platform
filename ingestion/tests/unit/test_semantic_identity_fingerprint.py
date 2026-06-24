"""deterministic semantic identity fingerprint 단위 (ADR#41, R-CrossBatchEventIdentity).

`semantic_identity_fingerprint(title, observed_at)` 는 공유 strong anchor(canonical_url/official_id)가
없어도 같은 사건을 보도하는 두 다른-URL 기사를 cross-batch 로 잇기 위한 **결정론 후보 키**다. 이 키가
같다고 자동 병합하지 않는다(호출부가 event_links possible 로만 링크) — 여기선 키 생성 규칙만 잠근다.

정책(보수·고정밀): 어순 무관(token-set)·stopword 제거·소문자 정규화. **None 조건**: ① 유의미 토큰
< 4(generic) ② date bucket 비어있음(시점 불명 → cross-day 오매칭 차단). `titles_similar` 와 동일 정규화.
stdlib only.
"""
from __future__ import annotations

from ingestion.orchestration.cross_source_dedup import (
    _MIN_SEMANTIC_TOKENS,
    semantic_identity_fingerprint as fp,
)

_DATE = "2026-06-24T10:00:00Z"
_T = "Federal Reserve raises benchmark interest rates today"


def test_same_tokens_same_day_same_fingerprint():
    assert fp(_T, _DATE) == fp(_T, _DATE)
    assert fp(_T, _DATE).startswith("sem:")


def test_word_order_invariant():
    # 어순만 다른 같은 토큰 집합 → 같은 fingerprint(token-set).
    a = fp("Federal Reserve raises benchmark interest rates today", _DATE)
    b = fp("today rates interest benchmark raises Reserve Federal", _DATE)
    assert a == b


def test_case_and_whitespace_invariant():
    a = fp("Federal Reserve Raises Benchmark Interest Rates Today", _DATE)
    b = fp("federal   reserve raises   benchmark interest rates today", _DATE)
    assert a == b


def test_different_day_different_fingerprint():
    # 같은 토큰·다른 날 → 다른 fingerprint(cross-day 오매칭 차단; scenario 4).
    assert fp(_T, "2026-06-24T10:00:00Z") != fp(_T, "2026-06-25T10:00:00Z")


def test_same_day_different_hour_same_fingerprint():
    # 같은 날짜 bucket(시각 무관) → 같은 fingerprint.
    assert fp(_T, "2026-06-24T01:00:00Z") == fp(_T, "2026-06-24T23:00:00Z")


def test_different_tokens_different_fingerprint():
    a = fp(_T, _DATE)
    b = fp("Coastal refinery fire forces mass evacuation nearby", _DATE)
    assert a != b


def test_generic_short_title_none():
    # 유의미 토큰 < _MIN_SEMANTIC_TOKENS → None(generic 충돌 차단).
    assert fp("Market update", _DATE) is None
    assert fp("Breaking news", _DATE) is None
    assert _MIN_SEMANTIC_TOKENS == 4


def test_stopwords_do_not_count_toward_min_tokens():
    # stopword(the/of/to/and...) 는 유의미 토큰에서 제외 → 임계 미달이면 None.
    assert fp("the of to and is are", _DATE) is None


def test_missing_or_unparseable_time_none():
    # 시점 불명(None/빈/파싱 불가) → None(시점 없는 fingerprint 금지).
    assert fp(_T, None) is None
    assert fp(_T, "") is None
    assert fp(_T, "not-a-date") is None


def test_empty_title_none():
    assert fp(None, _DATE) is None
    assert fp("", _DATE) is None


def test_min_tokens_boundary():
    # 정확히 4개 유의미 토큰(stopword 없음) → fingerprint 생성, 3개 → None.
    assert fp("alpha bravo charlie delta", _DATE) is not None      # 4 tokens
    assert fp("alpha bravo charlie", _DATE) is None                # 3 tokens

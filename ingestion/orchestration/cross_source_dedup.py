"""Phase F-8 Cross-source Dedup — 서로 다른 source의 같은 사건을 결정적으로 묶는다.

신규 embedding/vector 의존성을 도입하지 않는다(경량 결정적). 정책:
  - canonical_url 정확히 일치 → duplicate(high)
  - 같은 official id/accession → duplicate(high)
  - 같은 metric signal key(source_group이 달라도 동일 지표 동일 시각) → duplicate(high)
  - normalized title + 같은 날짜 bucket → possible_duplicate(medium)
  - title token Jaccard 높음 + 같은 날짜 → possible_duplicate(medium)

false positive가 위험하면 possible_duplicate로 hold한다(자동 병합하지 않는다). 목적은
EventQueue/raw_events 양쪽에서 같은 사건이 N개 source로 폭주하는 것을 막는 것.

stdlib만. 신규 설치 0.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ingestion.orchestration.eventqueue_dedup import (
    _external_url,
    _official_id,
    compute_record_key,
)
from ingestion.orchestration.time_normalizer import normalize_time

_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")
_TITLE_JACCARD_THRESHOLD = 0.8
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "with",
    "is", "are", "was", "were", "says", "say", "after", "as", "at", "by",
})

CONF_DUPLICATE = "duplicate"
CONF_POSSIBLE = "possible_duplicate"

# core 강성분 선택 시 **발행 가능 출처를 가진 성분을 우선**(ADR#37, P2-2): 두-강성분 약신호 브릿지에서
# publishable 성분이 record_key 사전순 패배로 통째로 WITHHELD 되는 것 차단. 값 계약: event_ingest_pipeline.
# _RECORD_TYPE_TO_SOURCE_TYPE + event_resolver._PUBLISHABLE_SOURCE_TYPES(official/article)와 동기 — drift 테스트로 잠금.
_PUBLISHABLE_RECORD_TYPES = frozenset({"official_record", "article_candidate"})


@dataclass(frozen=True)
class CrossSourceDedupResult:
    cluster_id: str
    duplicate_group: tuple[str, ...]
    primary_record_key: str
    duplicate_record_keys: tuple[str, ...]
    confidence: str
    reason: str
    # S2b (event_resolver 입력) — additive. 기존 소비처 비파괴(기본값 보존).
    signal_strength: float = 0.0          # 클러스터 결합 강도: 강신호=1.0, 아니면 약신호 Jaccard 연속값(orchestrator #2)
    clique_ok: bool = True                # 강신호 단일 연결성분이 전체 멤버를 덮는가(R-FalseMerge: transitive/bridge 흡수 차단)
    weak_only_members: tuple[str, ...] = ()  # 약신호로만 끌려온 멤버 키(clique 미달 → HOLD 후보, provenance)


def _norm_title(title: Optional[str]) -> str:
    return _WS.sub(" ", (title or "").strip().lower())


def _title_tokens(title: Optional[str]) -> frozenset[str]:
    toks = {t for t in _TOKEN.findall((title or "").lower()) if len(t) > 1 and t not in _STOPWORDS}
    return frozenset(toks)


def _date_bucket(record: dict) -> str:
    raw = record.get("published_at_or_observed_at")
    nt = normalize_time(raw) if raw else None
    if nt and nt.value:
        return nt.value[:10]  # YYYY-MM-DD
    return ""


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)  # 낮은 인덱스를 root로(결정성)


def cluster_records(records) -> list[CrossSourceDedupResult]:
    """record 목록 → cross-source 중복 클러스터. 단일 멤버 클러스터는 제외.

    강한 키(canonical/official/signal)로 먼저 union, 그 다음 약한 신호(title+date,
    token Jaccard)로 union하되 약한 결합만으로 묶인 클러스터는 possible_duplicate.
    """
    records = list(records)
    n = len(records)
    if n < 2:
        return []

    keys: list[str] = []
    for i, r in enumerate(records):
        k, _ = compute_record_key(r)
        keys.append(k or f"rec:{i}")

    uf = _UnionFind(n)
    strong_pairs: set[tuple[int, int]] = set()

    # 강한 키 인덱싱
    canon_idx: dict[str, int] = {}
    official_idx: dict[str, int] = {}
    signal_idx: dict[str, int] = {}
    for i, r in enumerate(records):
        canonical = r.get("canonical_url")
        if isinstance(canonical, str) and canonical:
            if canonical in canon_idx:
                uf.union(canon_idx[canonical], i); strong_pairs.add((min(canon_idx[canonical], i), max(canon_idx[canonical], i)))
            else:
                canon_idx[canonical] = i
        oid = _official_id(_external_url(r))
        if oid:
            if oid in official_idx:
                uf.union(official_idx[oid], i); strong_pairs.add((min(official_idx[oid], i), max(official_idx[oid], i)))
            else:
                official_idx[oid] = i
        if (r.get("record_type") == "structured_signal"):
            sig = f"{r.get('body_state_or_signal')}|{_date_bucket(r)}|{_norm_title(r.get('title_or_label'))}"
            if sig in signal_idx:
                uf.union(signal_idx[sig], i); strong_pairs.add((min(signal_idx[sig], i), max(signal_idx[sig], i)))
            else:
                signal_idx[sig] = i

    # 약한 신호: 같은 날짜 bucket 내 title 일치 / token Jaccard
    weak_pairs: set[tuple[int, int]] = set()
    weak_jaccard: dict[tuple[int, int], float] = {}   # pair → Jaccard 연속값(signal_strength 보존, S2b)
    by_bucket: dict[str, list[int]] = {}
    for i, r in enumerate(records):
        b = _date_bucket(r)
        if b:
            by_bucket.setdefault(b, []).append(i)
    for bucket, idxs in by_bucket.items():
        for a_pos in range(len(idxs)):
            for b_pos in range(a_pos + 1, len(idxs)):
                i, j = idxs[a_pos], idxs[b_pos]
                ti, tj = _norm_title(records[i].get("title_or_label")), _norm_title(records[j].get("title_or_label"))
                if not ti or not tj:
                    continue
                pair = (min(i, j), max(i, j))
                jac = 1.0 if ti == tj else _jaccard(
                    _title_tokens(records[i].get("title_or_label")),
                    _title_tokens(records[j].get("title_or_label")),
                )
                if jac >= _TITLE_JACCARD_THRESHOLD:
                    uf.union(i, j)
                    weak_pairs.add(pair)
                    weak_jaccard[pair] = max(weak_jaccard.get(pair, 0.0), jac)

    # 클러스터 수집
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    out: list[CrossSourceDedupResult] = []
    for root, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        # 멤버를 **레코드 키**로 정렬(ADR#37 입력순서 불변): members[0]=최저 인덱스(입력 의존)를 폐기 →
        # cluster_id/primary_record_key/duplicate_group/primary tie-break 가 입력 순서와 무관하게 동일.
        # (R-FalseMerge 약신호 cluster_id split 도 해소.) 동일 키(collapse)는 안정 정렬로 보존.
        members = sorted(members, key=lambda m: keys[m])
        member_set = set(members)
        # 클러스터 내 강신호/약신호 edge(provenance).
        strong_in = [(a, b) for (a, b) in strong_pairs if a in member_set and b in member_set]
        weak_in = [(a, b) for (a, b) in weak_pairs if a in member_set and b in member_set]
        has_strong = bool(strong_in)
        confidence = CONF_DUPLICATE if has_strong else CONF_POSSIBLE
        reason = "strong_key_match" if has_strong else "title_date_similarity"
        # R-FalseMerge clique 게이트(adversarial #1 + B1 교정): 강신호 edge **만으로** 단일 연결성분이
        # 전체 멤버를 덮어야 clique_ok=True. 강성분이 2개 이상이면(두 강성분이 약신호로만 브릿지된
        # 경우 포함) primary(members[0]) 강성분에 속하지 않는 멤버를 weak_only로 분리 → 자동 APPEND
        # 금지(transitive/bridge 흡수 차단). 단순히 "강신호 끝점인가"로 보면 두-강성분 브릿지를 놓친다.
        pos = {m: k for k, m in enumerate(members)}
        suf = _UnionFind(len(members))
        for a, b in strong_in:
            suf.union(pos[a], pos[b])
        # core 강성분 선택(R-FalseMerge fragility 차단, ADR#37): members[0](입력 최저 인덱스)에 고정하면
        # ① 두-강성분 약신호 브릿지에서 어느 성분이 core 인지, ② 단일 강성분+약신호 주변부에서 members[0]이
        # 주변부면 core 가 약신호 singleton 이 되는지가 **입력순서에 의존**한다. 대신 **최대 크기 → (동률 시)
        # publishable 성분 → 멤버 키 최소**(전수 키/타입 기반·입력순서 비의존)로 core 강성분 선정. 크기 우선이라
        # 약하게 붙은 publishable singleton 이 더 큰 강성분을 가로채지 않고(ADR#36 보존), **동률 강성분 사이에서만**
        # publishable 우선 → publishable 성분이 키 사전순 패배로 통째로 WITHHELD 되는 것(P2-2) 차단.
        comp: dict[int, list[int]] = {}
        for p in range(len(members)):
            comp.setdefault(suf.find(p), []).append(p)

        def _comp_has_publishable(poss: list[int]) -> bool:
            return any(records[members[p]].get("record_type") in _PUBLISHABLE_RECORD_TYPES for p in poss)

        primary_root = min(
            comp.items(),
            key=lambda it: (-len(it[1]), not _comp_has_publishable(it[1]), min(keys[members[p]] for p in it[1])),
        )[0]
        weak_only = [m for m in members if suf.find(pos[m]) != primary_root]
        clique_ok = len(weak_only) == 0
        # signal_strength(orchestrator #2): 1비트 양자화 폐기 — 강신호=1.0, 아니면 약신호 Jaccard 연속값.
        if strong_in:
            signal_strength = 1.0
        elif weak_in:
            signal_strength = max(weak_jaccard.get(p, 0.0) for p in weak_in)
        else:
            signal_strength = 0.0
        member_keys = tuple(keys[m] for m in members)
        out.append(CrossSourceDedupResult(
            cluster_id=f"xcluster:{keys[members[0]]}",
            duplicate_group=member_keys,
            primary_record_key=keys[members[0]],
            duplicate_record_keys=tuple(keys[m] for m in members[1:]),
            confidence=confidence,
            reason=reason,
            signal_strength=signal_strength,
            clique_ok=clique_ok,
            weak_only_members=tuple(keys[m] for m in weak_only),
        ))
    return out


def summarize_clusters(clusters) -> dict:
    """클러스터 분포 집계(모니터링/보고용)."""
    clusters = list(clusters)
    dup = sum(1 for c in clusters if c.confidence == CONF_DUPLICATE)
    possible = sum(1 for c in clusters if c.confidence == CONF_POSSIBLE)
    collapsed = sum(len(c.duplicate_record_keys) for c in clusters)
    return {
        "clusters": len(clusters),
        "duplicate_clusters": dup,
        "possible_duplicate_clusters": possible,
        "records_collapsed": collapsed,
    }

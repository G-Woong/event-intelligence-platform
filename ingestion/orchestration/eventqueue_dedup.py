"""Phase F-7 EventQueue Dedup — 같은 record가 큐에 반복 적재되지 않도록 dedup key 관리.

설계 05(EventQueue/저장 스키마)의 dedup 원칙. EventQueue record(build_eventqueue_record가
만든 dict)를 받아 record_type별 안정 키를 만들고, 영속 인덱스(JSON)로 중복을 collapse한다.

dedup key 우선순위(05):
  1. canonical_url
  2. source_url (external)
  3. official record id / filing accession / document id (url에서 추출)
  4. structured signal: source_id + signal_type + observed_at
  5. search result: source_id + normalized_title + url
  6. fallback: source_id + normalized_title + normalized_published_at

원칙: 식별 근거가 전혀 없으면 키를 지어내지 않고 None(=hold). 키가 None이면 dedup 불가로
보고하되 중복으로 단정하지 않는다.

stdlib만(hashlib/re/json). 신규 설치 0.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time as _time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ingestion.orchestration.time_normalizer import normalize_time

# url에서 official document id 추출 패턴(SEC accession / dart rcept / generic ?id=)
_ACCESSION = re.compile(r"(\d{10}-\d{2}-\d{6})")          # SEC EDGAR accession no
_RCEPT = re.compile(r"rcpNo=(\d+)")                       # OpenDART 접수번호
_GENERIC_ID = re.compile(r"[?&](?:id|docId|document_id|contentId|mt20id)=([^&]+)", re.I)
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class DedupDecision:
    record_key: Optional[str]
    is_duplicate: bool
    reason: Optional[str]
    existing_ref: Optional[str]


def _norm_title(title: Optional[str]) -> str:
    if not title:
        return ""
    return _WS.sub(" ", title.strip().lower())


def _hash(*parts: str) -> str:
    basis = "|".join(parts)
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _external_url(record: dict) -> Optional[str]:
    """source_url_or_evidence가 외부 http(s) URL이면 반환(로컬 경로/None 제외)."""
    val = record.get("source_url_or_evidence")
    if isinstance(val, str) and val.startswith(("http://", "https://")):
        return val
    return None


def _official_id(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    for pat in (_ACCESSION, _RCEPT):
        m = pat.search(url)
        if m:
            return m.group(1)
    m = _GENERIC_ID.search(url)
    if m:
        return m.group(1)
    return None


def compute_record_key(record: dict) -> tuple[Optional[str], Optional[str]]:
    """EventQueue record → (dedup_key, basis). 근거 없으면 (None, None).

    basis는 어떤 우선순위로 키가 정해졌는지(canonical_url/source_url/official_id/
    signal/search/fallback) — 보고/디버깅용.
    """
    rt = record.get("record_type") or ""
    source_id = record.get("source_id") or ""

    # 1) canonical_url
    canonical = record.get("canonical_url")
    if isinstance(canonical, str) and canonical:
        return f"canon:{_hash(canonical)}", "canonical_url"

    ext = _external_url(record)

    # 3) official id (official record 우선; url에 식별자 있으면)
    if rt == "official_record":
        oid = _official_id(ext)
        if oid:
            return f"officialid:{source_id}:{_hash(oid)}", "official_id"

    # 4) structured signal: source_id + signal_type + observed_at
    if rt == "structured_signal":
        signal_type = record.get("body_state_or_signal") or "signal"
        observed = record.get("published_at_or_observed_at")
        nt = normalize_time(observed).value if observed else ""
        return f"signal:{_hash(source_id, str(signal_type), nt or '')}", "signal_key"

    # 2) source_url (external) — search/community/article 공통 1차
    if ext:
        if rt == "search_result":
            title = _norm_title(record.get("title_or_label"))
            return f"search:{_hash(source_id, title, ext)}", "search_title_url"
        return f"url:{_hash(ext)}", "source_url"

    # 6) fallback: source_id + normalized_title + normalized_published_at
    title = _norm_title(record.get("title_or_label"))
    published = record.get("published_at_or_observed_at")
    npub = normalize_time(published).value if published else ""
    if not title and not npub:
        return None, None  # 식별 근거 없음 — 키 생성 안 함
    return f"meta:{_hash(source_id, title, npub or '')}", "fallback_title_time"


class DedupIndex:
    """seen dedup key → first ref(jsonl line / record id) 매핑. JSON 영속화."""

    def __init__(self, *, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._seen: dict[str, str] = {}
        if self._path and self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                seen = raw.get("seen") if isinstance(raw, dict) else None
                if isinstance(seen, dict):
                    self._seen = {str(k): str(v) for k, v in seen.items()}
            except (json.JSONDecodeError, OSError):
                self._seen = {}

    def check(self, key: Optional[str]) -> tuple[bool, Optional[str]]:
        """(is_duplicate, existing_ref). 키가 None이면 (False, None)."""
        if key is None:
            return False, None
        ref = self._seen.get(key)
        return (ref is not None, ref)

    def add(self, key: Optional[str], ref: str) -> None:
        if key is not None and key not in self._seen:
            self._seen[key] = ref

    def decide(self, record: dict, *, ref: str) -> DedupDecision:
        """record 1건의 dedup 결정 + (신규면) 인덱스에 등록."""
        key, basis = compute_record_key(record)
        if key is None:
            return DedupDecision(
                record_key=None, is_duplicate=False,
                reason="no_dedup_key", existing_ref=None,
            )
        is_dup, existing = self.check(key)
        if is_dup:
            return DedupDecision(
                record_key=key, is_duplicate=True,
                reason=f"duplicate:{basis}", existing_ref=existing,
            )
        self.add(key, ref)
        return DedupDecision(
            record_key=key, is_duplicate=False,
            reason=f"new:{basis}", existing_ref=None,
        )

    def size(self) -> int:
        return len(self._seen)

    def save(self, path: str | Path | None = None) -> Optional[Path]:
        p = Path(path) if path else self._path
        if p is None:
            return None
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"schema_version": 1, "seen": self._seen}, f, ensure_ascii=False, indent=1)
        try:
            os.replace(tmp, p)
        except PermissionError:
            _time.sleep(0.1)
            os.replace(tmp, p)
        return p


def dedup_records(records, *, index: Optional[DedupIndex] = None) -> list[tuple[dict, DedupDecision]]:
    """record 목록을 순서대로 dedup. index 미지정 시 메모리 인덱스 신규 생성.

    반환: [(record, DedupDecision), ...]. 같은 배치 내 중복도 collapse된다.
    """
    idx = index or DedupIndex()
    out: list[tuple[dict, DedupDecision]] = []
    for i, rec in enumerate(records):
        ref = rec.get("_ref") or f"batch:{i}"
        out.append((rec, idx.decide(rec, ref=ref)))
    return out

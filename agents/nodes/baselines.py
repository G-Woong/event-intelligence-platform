"""LangGraph 노드용 결정론적 baseline (mock 상수 대체, Orchestration 하드닝).

이 모듈은 LLM 없이 동작하는 **결정론적·입력 파생** baseline을 제공한다. 목적은 두 가지다.

1. mock 상수(`[mock-entity-1]`, 고정 `geopolitics/energy/defense`, `[mock] ...`)가 published 카드에
   노출되는 것을 차단한다(05 R-MockCard). baseline 결과는 입력 텍스트에서 파생된 실제 값이다.
2. LLM_PROVIDER="openai"일 때만 LLM이 baseline을 보강한다(노드 측에서 분기). LLM이 없으면(dev/mock)
   이 baseline이 1차 경로다.

주의: 이것은 LLM급 의미 분석이 **아니다**. rule/keyword 기반 baseline이며, 한계를 명시한다.
- entity: 대문자 고유명사 시퀀스 추출(소문자 개체/형태소 분석 없음).
- sector: keyword 매칭(동의어/문맥 추론 없음).
- fact_check: **구조적** 근거 확인(본문 존재 + grounded evidence)이며 의미적 사실검증이 아니다.
"""
from __future__ import annotations

import re

from agents.nodes.evidence_rules import has_grounded_evidence

# 고유명사 시퀀스 선두에서 제거할 일반어(문장 시작 대문자 오탐 완화).
_LEADING_STOPWORDS = frozenset(
    {
        "the", "a", "an", "this", "that", "these", "those", "his", "her", "their",
        "its", "our", "your", "my", "in", "on", "at", "for", "to", "of", "and",
        "but", "or", "as", "by", "with", "from", "after", "before", "while",
        "when", "where", "why", "how", "it", "he", "she", "they", "we", "i",
        "new", "us", "uk", "eu",
    }
)

# 단독으로는 개체로 보지 않는 흔한 대문자 단어.
_ENTITY_NOISE = frozenset(
    {
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
        "January", "February", "March", "April", "May", "June", "July", "August",
        "September", "October", "November", "December", "Reuters", "Bloomberg",
    }
)

# 1+ 대문자 시작 토큰 시퀀스(회사/기관/지명 후보). 약어(SEC, OPEC)도 허용.
_PROPER_NOUN = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,3})\b"
)

# sector → 소문자 keyword. 단순 substring 매칭(단어경계 포함)으로 결정론적.
_SECTOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "energy": ("oil", "gas", "opec", "crude", "lng", "pipeline", "refinery",
               "barrel", "energy", "petroleum", "electricity", "power grid"),
    "finance": ("bank", "fed", "interest rate", "inflation", "bond", "equity",
                "stocks", "ipo", "merger", "acquisition", "earnings", "central bank",
                "treasury", "currency", "forex"),
    "technology": ("chip", "semiconductor", "artificial intelligence", " ai ",
                   "software", "cyber", "cloud", "data center", "tech", "startup"),
    "defense": ("military", "defense", "missile", "troops", "weapon", "nato",
                "army", "navy", "airstrike", "warfare", "armed forces"),
    "health": ("virus", "vaccine", "fda", "drug", "pandemic", "outbreak",
               "hospital", "disease", "clinical"),
    "politics": ("election", "parliament", "sanction", "treaty", "congress",
                 "government", "minister", "president", "senate", "diplomatic"),
    "commodities": ("gold", "copper", "wheat", "metal", "mining", "silver", "corn"),
    "transport": ("airline", "shipping", "port", "freight", "rail", "aviation"),
}

# 코드가 주입하는 mock/fallback 센티넬. 실제 기사 텍스트에는 나타나지 않는 대괄호 토큰만 사용한다
# (자유텍스트의 'synthetic'/'placeholder' 단어 오탐을 피하기 위해 영어 단어는 제외).
_MOCK_SENTINELS = ("[mock", "[fallback", "[skip", "[no title]")


def _iter_texts(*values):
    """문자열/리스트를 평탄화해 소문자 토큰을 순회한다."""
    for v in values:
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            for item in v:
                yield str(item)
        else:
            yield str(v)


def contains_mock_sentinel(*values) -> bool:
    """카드 텍스트 필드(summary/impact/entities 등)에 mock 센티넬이 있으면 True.

    publish 게이트가 이를 호출해, LLM fallback 상수(`[fallback] ...`)나 mock 문자열이 published
    카드로 노출되는 것을 fail-closed로 차단한다(05 R-MockCard, 적대적 리뷰 지적 반영).
    """
    for text in _iter_texts(*values):
        low = text.lower()
        if any(marker in low for marker in _MOCK_SENTINELS):
            return True
    return False

_MAX_ENTITIES = 8
_MAX_SECTORS = 4


def extract_entities(title: str, body: str) -> list[str]:
    """제목+본문에서 대문자 고유명사 시퀀스를 추출한다(결정론적 NER baseline)."""
    text = f"{title}. {body}".strip()
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for match in _PROPER_NOUN.finditer(text):
        phrase = match.group(1).strip(" .-&")
        tokens = phrase.split()
        # 선두 일반어 제거(예: "The European Union" → "European Union").
        while tokens and tokens[0].lower() in _LEADING_STOPWORDS:
            tokens = tokens[1:]
        if not tokens:
            continue
        phrase = " ".join(tokens)
        # 단일 토큰이면 약어(>=2 대문자) 또는 충분히 긴 고유명사만 인정.
        if len(tokens) == 1:
            t = tokens[0]
            if t in _ENTITY_NOISE:
                continue
            is_acronym = t.isupper() and len(t) >= 2
            if not is_acronym and len(t) < 4:
                continue
        key = phrase.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(phrase)
        if len(found) >= _MAX_ENTITIES:
            break
    return found


def map_sectors(title: str, body: str, source_id: str = "") -> tuple[str, list[str]]:
    """제목+본문 keyword로 sector를 매핑한다. (theme, sectors) 반환.

    매칭이 없으면 theme="general", sectors=[]. 고정 상수를 반환하지 않는다.
    """
    text = f" {title} {body} ".lower()
    matched: list[tuple[str, int]] = []
    for sector, keywords in _SECTOR_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits:
            matched.append((sector, hits))
    if not matched:
        return "general", []
    # hit 수 내림차순(동률은 사전순 안정 정렬)으로 결정론적 정렬.
    matched.sort(key=lambda x: (-x[1], x[0]))
    sectors = [s for s, _ in matched[:_MAX_SECTORS]]
    theme = sectors[0]
    return theme, sectors


def impact_baseline(sectors: list[str], source_type: str = "") -> str:
    """근거 없는 구체 주장 대신 정직한 baseline 문구를 반환한다(투자조언/허위주장 금지)."""
    if sectors:
        joined = ", ".join(sectors)
        return (
            f"Relevant to {joined} sector(s). Quantitative impact not assessed "
            f"(deterministic baseline; no LLM impact model applied)."
        )
    return (
        "Sector relevance undetermined. Impact not assessed "
        "(deterministic baseline; no LLM impact model applied)."
    )


def summary_baseline(title: str, body: str, entities: list[str]) -> str:
    """본문 선두 문장을 추출한 정직한 baseline 요약(생성형 환각 없음)."""
    body = (body or "").strip()
    if not body:
        return (title or "").strip() or "[no content]"
    # 첫 1~2문장(최대 280자)만 추출. 환각·추론 없이 원문 그대로.
    sentences = re.split(r"(?<=[.!?])\s+", body)
    summary = ""
    for s in sentences:
        if not summary:
            summary = s.strip()
        elif len(summary) + len(s) + 1 <= 280:
            summary = f"{summary} {s.strip()}"
        else:
            break
    return summary[:280].strip() or (title or "").strip()


def structural_fact_check(body: str, evidence: list[str] | None) -> str:
    """구조적 근거 확인. "pass"는 본문 존재 + grounded evidence + 합성마커 없음일 때만.

    의미적 사실검증이 아니라 **게이트 가능한 구조적 최소요건**이다. LLM 미가용 시 가짜 "pass"를
    만들지 않기 위한 fail-closed baseline(빈본문/무근거 → "hold").
    """
    text = (body or "").strip()
    if not text:
        return "hold"
    low = text.lower()
    if any(marker in low for marker in _MOCK_SENTINELS):
        return "hold"
    if not has_grounded_evidence(evidence):
        return "hold"
    return "pass"

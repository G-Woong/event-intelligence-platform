"""Live Collection Audit 라운드(docs/85) — runner 3종 공유 헬퍼.

전부 부작용 최소 설계: 네트워크 호출 없음 (gate_check은 로컬 store 조회만).
skip 사유는 record의 `audit_action` 필드로만 기록 — PROBE_STATUS에 신규
literal을 추가하지 않는다 (docs/85 §11 함정 2).
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_REGISTRY_PATH = Path(__file__).parent.parent / "configs" / "source_registry.yaml"
OUTPUT_JSONL_DIR = Path(__file__).parent.parent / "outputs" / "jsonl"
OUTPUT_REPORTS_DIR = Path(__file__).parent.parent / "outputs" / "reports"

# 호출 금지 소스 (docs/85 §4) — registry status와 무관하게 하드 제외
AUDIT_EXCLUDED_IDS: frozenset[str] = frozenset({
    "krx_kind", "reddit", "x", "blind", "reuters", "fmkorea",
    "google_programmable_search",
})

# registry status 기반 제외
_EXCLUDED_STATUSES: frozenset[str] = frozenset({
    "MVP_EXCLUDED", "MVP_DEFERRED", "DEPRECATED_OR_EXCLUDED",
})

# audit_action 값 (record 전용 — PROBE_STATUS 아님)
AUDIT_ACTIONS: frozenset[str] = frozenset({
    "called", "cache_skip", "cooldown_skip", "health_skip",
    "query_unsupported", "dry_run",
})

# seed 평가 대상 필드 (3+ = seed_ready)
SEED_FIELDS: tuple[str, ...] = ("title", "url", "timestamp", "source_id", "snippet")

_TITLE_MAX = 120
_SNIPPET_MAX = 200


# ── 소스 목록 ────────────────────────────────────────────────────────────────

def load_audit_sources(layers: Optional[list[str]] = None) -> list[dict]:
    """source_registry.yaml 기반 audit 대상 소스 목록 (제외 필터 적용)."""
    import yaml
    with open(_REGISTRY_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    out: list[dict] = []
    for src in raw.get("sources", []):
        sid = src.get("id", "")
        if not sid or sid == "_dummy":
            continue
        if sid in AUDIT_EXCLUDED_IDS:
            continue
        if src.get("status") in _EXCLUDED_STATUSES:
            continue
        if layers and src.get("layer") not in layers:
            continue
        out.append({
            "id": sid,
            "name": src.get("name", sid),
            "type": src.get("type", ""),
            "layer": src.get("layer", ""),
            "status": src.get("status", ""),
        })
    return out


# ── seed 필드 평가 ───────────────────────────────────────────────────────────

def evaluate_event_seed_fields(item: dict) -> tuple[int, list[str]]:
    """title/url/timestamp/source_id/snippet 중 비어있지 않은 필드 수.

    timestamp는 'timestamp' 또는 'published_at' 키 둘 다 인정.
    """
    present: list[str] = []
    for field in SEED_FIELDS:
        if field == "timestamp":
            val = item.get("timestamp") or item.get("published_at")
        else:
            val = item.get(field)
        if isinstance(val, str) and val.strip():
            present.append(field)
        elif val is not None and not isinstance(val, str):
            present.append(field)
    return len(present), present


def seed_ready_label(count: int) -> str:
    """3+ = yes, 2 = partial, 그 외 no."""
    if count >= 3:
        return "yes"
    if count == 2:
        return "partial"
    return "no"


# 수치 임계값 signal 소스 — seed 5필드 대신 signal 기준으로 평가 (docs/88 §3-5).
# title/url 개념이 없어 seed 5필드 체계로는 영원히 no → 분류 오류이므로 평가 경로 분리.
NUMERIC_SIGNAL_SOURCES: frozenset[str] = frozenset({
    "finnhub", "alpha_vantage", "polygon", "coinbase_market",
    "binance_market", "twelve_data", "its", "eia", "bok_ecos", "kma",
})


def seed_ready_label_for(source_id: str, count: int, items_found: int) -> str:
    """seed 평가 라벨. 수치 signal 소스는 데이터 수신 자체가 ready(signal_ready)."""
    if source_id in NUMERIC_SIGNAL_SOURCES:
        return "signal_ready" if items_found > 0 else "no"
    return seed_ready_label(count)


# ── relevance ────────────────────────────────────────────────────────────────

def relevance_score(query: str, title: str, snippet: str = "") -> float:
    """query 대비 title+snippet 관련도 0.0~1.0.

    영문: 2자 이상 토큰 매칭. 한글: 2-gram substring 매칭.
    """
    text = f"{title or ''} {snippet or ''}".lower()
    units: list[str] = []
    units.extend(re.findall(r"[a-z0-9]{2,}", (query or "").lower()))
    for kor in re.findall(r"[가-힣]{2,}", query or ""):
        if len(kor) == 2:
            units.append(kor)
        else:
            units.extend(kor[i:i + 2] for i in range(len(kor) - 1))
    if not units:
        return 0.0
    matched = sum(1 for u in units if u in text)
    return matched / len(units)


def relevance_label(score: float) -> str:
    if score >= 0.5:
        return "high"
    if score >= 0.2:
        return "medium"
    return "low"


# ── related candidate 추출 (trend fallback enrichment) ───────────────────────

# Google Trends Explore 연관검색어가 막혔을 때, 뉴스/검색 fallback 결과의
# title+snippet에서 규칙 기반(co-occurring term / title bigram / 반복 개체)으로
# related_candidate를 만든다. LLM 없이 결정적. (PHASE 2-C)
_REL_STOP_EN = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were",
    "has", "have", "had", "will", "would", "could", "should", "its", "their",
    "his", "her", "they", "them", "you", "your", "our", "out", "into", "over",
    "after", "before", "about", "than", "then", "but", "not", "all", "new",
    "says", "say", "said", "amid", "via", "how", "why", "who", "what", "when",
    "more", "most", "year", "years", "day", "days", "week", "news", "report",
    "reports", "update", "live", "video", "photos", "latest",
})
_REL_EN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9.'-]{2,}")
_REL_EN_PROPER = re.compile(r"\b([A-Z][A-Za-z0-9.'-]+(?:\s+[A-Z][A-Za-z0-9.'-]+){0,2})\b")
_REL_KO_RUN = re.compile(r"[가-힣]{2,}")


def _seed_units(seed: str) -> set:
    units: set = set()
    units.update(t.lower() for t in _REL_EN_TOKEN.findall(seed or ""))
    for run in _REL_KO_RUN.findall(seed or ""):
        units.add(run)
        if len(run) > 2:
            units.update(run[i:i + 2] for i in range(len(run) - 1))
    return units


def extract_related_candidates(
    seed: str, samples: list[dict], max_candidates: int = 12
) -> list[dict]:
    """seed 1개에 대한 뉴스/검색 sample들에서 related_candidate를 규칙 기반 추출.

    method:
      repeated_term   — 2개 이상 문서에 공통 등장한 의미 토큰(영문) / 2-gram(한글)
      proper_entity   — title의 대문자 시작 고유명 구(영문, 1회 이상)
      title_bigram    — title 인접 토큰 2-gram(영문, 1회 이상)
    seed 자신과 stopword는 제외. 결정적(정렬) 출력. 네트워크 없음.
    """
    seed_units = _seed_units(seed)
    docs_tokens: list[set] = []
    proper: dict[str, int] = {}
    bigrams: dict[str, int] = {}
    ko_runs: dict[str, int] = {}

    for s in samples:
        title = (s.get("title") or "")
        text = f"{title} {s.get('snippet') or ''}"
        toks = [t.lower() for t in _REL_EN_TOKEN.findall(text)
                if t.lower() not in _REL_STOP_EN and t.lower() not in seed_units]
        docs_tokens.append(set(toks))
        # 영문 고유명 구 (title 우선)
        for m in _REL_EN_PROPER.findall(title):
            key = m.strip()
            if key.lower() in seed_units or len(key) < 4:
                continue
            if all(w.lower() in _REL_STOP_EN for w in key.split()):
                continue
            proper[key] = proper.get(key, 0) + 1
        # 영문 title bigram
        title_toks = [t for t in _REL_EN_TOKEN.findall(title)
                      if t.lower() not in _REL_STOP_EN]
        for a, b in zip(title_toks, title_toks[1:]):
            bg = f"{a} {b}"
            if a.lower() in seed_units and b.lower() in seed_units:
                continue
            bigrams[bg] = bigrams.get(bg, 0) + 1
        # 한글 2-gram run
        for run in _REL_KO_RUN.findall(text):
            if run in seed_units or len(run) < 2:
                continue
            ko_runs[run] = ko_runs.get(run, 0) + 1

    # 토큰 문서빈도 (몇 개 문서에 등장)
    df: dict[str, int] = {}
    for ts in docs_tokens:
        for t in ts:
            df[t] = df.get(t, 0) + 1

    out: list[dict] = []
    seen: set = set()

    def _add(phrase: str, method: str, support: int) -> None:
        key = phrase.strip().lower()
        if not key or key in seen or key in seed_units:
            return
        seen.add(key)
        out.append({"phrase": phrase.strip()[:80], "method": method, "support": support})

    for token, support in sorted(df.items(), key=lambda kv: (-kv[1], kv[0])):
        if support >= 2:
            _add(token, "repeated_term", support)
    for run, support in sorted(ko_runs.items(), key=lambda kv: (-kv[1], kv[0])):
        if support >= 2:
            _add(run, "repeated_term", support)
    for phrase, support in sorted(proper.items(), key=lambda kv: (-kv[1], kv[0].lower())):
        _add(phrase, "proper_entity", support)
    for bg, support in sorted(bigrams.items(), key=lambda kv: (-kv[1], kv[0].lower())):
        _add(bg, "title_bigram", support)
    return out[:max_candidates]


def truncate_query(query: str, max_tokens: int = 5, max_chars: int = 60) -> str:
    """장문 seed query 절단 (RISK-Q05). 토큰 수·문자 수 이중 상한.

    괄호/특수문자 안의 부연은 검색 적합성이 낮으므로 먼저 제거한다.
    opendart 공시명처럼 토큰 수는 적어도 한 토큰이 매우 긴 경우(공백 없는 장문)
    토큰 상한만으로는 못 막으므로 문자 상한을 함께 적용한다.
    """
    q = re.sub(r"[\(\)\[\]<>{}]", " ", query or "")
    q = re.sub(r"\s+", " ", q).strip()
    tokens = q.split(" ")[:max_tokens]
    out = " ".join(tokens)
    return out[:max_chars].strip()


# ── sample 추출 ──────────────────────────────────────────────────────────────

def _truncate(val, limit: int) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s[:limit] if s else None


def _dig(obj, path: Optional[str]):
    """dotted path 탐색 — dict key 및 list index 지원."""
    if not path:
        return None
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if idx < len(cur) else None
        else:
            return None
    return cur


# per-source JSON sample 매핑: list_path + item 내 상대 경로
_SAMPLE_PATHS: dict[str, dict] = {
    "serper": {"list": "organic", "title": "title", "url": "link",
               "snippet": "snippet", "published_at": "date"},
    "tavily": {"list": "results", "title": "title", "url": "url",
               "snippet": "content", "published_at": "published_date"},
    "exa": {"list": "results", "title": "title", "url": "url",
            "snippet": "text", "published_at": "publishedDate"},
    "naver_news_search": {"list": "items", "title": "title", "url": "link",
                          "snippet": "description", "published_at": "pubDate"},
    "naver_blog_search": {"list": "items", "title": "title", "url": "link",
                          "snippet": "description", "published_at": "postdate"},
    "guardian": {"list": "response.results", "title": "webTitle", "url": "webUrl",
                 "snippet": "sectionName", "published_at": "webPublicationDate"},
    "nyt": {"list": "response.docs", "title": "headline.main", "url": "web_url",
            "snippet": "abstract", "published_at": "pub_date"},
    "gdelt": {"list": "articles", "title": "title", "url": "url",
              "snippet": "domain", "published_at": "seendate"},
    "youtube": {"list": "items", "title": "snippet.title", "url": "id.videoId",
                "snippet": "snippet.description", "published_at": "snippet.publishedAt"},
    "gnews": {"list": "articles", "title": "title", "url": "url",
              "snippet": "description", "published_at": "publishedAt"},
    "newsapi": {"list": "articles", "title": "title", "url": "url",
                "snippet": "description", "published_at": "publishedAt"},
    "federal_register": {"list": "results", "title": "title", "url": "html_url",
                         "snippet": "abstract", "published_at": "publication_date"},
    "sec_edgar": {"list": "hits.hits", "title": "_source.display_names.0",
                  "url": "_id", "snippet": "_source.file_type",
                  "published_at": "_source.file_date"},
    "kofic": {"list": "boxOfficeResult.dailyBoxOfficeList", "title": "movieNm",
              "url": None, "snippet": "audiAcc", "published_at": "openDt"},
    "tmdb": {"list": "results", "title": "title", "url": "id",
             "snippet": "overview", "published_at": "release_date"},
    "opendart": {"list": "list", "title": "report_nm", "url": "rcept_no",
                 "snippet": "corp_name", "published_at": "rcept_dt"},
    "product_hunt": {"list": "data.posts.edges", "title": "node.name", "url": None,
                     "snippet": "node.tagline", "published_at": None},
    "aladin": {"list": "item", "title": "title", "url": "link",
               "snippet": "description", "published_at": "pubDate"},
    "twelve_data": {"list": "values", "title": "datetime", "url": None,
                    "snippet": "close", "published_at": "datetime"},
    "kma": {"list": "response.body.items.item", "title": "category", "url": None,
            "snippet": "obsrValue", "published_at": "baseDate"},
    "tour": {"list": "response.body.items.item", "title": "title", "url": None,
             "snippet": "addr1", "published_at": "modifiedtime"},
    # igdb: root가 JSON 배열 ($root) + first_release_date는 unix epoch (공통 정규화)
    "igdb": {"list": "$root", "title": "name", "url": "url",
             "snippet": "rating", "published_at": "first_release_date"},
    # hacker_news: detail 2차 호출 결과가 extracted_payload "items"에 저장됨. time=epoch
    "hacker_news": {"list": "items", "title": "title", "url": "url",
                    "snippet": "score", "published_at": "time"},
    # bok_ecos/eia/its: numeric/카탈로그 — url/date 개념 약함 (docs/08 §5)
    "bok_ecos": {"list": "StatisticTableList.row", "title": "STAT_NAME",
                 "url": None, "snippet": "CYCLE", "published_at": None},
    "eia": {"list": "response.routes", "title": "name", "url": None,
            "snippet": "description", "published_at": None},
    "its": {"list": "body.items", "title": "roadName", "url": None,
            "snippet": "speed", "published_at": "createdDate"},
}

# per-source XML 태그명 확장 (RSS 표준명 뒤에 시도) — data.go.kr 등 비-RSS XML
_XML_FIELD_NAMES: dict[str, dict[str, tuple[str, ...]]] = {
    "culture_info": {
        "title": ("title", "TITLE"),
        "url": ("url", "URL"),
        "snippet": ("place", "PLACE", "area", "realmName"),
        "published_at": ("startDate", "STRTDATE", "beginDe", "sdate"),
    },
    "kopis": {"published_at": ("prfpdfrom",)},  # 기존 하드코딩의 선언화 (동작 동일)
}

_GENERIC_LIST_KEYS = ("items", "results", "articles", "list", "values",
                      "products", "data", "hits")
_GENERIC_TITLE_KEYS = ("title", "name", "webTitle", "headline", "keyword",
                       "movieNm", "prfnm", "symbol")
_GENERIC_URL_KEYS = ("url", "link", "webUrl", "html_url", "permalink")
_GENERIC_TIME_KEYS = ("published_at", "publishedAt", "pubDate", "publication_date",
                      "datetime", "date", "timestamp", "seendate", "time")
_GENERIC_SNIPPET_KEYS = ("snippet", "description", "abstract", "content",
                         "summary", "overview", "price")


def _normalize_sample_url(source_id: str, url) -> Optional[str]:
    if url is None:
        return None
    s = str(url).strip()
    if not s:
        return None
    if source_id == "youtube" and not s.startswith("http"):
        return f"https://www.youtube.com/watch?v={s}"
    if source_id == "tmdb" and not s.startswith("http"):
        return f"https://www.themoviedb.org/movie/{s}"
    return s


def _normalize_epoch(value):
    """unix epoch(초) 정수/실수를 ISO 날짜 문자열로 변환. 그 외는 원본 반환."""
    if isinstance(value, (int, float)) and value > 10_000_000:
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d")
    return value


def _sample_from_json(source_id: str, parsed, max_samples: int) -> list[dict]:
    spec = _SAMPLE_PATHS.get(source_id)
    items = None
    if spec:
        # $root: 응답 root 자체가 JSON 배열인 소스 (igdb 등)
        items = parsed if spec["list"] == "$root" else _dig(parsed, spec["list"])
    if not isinstance(items, list):
        # generic fallback: dict에서 첫 list-of-dicts 필드 또는 root list
        spec = None
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            for key in _GENERIC_LIST_KEYS:
                val = parsed.get(key)
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    items = val
                    break
    if not isinstance(items, list):
        return []

    samples: list[dict] = []
    for item in items[:max_samples]:
        if not isinstance(item, dict):
            continue
        if spec:
            title = _dig(item, spec.get("title"))
            url = _dig(item, spec.get("url"))
            snippet = _dig(item, spec.get("snippet"))
            published = _dig(item, spec.get("published_at"))
        else:
            title = next((item[k] for k in _GENERIC_TITLE_KEYS if item.get(k)), None)
            url = next((item[k] for k in _GENERIC_URL_KEYS if item.get(k)), None)
            snippet = next((item[k] for k in _GENERIC_SNIPPET_KEYS if item.get(k)), None)
            published = next((item[k] for k in _GENERIC_TIME_KEYS if item.get(k)), None)
        published = _normalize_epoch(published)  # igdb/hacker_news epoch → ISO
        samples.append({
            "title": _truncate(_strip_tags(title), _TITLE_MAX),
            "url": _normalize_sample_url(source_id, url),
            "snippet": _truncate(_strip_tags(snippet), _SNIPPET_MAX),
            "published_at": _truncate(published, 64),
        })
    return samples


def _strip_tags(val) -> Optional[str]:
    if val is None:
        return None
    return re.sub(r"<[^>]+>", "", str(val))


def _sample_from_xml(source_id: str, text: str, max_samples: int) -> list[dict]:
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item") or root.findall(f".//{atom}entry")
    if not items and source_id == "kopis":
        items = root.findall(".//db")
    extra = _XML_FIELD_NAMES.get(source_id, {})
    samples: list[dict] = []
    for el in items[:max_samples]:
        def _find_text(*names):
            for n in names:
                child = el.find(n)
                if child is None:
                    child = el.find(f"{atom}{n}")
                if child is not None and (child.text or child.get("href")):
                    return child.text or child.get("href")
            return None
        samples.append({
            "title": _truncate(_find_text("title", "prfnm", *extra.get("title", ())), _TITLE_MAX),
            "url": _truncate(_find_text("link", "guid", *extra.get("url", ())), 500),
            "snippet": _truncate(_strip_tags(
                _find_text("description", "summary", *extra.get("snippet", ()))), _SNIPPET_MAX),
            "published_at": _truncate(
                _find_text("pubDate", "updated", "published", "prfpdfrom",
                           *extra.get("published_at", ())), 64),
        })
    return samples


def _sample_from_html(source_id: str, text: str, max_samples: int) -> list[dict]:
    title = None
    urls: list[str] = []
    try:
        from ingestion.sources._registry import get_source_instance
        instance = get_source_instance(source_id)
        if instance is not None:
            urls = list(instance.extract_candidate_urls(text))[:max_samples]
    except Exception:
        pass
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "lxml")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
    except Exception:
        pass
    if not urls and not title:
        return []
    samples = []
    for i, u in enumerate(urls or [None]):
        samples.append({
            "title": _truncate(title, _TITLE_MAX) if i == 0 else None,
            "url": u,
            "snippet": None,
            "published_at": None,
        })
    return samples


def extract_sample_items(
    source_id: str,
    artifact_path: Optional[str],
    max_samples: int = 3,
    resolve_canonical: bool = False,
    canonical_via_browser: bool = False,
) -> list[dict]:
    """raw_payload artifact에서 sample item ≤max_samples 추출 (json/xml/html 분기).

    title 120자 / snippet 200자 절단. 실패 시 빈 리스트 (예외 없음).

    resolve_canonical=True면 각 sample의 url을 url_resolver로 풀어 canonical_url을 부착한다
    (네트워크 I/O 발생 — 기본 off라 audit runner/순수 파싱 테스트는 영향 없음). 해석 실패 시
    canonical_url은 원본 url과 동일(예외 없음).

    canonical_via_browser=True면 HTTP resolve로 풀리지 않는 URL(예: Google News RSS 신형
    `news.google.com/rss/articles/CBM...`)을 Playwright headless 1-hop으로 승격 해석한다 —
    ap_news 원본 apnews.com 기사 URL 정규화에 사용. 브라우저 spawn 비용이 크므로 명시 opt-in.
    """
    samples = _extract_sample_items_raw(source_id, artifact_path, max_samples)
    if resolve_canonical and samples:
        from ingestion.tools import url_resolver
        for s in samples:
            u = s.get("url")
            if not u:
                continue
            if canonical_via_browser and url_resolver.needs_browser_resolution(u):
                s["canonical_url"] = url_resolver.resolve_via_browser(u)
            else:
                s["canonical_url"] = url_resolver.resolve(u)
    return samples


def _extract_sample_items_raw(
    source_id: str, artifact_path: Optional[str], max_samples: int
) -> list[dict]:
    if not artifact_path or not Path(artifact_path).exists():
        return []
    try:
        text = Path(artifact_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    stripped = text.lstrip()
    if not stripped:
        return []
    # JSON 우선
    if stripped[0] in "{[":
        try:
            parsed = json.loads(stripped)
            return _sample_from_json(source_id, parsed, max_samples)
        except Exception:
            return []
    if stripped.startswith("<?xml") or "<rss" in stripped[:500] or "<feed" in stripped[:500] \
            or (stripped.startswith("<") and not stripped[:200].lower().startswith(("<html", "<!doctype"))):
        samples = _sample_from_xml(source_id, text, max_samples)
        if samples:
            return samples
    return _sample_from_html(source_id, text, max_samples)


def extract_samples_from_rendered(
    source_id: str, html: Optional[str], max_samples: int = 3
) -> list[dict]:
    """Playwright(Route 2) 결과의 rendered html에서 site spec selector로 sample 추출.

    트렌드 소스는 keyword 텍스트가 title이 된다. selector 미매칭 시 page title fallback.
    """
    if not html:
        return []
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []
    selectors: list[str] = []
    try:
        from ingestion.probes.site_specs import load_site_specs
        spec = load_site_specs().get(source_id)
        if spec:
            selectors = list(spec.selectors.get("list", []))
    except Exception:
        pass
    samples: list[dict] = []
    seen: set[str] = set()
    for sel in selectors:
        try:
            matches = soup.select(sel)
        except Exception:
            continue
        for el in matches:
            text = el.get_text(" ", strip=True)
            if not text or text in seen:
                continue
            seen.add(text)
            href = el.get("href") if el.name == "a" else None
            samples.append({
                "title": _truncate(text, _TITLE_MAX),
                "url": _truncate(href, 500),
                "snippet": None,
                "published_at": None,
            })
            if len(samples) >= max_samples:
                return samples
        if samples:
            break
    if not samples and soup.title and soup.title.string:
        samples.append({
            "title": _truncate(soup.title.string, _TITLE_MAX),
            "url": None, "snippet": None, "published_at": None,
        })
    return samples


def collect_samples(result, max_samples: int = 3) -> list[dict]:
    """CollectionProbeResult에서 sample 추출 — raw artifact 우선, rendered html 차선."""
    raw_path = result.artifact_paths.raw_payload or result.artifact_paths.raw_html
    if raw_path:
        samples = extract_sample_items(result.source_id, raw_path, max_samples)
        if samples:
            return samples
    # raw가 id 목록형(hacker_news 등)이라 비면 detail이 저장된 extracted_payload 시도
    ep = getattr(result.artifact_paths, "extracted_payload", None)
    if ep:
        samples = extract_sample_items(result.source_id, ep, max_samples)
        if samples:
            return samples
    if result.extraction and result.extraction.rendered_page:
        return extract_samples_from_rendered(
            result.source_id, result.extraction.rendered_page.html, max_samples
        )
    return []


# ── gate / rate limit ────────────────────────────────────────────────────────

def gate_check(source_id: str, query: str = "") -> Optional[str]:
    """호출 전 gate. skip 사유(audit_action 값) 또는 None(호출 가능).

    순서: health should_skip → in_cooldown → is_cached.
    """
    try:
        from ingestion.core.source_health import get_health_store, should_skip
        state = get_health_store().get(source_id)
        skip, _reason = should_skip(state)
        if skip:
            return "health_skip"
    except Exception:
        pass
    try:
        from ingestion.core.rate_limit_policy import in_cooldown, is_cached
        cooled, _at = in_cooldown(source_id, query)
        if cooled:
            return "cooldown_skip"
        if is_cached(source_id, query):
            return "cache_skip"
    except Exception:
        pass
    return None


def enforce_min_interval(source_id: str, last_called: Optional[float]) -> float:
    """min_interval_seconds 강제 (in-process sleep). 잔여 대기시간을 반환.

    last_called: 직전 호출의 time.monotonic() 값 (없으면 대기 없음).
    Route 1(API)에 rate limit 게이트가 없는 코드 gap을 runner 레벨에서 보완.
    """
    from ingestion.core.rate_limit_policy import load_rate_limit_policy
    policy = load_rate_limit_policy(source_id)
    if last_called is None or policy.min_interval_seconds <= 0:
        return 0.0
    elapsed = time.monotonic() - last_called
    wait = policy.min_interval_seconds - elapsed
    if wait > 0:
        time.sleep(wait)
        return wait
    return 0.0


# ── 출력 ────────────────────────────────────────────────────────────────────

def audit_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_audit_jsonl(records: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    return path


def write_audit_md(content: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def safe_print(text: str) -> None:
    """Windows cp949 콘솔 안전 출력 (파일 기록은 항상 UTF-8)."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))

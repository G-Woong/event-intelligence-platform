# 06_SOURCE_REGISTRY_DESIGN — YAML 레지스트리 + SourceCrawler 인터페이스

## YAML 스키마

파일: `configs/source_registry.yaml`

```yaml
version: "1.0"
sources:
  - id: bbc                        # 고유 식별자
    name: "BBC News"               # 표시 이름
    type: news                     # news / community / official
    evidence_level: tier1          # tier1 / tier2 / tier3
    role: primary                  # primary / secondary / supplementary
    phase: 1                       # 1 / 2 / 3 / 0(internal)
    base_url: "https://www.bbc.com/news"
    known_blockers: []             # paywall / login_wall / captcha / robots
    expected_fields:               # 추출 기대 필드
      - title
      - body
      - published_at
      - author
```

## Evidence Level 정의

| Level | 설명 |
|---|---|
| tier1 | 공인 언론사, 공식 정부/기관 데이터 |
| tier2 | 검증된 커뮤니티, 국내 주요 매체 |
| tier3 | 커뮤니티 게시판, 소셜 미디어 |

## SourceCrawler 인터페이스

`crawling/sources/base.py`

```python
class SourceCrawler(ABC):
    def build_search_query(self, keywords) -> str: ...
    def get_entry_url(self) -> str: ...
    def extract_candidate_urls(self, html: str) -> list[str]: ...
    def get_expected_fields(self) -> list[str]: ...
    def fetch_entry_html(self, url: str) -> Optional[str]: ...    # fixture override
    def fetch_page_html(self, url: str, strategy: str) -> Optional[str]: ...
    def extract(self, html: str, url: str, strategy: str) -> Optional[dict]: ...
    def extract_source_specific_hints(self, html: str) -> dict: ...
```

## 30개 소스 분포

| Phase | Type | 개수 | ID 예시 |
|---|---|---|---|
| 1 | news | 10 | bbc, reuters, apnews … aljazeera |
| 2 | community | 10 | reddit, hackernews … bobaedream |
| 3 | official | 10 | gdelt, sec_edgar … reuters_data |
| 0 | internal | 1 | _dummy |

## 로딩 방식

```python
from crawling.core.source_registry import load_registry
registry = load_registry()          # configs/ 기본 경로
spec = registry.get("bbc")         # SourceSpec
sources = registry.get_by_phase(1) # list[SourceSpec]
```

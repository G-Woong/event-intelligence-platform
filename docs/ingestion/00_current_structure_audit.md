# 00 — Current Structure Audit (post-rename snapshot)

> 기준: Round 1 rename 완료 후 `ingestion/` 기준. 탐색일 2026-06-03.

## 1. 폴더별 역할

```
ingestion/
├── agents/          LangGraph 파이프라인 (graph.py 14노드, state.py, llm_judge.py)
├── configs/         YAML 소스 레지스트리 (source_registry.yaml, phase{1,2,3}_sources.yaml)
├── core/            공유 유틸리티 (artifact_store, error_taxonomy, logging_setup,
│                    quality_score, report_writer, retry_policy, source_registry)
│                    + 신규: env_loader.py
├── logs/            run/attempt/error JSONL 로그 (gitignore'd; .gitkeep만 추적)
├── outputs/         수집 산출물 (raw_html, extracted_text, extracted_payload,
│                    dom_snapshots, screenshots, reports, jsonl)
│                    + 신규: api_connectivity_report.md, api_connectivity_results.jsonl
├── runners/         진입점 스크립트 (run_one_source, run_phase, run_all_phases,
│                    inspect_last_failure, summarize_reports)
│                    + 신규: run_api_connectivity_check.py
├── schemas/         Pydantic 모델 (raw_document, extracted_article, extracted_post,
│                    event_candidate, extraction_diagnostics, source_report)
├── sources/         30개 소스 구현체 + base.py + _registry.py + _dummy.py
├── tests/           기존 4개 테스트 + 신규 unit/ + integration/ 하위
└── tools/           추출/페칭 툴 (html_fetch_tool, readability_extractor,
                     trafilatura_extractor, dom_candidate_extractor, metadata_extractor,
                     playwright_browser_tool, screenshot_logger, search_query_builder)
                     + 신규: check_env_hygiene.py
```

## 2. 공개 함수 시그니처 (핵심)

### core/artifact_store.py
```python
new_run_id(phase: int, source_id: str) -> str
url_hash(url: str) -> str                          # SHA1 8자
save_raw_html(run_id, source_id, uh, strategy, html) -> Path
save_extracted_text(run_id, source_id, uh, strategy, fields) -> Path
append_result_row(phase, source_id, row: dict) -> None
save_raw_payload(run_id, source_id, h, fmt, payload) -> Path
save_extracted_payload(run_id, source_id, h, fields) -> Path
build_dom_snapshot_dict(url, html, strategy, *, extra) -> dict
```

### core/source_registry.py
```python
class SourceSpec: id, name, type, evidence_level, role, phase, base_url,
                  known_blockers, expected_fields
load_registry(configs_dir: Path | None) -> SourceRegistry
class SourceRegistry: get(id) / all() / get_by_phase(phase)
```

### core/logging_setup.py
```python
configure_ingestion_logging(log_dir: Path, source_id: str, level: str) -> None
get_ingestion_logger(name: str) -> logging.Logger   # root = "ingestion"
```

### sources/_registry.py
```python
get_source_instance(source_id: str) -> Optional[SourceCrawler]
```

### sources/base.py (SourceCrawler ABC)
```python
get_entry_url() -> str
build_search_query(keywords?) -> str
fetch_entry_html(url) -> Optional[str]
fetch_page_html(url, strategy) -> Optional[str]
extract_candidate_urls(html) -> list[str]
extract(html, url, strategy) -> Optional[dict]
extract_source_specific_hints(html) -> dict
precheck_status() -> Optional[dict]   # {"status": str, "reason": str}
fallback_status() -> Optional[str]
```

## 3. LangGraph 14노드 흐름

```
initialize
  └─► build_search_query
       └─► fetch_entry_url ──[error]─► error_analysis
            └─► extract_candidate_urls         │
                 └─► fetch_target_page ──[err]─┤
                      └─► select_extraction_strategy
                           └─► extract_content ──[err]──► error_analysis
                                └─► score_quality
                                     └─► retry_decision
                                          ├─[pass]─► extract_event_candidates
                                          │           └─► llm_quality_judge
                                          │                └─► strategy_reflection
                                          │                     └─► write_source_report ─► END
                                          ├─[retry]─► select_extraction_strategy (loop)
                                          └─[exhaust]─► strategy_reflection ─► write_source_report
                                     error_analysis ──────────────────────► retry_decision
```

## 4. 소스 2패턴

| 패턴 | 설명 | 대표 소스 |
|---|---|---|
| **JSON-API** | `fetch_entry_html`에서 JSON 직접 파싱, `extract()`에서 raw_payload 반환 | GDELT, SEC EDGAR, OpenDart, EIA, Federal Register, HackerNews |
| **HTML-cascade** | 기본 httpx fetch → readability/trafilatura/dom_heuristic 3단계 cascade | BBC, AP, TechCrunch, ZDNet 등 뉴스형 |

## 5. 테스트 불변식

| 테스트 파일 | 불변식 |
|---|---|
| `test_source_registry.py` | 소스 총 30개 (real), phase 1/2/3 각 10개 |
| `test_error_taxonomy.py` | ErrorType 25개 항목 |
| `test_quality_score.py` | 품질 점수 계산 |
| `test_schema_validation.py` | Pydantic 스키마 |

## 6. import 의존도 (섬 현황)

`ingestion/` 내부 모듈은 완전히 자립적이다:
- `backend/`·`workers/`·`agents/` 어디서도 `ingestion.*` import 없음
- `ingestion/` 외부에서 참조하는 파일: `.gitignore`(59–68행), `plans/` 문서

## 7. Rename 지뢰 목록 (Round 1에서 처리 완료)

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| `_SOURCE_MAP` 31개 dotted path | `crawling.sources.*` | `ingestion.sources.*` |
| 모든 절대 import | `from crawling.X` | `from ingestion.X` |
| root 로거 이름 | `"crawling"` | `"ingestion"` |
| logging 함수명 | `configure_crawling_logging` / `get_crawling_logger` | `configure_ingestion_logging` / `get_ingestion_logger` |
| `.gitignore` 58–64행 | `crawling/outputs/` 등 | `ingestion/outputs/` 등 |
| run_one_source print 경로 | `crawling/outputs/reports/` | `ingestion/outputs/reports/` |

## 8. Path 상수 (변경 없음 이유)

모든 `Path(__file__).parent.parent` 기반 상수는 디렉터리 **깊이** 기준이므로
평면 rename에서 절대경로 위치는 변하지만 상대 깊이는 동일 → 런타임 해석 정상.

- `artifact_store._OUTPUTS_DIR` = `ingestion/core/../outputs` = `ingestion/outputs/` ✓
- `source_registry._CONFIGS_DIR` = `ingestion/core/../configs` = `ingestion/configs/` ✓
- `runner._ROOT` = `ingestion/runners/../../..` = repo 루트 ✓

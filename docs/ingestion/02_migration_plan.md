# 02 — Migration Plan

## Round 1 — 평면 Rename (완료: 2026-06-03)

### 완료된 작업

| 항목 | 상태 |
|---|---|
| `git mv crawling ingestion` | ✓ 완료 |
| 52개 .py 파일 import 치환 (`crawling.` → `ingestion.`) | ✓ 완료 |
| `_SOURCE_MAP` 31개 dotted path 치환 | ✓ 완료 |
| 로거 이름 `"crawling"` → `"ingestion"` | ✓ 완료 |
| `configure_crawling_logging` → `configure_ingestion_logging` | ✓ 완료 |
| `get_crawling_logger` → `get_ingestion_logger` | ✓ 완료 |
| `.gitignore` 58–64행 `crawling/` → `ingestion/` | ✓ 완료 |
| `.gitignore` GCP 키 패턴 추가 | ✓ 완료 |
| 잔존 `"crawling"` 참조 0건 확인 | ✓ 완료 |
| `ingestion/core/env_loader.py` 신규 | ✓ 완료 |
| `ingestion/tools/check_env_hygiene.py` 신규 | ✓ 완료 |
| `ingestion/tests/unit/test_env_loader.py` 신규 | ✓ 완료 |
| `ingestion/runners/run_api_connectivity_check.py` 신규 | ✓ 완료 |
| `ingestion/tests/integration/test_api_connectivity.py` 신규 | ✓ 완료 |
| 설계 문서 4종 (`docs/ingestion/`) | ✓ 완료 |
| `docs/COMPLIANCE_BOUNDARY.md` 갱신 | ✓ 완료 |
| `.env.example` ingestion 키 섹션 추가 | ✓ 완료 |

### Round 1 제약 사항 (의도적으로 변경 안 한 것)

- **계층 재배치 없음**: `sources/news/`, `sources/official/` 등 하위 분류 미착수
- **Path 상수 변경 없음**: `Path(__file__).parent.parent` 기반 상수는 깊이 기준이므로 평면 rename에서 그대로 동작
- **소스 수 유지**: 30개 (테스트 불변식 `test_registry_has_30_real_sources` 통과)
- **pipeline 모듈 미착수**: Round 2로 이연
- **layered registry 미착수**: Round 2로 이연

### 롤백 방법

Round 1은 git mv로 추적되므로 커밋 단위로 `git revert` 가능.
```bash
git log --oneline  # rename commit hash 확인
git revert <hash>  # ingestion/ → crawling/ 되돌리기
```

---

## Round 2 — Deep Re-nesting (미착수)

### 예정 작업

1. **sources 하위 분류**: `sources/` → `sources/news/`, `sources/community/`, `sources/official/`, `sources/search/`, `sources/media/`, `sources/blocked/`

2. **Path 상수 수정**: 디렉터리 깊이 1단계 추가되므로 `Path(__file__).parent.parent` → `Path(__file__).parent.parent.parent` 변경 필요 파일:
   - `core/artifact_store.py` (`_OUTPUTS_DIR`)
   - `core/source_registry.py` (`_CONFIGS_DIR`)
   - `runners/run_one_source.py` (`_ROOT`, `log_dir`, `output_dir`)
   - 모든 sources 파일의 상대 경로 참조

3. **Pipeline 6모듈 신규**: `pipeline/` 디렉터리 + `DiscoveryCollector`, `SearchEnrichmentCollector`, `EventCandidateExtractor`, `EventQueue`, `QueryGenerator`, `CanonicalEventBuilder`

4. **Layered source_registry.yaml**: layer/input_type/collection_methods/auth/rate_limit_policy 필드 추가

5. **`--live` connectivity 실호출**: 사용자 승인 후 `run_api_connectivity_check.py`의 live 분기 구현

6. **Playwright 소스**: `krx_kind`, `eu_press_corner` 완전 구현

### 파일 이동표 (Round 2 예정)

| 현재 경로 | 목표 경로 |
|---|---|
| `ingestion/sources/bbc.py` | `ingestion/sources/news/bbc.py` |
| `ingestion/sources/reddit.py` | `ingestion/sources/community/reddit.py` |
| `ingestion/sources/opendart.py` | `ingestion/sources/official/opendart.py` |
| `ingestion/sources/naver_blog_search.py` | `ingestion/sources/search/naver_blog_search.py` |
| `ingestion/sources/youtube.py` | `ingestion/sources/media/youtube.py` |
| `ingestion/sources/x.py` | `ingestion/sources/blocked/x.py` |
| `ingestion/sources/blind.py` | `ingestion/sources/blocked/blind.py` |

### Round 2 테스트 불변식 영향

- `test_registry_has_30_real_sources` — 소스 수 유지시 통과
- `test_registry_phase_split` — phase 1/2/3 각 10개 유지시 통과
- import 경로 변경으로 `_SOURCE_MAP` dotted path 재치환 필요

---

## 이연된 문서 (Round 2에서 작성)

- `04_source_layer_matrix.md` — 소스별 layer/method/quota 상세표
- `05_api_connectivity_results.md` — 실호출 결과
- `06_playwright_required_sources.md` — KRX KIND, EU Press Corner 구현 가이드
- `07_next_round_todo.md` — Round 3+ 로드맵

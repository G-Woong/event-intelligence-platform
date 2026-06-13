# 12 Agent Orchestration Probe Interface

Agent Orchestration이 호출할 수 있는 수집 함수 인터페이스 계약입니다.

---

## run_api_live_probe

```python
from ingestion.probes.api_probe import run_api_live_probe
from ingestion.probes.models import ProbeResult
```

### 시그니처

```python
def run_api_live_probe(
    service_id: str,
    max_calls: int = 1,
    env_path: Optional[Path] = None,
    dry_run: bool = False,
) -> ProbeResult
```

### 입력

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `service_id` | str | `_SERVICE_CONFIGS` 등록 ID (예: `"naver_news_search"`) |
| `max_calls` | int | 최대 API 호출 횟수. 기본 1. **항상 1 이상 유지** |
| `env_path` | Path | .env 파일 경로. None이면 환경변수에서 읽음 |
| `dry_run` | bool | True면 키 존재 확인만 (HTTP 미호출) |

### 출력: ProbeResult

```python
@dataclass
class ProbeResult:
    source_id: str          # service_id
    method: str             # "api"
    query: Optional[str]    # 사용한 검색 쿼리
    region: Optional[str]   # 지역 코드
    status: str             # PROBE_STATUS 상수 중 하나
    http_status: Optional[int]  # HTTP 응답 코드
    items_found: int        # 상위 레벨 아이템 수
    items_extracted: int    # 의미 있는 필드 추출 수
    meaningful_fields: list[str]  # 성공적으로 추출된 필드 이름
    artifact_paths: dict    # {"raw_payload": "/path/...", "extracted_payload": "/path/..."}
    error_category: Optional[str]
    next_action: str        # 권고 액션

    def to_dict(self) -> dict: ...
```

### status 값

```python
PROBE_STATUS = frozenset({
    "LIVE_SUCCESS",       # 실데이터 수신 + artifact 저장 성공
    "LIVE_PARTIAL",       # 200 응답, 유의미 필드 구조 불일치
    "MISSING_KEY",        # 키 없음 (HTTP 미호출)
    "INVALID_KEY",        # 401
    "PERMISSION_DENIED",  # 403
    "RATE_LIMITED",       # 429
    "QUOTA_EXHAUSTED",    # 일일 한도 소진
    "PLAN_RESTRICTED",    # 402
    "ENDPOINT_DEPRECATED",# 410
    "SCHEMA_CHANGED",     # 구조 변경
    "PARSE_ERROR",        # 파싱 실패
    "NETWORK_ERROR",      # 5xx 또는 연결 실패
    "TIMEOUT",            # 응답 시간 초과
    "BLOCKED",            # 로그인/라이선스 차단
    "DEFERRED",           # 이번 라운드 제외 (Playwright 필요 등)
    "UNKNOWN",            # 분류 불가
})
```

### 사용 예시

```python
result = run_api_live_probe("naver_news_search", max_calls=1)
if result.status == "LIVE_SUCCESS":
    raw = Path(result.artifact_paths["raw_payload"]).read_text(encoding="utf-8")
    # JSON 파싱 후 파이프라인 진입
elif result.status == "MISSING_KEY":
    # 키 없음 — 건너뜀
elif result.status == "RATE_LIMITED":
    # 재시도 스케줄링
```

---

## run_playwright_probe

```python
from ingestion.probes.playwright_probe import run_playwright_probe
```

### 시그니처

```python
def run_playwright_probe(
    site_id: str,
    query: Optional[str] = None,
    region: Optional[str] = None,
    max_items: int = 10,
) -> ProbeResult
```

### 입력

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `site_id` | str | `playwright_probe_sites.yaml` 등록 ID (예: `"google_trending_now"`) |
| `query` | Optional[str] | 검색 키워드 (input_type=keyword 사이트용) |
| `region` | Optional[str] | 지역 코드 예: `"KR"` (input_type=region 사이트용) |
| `max_items` | int | 최대 추출 아이템 수. 기본 10 |

### 출력: ProbeResult (동일 구조)

- `method`: `"playwright"`
- `artifact_paths` 키: `"screenshot"`, `"rendered_dom"`, `"raw_signal"`, `"extracted_body_N"`

### 사용 예시

```python
result = run_playwright_probe("google_trending_now", region="KR", max_items=10)
if result.status == "LIVE_SUCCESS":
    raw_signal = Path(result.artifact_paths["raw_signal"]).read_text(encoding="utf-8")
    items = json.loads(raw_signal)  # [{"keyword": "...", "url": "..."}, ...]
elif result.status == "BLOCKED":
    # CAPTCHA/login 감지 → 재시도 불가
```

---

## normalize_* 함수

```python
from ingestion.probes.normalizers import (
    normalize_api_result,
    normalize_signal_items,
    normalize_doc_items,
)
```

### normalize_api_result

```python
def normalize_api_result(service_id: str, parsed: Any) -> dict
```

API 응답 JSON에서 meaningful field를 추출. service_id별 필드 맵 기반.

### normalize_signal_items

```python
def normalize_signal_items(site_id: str, items: list) -> list[dict]
```

트렌딩 키워드 목록을 정규화. 출력 스키마:

```json
{
  "source": "google_trending_now",
  "signal_type": "trending_keyword",
  "official": true,
  "evidence_level": "low_to_medium",
  "rank": 1,
  "keyword": "젠슨 황",
  "observed_at": "2026-06-03T14:33:20+00:00",
  "source_url": "",
  "collection_method": "playwright"
}
```

### normalize_doc_items

```python
def normalize_doc_items(site_id: str, items: list) -> list[dict]
```

커뮤니티 문서 목록을 정규화. 출력 스키마:

```json
{
  "source": "dcinside",
  "title": "게시글 제목",
  "body": "본문 텍스트",
  "url": "https://...",
  "time": "2026-06-03T00:00:00",
  "score": 0
}
```

---

## artifact 경로 규칙

```
ingestion/outputs/
  raw_payload/{source_id}/{run_id}_{url_hash}_{fmt}.{ext}
  extracted_payload/{source_id}/{run_id}_{url_hash}.json
  raw_signal/{source_id}/{run_id}_{url_hash}.json
  rendered_dom/{source_id}/{run_id}_{url_hash}.html
  screenshots/{source_id}/{run_id}_{url_hash}.png
  jsonl/api_live_probe_results.jsonl
  jsonl/playwright_probe_results.jsonl
  reports/api_live_probe_report.md
  reports/playwright_probe_report.md
```

`run_id` 형식: `{YYYYMMDD_HHMMSS}_phase0_{source_id}`
`url_hash`: SHA-1 8자리 (엔드포인트 URL 기준, 키 파라미터 제외)

---

## 보안 제약

- `artifact_paths` 경로는 응답 본문 파일 경로만 담음. 요청 헤더/URL 쿼리 파라미터 미포함.
- API 키 값이 응답 본문에 포함된 경우 `_sanitize_response()`로 자동 제거 후 저장.
- env_status() 호출로 키 존재 여부만 확인. 실값은 `os.environ.get()` 이후 in-memory에서만 사용.

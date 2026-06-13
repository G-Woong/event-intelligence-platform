# 04. newsapi — `/v2/top-headlines` → `/v2/everything` 전환

> **상태: APPLIED — SUPERSEDED_BY [IMPLEMENTATION_TRACE_FINAL.md](./IMPLEMENTATION_TRACE_FINAL.md)** (2026-06-13). 본 지시문은 적용 완료. 원문은 이력 보존용이며 파괴적 삭제 금지. 현재 상태는 trace final + docs/ingestion/70·86·92 참조.

> ## ✅ 적용 완료 (2026-06-13)
> top-headlines+q가 헤드라인 풀 한정이라 임의 phrase 0건(구조적 부적합) → **`/v2/everything` 전환**.
> - 변경: `_SERVICE_CONFIGS["newsapi"].endpoint = .../v2/everything`(+free_plan/note),
>   `_PROBE_SPEC["newsapi"].extra_params = {q:"news", pageSize, sortBy:"publishedAt", language:"en"}`
>   — **country 제거**(everything에 보내면 400), q 필수라 기본 q 주입. query 주입은 기존
>   `_apply_query_override`가 q를 덮어씀(추가 작업 없음).
> - live 검증(quota 100/day 중 1회): `run_collection_probe --source newsapi --query "AI semiconductor"
>   --json` → **LIVE_SUCCESS, items_found=3**, 3건 전부 고관련(Sigurd chip/Marvell semiconductor/
>   China AI data center) — relevance HIGH. NEWSAPI_API_KEY 존재 확인(값 비노출).
> - 테스트: `ingestion/tests/unit/test_newsapi_everything.py` 3 passed(endpoint/no-country+기본q/query
>   override 전역불변). 전체 회귀 526 passed. 기존 `test_query_injection.py` newsapi 단언은 q/params만
>   검사하므로 회귀 없음.

> 선행: 01. 변경: `_SERVICE_CONFIGS` 1곳 + `_PROBE_SPEC` 1곳 + 테스트. live 검증 1회 (quota 100/day 중 1).

## 1. 해석 — 왜 0건이었나

docs/89 실측: `top-headlines?q=have duty to stay on` → 0건, `q=box office` → 0건 (LIVE_PARTIAL ×2). 원인은 API 계약이다:
- `/v2/top-headlines`는 "현재 헤드라인 풀" 안에서만 q를 필터링한다. 헤드라인 풀은 수십 건 수준이라 임의 phrase는 거의 항상 0건. **enrichment(과거 기사 검색) 용도와 구조적으로 부적합.**
- `/v2/everything`은 전체 아카이브 검색으로 q가 필수 입력이며 phrase 검색을 지원한다. 단 free(Developer) plan은 **기사 노출이 24시간 지연**되고 최근 1개월 범위만 검색된다 — enrichment 용도로는 허용 가능한 제약 (사건 확장 수집은 보통 발생 후 수 시간~수일 윈도우).
- 추가 계약 차이: everything은 `country` 파라미터를 **지원하지 않으며**(보내면 400), q/qInTitle/sources/domains 중 하나가 **필수**다. 따라서 query 없는 기본 probe도 기본 q가 있어야 한다.

## 2. 구현 diff

### (a) `ingestion/runners/run_api_connectivity_check.py` — endpoint 교체 (원본 309~317행)

```python
    "newsapi": {
        "keys": ["NEWSAPI_API_KEY"],
        "auth": "query_param_apiKey",
        "endpoint": "https://newsapi.org/v2/everything",
        "free_plan": "Developer: 100 req/day; no commercial use on free plan; everything은 24h 지연+최근 1개월",
        "docs_url": "https://newsapi.org/docs",
        "layer": "search_enrichment",
        "note": "top-headlines+q 0건 실측(docs/89)으로 everything 전환 (2026-06-13). everything은 q 필수.",
    },
```

### (b) `ingestion/probes/api_probe.py` — `_PROBE_SPEC["newsapi"]` 교체 (원본 201~206행)

```python
    "newsapi": {
        # /v2/everything: q 필수, country 미지원(400). 기본 q는 연결성 체크용.
        "extra_params": {"q": "news", "pageSize": "3", "sortBy": "publishedAt", "language": "en"},
        "meaningful_fields": ["articles"],
        "response_format": "json",
        "query_param": "q",
    },
```
- `country` 제거가 핵심 (everything에 보내면 400). `sortBy=publishedAt`은 enrichment가 "최신 관련 기사"를 원하기 때문. `language=en`은 ko 미지원 소스로 이미 라우팅되어 있으므로(2차 runner `_LANG_CAPS`) 정합.
- query 주입 시 `_apply_query_override`가 `extra_params["q"]`를 덮어쓴다 — 기존 메커니즘 그대로, 추가 작업 없음.

## 3. 신규 테스트 — `ingestion/tests/unit/test_newsapi_everything.py`

```python
def test_newsapi_endpoint_is_everything():
    from ingestion.runners.run_api_connectivity_check import _SERVICE_CONFIGS
    assert _SERVICE_CONFIGS["newsapi"]["endpoint"].endswith("/v2/everything")


def test_newsapi_spec_has_no_country_and_default_q():
    from ingestion.probes.api_probe import _PROBE_SPEC
    spec = _PROBE_SPEC["newsapi"]
    assert "country" not in spec["extra_params"], "everything은 country 미지원(400)"
    assert spec["extra_params"].get("q"), "everything은 q 필수"
    assert spec["query_param"] == "q"


def test_newsapi_query_injection_overrides_default_q():
    from ingestion.probes.api_probe import _PROBE_SPEC, _apply_query_override
    spec = _apply_query_override(_PROBE_SPEC["newsapi"], "box office")
    assert spec["extra_params"]["q"] == "box office"
    assert _PROBE_SPEC["newsapi"]["extra_params"]["q"] == "news"  # 전역 불변
```

**회귀 주의**: 기존 `test_query_injection.py`에 newsapi 관련 단언(top-headlines 전제)이 있는지 grep으로 확인 (`Select-String -Path ingestion\tests\unit\test_query_injection.py -Pattern newsapi`). top-headlines URL이나 country를 단언하는 테스트가 있으면 **이번 전환에 맞게 그 단언만** 갱신하라 (무관 단언 수정 금지).

## 4. live 검증 (1회) + 종결 기준

```powershell
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_collection_probe --source newsapi --query "AI semiconductor" --json
```
- [ ] status=LIVE_SUCCESS, items_found ≥ 1, sample title이 query와 관련 (육안 + relevance high 기대)
- [ ] 0건이면: raw artifact에서 `totalResults` 확인 — totalResults>0 + articles 0이면 plan 제약(지연) 문제로 진단하고 `qInTitle` 또는 날짜 범위(`from`) 조정 실험 1회. totalResults=0이면 query를 일반어("samsung")로 1회 교차 검증 후, 그래도 0이면 key plan 상태를 UNKNOWN으로 기록하고 DEFERRED.
- [ ] 단위 테스트 3건 + 전체 회귀 통과
- [ ] docs/70 newsapi 행, docs/89 §5-1 next_action 갱신 (RISK-S04 닫힘 표기)

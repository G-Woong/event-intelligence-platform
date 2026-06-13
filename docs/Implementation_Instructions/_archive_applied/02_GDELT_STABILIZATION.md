# 02. gdelt 안정화 — 429 원인 규명 + PARSE_ERROR 해소 + 장문 query 절단

> **상태: APPLIED — SUPERSEDED_BY [IMPLEMENTATION_TRACE_FINAL.md](./IMPLEMENTATION_TRACE_FINAL.md)** (2026-06-13). 본 지시문은 적용 완료. 원문은 이력 보존용이며 파괴적 삭제 금지. 현재 상태는 trace final + docs/ingestion/70·86·92 참조.

> ✅ **적용 완료 (2026-06-13)**: (a) gdelt spec에 `query_transform:"quote_phrase"` + `_transform_query` 추가 — 다단어 query를 큰따옴표로 감싸 GDELT의 200+오류텍스트 응답을 차단. (b) JSON parse except 블록을 비-JSON 200 정직 분류로 교체 — `rate limit`/`too many requests`/`limit requests`(실측 보강) → RATE_LIMITED, query 형식 오류 텍스트 → QUERY_ENCODING_OR_PARAM_ERROR (둘 다 기존 status, 신규 literal 없음). (c) `rate_limit_policy.yaml` gdelt: min_interval 5→60s, cooldown 300→900s. (d) `_audit_common.truncate_query`(토큰5·문자60 이중 상한) 추가 + `run_enrichment_live_audit._clean_query`가 이를 호출하도록 단일화(RISK-Q05). **STEP B 실측 보강**: live 1회 호출의 raw payload가 `"Please limit requests to one every 5 seconds..."` 평문이었고 이 문구가 §3-b 키워드에 안 걸려 `limit requests` 패턴을 추가함(docs/89 §5-2 PARSE_ERROR의 실제 원인일 개연성). 검증: 신규 `test_gdelt_stabilization.py` 6건 통과 + 전체 회귀 520 passed(509+5+6), 실패 0, secret scan PASS. **live LIVE_SUCCESS는 DEFERRED** — 외부 GDELT IP rate limit으로 429(코드 결함 아님), 00 §3.3에 따라 cooldown(900s) 만료 전 재호출 금지. 재개 조건은 체크리스트 항목 2 참조.

> 선행: **01 완료 필수** (429 재발 시 cooldown 기록이 안전망). 변경: `api_probe.py`, `rate_limit_policy.yaml`, `_audit_common.py`(또는 enrichment runner), 신규 테스트.

## 1. 해석 — 실측 사실과 원인 가설

실측 (docs/88, docs/89):
- 1차 audit: 단일 호출인데 **HTTP 429** (min_interval 5s 준수와 무관하게 발생)
- 2차 audit: query `have duty to stay on` → **PARSE_ERROR** (HTTP 200이지만 비-JSON 응답), query `global conflict` → **429**
- 시뮬레이션: cache_ttl 900s 덕분에 재호출 차단 (보호는 우연)

GDELT DOC 2.0 API(`https://api.gdeltproject.org/api/v2/doc/doc`)의 공개된 동작 특성에 기반한 가설:

**가설 H1 (PARSE_ERROR의 원인 — 유력)**: GDELT는 **여러 단어로 된 구(phrase)를 따옴표 없이 보내면 오류 메시지를 평문/HTML로, HTTP 200과 함께 반환**한다. 예: `query=have duty to stay on` → "Your query was too short or too long" 또는 "The phrase ... contains too common a word" 류의 텍스트 응답. 우리 파서는 JSON을 기대하므로 PARSE_ERROR가 된다. 즉 PARSE_ERROR는 네트워크 문제가 아니라 **query 형식 문제**일 가능성이 높다.
**가설 H2 (429의 원인)**: GDELT는 키 없는 public API로 IP 단위 rate limit이 엄격하다(비공식적으로 ~5초당 1회 + 부하 시 강화). 단일 호출 429는 ① 같은 라운드 내 직전 연결성 체크/다른 runner의 선행 호출 누적 ② 공유 IP(ISP NAT)에서 타 사용자 트래픽 ③ GDELT 서버 부하 시간대 중 하나다. **우리가 제어 가능한 것은 ①뿐**이므로, 간격을 보수적으로 늘리고 429 시 cooldown(01에서 수리됨)에 맡기는 것이 정답이다.

## 2. 루프 적용 (00 §3.2)

**STEP A 재현**: cooldown/cache 만료 확인 후(아래 명령으로 gate 상태 확인) 1회 호출:
```powershell
# gate 상태 확인 (호출 없음): rate_limit_cache.json에서 gdelt 키의 next_retry/calls 확인
Get-Content ingestion\outputs\state\rate_limit_cache.json | Select-String "gdelt"
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_collection_probe --source gdelt --json
```
**STEP B 진단**: 결과별 분기 —
- `LIVE_SUCCESS` → 1차 429는 일시적이었음. H2-②/③ 확정, 코드 수정은 §3의 (b)(c)만 적용 (방어적 조치).
- `RATE_LIMITED` → 01 수정 검증 기회: `rate_limit_cache.json`에 `next_retry.gdelt:` 키가 생겼는지 확인 (생겼으면 01 live 증거 확보). cooldown 만료까지 다른 소스 작업으로 전환.
- `PARSE_ERROR` → raw artifact(`ingestion/outputs/raw_payload/gdelt/` 최신 파일)의 처음 500자를 읽고 오류 문구를 체크리스트에 기록. H1 확정 여부 판단.

**STEP C 수정**: 아래 §3 전체 적용.

## 3. 구현 diff

### (a) phrase quoting — `ingestion/probes/api_probe.py`

`_apply_query_override` 함수(원본 384~409행)에 **소스별 query 변환 훅**을 추가한다. gdelt만의 특수 처리를 if문으로 박지 않고 spec 메타로 선언하는 이유: 이후 다른 소스(sec_edgar entity 검색 등)도 같은 메커니즘을 재사용하기 위함이다.

**(a-1)** `_PROBE_SPEC`의 gdelt entry(원본 100~105행)에 1키 추가:

```python
    "gdelt": {
        "extra_params": {"query": "samsung", "mode": "artlist", "format": "json", "maxrecords": "3"},
        "meaningful_fields": ["articles"],
        "response_format": "json",
        "query_param": "query",
        "query_transform": "quote_phrase",
    },
```

**(a-2)** `_apply_query_override` 바로 위에 변환 함수 추가 + 함수 본문에서 적용:

```python
def _transform_query(query: str, transform: str) -> str:
    """spec 메타 query_transform에 따른 소스별 query 전처리.

    quote_phrase: 공백 포함 다단어 query를 큰따옴표로 감싼다.
    GDELT DOC API는 따옴표 없는 다단어 구를 오류 텍스트(HTTP 200)로 응답한다 (docs/89 §5-2).
    """
    if transform == "quote_phrase":
        q = query.strip().strip('"')
        if " " in q:
            return f'"{q}"'
        return q
    return query
```

`_apply_query_override` 내부, deepcopy 직후·주입 직전에 1줄 삽입:

```python
    import copy
    spec = copy.deepcopy(probe_spec)
    transform = spec.get("query_transform", "")
    if transform:
        query = _transform_query(query, transform)
    if spec.get("query_in", "params") == "json_body":
        ...
```

### (b) 비-JSON 200 응답의 정직한 분류 — `ingestion/probes/api_probe.py`

현재 JSON 파싱 실패는 무조건 `PARSE_ERROR`(원본 757~759행)다. GDELT의 오류 텍스트는 진단 가능한 정보인데 버려진다. JSON 파싱 except 블록을 다음으로 교체:

```python
            except Exception as exc:
                logger.warning("JSON parse error for %s: %s", service_id, exc)
                lower_body = response_text[:500].lower()
                if "rate limit" in lower_body or "too many requests" in lower_body:
                    probe_status = "RATE_LIMITED"
                elif "query" in lower_body and (
                    "too short" in lower_body or "too long" in lower_body
                    or "too common" in lower_body or "invalid" in lower_body
                ):
                    # 서버가 query 형식 오류를 200+텍스트로 알린 경우 (GDELT 등)
                    probe_status = "QUERY_ENCODING_OR_PARAM_ERROR"
                else:
                    probe_status = "PARSE_ERROR"
```

근거: ① `QUERY_ENCODING_OR_PARAM_ERROR`는 **이미 존재하는 status**(`_NEXT_ACTION_MAP` 원본 335행)라 신규 literal 추가가 아니다. ② RATE_LIMITED로 재분류되면 01의 record 블록이 cooldown까지 기록한다 — soft 429 텍스트 응답도 보호망에 들어온다. ③ raw artifact는 이미 저장되므로(원본 699행) 원문 확인 경로는 유지된다.

**주의**: 이 분기는 `probe_status == "LIVE_SUCCESS"`인 fmt=json 경로 안에 있다. RATE_LIMITED로 재분류된 경우 01에서 추가한 return 직전 record 블록이 이를 잡아 next_retry_at을 채운다 — 추가 작업 불필요 (01을 먼저 적용해야 하는 이유).

### (c) 보수적 정책 강화 — `ingestion/configs/rate_limit_policy.yaml`

운영 권장 주기(docs/92)가 gdelt를 near_real_time 15분으로 분류했고, 실측상 5s 간격으로도 429가 났다. per_source.gdelt를 다음으로 교체:

```yaml
  gdelt:
    min_interval_seconds: 60
    cooldown_on_429_seconds: 900
    max_retries_on_429: 1
    cache_ttl_seconds: 900
```

근거: min_interval 5→60s (단발 검증·audit에서 연속 호출 금지 — 운영 주기 15분과 무관하게 같은 프로세스 내 보호), cooldown 300→900s (실측상 300s 후 재호출이 또 429를 맞았으므로 GDELT의 윈도우는 더 길다고 추정 — UNKNOWN이므로 보수적으로).

### (d) 장문 query 절단 (RISK-Q05, 체크리스트 #14) — `ingestion/runners/_audit_common.py`

opendart 공시명("일괄신고서(집합투자증권-신탁형)…") 같은 장문이 그대로 query로 가서 0건이 났다. 공용 헬퍼를 `_audit_common.py`의 relevance 섹션 근처에 추가:

```python
def truncate_query(query: str, max_tokens: int = 5, max_chars: int = 60) -> str:
    """장문 seed query 절단 (RISK-Q05). 토큰 수·문자 수 이중 상한.

    괄호/특수문자 안의 부연은 검색 적합성이 낮으므로 먼저 제거한다.
    """
    q = re.sub(r"[\(\)\[\]<>{}]", " ", query or "")
    q = re.sub(r"\s+", " ", q).strip()
    tokens = q.split(" ")[:max_tokens]
    out = " ".join(tokens)
    return out[:max_chars].strip()
```

그리고 `ingestion/runners/run_enrichment_live_audit.py`의 hot seed 도출(`derive_hot_queries` / `_clean_query`) 마지막 단계에서 모든 query에 `truncate_query`를 적용하도록 1줄 연결한다 (`_clean_query`가 이미 max_tokens=5를 하고 있으면 max_chars 상한만 추가 적용되는지 확인하고, 중복 로직이면 `_clean_query` 내부가 `truncate_query`를 호출하게 단일화하라 — 같은 규칙 두 벌 금지).

## 4. 신규 테스트 — `ingestion/tests/unit/test_gdelt_stabilization.py`

```python
import os
os.environ.setdefault("INGESTION_RATE_LIMIT_BACKEND", "memory")


def test_quote_phrase_wraps_multiword():
    from ingestion.probes.api_probe import _transform_query
    assert _transform_query("have duty to stay on", "quote_phrase") == '"have duty to stay on"'
    assert _transform_query("samsung", "quote_phrase") == "samsung"           # 단어 1개는 그대로
    assert _transform_query('"already quoted"', "quote_phrase") == '"already quoted"'  # 이중 인용 방지


def test_apply_query_override_uses_transform():
    from ingestion.probes.api_probe import _PROBE_SPEC, _apply_query_override
    spec = _apply_query_override(_PROBE_SPEC["gdelt"], "global conflict")
    assert spec["extra_params"]["query"] == '"global conflict"'
    # 전역 불변 (기존 함정 1 회귀 방지)
    assert _PROBE_SPEC["gdelt"]["extra_params"]["query"] == "samsung"


def test_non_json_rate_limit_text_reclassified(monkeypatch):
    # §3-(b): 200 + 'rate limit' 텍스트 → RATE_LIMITED (+01의 cooldown 기록)
    # 01 문서의 _FakeResponse/_FakeClient 패턴 재사용 (text='You have exceeded the rate limit', json() raises)
    ...


def test_non_json_query_error_text_reclassified(monkeypatch):
    # 200 + 'your query was too short' 텍스트 → QUERY_ENCODING_OR_PARAM_ERROR
    ...


def test_truncate_query():
    from ingestion.runners._audit_common import truncate_query
    long_q = "일괄신고서 (집합투자증권-신탁형) 제출 관련 안내 공시 자료 추가 첨부"
    out = truncate_query(long_q)
    assert len(out) <= 60 and len(out.split()) <= 5
    assert "(" not in out
```

`...` 표시 테스트 2건은 01 문서의 `_FakeResponse`/`_FakeClient`/`_patch_httpx`를 모듈 공유(또는 `conftest.py` 승격)해 완성하라. 두 테스트 모두 `result.status` 단언 + RATE_LIMITED 건은 `result.next_retry_at is not None`까지 단언한다.

## 5. live 검증 (STEP D — gate 준수)

```powershell
# cooldown/cache 만료 확인 후 1회만. quoting이 적용된 다단어 query로:
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_collection_probe --source gdelt --query "global conflict" --json
```
기대: `status=LIVE_SUCCESS`, `items_found≥1`, sample title 존재. 429를 만나면: `rate_limit_cache.json`의 `next_retry."gdelt:\"global conflict\""` 키 생성 확인(=01 live 증거) 후 **900s 대기 또는 다른 항목 진행 후 복귀** (iteration당 live 1회 규칙).

## 6. 종결 기준

- [ ] 단위 테스트 5건 통과 + 전체 회귀 통과
- [ ] live 1회 LIVE_SUCCESS (items≥1) — 또는 4 iteration 내 불가 시 DEFERRED(다음 cooldown 윈도우) 기록
- [ ] 429 발생 시 cooldown 기록 실증 스크린샷 대신 `rate_limit_cache.json` 발췌를 체크리스트에 기록
- [ ] 운영 노트: docs/92의 gdelt 주기를 "15분, 연속 실패 시 자동 cooldown 900s" 로 갱신

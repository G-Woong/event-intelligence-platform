# 08. API 소스 보강 — partial/no 소스 전량 종결 (federal_register·igdb·culture_info·hacker_news·bok_ecos·eia·its·시장 수치)

> **상태: APPLIED — SUPERSEDED_BY [IMPLEMENTATION_TRACE_FINAL.md](./IMPLEMENTATION_TRACE_FINAL.md)** (2026-06-13). 본 지시문은 적용 완료. 원문은 이력 보존용이며 파괴적 삭제 금지. 현재 상태는 trace final + docs/ingestion/70·86·92 참조.

> 선행: 01. 변경: `api_probe.py`(`_PROBE_SPEC` 3곳 + hn detail), `_audit_common.py`(`_SAMPLE_PATHS`/XML 맵/numeric signal/`collect_samples`), 테스트. live 검증: 소스당 1회 (전부 저쿼터 안전 소스).

## 0. 공통 원칙 — "no/partial"의 3가지 서로 다른 원인을 구분하라

직전 audit의 seed_ready no/partial은 한 덩어리가 아니다. 원인별로 처방이 다르다:
- **(A) 요청이 필드를 안 가져옴** (federal_register, igdb): probe spec의 요청 파라미터 수정 → 데이터 자체가 풍부해짐.
- **(B) 데이터는 다 왔는데 sample 매핑이 없어 평가 불가** (bok_ecos, eia, its, culture_info, hacker_news 부분): `_SAMPLE_PATHS`/XML 맵 추가 → **수집 코드는 무수정**.
- **(C) seed 필드 개념 자체가 부적합** (finnhub 등 시장 수치): 평가 체계를 분리 → 분류로 종결.
작업 전 반드시 해당 소스의 **기존 raw artifact를 먼저 읽고** (이미 LIVE_SUCCESS라 재호출 불필요) 실제 필드명을 확인하라. 아래 diff의 필드명은 표준 문서 기반 추정이 섞여 있다 — **artifact와 다르면 artifact가 정답이다.**

## 1. (A) federal_register — `fields[]` 확장 (체크리스트 #9)

원인: `_PROBE_SPEC` (api_probe.py:112-117)이 `"fields[]": "title"`만 요청 → 응답에 title만 옴 → url/date 부재는 당연한 결과였다.

```python
    "federal_register": {
        # fields[]를 title만 받던 것이 partial의 원인 (docs/88). httpx는 list 값을
        # 같은 키 반복으로 직렬화한다 (fields[]=title&fields[]=html_url&...).
        "extra_params": {
            "per_page": "3",
            "order": "newest",
            "fields[]": ["title", "html_url", "publication_date", "abstract", "document_number"],
        },
        "meaningful_fields": ["results", "count"],
        "response_format": "json",
        "query_param": "conditions[term]",
    },
```
`_SAMPLE_PATHS["federal_register"]`는 이미 html_url/publication_date/abstract를 본다(_audit_common.py:184-185) — **매핑 수정 불필요**, 요청만 고치면 맞물린다.
검증(live 1회): `run_collection_probe --source federal_register --json` → sample에 url+published_at 존재. 단위 테스트: spec의 fields[]가 list이고 5개 필드를 포함함을 단언.

## 2. (A) igdb — url/날짜 요청 + root 리스트 샘플 매핑 (체크리스트 #10a)

원인 2중: ① apicalypse body가 `name,first_release_date,rating`만 요청 — `url` 미요청 ② igdb 응답은 **root가 JSON 배열**인데 `_SAMPLE_PATHS` entry가 없어 generic fallback이 돌고, `first_release_date`(unix epoch)는 generic time 키 목록에 없어 날짜가 빠졌다.

**(a)** `_PROBE_SPEC["igdb"]` (api_probe.py:274-280):
```python
        "apicalypse_body": "fields name,url,first_release_date,rating; where rating > 80; limit 3;",
```
**(b)** `_audit_common.py` — root 리스트 지원 + epoch 변환. `_sample_from_json`의 spec 해석부에서 list 경로 `"$root"`를 인정:
```python
    spec = _SAMPLE_PATHS.get(source_id)
    items = None
    if spec:
        items = parsed if spec["list"] == "$root" else _dig(parsed, spec["list"])
```
`_SAMPLE_PATHS`에 추가:
```python
    "igdb": {"list": "$root", "title": "name", "url": "url",
             "snippet": "rating", "published_at": "first_release_date"},
```
epoch 정규화 — samples.append 직전에:
```python
        if isinstance(published, (int, float)) and published > 10_000_000:
            from datetime import datetime, timezone
            published = datetime.fromtimestamp(published, tz=timezone.utc).strftime("%Y-%m-%d")
```
검증: 단위 테스트(fake root-list payload) + live 1회 → sample에 url(igdb.com 경로)·날짜 존재 → seed_ready yes.

## 3. (B) culture_info — XML 필드명 맵 (체크리스트 #10b)

원인: `_sample_from_xml`은 RSS 계열 필드명(title/pubDate 등)만 안다. data.go.kr period2 응답의 `<item>` 자식 필드명은 다르다. **먼저 raw artifact를 열어 실제 태그명을 확인하라** (후보: `title`/`TITLE`, `startDate`/`STRTDATE`, `place`, `url` — UNKNOWN, artifact가 정답).

일반화 구현 — `_audit_common.py`에 per-source XML 필드명 확장 맵을 두고 `_sample_from_xml`의 `_find_text` 후보에 합류:
```python
# per-source XML 태그명 확장 (RSS 표준명 뒤에 시도)
_XML_FIELD_NAMES: dict[str, dict[str, tuple[str, ...]]] = {
    "culture_info": {
        "title": ("title", "TITLE"),
        "url": ("url", "URL"),
        "snippet": ("place", "PLACE", "area"),
        "published_at": ("startDate", "STRTDATE", "beginDe"),
    },
    "kopis": {"published_at": ("prfpdfrom",)},   # 기존 하드코딩의 선언화 (동작 동일 유지)
}
```
`_sample_from_xml` 내 4개 `_find_text(...)` 호출에 `*(_XML_FIELD_NAMES.get(source_id, {}).get("<필드>", ()))`를 추가 인자로 전달. kopis의 기존 거동(`.//db`, prfpdfrom)은 회귀 테스트로 고정.
검증: 기존 artifact 파일로 단위 테스트 (네트워크 0회) → title+published_at 채워짐 → partial→yes.

## 4. hacker_news — item detail 2차 호출 (체크리스트 #11)

원인: `topstories.json`은 **정수 id 배열**만 반환 — title/url이 구조적으로 없다. Firebase API 계약상 detail은 `/v0/item/{id}.json` 별도 호출이다.

설계: probe spec 메타로 선언하고 `run_api_live_probe`의 LIVE_SUCCESS 후처리에서 detail을 ≤3건 가져온다 (소스별 if문 최소화 — 메타 주도).

**(a)** `_PROBE_SPEC["hacker_news"]`:
```python
    "hacker_news": {
        "extra_params": {},
        "meaningful_fields": [],
        "response_format": "json",
        "detail_endpoint_template": "https://hacker-news.firebaseio.com/v0/item/{id}.json",
        "detail_limit": 3,
    },
```
**(b)** `api_probe.py` — JSON 파싱 성공 블록 뒤(extracted 저장 전)에:
```python
    # detail_endpoint_template: id 목록형 응답의 상세 2차 호출 (hacker_news 등)
    detail_tpl = probe_spec.get("detail_endpoint_template")
    if detail_tpl and probe_status == "LIVE_SUCCESS" and fmt == "json":
        try:
            ids = parsed if isinstance(parsed, list) else []
            detail_items: list[dict] = []
            with httpx.Client(timeout=_TIMEOUT_SEC) as client:
                for _id in ids[: int(probe_spec.get("detail_limit", 3))]:
                    r = client.get(detail_tpl.format(id=_id), headers=headers)
                    if r.status_code == 200:
                        d = r.json()
                        if isinstance(d, dict):
                            detail_items.append({
                                "title": d.get("title"), "url": d.get("url"),
                                "time": d.get("time"), "id": d.get("id"),
                                "score": d.get("score"),
                            })
                    time.sleep(0.2)
            if detail_items:
                extracted["items"] = detail_items
                items_found = len(detail_items)
        except Exception as exc:
            logger.warning("detail fetch failed for %s: %s", service_id, exc)
```
(`import time`은 파일 상단에 이미 없으면 추가. detail 호출도 동일 UA/타임아웃. 실패해도 본 probe는 유지 — 부가 기능 무해성 원칙.)
**(c)** sample 연결 — detail은 `extracted_payload`에 저장된다. `_audit_common.collect_samples`가 raw에서 빈 결과면 extracted_payload도 시도하도록 1분기 추가:
```python
def collect_samples(result, max_samples: int = 3) -> list[dict]:
    raw_path = result.artifact_paths.raw_payload or result.artifact_paths.raw_html
    if raw_path:
        samples = extract_sample_items(result.source_id, raw_path, max_samples)
        if samples:
            return samples
    ep = getattr(result.artifact_paths, "extracted_payload", None)
    if ep:
        samples = extract_sample_items(result.source_id, ep, max_samples)
        if samples:
            return samples
    ...
```
+ `_SAMPLE_PATHS["hacker_news"] = {"list": "items", "title": "title", "url": "url", "snippet": "score", "published_at": "time"}` (time도 §2의 epoch 정규화 적용 — 정규화를 spec 분기 밖 공통 위치에 두라).
검증: 단위 테스트(fake client가 ids→details 순차 응답) + live 1회 → seed_ready yes. epoch time → ISO 변환 확인.

## 5. (B) bok_ecos / eia / its — `_SAMPLE_PATHS` 추가 (체크리스트 #12)

**artifact 우선 확인 후** 다음을 시작점으로 추가 (필드명이 다르면 artifact 기준 수정):
```python
    "bok_ecos": {"list": "StatisticTableList.row", "title": "STAT_NAME",
                 "url": None, "snippet": "CYCLE", "published_at": None},
    "eia": {"list": "response.routes", "title": "name", "url": None,
            "snippet": "description", "published_at": None},
    "its": {"list": "body.items", "title": "roadName", "url": None,
            "snippet": "speed", "published_at": "createdDate"},
```
주의: ① eia의 현 endpoint는 `/v2/` 루트(라우트 카탈로그)다 — sample은 "카탈로그 확인"용이고, 사건용 시계열은 후속 라운드에서 route별 endpoint로 분리한다고 docs/86에 명기 ② its는 items가 3만+건이므로 sample 추출만 하고 전체 순회 금지 (기존 `[:max_samples]` 절단이 이미 보장 — 테스트로 고정).
검증: 기존 artifact로 단위 테스트 3건 (네트워크 0회).

## 6. (C) 시장/수치 소스 — numeric signal 평가 경로 (체크리스트 #13)

finnhub(flat quote)·alpha_vantage(Time Series dict)·polygon(prev-day aggs)·coinbase_market는 title/url 개념이 없어 seed 5필드 체계로는 영원히 no다. 이는 결함이 아니라 **분류 오류**이므로 평가 체계를 분리해 종결한다.

`_audit_common.py`에 추가:
```python
# 수치 임계값 signal 소스 — seed 5필드 대신 signal 기준으로 평가 (docs/88 §3-5)
NUMERIC_SIGNAL_SOURCES: frozenset[str] = frozenset({
    "finnhub", "alpha_vantage", "polygon", "coinbase_market",
    "binance_market", "twelve_data", "its", "eia", "bok_ecos", "kma",
})


def seed_ready_label_for(source_id: str, count: int, items_found: int) -> str:
    """seed 평가 라벨. 수치 signal 소스는 데이터 수신 자체가 ready."""
    if source_id in NUMERIC_SIGNAL_SOURCES:
        return "signal_ready" if items_found > 0 else "no"
    return seed_ready_label(count)
```
`run_primary_seed_live_audit.py`에서 `seed_ready_label(...)` 호출부를 `seed_ready_label_for(source_id, count, items_found)`로 교체 (기존 `seed_ready_label`은 삭제하지 않는다 — 기존 테스트가 참조). 보고서 라벨에 `signal_ready`가 추가되는 것은 docs/91 readiness 분류(수치 임계값 별도 취급)와 정합.
검증: 단위 테스트 — finnhub: items 1 → `signal_ready`, yna: 기존과 동일 라벨 (회귀).

## 7. 테스트 파일 구성 — `ingestion/tests/unit/test_api_source_field_fixes.py`

위 §1~6의 단언을 한 파일에 모은다 (fixture payload는 **기존 raw artifact에서 개인정보/장문 없이 최소 발췌**해 테스트 내 문자열로). 최소 케이스 목록: federal_register fields[] 단언 / igdb $root 샘플 + epoch 변환 / culture_info XML 맵 / kopis 회귀 / hacker_news detail mock e2e / collect_samples extracted fallback / bok_ecos·eia·its 샘플 3건 / numeric signal 라벨 2건 — **합계 ≥12 테스트**.

## 8. live 일괄 재검증 + 종결 기준

모든 diff 적용 + 전체 회귀 통과 후, 대상 소스만 1차 audit 재실행 (각 1회 호출, 전부 무쿼터/고쿼터 안전):
```powershell
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_primary_seed_live_audit --sources federal_register,igdb,culture_info,hacker_news,bok_ecos,eia,its,finnhub
```
- [ ] federal_register/igdb/culture_info/hacker_news → seed_ready **yes**
- [ ] bok_ecos/eia/its → sample 추출 성공 (+ numeric signal 분류 라벨)
- [ ] finnhub 등 → `signal_ready`
- [ ] 단위 테스트 ≥12 + 전체 회귀 통과, docs/70 해당 행 전부 갱신

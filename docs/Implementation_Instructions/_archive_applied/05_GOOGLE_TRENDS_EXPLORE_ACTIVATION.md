# 05. google_trends_explore 활성화 — DEFERRED 원인 식별 + 활용 경로 구현·검증

> **상태: APPLIED — SUPERSEDED_BY [IMPLEMENTATION_TRACE_FINAL.md](./IMPLEMENTATION_TRACE_FINAL.md)** (2026-06-13). 본 지시문은 적용 완료. 원문은 이력 보존용이며 파괴적 삭제 금지. 현재 상태는 trace final + docs/ingestion/70·86·92 참조.

> 선행: 01 (429 기록 안전망). 권장 병행: 07 §2 (Route 2 위임 — 완료 시 통합 경로까지 검증 가능). live 호출: **iteration당 최대 1회, 이 문서 전체에서 최대 2회** (min_interval 7200s 정책 준수).

## 1. 해석 — "DEFERRED"의 정확한 원인 (코드 부재가 아니다)

조사로 확정된 사실:
- `playwright_probe_sites.yaml`의 `google_trends_explore`는 **`deferred: false`** — site spec, selector 3종, search_strategy까지 전부 구현되어 있다.
- `ingestion/probes/playwright_probe.py:94-103`은 start_url의 `{query}`/`{region}` 템플릿 치환을 **이미 구현**했다 (query 기본 "samsung", region 기본 "KR").
- `rate_limit_policy.yaml:24-28`에 min_interval 7200s / cooldown 3600s / cache_ttl 7200s 보수 정책이 **이미 존재**한다 (과거 1800s 간격에서도 429 재발 이력 때문 — 정책 주석 참조).
- 직전 라운드의 DEFERRED는 **audit runner의 `--include-trends-explore` 플래그가 기본 off였고 이번에 켜지 않았기 때문**(docs/93 §2-17)이다. 즉 "구현 안 됨"이 아니라 "검증 실행을 의도적으로 미룸"이다.

따라서 이 문서의 일은 ① 단일 live 검증으로 selector 동작 여부를 확정하고 ② 운영 활용 모델(주기 수집에서의 위치)을 코드·정책에 고정하는 것이다.

## 2. 활용 모델 — 이벤트 큐에서의 위치 (설계 결정)

trends_explore는 **input_type=keyword** (start_url에 `{query}` 필수)다. 따라서 "그 자체가 1차 주기 소스"가 아니라:

- **1차 주기 소스는 google_trending_now / signal_bz / loword** (keyword 불필요, 실검 목록 자체가 seed).
- **trends_explore는 hot seed keyword의 related-queries 확장기** — 1차에서 감지된 keyword를 받아 연관 검색어를 돌려주는 **2차 enrichment** 위치다. 주기 수집 큐에서는 "사이클당 최상위 hot seed 1개에 대해서만, gate(7200s) 통과 시 1회" 패턴으로 편성한다.

이 분류를 `docs/ingestion/86`(role matrix)의 google_trends_explore 행에 반영하라: role=`enrichment(related_queries)`, recommended_frequency=`2h+, hot seed 트리거`.

## 3. 검증 절차 (루프 STEP A~E)

### STEP A — gate 확인 (호출 없음)

```powershell
Get-Content ingestion\outputs\state\rate_limit_cache.json | Select-String "google_trends_explore"
Get-Content ingestion\outputs\state\source_health.json | Select-String -Context 0,8 "google_trends_explore"
```
`next_retry`가 미래이거나 cache age < 7200s면 만료까지 이 항목을 일시정지하고 다른 문서 작업 진행 (00 §3.3 인터리빙).

### STEP B — 단독 경로 live 검증 (1회)

기존 runner를 그대로 사용한다 (Route 2 위임 전에도 동작하는 경로):

```powershell
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_playwright_probe --site google_trends_explore --query "이재명" --region KR
```
query는 **검증 시점의 실제 hot seed**(직전 1차 audit jsonl에서 signal_bz keyword 1개)를 쓴다 — 죽은 keyword는 related queries가 비어 LIVE_PARTIAL로 오판된다.

결과 분기:
- **LIVE_SUCCESS (items≥1)** → selector 유효. STEP D로.
- **LIVE_PARTIAL (page title만/0건)** → selector 미매칭. `outputs/rendered_dom/google_trends_explore/` 최신 html과 screenshot을 검안하고 **06 문서의 structure explorer**로 후보 selector를 도출 → `playwright_probe_sites.yaml`의 selectors.list 갱신 → 다음 gate 윈도우에서 재검증 (이 갱신은 06/07과 같은 절차).
  - 참고 가설: trends explore는 SPA로 위젯이 늦게 뜬다 — spec에 `wait_after_ms`가 **없다** (trending_now/signal_bz는 있음). selector 교체 전에 `wait_after_ms: 5000` + `selectors.wait_for: ".fe-related-queries-item"` 추가가 더 싼 1차 실험이다.
- **RATE_LIMITED** → playwright_probe가 cooldown 3600s를 기록한다(`playwright_probe.py:148-171` — 이미 구현됨). 기록 확인 후 윈도우 만료까지 일시정지. **iteration당 1회 규칙 엄수, 연속 재시도 절대 금지** (CLAUDE.md 하드 제약).
- **BLOCKED (CAPTCHA)** → 우회 금지. screenshot 증거와 함께 `BLOCKED_TERMINAL` 후보로 기록하되, 1회 관찰만으로 terminal 확정하지 말고 다음 윈도우 1회 재확인 후 판정.

### STEP C — 통합 경로 검증 (07 §2 완료 후, 1회)

07의 Route 2 위임이 적용되면 audit runner 경유 검증으로 승격한다:
```powershell
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_primary_seed_live_audit --sources google_trends_explore --include-trends-explore
```
이 경로는 gate_check → 호출 → `record_call`(cache_ttl 7200 기록)까지 자동 수행한다. 검증 포인트: ① jsonl record의 `audit_action="called"` ② 직후 같은 명령 재실행(dry: gate만 보면 됨) 시 `cache_skip` — **즉시 반복 호출이 구조적으로 차단됨을 실증** (이것이 "내가 활용 가능하게"의 핵심: 운영 중 실수로도 429 폭주가 안 남).

## 4. 단위 테스트 — `ingestion/tests/unit/test_trends_explore_activation.py`

전부 네트워크 없음:

```python
def test_spec_not_deferred_and_has_query_template():
    from ingestion.probes.site_specs import load_site_specs
    spec = load_site_specs()["google_trends_explore"]
    assert spec.deferred is False
    assert "{query}" in spec.start_url and "{region}" in spec.start_url
    assert spec.min_interval_minutes >= 120


def test_rate_policy_is_conservative():
    from ingestion.core.rate_limit_policy import load_rate_limit_policy
    p = load_rate_limit_policy("google_trends_explore")
    assert p.min_interval_seconds >= 7200
    assert p.max_retries_on_429 == 0          # 루프 내 재시도 금지의 코드화
    assert p.cache_ttl_seconds >= 7200


def test_url_template_substitution(monkeypatch):
    # playwright_probe의 치환 로직 검증: open_page를 가로채 URL만 캡처, html=None 반환
    import asyncio
    from ingestion.probes import playwright_probe as pp
    captured = {}

    async def fake_open_page(url, **kw):
        captured["url"] = url
        return None

    monkeypatch.setattr(pp, "open_page", fake_open_page)
    pp.run_playwright_probe("google_trends_explore", query="이재명 멜로니", region="KR")
    assert "geo=KR" in captured["url"]
    assert "{query}" not in captured["url"] and "{region}" not in captured["url"]
    assert "%EC%9D%B4%EC%9E%AC%EB%AA%85" in captured["url"]  # quote_plus 인코딩 확인
```

(wait_after_ms를 spec에 추가한 경우 `assert spec.wait_after_ms >= 3000` 단언도 추가.)

## 5. 종결 기준

- [ ] 단위 테스트 3건 통과 + 전체 회귀 통과
- [ ] live 1회에서 related query item ≥1 추출 (증거: raw_signal artifact 경로 + keyword 1건) — 또는 RATE_LIMITED/BLOCKED 관찰 시 cooldown·차단 증거와 함께 DEFERRED(다음 윈도우 시각 명기)
- [ ] cache_skip 재실행 실증 1건 (STEP C, 07 완료 시)
- [ ] docs/86 role 행 갱신 (enrichment(related_queries)) + docs/92 주기 표에 "hot seed 트리거, 2h+" 반영
- [ ] 체크리스트 #5 갱신

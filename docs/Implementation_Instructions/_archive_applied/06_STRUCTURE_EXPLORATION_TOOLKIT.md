# 06. 페이지 구조 탐색 툴킷 — `run_structure_explorer` 신설

> **상태: APPLIED — SUPERSEDED_BY [IMPLEMENTATION_TRACE_FINAL.md](./IMPLEMENTATION_TRACE_FINAL.md)** (2026-06-13). 본 지시문은 적용 완료. 원문은 이력 보존용이며 파괴적 삭제 금지. 현재 상태는 trace final + docs/ingestion/70·86·92 참조.

> 선행: 09 §1 (playwright chromium 설치 확인). 산출물: `ingestion/runners/run_structure_explorer.py` + 테스트. **07의 selector 소스 5종과 03/05의 fallback 진단이 전부 이 runner를 사용한다.**

## 1. 해석 — 왜 이 도구가 필요한가

직전 라운드의 RISK-S05(selector 미매칭 4종)는 모두 같은 패턴이다: YAML에 손으로 추정해 적은 CSS selector가 실제 렌더링된 DOM과 어긋났고, **어긋났을 때 "왜, 무엇으로 바꿔야 하는지"를 알아내는 표준 절차가 없었다.** 사람이 매번 rendered_dom을 열어 눈으로 찾는 방식은 에이전트 오케스트레이션에서 재현 불가능하다.

이 runner는 에이전트가 임의 사이트에 대해 **탐색→가설→검증을 기계적으로 수행할 수 있는 영구 경로**다. 출력은 "사람이 읽는 보고서"가 아니라 **그대로 YAML에 붙일 수 있는 selector 제안 패치**다. 한 번 만들면: selector가 깨질 때마다(사이트 개편) 에이전트가 이 runner를 돌려 스스로 복구한다 — selector self-healing 루프의 토대(09 §2-8).

## 2. 기존 자산 (재사용 — 새로 만들지 말 것)

| 자산 | 위치 | 재사용 포인트 |
|------|------|--------------|
| `open_page(..., capture_network=True)` | `ingestion/tools/playwright_browser_tool.py:24` | 렌더링 + **XHR/JSON 응답 로그**(`last_network_log` 모듈 변수, URL/method/status/content-type + ≤4KB JSON body). 숨은 JSON API 발견의 핵심 |
| `extract_with_dom_heuristic(html, url)` | `ingestion/tools/dom_candidate_extractor.py:23` | DOM 휴리스틱 본문/후보 추출 (`ExtractionResult` 반환) |
| `extract_with_trafilatura(html, url)` | `ingestion/tools/trafilatura_extractor.py:11` | 본문 추출 1순위 |
| `load_site_specs()` | `ingestion/probes/site_specs.py` | 기존 selector를 비교 기준선으로 로드 |
| `classify_content_blocker`, `_detect_429` | error_taxonomy / playwright_probe | 차단/429 페이지를 탐색 결과로 오인하지 않기 위한 전처리 |
| screenshot/rendered_dom 저장 | `artifact_store` | 증거 보존 |

## 3. 구현 명세 — `ingestion/runners/run_structure_explorer.py`

### 3-1. CLI

```
--site <site_id>          # playwright_probe_sites.yaml의 site (start_url/기존 selector 로드)
--url <직접 URL>          # site 미등록 페이지 탐색 (--site와 택일, 둘 다 없으면 에러)
--query <q> --region <r>  # start_url 템플릿 치환 (playwright_probe.py:94-103과 동일 규칙 — quote_plus)
--wait-ms 4000            # 렌더 후 대기 (기본 3000)
--max-candidates 10       # selector 후보 상한
--offline-dom <경로>      # 저장된 rendered_dom 파일로 재분석 (네트워크 0회 — 테스트/재진단용)
```

`--offline-dom`이 핵심 설계다: **live 1회로 DOM을 떠 놓으면 이후 분석·재분석은 전부 오프라인**이다 (호출 예산 절약 + 단위 테스트 가능).

### 3-2. 처리 단계 (함수 단위로 분리해 작성하라)

```python
def explore(site_id_or_url, query, region, wait_ms, offline_dom) -> dict:
    # [1] fetch (offline_dom 있으면 생략): open_page(capture_network=True,
    #     wait_after_ms=wait_ms, scroll=True, screenshot_path=..., dom_snapshot_path=...)
    #     주의: dom_snapshot_path는 50KB 절단 저장이므로(playwright_browser_tool.py:112)
    #     분석용 html은 반환값을 직접 쓰고, 전체 DOM은 별도 파일로 저장하라
    #     (artifact_store.save_rendered_dom 사용 — 절단 없음).
    # [2] 전처리: _detect_429(html) → {"verdict":"RATE_LIMITED"} 즉시 반환(+record_rate_limited),
    #     classify_content_blocker → {"verdict":"BLOCKED"} 즉시 반환. 차단 페이지의 DOM에서
    #     selector를 제안하는 헛수고 방지.
    # [3] network API 발견: last_network_log에서
    #     content_type에 json 포함 & status 200 & 응답 body가 리스트/딕셔너리인 entry를 추려
    #     {"url": ..., "json_keys": 최상위 키 목록, "list_lengths": 리스트 필드 길이}로 요약.
    #     **본문 전문은 보고서에 넣지 않는다** (제약: 원문 장문 복사 금지).
    # [4] 기존 selector 검증: site spec의 selectors.list 각각에 대해
    #     soup.select(sel) 매칭 수 + 첫 매칭 텍스트(120자)를 기록 → "어느 selector가 왜 죽었나" 즉답.
    # [5] selector 후보 채굴 (핵심):
    def mine_selector_candidates(html: str, max_candidates: int) -> list[dict]:
        # BeautifulSoup(html, "lxml") 후:
        # (a) 반복 구조 탐지: 같은 (tag, class frozenset) 시그니처가 5회 이상 나타나고
        #     각 노드의 get_text(strip=True)가 3자 이상인 그룹을 수집.
        # (b) 각 그룹을 CSS selector 문자열로 직렬화: "tag.class1.class2"
        #     (class가 없으면 부모 1단계 포함 "parent > tag").
        # (c) 점수화: score = 매칭수 가중(5~30이 최적, 너무 많으면 nav/footer 노이즈)
        #     + 텍스트 평균 길이 가중 + a[href] 보유 비율 가중(목록형 소스에 유리)
        #     - 클래스명에 해시 패턴(`css-`, 6자 이상 무작위 영숫자) 포함 시 감점
        #       (styled-components — loword가 이 케이스, 재빌드에 깨짐).
        # (d) 상위 max_candidates개를 {"selector", "match_count", "sample_texts": [≤3건, 120자 절단],
        #     "has_links": bool, "stability": "stable|fragile"} 형태로 반환.
    # [6] 본문 추출 평가 (상세 페이지 탐색 시): extract_with_trafilatura → 실패 시
    #     extract_with_dom_heuristic. body 길이·제목 유무만 기록 (본문은 200자 절단 미리보기).
    # [7] 출력 2종:
    #     outputs/jsonl/structure_explorer_{site}_{ts}.jsonl (전체 기록)
    #     outputs/reports/structure_explorer_{site}_{ts}.md — 마지막 섹션에 **YAML 제안 패치**:
    #
    #     ## Proposed YAML patch (playwright_probe_sites.yaml)
    #     ```yaml
    #     <site_id>:
    #       selectors:
    #         list:
    #           - "<1순위 selector>"
    #           - "<2순위>"
    #         wait_for: "<1순위 selector>"
    #       wait_after_ms: <렌더 안정 관찰값>
    #     ```
    #     ## Hidden API candidates (있으면)
    #     - <URL> — keys: [...] (이 경로가 selector보다 안정적이면 Route 1 전환 검토)
```

### 3-3. 에이전트 사용 계약 (docstring에 그대로 명시하라)

```
탐색 루프 (selector 복구 표준 절차):
1. run_structure_explorer --site X            → live 1회, DOM·network·후보 확보
2. 보고서의 YAML 패치를 playwright_probe_sites.yaml에 적용 (사람/에이전트)
3. run_playwright_probe --site X              → items_found ≥ 기대치 검증
4. 실패 시 run_structure_explorer --offline-dom <1의 DOM 경로> --max-candidates 20
   으로 재채굴 (live 재호출 없이) → 2로
5. Hidden API가 발견되면 selector 대신 Route 1(API probe) 전환을 우선 검토
   — JSON API > CSS selector (안정성 서열).
```

## 4. 구현 시 함정

1. **gate 준수**: `--site` 모드에서 fetch 전에 `gate_check(site_id)`를 호출하고 skip 사유가 있으면 live 대신 최신 rendered_dom으로 offline 분석을 자동 수행 (google_trends 계열 보호).
2. **모듈 레벨 import** 유지 (기존 runner 규칙 — 테스트 monkeypatch 가능성).
3. `last_network_log`는 **await 직후 즉시 복사**해야 한다 (다음 open_page 호출이 덮어씀 — playwright_browser_tool.py:129 주석).
4. Windows 콘솔: `safe_print`(_audit_common) 재사용. 파일은 UTF-8.
5. network log의 JSON body에 토큰/키가 에코될 수 있다 — 보고서에 body를 싣지 않는 이유. URL의 query string도 `?key=` 패턴이 보이면 `***`로 마스킹하는 `_mask_url(url)` 헬퍼를 넣어라 (`re.sub(r"(key|token|apikey|api_key|serviceKey)=[^&]+", r"\1=***", url, flags=re.I)`).

## 5. 테스트 — `ingestion/tests/unit/test_structure_explorer.py` (전부 오프라인)

```python
# fixture: 반복 구조를 가진 합성 HTML
_FAKE_HTML = """
<html><head><title>t</title></head><body>
<nav><a href="/1">메뉴1</a><a href="/2">메뉴2</a></nav>
<ul class="rank-list">
""" + "".join(
    f'<li class="rank-item"><a href="/kw/{i}">실시간 키워드 {i}</a></li>' for i in range(10)
) + """
</ul></body></html>"""


def test_mine_candidates_finds_repeated_structure():
    from ingestion.runners.run_structure_explorer import mine_selector_candidates
    cands = mine_selector_candidates(_FAKE_HTML, max_candidates=5)
    assert cands, "반복 li.rank-item을 찾아야 한다"
    top = cands[0]
    assert top["match_count"] >= 8
    assert any("rank-item" in c["selector"] or "rank-list" in c["selector"] for c in cands)
    assert top["sample_texts"][0].startswith("실시간 키워드")


def test_styled_component_hash_classes_marked_fragile():
    from ingestion.runners.run_structure_explorer import mine_selector_candidates
    html = "<div>" + "".join(
        f'<span class="css-1a2b3c4">kw {i}</span>' for i in range(8)) + "</div>"
    cands = mine_selector_candidates(html, max_candidates=5)
    assert cands and cands[0]["stability"] == "fragile"


def test_offline_dom_mode_no_network(tmp_path, monkeypatch):
    # open_page가 호출되면 실패하도록 막고, --offline-dom 경로로 분석이 완료되는지
    dom = tmp_path / "page.html"
    dom.write_text(_FAKE_HTML, encoding="utf-8")
    from ingestion.runners import run_structure_explorer as rse

    async def _boom(*a, **k):
        raise AssertionError("offline 모드에서 네트워크 호출 금지")

    monkeypatch.setattr("ingestion.tools.playwright_browser_tool.open_page", _boom)
    report = rse.explore(site_id_or_url="signal_bz", query=None, region=None,
                         wait_ms=0, offline_dom=str(dom))
    assert report["candidates"]


def test_mask_url_hides_keys():
    from ingestion.runners.run_structure_explorer import _mask_url
    assert "***" in _mask_url("https://x.com/api?serviceKey=SECRET123&a=1")
    assert "SECRET123" not in _mask_url("https://x.com/api?serviceKey=SECRET123")
```

## 6. 종결 기준

- [ ] runner 신설 + 단위 테스트 4건 통과 + 전체 회귀 통과
- [ ] 실전 검증 1건: 07의 첫 대상(eu_press_corner 권장)에 대해 live 1회 → YAML 패치 제안이 생성됨 (증거: 보고서 경로)
- [ ] secret scan PASS (network log 마스킹 확인 포함)
- [ ] 체크리스트 #15 일부(구조 탐색 기법) 충족 기록

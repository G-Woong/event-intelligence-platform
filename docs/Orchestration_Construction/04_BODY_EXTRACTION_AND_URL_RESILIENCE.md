# 04 — 본문 추출 및 URL 복원력 설계 (Body Extraction & URL Resilience)

> **목적**: 주어진 URL에서 **본문 추출 실패를 최소화**하는 확장형 cascade를 설계한다. 동시에 **약관·저작권을 지키며**(우회 금지, full-text 무단 저장 금지) 실패해도 사건 후보 자체는 잃지 않게 한다.
> **현재 자산**: site_selector → trafilatura → readability → dom_heuristic cascade + Playwright 렌더 + url_resolver + feed_discovery가 이미 구현돼 있다. 이 문서는 이들을 **하나의 복원력 있는 상태머신**으로 묶는다.

---

## 0. 비개발자를 위한 설명

웹페이지에서 "기사 본문"만 깨끗하게 뽑아내는 일은 생각보다 어렵다. 페이지에는 광고·메뉴·댓글·추천기사 같은 군더더기(boilerplate)가 본문보다 훨씬 많다. 게다가:

- 어떤 사이트는 HTML만 받아도 본문이 들어 있다(쉬움).
- 어떤 사이트는 자바스크립트로 본문을 나중에 그린다 → 브라우저로 열어야 보인다(어려움).
- 어떤 사이트는 로그인/결제벽으로 막혀 있다 → **우리는 뚫지 않는다**(금지).
- 구글 뉴스 링크는 원본 기사 주소를 숨긴다 → 한 번 풀어야 한다(URL 해석).

그래서 우리는 **"쉬운 방법부터 차례로 시도하고, 막히면 다음 방법으로 넘어가는 사다리(cascade)"**를 만든다. 그리고 **끝까지 본문을 못 뽑아도, "이런 사건이 있었다"는 단서(제목·URL·시각)는 버리지 않는다.** 본문이 없다고 사건을 통째로 날리면 안 되기 때문이다.

---

## 1. BodyExtractionState (본문 추출 상태)

```python
# Proposed — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY: 신규 ingestion/orchestration/body_extraction_state.py
@dataclass
class BodyExtractionState:
    url: str
    canonical_url: str | None = None
    source_id: str = ""
    fetch_attempts: list[dict] = field(default_factory=list)   # [{strategy, status, error}]
    strategy_attempts: list[str] = field(default_factory=list)
    raw_html_path: str | None = None
    rendered_dom_path: str | None = None
    extracted_text_path: str | None = None
    metadata: dict = field(default_factory=dict)               # og:title, author, published_at, language
    body_length: int = 0
    boilerplate_ratio: float = 0.0
    language: str | None = None
    extraction_status: str = "pending"  # pending|success|partial|body_missing|blocked
    failure_category: str | None = None # ErrorType
    fallback_used: str | None = None
    legal_storage_policy: str = "preview_only"  # full|preview_only|signal_only
    next_action: str | None = None
```

이 상태는 추출 과정 전체를 추적하고, **artifact 경로**를 단계마다 남긴다(증거 보존). 실패해도 상태에 "왜·어디까지" 남으므로 디버깅·재시도가 쉽다.

---

## 2. BodyExtractionStrategy (추출 전략 사다리)

| 순서 | strategy | 매핑 함수 | 성공 기준 | 실패 시 |
|---|---|---|---|---|
| 1 | **existing_artifact_reuse** | `artifact_store` 조회 | 캐시 본문 존재 | 다음 |
| 2 | **direct_http** | `html_fetch_tool.fetch_html` | HTTP 200 + HTML | url_resolution/browser |
| 3 | **url_resolution** | `url_resolver.resolve` / `resolve_via_browser` | 원본 URL 확보 | direct 재시도 |
| 4 | **site_specific_selector** | `article_body_extractor`(body_selectors) | ≥50자 | trafilatura |
| 5 | **readability** | `readability_extractor.extract_with_readability` | ≥200자 | trafilatura |
| 6 | **trafilatura** | `trafilatura_extractor.extract_with_trafilatura` | ≥200자 | dom_heuristic |
| 7 | **dom_heuristic** | `dom_candidate_extractor.extract_with_dom_heuristic` | ≥200자 | rendered_dom |
| 8 | **rendered_dom / playwright_probe** | `CloudBrowserLikeStrategy().fetch` / `open_page` | 렌더 후 ≥200자 | snippet |
| 9 | **rss_summary / provider_snippet** | feed/검색 snippet | snippet 존재 | body_missing |
| 10 | **body_missing (candidate retained)** | — | 제목+URL+시각 보존 | needs_manual_rule |
| 11 | **manual_rule_needed / blocked_by_policy** | 리포트만 | — | (사람 개입) |

> **기존 cascade와의 관계**: `article_body_extractor.py`의 내부 cascade(site_selector → trafilatura → readability → dom_heuristic)는 4~7단계에 해당한다. 이 문서는 그 앞(1~3 캐시/URL해석)과 뒤(8~11 렌더/snippet/보존)를 **감싸는** 상위 사다리다.

---

## 3. 본문 추출 cascade (전체 흐름)

```
extract_body(url, source_id):
 ① 캐시 재사용     existing_artifact_reuse  → 있으면 즉시 반환 (네트워크 0, 비용 0)
 ② 직접 fetch      direct_http
 ③ URL 정규화      needs_browser_resolution(url)? → resolve_via_browser (Google News 등)
 ④ site parser     site_specific_selector (≥50자)
 ⑤ readability     (≥200자)
 ⑥ trafilatura     (≥200자)
 ⑦ dom heuristic   (≥200자)
 ⑧ rendered DOM    Playwright (JS 렌더 필요 시) — blocker 감지하면 즉시 중단
 ⑨ snippet fallback rss_summary / provider_snippet (본문 대신 요약)
 ⑩ body_missing    candidate는 보존 (제목/URL/시각) — 사건은 살린다
 ⑪ manual/blocked  needs_manual_rule 또는 BLOCKED_BY_POLICY (우회 안 함)
 각 단계: artifact 저장 + state.fetch_attempts 기록
```

**핵심 설계 결정**:
- **단계마다 artifact를 남긴다** → 나중에 같은 URL 재요청 시 ①에서 즉시 재사용(비용 절감 + 결정성).
- **blocker(CAPTCHA/login/paywall/robots) 감지 즉시 중단** → 절대 우회하지 않음(BLOCKED_TERMINAL).
- **body_missing ≠ 실패** → 사건 후보는 보존. body는 나중에 enrichment로 보강 가능.

---

## 4. URL 복원력 (resilience)

URL 단계의 실패도 본문 실패의 큰 원인이다. 대응:

| 문제 | 대응 함수 | 비고 |
|---|---|---|
| Google News 신형 URL(원본 숨김) | `url_resolver.resolve_via_browser` | `needs_browser_resolution`으로 사전 판별 |
| redirect 체인 | `url_resolver.resolve(max_hops=5)` | httpx 추적 |
| canonical 불일치 | `url_resolver.canonical_from_html` | og:url/rel=canonical |
| feed 없는 매체 | `feed_discovery.google_news_proxy_url` | RSS 프록시 |
| feed 발견 | `feed_discovery.discover_feeds` + `validate_feed` | 네트워크 최소 |

---

## 5. 본문 추출 실패를 줄이는 원칙 (요약)

1. **쉬운 것부터**: HTTP→파서→렌더 순. 비싼 Playwright는 마지막.
2. **캐시 우선**: 같은 URL은 다시 안 받는다.
3. **URL 먼저 푼다**: Google News 등은 원본 해석 후 추출.
4. **렌더는 필요할 때만**: `DYNAMIC_RENDER_REQUIRED`/`EXTRACTION_EMPTY`일 때만 browser.
5. **막히면 멈춘다**: blocker는 우회 없이 격리.
6. **본문 없어도 사건은 보존**: snippet/제목으로 candidate 유지.
7. **무한 재시도 금지**: 전략 소진 시 body_missing으로 종결.

### 언제 live browser를 쓰지 말아야 하나
- 쿨다운/격리 소스(health gate).
- blocker 감지된 소스(fmkorea/blind/reuters).
- numeric/API 소스(body 불필요).
- 이미 캐시 본문이 있는 URL.

### 언제 full-text 저장을 피해야 하나
- `legal_storage_policy != "full"`인 소스(nyt/guardian/newsapi = preview_only).
- 재배포 금지 약관 소스 → preview(요약 일부)만 공개, raw artifact는 internal_only.
- `publication_policy.yaml`의 `max_public_preview_chars` 준수.

---

## 6. google_trends_explore fallback chain (특수 사례 — 본문 아님이지만 복원력 동일 원리)

> **상태**: CONFIRMED_EXTERNAL_RATE_LIMIT (PASS 아님). 정품 429(robot.png), CAPTCHA 아님.

```
google_trends_explore 실패(429) 시 자동 fallback:
  A. google_trending_now (Playwright) — trend ≥3, 쿨다운 시 직전 artifact 재사용
  B. google_trends_trending_now_export — 공개 RSS trends.google.com/trending/rss?geo={region}
  C. 뉴스/검색 enrichment — serper/tavily/naver(+영문 exa/gnews/newsapi/guardian/ap_news)
     → extract_related_candidates 규칙 기반 related expansion
실측: collected fallback 5, aggregate related 19, body 1. 우회 0건.
```

이 chain은 **본문 cascade와 같은 철학**이다: 주 경로가 막히면 대체 경로로 "사건 맥락"을 확보하되, **우회는 하지 않는다**.

---

## 7. 저작권/약관 리스크 (legal storage)

| 정책 | 적용 | 근거 |
|---|---|---|
| full 저장 허용 | 공식·공개 데이터(공시/통계/공공) | tier1, 재배포 보통 허용 |
| preview_only | nyt, guardian, newsapi, 일반 뉴스 | 재배포 제한 약관 |
| signal_only | numeric, 트렌드 | body 자체가 없음 |
| internal_only(raw artifact) | 전체 | raw_html/dom은 비공개, 게시 계층 미연결 |

`publication_policy.yaml`: `allow_full_text_publication`, `max_public_preview_chars`, `attribution_required`, `source_url_required`, `raw_artifact_visibility: internal_only`. **수집 경로는 게시 경로와 분리**(INGESTION_FINAL §11).

---

## 8. Implementation diff blueprint

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY
diff --git a/ingestion/orchestration/body_extraction_state.py b/ingestion/orchestration/body_extraction_state.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/body_extraction_state.py
@@
+@dataclass
+class BodyExtractionState: ...   # §1

diff --git a/ingestion/orchestration/body_cascade.py b/ingestion/orchestration/body_cascade.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/body_cascade.py
@@
+def extract_body(url: str, source_id: str, profile, *, allow_browser=True) -> BodyExtractionState:
+    """§3 cascade를 오케스트레이션. 기존 extractor/resolver를 호출만 한다."""
+    # ① existing_artifact_reuse → ② direct_http → ③ url_resolution
+    # → ④~⑦ article_body_extractor (기존 cascade) → ⑧ rendered_dom
+    # → ⑨ snippet → ⑩ body_missing → ⑪ blocked/manual
+    ...
```

**수정하지 않는 파일**: `article_body_extractor.py`, `readability_extractor.py`, `trafilatura_extractor.py`, `dom_candidate_extractor.py`, `url_resolver.py`, `feed_discovery.py`, `playwright_browser_tool.py`. 모두 **호출만** 한다.

---

## 9. test plan

```
test_cascade_reuses_cached_artifact          # ① 캐시 히트 → 네트워크 0
test_cascade_resolves_google_news_url        # ③ resolve_via_browser 호출
test_cascade_site_selector_then_trafilatura  # ④→⑥ 폴백
test_cascade_renders_when_extraction_empty   # ⑦ 실패 → ⑧ browser
test_cascade_blocker_stops_immediately       # blocker → ⑪ (우회 안 함)
test_cascade_body_missing_retains_candidate  # ⑩ 사건 보존
test_cascade_preview_only_truncates          # legal preview_only 길이 제한
test_trends_fallback_chain_nonblocking       # §6 A→B→C, 우회 0
```

---

## 10. Agent Committee Review

| agent | 피드백 | status |
|---|---|---|
| source-ingestion-engineer | 기존 extractor를 감싸는 상위 cascade가 코드 무수정 원칙 충족 | CLOSED_BY_DESIGN |
| data-quality-auditor | body_missing 보존 + boilerplate_ratio 추적 → 품질 게이트(09)와 연결 | CLOSED_BY_TEST_PLAN |
| legal-safety-compliance-reviewer | preview_only/internal_only/우회 금지 명시 — 승인 | CLOSED_BY_DESIGN |
| adversarial-reality-critic | "body_missing≠실패" 설계가 사건 손실을 막음. 렌더 남용만 경계 | CLOSED_BY_DESIGN |
| operations-sre-agent | 캐시 우선 + 렌더 최소화로 비용·시간 절감 | CLOSED_BY_DESIGN |
| test-validation-agent | 8개 테스트가 cascade 분기 커버 | CLOSED_BY_TEST_PLAN |

---

## 11. Risk Closure

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| 본문 추출 실패율 높음 | 단일 전략 의존 | 빈 사건 카드 | body_length 측정 | 11단계 cascade + 캐시 | 추출 성공률 테스트 | CLOSED_BY_TEST_PLAN |
| Playwright 남용 | 매번 렌더 | 시간·CPU 폭발 | 렌더 호출 카운트 | 조건부 렌더(EXTRACTION_EMPTY 시만) | 렌더 호출 테스트 | CLOSED_BY_DESIGN |
| full-text 무단 저장 | preview 정책 미적용 | 저작권 위험 | publication_policy 검사 | preview_only/internal_only | preview 길이 테스트 | CLOSED_BY_DESIGN |
| paywall 우회 유혹 | 본문 욕심 | 약관 위반 | blocker 로그 | 즉시 BLOCKED_TERMINAL | grep "paywall bypass" 0 | BLOCKED_BY_POLICY |
| 사건 손실 | body 실패 시 후보 폐기 | 데이터 손실 | candidate 카운트 | body_missing 보존 | retain 테스트 | CLOSED_BY_DESIGN |

---

## 12. Commercialization Impact

- **본문 품질 = 카드 품질 = 체류시간**: 깨끗한 본문이 좋은 요약·사건 카드를 만든다. cascade가 본문 확보율을 높일수록 제품 가치 상승.
- **비용 절감**: 캐시 우선 + 렌더 최소화로 인프라 비용을 낮춘다(상용화 시 마진).
- **법적 안전 = 사업 지속성**: preview_only/우회 금지가 약관 분쟁을 사전 차단 → B2B 계약 시 리스크 항목 해소.
- **fallback chain = 가용성**: 주 소스가 막혀도 사건 맥락을 잃지 않아 "빈 화면"이 줄어든다(사용자 신뢰).

---

## 13. USER_CONFIRMATION_REQUIRED

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| body 최소 길이 기준(현재 200자)? | 품질 vs 수집량 | 뉴스 200자 유지, 커뮤니티 50자 | No |
| preview 공개 글자 수 상한? | 저작권 안전 | publication_policy.yaml 기본값 준수 | No |
| 렌더(Playwright) 일일 호출 상한? | CPU/시간 비용 | 소스당 cycle 1회 + on-demand | No |

---

## 14. Phase D 실제 구현 현황 (2026-06-14)

§1의 `BodyExtractionState`는 **`ingestion/orchestration/body_state.py`**로 구현됨(문서 제안 경로
`body_extraction_state.py` 대신 짧은 이름 채택). `assess_body_state(...)`가 §3 cascade 우선순위를
정규화한다. 실제 필드/상태:

| state | 조건 | body_missing |
|---|---|---|
| `present` | body_text ≥ 임계(뉴스 200 / 커뮤니티 50) | False |
| `partial` | 50 ≤ body_text < 임계 | False |
| `snippet_only` | body 부족 + summary 존재 (full body 아님) | **True** |
| `numeric_exempt` | numeric/trend 신호(본문 불요) | False |
| `missing` | body·summary 모두 없음 | True |
| `no_artifact` / `parser_error` / `malformed` | artifact 없음/파싱 실패/깨짐 | True |

상수: `FULL_BODY_MIN=200`, `COMMUNITY_FULL_MIN=50`, `PARTIAL_MIN=50`. **body_missing≠실패** 원칙 유지.
`canonical_url`은 **`canonical_url.py:canonicalize_url`**(no-network: scheme/host 소문자, tracking 제거,
fragment 제거, trailing slash 정책, query 정렬)로 구현. 네트워크 redirect 해석(`url_resolver`)은
`allow_network_resolution=True` + resolver 주입 시에만 호출(기본 off).

**Phase E로 넘기는 품질 항목**(data-quality 감사): ① body 기반 dedup 실행(현재는 canonical *키*만 생성,
collapse 미실행) ② boilerplate 비율 게이트(현재 길이만 측정) ③ source→purpose 매핑 강제(임계 오적용 방지)
④ `published_at` ISO-8601 정규화(GDELT/RSS/ISO 혼재) ⑤ evidence 역추적(다중 candidate 공유 artifact).

**알려진 한계**: HTML 페이지(zdnet_korea/etnews)의 기사-level 분해는 Phase D 범위 밖 → `artifact_parser`가
`html_unsupported` fallback으로 정직 처리(사건은 source-level로 보존). 본문 추출은 04 본문 cascade(기존
extractor) 책임.

## 15. Phase D-P Body Extraction 실측 분포 (2026-06-14)

실제 artifact 49소스에 `assess_body_state`를 적용한 production 분포(`production_audit.py`):

| state | 건수 | 비고 |
|---|---|---|
| present(≥임계) | **0** | RSS는 description→summary로 들어가 body_text 없음 → present 0 |
| partial | **0** | 본문 fetch 단계 부재(현재 RSS/JSON 키 한정) |
| snippet_only | 371 | 뉴스 다수(yna/ap_news 등) — summary만, body_missing=True |
| numeric_exempt | 3633 | market/trend(binance 3600 등) — 본문 불요, 정상 |
| missing | 101 | news 53/official 22/domain 23/search 3 |

**정직 결론**: body **추출 파이프라인은 아직 작동하지 않는다**(present=0). body_state classifier는 정확히 분류하나(snippet을 full로 위장하지 않음, market missing=0), 입력 본문이 없다. RSS/JSON은 헤드라인+요약만 제공하므로, 상용 event feed 본문은 **canonical_url(446/446 확보)을 fetch 대상으로 한 Phase E 본문 추출**(readability/trafilatura류)이 선행조건. **canonical_url no-network 정규화는 URL resolution(redirect/단축 복원)이 아님** — network_calls=0, 표기 정규화만. Google News/단축 URL 복원은 별도(url_resolver opt-in).

**알려진 한계 추가**: `normalize_published_at`는 date-only를 `00:00:00 UTC`로, 타임존 미표기를 UTC로 가정(precision_lost 가능). Unix epoch/`YYYY.MM.DD`/한글 날짜 미지원 → unrecognized(hold). 정밀화는 Phase E.

### Phase E-1 — body cascade 실측·보강 (2026-06-14)

`artifact_parser.py`에 본문 cascade 보강(stdlib, 신규 설치 0): RSS `content:encoded`/Atom `<content>` → `_strip_html`로 본문 회수, 중첩 컨테이너(`response.docs`/`hits.hits`)·`_source` 평탄화·`headline.main`·`pub_date` 매핑.

**실측(enabled 50소스, 네트워크 0)**: body `present=1`, `partial=0`, `snippet_only=376`, `body_missing=31795`, `numeric_exempt=3630`. 그룹별 news{present 1, snippet 363, missing 57} / official{missing 122} / domain{missing 31607(its 교통 데이터셋)} / market·trend{numeric_exempt 3630}.

**긍정편향 자가 교정(핵심)**: the_verge atom content 10건 중 9건이 "Read the full story at The Verge." **발췌**였다 — 길이≥200만으로 present 판정하던 결함을 `body_state._looks_truncated`(excerpt 마커 탐지)로 보강해 present→snippet_only 강등. 결과 present 10→1. **즉 실측 본문 추출 성공은 사실상 0**(남은 1건도 마커 없는 단일 항목). 뉴스 본문은 여전히 canonical_url 기반 **전체 기사 fetch(Phase E)**가 선행조건이다. content:encoded/atom 경로는 *피드가 전문을 실을 때만* 유효하며 the_verge처럼 대부분 발췌다.

### Phase E-2 — live 본문 fetch 실측 (2026-06-14, run 20260614T105328Z)

뉴스 본문을 **canonical_url에서 policy-safe 전체 기사 fetch**로 확보(E-1의 "present≈0"을 실제로 돌파). `full_source_revival.fetch_article_body`:
- 기존 자산 재사용(신규 설치 0): `html_fetch_tool`(httpx GET+timeout, 우회 없음) → `trafilatura`→`readability` 추출.
- **robots.txt 준수**(stdlib `urllib.robotparser`): disallow면 fetch 안 함(`ROBOTS_BLOCKED`). paywall/login/captcha/proxy 우회 0.
- **길이-only 금지**: excerpt 마커 탐지 + boilerplate 휴리스틱. snippet/excerpt는 present로 승격 안 함(SUCCESS만 promote).

**실측**: news 본문 fetch SUCCESS로 **ARTICLE_BODY_ALIVE 6** 확보 — bbc(4926자)/techcrunch(8380)/guardian(16213)/aljazeera(2386)/yna(336) 5건이 live 전체 본문(trafilatura, boilerplate=low, excerpt=False), the_verge 1건은 feed-level present. ap_news/hankyung/maekyung/cnbc/nyt는 fetch 실패/excerpt → `NEEDS_BODY_FETCH_UNRESOLVED`(root cause BODY_FETCH_FAILED/BODY_FETCH_REQUIRED).
**증거 보존(F2)**: 승격 본문은 `samples/<id>/body_fetch_evidence.txt`에 sha256+길이+head≤500자(gitignored, internal_only)로 남겨 ALIVE 판정 사후 검증 가능. 전문은 미커밋.
**소스 어댑터**: 0분해 회복용 `source_adapters.py`(source_id 스코프, 전역 인플레 회피) — opendart(`list`→공시 record), coinbase(`products`→단일 numeric), binance(`[ticker…]`→단일 numeric). artifact 다중 후보 중 **가장 많이 분해되는 것 선택**(`_select_best_artifact`, hacker_news raw=id리스트 vs extracted={items} 문제 해결).

> 다음 문서: `05_EVENT_QUEUE_AND_STORAGE_SCHEMA.md`.


## Phase E-3 — Body Fetch Strategy Ladder (run 20260614T114401Z)

`body_fetch_strategy.fetch_body_with_ladder`: robots_check → httpx → trafilatura → readability →
bs4(static <article>/<p>) → (policy-safe) browser render → body_state. 저장 raw_html을 직접 주입하면
재fetch 없이 추출(zdnet/etnews). 신규 설치 0(기존 httpx/trafilatura/readability/bs4/selenium 재사용).

긍정편향 차단(리뷰 흡수):
- **confident_full** = present + (length ≥ 600 또는 title content 토큰이 본문에 등장). present이지만
  짧고 title과 무관한 본문(예: cnbc Pro 프로모션 492자)은 SUCCESS로 둔갑하지 않고 EXCERPT_ONLY.
  title overlap은 불용어(from/than/news 등)를 제외해 우연 매칭을 막는다.
- **no bypass**: paywall/login/captcha 마커는 **구체 문구만**(footer의 일반 'subscribe'/'구독'/script의
  'recaptcha' 제외). 마커 감지 시 browser 렌더를 시도하지 않고 *_BLOCKED_NO_BYPASS로 닫는다.
  단 실제 full body를 서빙된 HTML에서 확보했으면(우회 아님) SUCCESS 인정.
- 실측: ap_news 3054 / zdnet 3251 / etnews 1244 / hankyung 3883 / maekyung 5943자(trafilatura 실본문,
  sha256 보존). nyt=HTTP_403(우회 없이 닫음), cnbc=EXCERPT_ONLY(Pro 프로모션, 본문 아님).

## Phase G — Force Production-Ready Source Closure

**판정: PARTIAL_WITH_HARD_BLOCKERS** (ALL_READY 아님).

본문/URL 관점의 정직성 갱신:
- **cnbc**: RSS article references를 통해 ARTICLE_PARTIAL_ALIVE로 승격했으나 **snippet_only preview**일 뿐 full body가 아니다. 법적으로 정확한 자세이며, full body로 둔갑시키지 않는다.
- **nyt**: 공식 Article Search API로 승격(과거 403은 웹스크래핑 시도였고, 공식 API는 정상 동작 — **우회가 아니다**). 단 preview_only / non_commercial / commercial_license_required 단서를 strategy memory evidence에 남긴다. min_interval 7200s(~12/day)로 무료 티어 500/day에 충분히 못 미친다.
- 동일한 preview-only 자세가 guardian/newsapi/aladin에도 적용(문서화).
- evidence URL에서 API key는 stripped(`vendor_api_routes.py`가 env에서만 key를 읽음).

본문 보강 ladder(`body_rescue_ladder.py`)는 현재 RSS snippet 단계까지이며, full body 통합은 STILL OPEN으로 남긴다. assess_body_state=="present"인 것만 body로 계수하고 snippet_only는 body로 계수하지 않는다.

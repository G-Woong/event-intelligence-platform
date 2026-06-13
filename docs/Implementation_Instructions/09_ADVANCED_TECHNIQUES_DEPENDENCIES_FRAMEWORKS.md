# 09. 상용 수집 기법 흡수 — 의존성 점검 + 고급 기법 카탈로그(12종) + 프레임워크/MCP 적용

> §1(의존성)은 **06/07보다 먼저** 실행. 나머지는 병행 가능. 산출물: `ingestion/tools/check_dependency_readiness.py` + 기법별 적용 diff/테스트 설계 + 프레임워크 결정 기록.

## §1. 의존성 준비 상태 점검 (선행 필수)

### 1-1. 현재 설치 상태 (requirements.txt 확정 사실)

playwright 1.48.0, selenium 4.26.1, trafilatura 1.12.2, readability-lxml 0.8.1, beautifulsoup4, lxml, feedparser 6.0.11, httpx, langgraph 0.2.76, langchain 0.2.11, tenacity 8.5.0 — **본 라운드에 필요한 라이브러리는 전부 이미 설치되어 있다. 신규 pip 설치는 기본적으로 불필요하다.** 단 라이브러리 설치와 별개로 **playwright 브라우저 바이너리**와 **selenium 드라이버**는 별도 준비물이다.

### 1-2. 신규 도구 — `ingestion/tools/check_dependency_readiness.py`

기법들이 의존하는 런타임 자원을 한 번에 점검하는 도구. 에이전트는 탐색/수집 작업 시작 전 항상 이것부터 돌린다.

```python
"""수집 파이프라인 런타임 의존성 점검. 키 값 미출력 (NAME/존재만).
종료 코드: 전부 READY=0, 하나라도 MISSING=1."""
# 점검 항목과 방법:
# [1] import 가능성: playwright, selenium, trafilatura, readability(lxml_html_clean 포함),
#     bs4, lxml, feedparser, yaml, httpx, langgraph — importlib.import_module, 실패 시 MISSING
# [2] playwright chromium 바이너리: sync_playwright().chromium.launch(headless=True) 시도
#     후 즉시 close. Exception 문구에 "Executable doesn't exist" 포함 시
#     FIX="python -m playwright install chromium" 안내. (타임아웃 15s)
# [3] selenium: 기존 ingestion/fetch_strategies/selenium_strategy.py의
#     selenium_env_status() 재사용 — {"ready": bool} 그대로 보고 (새로 만들지 마라)
# [4] 상태 파일 쓰기 권한: outputs/state/ 에 tmp 파일 write→delete
# [5] (정보성) INGESTION_RATE_LIMIT_BACKEND 현재 값, rate_limit_cache.json 존재 여부
# 출력: 표 (component / status READY|MISSING|DEGRADED / fix 명령) + exit code
```
검증: `.\.venv\Scripts\python.exe -m ingestion.tools.check_dependency_readiness` → 전 항목 READY. chromium MISSING이면 안내된 설치 명령 실행 후 재점검 (이 설치는 파괴적 명령이 아니므로 즉시 수행 가능). 단위 테스트: import 점검 함수에 가짜 모듈명 → MISSING 반환.

## §2. 고급 기법 카탈로그 — 12종 (각: 개념 → 적용 지점 → 구현 → 테스트 설계)

> 원칙: **안정성 서열 — 공식 API > RSS/sitemap > 숨은 JSON(XHR) > CSS selector > 본문 휴리스틱.** 항상 서열 상위 경로로 승격할 기회를 찾는 것이 상용 운영의 핵심이다. 아래 1~5는 이번 라운드에 즉시 구현, 6~12는 구현 또는 설계 고정(명시) 대상이다.

**기법 1 — 숨은 API 스니핑 (network capture)**: 렌더링 중 XHR/fetch 응답을 관찰해 페이지가 쓰는 내부 JSON endpoint를 발견, selector 의존을 제거한다. 적용: 06 explorer [3]단계 (loword/eu_press_corner/trending_now가 1차 고객). 구현: `open_page(capture_network=True)` + `last_network_log` (이미 존재). 테스트: explorer 단위 테스트(06 §5) + URL 마스킹 테스트. **준법 경계**: 관찰만 한다 — 인증 토큰 재사용/리플레이 금지, 로그인 세션 필요 endpoint는 BLOCKED 처리.

**기법 2 — RSS/Atom 자동 발견(autodiscovery)**: HTML `<head>`의 `<link rel="alternate" type="application/rss+xml" href=...>`를 파싱해 그 사이트의 공식 feed를 찾는다. 적용: ap_news(03), 향후 신규 뉴스 소스 온보딩 표준 1단계. 구현: `ingestion/tools/feed_discovery.py` 신설 — `discover_feeds(html, base_url) -> list[str]` (BeautifulSoup, `link[rel=alternate]` + 휴리스틱 후보 `/rss`, `/feed`, `/index.rss` 경로) + `validate_feed(url)` (httpx GET → `feedparser.parse` → `bozo==0 and entries>0`). 테스트: link 태그 fixture에서 발견 / bozo feed 거부.

**기법 3 — Google News RSS 프록시**: 자체 feed가 없는 매체를 `news.google.com/rss/search?q=site:<domain>` 으로 우회 구독. 적용: 03의 ap_news 후보 2, 차단/feed 부재 매체 전반의 표준 폴백. 구현: feed_discovery에 `google_news_proxy_url(domain, lang="en-US", country="US")` 헬퍼. 주의: link가 redirect URL — 정규화 시 원 URL 해석 필요(기법 4), evidence_level 1단계 하향. 테스트: URL 생성 규칙 단언.

**기법 4 — redirect/원본 URL 해석기**: 프록시·단축 URL을 `httpx.head(follow_redirects=True)`로 풀어 canonical URL을 얻는다 (중복 제거 정확도와 직결). 구현: `ingestion/tools/url_resolver.py` — `resolve(url, max_hops=5) -> str`, 실패 시 원본 반환, 동일 도메인 캐시 dict. 테스트: monkeypatch transport로 3-hop 시나리오.

**기법 5 — 본문 추출 캐스케이드**: trafilatura→readability→DOM 휴리스틱 3단 폴백 (07 §4에서 구현 완료). 적용: 모든 click-through/상세 페이지. 테스트: 07 §7.

**기법 6 — sitemap/news-sitemap 발견**: `robots.txt`의 `Sitemap:` 줄과 `/sitemap.xml`, `/news-sitemap.xml`을 조회해 기사 URL+lastmod를 수집 (RSS보다 깊은 백필). 적용: RSS 없는 공식 기관 사이트(eu_press_corner 폴백). 구현 설계: `feed_discovery.discover_sitemaps(base_url)` — lastmod 최근 N건만. 테스트: sitemap fixture 파싱. (이번 라운드: eu_press_corner가 기법 1로 해결되면 설계만 고정.)

**기법 7 — Conditional GET (ETag/Last-Modified)**: 주기 폴링 시 `If-None-Match`/`If-Modified-Since` 헤더로 304를 받아 대역폭·차단 위험을 줄인다. 적용: RSS 11종의 운영 주기 수집(plans/012 전 설계 고정). 구현 설계: rate_limit_store에 `etag:{source_id}` 키 추가 저장 — fetch 직전 조회, 응답에서 갱신. 304는 LIVE_SUCCESS(변경 없음, artifacts_new=0)로 분류. 테스트: fake 304 응답 분기.

**기법 8 — selector self-healing 루프**: EXTRACTION_EMPTY/매칭 0이 cycle N회 연속이면 explorer를 offline-dom 모드로 자동 재실행해 후보 selector를 제안, YAML patch 파일을 생성해 사람이/에이전트가 승인-적용한다. 적용: 06 explorer + health store 조합. 구현 설계: `source_health`에 `extraction_empty_streak` 추가는 **하지 않고**(스키마 변경 최소화) audit jsonl 누적에서 streak를 계산하는 점검 스크립트로 시작. 테스트: streak 계산 함수 단위 테스트.

**기법 9 — 전략 사다리 명시 운용**: httpx_direct → (EXTRACTION_EMPTY 시) playwright_basic → scroll → wait_network_idle → click_more → (전부 실패+드라이버 준비 시) selenium_rendered_dom. **이미 구현되어 있다** (`strategy_selection.select_next_strategy` + `STRATEGY_SEQUENCE`). 이번 라운드 일: ① source_spec에 `preferred_browser: selenium` 메타가 동작함을 문서화 ② 에이전트 지침 — "playwright가 빈 DOM을 주면 selenium 교차 검증 1회"를 07 STEP B의 표준 실험으로 추가 (`run_selenium_smoke.py` 활용). 테스트: 기존 test 스위트가 커버 — 추가 없음.

**기법 10 — soft-block/429 텍스트 분류 공유화**: `_RATE_LIMITED_SIGNALS`(playwright_probe)와 02 §3-(b)의 텍스트 분류가 두 벌이 되지 않게, 시그널 목록을 `error_taxonomy.py`로 승격해 양쪽이 import. 구현: 목록 이동 + 양쪽 import 교체 (동작 무변경). 테스트: 기존 테스트 통과 + import 위치 단언.

**기법 11 — LLM judge 추출 품질 게이트**: 추출된 본문/keyword가 "실데이터인가, 메뉴/광고 노이즈인가"를 LLM이 판정 (기존 `ingestion/agents/llm_judge.py` 재사용). 적용: 커뮤니티 본문(노이즈 감수 정책)의 하류 필터 — 수집은 다 하되 이벤트 큐 투입 전 judge 점수를 메타로 부착. 구현 설계: judge 입력은 절단본(500자), OPENAI_API_KEY 부재 시 `judge_score=UNKNOWN`으로 무해 통과. 테스트: 키 없는 환경에서 UNKNOWN 경로.

**기법 12 — DOM 구조 지문(fingerprint) 변경 감지**: rendered DOM의 (tag,class) 시그니처 멀티셋을 해시해 저장, 다음 수집 때 유사도가 급락하면 "사이트 개편" 경보 → 기법 8 트리거. 구현 설계: explorer [5]의 시그니처 수집을 재사용해 `structure_fingerprint` 필드로 jsonl에 기록 (비교 로직은 후속). 테스트: 동일 DOM → 동일 지문, 구조 변경 → 다른 지문.

### 적용 우선순위 매트릭스

| 즉시 구현 (이번 턴) | 설계 고정 + 부분 구현 | 후속 라운드 |
|---|---|---|
| 1, 2, 3, 4, 5, 10 | 6, 8, 12 (explorer에 토대) | 7 (plans/012 주기 수집과 함께), 11 (이벤트 큐 투입 시) |

## §3. 프레임워크/오케스트레이션 — 결정과 근거

**결정: 이번 라운드는 신규 프레임워크를 설치하지 않는다. LangGraph(이미 0.2.76 설치)로 탐색-수집-확장-검증 그래프를 구성한다.** 근거: ① "deep agents"류 프레임워크의 핵심(계획자-실행자 분리, 도구 루프, 상태 영속)은 LangGraph 노드+체크포인터로 동일하게 구현된다 ② 의존성 추가는 Windows/py3.11 고정 환경에서 회귀 표면을 넓힌다 ③ 본 repo에 이미 `ingestion/agents/graph.py`/`state.py` 골격이 있다.

**LangGraph 수집 에이전트 그래프 설계 (구현 명세 — `ingestion/agents/collection_graph.py` 신설은 본 라운드 선택 사항, 설계는 고정):**
```
state: {source_id, query, attempt_log[], verdict, artifacts[]}
nodes:
  gate        → gate_check; skip이면 END(verdict=skipped)
  probe       → run_collection_probe (Route 1/2/3 — 기존 라우팅 그대로 도구화)
  diagnose    → status≠SUCCESS 시 raw artifact 검안 + 가설 생성 (LLM 노드)
  explore     → run_structure_explorer (offline 우선)
  patch       → YAML/spec 패치 제안 생성 (적용은 human-in-the-loop interrupt)
  verify      → 재probe + 종결 기준 판정
edges: gate→probe→(성공)verify / (실패)diagnose→explore→patch→[interrupt]→verify→(미달 & iter<4)diagnose
```
이것은 00 §3의 종결 루프를 그래프로 코드화한 것이다 — 사람이 돌리던 루프와 에이전트가 돌리는 루프가 같은 구조를 갖는다.

**MCP**: Claude Code 세션에서 Playwright MCP/fetch MCP를 붙이면 에이전트가 브라우저 탐색을 대화 도구로 수행할 수 있으나, **본 파이프라인의 재현 가능성은 repo 내 runner가 보장해야 하므로** MCP는 "개발 중 보조 탐색"으로만 위치시킨다 (수집 경로가 MCP에 의존하면 headless/cron 운영에서 깨진다). `.claude/settings.json`에 MCP를 추가할 경우 별도 사용자 승인 후 진행 — 이 라운드 범위 외, 기록만 남긴다.

**deepagents 등 신규 패키지를 굳이 도입할 경우의 절차 (옵션)**: ① `uv pip install --dry-run`으로 의존 충돌 확인(특히 langchain-core 0.2.43 핀과의 호환) ② requirements.txt에 핀 버전 추가 ③ import smoke 테스트 ④ 기존 509+ 테스트 무영향 확인. 충돌 시 도입 포기하고 LangGraph 경로 유지 — **충돌을 풀기 위한 기존 핀 변경 금지**.

## §4. 이번 턴 구현 체크 (체크리스트 #15)

- [ ] `check_dependency_readiness` 신설 + 전 항목 READY (증거: 실행 출력)
- [ ] `feed_discovery.py` (기법 2·3) + `url_resolver.py` (기법 4) + 테스트
- [ ] 기법 10 공유화 diff + 회귀 통과
- [ ] 기법 6·8·12 설계가 06 explorer 산출물에 반영됨 (지문 필드, offline 재채굴)
- [ ] §3 결정(LangGraph 채택, MCP 보조 위치, 신규 패키지 보류)을 docs/72에 1섹션으로 등재

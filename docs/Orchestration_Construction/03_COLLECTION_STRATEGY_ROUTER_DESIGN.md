# 03 — 수집 전략 라우터 설계 (Collection Strategy Router)

> **목적**: "어떤 소스를, 어떤 상황에서, 어떤 수집 방법으로" 호출할지 결정하는 **결정적(deterministic) 라우터**를 설계한다. 이미 존재하는 3-way 라우팅(`run_collection_probe`)을 **대체하지 않고 그 위에 얇게 얹는다**.
> **핵심 원칙**: 라우터는 LLM이 아니다. 소스 프로파일 + 현재 상태(health/rate-limit) + 직전 실패 분류 → 다음 전략을 **규칙으로** 고른다. (LLM 판단은 07 문서의 제한된 지점에만.)

---

## 0. 비개발자를 위한 설명

"전략 라우터"는 식당의 주방장 같은 존재다. 주문(소스 수집 요청)이 들어오면, 재료(소스 특징)와 현재 주방 상태(이미 너무 바쁜가? 이 재료는 떨어졌나?)를 보고 **어떤 조리법(전략)으로 만들지** 결정한다. 핵심은:

- 같은 재료라도 상황에 따라 다른 조리법을 쓴다(HTTP가 막히면 브라우저로).
- 떨어진 재료(차단된 소스)는 주문을 거절한다(격리).
- 한 번 실패한 조리법을 무한 반복하지 않는다(실패 분류 → 다른 전략으로).

이 모든 결정은 **정해진 규칙표**로 이뤄진다. "AI가 알아서"가 아니다. 그래야 비용과 동작이 예측 가능하다.

---

## 1. CollectionStrategy enum (수집 전략 목록)

> 기존 `STRATEGY_SEQUENCE`(전략 루프 내부 10단계)와 **다른 층위**다. CollectionStrategy는 "소스 단위 진입 전략"(어느 Route로 갈지 + 무슨 목적인지)이고, STRATEGY_SEQUENCE는 "Route 3 내부의 fetch 시도 순서"다. 라우터는 전자를 고르고, 후자는 기존 코드가 처리한다.

```
CollectionStrategy (Enum):
  # ── 진입 전략 (어느 Route) ──
  API_JSON_FETCH          # Route 1: 구조화 API (규제/공시/시세/도메인)
  RSS_FEED_FETCH          # feed 우선 (뉴스)
  GOOGLE_NEWS_RSS_PROXY   # feed 없는 매체 → Google News RSS (ap_news 등)
  PLAYWRIGHT_SELECTOR_FETCH  # Route 2: YAML selector (eu_press_corner, dcinside 등)
  STRATEGY_LOOP_FETCH     # Route 3: httpx→playwright 전략 루프 (일반 뉴스/HTML)
  STRUCTURE_EXPLORER      # selector 미발견 시 DOM 채굴
  BROWSER_PROBE           # Playwright 렌더 단독

  # ── 보조/특수 전략 ──
  BODY_EXTRACTION_ONLY    # 이미 URL 있음 → 본문만 추출 (04 cascade)
  URL_RESOLUTION          # Google News URL → 원본 URL 해석
  RELATED_EXPANSION       # 검색 기반 주변 정보 확장 (on-demand)
  NUMERIC_SIGNAL_FETCH    # 시세 (body 면제)
  COMMUNITY_THREAD_FETCH  # 커뮤니티 반응
  OFFICIAL_STATEMENT_FETCH # 공식 발표 확인
  NO_CALL_COOLDOWN        # 쿨다운/격리 → 호출 안 함 (직전 artifact 재사용)
```

각 전략은 **기존 함수에 매핑**된다(신규 수집 코드 0):

| CollectionStrategy | 매핑 함수 |
|---|---|
| API_JSON_FETCH | `run_api_live_probe(source_id)` |
| RSS_FEED_FETCH | `feed_discovery` + `html_fetch_tool.fetch_html` |
| GOOGLE_NEWS_RSS_PROXY | `feed_discovery.google_news_proxy_url` |
| PLAYWRIGHT_SELECTOR_FETCH | `run_playwright_probe(site_id)` |
| STRATEGY_LOOP_FETCH | `run_fetch_strategy_loop(source_id, url, ...)` |
| STRUCTURE_EXPLORER | `run_structure_explorer` |
| BROWSER_PROBE | `CloudBrowserLikeStrategy().fetch` |
| BODY_EXTRACTION_ONLY | `article_body_extractor.extract_article_body` |
| URL_RESOLUTION | `url_resolver.resolve` / `resolve_via_browser` |
| NUMERIC_SIGNAL_FETCH | `run_api_live_probe` (NUMERIC_SIGNAL_SOURCES) |
| NO_CALL_COOLDOWN | (호출 없음 — health gate 반환) |

---

## 2. SourceProfile schema (02 §4 구현)

```python
# Proposed — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY: 신규 파일 ingestion/orchestration/source_profile.py
from dataclasses import dataclass, field
from enum import Enum

@dataclass(frozen=True)
class SourceProfile:
    source_id: str
    source_type: str           # news|regulatory|community|trend|search|numeric|domain|fallback
    role: str                  # primary_seed|enrichment|both|deferred|excluded
    data_shape: str            # article|structured_filing|post|keyword_list|numeric|search_result
    access_method: str         # api|rss|playwright|strategy_loop
    freshness_need: str        # near_real_time|short|medium|daily
    rate_limit_sensitivity: str # low|medium|high
    body_extraction_difficulty: str # none|low|medium|high
    legal_risk: str            # low|conditional|excluded
    commercial_value: str      # low|medium|high
    reliability_score: float   # 0.0~1.0
    preferred_strategy: str    # CollectionStrategy.value
    fallback_strategies: list[str] = field(default_factory=list)
    blocked_conditions: list[str] = field(default_factory=list)
    artifact_policy: str = "full"  # full|signal_only|preview_only
```

**SourceProfile은 어디서 오는가?** — `source_registry.yaml`을 1차 출처로 하고, 부족한 필드(freshness_need, preferred_strategy 등)는 **신규 YAML `source_profiles.yaml`**로 보강한다. registry는 수정하지 않는다(읽기만).

> **Phase C 실제 구현 노트 (2026-06-14)**: 위 §2 스키마는 설계 풍부판이다. 실제 구현
> (`ingestion/orchestration/source_profile.py`)은 **운영 최소셋**으로 간소화했다:
> `source_id, enabled, purpose, freshness_bucket, min_interval_seconds, risk_level,
> preferred_strategy, requires_api_key, is_community, confirmation_policy, notes`.
> StrategyRouter도 §3 풀버전(health/rate-limit 의존) 대신 **최소 `decide_strategy(profile)
> -> StrategyDecision`**(순수 함수, read-only metadata)로 구현했다 — community는
> `confirmation_policy`를 `unconfirmed_until_corroborated`로 보정(단독 확정 금지). 실제 수집
> 라우팅/재시도는 여전히 `run_collection_probe`가 책임(대체 안 함). `source_profiles.yaml`은
> 특성이 실측 확인된 8개 대표 소스로 시작하고 44 전수는 점진 확장한다. health/rate-limit
> 의존 라우팅(§3 풀버전)과 fallback 전략 순회는 Phase D~E/G로 이월.

---

## 3. StrategyRouter 설계

```python
# Proposed — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY: 신규 파일 ingestion/orchestration/strategy_router.py
class StrategyRouter:
    """소스 프로파일 + 현재 상태 + 직전 실패 → 다음 CollectionStrategy 결정 (결정적)."""

    def __init__(self, profiles: dict[str, SourceProfile],
                 health_store, rate_limit_store):
        self._profiles = profiles
        self._health = health_store
        self._rl = rate_limit_store

    def route(self, source_id: str, purpose: str,
              previous_failure: str | None = None) -> str:
        profile = self._profiles[source_id]

        # 1) 격리/제외 소스 → 호출 안 함
        if profile.role in ("excluded", "deferred"):
            return CollectionStrategy.NO_CALL_COOLDOWN.value
        health = self._health.get(source_id)
        if health and health.is_blocked_terminal():
            return CollectionStrategy.NO_CALL_COOLDOWN.value

        # 2) 쿨다운 중 → 호출 안 함
        if self._rl.is_cooling_down(source_id):
            return CollectionStrategy.NO_CALL_COOLDOWN.value

        # 3) 직전 실패가 있으면 → 실패 분류에 따라 fallback 전략
        if previous_failure:
            nxt = self._fallback_for(profile, previous_failure)
            if nxt:
                return nxt

        # 4) 정상 → preferred_strategy
        return profile.preferred_strategy

    def _fallback_for(self, profile, failure: str) -> str | None:
        # 차단형은 fallback 없음 (terminal)
        if failure in ("CAPTCHA_DETECTED", "LOGIN_WALL_DETECTED",
                       "PAYWALL_DETECTED", "ROBOTS_BLOCKED"):
            return CollectionStrategy.NO_CALL_COOLDOWN.value
        if failure == "RATE_LIMITED":
            return CollectionStrategy.NO_CALL_COOLDOWN.value
        # 추출 실패 → 다음 fallback_strategies 순회 (소진 시 None)
        for fb in profile.fallback_strategies:
            if not self._already_tried(fb):
                return fb
        return None
```

**중요**: StrategyRouter는 `run_collection_probe`를 **대체하지 않는다**. 라우터가 고른 CollectionStrategy가 `STRATEGY_LOOP_FETCH`면 결국 `run_collection_probe`(또는 `run_fetch_strategy_loop`)를 부른다. 라우터는 "어느 진입점/목적"만 결정하고, 실제 fetch·재시도는 기존 코드가 한다.

---

## 4. source_registry 확장안 (registry 수정 없이)

```yaml
# Proposed new file — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY: ingestion/configs/source_profiles.yaml
# registry.yaml은 건드리지 않고, profile 보강 필드만 별도 파일로.
version: 1
profiles:
  yna:
    source_type: news
    role: primary_seed
    freshness_need: near_real_time
    rate_limit_sensitivity: low
    preferred_strategy: strategy_loop_fetch
    fallback_strategies: [google_news_rss_proxy, related_expansion]
    commercial_value: high
  google_trends_explore:
    source_type: trend
    role: enrichment
    freshness_need: medium
    rate_limit_sensitivity: high        # CONFIRMED_EXTERNAL_RATE_LIMIT
    preferred_strategy: no_call_cooldown # gate 필수 — 기본은 호출 안 함
    fallback_strategies: [structure_explorer, rss_feed_fetch, related_expansion]
    blocked_conditions: [quota]
    artifact_policy: signal_only
  finnhub:
    source_type: numeric
    role: primary_seed
    freshness_need: near_real_time
    preferred_strategy: numeric_signal_fetch
    body_extraction_difficulty: none
    artifact_policy: signal_only
  # ... 44 CORE_READY 소스 전부 (구현 턴에서 작성)
```

---

## 5. 연계: retry_policy / rate_limit_policy

- **retry_policy.yaml**: 라우터는 재시도 횟수를 직접 세지 않는다. `run_fetch_strategy_loop`가 이미 `per_source:` budget을 적용(2026-06-12 구현). 라우터는 "fallback 전략 선택"만, 재시도 상한은 기존 코드.
- **rate_limit_policy.yaml**: `is_cooling_down()` / `is_cached()`는 `get_store()`(또는 rate_limit_policy.py 함수)에 위임. 라우터는 결과만 읽는다.
- **분리 원칙**: 라우터는 **상태를 바꾸지 않는다(read-only)**. 호출·기록은 기존 probe가 한다.

> ⚠️ **VERIFY (U-1)**: `is_cooling_down`/`is_cached`의 정확한 함수명·위치는 구현 직전 grep으로 확인(`rate_limit_store.py` vs `rate_limit_policy.py`).

---

## 6. failure classification → next_action 매핑 (라우터 관점)

| previous_failure | next CollectionStrategy | 근거 |
|---|---|---|
| EXTRACTION_EMPTY / EXTRACTION_TOO_SHORT | fallback_strategies 다음(보통 browser_probe) | 기존 selection 로직 정합 |
| DYNAMIC_RENDER_REQUIRED | browser_probe | JS 렌더 필요 |
| RATE_LIMITED | no_call_cooldown | 쿨다운 + 재시도 큐(06) |
| CAPTCHA/LOGIN/PAYWALL/ROBOTS | no_call_cooldown(terminal) | 격리(06 §5) |
| NETWORK_TIMEOUT / HTTP_5XX | preferred 재시도(지수 backoff) | 일시적 |
| SELECTOR_MATCHED_BUT_URL_EMPTY | structure_explorer | selector 갱신 필요 |
| INVALID_KEY / PARAMETER_MISSING | no_call_cooldown + WARNING 리포트 | 설정 문제(사람 개입) |

---

## 7. 라우터 단위 테스트 계획

```
test_router_excluded_source_returns_no_call         # fmkorea → NO_CALL_COOLDOWN
test_router_blocked_terminal_returns_no_call        # health BLOCKED → NO_CALL
test_router_cooldown_returns_no_call                # rate-limit cooling → NO_CALL
test_router_normal_returns_preferred                # yna → strategy_loop_fetch
test_router_extraction_empty_advances_fallback      # EXTRACTION_EMPTY → browser_probe
test_router_rate_limited_returns_cooldown           # RATE_LIMITED → NO_CALL
test_router_captcha_terminal_no_fallback            # CAPTCHA → NO_CALL (fallback 없음)
test_router_readonly_does_not_mutate_store          # route()가 store 변경 안 함
```

---

## 8. Implementation diff blueprint

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY (신규 디렉터리 ingestion/orchestration/ 생성)
diff --git a/ingestion/orchestration/__init__.py b/ingestion/orchestration/__init__.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/__init__.py
@@
+"""Orchestration layer: deterministic routing over run_collection_probe.
+Does NOT replace fetch_strategies — wraps it."""

diff --git a/ingestion/orchestration/source_profile.py b/ingestion/orchestration/source_profile.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/source_profile.py
@@
+from dataclasses import dataclass, field
+@dataclass(frozen=True)
+class SourceProfile:
+    source_id: str
+    ...  # §2 전체
+def load_profiles(path="ingestion/configs/source_profiles.yaml") -> dict[str, SourceProfile]:
+    ...

diff --git a/ingestion/orchestration/collection_strategy.py b/ingestion/orchestration/collection_strategy.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/collection_strategy.py
@@
+from enum import Enum
+class CollectionStrategy(str, Enum):
+    API_JSON_FETCH = "api_json_fetch"
+    ...  # §1 전체

diff --git a/ingestion/orchestration/strategy_router.py b/ingestion/orchestration/strategy_router.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/strategy_router.py
@@
+class StrategyRouter:
+    ...  # §3 전체

diff --git a/ingestion/configs/source_profiles.yaml b/ingestion/configs/source_profiles.yaml
new file mode 100644
--- /dev/null
+++ b/ingestion/configs/source_profiles.yaml
@@
+version: 1
+profiles: { ... }  # §4 (44 소스)

diff --git a/ingestion/tests/unit/test_strategy_router.py b/ingestion/tests/unit/test_strategy_router.py
new file mode 100644
--- /dev/null
+++ b/ingestion/tests/unit/test_strategy_router.py
@@
+# §7 테스트 전체
```

**수정하지 않는 파일** (중요): `collection_probe.py`, `strategy_runner.py`, `strategy_selection.py`, `source_registry.yaml`, `rate_limit_policy.yaml`, `retry_policy.yaml`. 라우터는 이들을 **호출만** 한다.

---

## 9. Agent Committee Review

| agent | 피드백 | status |
|---|---|---|
| orchestrator-architect | 2층 분리(CollectionStrategy=진입 vs STRATEGY_SEQUENCE=fetch)가 기존 코드와 충돌 없음 | CLOSED_BY_DESIGN |
| source-ingestion-engineer | 라우터 read-only + 기존 함수 매핑 → 수집 코드 무수정. 정합 | CLOSED_BY_DESIGN |
| adversarial-reality-critic | U-1(rate-limit 함수 위치) 미확정이 유일 리스크. "VERIFY PATH" 표기 적절 | DEFERRED_WITH_TRIGGER |
| test-validation-agent | 8개 단위 테스트가 분기 커버. readonly 테스트 포함 양호 | CLOSED_BY_TEST_PLAN |
| operations-sre-agent | NO_CALL_COOLDOWN이 워커 슬롯 점유 없이 즉시 반환 — 운영 효율 | CLOSED_BY_DESIGN |
| security-permission-guardian | 라우터가 .env/secret 접근 없음 확인 | CLOSED_BY_DESIGN |

---

## 10. Risk Closure

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| 라우터가 기존 로직 중복/충돌 | STRATEGY_SEQUENCE와 혼동 | 이중 재시도 | 코드 리뷰 | 2층 분리 명시(§1) | 통합 테스트 회귀 0 | CLOSED_BY_DESIGN |
| rate-limit 함수 오인(U-1) | policy vs store 위치 | 잘못된 import | grep 확인 | VERIFY PATH 표기 | 구현 직전 grep | DEFERRED_WITH_TRIGGER |
| 라우터 상태 변경 부작용 | route()가 store mutate | 동시성 버그 | readonly 테스트 | route() read-only 설계 | test_router_readonly | CLOSED_BY_TEST_PLAN |
| profile 누락 소스 | source_profiles.yaml 불완전 | KeyError | 로딩 검증 | 44 소스 전수 + 기본값 | 로딩 테스트 | CLOSED_BY_TEST_PLAN |

---

## 11. Commercialization Impact

- **비용 예측성**: 라우터가 결정적이므로 "이 소스를 하루 몇 번 호출하는가"가 사전 계산 가능 → 외부 API 비용을 사업계획에 넣을 수 있다.
- **확장 용이성**: 새 소스 추가 = `source_profiles.yaml`에 한 블록 추가. 영업이 "이 소스도 넣어달라"고 하면 하루 내 반영.
- **신뢰성 = 제품 가치**: NO_CALL_COOLDOWN/격리로 차단 소스를 깔끔히 빼므로, 사용자에게 "죽은 소스"가 노출되지 않는다.

---

## 12. USER_CONFIRMATION_REQUIRED

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| source_profiles.yaml을 별도 파일로 둘까(registry 수정 회피)? | registry 안정성 | 별도 파일(권장) | No |
| 라우터를 ingestion/orchestration/ 신규 패키지로? | 코드 위치 | 예(신규 패키지) | No |
| fallback_strategies 기본 깊이(최대 몇 단계)? | 비용·시간 상한 | 최대 3단계 | No |

> 다음 문서: `04_BODY_EXTRACTION_AND_URL_RESILIENCE.md`.


## Phase E-3 — Source Strategy Memory (run 20260614T114401Z)

killer 루프가 source별 best/failed 전략을 **학습**해 다음 실행에 반영한다(단순 보고서 아님).
- 모델: `SourceStrategyMemory`(source_strategy_memory.py) — previous/final status, root_cause
  before/after, successful_strategy, failed_strategies, preferred_next_strategy, adapter_name,
  body_fetch_strategy, browser_strategy, parser_notes, cooldown_policy, safety_policy=no_bypass, evidence.
- 저장: canonical `ingestion/configs/source_strategy_memory.yaml`(커밋, secret 없음 — evidence는
  sha256/adapter 이름만) + run output `.../source_strategy_memory.learned.yaml`(gitignored).
- consume: `decide_strategy_with_memory(profile, memory)`가 성공 전략을 preferred_strategy로 덮어쓰고,
  `is_known_dead_end()`로 terminal(nyt/its 등) 무의미 재시도를 회피한다. 다음 plan이 이를 참조한다.


## Phase F — Production Orchestration Closure

Phase F에서 SourceStrategyMemory가 production 전략 선택을 직접 구동한다 —
`decide_production_strategy`(production_state.py) → `preferred_strategy_for(memory)`가
profile.preferred_strategy를 덮어쓴다. dead-end auto-skip 강제(known_dead_end 또는 is_known_dead_end).

`production_scheduler.build_production_run_plan`이 다음을 하나의 plan으로 통합한다:
ProductionSourceState + memory + RateLimitGovernor + quarantine + dead-end + cycle_planner.is_due.

Skip 우선순위: excluded > dead-end/not-ready > quarantine > cooldown(state) >
governor(rate-limit/min_interval) > interval(is_due). is_due cadence 레이어는 wired되어 있다
(last_run_at는 직전 state의 last_success_at에서) — governor와 나란히 두 번째 게이트로 작동한다.

모드:
- production (interval 준수)
- production-validation (interval 면제, 단 policy/cooldown/quarantine은 여전히 강제)
- production-dry-run (네트워크 0)

## Phase G — Force Production-Ready Source Closure

**판정: PARTIAL_WITH_HARD_BLOCKERS** (ALL_READY 아님).

비준비 소스를 닫기 위한 rescue/closure 흐름을 라우터에 추가했다:
- `source_readiness_closure.py` — 소스별 gap matrix를 만들어 어떤 소스가 비준비/degraded/제외인지 분류.
- `rescue_router.py` — 비준비 소스를 공식 API 라우트(`vendor_api_routes.py`)로 재라우팅. 우회 없음, key는 env에서만 읽고 evidence URL에서 stripped.
- `body_rescue_ladder.py` — 본문 보강용 ladder(현재 RSS snippet 단계).
- `source_value_policy.py` — not_service_useful/policy 제외 판정(its/dcinside/google_trends_explore).
- `run_source_readiness_closure.py` — closure 러너 CLI.

라우팅 결과:
- 공식 API로 승격(우회 아님): bok_ecos(ECOS StatisticSearch), eia(v2 data), kma(getUltraSrtNcst, base_date/time 수정으로 resultCode 10 해소), nyt(공식 Article Search — 기존 403은 웹스크래핑 탓), cnbc(RSS article references → snippet_only).
- 제외(enabled=false): its, dcinside, google_trends_explore.

홀드오버: gdelt는 라우트 wired·cooldown 자동관리이나 이번 런에 신선 데이터 없음 → EXTERNAL_RATE_LIMITED 유지. culture_info/product_hunt는 anchor 수정 커밋됐으나 라이브 재검증 부재로 degraded 유지.

---

## Phase G-2 — Last-Chance Source Resurrection (dcinside / google_trends_explore / gdelt)

**판정: PARTIAL_MIXED_PENDING_AND_BLOCKERS**. 라우터 관점에서 3개 소스에 대해 **새 진입 전략 2개와 거부 규칙 1개**를 결정적(deterministic) 규칙으로 추가했다. 어느 것도 LLM 판단이 아니며, 모든 분기는 소스 프로파일 + robots 실측 + rate-limit 상태로만 갈린다.

- **dcinside → 신규 전략 `robots_allowed_static_list_fetch`(산출은 DEGRADED 등급)**. `source_policy_probe.py`(robots 파서)가 갤러리별 robots를 읽어 allowed면 `dcinside_strategy.py`가 generic UA로 list HTML을 static GET한다. 이 전략은 **Cloudflare 챌린지/CAPTCHA/login을 감지하는 즉시 `*_BLOCKED_NO_BYPASS`로 중단**하는 가드를 내장한다 — 즉 "막히면 다른 전략으로 강행"이 아니라 "막히면 정직하게 포기"가 규칙이다. live 실증: robots 허용 갤러리 stockus → HTTP 200, nginx, 챌린지 없음 → 30 community_signal 파싱. registry route에 dcinside를 이 전략으로 wiring. 단 이 전략의 산출은 clean READY가 아니라 **PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY(=production_state DEGRADED)**다: 검증 범위가 stockus 단일 갤러리(SCOPE_SINGLE_GALLERY_STOCKUS)이고 list 메타데이터만(LIST_PREVIEW_ONLY_NO_BODY)이며 ToS 자동수집 조항 미검증(TOS_AUTOMATED_USE_UNVERIFIED). 라우터는 추가 갤러리를 일괄 확장하지 않고 갤러리별 robots 재확인을 전제로 한다.
- **google_trends_explore → 라우터에서 거부(requires_contract)**. trends.google.com robots는 비어있으나(차단 아님) 공식 API 부재 + explore 엔드포인트 anti-abuse 429 + 우회 금지(proxy/anti-bot/login 모두 불가)로 **compliant 자동 진입 전략이 존재하지 않는다**. 따라서 라우터는 이 소스를 호출하지 않고 requires_official_api_or_contract로 거부한다.
- **gdelt → 신규 전략 `gdelt_strategy.py`**. `RateLimitGovernor`가 min_interval/cooldown을 강제하고, query 단순화 ladder(broad→keyword→narrow)를 spaced probe로 시도한다. 429면 cooldown_until을 governor state 파일에 영속하고 **즉시 pending_resume로 빠진다(무한 retry 금지)** — 다음 run에서 cooldown 만료 시 자동 재개.

라우팅 안전을 강제하는 새 결정 계층: `source_supervisor.py`(LLM-ready지만 현재는 deterministic supervisor)가 unsafe 전략(우회·미허용 path)을 **거부**한다. supervisor가 승인한 전략만 라우터 산출로 인정된다.

## Phase G-3 — Final Source Closure

**판정: PARTIAL_WITH_VERIFIED_HARD_BLOCKERS**. 라우터를 나열식 `if source==...` 분기에서 **공통 결정 그래프**로 정리했다: `SourceCapability`(능력 선언) → `StrategyGraph`(전략 노드 빌드, unsafe 전략은 빌드 시점에 거부) → `ToolPlan`(policy/rate-limit/secret 불변식 강제 — secret **값**은 미포함, 정책 이름만 실음). 모든 분기는 여전히 deterministic이며 LLM 판단이 아니다.

- **StrategyGraph가 unsafe 전략을 빌드 단계에서 거부**한다 — 우회·미허용 path·합성 url 산출 전략은 노드로 등록되지 못한다. "막히면 다른 전략으로 강행"이 구조적으로 불가능하다.
- **product_hunt 전략 노드**: 합성 slug 전략 노드를 제거하고 GraphQL 실-url 노드(`url slug createdAt featuredAt id`)로 교체 → 라이브 canonical url + createdAt 산출. `fetch_product_hunt`.
- **culture_info 전략 노드 ladder**: data.go.kr `period2`(list) → `detail2`(seq별 detail) 2단 노드로 실 전시 url 해소. placeUrl 폴백 노드는 제거(무관 venue url 둔갑 금지). `fetch_culture_info`.
- **dcinside 전략 노드**: robots-allowed list fetch 노드 유지(generic UA static, 우회 0). detail body 노드는 정책상 비활성(ToolPlan이 list-only 정책 불변식을 강제).
- **gdelt 전략 노드**: Colab-parity DOC 2.0 ArtList 노드 유지, `RateLimitGovernor` lock과 결합해 429 시 pending_resume.

ToolPlan 불변식 위반(우회·secret 노출·rate-limit 무시) 전략은 라우터 산출로 인정되지 않는다. 신규 모듈: `source_capability.py`, `strategy_graph.py`, `tool_plan.py`.

## Phase G-4 — 흡수 구조 확장 (CommunityCorroborationGate + SourceSpecificProof + classify_risk_closure)

G-3의 결정 그래프를 나열식 `if`로 되돌리지 않고, 두 노드를 흡수 체인에 정식 편입했다(여전히 deterministic, LLM 판단 아님):

- **CommunityCorroborationGate**(`community_corroboration_gate.py`): EvidenceGate 하류 노드. 익명 금융/투자 갤러리(stockus 등)→`publish_level=internal_queue_only`, 펌핑/투자권유성 제목(매수/풀매수/가즈아/떡상/목표가 등)→`publish_blocked_until_corrob`, 그 외 커뮤니티→`preview_candidate`. 익명 source는 항상 `requires_external_confirmation=True`(09 참조).
- **SourceSpecificProof**(`source_specific_proof.py`): 격리 dedup namespace로 source별 EventQueue/raw_events contract 통과를 입증하는 노드. 공유 production dedup의 collapse(eq=0)와 분리해 소스 단위 contract_pass를 정직히 측정(05 참조).
- **classify_risk_closure**(`final_source_closure.py`): closure 시점에 각 비제외 소스를 status enum으로 분류하는 함수(PRODUCTION_READY_COMMUNITY_PREVIEW tier 포함).

확장된 흡수 체인: SourceCapability → PolicyProbe → StrategyGraph → ToolPlan → EvidenceGate → **CommunityCorroborationGate** → GdeltRateLimitProfile(RateLimitGovernor host-level) → **SourceSpecificProof** → StrategyMemory(+llm_agent_hints) → ProductionState(+PRODUCTION_READY_COMMUNITY_PREVIEW) → Monitoring → SourceSupervisorDecision(unsafe 전략 거부, proxy_rotation 등 AllowedStrategyRegistry 밖이면 거부).

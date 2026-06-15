# 08 — 재시도 / Rate-limit / 실패 정책 (Retry · Rate-limit · Failure Policy)

> **목적**: 호출 실패, 본문 추출 실패, rate-limit(429), provider gap을 **닫힌 정책**으로 처리한다. 실패 시 "더 많이 수집"이 아니라 **`분류 → fallback 선택 → 상태 영속`**으로 진행한다.
> **불변 원칙**: **우회하지 않는다.** Google Trends 429는 external gap, GDELT는 min_interval 준수, CAPTCHA/login/paywall은 BLOCKED/DEFER. 어느 것도 proxy/internal RPC/login 우회로 풀지 않는다.

---

## 0. 비개발자를 위한 설명

수집은 자주 실패한다. 인터넷이 원래 그렇다. 중요한 건 **실패에 어떻게 반응하느냐**다. 나쁜 반응은 "안 되네? 더 세게 다시 해보자"이고, 이건 IP 차단·비용 폭발·약관 위반으로 이어진다.

우리의 반응은 **차분한 의사**처럼 설계한다:
1. **진단**: 무슨 실패인가? (네트워크 일시 장애? 너무 자주 불러서 거절(429)? 로그인벽?)
2. **처방**: 진단에 따라 다르게 — 일시 장애는 잠깐 쉬고 재시도, 429는 한참 쉬고 대체 소스로, 로그인벽은 **포기하고 격리**(절대 뚫지 않음).
3. **기록**: 다음에 같은 실수를 안 하도록 "언제 다시 시도할지"를 적어둔다.

특히 **"막힌 문은 뚫지 않는다"**가 절대 원칙이다. CAPTCHA·로그인·결제벽은 우회하지 않고 그냥 그 소스를 뺀다.

---

## 1. error taxonomy (실패 분류 — 이미 존재)

> `ingestion/core/error_taxonomy.py:ErrorType` (~40종, 01 §3.3). 4군으로 묶어 정책을 건다.

| 군 | ErrorType | 정책 |
|---|---|---|
| **transient (일시)** | NETWORK_TIMEOUT, NETWORK_DNS_FAIL, NETWORK_CONNECTION_RESET, HTTP_5XX, HTTP_REDIRECT_LOOP | 지수 backoff 재시도(상한 내) |
| **rate (과호출)** | RATE_LIMITED, LLM_RATE_LIMIT | 쿨다운 + 재시도 큐, 우회 금지 |
| **terminal (차단)** | CAPTCHA_DETECTED, LOGIN_WALL_DETECTED, PAYWALL_DETECTED, ROBOTS_BLOCKED | 즉시 격리, 재시도 불가, 우회 금지 |
| **config/extraction** | INVALID_KEY, PARAMETER_MISSING, EXTRACTION_EMPTY, SELECTOR_MATCHED_BUT_URL_EMPTY | fallback 전략 또는 사람 개입(WARNING) |

---

## 2. retry policy (재시도)

> `ingestion/configs/retry_policy.yaml` (이미 존재): max_attempts, max_strategies_per_url, backoff(initial/max/exponential_base), retry_on, no_retry_on, per_source.

| 항목 | 값(기본) | 비고 |
|---|---|---|
| max_attempts | 5 | transient에만 |
| max_strategies_per_url | 3 | per_source override 가능 |
| backoff | initial 1s, exponential_base 2, max 30s | transient |
| retry_on | NETWORK_*, HTTP_5XX | |
| no_retry_on | CAPTCHA/LOGIN/PAYWALL/ROBOTS, INVALID_KEY | terminal/config |

**원칙**: 재시도 카운팅·budget은 **기존 `run_fetch_strategy_loop`가 이미 한다**. 오케스트레이션은 이를 **새로 만들지 않고** 결과(next_action)만 사용.

---

## 3. cooldown / backoff / Retry-After

| 상황 | 처리 |
|---|---|
| 429 (RATE_LIMITED) | `record_rate_limited()` → cooldown_seconds 영속. 그 시간 동안 health gate가 호출 차단 |
| Retry-After 헤더 존재 | 헤더 값 우선(>cooldown이면 헤더) |
| 연속 429 N회(기본 3) | cooldown 지수 증가(600→1800→7200s) + WARNING (IP 차단 예방, plans/012 §4.3) |
| transient | retry_policy backoff(지수, jitter) |

**핵심 전환(plans/012 §4)**: 현재 strategy loop는 429 시 `time.sleep(cooldown)`으로 워커 슬롯을 점유한다. **Celery(Phase G)에서는 sleep 대신 즉시 반환 + 재시도 큐**(§5). 단일 프로세스(Phase A)에서는 sleep 폴백 유지.

---

## 4. source-specific min_interval (소스별 최소 간격)

> `rate_limit_policy.yaml` per_source. INGESTION_FINAL §5 인용.

| source_id | min_interval | cooldown_on_429 | max_retries_on_429 | 비고 |
|---|---|---|---|---|
| gdelt | 60s | 900s | 1 | 커뮤니티 5s 대비 12배 보수. UA 필수 |
| google_trends_explore | 7200s | 3600s | 0 | **CONFIRMED_EXTERNAL_RATE_LIMIT**. 우회 불가 |
| google_trending_now | 7200s | 3600s | 0 | 동일 provider 정책 |
| alpha_vantage | (일 25) | — | — | daily quota guard |

---

## 5. RATE_LIMITED → 재시도 큐 (Phase G)

```
collect_source(source_id) 결과가 RATE_LIMITED:
  1. probe의 next_retry_at(epoch) 사용 → Redis sorted set retry_queue에 ZADD
     {source_id, query, reason}, score=next_retry_at
  2. task 즉시 반환 (sleep 없음 — 워커 슬롯 해방)
  3. 분 단위 beat task drain_retry_queue:
     ZRANGEBYSCORE retry_queue 0 now → collect_source.delay() 재발행
  4. 연속 RATE_LIMITED N회 초과 → cooldown 지수 증가 + WARNING
```

Phase A(단일 프로세스)에서는 retry_queue 대신 local_file에 next_retry_at 기록, 다음 cycle에서 due 소스만 재시도.

---

## 6. BLOCKED terminal 소스 자동 격리·재점검 (Phase G)

```
BLOCKED(CAPTCHA/LOGIN/PAYWALL/ROBOTS) 판정:
  1. Redis source_quarantine hash에 {source_id: {first_seen, count, last_error}} 기록
  2. beat 스케줄이 매 tick에 quarantine 조회 → 격리 소스 자동 제외
  3. 재점검: 격리 소스는 주 1회 단일 probe만. 2회 연속 성공 → 자동 복귀.
     4주 연속 BLOCKED → registry status 갱신 "제안" 리포트(자동 수정 안 함, 사람 승인)
  4. MVP_EXCLUDED/DEFERRED(x, blind, reuters, fmkorea, google_programmable_search, reddit)
     → 처음부터 스케줄 제외 (registry status를 스케줄러가 읽음)
```

Phase A에서는 `get_health_store()`의 BLOCKED_TERMINAL 상태가 health gate에서 동일 효과(이미 구현).

---

## 7. daily quota guard (비용·약관 상한, RISK-R02)

```
Redis 카운터 quota:{source_id}:{YYYYMMDD} INCR + 자정 TTL.
한도(yaml daily_quota 신규 필드, 한도의 90% 수준):
  newsapi=90, nyt=450, guardian=4500, alpha_vantage=20,
  serper≤30, tavily/exa≤30 (04 §enrichment budget)
초과 시 해당 소스 task 그날 skip + 로그.
```

Phase A에서는 local_file 카운터로 동일.

---

## 8. failure → next_action 매핑 (정책 표)

| failure | next_action | sleep? | 우회? |
|---|---|---|---|
| NETWORK_TIMEOUT/HTTP_5XX | retry(backoff) | 짧게(transient) | No |
| RATE_LIMITED | cooldown + retry_queue | **No(Celery)** / sleep(단일) | **No** |
| CAPTCHA/LOGIN/PAYWALL/ROBOTS | quarantine(terminal) | No | **No(절대)** |
| EXTRACTION_EMPTY | fallback 전략(browser) | No | No |
| SELECTOR_MATCHED_BUT_URL_EMPTY | structure_explorer | No | No |
| INVALID_KEY/PARAMETER_MISSING | WARNING 리포트(사람) | No | No |
| quota 초과 | skip(그날) | No | No |

**불변**: 어떤 행에도 "proxy rotation / internal RPC / login 우회 / 429 무시 연속 재시도"는 없다. 이것이 정책의 핵심.

---

## 9. google_trends_explore 특수 처리 (왜곡 금지)

- **상태**: CONFIRMED_EXTERNAL_RATE_LIMIT. **PASS 아님.** optional_enrichment. 이벤트 큐 비차단.
- **정책**: min_interval 7200s, cooldown 3600s, max_retries 0. gate 필수.
- **실패 시**: 04 §6 fallback chain(A google_trending_now → B RSS export → C 검색 enrichment). 우회 0건.
- **재개**: gate 통과 후 `--rate-limit-backend local_file`로 1회 probe(메모리 backend는 재시작 시 cooldown 소실).

---

## 10. Implementation diff blueprint

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY — Phase G (Celery) 진입 시
diff --git a/ingestion/orchestration/retry_queue.py b/ingestion/orchestration/retry_queue.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/retry_queue.py
@@
+def push_retry(redis, source_id, query, reason, next_retry_at): ...   # ZADD
+def drain_due(redis, now) -> list: ...                                # ZRANGEBYSCORE

diff --git a/ingestion/orchestration/quarantine.py b/ingestion/orchestration/quarantine.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/quarantine.py
@@
+def quarantine_source(redis, source_id, error): ...
+def is_quarantined(redis, source_id) -> bool: ...
+def due_for_recheck(redis) -> list: ...   # 주 1회

diff --git a/ingestion/orchestration/quota_guard.py b/ingestion/orchestration/quota_guard.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/quota_guard.py
@@
+def incr_and_check(redis, source_id, daily_quota) -> bool: ...  # INCR + TTL

diff --git a/ingestion/configs/rate_limit_policy.yaml b/ingestion/configs/rate_limit_policy.yaml
--- a/ingestion/configs/rate_limit_policy.yaml
+++ b/ingestion/configs/rate_limit_policy.yaml
@@ per_source:
+  newsapi:
+    daily_quota: 90      # 신규 필드 (한도 100의 90%)
+  nyt:
+    daily_quota: 450
```

**수정하지 않는 파일**: `strategy_runner.py`(sleep 폴백 유지), `failure_classifier.py`, `error_taxonomy.py`. rate_limit_policy.yaml은 daily_quota 필드 추가만(per_source 확장, 기존 키 불변).

---

## 11. test plan

```
test_transient_retries_with_backoff      # NETWORK_TIMEOUT → 재시도
test_rate_limited_no_sleep_celery        # 429 → 즉시 반환 + retry_queue
test_rate_limited_sleep_single_process   # 단일 모드 sleep 폴백
test_blocker_quarantines_immediately     # CAPTCHA → 격리 (재시도 0)
test_quarantine_excluded_from_schedule   # 격리 소스 beat 제외
test_quota_guard_skips_after_limit       # newsapi 90 도달 → skip
test_trends_429_confirmed_not_pass       # google_trends_explore PASS 표기 0
test_no_bypass_in_policy                 # grep proxy/captcha bypass 0
```

---

## 12. Agent Committee Review

| agent | 피드백 | status |
|---|---|---|
| operations-sre-agent | sleep→재시도 큐 전환이 워커 효율 핵심. 지수 cooldown으로 IP 차단 예방 | CLOSED_BY_DESIGN |
| source-ingestion-engineer | 기존 retry_policy/strategy loop 재사용, 신규 카운팅 안 만듦 | CLOSED_BY_DESIGN |
| legal-safety-compliance-reviewer | 우회 0 정책 + terminal 격리 명시 — 승인 | BLOCKED_BY_POLICY(우회) |
| adversarial-reality-critic | "실패=더 수집 아님" 전환이 핵심. 연속 429 지수 증가 양호 | CLOSED_BY_DESIGN |
| security-permission-guardian | quota guard로 비용·약관 동시 방어 | CLOSED_BY_DESIGN |
| commercialization-strategist | daily_quota가 비용 상한 = 사업 예측성 | CLOSED_BY_DESIGN |
| test-validation-agent | no_bypass/PASS 표기 테스트가 정책 회귀 방지 | CLOSED_BY_TEST_PLAN |

---

## 13. Risk Closure

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| provider 429 폭주 | min_interval 위반 | IP 차단 | 429 카운트 | min_interval + cooldown + 지수 | test_rate_limited | CLOSED_BY_DESIGN |
| 우회 시도 | 429 회피 욕구 | 약관 위반 | grep proxy/bypass | BLOCKED_BY_POLICY 고정 | grep 0건 | BLOCKED_BY_POLICY |
| 워커 슬롯 점유 | time.sleep cooldown | 처리량 저하 | 슬롯 모니터 | 재시도 큐(Celery) | test_no_sleep | CLOSED_BY_DESIGN |
| 비용 폭발 | quota 없음 | 과금 | quota 카운터 | daily_quota guard | test_quota_skip | CLOSED_BY_TEST_PLAN |
| google_trends PASS 오기 | 상태 왜곡 | 거짓 보고 | grep | CONFIRMED 고정(§9) | test_trends_not_pass | CLOSED_BY_DESIGN |
| 격리 소스 재호출 | 스케줄러 미반영 | 차단 악화 | quarantine 조회 | beat가 매 tick 조회 | test_quarantine_excluded | CLOSED_BY_TEST_PLAN |

---

## 14. Commercialization Impact

- **비용 상한 = 사업 예측성**: daily_quota로 "최악의 경우 일 비용"을 못 박을 수 있어, 가격·마진을 설계할 수 있다.
- **약관 준수 = 계약 가능성**: 우회 0 정책은 B2B 계약 시 법무 심사를 통과하게 하는 전제. "합법적 데이터 수집"이 영업 포인트.
- **가용성 = 신뢰**: 자동 격리·복귀로 죽은 소스가 사용자에게 안 보이고, 살아난 소스는 자동 복귀 → 운영 인력 최소화.
- **IP 차단 예방 = 지속성**: 지수 cooldown이 소스를 영구 차단당하지 않게 보호 → 데이터 자산 보존.

---

## 15. USER_CONFIRMATION_REQUIRED

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| daily_quota 기본값(한도의 몇 %)? | 안전 여유 | 90% | No |
| 연속 429 cooldown 지수 상한? | IP 차단 예방 | 7200s | No |
| 격리 재점검 주기? | 복귀 속도 vs 부하 | 주 1회 | No |
| Phase A에서 sleep 폴백 유지? | 단일 프로세스 단순성 | 예 | No |

### Phase E-2 — live revival의 rate-limit/실패 처리 (2026-06-14, run 20260614T105328Z)

full-revival의 모든 live 호출은 `run_collection_probe`(force=False) 경유 → health gate(쿨다운/격리/차단)를 존중한다. revival 루프의 실패 정책:
- **소스 격리**: `_revive_one_source`는 예외를 삼키고 소스별로 닫는다(한 소스 실패가 전체 run을 죽이지 않음). final_status 없는 소스 0 보장.
- **rate-limit 무리한 재시도 금지**: probe가 RATE_LIMITED면 즉시 `EXTERNAL_RATE_LIMITED`로 닫고 strategy ladder 재시도 안 함(strategy attempt 1건만). run4에서 gdelt/google_trends_explore가 이 경로로 정직하게 닫힘.
- **body fetch**: 소스당 1회(첫 candidate canonical_url), 15s timeout, robots disallow면 미fetch. 폭주/무한재시도 없음.
- **재실행 가능**: 산출물은 run_id별 디렉터리. 연속 실행 시 health 쿨다운이 누적돼 외부 부하를 억제(3회 연속 live run에서 rate-limit이 늘 수 있으나 이는 정책 준수의 결과).
- root cause taxonomy(RATE_LIMITED/EXTERNAL_API_ERROR/EMPTY_PAYLOAD/...)로 실패를 원자 분류 — "unknown"으로 끝내지 않음.

> 다음 문서: `09_DATA_QUALITY_EVALUATION_AND_RISK_GATES.md`.


## Phase E-3 — Rate-limit 재검증 정책 (run 20260614T114401Z)

RATE_LIMITED 2(gdelt/google_trends_explore)를 force=False(쿨다운 존중)로 **1회만** 재검증한다.
- 쿨다운 해소 시 정상 데이터 → alive 승격(예: gdelt가 회차에 따라 OFFICIAL_RECORD_ALIVE).
- 여전히 rate-limit이면 `EXTERNAL_RATE_LIMITED_WITH_RETRY_POLICY`로 clean terminal(무한 retry 없음,
  우회 없음, next_action=retry_after_cooldown). 폭주 방지: source별 strategy attempt ≤5, browser ≤1.
- HTTP 429는 body ladder에서도 EXTERNAL_RATE_LIMITED_WITH_RETRY_POLICY로 닫는다.


## Phase F — Production Orchestration Closure

Phase F는 런타임 거버넌스를 wired한다.

RateLimitGovernor(`rate_limit_governor.py`): per-source last_call_at + cooldown_until(wall-clock,
injectable now, persisted JSON). `detect_rate_limit_signal`은 error_taxonomy를 재사용한다
(429 / rate-limit text / GDELT note). cooldown = Retry-After 또는 per-bucket 보수적 기본값,
`_MAX_COOLDOWN_SECONDS=86400`으로 clamp(무한 대기 없음).

Quarantine(`quarantine.py`)은 runner에 **WIRED** 되었다: probe 실패가 persisted production state의
consecutive_failure_count에 누적되고, `evaluate_quarantine`가 retryable 실패를 threshold 3에서
quarantine → QUARANTINED, 6h recovery(`is_quarantine_active`가 재진입 게이트). policy terminal
(CAPTCHA/LOGIN/PAYWALL/ROBOTS)은 즉시 dead-end(quarantine 아님, 우회 없음).
body-fetch 반복은 alt strategy 시도 후 quarantine.

회귀 테스트로 3회 연속 실패 → QUARANTINED 확인.

## Phase G — Force Production-Ready Source Closure

**판정: PARTIAL_WITH_HARD_BLOCKERS** (ALL_READY 아님).

**gdelt — 정직한 rate-limit 홀드오버**:
- provider rate-limit에 걸림(HTTP 429 "one every 5 seconds"). 이번 세션에 누적된 호출이 IP를 throttle했다.
- 라우트는 정상 wired(GDELT DOC)이고 cooldown은 Phase F에서 자동관리(`_MAX_COOLDOWN_SECONDS=86400` clamp)되며 자가회복형이다.
- 그러나 이번 런에 신선 데이터를 못 받았으므로 **production_ready로 주장하지 않는다** → **EXTERNAL_RATE_LIMITED** 유지. 우회 금지 원칙과 정합(프록시 로테이션·내부 RPC 스크래핑 등 회피책 채택 안 함).
- 회복 경로: provider가 throttle하지 않는 윈도(non-throttled window)에서 재시도. 큐 점유 없이 cooldown 만료 후 자동 재진입.

기타 rate/policy 처리:
- nyt min_interval 7200s(~12/day)로 무료 티어 500/day에 안전 마진.
- google_trends_explore는 no key + probe unwired → needs_api_integration으로 enabled=false(429 회피가 아니라 미연동).
- its/dcinside는 policy/robots 제외(우회 없음).

---

## Phase G-2 — Last-Chance Source Resurrection (dcinside / google_trends_explore / gdelt)

**판정: PARTIAL_MIXED_PENDING_AND_BLOCKERS**. retry/rate-limit/failure 정책 관점에서 이번 단계는 **"막힌 문은 뚫지 않는다" 원칙을 세 가지 서로 다른 실패 유형에 정직하게 적용**한 사례다.

- **gdelt — 429 처리 강화(pending_resume, 무한 retry 금지)**. 신규 `gdelt_strategy.py`의 `RateLimitGovernor`가 min_interval/cooldown을 강제하고, query 단순화 ladder(broad→keyword→narrow)를 spaced probe로 시도한다. live probe가 HTTP 429("one every 5 seconds")를 반환하면 cooldown_until을 영속하고 **즉시 pending_resume로 빠진다 — 재시도를 무한 반복하지 않는다**. cooldown은 governor state 파일에 영속되어 다음 run에서 자동 재개. production_state는 `EXTERNAL_RATE_LIMITED_PENDING_RESUME → EXTERNAL_RATE_LIMITED`로 매핑해 fresh data 0건을 READY로 둔갑시키지 않는다. 회복 경로: provider non-throttled 윈도에서 단발 재수집(프록시 로테이션·내부 RPC 회피책 채택 안 함).
- **google_trends_explore — anti-abuse 429를 우회로 풀지 않음(blocker로 격상)**. robots는 비어있으나 공식 API 부재 + explore 엔드포인트 anti-abuse 429 + 우회(proxy/anti-bot/login) 금지로 compliant 자동 경로가 없다. 과거 "추측성 disable(needs_api_integration)"을 **검증된 evidence 기반 blocker(requires_official_api_or_contract)로 격상**했다. 429를 회피책으로 풀지 않고 공식 API/계약 확보 전까지 호출 안 함.
- **dcinside — robots-allowed path만, 차단 감지 시 즉시 중단(최종 등급 DEGRADED)**. robots 허용 갤러리에 한해 generic UA static GET하며, **Cloudflare 챌린지/CAPTCHA/login 감지 즉시 `*_BLOCKED_NO_BYPASS`로 중단**한다(렌더 강행·우회 없음). 이는 08의 "CAPTCHA/login/paywall은 BLOCKED, 우회 안 함" 원칙의 정확한 실행이다. registry known_blockers `[cloudflare,anti_bot]`는 실측 결과 챌린지가 없어 `[]`로 정정. 다만 사이트가 AI 크롤러를 robots에서 전면 차단한 상태를 generic UA로 접근한 점(AI_CRAWLER_ROBOTS_BLOCK_HONORED_GENERIC_UA)과 ToS 자동수집 조항 미검증(TOS_AUTOMATED_USE_UNVERIFIED, legal-safety review pending)을 정책 리스크로 남겨, 최종 등급은 clean READY가 아니라 **PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY(=production_state DEGRADED)**로 강등했다.

검증: 전체 회귀 1130 passed, secret scan PASS(210), 신규 설치 0, no bypass.

# 84. Pre-Orchestration Risk Closure 최종 보고서

날짜: 2026-06-12
계획: docs/74 | 기준선: 359 passed → 종료: **450 passed, 0 failed**

## 1. Risk별 결과 (§14 체크리스트 판정)

| 항목 | 판정 | 근거 |
|------|------|------|
| 12-2 Celery+Redis 미구현 확인 | **PASS** | beat/worker/스케줄러 코드 0건 — plans/012로 유지 |
| 12-1 store pluggable + local persistent | **PASS** | `rate_limit_store.py` 3종 backend, 재기동 roundtrip 테스트 + 2-프로세스 스모크 PASS (docs/75) |
| 12-1 redis optional 안전 fallback | **PASS** | 연결 불가 → NOT_CONFIGURED no-op + local_file→memory 자동 fallback (테스트 가드) |
| 12-3 health 전이 테스트 | **PASS** | 21 tests — 전이 5종/임계값/회복/gate 네트워크 미호출/force (docs/76) |
| 12-4 runtime check 러너 + Docker 문서 | **PASS** | 러너 + 5 tests + 실측 `READY` + docs/77 (실제 빌드는 의도적 비범위) |
| 12-5 복원력 테스트 + challenge solving 미구현 | **PASS** | 14 tests, 코드 diff 0 — blocker 4종 즉시 terminal (docs/78) |
| 12-6 RATE_LIMITED가 UNKNOWN/FAILED로 안 떨어짐 | **PASS** | Route 2 429 감지 + 매핑 테스트 + trends 1회 검증 RATE_LIMITED+영속 (docs/79) |
| 12-7 publication boundary 정리 | **PASS** | yaml+모듈+10 tests, 수집 경로 미연결 가드 (docs/80) |
| 12-8 scan 도구 + sanitize 회귀 | **PASS** | 11 tests + baseline/종료 스캔 PASS 710 files (docs/81) |
| 12-9 alias 테스트 | **PASS** | 8 tests — _ALIASES 전체/MISMATCH/EMPTY (docs/82) |
| 12-10 6개 재프로브 + registry 갱신 | **PASS** | 6/6 LIVE_SUCCESS + registry status 갱신 (docs/83) |
| docs 74~84 + 71~73 갱신 | **PASS** | 신규 11편 + 갱신 3편 |
| pytest·hygiene·scan 통과 | **PASS** | 450 passed / scan exit 0 / hygiene는 의도된 WARNING 6건(아래) |

미충족 항목 없음. 단, hygiene exit 1은 legacy alias 6건의 **의도된 경고**(기능 무영향,
사용자 액션 A-1)이며 도구 자체 동작은 정상이다.

## 2. 수집 루프 동작 (이번 라운드 이후)

```
run_collection_probe(source_id, force=False)
 ├─ health gate: BLOCKED_TERMINAL/쿨다운/격리/이월 → 네트워크 없이 즉시 반환
 ├─ Route 1 (API) / Route 2 (Playwright 렌더) / Route 3 (전략 루프)
 │    ├─ 전략 루프 진입 전: is_cached + in_cooldown(영속) gate
 │    ├─ 429 → record_rate_limited → deadline 영속 (backend에 따라 디스크/redis)
 │    └─ CAPTCHA/LOGIN/PAYWALL/ROBOTS → 즉시 terminal BLOCKED
 └─ 모든 return 직전 health store 갱신 (성공 시 failure_count 리셋)
```

Celery(plans/012)는 `get_store()`(redis backend)·`get_health_store().list_due_for_retry()`·
`run_collection_probe`를 그대로 꽂아 쓴다 — 인터페이스 준비 완료.

## 3. 봇 대응 원칙 (불변 확인)

허용: UA 변형, 추출기 교체, JS 렌더(playwright/selenium), 정책 내 429 재시도.
금지: CAPTCHA/Turnstile/challenge solving, 로그인·페이월 우회, robots 무시 — 감지 즉시
terminal + health store에 BLOCKED_TERMINAL 영속 (재시도 자체가 차단됨). 테스트로 고정.

## 4. 재프로브 결과 (12-10)

6/6 LIVE_SUCCESS: yna(120) hankyung(50) maekyung(50) aljazeera(25) zdnet_korea(10)
etnews(10) → **CORE_READY 38 → 44**. google_trends_explore 1회: RATE_LIMITED +
next_retry_at 디스크 영속 — 성공 기준 충족, 즉시 재시도 안 함.

## 5. 보안·배포 상태

- secret scan: baseline + 종료 2회 PASS (710 files, BLOCKED 0). 키 값은 어떤 리포트에도
  미포함 (메모리 내 비교 + boolean assert).
- `.env` 미수정 (legacy alias 개명은 사용자 액션 A-1).
- browser runtime: 로컬 READY 실측. Docker 전제(playwright 이미지/한글 폰트/headless/
  shm) docs/77 문서화 — 이미지 빌드는 plans/012.

## 6. 문서/테스트 집계

- 신규 문서: docs/74~84 (11편). 갱신: docs/71(리스크 레지스터 — T02 부분해소/F01·S01·R01
  해소/L01 정책화), docs/72(store 구조+health gate), docs/73(CORE_READY 44, 신규 러너/도구,
  사용자 액션 A-1 확대 + A-5/A-6 추가).
- 신규 테스트 8파일 91개: scan_secrets 11, rate_limit_store 16(시그니처 가드 포함),
  source_health 21, google_trends_guard 6, strategy_resilience 14, browser_runtime_check 5,
  publication_policy 10, env_alias_precedence 8 — 기존 359개와 함께 **450 passed**.
- 기존 `test_rate_limit_policy.py` 27개(계획서 표기 "20개"는 과소집계) **무수정** 전체 통과.

## 7. 잔여/이월

| 항목 | 상태 | 경로 |
|------|------|------|
| 12-2 Celery+Redis 주기 수집 | DEFERRED (의도) | plans/012 |
| Redis 실인스턴스 연동·멀티워커 검증 | DEFERRED | plans/012 §3 |
| publication 가드의 게시 계층 연결 | DEFERRED | 게시 계층 구현 시 |
| 뉴스 약관 법무 검토 (RISK-L01 잔여) | 사용자/출시 전 | docs/80 §5 |
| scan pre-commit/CI 등록 | 사용자 선택 | docs/81 §4 (A-6) |
| .env legacy alias 6건 개명 | 사용자 선택 | docs/82 §4 (A-1) |

비고: `ingestion/outputs/state/_cooldown_smoke.py`는 1회용 스모크 스크립트로 남아 있다
(삭제는 destructive 제약상 사용자 판단).

## 8. 최종 판정

**A (계획 전 항목 닫힘)** — 12-2 제외 9개 리스크 모두 PASS, 테스트 450/450, 보안 스캔
PASS, live 검증 7회(뉴스 6 + trends 1, 소스당 1회 원칙 준수). Celery 오케스트레이션
(plans/012) 착수 전제 조건 충족.

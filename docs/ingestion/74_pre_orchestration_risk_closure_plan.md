# 74. Pre-Orchestration Risk Closure 라운드 — 계획

날짜: 2026-06-12
기준선: `python -m pytest ingestion/tests -q` → **359 passed** (라운드 시작 시점 확인)

## 1. 목적

직전 라운드(docs 70~73)에서 38개 소스가 CORE_READY로 확정됐다. Celery+Redis 주기 수집
오케스트레이션(plans/012)으로 넘어가기 전에, 남은 운영 리스크를 이번 라운드에서 닫는다.

**이번 라운드는 12-2(Celery+Redis 주기 수집)를 구현하지 않는다.** 모든 새 store/guard는
나중에 Celery worker가 그대로 꽂아 쓸 수 있는 인터페이스로 만든다.

## 2. Scope

| RISK | 내용 | 닫는 방법 | 대상 파일 | 테스트 | 문서 |
|------|------|-----------|-----------|--------|------|
| 12-1 | rate limit 캐시가 in-process dict — 재기동 시 휘발 | pluggable `RateLimitStore` (memory / local_file / redis) + cooldown 영속화 | `ingestion/core/rate_limit_store.py`(신규), `rate_limit_policy.py`, `rate_limit_policy.yaml`, `strategy_runner.py` | `test_rate_limit_store.py` + 기존 20개 무수정 통과 | docs/75 |
| 12-3 | 장애 소스 격리 부재 — 죽은 소스를 매 라운드 재시도 | `SourceHealthState` 전이 모델 + quarantine + collection_probe health gate | `ingestion/core/source_health.py`(신규), `collection_probe.py` | `test_source_health.py` | docs/76 |
| 12-4 | 브라우저 런타임(배포 환경) 검증 수단 없음 | runtime check 러너 + Docker 배포 전제 문서화 | `runners/run_browser_runtime_check.py`(신규) | `test_browser_runtime_check.py` | docs/77 |
| 12-5 | 전략 복원력이 테스트로 고정되지 않음 | 동작 변경 없이 회귀 테스트로 고정 | (코드 변경 없음) | `test_strategy_resilience.py` | docs/78 |
| 12-6 | Google Trends 429 재발 — cooldown이 휘발 | trends 정책 강화(2h) + 429 영속화 + Route 2 429 감지 | `rate_limit_policy.yaml`, `playwright_probe.py`, `cloud_browser_like.py` | `test_google_trends_guard.py` | docs/79 |
| 12-7 | 게시(퍼블리싱) 경계 미정의 — 저작권/약관 리스크 | publication policy 레이어(수집 경로 미연결) | `configs/publication_policy.yaml`(신규), `core/publication_policy.py`(신규) | `test_publication_policy.py` | docs/80 |
| 12-8 | secret 유출 스캔 자동화 부재 | 2계층 scan 도구 (패턴 WARNING / .env 실값 일치 BLOCKED) | `tools/scan_secrets.py`(신규) | `test_scan_secrets.py` + `_sanitize_response` 회귀 | docs/81 |
| 12-9 | env alias 위생 — legacy 이름 혼재 | hygiene 도구 일반화(_ALIASES 전체) + ALIAS_VALUE_MISMATCH/EMPTY_VALUE | `tools/check_env_hygiene.py`, `.env.example` | `test_env_alias_precedence.py` | docs/82 |
| 12-10 | Phase 1 뉴스 6개(yna/hankyung/maekyung/aljazeera/zdnet_korea/etnews) 미검증 | CLI 러너 신규 + live 재프로브(소스당 1회) + registry status 실측 갱신 | `runners/run_collection_probe.py`(신규), `source_registry.yaml` | (live 검증) | docs/83 |

## 3. 제외 Scope (이번 라운드에서 하지 않는 것)

- **12-2 Celery+Redis 주기 수집** — plans/012에서 수행. beat/worker/주기 스케줄러 구현 금지.
- CAPTCHA/Turnstile/login/paywall 우회 — 정책상 영구 금지 (terminal BLOCKED 처리).
- 실제 Docker 이미지 빌드 — docs/77에 전제만 문서화.
- fakeredis 의존성 추가 — dict 기반 fake client 주입으로 테스트.
- registry 57개 entry 구조 변경 — publication policy는 별도 yaml.

## 4. 설계 전제 (탐색으로 확정한 사실)

- 뉴스 6개는 이미 `_PROBE_SPEC`에 존재 (`api_probe.py`) → `run_collection_probe`가 Route 1로
  라우팅. 새 라우팅 경로 불필요, CLI 러너 + sample_title/url 보강만 필요.
- 기존 rate-limit 테스트 20개가 모듈 레벨 `_call_cache` dict를 직접 import·mutate +
  `time.monotonic` monkeypatch → in-memory backend는 **그 dict 객체를 그대로** backing으로
  사용해야 함 (재할당 금지, `.clear()`만 허용).
- `PROBE_STATUS`는 `ProbeResult.__post_init__`에서 강제 → 새 literal `RATE_LIMITED_DEFERRED`
  추가 금지. status는 `RATE_LIMITED` 유지, 뉘앙스는 `retry_after_reason`/health state로 표현.
- `CloudBrowserLikeStrategy`(Route 2)에 429 감지 없음 → 12-6에서 닫을 실제 gap.
- `ingestion/outputs/state/` 없음(신규 생성). redis==5.0.0 설치됨, fakeredis 미설치.
- 예산 모순 해소: 전역 기본 3 유지(기존 테스트 고정), 봇 의심/브라우저 필수 소스는
  `per_source:` 오버라이드 (krx_kind=8, dcinside=6 기존 유지).

## 5. 하드 제약

- API 키·토큰·`.env` 값 출력/로그/문서/리포트 저장 전면 금지. 키는 NAME·존재여부만.
- `.env` 수정 금지 (`.env.example`은 수정 가능). rm/reset/clean/push 금지.
- live 호출 소스당 1회 원칙.
- Celery beat/worker/주기 스케줄러 구현 금지.

## 6. 작업 순서 (의존성 순)

1. **Step 0** — 본 문서 + 기준선 (359 passed 확인 완료)
2. **Step 1** — 12-8 secret scan (이후 모든 artifact의 게이트이므로 최우선)
3. **Step 2** — 12-1 RateLimitStore
4. **Step 3** — 12-3 SourceHealthState (Step 2의 store 패턴 재사용)
5. **Step 4** — 12-6 trends guard (Step 2의 `record_rate_limited` 사용)
6. **Step 5** — 12-5 복원력 테스트 고정
7. **Step 6** — 12-4 browser runtime check
8. **Step 7** — 12-10 CLI 러너 + 뉴스 6개 live 재프로브 (Step 3 health gate 경유)
9. **Step 8** — 12-7 publication boundary
10. **Step 9** — 12-9 env alias 위생
11. **Step 10** — 통합 검증 + docs 71~73 갱신 + docs/84 최종 보고

## 7. Fallback 정책

- Redis backend 불가(미설치/연결 실패) → local_file → memory 순 자동 fallback. 예외 금지.
- local_file 손상(JSON parse 실패) → 빈 상태로 시작 (수집 중단 금지).
- 시계 역행(미래 timestamp) → 만료 처리.
- health gate 오분류(CAPTCHA 오탐 등) → `--force` 플래그 + JSON 수동 편집 절차 (docs/76).
- 뉴스 보강 시 extract_candidate_urls 0건 → 실패가 아니라 `next_action="update_selector"`.

## 8. 이월 항목 (이번 라운드 종료 후 잔여)

- 12-2: Celery beat/worker 주기 수집 — plans/012.
- Redis backend의 멀티워커 동시성 검증 — Redis 실인스턴스가 붙는 plans/012에서.
- publication policy의 게시 계층 연결 — 게시 계층(API/프론트) 구현 시.
- `SourceHealthStore.list_due_for_retry()` 소비자 — Celery 스케줄러 진입점.

## 9. 종료 조건

§14 체크리스트(사용자) 기준 — 각 항목 PASS/PARTIAL/FAILED/BLOCKED/DEFERRED/UNKNOWN으로
docs/84에 명시. 미충족 항목에 "완료" 표기 금지.

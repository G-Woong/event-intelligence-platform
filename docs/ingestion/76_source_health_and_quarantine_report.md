# 76. Source Health / Quarantine 보고서 (RISK 12-3)

날짜: 2026-06-12

## 1. 무엇을 닫았는가

장애 소스 격리 메커니즘이 없어, 죽은/차단된 소스를 매 라운드 동일하게 재시도했다
(RISK-F01). 이제 소스별 health 상태가 영속화되고, `run_collection_probe`가 상단
health gate에서 네트워크 호출 없이 스킵한다.

## 2. 상태 모델 (`ingestion/core/source_health.py`)

| 상태 | 의미 | 진입 조건 |
|------|------|-----------|
| `HEALTHY` | 정상 | LIVE_SUCCESS / LIVE_PARTIAL (failure_count 리셋) |
| `DEGRADED` | 일시 장애 누적 중 | NETWORK_ERROR/TIMEOUT/5XX 누적 < 3 |
| `RATE_LIMITED_COOLDOWN` | 429 cooldown | RATE_LIMITED (+next_retry_at) |
| `QUARANTINED_RETRYABLE` | 격리(재시도 가능) | 일시 장애 누적 ≥ 3 (+6h 재점검 시각) |
| `BLOCKED_TERMINAL` | 영구 차단 | CAPTCHA/LOGIN_WALL/PAYWALL/ROBOTS 또는 status=BLOCKED 즉시 |
| `DEFERRED_SPECIAL_ROUND` | 특수 라운드 이월 | DEFERRED |

전이는 순수 함수 `apply_probe_outcome(prev, *, status, error_category, next_retry_at,
quarantine_threshold=3)`로만 일어난다 (테스트 용이성).

`should_skip(state) -> (bool, reason)`:
- `BLOCKED_TERMINAL` → 항상 skip
- `DEFERRED_SPECIAL_ROUND` → skip (특수 라운드에서만 처리)
- `RATE_LIMITED_COOLDOWN` / `QUARANTINED_RETRYABLE` → `next_retry_at`이 미래일 때만 skip
  (deadline 경과 시 자동 재시도 허용)

## 3. Store

- `SourceHealthStore`(ABC) + `InMemorySourceHealthStore`(테스트용) +
  `LocalFileSourceHealthStore`(`ingestion/outputs/state/source_health.json`,
  tempfile+os.replace 원자적 쓰기, 손상 시 빈 상태).
- `get_health_store()` 싱글턴 — 기본 local_file. `reset_health_store_for_tests(store)`로
  테스트 주입.
- `list_due_for_retry()` — **미래 Celery 스케줄러 진입점** (이번 라운드 소비자 없음).

## 4. collection_probe 통합 (최소 diff)

- `run_collection_probe(source_id, query=None, max_items=5, force=False)` —
  `force` kwarg 추가 (기존 호출부 무영향).
- 상단 `_health_gate`: BLOCKED_TERMINAL → 네트워크 없이 `BLOCKED` 반환,
  cooldown/quarantine 미래 → `RATE_LIMITED`, deferred → `DEFERRED`.
  `next_action="health_gate_skip:<reason>"`으로 구분 가능.
- 하단 `_update_health(result)`: Route 1/2/3 모든 결과 return 직전 store 갱신.
  store 장애 시에도 절대 raise하지 않음 (수집을 막지 않는다).
- 통합 지점은 **collection_probe 단일화** — strategy_runner는 health store를 직접 보지
  않는다 (rate limit cooldown만 본다).

## 5. 수동 unquarantine 절차 (오분류 복구)

health gate 과차단 시나리오: CAPTCHA 오분류 1회로 BLOCKED_TERMINAL에 들어가면 영구
스킵된다. 복구 방법 2가지:

1. **`--force` 우회 점검**: `python -m ingestion.runners.run_collection_probe --source <id> --force`
   → gate를 우회해 1회 live 점검. 성공하면 `_update_health`가 HEALTHY로 자동 복구.
2. **JSON 수동 편집**: `ingestion/outputs/state/source_health.json`에서 해당 source_id
   entry의 `"state"`를 `"HEALTHY"`로 바꾸고 `"failure_count": 0`으로 리셋 (파일은 사람이
   편집 가능한 indent JSON).

## 6. 검증

`ingestion/tests/unit/test_source_health.py` — **21 passed**:
전이 5종(성공/partial/429/blocker 4종/deferred), 누적→격리 임계값, 격리 후 회복,
커스텀 threshold, should_skip 3종, local file roundtrip/손상 복구, list_due_for_retry,
BLOCKED skip 시 네트워크 미호출(monkeypatch 가드), force 우회, 성공 시 store 갱신,
cooldown gate.

## 7. 비범위

- 스케줄러/Celery queue 구현 없음 (12-2, plans/012).
- registry 57개 entry 구조 변경 없음 — health는 별도 상태 파일.

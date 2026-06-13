# 75. RateLimitStore Closure 보고서 (RISK 12-1)

날짜: 2026-06-12

## 1. 무엇을 닫았는가

rate limit 캐시(`_call_cache`)가 in-process dict라 **재기동 시 휘발**되어, 429 cooldown이
프로세스 수명에 묶여 있었다 (RISK-T02 일부). 이제 backing store가 pluggable해졌고,
429 cooldown deadline(`next_retry_at`)이 영속화된다.

## 2. 구조

신규 `ingestion/core/rate_limit_store.py`:

```
RateLimitStore (ABC)
 ├── InMemoryRateLimitStore(backing: dict)     # 기본. 모듈 레벨 _call_cache 그 객체를 backing
 ├── LocalPersistentRateLimitStore             # ingestion/outputs/state/rate_limit_cache.json
 └── RedisRateLimitStore(client=None, url=None) # plans/012 §3 키 계약: rate_limit:{source_id}:{query_hash}
```

인터페이스: `age_seconds(key)` / `record(key, ttl_seconds)` / `get_next_retry_at(key)` /
`set_next_retry_at(key, iso_ts, reason)` / `status()` →
`READY | NOT_CONFIGURED | DEGRADED_FALLBACK`.

### backend 선택 (우선순위)

1. env `INGESTION_RATE_LIMIT_BACKEND` (memory/local_file/redis)
2. `rate_limit_policy.yaml`의 `rate_limit_backend:` 섹션
3. 기본 `memory` — **기존 동작 무변경**

redis 선택 + 연결 불가 → local_file → memory 순 자동 fallback (예외 금지, 검증됨).

### 설계 결정

- **`_call_cache` 재할당 금지**: 기존 테스트 20개가 dict 객체 참조를 직접 보유·mutate하고
  `time.monotonic`을 monkeypatch한다. InMemoryRateLimitStore는 그 dict를 backing으로 받고
  monotonic을 호출 시점에 평가한다. → 기존 20개 테스트 **무수정 통과** 확인.
- **local_file은 wall-clock만 저장**: monotonic은 프로세스 간 의미가 없으므로 디스크에는
  `time.time()` epoch + ISO 8601만 기록 (테스트로 가드).
- **원자적 쓰기**: tempfile + `os.replace`. Windows 파일 잠금 대비 PermissionError 1회 재시도.
- **손상 JSON → 빈 상태 시작**, **미래 timestamp(시계 역행) → 만료 처리**.
- **redis lazy import + client 주입**: fakeredis 의존성 추가 없이 dict 기반 fake client로 테스트.

## 3. 공개 시그니처 (불변 + 신규)

| 함수 | 변경 |
|------|------|
| `cache_key(source_id, query="")` | 불변 |
| `is_cached(source_id, query="")` | 시그니처 불변, 내부만 store 경유 |
| `record_call(source_id, query="")` | 시그니처 불변, 내부만 store 경유 (ttl 전달) |
| `record_rate_limited(source_id, query="", cooldown_seconds=None) -> str(ISO)` | **신규** |
| `in_cooldown(source_id, query="") -> tuple[bool, Optional[str]]` | **신규** |

`strategy_runner.py` 최소 수정 2곳:
- 루프 진입 전 `in_cooldown` 체크 → 네트워크 없이 `status="rate_limited"` 반환.
- 429 재시도 소진 종료 경로에서 `record_rate_limited` 호출 → deadline 영속화.

## 4. 검증

- `test_rate_limit_store.py` — **신규 테스트 통과** (local 재기동 roundtrip, 손상 JSON,
  clock skew, monotonic 미저장 가드, next_retry_at 영속, fake client SETEX/키 패턴,
  NOT_CONFIGURED no-op, env override, redis fallback, 싱글턴, 시그니처 가드,
  record_rate_limited/in_cooldown roundtrip, 만료 cooldown)
- `test_rate_limit_policy.py` — 기존 **27개 무수정 전체 통과** (계획서의 "20개"는 과소집계 — `_call_cache` 직접 mutate·monkeypatch 테스트 포함 전부 무수정)

## 5. 한계 / 이월 (plans/012 몫)

- **멀티워커 동시성**: local_file 백엔드의 read-modify-write는 단일 프로세스 가정.
  멀티워커 안전성은 Redis backend(SETEX 원자성)가 담당 — Redis 실인스턴스 연동·검증은
  plans/012에서 수행.
- Celery task가 사용할 진입점: `get_store()` + `record_rate_limited`/`in_cooldown` 그대로.

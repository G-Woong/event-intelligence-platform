# Observability — LangSmith Tracing

## Overview

`backend/app/core/observability.py`의 `setup_langsmith()`는 FastAPI lifespan 시작 시 1회 호출된다.
`LANGSMITH_TRACING=true`이면 LangChain 환경변수를 wiring하고, 아니면 no-op.

## 활성화

`.env` 또는 환경변수에 다음을 설정:

```
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=<your-key>
LANGSMITH_PROJECT=event-intelligence
```

`LANGSMITH_TRACING`이 `true`, `1`, `yes` (대소문자 무관) 중 하나여야 활성화된다.

## 동작 방식

- `LANGCHAIN_TRACING_V2=true` 설정 → LangChain이 LangSmith로 trace 자동 전송
- `LANGCHAIN_ENDPOINT`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` 순서로 wiring
- LangChain이 설치되지 않은 환경에서도 `os.environ` 설정만 하므로 부작용 없음
- 시작 로그: `LangSmith tracing enabled project=<project>`
- 비활성 로그: `LangSmith tracing disabled (LANGSMITH_TRACING unset/false)`

## API 키 보안

- `LANGSMITH_API_KEY` 값은 로그/응답에 절대 출력되지 않는다
- `settings.redacted_env_status()`로 키 존재 여부(길이)만 확인 가능

## Opt-in Smoke Test

LangSmith 실전송 smoke는 기본 CI에 포함되지 않는다.
실행하려면:

```bash
LANGSMITH_TRACING=true \
LANGSMITH_API_KEY=<key> \
LANGSMITH_PROJECT=ei-test \
RUN_LANGSMITH_SMOKE=1 \
pytest tests/smoke/ -k langsmith -v
```

> `RUN_LANGSMITH_SMOKE=1` smoke 테스트는 본 STEP에서 작성되지 않았다. STEP 008B에서 추가 예정.

## Reconciler 로그 패턴 (STEP 008B)

`POST /api/admin/raw-events/reconcile-stuck` 호출 시 서비스 레이어에서 다음 로그가 출력된다:

| 이벤트 | 레벨 | 위치 |
|---|---|---|
| stuck row 발견 | (없음, 결과가 response에 포함됨) | reconciler_service |
| _patch_status retry 시작 | (tenacity 내부 — WARNING 없음) | agent_worker |
| _patch_status 3회 모두 실패 | WARNING | agent_worker: `raw_event status update failed after retries id=... reason=...` |
| raw_event_id 없어서 스킵 | WARNING | agent_worker: `raw_event_id absent — status update skipped status=...` |

### stuck 탐지 기준
- `status == "enqueued"` AND `updated_at < now() - before_seconds`
- 기본 `before_seconds=600` (10분). 운영 환경 권장값: 600~1800.

## 다음 단계

- STEP 008C: reconciler cron 자동 실행 + span 커스텀 메타데이터 + `raw_event_id` 태깅
- STEP 010: LLM 호출 비용/레이턴시 대시보드 연동

# agents/

LangGraph 기반 이벤트 처리 파이프라인.

## 구조

- `graphs/event_processing_graph.py` — 11-node StateGraph. `run(RawEvent) -> FinalEventCard`
- `state/event_state.py` — `EventState` TypedDict
- `nodes/` — 각 노드 함수 (STEP 003: 모두 mock)
- `agent_worker.py` — `stream:to_agent` consumer. 그래프 실행 후 backend에 HTTP POST

## 실행

```bash
python -m agents.agent_worker
```

환경변수 `REDIS_URL`, `BACKEND_URL` 필요.

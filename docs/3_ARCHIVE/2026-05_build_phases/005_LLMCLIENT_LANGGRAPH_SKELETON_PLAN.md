# STEP 005 — LLMClient Wire-up + Extensible LangGraph/LangChain Agent Skeleton
# (Plan 영구 사본 — 실행 전 확정본)

## 목표

STEP 004.5 skeleton audit에서 확인된 미연결 LLMClient를 agent 노드에 wire-up하고,
향후 provider/prompt/노드 고도화를 테스트 주도로 확장할 수 있는 교체 가능한 골격을 구축한다.

## 사용자 결정 사항

- 구조화 출력: 순수 Pydantic + `json.loads` (instructor/pydantic-ai 미도입)
- agent-worker 동기 유지 (async 전환 STEP 008로 연기)
- `.env.example` 신설 + `Settings`에 LLM_* 키 확장

## 수정·생성 대상 파일

| 경로 | 작업 |
|---|---|
| `backend/app/services/llm_client.py` | 전체 재작성 (BaseLLMClient/Mock/OpenAI/factory/lazy singleton + legacy alias) |
| `backend/app/core/config.py` | LLM_* 5개 필드 추가, redacted_env_status에 LLM_PROVIDER 추가 |
| `agents/tools/__init__.py` | 신규 (빈 파일) |
| `agents/tools/llm.py` | 신규 (4개 헬퍼 + 4개 Pydantic Output) |
| `agents/prompts/__init__.py` | 신규 (load_prompt) |
| `agents/prompts/summarize_event.md` | 신규 |
| `agents/prompts/impact_analysis.md` | 신규 |
| `agents/prompts/fact_check.md` | 신규 |
| `agents/prompts/final_card_writer.md` | 신규 |
| `agents/nodes/impact_analysis.py` | LLM tool 호출 + fallback |
| `agents/nodes/fact_check.py` | LLM tool 호출 + fallback |
| `agents/nodes/final_writer.py` | summary만 LLM tool 호출 + fallback |
| `agents/state/event_state.py` | 4개 필드 추가 |
| `agents/graphs/event_processing_graph.py` | initial state에 llm_provider/llm_errors 주입 |
| `agents/tests/__init__.py` | 신규 |
| `agents/tests/test_prompts.py` | 신규 (2 cases) |
| `agents/tests/test_tools_llm.py` | 신규 (3 cases) |
| `agents/tests/test_nodes_with_llm.py` | 신규 (4 cases) |
| `agents/tests/test_pipeline_with_llm.py` | 신규 (1 case) |
| `agents/tests/test_openai_smoke.py` | 신규 (opt-in 1 case) |
| `backend/tests/test_llm_client.py` | 신규 (5 cases) |
| `docker-compose.dev.yml` | agent-worker.environment에 LLM_PROVIDER/LLM_MODEL 명시 |
| `.env.example` | 신규 (루트, 키 이름만) |
| `docs/ARCHITECTURE.md` | 헤더 STEP 005, skeleton 표 갱신 |
| `docs/TRD.md` | 헤더 STEP 005, env 표 LLM_* 5개 추가 |
| `docs/AGENT_WORKFLOW.md` | LLM 호출 경로 보강 |
| `docs/COMPATIBILITY_NOTES.md` | STEP 005 추가 기록 |
| `docs/LLM_AGENT_DESIGN.md` | 신규 |
| `docs/PROMPT_EXPERIMENT_GUIDE.md` | 신규 |
| `plans/005_LLMCLIENT_LANGGRAPH_SKELETON_PLAN.md` | 본 파일 |
| `plans/005_LLMCLIENT_LANGGRAPH_SKELETON_REPORT.md` | 신규 (실행 보고) |

## 설계 원칙

1. Provider 교체 가능: BaseLLMClient (ABC) → MockLLMClient, OpenAILLMClient
2. 노드는 LLM에 강결합 금지: 노드는 EventState → EventState만 유지. LLM은 agents/tools/llm.py 경유
3. 프롬프트 분리: agents/prompts/*.md 텍스트 파일. load_prompt(name) 헬퍼로 로딩
4. mock/real 분기: LLM_PROVIDER=mock이면 기존 e2e/smoke PASS. LLM_PROVIDER=openai이면 GPT-4o-mini 호출
5. Pydantic 검증 + fallback: LLM 응답 실패 시 mock-equivalent 값으로 fallback, llm_errors 누적
6. opt-in 실호출 테스트: RUN_OPENAI_SMOKE=1이 아니면 OpenAI 실호출 테스트 skip
7. 동기 유지: 그래프와 LLMClient.complete()는 동기. tenacity 동기 retry 1-2회

## 비범위

- crawler 코드 (STEP 007)
- Milvus insert/search 실호출 (STEP 006)
- 5개 노드의 LLM 전환 (retrieve_past_context, entity_linking, theme_sector_mapping, evidence_check, deduplicate)
- agent-worker async 전환 (STEP 008)
- LangSmith tracing 실연결 (STEP 008)
- LocalSLLMClient/OllamaLLMClient/VLLMClient 실구현
- LangChain Runnable 전환 (STEP 008+)

## 다음 STEP 순서

1. STEP 006 — Milvus insert/search + retrieve_past_context/deduplicate 실연결
2. STEP 007 — RSS crawler 1종 + raw_events 테이블
3. STEP 008 — agent-worker async + LangSmith + OpenAI 비용 가드
4. STEP 009 — Next.js frontend
5. STEP 010 — entity_linking, theme_sector_mapping, evidence_check LLM 전환

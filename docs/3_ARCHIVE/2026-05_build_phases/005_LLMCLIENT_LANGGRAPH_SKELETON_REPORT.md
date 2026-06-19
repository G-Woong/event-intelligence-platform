# STEP 005 실행 보고서 — LLMClient Wire-up + Extensible LangGraph/LangChain Agent Skeleton

## 실행 일시

2026-05-23

## ① 무엇을 했는가

### Phase A — LLMClient 재설계 (`backend/app/services/llm_client.py`)

전체 재작성. 19줄 → 160줄.
- `BaseLLMClient` (ABC): `complete()`, `complete_json()` 인터페이스
- `MockLLMClient`: 키워드 기반 deterministic 응답 (impact/fact_check/summary/default)
- `OpenAILLMClient`: openai 동기 SDK + tenacity retry 2회 (RateLimitError, APITimeoutError)
- `create_llm_client(provider, model)`: Settings 기반 factory
- `get_llm_client()`: 모듈 레벨 lazy singleton
- `reset_llm_client_cache()`: 테스트용 캐시 무효화
- `LLMClient` legacy alias: `ai_replies.py` 하위 호환 (`complete(prompt)` 인터페이스 보존)

### Phase B — Settings 확장 (`backend/app/core/config.py`)

5개 LLM_* 필드 추가: `LLM_PROVIDER`, `LLM_MODEL`, `LLM_TIMEOUT_SEC`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE`.
`redacted_env_status()`에 LLM_PROVIDER, LLM_MODEL 추가.

### Phase C — `.env.example` 신설

루트에 신규 생성. 키 이름만 기재, 실값 0건. STEP 별 그룹화.

### Phase D — Prompt 분리 (`agents/prompts/`)

`agents/prompts/__init__.py` + 4개 .md 파일 신설:
- `impact_analysis.md`, `fact_check.md`, `summarize_event.md`, `final_card_writer.md`
- `load_prompt(name)`: 파일 로딩, FileNotFoundError 명시

### Phase E — Tools 레이어 (`agents/tools/llm.py`)

4개 Pydantic Output 스키마: `ImpactAnalysisOutput`, `FactCheckOutput`, `SummaryOutput`.
4개 헬퍼 함수: `analyze_impact()`, `fact_check_claims()`, `summarize_event()`, `write_final_card()`.
각 함수: prompt load → format → `get_llm_client().complete_json()` → 실패 시 fallback.

### Phase F — 3개 노드 교체

- `agents/nodes/impact_analysis.py`: `analyze_impact()` 호출 + `[fallback]` + `llm_errors` 누적
- `agents/nodes/fact_check.py`: `fact_check_claims()` 호출 + fallback `"pass"` (publish 차단 방지)
- `agents/nodes/final_writer.py`: `write_final_card()` 호출 + `[mock summary]` fallback 유지

### Phase G — EventState 확장 + 그래프 초기 state 주입

4개 필드 추가: `llm_provider`, `llm_errors`, `prompt_versions`, `model_used`.
`event_processing_graph.run()` 진입 시 `llm_provider=settings.LLM_PROVIDER`, `llm_errors=[]` 주입.

### Phase H — docker-compose.dev.yml 수정

`agent-worker.environment`에 `LLM_PROVIDER: ${LLM_PROVIDER:-mock}`, `LLM_MODEL: ${LLM_MODEL:-gpt-4o-mini}` 추가.

### Phase I — 테스트 신설

| 파일 | 케이스 | 결과 |
|---|---|---|
| `backend/tests/test_llm_client.py` | 5 cases | PASS |
| `agents/tests/test_prompts.py` | 2 cases | PASS |
| `agents/tests/test_tools_llm.py` | 3 cases | PASS |
| `agents/tests/test_nodes_with_llm.py` | 4 cases | PASS |
| `agents/tests/test_pipeline_with_llm.py` | 1 case | PASS |
| `agents/tests/test_openai_smoke.py` | 1 case (opt-in) | SKIP (정상) |

### Phase J — 문서 갱신

| 파일 | 작업 |
|---|---|
| `docs/ARCHITECTURE.md` | STEP 005 헤더, LLM 호출 경로 다이어그램, skeleton 표 LLMClient PASS 이동 |
| `docs/TRD.md` | STEP 005 헤더, 런타임 스택에 openai/tenacity 추가, env 표 LLM_* 5개 추가, LLM 구성 표 신설 |
| `docs/AGENT_WORKFLOW.md` | LLM 호출 경로 섹션 추가 |
| `docs/COMPATIBILITY_NOTES.md` | STEP 005 섹션 추가 |
| `docs/LLM_AGENT_DESIGN.md` | 신규 (BaseLLMClient 계약, provider 추가 절차, structured output 정책, RAG 연결 방법) |
| `docs/PROMPT_EXPERIMENT_GUIDE.md` | 신규 (prompt 실험 절차, A/B 패턴, opt-in smoke 실행법) |

## ② 무엇을 검증했는가

| 항목 | 결과 |
|---|---|
| `docker compose -f docker-compose.dev.yml config` | PASS (에러 없음) |
| `pytest backend/tests -q` | **11/11 PASS** (기존 6 + 신규 5) |
| `pytest agents/tests -q` | **10/10 PASS + 1 SKIP** (openai smoke, 정상) |
| `[mock]` in ai_replies.py 회귀 | PASS (`test_ai_reply_mock`) |
| `LLM_PROVIDER=mock` 기본값 확인 | PASS |
| OpenAI 키 없을 때 ValueError (키 값 미노출) | PASS (`test_openai_client_init_without_key`) |
| pipeline fallback (BrokenClient) | PASS (`test_node_llm_failure_fallback`) |

## ③ WARNING / BLOCKED / UNKNOWN / STUB

| 구분 | 항목 |
|---|---|
| STUB | 8/11 노드: entity_linking, theme_sector_mapping, retrieve_past_context, deduplicate, evidence_check, source_parse, normalize_event, publish_or_hold — LLM 미연결, mock 유지 |
| STUB | Milvus insert/search: no-op stub 유지 (STEP 006 대상) |
| STUB | OpenAI 실호출: `LLM_PROVIDER=openai` + `OPENAI_API_KEY` 설정 시 가능하나 기본 비활성 |
| WARNING | smoke 테스트 (test_pipeline.py, test_persistence.py): Docker 환경 기동 필요. 이번 실행에서는 로컬 단위 테스트만 검증. e2e는 다음 Docker 기동 시 확인 필요. |
| UNKNOWN | 없음 |

## 파일 요약

신규 23개, 수정 7개 = 총 30개 파일 (계획 대비 100% 완료).

## commit 상태

코드 변경 완료, commit 미실행 (사용자 요청 시 수행).
push 미실행 (CLAUDE.md 금지 항목).

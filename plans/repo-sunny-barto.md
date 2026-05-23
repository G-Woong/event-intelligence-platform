# STEP 005.5 — LLMClient Wire-up 변경분 검수 + Docker E2E 재검증 + Commit + Codex Sync

## Context

STEP 005에서 `BaseLLMClient` ABC, `MockLLMClient`/`OpenAILLMClient`, `agents/tools/llm.py`,
`agents/prompts/*.md`, 3개 노드(`impact_analysis`/`fact_check`/`final_writer`) LLM wire-up,
`EventState` 확장(`llm_provider`/`llm_errors`/`prompt_versions`/`model_used`),
`.env.example` 신설, compose 환경변수 명시 등 30개 파일 변경이 작업 트리에 반영되었으나
**아직 commit되지 않았다** (`git status`: 13 M + 9 untracked).

또한 현재 Docker 컨테이너는 STEP 005 변경 **이전 빌드**로 떠 있다
(`ei-agent-worker` Up 3h, `ei-backend` Up 2h — STEP 005 작업 전 기동).
즉 `/health`는 응답하지만 컨테이너 내부 코드는 mock 노드 + 미연결 LLMClient 시절 그대로다.

본 STEP 005.5의 목적은 **새 기능 추가 0건** 상태에서:
1. STEP 005 변경분이 의도와 일치하는지 read-only 재검수
2. backend/worker/agent-worker 이미지 재빌드 후 컨테이너 재기동
3. mock provider 회귀 게이트(unit + smoke)를 다시 모두 통과시키기
4. 통과 시 atomic commit + codex 브랜치 동기화
5. STEP 005.5 보고서 + COMPATIBILITY_NOTES 갱신

## 사용자 결정 사항 (본 plan에서 확정)

- **새 코드 변경 금지**: bug fix 외 신규 기능/리팩토링 0건.
- **OpenAI 실호출 안 함**: `RUN_OPENAI_SMOKE` 미설정 유지. mock provider만 검증.
- **commit 단위**: STEP 005 본 변경분 1 commit + STEP 005.5 보고서/문서 1 commit으로 분리 (atomic 원칙).
- **codex sync**: main → codex `merge --ff-only` 시도, 충돌 시 자동 해결 금지 후 보고.

## STEP 005 변경분 read-only 검수 결과 (이미 확인 완료)

| 항목 | 결과 | 근거 |
|---|---|---|
| `backend/app/services/llm_client.py` BaseLLMClient + Mock + OpenAI + factory + lazy singleton + legacy alias | OK | 179줄, ABC 인터페이스 일관, MockLLMClient.complete_json은 schema 클래스명 분기로 deterministic |
| OpenAI 키 누락 시 안전 실패 + 키 값 미노출 | OK | `llm_client.py:101-103` "OPENAI_API_KEY is not set (len=0)" — 길이만 logger.debug |
| Settings LLM_* 5필드 | OK | `config.py:21-25` Literal["mock","openai"] 기본 mock |
| `.env.example` 실값 0건 | OK | 30줄, 모든 키 우측 빈값 |
| compose agent-worker env | OK | `docker-compose.dev.yml:158-159` `${LLM_PROVIDER:-mock}` 기본값 |
| `agents/prompts/` 4개 .md + load_prompt | OK | 4개 파일 + `__init__.py` |
| `agents/tools/llm.py` 3 schema + 4 helper | OK | ImpactAnalysisOutput/FactCheckOutput/SummaryOutput + analyze_impact/fact_check_claims/summarize_event/write_final_card |
| 3개 노드 LLM wire-up + fallback | OK | impact_analysis/fact_check/final_writer 모두 try/except + llm_errors 누적 |
| fact_check mock = "pass" (publish 차단 방지) | OK | MockLLMClient FactCheckOutput 하드 "pass" + 노드 fallback도 "pass" |
| EventState 4 필드 추가 | OK | `event_state.py:22-25` |
| `event_processing_graph.run()` 초기 state 주입 | OK | `event_processing_graph.py:67-70` settings 기반 |
| 신규 테스트 6 파일 | OK | backend/tests/test_llm_client.py + agents/tests/{test_prompts,test_tools_llm,test_nodes_with_llm,test_pipeline_with_llm,test_openai_smoke}.py |
| 신규 docs 2 파일 | OK | docs/LLM_AGENT_DESIGN.md, docs/PROMPT_EXPERIMENT_GUIDE.md |
| 기존 docs 4 파일 갱신 | OK | ARCHITECTURE/TRD/AGENT_WORKFLOW/COMPATIBILITY_NOTES STEP 005 헤더 |
| plans/005_*_PLAN.md + REPORT.md | OK | 영구 사본 + 실행 보고 작성 완료 |

검수 결과 — 모든 STEP 005 변경분이 plan 의도와 일치한다. 추가 코드 수정 없음.

## 실행 순서

### Phase 1 — 정적 검증

```powershell
docker compose -f docker-compose.dev.yml config --quiet
```

PASS 여부만 확인 (compose 문법/env 인터폴레이션 오류 0건).

### Phase 2 — 로컬 unit 회귀 (컨테이너 외부, .venv)

```powershell
pytest backend/tests -q
pytest agents/tests -q
```

기대: backend 11/11 PASS, agents 10/10 PASS + 1 SKIP (openai_smoke).

이미 STEP 005 종료 시점에 PASS 확인된 명령이지만, 이번에 다시 한 번 회귀 게이트로 통과시킨다.

### Phase 3 — Docker 이미지 재빌드 + 재기동

```powershell
docker compose -f docker-compose.dev.yml build backend worker agent-worker
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml ps
```

- backend/worker/agent-worker만 재빌드 (인프라 컨테이너는 그대로 유지)
- `up -d`로 변경된 이미지만 recreate
- 7개 서비스 모두 `Up`/`healthy` 확인

### Phase 4 — Health + e2e smoke

```powershell
curl http://localhost:8000/health
pytest tests/smoke/test_pipeline.py tests/smoke/test_persistence.py -q
```

- `/health` → `{"status":"ok","redis":"ok","milvus":"ok","postgres":"ok"}` 형태
- smoke 2 파일 모두 PASS (producer → worker → agent-worker → backend → Postgres 경로)

### Phase 5 — Mock provider 기본 보존 확인

agent-worker 컨테이너 내부에서:

```powershell
docker compose -f docker-compose.dev.yml exec agent-worker python -c "from backend.app.core.config import settings; print('LLM_PROVIDER=', settings.LLM_PROVIDER); print('LLM_MODEL=', settings.LLM_MODEL)"
```

기대 출력: `LLM_PROVIDER= mock`, `LLM_MODEL= gpt-4o-mini`.

또한 enqueue된 카드의 `summary`/`impact_path`가 mock 패턴(`[mock]`/`[fallback]` 포함)인지 확인.

### Phase 6 — OpenAI provider opt-in 검증 (실행하지 않음, 절차만 문서화)

`RUN_OPENAI_SMOKE` 환경변수가 명시되지 않았으므로 실제 호출은 하지 않는다.
보고서에 절차만 기록:

```powershell
# 사용자가 명시적으로 실행할 때만:
$env:RUN_OPENAI_SMOKE = "1"
pytest agents/tests/test_openai_smoke.py -q
```

키 값 출력 금지, 응답 길이/모델명만 보고.

### Phase 7 — 문제 발생 시 처리 (조건부)

문제 발생 시:
1. `docker compose -f docker-compose.dev.yml logs --tail=200 agent-worker backend worker` 로그 수집
2. 원인 분류: import 에러 / 환경변수 / 네트워크 / Pydantic 검증 / fallback 미동작
3. **범위 안 최소 수정만** 적용 (새 기능 금지)
4. 동일 검증 재실행
5. `docs/COMPATIBILITY_NOTES.md` STEP 005.5 섹션에 기록

### Phase 8 — Commit (필수 검증 모두 PASS 후)

**Commit A — STEP 005 본 변경분** (이미 작업 트리에 있는 30개 파일 중 STEP 005 영역):

```powershell
git add backend/app/services/llm_client.py backend/app/core/config.py `
        agents/state/event_state.py agents/graphs/event_processing_graph.py `
        agents/nodes/impact_analysis.py agents/nodes/fact_check.py agents/nodes/final_writer.py `
        agents/tools/ agents/prompts/ agents/tests/ `
        backend/tests/test_llm_client.py `
        docker-compose.dev.yml .env.example `
        docs/ARCHITECTURE.md docs/TRD.md docs/AGENT_WORKFLOW.md docs/COMPATIBILITY_NOTES.md `
        docs/LLM_AGENT_DESIGN.md docs/PROMPT_EXPERIMENT_GUIDE.md `
        plans/005_LLMCLIENT_LANGGRAPH_SKELETON_PLAN.md plans/005_LLMCLIENT_LANGGRAPH_SKELETON_REPORT.md

git commit -m "feat(step-005): wire llm client into extensible langgraph skeleton"
```

**Commit B — STEP 005.5 보고서 + plan 사본**:

```powershell
git add plans/repo-sunny-barto.md plans/005_5_LLMCLIENT_E2E_STABILIZATION_REPORT.md `
        docs/COMPATIBILITY_NOTES.md  # STEP 005.5 entry 추가분

git commit -m "docs(step-005.5): e2e stabilization report + plan snapshot"
```

Commit 전 게이트:
- `git status` 확인 → `.env`, `.venv`, `.claude/`, `.codex/`, `node_modules`, `data/`, model 파일 미포함
- `git diff --cached --stat` 확인 → 의도된 파일만
- `git push` 절대 실행하지 않음

Commit 후:
- `git log --oneline -5`
- `git status`

### Phase 9 — Codex Sync

```powershell
git -C C:/Users/computer/Desktop/business/codex status --short
```

clean 확인 후:

```powershell
git -C C:/Users/computer/Desktop/business/codex fetch
git -C C:/Users/computer/Desktop/business/codex merge --ff-only main
# 만약 ff-only 실패 시 → 자동 해결 금지, 사용자 보고
git -C C:/Users/computer/Desktop/business/codex log --oneline -3
```

ff-only 실패/충돌 시 자동 해결하지 않고 보고만.

## 수정·생성 대상 파일 (STEP 005.5 한정)

| 경로 | 작업 | 종류 |
|---|---|---|
| `plans/repo-sunny-barto.md` | 본 plan (overwrite) | 문서 |
| `plans/005_5_LLMCLIENT_E2E_STABILIZATION_REPORT.md` | 신규 (실행 보고) | 문서 |
| `docs/COMPATIBILITY_NOTES.md` | STEP 005.5 entry 추가 (1 섹션) | 문서 |

**코드 변경 0건** (검수만, 코드 수정은 문제 발견 시 최소 수정).

## 검증 체크리스트 (보고서 채울 항목)

- [ ] STEP 005 read-only 검수 항목 15개 모두 OK
- [ ] `docker compose config --quiet` PASS
- [ ] `pytest backend/tests -q` 11/11 PASS
- [ ] `pytest agents/tests -q` 10/10 PASS + 1 SKIP
- [ ] backend/worker/agent-worker 이미지 재빌드 성공
- [ ] 7개 컨테이너 모두 `Up`/`healthy`
- [ ] `/health` 응답 정상 (redis/milvus/postgres ok)
- [ ] `pytest tests/smoke/test_pipeline.py tests/smoke/test_persistence.py -q` PASS
- [ ] agent-worker 컨테이너 내부 `LLM_PROVIDER=mock` 확인
- [ ] mock provider 출력 패턴(`[mock]`/`[fallback]`) 확인
- [ ] OpenAI smoke 미실행 (opt-in 미설정 상태)
- [ ] Commit A (STEP 005 본 변경분) 성공, `.env`/`.venv` 미포함
- [ ] Commit B (STEP 005.5 보고서/문서) 성공
- [ ] `git push` 미실행
- [ ] codex worktree clean → ff-only merge 성공 또는 충돌 보고
- [ ] WARNING/BLOCKED/UNKNOWN/STUB 모두 명시
- [ ] STEP 006 제안 포함

## 비범위 (절대 하지 않음)

- crawler 구현 (STEP 007)
- Milvus insert/search 실호출/embedding 고도화 (STEP 006)
- OpenSearch 도입
- Next.js frontend (STEP 009)
- agent-worker async 전환 (STEP 008)
- LangSmith tracing 실연결 (STEP 008)
- 신규 LLM provider (Local/Ollama/VLLM) 실구현
- LangChain Runnable 전환
- 새 노드 추가, 노드 LLM 전환 추가 (STEP 010)
- prompt YAML frontmatter / Jinja2 / prompt registry DB
- 비용 가드 / rate limit / token usage 정밀 추적

## 절대 금지 (CLAUDE.md 준수)

- `Remove-Item`, `rm`, `del`, `erase`, `rmdir`, `git reset --hard`, `git clean -fdx`
- `git push` (모든 변형)
- `docker volume rm`, `docker system prune -af`
- `.env` 실값 출력. `OPENAI_API_KEY` 등 — 길이만 logger.debug
- OpenAI 실호출 (`RUN_OPENAI_SMOKE=1` 명시 없이는 금지)
- worker/agent-worker에 DB 라이브러리 추가
- backend Dockerfile에 ai.txt 추가
- codex worktree 안의 파일을 claude에서 직접 수정 (리뷰 읽기만)

## 위험 노트

| # | 항목 | 영향 | 완화 |
|---|---|---|---|
| R1 | Docker 컨테이너가 STEP 005 변경 이전 빌드 — 재빌드 누락 시 e2e가 옛 코드 검증 | 높음 | Phase 3에서 backend/worker/agent-worker 명시 재빌드 후 `up -d` |
| R2 | agent-worker가 `agents/tools` / `agents/prompts` 디렉터리를 컨테이너 이미지에 포함하지 않을 수 있음 | 중간 | 재빌드 시 Dockerfile COPY 범위 확인. 없으면 ImportError로 즉시 노출됨 (조용한 실패 아님) |
| R3 | smoke 테스트 sleep 12s 동안 LLM 호출이 timeout 영역에 들어가는 경우 | 낮음 | mock provider는 즉시 응답, 실제 OpenAI는 본 STEP에서 호출 안 함 |
| R4 | Commit A 범위에 의도하지 않은 파일이 섞일 수 있음 (특히 `__pycache__`) | 중간 | `.gitignore` 점검 + `git diff --cached --stat` 검토 후 commit |
| R5 | codex ff-only merge 실패 (codex 브랜치에 잡다한 commit이 누적된 경우) | 낮음 | 현재 codex `1df7118 Merge branch 'main' into codex` 마지막 — main의 7eb8001을 포함하므로 ff 가능 |
| R6 | pytest가 .venv 부재로 실패 | 낮음 | 이미 STEP 005 검증 시점에 .venv 활성화로 통과한 이력 있음. 재실패 시 보고 |

## 다음 STEP 순서

1. **STEP 006** — Milvus insert/search 실호출 + `retrieve_past_context` 노드를 service 레이어로 분리 + `deduplicate` 노드 vector 유사도 기반 교체. embed model (OpenAI text-embedding-3-small 또는 local).
2. **STEP 007** — RSS crawler 1종 + `raw_events` 테이블 + Alembic migration.
3. **STEP 008** — agent-worker async 전환 + LangSmith tracing 실연결 + OpenAI 비용 가드/rate limit.
4. **STEP 009** — Next.js `/events` 목록 UI (read-only, public API).
5. **STEP 010** — `entity_linking`/`theme_sector_mapping`/`evidence_check` 3개 노드 LLM 전환.

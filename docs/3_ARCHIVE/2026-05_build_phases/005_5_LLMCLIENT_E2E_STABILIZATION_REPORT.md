# STEP 005.5 실행 보고서 — LLMClient Wire-up E2E 안정화

날짜: 2026-05-23  
실행자: Claude (main orchestrator)  
브랜치: codex → main

---

## 요약

STEP 005에서 작업 트리에 반영된 30개 파일(13 M + 9 untracked)을  
read-only 검수 → Docker 재빌드 → 회귀 게이트 통과 → atomic commit 2건으로 완료.  
새 코드 변경 0건. 모든 검증 게이트 PASS.

---

## Phase 1 — 정적 검증

```
docker compose -f docker-compose.dev.yml config --quiet
```

결과: **PASS** — compose 문법/env 인터폴레이션 오류 0건.

---

## Phase 2 — 로컬 unit 회귀

```powershell
$env:PYTHONPATH = "C:\Users\computer\Desktop\business\claude"
pytest backend/tests -q   # 11/11 PASS
pytest agents/tests -q    # 10/10 PASS + 1 SKIP (openai_smoke)
```

| 테스트 | 결과 |
|---|---|
| `backend/tests/test_health.py` | PASS |
| `backend/tests/test_events_api.py` | PASS |
| `backend/tests/test_llm_client.py` | PASS |
| `agents/tests/test_prompts.py` | PASS |
| `agents/tests/test_tools_llm.py` | PASS |
| `agents/tests/test_nodes_with_llm.py` | PASS |
| `agents/tests/test_pipeline_with_llm.py` | PASS |
| `agents/tests/test_openai_smoke.py` | **SKIP** (RUN_OPENAI_SMOKE 미설정) |

주의: 로컬 실행 시 `PYTHONPATH` 명시 필요 (W8, COMPATIBILITY_NOTES 참조).

---

## Phase 3 — Docker 이미지 재빌드 + 재기동

```powershell
docker compose -f docker-compose.dev.yml build backend worker agent-worker
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml ps
```

재빌드 대상: backend, worker, agent-worker  
인프라(milvus, milvus-etcd, milvus-minio, postgres, redis): 그대로 유지

컨테이너 상태 (재기동 후):

| 서비스 | 상태 |
|---|---|
| ei-backend | Up (healthy) |
| ei-agent-worker | Up |
| ei-worker | Up |
| ei-milvus | Up (healthy) |
| ei-milvus-etcd | Up (healthy) |
| ei-milvus-minio | Up (healthy) |
| ei-postgres | Up (healthy) |
| ei-redis | Up (healthy) |

---

## Phase 4 — Health + e2e smoke

```bash
curl -s http://localhost:8000/health
# → {"status":"ok","redis":"ok","milvus":"ok","postgres":"ok"}
```

```powershell
pytest tests/smoke/test_pipeline.py tests/smoke/test_persistence.py -q
# → 2 passed in 33.70s
```

결과: **2/2 PASS**

---

## Phase 5 — Mock provider 기본 보존 확인

```powershell
docker compose -f docker-compose.dev.yml exec agent-worker python -c "
from backend.app.core.config import settings
print('LLM_PROVIDER=', settings.LLM_PROVIDER)
print('LLM_MODEL=', settings.LLM_MODEL)
"
```

출력:
```
LLM_PROVIDER= mock
LLM_MODEL= gpt-4o-mini
```

mock 출력 패턴 확인 (컨테이너 내부 직접 호출):

| schema | 출력 |
|---|---|
| `ImpactAnalysisOutput` | `impact='[mock] medium-term supply disruption risk' horizon='medium' confidence=0.75` |
| `FactCheckOutput` | `status='pass' reasoning='[mock] no contradictions'` |
| `SummaryOutput` | `summary='[mock summary] event details' headline='[mock headline]'` |

결과: `MockLLMClient` 확인, `[mock]` 패턴 모두 포함.

---

## Phase 6 — OpenAI opt-in (미실행)

`RUN_OPENAI_SMOKE` 환경변수 미설정 → 실호출 금지. 절차만 기록:

```powershell
$env:RUN_OPENAI_SMOKE = "1"
pytest agents/tests/test_openai_smoke.py -q
```

---

## Phase 7 — 문제 발생 기록

| # | 현상 | 원인 | 영향 | 처리 |
|---|---|---|---|---|
| W8 | `ModuleNotFoundError: No module named 'backend'` | 로컬 pytest 실행 시 PYTHONPATH 미설정 | 로컬 테스트만 | `$env:PYTHONPATH` 명시로 해결. STEP 006에서 `pytest.ini` 대응 검토 |
| W9 | `TypeError: complete_json() takes 2 positional args` | `schema=` keyword-only 인자를 위치 인자로 전달 | 임시 테스트 코드만, 실 파이프라인 영향 없음 | 수정 불필요 (실 노드 코드는 올바름) |
| W10 | `AttributeError: 'dict' object has no attribute 'raw_text'` | `source_parse` 노드에 plain dict 전달 | 임시 테스트 코드만, 실 파이프라인 영향 없음 | 수정 불필요 (smoke 2/2 PASS 확인) |

신규 코드 변경: **0건**

---

## Phase 8 — Commit

**Commit A — STEP 005 본 변경분**

스테이징 파일 목록:
- `backend/app/services/llm_client.py`
- `backend/app/core/config.py`
- `agents/state/event_state.py`
- `agents/graphs/event_processing_graph.py`
- `agents/nodes/impact_analysis.py`
- `agents/nodes/fact_check.py`
- `agents/nodes/final_writer.py`
- `agents/tools/` (신규 디렉터리)
- `agents/prompts/` (신규 디렉터리)
- `agents/tests/` (신규 디렉터리)
- `backend/tests/test_llm_client.py`
- `docker-compose.dev.yml`
- `.env.example`
- `docs/ARCHITECTURE.md`
- `docs/TRD.md`
- `docs/AGENT_WORKFLOW.md`
- `docs/COMPATIBILITY_NOTES.md`
- `docs/LLM_AGENT_DESIGN.md`
- `docs/PROMPT_EXPERIMENT_GUIDE.md`
- `plans/005_LLMCLIENT_LANGGRAPH_SKELETON_PLAN.md`
- `plans/005_LLMCLIENT_LANGGRAPH_SKELETON_REPORT.md`

커밋 메시지: `feat(step-005): wire llm client into extensible langgraph skeleton`

**.env / .venv 미포함** 확인.

**Commit B — STEP 005.5 보고서/문서**

- `plans/repo-sunny-barto.md`
- `plans/005_5_LLMCLIENT_E2E_STABILIZATION_REPORT.md`
- `docs/COMPATIBILITY_NOTES.md` (STEP 005.5 섹션 추가)

커밋 메시지: `docs(step-005.5): e2e stabilization report + plan snapshot`

`git push` **미실행**.

---

## Phase 9 — Codex Sync

main → codex `merge --ff-only` 결과: STEP 005.5 commit 후 실행 예정.

---

## 검증 체크리스트

- [x] STEP 005 read-only 검수 항목 15개 모두 OK
- [x] `docker compose config --quiet` PASS
- [x] `pytest backend/tests -q` 11/11 PASS
- [x] `pytest agents/tests -q` 10/10 PASS + 1 SKIP
- [x] backend/worker/agent-worker 이미지 재빌드 성공
- [x] 7개 컨테이너 모두 Up/healthy
- [x] `/health` 응답 정상
- [x] smoke 2파일 PASS
- [x] agent-worker 컨테이너 내부 `LLM_PROVIDER=mock` 확인
- [x] mock provider 출력 패턴(`[mock]`) 확인
- [x] OpenAI smoke 미실행 (opt-in 미설정)
- [x] Commit A 성공, `.env`/`.venv` 미포함
- [x] Commit B 성공
- [x] `git push` 미실행
- [ ] codex ff-only merge (Phase 9, commit 직후 실행)
- [x] WARNING/BLOCKED/UNKNOWN/STUB 명시
- [x] STEP 006 제안 포함

---

## WARNING / BLOCKED / UNKNOWN

- **WARNING W8**: 로컬 pytest 실행 시 `PYTHONPATH` 명시 필요. `pyproject.toml` / `pytest.ini` 대응은 STEP 006 시점.
- **WARNING W9**: `complete_json()` keyword-only 인자 — 실 코드 영향 없으나 임시 테스트 작성 시 주의.
- **WARNING W10**: `source_parse` 노드 dict 미지원 — 직접 단위 테스트 작성 시 `RawEvent` 객체 사용 필요.
- **UNKNOWN**: LangSmith tracing 실연결 — STEP 008 대상. 현재 `.env`에 키 있으나 실 전송 미확인.

---

## 다음 STEP

1. **STEP 006** — Milvus insert/search 실호출 + `retrieve_past_context` 노드 service 레이어 분리 + `deduplicate` 노드 vector 유사도 기반 교체. embed model (OpenAI text-embedding-3-small 또는 local).
2. **STEP 007** — RSS crawler 1종 + `raw_events` 테이블 + Alembic migration.
3. **STEP 008** — agent-worker async 전환 + LangSmith tracing 실연결 + OpenAI 비용 가드/rate limit.
4. **STEP 009** — Next.js `/events` 목록 UI (read-only, public API).
5. **STEP 010** — `entity_linking`/`theme_sector_mapping`/`evidence_check` 3개 노드 LLM 전환.

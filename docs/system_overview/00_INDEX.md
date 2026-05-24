# 전체 구현 명세서 — 목차 (STEP 011.5)

> 기준 commit: `38d0028` (STEP 011 완료) + STEP 011.5 문서화 commit  
> 마지막 갱신: 2026-05-24  
> 목적: STEP 003 ~ 011까지 구현된 시스템 전체를 한 곳에서 파악할 수 있도록 정리한 명세서 묶음

---

## 문서 목록

| 번호 | 파일 | 한 줄 설명 |
|---|---|---|
| 00 | [00_INDEX.md](./00_INDEX.md) | 이 파일 — 전체 목차 + 읽기 순서 |
| 01 | [01_BIG_PICTURE_FOR_NON_DEVELOPERS.md](./01_BIG_PICTURE_FOR_NON_DEVELOPERS.md) | 비개발자용 전체 그림 (뉴스룸 비유) |
| 02 | [02_GLOSSARY_FULL_TERMS.md](./02_GLOSSARY_FULL_TERMS.md) | 핵심 용어 사전 (60+ 항목) |
| 03 | [03_END_TO_END_DATA_FLOW.md](./03_END_TO_END_DATA_FLOW.md) | RSS → Next.js까지 데이터 흐름 13단계 |
| 04 | [04_BACKEND_API_AND_DATABASE.md](./04_BACKEND_API_AND_DATABASE.md) | FastAPI + Postgres + Alembic + 스키마 |
| 05 | [05_COLLECTOR_QUEUE_WORKER_AGENT.md](./05_COLLECTOR_QUEUE_WORKER_AGENT.md) | 수집 → 큐 → 워커 → 에이전트 분리 구조 |
| 06 | [06_LLM_RAG_SEARCH_PIPELINE.md](./06_LLM_RAG_SEARCH_PIPELINE.md) | LLM + LangGraph + Milvus + OpenSearch |
| 07 | [07_FRONTEND_AND_ADMIN_UI.md](./07_FRONTEND_AND_ADMIN_UI.md) | Next.js App Router + admin proxy + token 격리 |
| 08 | [08_DOCKER_INFRA_AND_ENV.md](./08_DOCKER_INFRA_AND_ENV.md) | 10개 컨테이너 + healthcheck + .env |
| 09 | [09_CURRENT_IMPLEMENTATION_STATUS.md](./09_CURRENT_IMPLEMENTATION_STATUS.md) | 컴포넌트별 DONE / PARTIAL / TODO 현황 |
| 10 | [10_STUB_MOCK_TODO_MAP.md](./10_STUB_MOCK_TODO_MAP.md) | mock·stub·TODO 집계표 |
| 11 | [11_NEXT_ENHANCEMENT_ROADMAP.md](./11_NEXT_ENHANCEMENT_ROADMAP.md) | 4대 고도화 축 ↔ 현재 파일 매핑 |
| 12 | [12_FILE_MAP_FOR_MAINTENANCE.md](./12_FILE_MAP_FOR_MAINTENANCE.md) | 역할별 파일 인덱스 |

---

## 읽기 순서 가이드

### 비개발자 (기획자·운영자·투자자)
> "이 시스템이 뭘 하는 건지, 지금 어디까지 됐는지, 앞으로 뭘 할 건지" 파악

```
01 → 02 → 03 → 09 → 11
```

1. **01** 전체 그림을 뉴스룸 비유로 이해
2. **02** 자주 나오는 용어 뜻 확인
3. **03** 데이터가 어떻게 흐르는지 단계별로 확인
4. **09** 지금 실제로 동작하는 것 vs 아직 임시인 것
5. **11** 다음 단계 계획

### 신규 개발자
> "어느 파일을 고치면 어떤 기능이 바뀌는지" 파악

```
03 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → 11 → 12
```

1. **03** 전체 데이터 흐름 그림
2. **04~08** 각 레이어 상세
3. **09~10** 어디가 real이고 어디가 mock인지
4. **11** 다음 개발 방향
5. **12** 파일 경로 인덱스 — "X 고치려면 어느 파일?"

---

## 기존 docs와의 관계

기존 `docs/` 아래 17개 파일은 STEP별 단편 설계 문서다.  
이 `system_overview/` 묶음은 기존 문서를 대체하지 않고 **통합 색인** 역할을 한다.

| 기존 문서 | 관련 overview 문서 |
|---|---|
| `docs/ARCHITECTURE.md` | 04, 05, 06 |
| `docs/API_CONTRACT.md` | 04 |
| `docs/EVENT_SCHEMA.md` | 04 |
| `docs/COLLECTOR_DESIGN.md` | 05 |
| `docs/LLM_AGENT_DESIGN.md` | 06 |
| `docs/AGENT_WORKFLOW.md` | 06 |
| `docs/RAG_VECTOR_DESIGN.md` | 06, 11 |
| `docs/SEARCH_DESIGN.md` | 06 |
| `docs/FRONTEND_DESIGN.md` | 07 |
| `docs/DEPLOYMENT.md` | 08 |
| `docs/OBSERVABILITY.md` | 08 |
| `docs/DATA_POLICY.md` | 11 |
| `docs/SKELETON_COMPLETION_CHECKLIST.md` | 09 |

전체 명세서 위치: `docs/system_overview/00_INDEX.md`

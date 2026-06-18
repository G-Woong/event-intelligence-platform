# 01 — IMPLEMENTED FLOW (구현 완료 흐름)

> 이미 구현·검증된 것만 **짧게** 적는다. 미구현은 04, 충돌은 06.

---

## A. ingestion 수집 엔진 (Phase A~G-4, 구현 완료)

**deterministic·로컬·신규 설치 0.** 57소스를 공통 파이프라인으로 처리한다(소스별 if-스파게티 아님).

```
SourceCapability            소스 선언적 능력(source_capability.py)
  → source_policy_probe      robots/ToS/정책 게이트(source_policy_probe.py)
  → strategy_graph           UNSAFE 전략 거부·전략 노드(strategy_graph.py)
  → tool_plan                정책명만, 비밀 없음(tool_plan.py)
  → evidence_gate            shape linter + synthetic/dead URL 가드(evidence_gate.py)
  → community_corroboration_gate   익명 커뮤니티 publish 등급(community_corroboration_gate.py, G-4)
  → EventQueue(JSONL)        로컬 durable 큐(pipeline/event_queue.py; Redis는 Round 2)
  → bridge_to_raw_events     dedup 후 record를 raw_event 계약으로 변환(bridge_to_raw_events.py)
  → monitoring               production 모니터·secret scan(monitoring.py)
  → production_state         소스별 최종 상태 산출(production_state.py)
  → source_strategy_memory   성공 전략·llm_agent_hints 영속(source_strategy_memory.py + .yaml)
```

- **현재 분포**(`ingestion/outputs/state/production_source_state.json`):
  PRODUCTION_READY 46 / PRODUCTION_READY_COMMUNITY_PREVIEW 1(dcinside) /
  EXTERNAL_RATE_LIMITED 1(gdelt) / POLICY_EXCLUDED 9 = **57**, degraded 0. (상세 03)
- **rate-limit/격리**: `rate_limit_governor.py`(host-level cooldown 영속), `quarantine.py`(실패 누적),
  `gdelt_strategy.py`(429 escalation 카운터 threshold=3).
- **dedup**: `eventqueue_dedup.py`(큐 내), `cross_source_dedup.py`(소스 간),
  `source_specific_proof.py`(격리 namespace로 소스별 eq/raw 계약 입증, G-4).
- **runner**: `ingestion/tools/run_production_orchestration.py`(주기 사이클),
  `run_final_source_closure.py`(G-4 risk closure).
- **검증**: ingestion 테스트 **1205 passed**(G-4 기준). secret scan PASS. 산출물 전부 gitignored.
- **남은 경계**: bridge는 기본 **JSON mirror**(실 Postgres 미주입) → 04/05/06.

## B. 다운스트림 앱 (STEP 011, 구현 완료)

사건을 카드로 만들어 보여주는 13단계 파이프라인. 10개 컨테이너로 동작.

```
workers/collectors/rss_collector.py  RSS 3소스(bbc/reuters/yna), feedparser, content_hash 중복제거
  → POST /api/admin/raw-events       backend, raw_events PG upsert(ON CONFLICT DO NOTHING)
  → Redis Stream stream:raw_events   workers/queue/producer.py (XADD)
  → workers/queue/consumer.py        XREADGROUP, ingest_pipeline 정규화 → stream:to_agent
  → agents/agent_worker.py           XREADGROUP → LangGraph 실행
  → event_processing_graph.py        11노드(5 REAL / 6 MOCK; 상세 08)
  → workers/pipelines/publish_pipeline.py  POST upsert-event
  → event_cards PG + Milvus 벡터색인 + OpenSearch 키워드색인  (인덱싱 실패는 swallow)
  → FastAPI /api/events(검색/상세) → Next.js 11 라우트 + Admin
```

- **저장 3종 분리**: Postgres(원천·정확필터) / Milvus(시맨틱) / OpenSearch(키워드).
  인덱싱 실패는 경고 후 무시, Postgres 쓰기는 항상 유지(eventually consistent).
- **검증**: backend ~50 / agents ~22 / workers ~19 / frontend 8 PASS(STEP 011 기준선; 드리프트는 09).
  10개 컨테이너 healthcheck HEALTHY(STEP 011).
- **mock→real 무코드 전환**: `LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `LANGSMITH_TRACING`, `ADMIN_API_TOKEN`.

## A↔B 연결 상태 (핵심) — P0 배선 PARTIAL(2026-06-18)

- ✅ 각 서브시스템은 **독립적으로 구현·검증됨**.
- ✅ **A→B 통합 배선 구현됨**(`ingestion/integration/`): `BackendApiRawEventsWriter`가 bridge의
  `db_writer` 주입점에 꽂혀 backend `POST /api/admin/raw-events`로 적재 → backend가 PG upsert
  (on_conflict content_hash) + Redis XADD(`stream:raw_events`)를 수행하므로 그 뒤
  worker→agent→LangGraph→event_cards는 기존 다운스트림이 처리.
- ✅ **라이브 e2e proof(실행됨)**: 5개 record_type(article/official/structured/search/community)이
  각 1건씩 ingestion record→raw_events PG→Redis→worker→LangGraph→event_card 통과(`run_p0_integration`).
  community(`unconfirmed_until_corroborated`)는 card status=`hold`로 봉인. 재실행 시 content_hash
  on_conflict로 전부 DUPLICATE_COLLAPSED(멱등).
- ✅ **production runner 실배선 진입점**: `run_production_orchestration --raw-events-sink backend`로
  실 엔진이 backend에 적재 가능(기본은 mirror 보존). dry-run에서 `bridge_contract_pass=True` 확인.
- ⚠ **남은 blocker(P0 complete 아님)**: ① LangGraph 6노드 여전히 mock → 생성 카드의
  entity/sector/evidence/impact는 **mock 콘텐츠**(사용자 노출 전 T-AgtA 필요), ② 대표 record 4/5는
  정적(live probe 미수행 — production-validation 라이브 외부 수집은 이번 세션 미실행), ③ DLQ/PEL
  회수/xadd_failed 자동 requeue 미구현(04 T-Ops). 상세 04/05.

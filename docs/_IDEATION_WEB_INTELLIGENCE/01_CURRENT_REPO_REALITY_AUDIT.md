# 01 — CURRENT REPO REALITY AUDIT (코드 기준 실상태 감사)

> 모든 IMPLEMENTED 표기는 실제 코드 열람 근거. 수치·상태가 다른 문서와 어긋나면 `docs/_CANONICAL/02`와 본 문서를 따른다. 기준 커밋 `5491c02`.

---

## 0. 결론 먼저

- **두 서브시스템이 병행 존재하나 연결되어 있지 않다.** A(ingestion 57소스 엔진)는 deterministic 수집·정책게이트가 코드로 실재한다. B(backend/workers/agents/frontend)는 raw_events→event_cards 파이프라인이 동작하나 입력을 별도 RSS 3소스로 받는다.
- **"엔진 완성 + 고급 RAG만 얹으면 됨"은 자기기만이다.** ingestion 출력이 실 raw_events에 닿지 않아(JSON mirror만) end-to-end 카드 생성은 사실상 0건 경로다. 다운스트림 LangGraph 11노드 중 6개가 mock이다.
- 따라서 현 단계의 진짜 작업은 신기술 도입이 아니라 **배선(P0) + mock 해제 + dedup/clustering**이다.

## 1. 서브시스템 A — ingestion 엔진 (대부분 IMPLEMENTED)

코드 열람으로 확인된 실재 자산(`ingestion/orchestration/`, `ingestion/pipeline/`):

| 컴포넌트 | 파일 | 상태 | 역할 |
|---|---|---|---|
| SourceCapability | `source_capability.py` | IMPLEMENTED | 소스 능력(list/detail/api/rss/static/browser/key/policy) 선언 모델 |
| StrategyGraph | `strategy_graph.py` | IMPLEMENTED | capability→안전 전략 노드 빌드, `UNSAFE_STRATEGIES` 11종 빌드 reject |
| SourcePolicyProbe | `source_policy_probe.py` | IMPLEMENTED | robots longest-match, AI 크롤러 토큰 차단, paywall/login 마커 |
| EvidenceGate | `evidence_gate.py` | IMPLEMENTED | 외부URL+stable_id+time+payload shape 린터, synthetic/local URL 거부 |
| CommunityCorroborationGate | `community_corroboration_gate.py` | IMPLEMENTED | dcinside 금융갤 `internal_queue_only` 봉인, 펌핑 제목 publish 차단 |
| SourceStrategyMemory | `source_strategy_memory.py` | IMPLEMENTED | 소스별 successful_strategy + `llm_agent_hints` 누적 |
| ProductionState | `production_state.py` | IMPLEMENTED | total function(UNKNOWN=0), SCHEDULABLE_STATES 분리 |
| RawEventBridge | `bridge_to_raw_events.py` | **PARTIAL** | content_hash dedup·url NOT NULL·preview_only 계약 완비, **그러나 db_writer=None 기본 → mirror만** |
| EventQueue | `pipeline/event_queue.py` | **PARTIAL** | JSONL fallback 동작, **`_redis_*` 4개 NotImplementedError("Round 2")** |
| 본문추출 | `tools/trafilatura_extractor.py` 등 | IMPLEMENTED | selector→trafilatura→readability→dom cascade |
| monitoring | `orchestration/monitoring.py` | IMPLEMENTED | production_summary/alerts/source_health, critical→exit code |
| rate-limit | `configs/rate_limit_policy.yaml`, `core/rate_limit_store.py` | IMPLEMENTED | gdelt 60s/900s, trends 7200s/0재시도; memory/local_file/redis 백엔드 |

**소스 분포(57)**: PRODUCTION_READY 46 / dcinside COMMUNITY_PREVIEW 1 / gdelt EXTERNAL_RATE_LIMITED 1(scheduled 429) / POLICY_EXCLUDED 9. degraded 0.
**주의**: READY 다수는 단발 `LIVE_SUCCESS`(예: 2026-06-12 실측) 근거이며 지속 운영 검증은 부분적이다(→ 지속검증 TODO).

## 2. 서브시스템 B — 다운스트림 앱 (혼재)

| 영역 | 상태 | 근거 |
|---|---|---|
| backend FastAPI events list/search/detail | IMPLEMENTED | `backend/app/api/events.py`, OpenSearch multi_match |
| admin API(10) | IMPLEMENTED | dev bypass 주의(빈 토큰=허용) |
| themes/sectors/comments/ai_replies | **PARTIAL** | 스켈레톤/미완성 |
| raw_events / event_cards 스키마 | IMPLEMENTED | alembic 0001~0003, raw_text=요약만(본문 저장 금지) |
| 3엔진 검색 | IMPLEMENTED | Milvus(1536 IVF_FLAT/COSINE) + OpenSearch(keyword) + PG. 인덱싱 swallow |
| workers RSS 수집 | IMPLEMENTED | `workers/collectors/rss_collector.py` 3소스 → raw_events PG |
| Redis Stream(B측) | IMPLEMENTED | `workers/queue/producer.py` XADD, `consumer.py` XREADGROUP+heartbeat |
| LangGraph 11노드 | **5 REAL / 6 MOCK** | 아래 표 |
| frontend Next.js 15.5.18 | IMPLEMENTED | 11 라우트 + 4 API route, server-only admin token |

**LangGraph 11노드 real/mock**(`agents/graphs/event_processing_graph.py`, `agents/nodes/`):

| 노드 | 상태 | 노드 | 상태 |
|---|---|---|---|
| source_parse | REAL | entity_linking | MOCK(`[mock-entity-1]` 고정) |
| normalize_event | REAL | sector_mapping | MOCK(하드코딩 분류) |
| deduplicate | PARTIAL(dedupe_key만) | impact_analysis | MOCK |
| retrieve_past_context | REAL(Milvus top-k) | evidence_check | MOCK(빈 목록) |
| publish_or_hold | REAL | fact_check | MOCK("pass" 고정) |
| | | final_writer | MOCK |

mock→real 전환은 코드 없이 env 토글(`LLM_PROVIDER`, `EMBEDDING_PROVIDER`)로 일부 가능하나, entity_linking/sector_mapping 등은 실 NER/분류 구현이 필요하다.

## 3. 중앙 통합 갭 (P0)

```text
ingestion EventQueue(JSONL) ──X── (미배선) ──X──> raw_events PG ──> LangGraph ──> event_cards
        │                                              ▲
        └── bridge_to_raw_events (db_writer=None → JSON mirror만)   └── workers/ RSS 3소스 (별도 경로)
```

- ingestion 57소스의 산출물은 JSON mirror 파일에만 쌓이고, 실 raw_events PG는 workers RSS 3소스가 채운다.
- 즉 "57소스 엔진"의 결과가 사용자 화면(event_cards)까지 도달하는 경로가 끊겨 있다. **이것이 모든 수익화·고도화의 선행조건이다.**
- 부차 갭: ingestion EventQueue가 Redis 미배선(JSONL), Celery(celery_app/tasks/retry_queue/quota_guard) 미구현, 내장 scheduler 부재(외부 cron 가정).

## 4. 미구현/설계전용 (코드 부재 확인)

- 검색 외부 확장 layer(`search/expansion`) — 없음.
- event clustering/timeline/ranking — `agents/` 내 grep 0건.
- KG-RAG/GraphRAG/entity-event graph — 없음(event_cards.entities JSONB 필드만 존재, 그래프 저장·추론 없음).
- hybrid search(BM25+vector RRF), reranker, 한국어 nori — 미구현.
- LLM SourceSupervisor 실 provider 루프 — 인터페이스(`source_supervisor.decide`)만, 규칙기반 동작.
- alert/report/API 상품, shadcn/ui, i18n, Playwright e2e — 미구현.

## 5. 버전 핀 (변경 금지)

Python 3.11 / langgraph 0.2.76 / langchain 0.2.11(v1 보류) / pymilvus 2.4.4 / openai 1.108.x / Next.js 15.5.18 / FastAPI 0.115.x / SQLAlchemy 2.0.x. uv 전용, conda 금지.
> 웹 리서치상 LangGraph 1.0(2025-10 GA, durable execution/checkpointing/HITL)이 기본 런타임이 됐으나, 0.2.76 유지는 의도된 결정이며 업그레이드는 redis checkpointer 전환 시점에 함께 평가한다(상세 10).

## 6. 테스트 베이스라인

- ingestion: 1205 passed (G-4 기준, 확정).
- 다운스트림(STEP 011 스냅샷, `NEEDS_VERIFICATION`): backend ~50 / agents ~22 / workers ~19 / frontend 8.
> 다운스트림 수치는 STEP 011 이후 재집계되지 않았다(드리프트 가능). 정확값은 재실행 필요 — `docs/_CANONICAL/09` 참조.

## 7. 감사 결론 (구현 vs 아이디어 분리)

- **이미 강한 것**: 정책안전 수집 라우팅·게이트·전략메모리(A), 3엔진 저장·검색 골격(B), 프론트 셸. 이는 "connector 개수"로 환산되지 않는 자산이다.
- **끊긴 것(P0)**: A→B 배선. 이게 풀리기 전엔 소스 추가·고급 RAG·상용화 모두 공허하다.
- **욕심내면 안 되는 것**: GraphRAG/검색확장/reranker는 토대(배선·dedup·mock 해제) 이후의 P2~P6다.

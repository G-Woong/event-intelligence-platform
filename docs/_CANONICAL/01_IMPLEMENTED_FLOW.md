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
- ✅ **P0 하드닝(2026-06-18) — mock 카드 published 노출 봉인(fail-closed)**: `evidence_check`가 실 source
  URL만 근거로 채택(`evidence_rules` 구조검증), `publish_or_hold`가 근거+fact_check pass+본문 게이트,
  `final_writer` 기본 `hold`, 공개 `GET /api/events`는 published-only. **라이브 proof**: 유효 URL→카드
  `published`+목록 노출, synthetic URL→카드 `hold`+목록 비노출(`GATE_LIVE_PROOF=PASS`).
- ✅ **P0 하드닝 — DLQ/PEL 부품**: `workers/queue/dlq.py`(route_failure 재시도/DLQ, reap_pending XAUTOCLAIM),
  consumer 실패시 DLQ 라우팅(silent leak 제거), `run_dlq_reaper` CLI, `requeue_failed_xadd`(poison 한도).
- ✅ **Orchestration 하드닝(2026-06-18) — mock 상수 제거 + baseline**: entity/sector/impact/summary/fact_check
  5노드의 mock 고정 상수를 **결정론적 입력파생 baseline**으로 대체(`agents/nodes/baselines.py`), `publish_or_hold`에
  합성마커 백스톱 추가. **라이브 proof**: 실 URL→카드 `published`(entities=['OPEC','Saudi Aramco',...], sectors=['energy'],
  정직 impact/추출 요약), synthetic URL→`hold`+공개 404(`BASELINE_LIVE_PROOF=PASS`).
- ✅ **Orchestration 하드닝 — admin auth 운영 fail-closed**: `APP_ENV` 도입, production/staging 토큰 미설정 시
  admin 503 + 기동 거부. **복구 주기 드라이버** `run_recovery_scheduler`(reconcile+requeue-failed-xadd+PEL reap),
  backend `POST /raw-events/requeue-failed-xadd` 엔드포인트.
- ✅ **Orchestration source-live 라운드(2026-06-18)**:
  - **evidence_check HTTP 도달성(SSRF-safe, best-effort)**: `evidence_reachability.py` — DNS 해석 후
    전역 유니캐스트(`ip_is_public`=is_global whitelist, IPv4-mapped 언맵) 검증, redirect 매 hop 재검증,
    HEAD→GET fallback. `settings.EVIDENCE_REACHABILITY_CHECK`(기본 off). 잔존: DNS rebinding/TOCTOU(문서화).
  - **복구 드라이버 라이브 tick + compose service**: `docker-compose.dev.yml`에 `recovery-scheduler`
    service 추가(worker 이미지, `--interval-sec 60`). 라이브 `--once` tick 입증: reconcile/requeue/PEL reap
    3 action 전부 backend:8000 인-네트워크 성공(`actions=3 ok=3`). scheduler logging 구성 추가.
  - **admin auth 자세 단일화**: `security.assert_startup_auth_posture`(prod fail-closed + APP_ENV=dev
    오배포 경고), `.env.example`에 APP_ENV 보안주석.
  - **source-wide final_action matrix**: `run_orchestration_source_validation.py`(네트워크 0 분류)
    → 57소스: CALLABLE_NOT_PROBED 46 / SKIPPED_POLICY_EXCLUDED 9 / RATE_LIMITED_SCHEDULED 1(gdelt) /
    HELD_BY_POLICY 1(dcinside). 가짜 green 없음.
  - **라이브 외부 probe 1건 직접 관찰**: vetted runner로 bbc 라이브 수집 → 36 records 실추출 →
    34 EventQueue/raw_events(mirror) 적재, 2 DUPLICATE_COLLAPSED. rate_limited=0.
- ✅ **Source-to-card E2E 라운드(2026-06-18, 2f)**:
  - **라이브 외부 → backend sink → event_card E2E 직접 관찰**: `production-validation --raw-events-sink
    backend` 로 **ap_news**(Google News RSS) 100 records 라이브 → raw_events PG 100 → Redis +100 →
    worker(group:ingest, pending0/lag0) → agent-worker(group:agent) → LangGraph → **event_cards 100건**
    (evidence=news.google.com URL 확정). 무본문 snippet_only → fail-closed 전량 hold(공개 published 129 불변).
    직전 "backend sink end-to-end 미실행" blocker 해소(현 스택은 no-token admin write 수락=422 probe 확인).
  - **timeout 거짓실패 버그 수정**: `BackendApiRawEventsWriter` timeout 10→30초. burst tail-latency(>10초)에서
    서버는 200 완료인데 클라이언트가 거짓 transport-fail 집계(100건 중 54 false-fail) → contract_fail 거짓
    critical. 멱등 endpoint 라 timeout 안전. 수정 후 재실행 critical=0, contract_pass=True. 회귀 +2 테스트.
  - **recovery-scheduler 상주 daemon**: `up -d` 로 상시 기동, 즉시 첫 tick `actions=3 ok=3`, 60초 주기.
- ⚠ **남은 blocker**: ① entity/sector는 **LLM급 아닌 결정론적 baseline**, ② 46 CALLABLE 소스 **전수** 라이브
  probe(이번은 ap_news+bbc급), ③ timeout 수정의 100건 burst 재검증, ④ DLQ depth 알림·라이브 chaos,
  ⑤ ap_news 무본문은 정상 hold이나 **published 상용 카드는 실본문 소스 필요**(T-AgtA). 상세 04/05.

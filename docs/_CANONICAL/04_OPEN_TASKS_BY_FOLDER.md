# 04 — OPEN TASKS BY FOLDER (폴더별 미구현 TASK)

> 구현 완료된 것은 여기 없다(01 참조). RISK는 05, 고도화는 07.
> 우선순위: P0 통합 차단 / P1 기능 갭 / P2 운영·품질.

---

## ingestion/ (수집 엔진)

### T-IngA · ingestion → 다운스트림 raw_events 실 배선  **[P0 — PARTIAL DONE 2026-06-18]**
- Folder: `ingestion/integration/`, `ingestion/orchestration/`, `backend/app/services/`
- DONE: `ingestion/integration/raw_events_writer.py`(`BackendApiRawEventsWriter` = bridge db_writer 콜러블,
  backend POST 경유 PG+Redis), `downstream_contracts.py`(record_type별 계약 검증),
  `p0_integration_runner.py`+`tools/run_p0_integration.py`(e2e proof). `run_production_orchestration`에
  `--raw-events-sink backend` 주입 진입점 추가. 라이브 e2e 5타입 통과, 멱등 collapse 확인.
- 남은 부분(P0 complete까지): ① production-validation 라이브 외부 probe→backend 실적재 1회 검증
  (이번 세션 미실행, dry-run+proof-runner만), ② 카드 콘텐츠 mock(T-AgtA 의존).
- Owner: source-ingestion-engineer + orchestrator-architect / Priority: P0(잔여)

### T-Ops-DLQ · Redis DLQ / PEL 회수 / xadd_failed 자동 requeue  **[P0(운영 안전)]**
- Files: `workers/queue/consumer.py`(예외 시 XACK 누락→PEL 영구잔류), `agents/agent_worker.py`(무조건 XACK→실패 소실), `backend/app/services/{raw_event_service,reconciler_service}.py`(requeue 부품 존재, 자동 트리거 없음)
- Required: DLQ stream + XAUTOCLAIM reaper + status=failed row 주기 requeue(Celery beat). 부품 대부분 존재, 배선 중심.
- Acceptance: poison 메시지 DLQ 격리, consumer 크래시 후 PEL 회수, xadd_failed 자동 회복.
- Priority: P0(데이터 정체 직결, 팀 리뷰 지적) / Owner: operations-sre-agent

### T-IngB · EventQueue Redis Stream 모드 활성화  **[DONE 2026-06-18]**
- Files: `ingestion/pipeline/event_queue.py`
- DONE: `_redis_enqueue/_dequeue/_peek/_mark_done` 구현(Stream `stream:ingestion_eventqueue` +
  consumer group + PEL ack). 주입형 client로 테스트(test_p0_redis_publish, test_pipeline_scaffold).
- 주의: 이 스트림은 A측 EventQueue 자체 durable 백엔드(P0 핵심 전달경로는 backend `stream:raw_events`).
  production runner는 현재 EventQueue를 JSONL로 사용 — Redis 백엔드 채택 여부는 운영 결정(P1).

### T-IngC · Celery 스케줄링 (Phase H)  **[P1]**
- Files(미생성): `celery_app.py`, `tasks.py`, `retry_queue.py`, `quota_guard.py`
- Current: 주기 판정은 `cycle_planner.py`(순수함수) + 외부 cron 가정. 분산 스케줄러 없음.
- Required: Celery beat 스케줄 + Windows `--pool=solo` 확인 + rate_limit_policy cache_ttl 연동.
- Blocker: Redis/Postgres 컨테이너 가동 + 사용자 승인(INSTALL_CANDIDATE).
- Priority: P1

### T-IngD · CommunityCorroborationGate → publish 파이프라인 배선  **[PARTIAL DONE 2026-06-18]**
- Files: `community_corroboration_gate.py`(등급 산출), `agents/nodes/publish_or_hold.py`(B측 소비 추가)
- DONE: B측 `publish_or_hold`가 `confirmation_policy ∈ {unconfirmed_until_corroborated,
  internal_queue_only, publish_blocked_until_corrob}`이면 fact_check와 무관하게 card status=`hold` 강제.
  라이브 e2e로 community 카드 hold 봉인 확인. p0_integration_runner는 `internal_queue_only`를 bridge에서 제외.
- 남은 부분: A측 publish_level 메타(gallery_id 기반 internal/blocked 세분)를 raw_metadata로 끝까지 운반해
  B측에서 등급별 차등 처리(현재는 정책 set 일괄 hold). dcinside 수집 자체는 R-DcToS 봉인 유지.
- Priority: P1(잔여) (05 R-DcToS 연동)

## agents/ (LangGraph)

### T-AgtA · 6개 mock 노드 실모델 연결  **[P1]**
- Files: `agents/nodes/{entity_linking,sector_mapping,impact_analysis,evidence_check,fact_check,final_writer}.py`
- Current: 6/11 노드 mock(고정/템플릿 반환). 5 REAL(parse/normalize/retrieve_context/publish_or_hold + partial deduplicate).
- Required: NER/분류기/프롬프트 자산 연결(`agents/prompts/*.md` → load_prompt → LLMClient). `LLM_PROVIDER=openai` 전제.
- Acceptance: 각 노드 실 출력 + 스키마 검증 통과, mock 분기 제거 아닌 실경로 추가.
- Priority: P1

### T-AgtB · deduplicate 벡터 유사도 임계값 결정  **[P2]**
- Files: `agents/nodes/deduplicate.py`(dedupe_key는 생성, 벡터 cosine 기준 미정)
- Required: Milvus cosine threshold 결정 + 적용.

### T-AgtC · 프롬프트 자산 코드 통합  **[P2]**
- Files: `agents/prompts/{impact_analysis,fact_check,summarize_event,final_card_writer}.md`(초안만, 코드 미연결)

## backend/

### T-BeA · themes/sectors/comments/ai_replies 실로직  **[P2]** — 현재 스켈레톤/미완성.
### T-BeB · raw_events TTL/아카이브 정책  **[P2]** — `DATA_POLICY.md` "TTL 미정" 미해결.
### T-BeC · /api/internal/search-similar 인증 미들웨어  **[P2]** — 현재 인증 없음(TODO 주석).

## search/

### T-SrA · Hybrid search(BM25+벡터 rerank)  **[P2]** — 현재 OpenSearch keyword only.
### T-SrB · 한국어 nori analyzer  **[P2]** — 현재 기본 분석기.

## frontend/

### T-FeA · shadcn/ui 디자인 시스템 / i18n / Playwright e2e  **[P2]** — 미구현.

## infra/ops

### T-OpA · 내장 scheduler daemon  **[P2]** — 외부 cron 가정.
### T-OpB · RBAC/OAuth2 + Admin bypass 해제  **[P1]** — 운영 배포 전 필수(05 R-Auth).
### T-OpC · production Docker / TLS / CDN  **[P2]** — dev 설정만 존재.

## docs/

### T-DocA · INGESTION_FINAL/IMPLEMENTATION_TRACE 수치 갱신  **[P2]**
- 509/635/648 테스트 수, "44 CORE_READY/58" → 현재 1205 / 46 PRODUCTION_READY / 57로 갱신(또는 canonical 포인터).
### T-DocB · artifact_manifest_final.md에 G-4·orchestration 산출물 추가  **[P2]**
- `community_corroboration_gate`/`source_specific_proof`/orchestration cycle 출력 미등재.

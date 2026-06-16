# 04 — OPEN TASKS BY FOLDER (폴더별 미구현 TASK)

> 구현 완료된 것은 여기 없다(01 참조). RISK는 05, 고도화는 07.
> 우선순위: P0 통합 차단 / P1 기능 갭 / P2 운영·품질.

---

## ingestion/ (수집 엔진)

### T-IngA · ingestion → 다운스트림 raw_events 실 배선  **[P0]**
- Folder: `ingestion/orchestration/`, `backend/app/services/`
- Files: `bridge_to_raw_events.py`(주입형 db_writer 지원), `run_production_orchestration.py`(기본 `db_writer=None`), `backend/app/services/raw_event_service.py`
- Current: bridge가 **JSON mirror로만** 기록. 57소스 출력이 실 PG/Redis stream에 들어가지 않음.
- Why not: Phase H(브리지) DEFERRED — async+pydantic+AsyncSession 어댑터 미구현.
- Risk if ignored: 두 자산이 영원히 분리 → ingestion 가치가 다운스트림에 미반영.
- Required: `create_raw_event`(async/AsyncSession)에 맞는 db_writer 어댑터 구현 + runner에서 주입 + idempotent 보장.
- Acceptance: production 사이클 1회 → 실 raw_events row 증가 + Redis stream XADD 확인, 중복 미적재.
- Owner: source-ingestion-engineer + orchestrator-architect / Priority: P0

### T-IngB · EventQueue Redis Stream 모드 활성화  **[P1]**
- Files: `ingestion/pipeline/event_queue.py`(REDIS_URL 시 redis 경로 디스패치, 실제 client는 "Round 2")
- Current: REDIS_URL 없는 deterministic 사이클에선 JSONL fallback만 동작.
- Required: redis client 배선 + enqueue/dequeue/peek/mark_done 구현 + 테스트.
- Acceptance: REDIS_URL 설정 시 stream 기반 큐 동작, JSONL과 계약 동일.
- Priority: P1 (T-IngA의 후속/대안 경로)

### T-IngC · Celery 스케줄링 (Phase H)  **[P1]**
- Files(미생성): `celery_app.py`, `tasks.py`, `retry_queue.py`, `quota_guard.py`
- Current: 주기 판정은 `cycle_planner.py`(순수함수) + 외부 cron 가정. 분산 스케줄러 없음.
- Required: Celery beat 스케줄 + Windows `--pool=solo` 확인 + rate_limit_policy cache_ttl 연동.
- Blocker: Redis/Postgres 컨테이너 가동 + 사용자 승인(INSTALL_CANDIDATE).
- Priority: P1

### T-IngD · CommunityCorroborationGate → publish 파이프라인 배선  **[P1]**
- Files: `community_corroboration_gate.py`(publish 등급 산출은 구현) → 다운스트림 publish 계층 소비 미연결.
- Current: 등급(internal_queue_only/publish_blocked/preview_candidate)은 record에 부착되나 소비처 없음.
- Required: quality/safety publish 계층이 등급을 강제하도록 연결(특히 익명 금융 갤러리 internal_queue_only).
- Priority: P1 (dcinside publish 해제의 전제, 05 R-DcToS와 연동)

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

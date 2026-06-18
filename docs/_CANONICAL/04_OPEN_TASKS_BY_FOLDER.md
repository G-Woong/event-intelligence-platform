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

### T-Ops-DLQ · Redis DLQ / PEL 회수 / xadd_failed 자동 requeue  **[P0 — PARTIAL DONE 2026-06-18]**
- DONE: `workers/queue/dlq.py`(`route_failure`=재시도 사본 재발행 또는 max_retries 초과 시 DLQ 격리+원본 ack;
  `reap_pending`=XAUTOCLAIM PEL 회수). `workers/queue/consumer.py`가 process 실패 시 DLQ 라우팅(silent
  PEL leak 제거). `workers/tools/run_dlq_reaper.py` CLI. `reconciler_service.requeue_failed_xadd`(xadd_failed
  행을 max_requeue 한도 내 자동 requeue, poison 무한루프 방지). 테스트: `workers/tests/test_dlq_reaper.py`(7),
  `backend/tests/test_requeue_failed_xadd.py`(4) — FakeRedis/mock, 네트워크 0.
- DONE(Orchestration 하드닝 2026-06-18): 주기 복구 **드라이버** `workers/tools/run_recovery_scheduler.py`
  (매 tick: reconcile-stuck + requeue-failed-xadd + PEL reap, 각 action 에러 격리, `--once`/`--interval-sec`,
  all-fail 시 non-zero exit). backend에 `POST /api/admin/raw-events/requeue-failed-xadd` 엔드포인트 추가
  (`reconciler_service.requeue_failed_xadd` 노출). 테스트: `workers/tests/test_recovery_scheduler.py`(4),
  `backend/tests/test_reconciler_api.py`(requeue-failed-xadd 2 추가).
- DONE(source-live 라운드 2026-06-18): `docker-compose.dev.yml`에 **`recovery-scheduler` service 추가**
  (worker 이미지 재사용, `--interval-sec 60`). scheduler에 logging.basicConfig + cycle 요약 로그 추가
  (이전엔 무출력). **라이브 `--once` tick 입증**: compose run → reconcile_stuck(200)/requeue_failed_xadd(200)/
  reap_pending(claimed=0) `actions=3 ok=3` EXIT=0.
- 남은 부분: ① **daemon 상시 가동**(compose service는 정의/검증됨; `up -d`로 상주 배포는 ops 결정),
  ② DLQ depth 모니터링/알림 임계값, ③ worker-kill 라이브 chaos(현재 단위 FakeRedis까지).
- Acceptance(잔여): daemon 상시 배포 + DLQ depth 알림 + 라이브 chaos. Priority: P1(잔여) / Owner: operations-sre-agent

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

### T-AgtA · mock 노드 실모델 연결  **[P1 — mock 상수 제거+baseline DONE 2026-06-18; LLM급 잔여]**
- Files: `agents/nodes/{baselines,entity_linking,sector_mapping,impact_analysis,evidence_check,fact_check,final_writer,publish_or_hold,evidence_rules}.py`
- DONE(Orchestration 하드닝): 5노드의 **mock 고정 상수를 결정론적 입력파생 baseline으로 대체**
  (`agents/nodes/baselines.py`): entity=대문자 고유명사 추출, sector=keyword 분류, impact=정직한 baseline 문구,
  summary=본문 추출, fact_check=**구조적 fail-closed**(본문+grounded evidence+합성마커없음일 때만 pass).
  `publish_or_hold`에 **카드 텍스트 합성마커 백스톱** 추가(`[fallback]`/`[mock]` 우회노출 차단). `LLM_PROVIDER=openai`
  일 때만 LLM 보강(상수 반환 시 baseline 복귀). 라이브 입증(재빌드 스택): 실 URL 카드가 실 entity/sector/추출요약으로
  published, synthetic URL은 hold+공개 404. 테스트: `agents/tests/test_entity_sector_impact_fact_real_baseline.py`,
  `test_event_graph_no_mock_published.py`, `test_evidence_check_real_validation.py`.
- DONE(source-live 라운드 2026-06-18): **`evidence_check` URL 도달성(HTTP) 구현** —
  `agents/nodes/evidence_reachability.py`(SSRF-safe best-effort): DNS 해석 후 is_global whitelist
  (IPv4-mapped 언맵), redirect 매 hop 재검증(follow_redirects 강제 off), HEAD→GET fallback, 짧은 timeout.
  `EVIDENCE_REACHABILITY_CHECK` 토글(기본 off). 적대적 리뷰 REAL_BUG 2건 반영(TOCTOU 문서화/철회, IPv4-mapped
  수정). 테스트: `test_evidence_reachability_ssrf_safe.py`(17), `test_evidence_check_real_validation.py`(+3 배선).
- 남은(LLM급 정밀도): entity NER/sector 분류기는 **결정론적 baseline**(LLM급 의미분석 아님). LLM 보강
  (`LLM_PROVIDER=openai`)·evidence 도달성 라이브(openai/network)는 미배포(키 미설정). DNS rebinding/TOCTOU 잔존.
- Required: NER/분류기/프롬프트 자산 연결(`agents/prompts/*.md` → load_prompt → LLMClient, `LLM_PROVIDER=openai`),
  evidence reachability(SSRF-safe HEAD/GET).
- Acceptance: LLM급 실 출력 + 스키마 검증 + evidence 도달성. Priority: P1(잔여)

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
### T-OpB · RBAC/OAuth2 + Admin bypass 해제  **[P1 — prod fail-closed DONE 2026-06-18; RBAC 잔여]**
- DONE(Orchestration 하드닝): `APP_ENV`(dev/test/staging/production) 도입. `require_admin_token`이
  **production/staging에서 토큰 미설정 시 503 거부**, `main.py` lifespan은 운영 모드 토큰 미설정 시 **기동 거부**
  (RuntimeError). dev/test만 bypass 유지. 테스트: `backend/tests/test_admin_api_token_required_in_production.py`(5).
- 남은: RBAC/OAuth2 per-endpoint scope. 운영 배포 전 `APP_ENV=production` + `ADMIN_API_TOKEN` 설정 필수(05 R-Auth).
### T-OpC · production Docker / TLS / CDN  **[P2]** — dev 설정만 존재.

## docs/

### T-DocA · INGESTION_FINAL/IMPLEMENTATION_TRACE 수치 갱신  **[P2]**
- 509/635/648 테스트 수, "44 CORE_READY/58" → 현재 1205 / 46 PRODUCTION_READY / 57로 갱신(또는 canonical 포인터).
### T-DocB · artifact_manifest_final.md에 G-4·orchestration 산출물 추가  **[P2]**
- `community_corroboration_gate`/`source_specific_proof`/orchestration cycle 출력 미등재.

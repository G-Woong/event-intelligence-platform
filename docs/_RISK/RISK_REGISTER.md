# RISK REGISTER (위험 등록부) — 단일 출처

> 위치: `docs/_RISK/RISK_REGISTER.md`. (2026-06-19 `_CANONICAL/05_RISK_REGISTER.md` 에서 **본문 통째 이동** — R3 단일출처. `_CANONICAL/00` 이 이 경로를 가리킨다. 권위 정점 `_CANONICAL/*` 의 risk 토픽(#05)은 물리적으로 여기 존재한다.)
>
> **RISK ≠ TODO** — 종결조건(Closure)이 충족돼야 닫힌다.
> **3상태(매 턴 turn-closeout 이 관리):**
> - **열림(open):** Closure 미충족 → 이 파일.
> - **부분종결(partial):** severity 하향됐으나 Closure 미충족 → 이 파일 유지, 종결 이력은 1줄 요약 + archive 링크로 압축.
> - **완전종결(closed):** Closure 충족 → `RISK_CLOSED.md` 로 흐름 1~3줄만 이관, 상세 본문은 `_ARCHIVE_SUPERSEDED`.

---

### R-Integration · 두 수집 경로 미통합  — Severity: HIGH→MEDIUM→LOW-MEDIUM (라이브 외부→card E2E 관찰 2026-06-18)
- Area: source 수집 안정성 / 아키텍처
- Description: ingestion 엔진 출력→다운스트림 raw_events PG 배선.
- DONE: `ingestion/integration/` adapter(BackendApiRawEventsWriter) + `--raw-events-sink backend` 진입점.
  라이브 e2e 5타입(ingestion record→PG→Redis→worker→LangGraph→event_card) 통과, 멱등 collapse 확인.
- DONE(2f 라운드, 2026-06-18): **라이브 외부 source → backend sink → event_card E2E 직접 관찰**.
  `production-validation --raw-events-sink backend` 로 **ap_news**(Google News RSS) 100 records 라이브 fetch →
  raw_events PG 100 rows → Redis +100 → worker(pending0/lag0) → agent-worker → LangGraph → **event_cards 100건**
  (evidence 에 news.google.com URL 확정), 무본문이라 전량 status=hold(fail-closed, 공개 비노출). 직전
  "라이브 외부 probe→backend 실적재 미검증" 갭 **해소**.
- DONE: **timeout 거짓실패 버그 수정** — writer timeout 10→30초(burst tail-latency >10초에서 서버는 200 완료인데
  클라이언트가 거짓 transport-fail 집계하던 문제; 100건 중 54 false-fail 관찰). 수정 후 재실행 contract_pass=True.
- Remaining gap: ① 기본 sink 는 여전히 mirror(backend opt-in) — 정식 production 스케줄에서 backend 채택,
  ② 46 CALLABLE 소스 **전수** 라이브 probe 미완, ③ timeout 수정의 100건 burst 재검증.
- Closure: backend sink 상시 스케줄 + 46 소스 전수 라이브 idempotent 적재 시 LOW.

### R-SourceRoleDrift · source 역할 정의와 실제 routing 불일치  — Severity: MEDIUM→LOW (taxonomy 파생+잠금 2026-06-18)
- Area: source-aware orchestration / 헌법 3(역할별 연결)
- Description: source 를 모두 같은 방식으로 수집하면 search 결과가 evidence 로, community 가 published 로 새는 위험.
- DONE(2026-06-18): `source_role.py` — source_group/is_community/confirmation_policy 에서 7역할
  (ARTICLE_BODY/EXPANSION_SEARCH/OFFICIAL_RECORD/STRUCTURED_SIGNAL/COMMUNITY_EARLY_SIGNAL/ENRICHMENT_ONLY/
  PERIODIC_EVENT_QUEUE)을 **결정론적 파생**(새 데이터 하드코딩 0, 단일 출처 유지). routing_mode+publication_policy
  동반. EXPANSION/COMMUNITY 는 `never_direct_publish` 를 publication_policy 에 항상 포함(증거승격·무검증공개 차단).
  `run_orchestration_source_validation` 이 SOURCE_ROLE_MATRIX 로 emit(57: ARTICLE 14/COMMUNITY 9/ENRICHMENT 13/
  EXPANSION 7/OFFICIAL 8/STRUCTURED 6). 잠금: `test_source_role_taxonomy.py`(36).
- Remaining gap: 분류·정책은 코드로 강제되나 **role 별 라이브 end-to-end proof** 는 ARTICLE(ap_news)만 관찰됨 —
  EXPANSION/OFFICIAL/STRUCTURED/COMMUNITY 각 1건 라이브 route proof 미완(03 1b). 04 T-IngA 연동.
- Closure: role 별 최소 1건 라이브 route proof + run_role_aware 통합 시 LOW.

### R-MockCard · 생성 event_card 콘텐츠 mock  — Severity: HIGH→MEDIUM→LOW-MEDIUM (mock 상수 제거 2026-06-18 Orchestration 하드닝)
- Area: 정보 신뢰성(§1) / 상품성
- Description(과거): LangGraph 6노드가 mock 고정 상수 → 카드 entity/sector/impact가 고정/가짜
  (예: 모든 입력을 geopolitics/energy/defense로 분류). raw_event 연결·status는 실제이나 알맹이는 mock이었음.
- DONE(Orchestration 하드닝, 상수 제거 + 게이트 백스톱):
  ① 5노드의 mock 고정 상수를 **결정론적 입력파생 baseline**으로 대체(`agents/nodes/baselines.py`):
     entity=고유명사 추출, sector=keyword 분류, impact=정직한 baseline, summary=본문 추출,
     fact_check=구조적 fail-closed. `[mock-*]`/고정상수/`[mock]`/`[fallback]`이 카드에 들어가지 않는다.
  ② `publish_or_hold`에 **카드 텍스트(summary/impact) 합성마커 백스톱** 추가 — openai 모드에서 LLM이
     `[fallback]` 상수를 반환해도 published 우회노출 차단(적대적 리뷰 REAL_BUG 지적 반영).
  ③ 공개 `GET /api/events`(목록)·`/api/events/{id}`(단건) 모두 published 카드만.
  → 라이브 입증(재빌드 스택): 실 URL 카드가 `entities=['OPEC','Saudi Aramco','European Union',...]`,
     `sectors=['energy']`, 정직한 impact/추출 요약으로 published; synthetic URL은 hold + 공개 404.
- Evidence: `agents/nodes/baselines.py`, `live_baseline_smoke.py`(BASELINE_LIVE_PROOF: PASS).
- Current mitigation (P0 하드닝, 노출 차단 = fail-closed):
- evidence(P0 하드닝 유지): `evidence_check`는 실 source URL만 근거로 채택, `evidence_rules`가 http(s)+공개호스트,
  합성/로컬/플레이스홀더 + 사설/loopback/link-local(메타데이터 169.254.169.254)/예약 IP(`ipaddress`) +
  RFC2606 예약도메인 거부(SSRF 가드).
- DONE(source-live 라운드, 2026-06-18): **evidence_check HTTP 도달성 구현**(`evidence_reachability.py`,
  SSRF-safe best-effort) — DNS 해석 후 is_global whitelist(IPv4-mapped 언맵), redirect 매 hop 재검증,
  HEAD→GET, `EVIDENCE_REACHABILITY_CHECK` 토글(기본 off). 적대적 리뷰 REAL_BUG 2건(TOCTOU 문서화/철회,
  IPv4-mapped 수정) 반영 + 회귀잠금. 잔존: DNS rebinding/TOCTOU(egress 방화벽 권고).
- Remaining gap: entity/sector는 여전히 **결정론적 baseline**(LLM급 정밀도 아님), LLM 보강
  (`LLM_PROVIDER=openai`) 미배포, evidence 도달성 라이브(openai/network) 미배포. → 04 T-AgtA.
- Closure: LLM급 entity/sector 완료 시 LOW(evidence 도달성은 구조검증→HTTP까지 진행됨).

### R-ContentTypeGateDormant · source_content_type 라이브 게이트 현재 트리거 0건  — Severity: LOW (신규 2026-06-22, 턴1 적대 감사 B-1)
- Area: source 수집 / body 판정 정직성
- Description: `rescue_router.decide_rescue`에 source_content_type body 게이트 배선(BODY_LADDER_FETCH인데 `body_ladder_eligible=False`면 STRUCTURED_SIGNAL_REDUCE). 코드는 정합(회귀 0, test-validation PASS·orchestrator SOUND)이나 **현 상태 분포에서 라이브 트리거 0건** — 카탈로그 6종(aladin/tmdb/kofic/kopis/tour/igdb)은 PRODUCTION_READY라 gap matrix 제외, BODY_FETCH layer는 `EXTERNAL_API_ERROR`+EXCERPT/NO_FULL_BODY에서만 부여되는데 해당 상태 소스 0. 즉 현재는 **미래 회귀/오분류 방어용 가드레일**이며 라이브 즉효 아님(보고에서 "배선 완료"를 효과 즉발로 과대표현 금지).
- 잔여 취약성(감사 N-1/N-4): ① 신규 카탈로그 소스는 `_CATALOG`(`source_content_type.py`)에 등록 필수 — 누락 시 source_group="domain"→article 기본으로 거짓 음성(body ladder 헛돌이). ② 게이트가 활성화되면 STRUCTURED_SIGNAL_REDUCE가 `still_not_ready`로 집계돼 "metadata_complete인데 not_ready" 표기 모순 — monitoring에 `metadata_complete_holdover` 별도 카테고리 분리 권고.
- Closure: 카탈로그가 실제 BODY_FETCH 경로를 받는 시나리오에서 게이트 라이브 트리거 1건 관찰(거짓 음성 0) + 표기 분리 시 종결. 트리거 경로 영구 부재로 확인되면 "가드레일"로 정직 문서화 후 partial-closed.

### R-EventTimelineS2Hardening · S1 Event 토대의 S2 이전 확정 필요 항목  — Severity: LOW (신규 2026-06-22 · ①②③ 종결, ④ 상류만 잔여)
- Area: data-model / Event 타임라인
- Description: S1(events/event_updates/event_cards.event_id nullable FK)은 비파괴·정합이나, S2 착수 전에 확정할 정책 항목 ①~④ 가 적대/법무 감사에서 식별됨.
- DONE(S2d — `event_timeline_service`): **②③ 종결.** ② `_ensure_aware`(tz-naive→UTC)+`_coerce_uuid`(UUID/str 경계)를 CRUD 입력 전 적용(live-PG `test_live_tz_naive_defended`·`test_live_uuid_str_boundary` 입증). ③ `set_snapshot` 이 카드 탈취 거부 + 세팅 후 실제 영속값 재조회로 is_snapshot_bidirectional 검증(live-PG `test_live_set_snapshot_bidirectional_and_reject_steal` 입증).
- DONE(S2e live-PG — ADR#20, **① DB 레벨 입증(test-DB)**): app-layer hard-delete 미제공(삭제 메서드 0) **+ FK CASCADE→RESTRICT(alembic 0006)** 로 app+DB 양층 감사 보호. **disposable test DB(event_intel_test)** 에서 0001~0006 up/down + **confdeltype='r' 4 FK 직접 단언**(`test_live_all_event_fks_are_restrict` — 회귀 고정) + `DELETE FROM events`(감사 이력 보유)가 IntegrityError 로 차단됨(`test_live_fk_restrict_blocks_event_delete_with_history`). 적대 B-2(감사 보호 app 한정·DB 미보호) **해소**. (단 **운영 DB(event_intel) 0006 배포는 배포 단계 잔여** — test-DB 입증 ≠ 운영 적용.)
- DONE(C live wiring, 2026-06-22 — `candidate_from_cluster`): ④ 상류 candidate_for 매퍼 **배선 + 본 경로 가드 완료**. 기본 매퍼는 canonical_title(record title 상한 512 절단)·delta_summary(provenance enum 라벨 `{confidence}:{reason}`)·evidence(allowlist scalar)·source_refs(짧은 식별자)만 후보화 → 본문/PII 미합성 + service `_sanitize_*` 2차 차단(legal evidence_review APPROVED, live-PG 실 JSONB 입증).
- DONE(D-1 운영 결선, 2026-06-22 — ADR#23): **운영 결선 composition root 구현** — `backend/app/tools/run_event_orchestration.py`(backend-side, 전용 NullPool 엔진 생명주기 소유, sink 주입, decoupling 보존). 운영 runner 가 `--event-resolution`/`EVENT_RESOLUTION_ENABLED` 로 Event 영속 *능력* 확보(live-PG 로 실 sink CREATE→APPEND 입증). 단 **주기 auto-trigger·실 production-validation·운영 DB 0006 배포는 여전히 잔여**(능력 ≠ 운영 가동).
- 잔여(open): **④ 임의 주입 passthrough + 운영 배포** — `event_timeline_service.create_event`/`append_update` 의 `canonical_title`/`delta_summary` 는 sanitize 미적용(길이 상한 없음). 기본 매퍼는 안전하나 **외부가 `candidate_for`/raw `ResolvedCandidate` 를 직접 주입**하면 무검열 영속 가능 — 영속층 title/delta 상한 가드는 차기 하드닝(legal residual ①②). + 운영 DB 0006 배포 + 주기 auto-trigger(Celery beat)/실 production-validation Event 누적(D-1 능력은 확보, 운영 가동 미입증).
- Closure: ④ 영속층 title/delta passthrough 가드(또는 주입 호출자 검증 계약) + 운영 DB 0006 배포 + 주기 트리거로 실 수집 Event 누적 입증 시 **완전 종결**. (①②③ test-DB 입증·④ 기본 매퍼 경로 가드 + D-1 composition root 완료 — severity LOW.)

> **R-EventSinkDbTarget** — **CLOSED 2026-06-23**(D-2c). APP_ENV allowlist(dev/test)+dbname prod-마커 교차검증 2중 fail-closed 가드(`backend/app/tools/db_target.py`) + seed/runner 단일 출처 공유. 흐름·근거는 `RISK_CLOSED.md`.

### R-RealSourceLoopUnproven · 경로 B(Event 타임라인) 실데이터 흐름 — ✅ 1회 입증(2 Event), 품질/커버리지 잔여  — Severity: MEDIUM→LOW (부분종결 2026-06-23 · 실 소스 production-validation)
- Area: product / pipeline / Event 타임라인 / 검증
- Description: **전수 감사(2026-06-23, 3-agent)** 가 경로 A(수집→raw_events; →event_cards)는 실데이터 PROVEN, 경로 B(수집→cross_source_dedup→`event_ingest_pipeline`→`event_resolution_pipeline`→`event_timeline_service`→`/api/events/timeline`→`/events/timeline`)는 **코드 배선 완료이나 실 웹 데이터 0회**로 판정했었다. → **이후 실 소스 production-validation 으로 경로 B 실데이터 1회 입증(아래).**
- ✅ **입증(2026-06-23, ADR#29):** keyless 뉴스 10소스 live fetch(0 error·0 rate_limited) → **411 real records** → `event_ingest_pipeline`(EVENT_RESOLUTION_ENABLED on, DB=event_intel_test) → cross_source_dedup **2 클러스터**(possible_duplicate) → resolver **CREATE 2 + HOLD(held members 3→possible links 3)** → `/api/events/timeline` 실데이터 **2 Event non-empty** → `/events/timeline` **브라우저 렌더**(실 헤드라인: yna `[속보] 코스피 서킷브레이커`, 매경 `대우건설 중동재건 TF`). **경로 B 가 실 웹 데이터로 Event 를 만들어 화면에 노출함을 최초 입증.** + 약신호 corroborator 를 HOLD 로 보류(자동병합 금지 — **R-FalseMerge 보호가 실데이터로 작동**).
- **핵심 발견(실 파이프라인 특성):** ① **Event 생성은 cross-source 겹침 필요** — 작은/다양한 fetch(4소스·62records)는 클러스터 0→Event 0(singletons_dropped 전량); 볼륨(10소스·411)에서야 2 클러스터. ② **CREATE genesis = updates 0**(당시) — candidate 의 evidence/delta_summary 가 APPEND 에서만 영속됐던 설계 gap → **ADR#31 genesis update 로 해소**(CREATE 시 첫 타임라인 항목 영속·화면 렌더 관측). ③ market 소스는 자산별 아닌 **단일 집계 스냅샷** 1건 → 미클러스터.
- ✅ **추가 해소(ADR#30, 2026-06-23):** ⑦ delta_summary 자연어화 = **`build_delta_summary` 실경로 적용·종결**. + APPEND 경로 **결정론 관측**(강신호 CREATE→APPEND, event_intel_test 실 update 자연어 delta_summary — 단 synthetic record, 실 fetch APPEND 은 잔여).
- ✅ **CREATE genesis 가시화(ADR#31, 2026-06-23):** clean-win CREATE 가 genesis update(생성 근거) 1행 영속 → CREATE-only Event 의 빈 상세 해소. 실 파이프라인 CREATE → `/events/timeline/{id}` 화면에 genesis 자연어("뉴스 보도가 동일 식별자로 확인된 사건입니다.")+evidence 렌더 **1회 관측(Playwright)**. **R-EventTimelineRenderHardening 완전 종결**.
- ✅ **비뉴스 타입 라우팅·fidelity 검증(ADR#32, 2026-06-23):** 결정론(실 파이프라인 5 시나리오)+실 fetch(probe). official+news 강신호→**CREATE**(evidence source_type=official+article)·structured 단일/2종→**0 Event**(singleton=signal-only 정상)·community+news 약신호→**CREATE 저신뢰+community HELD**(R-FalseMerge 작동)·pure-community 강신호→**발행 Event(gap)**. 실 fetch: federal_register LIVE 10000·sec_edgar 100·hacker_news 3(타입 분류 확인). resolver 는 source_type 무관(signal 강도 라우팅) → **R-SourceTypeFidelityGate 신규 등재**.
- 잔여(open, LOW): **실 fetch APPEND 미관측**(같은 사건 재출현 필요; genesis 자연어 화면 도달은 ADR#31 로 입증) · **source-type fidelity**: 타입 라우팅·보존 결정론 입증(ADR#32) 단 **실 cross-source 비뉴스 Event 미관측**(단일소스 probe=싱글톤) · 주기 auto-trigger 미배선 · 운영 DB(event_intel) **revision 0003 = head 0009 대비 6 뒤(0004~0009 미적용·전부 upgrade additive·non-destructive·ADR#48 readiness probe 정량화)**·검증은 event_intel_test(0009 HEAD).
- **부분진전(ADR#54 real-source identity smoke 진단 tool, 2026-06-25):** `real_source_identity_smoke.py`(기본 offline fake·network 0·DB 0·결정론)가 fetch(주입)→cluster→candidate 까지 write-free 로 돌려 **단계별 실패 분류**(body_missing/no_cluster_singleton/non_publishable_role/no_semantic_fingerprint) + source_role_distribution + publishable_anchor 를 report. probe 주입점으로 실 network fetch 는 opt-in(CI 필수 아님)·`run_db_identity_smoke`(safe-target gated·test/dev)가 기존 `ingest_records_to_events`로 DB 단계 도달. **단 기본 fake-source(real_fetch=0)·실 network/실 볼륨 미수행·DB 단계 offline None** — 진단 scaffold 이지 경로 B 실 cross-source 닫음 아님(정직). community anchor 금지·no_auto_merge 불변.
- **부분진전(ADR#55 real-source live-db smoke 실행, 2026-06-25):** ADR#54 의 fake-default 한계를 **실 fetch + 실 DB** 로 한 단계 넘음. `fetch_real_source_records`(key-free official JSON API allowlist `federal_register`/`sec_edgar`·bounded·opt-in·CI 아님·본문 미저장·transport 주입 CI network 0) + `run_db_identity_smoke`(disposable `event_intel_test` head 0009·safe-target gated). **실측: 실 federal_register fetch 5 official records → ingest: created 1 + identity_link 1(held member) · adjudications 0 · packet_eligible 0 · no_auto_merge=True · event_count 4→6.** `real_source_smoke_report` 가 §4 activation report + source quality matrix + agent readiness 9조건(단일 출처) 조립. **정직 분해:** adjudications 0 = held-member link reason `new_event_low_confidence`(≠`semantic_cross_batch_candidate`) → 실 Event 는 형성되나 **cross-batch adjudication substrate 는 동일사건 다중소스/시계열 fingerprint 중첩 필요**(single bounded single-source = source scarcity). **여전히 잔여:** live_network=opt-in tool(CI 아님)·live_db=disposable test DB(production 아님)·실 cross-source 비뉴스 Event·실 adjudication backlog·reviewer/gold/merge·운영 가동(완전종결 금지). community/market/catalog `guard_only`(anchor 금지).
- Closure(완전 종결): ✅ CREATE genesis evidence 표시(ADR#31) + △ 비-뉴스 타입 Event 형성(ADR#32 결정론 입증·**실 cross-source 미관측**) + **주기 auto-trigger** + 실 fetch APPEND 관측. severity **LOW**(경로 B 핵심 흐름·delta_summary 자연어·genesis 가시화·타입 라우팅 입증; 잔여는 실 cross-source 비뉴스 Event·운영 가동·실 fetch APPEND).
- 관계: R-EventTimelineS2Hardening(④ 운영 가동 잔여)·R-EventModelMigration(synthetic records 기준)·R-EventTimelineRenderHardening(**CLOSED — ADR#31 genesis 렌더**)·R-SourceTypeFidelityGate(**CLOSED — ADR#37 약신호 정책·입력순서 불변**)·R-Integration(경로 A 실데이터)·**R-LiveIdentityBacklog(ADR#47 — 운영 DB(event_intel) 미마이그레이션 잔여가 live labeling packet 백로그를 0 으로 막음)**을 **제품 수준에서 통합 추적**(중복 등재 아님 — 분산된 잔여를 단일 closure 로 묶음).

### R-SourceTypeFidelityGate · 비뉴스/약신호 발행 fidelity gate  — CLOSED (2026-06-23 · ADR#33/#34/#35/#36/#37) → `RISK_CLOSED.md`
> 완전 종결(adversarial JUSTIFIED 2-pass): gate(#33)+authority(#34)+held-dedup·fail-closed(#35)+강신호 core-policy(#36)+약신호 동질-publishable 정책·입력순서 불변 core/gate(#37). 상세 흐름은 `RISK_CLOSED.md`. (R-FalseMerge held 승격 잔여는 별개 RISK 로 open 유지.)

### R-EventTimelineApiScale · Event 타임라인 read API 의 대규모 응답/페이지네이션 비용  — Severity: LOW (신규 2026-06-23 · D-2a architecture/code)
- Area: api / web / 성능
- Description: D-2a `/api/events/timeline*`(ADR#24)의 규모 잔여 — ① 단건 `get_public_event`/`get_event` 가 event_updates 를 **무제한 로드**(장수명 event 가 수백~수천 update 누적 시 응답 비대), ② `list_events` 의 `id IN (cluster_event_map)` 서브쿼리 plan 이 cluster_event_map 대규모 시 비효율 가능(EXPLAIN 미측정), ③ offset 페이지네이션의 deep-offset 비용.
- 완화(D-2a): list 정렬에 (last_update_at desc, **id desc**) 결정적 tie-breaker → 페이지네이션 중복/누락 차단. list limit 상한 le=100. flag off-by-default 라 미노출 기본. read-only(쓰기/삭제 0).
- 잔여(open): 단건 updates 페이지네이션(또는 `/timeline/{id}/updates` 분리)·IN-서브쿼리 live-PG EXPLAIN(JOIN/EXISTS 대안 비교)·deep-offset → keyset 전환(트래픽 발생 후).
- Closure: 단건 updates 페이지네이션 + IN-서브쿼리 plan 실측 통과 시 종결. severity LOW(flag off·limit 상한·tie-breaker 로 완화, 트래픽 전까지 비활성).

> **R-EventTimelineRenderHardening** — **CLOSED 2026-06-23**. ① 비-404 raw 에러 → page/전역 error.tsx 일반화(ADR#26) · ③ 내부 식별자 wire 노출 → Public* 구조적 제외(ADR#26) · ② delta_summary 디버그 라벨 → `build_delta_summary` 자연어(ADR#30) **+ CREATE genesis update(ADR#31) 로 실 렌더 도달**: 실 파이프라인 CREATE → `/events/timeline/{id}` 화면에 genesis 자연어(`"뉴스 보도가 동일 식별자로 확인된 사건입니다."`) + evidence 링크(`example.com … (article · primary)`) 렌더 **1회 관측(Playwright, synthetic 강신호)** — 지난 턴 adversarial P1-1 의 "화면 미도달"을 genesis 로 해소(**render 메커니즘** 종결; 실 fetch genesis 렌더는 R-RealSourceLoopUnproven). 흐름·근거는 `RISK_CLOSED.md`.

### R-Gdelt429 · gdelt provider 429  — Severity: MEDIUM
- Area: rate-limit / cooldown / retry
- Description: provider가 429 반환. 우회 불가(정책상 금지).
- Evidence: `rate_limit_evidence.md` §1~3, production_state EXTERNAL_RATE_LIMITED.
- Current mitigation: host-level cooldown 영속 + consecutive_pending 카운터(threshold=3 escalate) + next_resume scheduled + repro_cmd. 단일 429로 disable 안 함.
- Remaining gap: 비-throttle 윈도에서 fresh record 확보. escalation report 소비 wiring.
- Closure: 정상 윈도 1회 fresh 수집 성공 → PRODUCTION_READY.

### R-DcToS · dcinside ToS 자동수집 적법성  — Severity: MEDIUM
- Area: robots / ToS / legal
- Description: robots는 allow이나 ToS 자동수집 적법성 UNVERIFIED.
- Current mitigation: **수집/큐는 닫고 publish는 CommunityCorroborationGate로 봉인**(금융 익명 갤러리 internal_queue_only, 펌핑 제목 publish_blocked). PII 닉네임 미수집. "ToS verified" 사칭 없음.
- DONE(2026-06-22 라이브 재검증): 공개 상세 **소량 산문 본문 추출 역량** 확인(`LIMITED_PUBLIC_BODY`, 보수적 필터 후 의미본문 1건). **역량≠적법** — 정책을 `docs/5_REFERENCE/DATA_POLICY.md §커뮤니티 공개 본문 수집`에 문서화(대량 수집/publish는 봉인 유지, 단일 갤러리 범위). 증거: `reports/dcinside_live_body_probe.md`.
- Remaining gap: legal-safety-compliance-reviewer 검토.
- Closure: 법무 검토 통과 → publish 게이트 해제 검토(04 T-IngD 전제).

### R-FullText · 전문 저장/재배포  — Severity: HIGH(정책)
- Area: 저작권 / 법무
- Description: 기사 전문 저장·외부 공개 금지(제목+요약만).
- Current mitigation: `bridge_to_raw_events`가 raw_text="" 기본. 원문 5계층은 내부저장 ≠ 외부공개. `COMPLIANCE_BOUNDARY.md`/`DATA_POLICY.md` 정렬.
- Closure: 정책 상시 유지(불변 제약).

### R-Bypass · 우회 금지 불변  — Severity: HIGH(정책)
- Area: robots/ToS/legal
- Description: CAPTCHA/login/paywall/rate-limit/proxy rotation/anti-bot 우회 전면 금지. google_trends_explore는 CONFIRMED_EXTERNAL_RATE_LIMIT — PASS 표기 금지.
- Current mitigation: 코드/문서 전반 enforced(09 정책 게이트). fallback chain은 0 bypass 입증(`rate_limit_evidence.md` §5).
- Closure: 불변.

### R-Auth · Admin 인증 bypass  — Severity: HIGH→MEDIUM (prod fail-closed 2026-06-18 Orchestration 하드닝)
- Area: monitoring/보안
- Description: `ADMIN_API_TOKEN` 빈 값이면 Admin API 허용(dev 편의). RBAC/OAuth 없음.
- Current mitigation: **`APP_ENV` 도입 — production/staging에서는 토큰 미설정 시 admin API 503 거부 +
  backend 기동 자체 거부**(`security.require_admin_token`, `main.py` lifespan RuntimeError). dev/test만 bypass
  유지. 토큰 설정 시 timing-safe 검사. server-only 격리로 토큰 노출 차단. 테스트: `test_admin_api_token_required_in_production.py`.
- DONE(source-live 라운드, 2026-06-18): 인증 자세를 `security.assert_startup_auth_posture` 단일 출처로
  통합(main.py 중복 제거 → 드리프트 차단). `APP_ENV=dev` + 토큰 미설정 시 **명시적·실행가능 경고**
  (UNAUTHENTICATED + "공개 배포 전 APP_ENV=production 필수"). `.env.example`에 APP_ENV 보안 주석.
- Remaining gap: RBAC/OAuth per-endpoint scope(04 T-OpB). `APP_ENV=dev`로 운영 오배포 시 여전히 무인증
  (경고는 추가됐으나 배포 환경변수 규율이 최종 방어선).
- Closure: RBAC + 운영 배포에서 `APP_ENV=production` 강제.

### R-Secret · 비밀 유출  — Severity: HIGH
- Area: secret leakage
- Description: API 키/.env 노출 위험.
- Current mitigation: `os.getenv`/pydantic-settings로만 읽음, 길이만 로깅, `monitoring.py` secret scan PASS, 산출물 gitignored, `forbidden_command_guard.py`.
- Closure: 상시 secret scan PASS 유지.

### R-Dedup · cross-source dedup 기준 미정  — Severity: LOW
- Area: dedup / merge
- Description: agents `deduplicate` 노드 벡터 cosine 임계값 미정(dedupe_key만).
- Remaining gap: 04 T-AgtB.

### R-Postcss · postcss moderate CVE  — Severity: LOW
- Area: 의존성 보안
- Description: `COMPATIBILITY_NOTES.md` 기록 — `npm audit fix --force` 금지하 잔존.
- Remaining gap: 안전한 수동 업그레이드 경로 확인.

### R-StaleDocs · 구버전 문서 충돌  — Severity: LOW
- Area: outdated docs conflict
- Description: 다수 문서가 stale 수치(509/635/648 테스트, 44소스, DART/SEC TODO) 보유 → 신규 세션 오인 유발.
- Current mitigation: 통폐합 **실행 완료**(2026-06-19, 생애주기 재편 + 후속 검증). 실행 명세는 `docs/3_ARCHIVE/2026-06_harness_design/07_REPO_REFACTOR_AND_CONSOLIDATION_SPEC.md`로 이관, 결과 지도 = `_CANONICAL/10_DOCS_COVERAGE_MANIFEST`. Phase 7: `*_FINAL`(509/648/635)에 SUPERSEDED 배너 부착, `CORS_ORIGINS`→`CORS_ALLOW_ORIGINS` drift 정정.
- Closure: 핵심 stale 수치/충돌은 canonical 정렬 + 배너로 처리. **잔여(LOW open):** `_CANONICAL/06_CONFLICTS`·`07_BACKLOG`의 구 `Orchestration_Construction/` 경로 인용(역사 ledger) sweep 미수행 → 완전 종결 보류.

### R-PromptInjection · LLM 노드 prompt injection  — Severity: MEDIUM(미래)
- Area: LLM supervisor 판단 위험 / hallucinated evidence
- Description: 외부 텍스트가 LLM 노드/SourceSupervisor 판단에 주입될 위험. synthetic URL을 안정 증거로 쓰면 안 됨.
- Current mitigation: EvidenceGate(synthetic/dead URL 가드), SourceSupervisor는 우회 제안 거부, 수집은 deterministic(LLM은 가치 지점만).
- Remaining gap: 6 mock 노드 실연결(04 T-AgtA) 시 입력 신뢰경계 재검토. DEFERRED_WITH_TRIGGER.

### R-DeadCodeAudit · 코드 레벨 dead code 자동 감사 — ruff+vulture 연동, 통폐합 미수행  — Severity: LOW-MEDIUM→LOW (phase-2 vulture 연동, 2026-06-19)
- Area: harness / docs 동기화 정확성
- Description: dead code(미사용 모듈/심볼/import/지역변수 + **uncalled function/class/method**)를 식별하는 자동 파이프라인.
- DONE(phase-2, 삭제 없음): **ruff(F401/F811/F841) + vulture(2.16, .venv 설치) 연동** `scripts/dead_code_scan.py`. **450 모듈 스캔, 결정적 221 후보 = 132 symbol(ruff) + 84 vulture + 5 module**(2회 재실행 동일). 분류: production 131 / tests 90. **vulture가 ruff 못 잡는 정의 레벨 dead code(uncalled function 42/class 32/method 6/property 1) 추가** — per-kind confidence floor(정의=60, var/import=90, attribute=80)로 노이즈 억제, alembic/migrations 제외(프레임워크 entrypoint FP). 후보별 `evidence/confidence/false_positive_risk/recommended_action/deletion_allowed:false`+`category`.
- Evidence: `scripts/dead_code_scan.py`(ruff=True vulture=True, 221, 2회 동일), `.harness/dead_code_candidates.json`, 팀감사 adversarial(vulture conf80은 ruff 중복 지적→conf60 정의레벨로 정정)+test-validation(production 샘플 진짜 unused 확인).
- Remaining gap: **(1) 통폐합 미수행**(phase-3, dry-run→audit→소규모 commit) — production 정의 레벨 70건 우선, alembic 외 framework entrypoint(tool 등록·plugin) 개별 검토 필수. **(2) vulture 정의 레벨 다수가 LOW confidence(60%)** — dynamic dispatch/CLI entrypoint FP 위험, 삭제 전 수동 확인. **(3) test 후보 90건은 저가치**.
- Closure: 프로덕션 정의 레벨 후보 1차 팀 감사 통폐합(소규모 batch) → 종결 검토. **삭제는 항상 dry-run→팀 감사→소규모 commit.**

### R-CloseoutTrust · closeout 게이트는 구조화 자기보고 기반(LLM 실제 수행은 미검증)  — Severity: MEDIUM→LOW-MEDIUM (content-hash+evidence 게이트, 2026-06-19 재감사)
- Area: harness / closeout 무결성
- Description: stamp 게이트는 ① `machine_status.audit_types(객관·훅계산) ⊆ audit_types_addressed`(커버리지) ② required audit별 `audit_evidence` 구조화 레코드(executed=true+verdict) ③ `working_tree_signature == 현재 sig`(content-hash 포함) ④ unresolved 없음을 검사한다.
- DONE(phase-2, 2026-06-19 — 라이브 green 입증): **(a) content-hash signature** — `compute_signature`가 중요 파일군(RISK/PROJECT_STATUS/hooks/skills/scripts/configs/tests/_canonical/harness_construction)의 내용 hash를 sig에 합성 → **동일 경로 내용-only 변경도 mismatch**(R2 닫힘). hook과 `scripts/closeout_sig.py`가 **동일 함수+동일 경로집합**(`collect_changed_paths`, commit 대칭) 사용. **(b) evidence 게이트** — `_audit_attested`가 required audit마다 구조화 evidence 요구 → 자기보고 `code_review_completed=true`만으론 **불통과**. 실증: 무evidence stamp closeout_current=False, evidence stamp=True, content-only 변경 sig flip, commit 대칭 sig 일치(이번 턴 closeout_stamp가 새 게이트를 라이브 통과).
- Evidence: `turn_state_snapshot.py`(`compute_signature`/`_audit_attested`/`collect_changed_paths`), `scripts/closeout_sig.py`, 이번 턴 closeout_stamp.json(audit_evidence 채워진 v2), 팀감사 orchestrator(REAL_BUG 수정 반영)·adversarial(과장 톤다운 반영).
- Remaining gap(정직): **(1) evidence는 여전히 에이전트 자기보고** — `executed/verdict`를 가짜로 채우면 통과(위조 *비용*만 상승, 본질 자기보고). 진짜 강화는 subagent 산출물 파일 존재 요구이나 `03 §4`(영구 리포트 파일 금지)와 상충 → 보류. transcript 사후검증이 최종 방어선. **(2) enforce=block 미실증**(soft 유지). **(3) closeout_sig.py 실행 누락 시 조용히 약화**(절차 규율 의존). **(4) commit-first nudge 침묵(R2 trade-off)** — `should_nudge`가 uncommitted(porcelain) 기준이라 commit 직후 transient nudge는 제거됐으나, `/turn-closeout` 없이 commit-first 하면 미마감 audit이 stdout nudge로 노출 안 됨(`machine_status.closeout_current=False`에만 흔적 잔존, fail-open 침묵). 보완: closeout 스킬 진입 시 machine_status 소비(orchestrator 지적).
- Closure: subagent 산출물 hash/존재를 게이트 증거로 요구(03 §4 절충안 마련) 또는 enforce=block 실증 시 LOW. **자기보고 한계는 "완화됨, 완전 제거 불가"로 잔존.**

### R-HarnessReproducibility · `.claude/settings.json` gitignored → 신규 clone에서 훅 미등록  — Severity: MEDIUM→LOW (doctor+문서+self-check, 2026-06-19 신규)
- Area: harness / 재현성
- Description: `.gitignore`가 `.claude/*`를 제외하고 `agents/`·`skills/`·`hooks/`만 재포함 → **`settings.json`은 gitignored**(`git check-ignore` 확인). 신규 clone/머신/codex worktree는 훅 *스크립트*는 받지만 **훅을 등록하는 settings.json이 없어** 하네스가 조용히 비활성(Stop 스냅샷·PostToolUse flag·금지명령 가드 미동작, 무에러).
- DONE(2026-06-19): **(a) `scripts/harness_doctor.py`** — settings.json 존재·필수 훅5 등록·디스크 파일·Stop hook loop guard·config 점검, 누락 시 FAIL+remediation(exit 1). **(b) `.claude/settings.example.json`(tracked, 비밀 없음) + `.gitignore` 예외** — 부트스트랩 결정(팀감사 orchestrator 권고 (b) template-only 채택): fresh clone이 `Copy-Item settings.example.json settings.json` 1-step으로 훅 재등록. settings.json 자체는 gitignored 유지(로컬 prefs/오버라이드 분리). **(c) README setup 섹션 + doctor가 누락 시 template 복사 명령 안내**. **(d) `machine_status.settings_health`** 매 턴 기록.
- Evidence: `.claude/settings.example.json`(secret scan PASS), `.gitignore`(`!.claude/settings.example.json`), `scripts/harness_doctor.py`(PASS), README, `turn_state_snapshot._settings_health`.
- Remaining gap: 복사는 **수동 1-step**(자동 아님) — fresh clone에서 doctor/copy를 안 하면 여전히 침묵(settings.json 없으면 self-check도 미동작). **settings.json 직접 tracked 전환은 user decision으로 남김**(로컬 prefs/비밀 유입 표면 trade-off — 사용자 지시상 임의 전환 금지).
- Closure: settings.json tracked 전환 결정(user) 또는 doctor를 setup/CI에 강제 배선 시 LOW→검토. **현재 부트스트랩은 template으로 실질 해결, 자동화만 잔여.**

### R-DocsLifecycle · docs 작성물의 작성-후 흐름(active→superseded→archive→trash) 규율  — Severity: LOW (audit-as-test 고정, 2026-06-19 신규)
- Area: harness / docs lifecycle
- Description: 작성된 docs가 이후 active/superseded/dead/archive/trash 중 어디로 흘러야 하는지 규율이 prose로만 있어 회귀·임의 이동 위험.
- DONE(2026-06-19): **(a) `scripts/docs_lifecycle_audit.py`(read-only/dry-run)** — 136 docs를 role/expected_lifecycle/protected/move_allowed/후보로 분류, 33 protected. 이동은 머신 마커 `<!-- LIFECYCLE: superseded|dead -->` 기반(키워드 추측 배제 → 02 정책 일치). `sweep_dry_run`은 moves_applied=0·manifests_created=0(무매니페스트 trash 유지). **(b) `tests/test_docs_lifecycle.py` 19개 invariant** — PROJECT_STATUS/RISK/README/canonical/contract/source-registry/*_FINAL 보호, superseded→dry-run archive, dead→dry-run trash, apply 없이 이동 0, trash manifest 0, 월별 ledger, conflict 검출(비어있지 않을 때), stale→risk 등록. SKILL step 5 배선.
- Evidence: `scripts/docs_lifecycle_audit.py`, `tests/test_docs_lifecycle.py`(19 passed), `.harness/docs_lifecycle_audit.json`, 팀감사 curator(보호 누락 3건→*_FINAL/manifest 보호 추가)+adversarial(동어반복 한계 명시).
- Remaining gap(정직): 테스트는 **분류기 계약 + 디스크 불변식**을 고정하지, 실제 `Move-Item`을 수행하는 **turn-closeout 스킬의 이동 안전성은 미테스트**(adversarial 지적). dead/superseded 자동 탐지는 머신 마커 의존(현재 마커 0개 → 후보 0). archived→trash retention 전이는 후보 플래그로 미표현(선언만).
- Closure: 스킬의 실제 이동 경로를 dry-run 통합 테스트로 커버 + 마커 운용 1회 라이브 → 검토. **첫 apply 승인 = `02 §A.4` 팀 감사(docs-memory-curator + adversarial-reality-critic) 통과 + 명시 confirm, 단독 이동 금지**(curator 지적 반영).

### R-LLMCollectBoundary · LLM 수집 라우팅/확장쿼리가 우회·rate위반·비용폭주 제안  — Severity: MEDIUM (미래, 2026-06-20 신규 — ADR#14)
- Area: ingestion/agents / LLM 수집 관여(P/G/F) / 헌법(우회 금지)
- Description: S5/S6에서 LLM이 LAYER P(라우팅·확장쿼리)에 관여하며 robots_ignore/proxy_rotation 같은 우회 전략, rate-limit 위반, 유료검색 비용 폭주를 제안할 위험.
- Current mitigation: LAYER G 결정론 게이트(`_UNSAFE_STRATEGIES` allowlist + per-event/월 budget guard) — **차단 메커니즘은 실구현**(`source_supervisor.py` `_ALLOWED_BY_LAYER`/`_UNSAFE_STRATEGIES`). off 토글(`LLM_PROVIDER=""`)로 결정론 100% 폴백.
- Remaining gap(정직, adversarial): **(1) audit trace 미구현** — `source_supervisor.py:104`는 허용 밖 LLM 제안을 *침묵 폐기*(반환값·로그 무기록). "제안·채택·거부 구조화 로깅" 완화책은 **TODO**. (2) **신규 발견 cold triage 비용**(Change Detection last_state 부재 구간)은 budget 산식 밖 → R-DiscoveryCostStarvation. (3) `llm_propose` 실 provider 미배선(현재 테스트 람다).
- Closure: off 100% 폴백 + unsafe 제안 차단 회귀 + **LLM 동적 unsafe 제안이 반환값+로그에 명시**되는 테스트 + 월 예산 상한 강제 테스트.

### R-AgentDebateSafety · 에이전트 발화 투자조언화/근거없는 단정/prompt injection  — Severity: MEDIUM (미래, 2026-06-20 신규 — S9)
- Area: agents/community / 헌법1(투자조언 금지) / R-PromptInjection 교차
- Description: Agent Debate Layer의 에이전트 발화가 ① 매수/매도·가격판단 톤(투자조언), ② evidence 없는 단정, ③ 외부 텍스트 injection에 조종될 위험.
- Current mitigation: (설계, 미구현) 발화 게이트 fail-closed — evidence_refs 필수(없으면 게시 거부) + 투자조언 톤 필터(`has_investment_advice`, publish 게이트 철학 확장) + injection 방어(EvidenceGate 확장). kill switch = `DEBATE_ENABLED=false`.
- Remaining gap: comment.py debate 컬럼 0(미구현), 페르소나 논쟁 그래프 부재. 발화 게이트 코드 부재.
- Closure: 발화 게이트 fail-closed 테스트(evidence 없는 에이전트 발화 거부) + 투자조언 표현 차단 회귀 + injection 차단 테스트.

### R-EventModelMigration · 카드→Event/Update 전환 + 3엔진 정합성 드리프트  — Severity: MEDIUM (미래, 2026-06-20 신규 — S1)
- Area: data-model / 비파괴 마이그레이션 / L5 정합성
- Description: 1회성 카드 → Event/Update 모델 전환 시 기존 카드·테스트·UI 호환성 + 신규 이중쓰기(events↔event_cards 스냅샷) 정합성 위험. event_cards 스냅샷이 자주 재생성되면 3엔진(PG/Milvus/OpenSearch) 색인 드리프트 빈도 증가.
- Current mitigation: (설계) additive 마이그레이션(신규 컬럼 nullable/신규 테이블) + 카드=스냅샷 뷰 비파괴 유지(alembic downgrade 제공).
- DONE(S2e live-PG, 2026-06-22 — 부분): **alembic 0001~0006 실 Postgres up/down 실증**(event_intel_test, ADR#21) — additive 마이그레이션·downgrade 가역이 mock 텍스트가 아니라 실 DB 에서 동작 확인. Event append E2E 도 live-PG(`test_event_resolution_live_pg`). **단 PG 단일 엔진** — 3엔진(Milvus/OpenSearch) 정합은 미터치.
- DONE(C live wiring, 2026-06-22 — 부분): Event 영속 경로(`event_ingest_pipeline`)가 events/event_updates 에 write 하되 **event_cards 는 무변경(병행)** — additive 비파괴 입증(`s.cards == {}`). 카드↔Event 가 깨지지 않음(Event 가 카드를 덮어쓰지 않음).
- Remaining gap(정직): ① **3엔진(PG/Milvus/OpenSearch) 동일 card_id 정합성 미검증** — live-PG 는 PG 만 입증. 색인 swallow(MASTER L5)와 결합 시 검색-목록 불일치(신뢰 훼손)는 그대로. Event 스냅샷 재색인 드리프트는 미배선(카드 렌더/색인 경로가 Event 와 미결선). ② **event_cards.event_id 자동 연결 이월(C, ADR#22)** — live wiring 은 events 만 만들고 카드↔Event 를 자동 연결하지 않는다(set_snapshot 명시 연결만). Event 와 card 가 분리 운영되어 "이 카드가 어느 Event 인가" 역참조가 비어 있음 — 카드↔Event 매칭 정책(ADR) 필요.
- Closure: **3엔진 동일 card_id 정합성 불변식 테스트 + 미전파 카드 메트릭(outbox SLO)**(live wiring + 색인 경로). ADR로 `cluster_event_map` 단일 진실원천 vs `event_cards.event_id` derived 결정 기록(ADR#16/#19 부분 반영, 색인 정합 잔여).

> **R-FalseMerge** — **CLOSED 2026-06-24**(ADR#39, adversarial JUSTIFIED — 직전 2턴 OVERCLAIM 잡은 동일 critic). Union-Find transitive **OVER-merge**(DISTINCT 사건 병합) 방어 완결: clique 게이트(강신호 core 만 자동 APPEND·weak_only HOLD) + held-dedup(ADR#35) + 입력순서 불변 core/gate(ADR#37) + **held 승격 title-judge(ADR#38)**. **live-PG 30/30 실증**(held 재등장 same-title→parent APPEND[중복 0]·different-title→독립 CREATE[거짓병합 0]·멱등 + 동시 CREATE orphan 0 + FK RESTRICT + transitive weak held). 거짓병합 방어: record_key exact AND title-Jaccard **2단 게이트**. 흐름·근거는 `RISK_CLOSED.md`. **⚠ 범위 한정 — OVER-merge 만.** cross-batch UNDER-merge(같은 사건이 배치마다 새 Event 로 분열 → **결과적 중복 Event**)는 **R-CrossBatchEventIdentity(아래)로 이월·미해결** — 이 종결은 "Event 중복 완전 해결" 이 아니다.

### R-CrossBatchEventIdentity · 같은 사건이 배치 경계에서 새 Event 로 분열(UNDER-merge)  — Severity: MEDIUM (신규 2026-06-24 · ADR#39 — R-FalseMerge 에서 분리; ADR#40 shared-anchor 부분종결 · ADR#41 semantic 후보 substrate 추가)
- Area: Event identity / lineage / 중복 Event / RAG·KG substrate 무결성
- Description: Event identity 가 `cluster_id = xcluster:{min(member record_keys)}`(`cross_source_dedup.py`)에 묶임. 같은 사건의 **새 corroborating 기사/공식문서가 다음 배치에 추가**되면 cluster 멤버십(최소 record_key)이 바뀌어 cluster_id 가 달라지고 → cluster_event_map 미매핑 → **새 Event CREATE → 같은 사건이 배치마다 분열**(timeline/RAG/KG/Entity graph/LLM routing 오염). R-FalseMerge(OVER-merge)의 **반대 실패모드**(UNDER-merge).
- 후보 정책(ADR#40): (A) cluster_id 안정화만(여전히 cluster 생성 의존·취약·단독 금지) (B) **cluster_id 분리 deterministic Event Identity Layer**(strong anchor→event·보수 승격·semantic hook 개방) (C) embedding/LLM semantic 즉시(mock-default·이르다·금지). **선택 B**(첫 구현 LLM 없이 보수; semantic=future).
- **DONE(ADR#40 deterministic 층, 2026-06-24):** 신규 `event_identity_map(identity_key→event_id, alembic 0007, FK RESTRICT)` — cluster_id 와 분리. `candidate_from_cluster` 가 **강신호 core**(weak_only/held 제외) ∩ publishable(official/article) ∩ strong key(canonical_url/official_id) 멤버의 record_key 를 `identity_keys` anchor 로. `map_event_identities`(CREATE/APPEND claim; WITHHELD/HOLD 미claim) + `find_events_by_identity` + `resolve_and_apply_cluster` 미매핑 CREATE 전 anchor lookup → **정확히 1개 기존 Event 면 APPEND**(cross-batch 수렴), 2개 이상(모호)→승격 안 함(잘못된 병합 0→CREATE). **live-PG 검증**: same-anchor→APPEND(분열 0)·different→CREATE(false-merge 0)·ambiguous→no-merge·idempotent·ingest E2E(같은 기사 재clustering→APPEND). held(weak_only) anchor 제외로 ADR#38 회귀 0. adversarial: false-merge hole 신규 0(anchor=기존 record_key 재사용).
- **DONE(ADR#41 deterministic semantic 후보 substrate, 2026-06-24):** 공유 strong anchor 가 없어도 같은 사건 후보를 보수적으로 **표면화**한다(병합 아님). 신규 `event_identity_candidate(candidate_key→event_id, alembic 0008, FK RESTRICT)` — `event_identity_map`(확정 anchor)과 **분리**. `semantic_identity_fingerprint(title, observed_at)`=normalized token-set(어순무관·stopword제거)+date bucket→`sem:{sha1}`(유의미 토큰<4 generic·시점불명은 None). publishable core 멤버만 fingerprint 생성. 미매핑 cluster 가 strong/held 승격에 안 잡히고 fingerprint 가 **정확히 1개** 기존 Event 를 가리키면 → CREATE 후 `event_links(possible, reason='semantic_cross_batch_candidate')` 로 **LINK 만**(자동 APPEND/merge 0 = false-merge surface 0), 2개+(모호)→링크 안 함. **live-PG 검증(ADR#40 과 대칭)**: same-fingerprint→링크(병합 0·events 2)·ambiguous→링크 0·no-match→독립 CREATE·non-publishable(community) fingerprint→WITHHELD(claim/link 0). adversarial JUSTIFIED(safety 단단·false-merge 0).
- **⚠ 부분종결 — 닫힌 범위 vs 미해결(정직, adversarial 강제):**
  - **닫힌 범위(병합):** deterministic **shared-anchor** cross-batch identity — publishable core 가 **동일 canonical_url/official_id** 재등장(syndicated wire). 기존 Event 로 APPEND(실제 병합·분열 0). live-PG 입증(ADR#40).
  - **닫힌 범위(후보 substrate):** **공유 anchor 없는** 같은 token-set+같은 날 publishable 후보를 `event_links(possible)` 로 **표면화**(ADR#41). live-PG 입증.
  - **⚠ 미해결(여전히 OPEN) — 핵심:** ADR#41 은 **LINK 만 — 중복 Event count 는 1건도 줄지 않는다**(실제 병합 아님). 같은 사건은 여전히 N개 Event 로 분열돼 있고, 후보 관계만 가역적으로 기록된다. **실 병합(count 감소)·패러프레이즈/동의어/다국어 동일성**은 semantic adjudicator(embedding/LLM/KG, mock-default·미구현) 필요 → **종결 아님.** "후보 substrate 추가"를 "중복 해결/진전"으로 오기록 금지.
  - **⚠ LINK 소비처 0(정직):** `event_links(possible, semantic_cross_batch_candidate)` 를 읽는 downstream 은 현재 0개(RAG/KG/adjudicator 미구현) — 미래 adjudicator 가 재판정할 가역 raw substrate 로 보존(append-only·possible→confirmed/rejected/merged). closure 조건이 R-SemanticIdentityAdjudicator 에 명시돼 있어야 "죽은 LINK" 가 아님.
  - **⚠ fingerprint 보수성 한계:** token-set(어순무관) 매칭은 같은 4+토큰의 다른 의미 배열을 같은 fingerprint 로 볼 수 있음(같은 날 한정·LINK 만이라 피해 1행). **한국어 어절 토큰화(`_TOKEN`)에서 4-임계는 언어별 캘리브레이션 근거 없음**(영어 4토큰≠한국어 4어절; 주로 재현율=한국어 사건 놓침 위험) — adjudicator 단계 캘리브레이션 이월.
  - **잔여 false-merge 주의(ADR#40 부터):** canonical_url fragment 제거 시 같은 URL=다른 사건(live-blog) cross-batch 오APPEND 가능(기존 record_key 한계의 확장; 모니터링).
- Closure: semantic/entity adjudicator(R-SemanticIdentityAdjudicator) 구현으로 **실 병합→중복 Event count 감소 입증** + fragment 오APPEND 가드. **RAG/KG 이전 필수 gate**(substrate 분열은 downstream 오염). severity MEDIUM(deterministic 층으로 syndication 병합·shared-anchor 케이스는 닫힘·후보는 표면화).

### R-SemanticIdentityAdjudicator · 공유 anchor 없는 같은-사건 실 병합 미구현(후보·shadow 판정만)  — Severity: MEDIUM (신규 2026-06-24 · ADR#41 분리; ADR#42 shadow consumer 부분 진전)
- Area: Event identity 실 병합 / 중복 Event 감소 / RAG·KG substrate / semantic adjudication
- Description: ADR#41 deterministic 층은 공유 anchor 없는 같은-사건을 `event_links(possible)` 후보로 **표면화만** 한다 — **중복 Event count 는 줄지 않는다**. 후보를 실제 병합(또는 기각)해 중복을 해소하려면 패러프레이즈/동의어/다국어/엔티티 기반 동일성 판정이 필요하고, 이는 embedding/LLM/KG adjudicator(현재 `EMBEDDING_PROVIDER=mock`·`LLM_PROVIDER=mock`·미구현)를 요구한다. **이 RISK 는 R-CrossBatchEventIdentity 의 종결 구실이 아니다**(분리는 실 병합 잔여를 정직하게 추적하기 위함 — ADR#41 논거 선행).
- 후보 정책(ADR#42 §3): (A) **deterministic adjudicator shadow mode**(이번 턴 DONE — LINK 소비·status 산출·자동 병합 0) (B) future embedding/LLM `semantic_score` hook interface(slot DONE·provider 미배선) (C) **automatic semantic APPEND 즉시 도입 금지**(평가셋/threshold/precision 미비 → shadow/offline 먼저). production merge 금지.
- **부분 진전(ADR#42 deterministic shadow adjudicator, 2026-06-24):** 신규 `semantic_identity_adjudicator.py` + `event_identity_adjudication(link_id PK→event_links FK RESTRICT, alembic 0009)` 가 possible-link 를 소비해 deterministic feature(title Jaccard·date_distance·source_type·multiple_candidates·언어·generic)로 status(likely_same/ambiguous/likely_different/insufficient) 산출·idempotent 영속. **자동 병합 0**(events/updates/map 미변경·read+adjudication write only)·**API 미노출**·source role guard(community/market/catalog/unknown→insufficient/fail-closed). live-PG 검증(소비·Event count 불변·idempotent·ambiguous). adversarial: safety(병합 0·노출 0·idempotent·guard) JUSTIFIED·HIGH 결함 0.
- Current mitigation: `event_links(possible)` 가역 raw substrate + deterministic shadow status(eval substrate). false-merge surface 0(병합 0).
- Remaining gap(정직, adversarial): ① possible 링크 소비 adjudicator → **deterministic shadow 부분 해소(ADR#42)**; embedding/LLM/KG 실 adjudicator 잔여 ② 실 병합으로 중복 Event count 감소 **미해소**(auto_merged 항상 0) ③ fingerprint 한국어 어절 4-임계 캘리브레이션 **미해소**(ADR#42 가 임계 상속·이월 약속 미이행; stopword 영어전용·한국어 likely_same 단위 테스트만 추가) ④ offline 평가셋·precision/recall 기준 **부분 해소**(ADR#43 harness + ADR#44 gold loader/readiness — fixture 0.57·gold 0.6 측정·merge gate 미달 입증; **실 병합·production gold 잔여** → R-IdentityEvalDataset·R-IdentityHumanLabeling) ⑤ adjudication 테이블 소비처 = ADR#43 워크시트 export → ADR#44 gold 승격 workflow(코드 DONE·실 라벨 0; shadow substrate 로서 정당).
- Closure: embedding/LLM/KG adjudicator + 실 병합으로 **중복 Event count 감소 입증**(live-PG) + 언어별 fingerprint 캘리브레이션 + labeled 평가셋 precision 입증 + production gate(P/G/F·unsafe 차단) + **MERGE_GATE 런타임 배선**(gate 통과 없이 merge 함수가 raise — 문서적 약속이 코드로 우회되지 않게; ADR#43 adversarial). **deterministic shadow 만으로 종결 금지** — 실 병합·평가셋 없이는 "측정 불가 라벨". RAG/KG 이전 필수 gate 유지(실 병합 미입증).

### R-IdentityEvalDataset · semantic adjudication 라벨이 self-labeled 라 precision 측정 불가  — Severity: MEDIUM (신규 2026-06-24 · ADR#42; ADR#43 harness 부분 진전; ADR#44 gold loader/separation/readiness 부분 진전)
- Area: semantic identity 평가 / eval dataset / adjudicator precision-recall
- Description: ADR#42 `event_identity_adjudication` status 는 deterministic heuristic **출력**이라 self-labeled — 자기 precision/recall 측정 불가. 미래 embedding/LLM adjudicator·임계 캘리브레이션 평가에 **독립 gold label** 필요.
- **부분 진전(ADR#43 harness, 2026-06-24):** 신규 `identity_eval_dataset.py`(EvalPair·`load_eval_pairs` JSONL allowlist[raw body/PII 차단]·`evaluate_adjudicator`=precision/FPR/recall/coverage + by_language/source_type/risk_tag) + `fixtures/identity_eval_pairs.jsonl`(22 pair 진단 세트·4사분면·KO/EN/mixed·risk tags) + `export_identity_eval_pairs.py`(adjudication→human-labeling 워크시트·소비처). **측정 결과(정직):** 현재 deterministic adjudicator precision **0.57**·FPR **0.2**·hard-neg FP **3**·recall 0.57·KO precision 0.67 → **merge gate(precision≥0.98·FPR≤0.01·hard-neg FP=0) 미달**·`auto_merge_enabled=False`(불변). adversarial JUSTIFIED(병합 0·PII 차단·정직 미달 보고).
- **부분 진전(ADR#44 gold loader/separation, 2026-06-24):** 신규 `identity_human_labeling.py` 가 **gold set loader/evaluator**(`load_gold_pairs`·`evaluate_adjudicator_on_gold`)·**fixture vs gold 분리**(`compare_fixture_vs_gold_metrics`·`dataset_source` synthetic|live)·**merge readiness 산출**(`evaluate_gold_merge_readiness`=live gold만·표본 floor·auto-merge OFF)·KO/mixed breakdown 을 제공. sample gold(11 gold 행): precision 0.6·FPR 0.33·KO 0.5·hard-neg FP 2 → gate 미달. **측정 도구는 gold 까지 확장됐으나 실 production gold 는 여전히 0.**
- **⚠ 미해소(OPEN, adversarial):** ① fixture 는 **진단(stress) 세트** — production precision 대표 표본 아님(0.57≠운영 precision)·통계 규모 부족(22 pair) ② **live-derived + human-labeled** gold set 0개(ADR#44 샘플은 hand-authored 시연) ③ 워크시트→gold 승격 **workflow 코드는 ADR#44 로 DONE**·실 human labeling 운영(담당/SLA/agreement) **부재**(→R-IdentityHumanLabeling) ④ 한국어 캘리브레이션은 **측정만**(0.67·gold 0.5 재확인)·실제 교정(stopword/어절 임계) **미이행**(gap 또 이월) ⑤ MERGE_GATE 는 현재 **장식**(merge 코드 미존재·런타임 배선 없음)·표본 floor=draft placeholder.
- Current mitigation: harness(fixture + gold loader) + 진단 fixture + sample gold + status/언어 분포 report + readiness 산출 — 측정 도구는 작동하나 production gold 아님.
- **부분진전(ADR#45 표본 floor 통계 추정, 2026-06-24):** `estimate_sample_floor_for_precision/fpr`(normal-approx n=z²p(1−p)/e²) 추가 — precision 0.98±0.02→189·FPR 0.01±0.01→381. 기존 200/50 draft 가 양성 floor 와 같은 자릿수임을 보이고 KO 50·음성 floor 가 낙관적임을 정량화(magic number→근거 있는 값 대체 착수). **여전히 운영 합의 전·실 gold 0.**
- Closure: **live-derived + human-labeled** identity pair set(통계 규모) + production precision/recall 측정 + 한국어 실 캘리브레이션 + MERGE_GATE 런타임 배선 + 표본 floor 신뢰구간 합의(추정기 DONE·합의 미완). **harness 구축 ≠ gold set 충족** — 완전종결 금지(fixture/sample 만으로 닫으면 OVERCLAIM).

### R-IdentityHumanLabeling · 워크시트→gold 승격 workflow + reviewer agreement protocol + labeling packet(코드 DONE·실 production gold/agreement 0)  — Severity: MEDIUM (신규 2026-06-24 · ADR#43 — adversarial 권고; ADR#44 workflow 부분종결; ADR#45 reviewer agreement protocol 부분진전; ADR#46 labeling packet scaffold 부분진전)
- Area: semantic identity 평가 / human labeling / gold set 승격
- Description: ADR#43 `export_identity_eval_pairs` 가 `event_identity_adjudication`(소비처 0이던)을 워크시트 JSONL(label='unlabeled')로 소비했으나, **사람이 gold label 을 채워 승격하는 workflow(provenance 검증·gold-only metric·라운드트립)가 없어** 워크시트가 또 다른 휘발성 산출물이 될 수 있었다(dead-data 형태 변환). 즉 "소비처 추가로 dead-data 감소"는 human labeling 이 실재해야만 참.
- **부분종결(ADR#44 workflow, 2026-06-24):** 신규 `identity_human_labeling.py` — `GoldPair`(provenance reviewed_by/reviewed_at/review_status/label_confidence + dataset_source synthetic_fixture|live_derived 분리자)·`load_gold_pairs`(provenance 필수·enum·reviewed_at ISO·중복·raw body/PII/워크시트 보조키 차단)·`promote_worksheet_to_gold`(보조키 제거·사람이 label 강제=self-label 금지)·`evaluate_adjudicator_on_gold`(review_status='gold'만; needs_review/rejected 제외)·`generate_gold_eval_report`/`compare_fixture_vs_gold_metrics`/`summarize_labeling_backlog`·`evaluate_gold_merge_readiness`(**live_derived gold만** MERGE_GATE + 표본 floor·`auto_merge_enabled=False` 불변). + `fixtures/identity_gold_pairs.sample.jsonl`(13행 **시연 샘플**). unit 30 + live-PG 3. adversarial JUSTIFIED(safety·provenance·PII·metric 수동 재현 일치·오라벨 0·BUG 0).
- **부분진전(ADR#45 reviewer agreement protocol, 2026-06-24):** `identity_human_labeling.py` 확장 — `ReviewerLabel`(reviewer_id·review_round·**reviewer_kind[human only]**)·`load_reviewer_labels`(model/self/llm/adjudicator label 거부·중복 거부·PII 차단)·`resolve_gold_from_reviewers`(1명=insufficient·2+전원합의=agreed·불일치+adjudication=adjudicated·**불일치=conflict[자동 gold 금지]**·`_validate_adjudication` 으로 LLM-as-judge 차단)·`resolved_to_gold_pairs`(agreed/adjudicated만)·sampling bucket(12+미분류 경고)·`estimate_sample_floor_for_precision/fpr`(normal-approx: precision 0.98±0.02→189·FPR 0.01±0.01→381)·`generate_labeling_protocol_report`. + `fixtures/identity_reviewer_labels.sample.jsonl`(16행 시연). unit 31 + live-PG 4. adversarial JUSTIFIED·MEDIUM 2 수정(adjudication LLM 뒷문·insufficient bucket 공백).
- **부분진전(ADR#46 labeling packet scaffold, 2026-06-24):** `identity_human_labeling.py` 확장 — `build_labeling_packet`(live 워크시트→bucket 샘플링→reviewer ≥2 배정→**predicted_status/score/reason 차폐**=bias 0)·`validate_labeling_packet`(verdict 누출·raw body/PII·enum fail-loud)·`labeler_facing_view`(bucket+판정 제거)·`summarize_packet_sampling`(deficit/oversample/floor 대조·`selection_method` 명시)·`adjudication_queue_from_resolved`(conflict→human-only 큐). + `fixtures/identity_labeling_candidates.sample.jsonl`(16행·15 bucket). adversarial **HIGH 1 수정**(`export_identity_eval_pairs._to_eval_source_type`: evidence 'signal'→eval 'market' — 라이브 market 후보 packet 진입 가능)·MEDIUM 2 보완. unit 26 + eval +1 + live-PG 5. **packet 은 reviewer label→gold 입력 scaffold·gold 아님**.
- Current mitigation: 승격 경로(export→promote→write→load→evaluate) + reviewer agreement protocol(합의/conflict/adjudication resolution) + labeling packet(bucket 샘플링·reviewer 배정·verdict 차폐) 코드·테스트로 동작 입증·결정론·Event 불변. raw body/PII/self-label/model-label/보조키/model 판정 누출 구조적 차단.
- Remaining gap(정직, adversarial): ① **실 human-reviewed production gold 0**(샘플은 hand-authored 시연 — 실 reviewer 검수·통계 규모 0) ② human labeling 담당/절차/SLA 0 ③ **reviewer agreement 실측 0**(protocol 코드는 DONE·실 다중 reviewer 합의 데이터 0 → R-ReviewerAgreement) ④ sampling 대표성 실데이터 0(→ R-GoldSamplingBias) ⑤ 주기적 export→label→eval 루프 미배선 ⑥ 표본 floor(live 200/KO 50)=추정기 추가됐으나 운영 합의 전(KO 50 낙관적).
- Closure: **실 human-reviewed live-derived gold 누적**(통계 규모) + human labeling 운영 절차/SLA + reviewer agreement 실측(R-ReviewerAgreement) + sampling 대표성(R-GoldSamplingBias) + 표본 floor 합의 + export→label→`evaluate_adjudicator_on_gold` 주기 루프. **protocol 코드 ≠ 실 gold/실 agreement** — 코드만으로 완전종결 금지(OVERCLAIM).

### R-ReviewerAgreement · 다중 reviewer 합의 실측·운영 절차 부재(protocol+packet 코드만)  — Severity: MEDIUM (신규 2026-06-24 · ADR#45 — adversarial 권고; ADR#46 packet scaffold 부분진전; ADR#47 live-PG 백로그 적용 부분진전)
- Area: semantic identity 평가 / human labeling / reviewer 합의 신뢰도
- Description: ADR#45 `resolve_gold_from_reviewers` 가 다중 reviewer 합의(agreed)·conflict(자동 gold 금지)·adjudication 을 resolution 하는 **protocol 코드**를 제공하나, **실제 다중 reviewer 가 같은 pair 를 검수한 합의 데이터·inter-reviewer agreement 실측이 0**이다. 단일 reviewer gold 의 신뢰는 한 사람 편향/오류로 무너질 수 있어, 합의 실측 없이는 gold precision 을 production 으로 주장할 수 없다.
- **부분진전(ADR#46 packet scaffold, 2026-06-24):** `build_labeling_packet`(live 워크시트→reviewer **배정** packet·동일 pair distinct ≥2명 round-robin)·`adjudication_queue_from_resolved`(conflict→사람 lead 배정 큐·label 미탑재·human adjudicator only)·`labeler_facing_view`(model 판정·bucket 차폐=bias 0)·packet→reviewer label→resolve roundtrip 테스트. 즉 **실 다중 reviewer 검수를 시작할 운영 도구**가 생겼다(실 합의 데이터는 여전히 0). adversarial JUSTIFIED(HIGH 1 수정·MEDIUM 2 보완).
- **부분진전(ADR#47 live-PG 백로그 적용, 2026-06-24):** `build_live_identity_labeling_packet.py`(read-only)가 위 reviewer 배정/roundtrip 을 **synthetic fixture 가 아니라 실 파이프라인 유래 live-PG adjudication 백로그**에 적용(live-PG 테스트 `test_live_tool_*`: link→adjudication→eligible 1·reviewer item 2·conflict→queue·Event 불변). 실 합의/SLA/담당은 여전히 0(완전종결 금지).
- Current mitigation: percent-agreement 산출·conflict no-auto-gold·만장일치만 agreed(2:1 다수결→conflict)·model/self/LLM adjudicator label 거부(fail-loud)·reviewer ≥2 배정 packet·conflict adjudication 큐 — 코드·테스트로 안전 잠금.
- Remaining gap: ① 실 다중 reviewer 합의 데이터 0 ② Cohen kappa(규모 확보 후) 미산출 ③ reviewer 운영 절차/SLA/충원 0 ④ conflict adjudication 담당(사람 lead) 미배치 ⑤ reviewer_id PII redaction/hashing 정책 미확정.
- Closure: 실 다중 reviewer 합의 데이터(통계 규모) + agreement rate/kappa 실측 + reviewer 운영 절차 + adjudication 담당. **합의 protocol/packet 코드 ≠ 합의 실측** — 코드만으로 종결 금지.

### R-GoldSamplingBias · gold sampling 대표성·oversampling 실데이터 부재(bucket+packet 코드만)  — Severity: MEDIUM (신규 2026-06-24 · ADR#45 — adversarial 권고; ADR#46 packet sampling 부분진전; ADR#47 bucket-hash 표집·live backlog report 부분진전)
- Area: semantic identity 평가 / gold set 대표성 / sampling
- Description: ADR#45 `assign_sampling_bucket`/`summarize_sampling_buckets` 가 12 bucket(likely_same/hard_negative/KO/mixed/community/market/catalog/far_date/...)으로 pair 대표성을 추적하는 **코드**를 제공하나, **실데이터가 없어 bucket 별 충원·hard-negative/KO oversampling 이 실행되지 않았다**. 대표성 없는 gold 는 쉬운 영어 positive 만 쌓여 precision 을 과대평가하고 한국어/hard-negative 실패모드를 평균 뒤에 숨긴다.
- **부분진전(ADR#46 packet sampling, 2026-06-24):** `assign_candidate_bucket`(라벨 전 15 candidate bucket·가드 우선)·`summarize_packet_sampling`(selected/deficit/oversampled/underfilled·by_language/source_type/risk_tag·live_vs_synthetic·표본 floor 대조[189/381]·hard_negative/ambiguous/KO oversample target). deficit 를 **숫자로** 노출(평균 뒤 숨김 0)·synthetic 은 live floor 미부풀림. **단 selection 은 무작위 아닌 `deterministic_pair_id_order_cap`**(대표성 미입증·정직 표기). adversarial HIGH 수정: evidence 'signal'→eval 'market' 정규화(market_guard 라이브 진입 가능).
- **부분진전(ADR#47 옵션 D + live backlog report, 2026-06-24):** `SELECTION_BUCKET_HASH`(=`deterministic_bucket_hash_cap`·sha256(pair_id) 정렬) 추가 — over-cap bucket 에서 낮은 pair_id 정렬 편향을 완화(재현 가능·결정론·테스트로 order≠hash divergence 입증). `build_live_identity_labeling_packet.generate_live_packet_report` 가 live-PG 백로그 기준 `selected_by_bucket`/`deficit_by_bucket`/`exclusion_reasons`/`live_vs_synthetic`/floor 를 산출. **단 효과는 over-cap 에서만(현 1행 규모 nil)·실 충원/대표성 0**·`dataset_source` 부재→live default 는 fail-open(gold floor 충당 시 fail-closed 재검토·운영 메모). 완전종결 금지.
- Current mitigation: bucket 결정론 배정·미분류(other) 경고·draft min target(20)·insufficient/guard 전용 bucket 라우팅·deficit/oversample/floor 대조 report — 코드·테스트로 가시화.
- Remaining gap: ① 실 sampling 데이터 0 ② bucket 별 충원·oversampling 미실행 ③ min target 통계 근거 미확정(placeholder) ④ 대표성 검증 절차 0 ⑤ selection=정렬 cut-off(무작위 표집 아님 — 대표성 미보장).
- Closure: 실 live-derived sampling + bucket 별 충원(hard-negative/KO/mixed oversample) + min target 통계 근거 + 대표성 검증(무작위/층화 표집). **bucket/packet 코드 ≠ 대표 표본** — 코드만으로 종결 금지.

### R-LiveIdentityBacklog · live-derived identity candidate/adjudication 백로그 자체가 0(packet pilot 이 읽을 실 운영 후보 부재)  — Severity: MEDIUM (신규 2026-06-24 · ADR#47 — 실 probe 확정 blocker; ADR#48 stage③ 배선+migration readiness 부분진전; ADR#49 incremental/no-cluster backfill+runbook 부분진전[gap②③ 해소]; ADR#50 keyset/backfill 운영 CLI/deploy checklist/scheduler idiom 부분진전[gap③④ 추가 진전]; ADR#51 scheduler-ready preflight/exit-code/created_at 시간순 cursor/scheduler 스크립트 부분진전[gap④ scheduler-ready·미가동]; ADR#52 docker scaffold profile-gated·dry-run default 부분진전[gap② docker 배선·미가동·index/lock DEFER]; ADR#53 docker build/up dry-run 실측[3경로 exit 2/1/0·ingestion COPY 런타임 버그 발견·수정·live-PG 91p 재실행] 부분진전[gap② docker 실행성 입증·실가동 0]; ADR#54 production activation preflight + real-source identity smoke 부분진전[운영 DB boundary·safe-target no-op 표면화·단계별 진단 tool·fake-default·점검/진단≠가동]; ADR#55 real-source live-db smoke 부분진전[실 federal_register fetch 5 official→event_intel_test(head 0009) ingest: created 1·identity_link 1·adjudications 0·packet_eligible 0·source quality matrix·agent readiness 9조건; source scarcity 분해·live_network=opt-in tool·live_db=disposable test DB≠production·production 백로그 0 불변])
- Area: semantic identity 평가 / live-derived labeling 운영 / 실 source loop
- Description: ADR#47 packet pilot(`build_live_identity_labeling_packet.py`)은 live-PG `event_identity_adjudication ⋈ event_links(semantic)` 백로그를 읽어 packet 을 만든다. 그러나 **실 probe 결과 백로그가 0**: ① 운영 DB `event_intel` 가 **미마이그레이션**(relation 없음 — 실 ingest 영속 0) ② 단계 ③ shadow adjudication(`adjudicate_semantic_links`)이 **live 루프 미배선**(production 호출자 0 — `apply_routing` 은 단계 ①anchor·②fingerprint/link 까지만; 단계 ③는 test/도구 수동 호출만). 따라서 packet pilot 은 **운영 자동 산출 후보가 0**이고, live_selected>0 은 테스트가 단계 ③를 수동 실행해야만 성립한다(도구가 `exclusion_reasons.semantic_link_without_adjudication` 로 정직 표면화).
- **경계(중첩 RISK 와 구분):** 이 RISK 는 위 두 잔여의 **결합이 packet pilot 운영성을 막는다**는 점을 단일 추적한다 — (a) 운영 DB 미마이그레이션·주기 trigger 잔여는 **R-RealSourceLoopUnproven**(register §R-RealSourceLoopUnproven 잔여 "운영 DB 0006 미배포")에서, (b) 단계 ③ adjudication 의 실 병합·임계 캘리브레이션은 **R-SemanticIdentityAdjudicator**(gap ①②③⑤)에서 각각 추적 중. R-LiveIdentityBacklog 는 그 둘을 **중복 등재하지 않고** "live labeling packet 이 읽을 실 백로그를 채우는 운영 배선"이라는 교차 목표만 본다(R-LabelingPacketOps 처럼 도구 자체가 아니라 **데이터 부재**가 blocker).
- **부분진전(ADR#48 stage③ operational wiring + migration readiness, 2026-06-24):** ② 단계 ③ 배선 — `event_ingest_pipeline.ingest_records_to_events(adjudicate_semantic=)` 가 클러스터 루프 뒤 flag(`EVENT_SEMANTIC_ADJUDICATION_ENABLED`, off-by-default) on 이면 `adjudicate_semantic_links`(③)를 배치 전역 1회 자동 실행 → event_identity_adjudication 백로그 자동 누적(자동 병합 0·shadow write only·link_id PK 멱등). live-PG E2E: ingest(adjudicate_semantic=True)→adjudication 1 자동→packet eligible 1·**live_selected 1(운영 loop 유래·synthetic/수동 아님)**·Event 불변. ① migration readiness probe(`identity_backlog_readiness.py`·read-only): 운영 DB **0003 vs head 0009 = 6 revision 뒤(upgrade additive·non-destructive)**·identity 테이블 부재 정량화. **단 운영 DB upgrade 미적용**(배포 행위)·실 fetch 0 → production 백로그 여전히 0. adversarial JUSTIFIED(no-merge·off-path load-bearing·과잉 종결 0).
- **부분진전(ADR#49 incremental / no-cluster backfill + runbook, 2026-06-24):** gap②③ 해소 — (gap②) `ingest_records_to_events` 의 `if not clusters: return` **제거** → 클러스터 0 배치도 stage③ backfill 실행(이전 배치 미판정 pending link 처리). 신규 `backfill_semantic_adjudications.py`(read/write adjudication only·dry-run·bounded limit·event count before-after)로 누적 백로그를 주기 job/수동 따라잡기 가능. (gap③) `adjudicate_semantic_links(only_unadjudicated=, limit=)` **incremental** — 비싼 per-link Event view load+persist 를 **미판정 link 만**으로 한정(매 배치 전수 재판정 회피). **ambiguity 정확성 불변**(cand_targets 는 incremental 필터 전 전체 link 로 산출·회귀 가드 테스트). 운영 DB 0003→0009 배포 **runbook**(`15_IMPLEMENTATION_ROADMAP.md`)·flag 순서 문서화. adversarial 코드 JUSTIFIED.
- **부분진전(ADR#50 backfill operation hardening + deploy checklist, 2026-06-24):** gap③④ 추가 진전 — (gap③) `_semantic_links`/`adjudicate_semantic_links(after_link_id=)` 가 **keyset**(`WHERE id>cursor·NOT IN adjudication·LIMIT`)을 SQL 로 push → bounded run 의 cheap O(전체) 메모리 적재 회피(페이지만 로드). **ambiguity 정확성은 page candidate 한정 GROUP BY(`_candidate_target_counts`)로 link별 status 동작 보존**(기존 78 live-PG 무회귀). unused `_adjudicated_link_ids` 제거. **정직(adversarial HIGH②)**: `event_links.id`=**UUIDv4(랜덤)** → cursor 는 byte 순서·**시간순 아님**(재현 가능 페이지 경계일 뿐)·진행 중 INSERT 는 cursor 아래로 떨어질 수 있어 **백로그 진행/완전성 보장은 cursor 가 아니라 only_unadjudicated**·limit/cursor 미지정 전수 경로는 `full_scan=True` 표면화(즉 gap③ 은 *완화*이지 해소 아님). (gap④) 교차 backfill 은 link_id PK upsert 로 **중복행 0(데이터 안전)** — 2-세션 교차 backfill live-PG 검증·중복 work 는 단일 runner/disjoint cursor 권고(docs)·**lock 과대주장 안 함**(report `idempotent_persist=True`·`lock` 키 없음). **정직(adversarial HIGH③)**: PK upsert 무중복은 deterministic classifier+last-writer-wins 라 무해한 것·양쪽 `ORDER BY id asc` 동일 잠금순서로 ABBA 회피(설계)·**OS-병렬 race/deadlock 은 stress-test 안 됨**. `backfill_semantic_adjudications` **운영 CLI**(`--limit/--after-link-id/--dry-run`·`assert_safe_write_target` 가드·`next_cursor`/`full_scan`/`idempotent_persist` report). `build_operational_deploy_checklist`(0003→head 명령 문자열·`backup_required`·`executed=False`)+readiness read-only CLI(`python -m …identity_backlog_readiness`). 주기 가동은 **새 scheduler 발명 불필요** — 기존 `run_recovery_scheduler --once`/docker `recovery-scheduler` 관용구 **재사용 가능(설계·미배선·운영 DB migration 후 게이트)**(backfill 은 자체 `--once` CLI 일 뿐 recovery-scheduler 에 미배선). adversarial 코드 JUSTIFIED(ambiguity 정확성 VALID·정직성 3건[②UUIDv4 cursor·③테스트·⑧scheduler 서사] 본 갱신에 반영).
- **부분진전(ADR#51 backfill scheduler operationalization, 2026-06-25):** gap④ scheduler-ready + 시간순 cursor — (preflight) `backfill_preflight`+`run_backfill_with_preflight`: **ready_for_stage3 hard gate**(운영 DB 0003 adjudication 테이블 부재 시 dry-run 포함 차단 — backfill 쿼리 크래시 방지) + **flag persist gate**(`EVENT_SEMANTIC_ADJUDICATION_ENABLED` off 면 persist 만 차단·dry-run 은 read-only 허용·`allow_flag_off` 우회). (exit code) `decide_exit_code` 0=성공/1=blocked/2=runtime/3=dry-run pending(scheduler/cron 결정론 관측). (cursor) **`event_links.created_at` 활용 `cursor_mode='created_at'`**(`or_(created_at>cur, and_(created_at==cur, id>after_link_id))` 컬럼 비교·행값 `tuple_` 는 UUID 타입강제 실패→교체·`next_created_at` report) → **오래된 백로그 우선**(직전 "UUIDv4 시간순 불가" 한계 정정). **정직**: created_at=txn 시각 → **배치 간만** 시간순 정확(동일 배치 intra-txn 동일 timestamp→id tie-break·임의)·created_at 인덱스 없어 정렬 비용. (scheduler) `workers/tools/run_semantic_backfill_scheduler.py`(recovery-scheduler 관용구 복제·preflight gated·**dry-run default·--limit 기본 100·docker 미배선·미가동**). live-PG: created_at 시간순(id 역순 입증)·복합 cursor resume(중복 0·소진)·preflight flag on/off persist gate·dry-run flag-무관 허용·Event 불변(자동 병합 0). 구현 중 복합 cursor `uuid>varchar` 타입 버그 self-found+fixed(live-PG)·adversarial critic 검증 반영.
- **부분진전(ADR#52 production scheduler activation readiness — docker scaffold, 2026-06-25):** gap② docker 배선 — scheduler 가 compose 서비스 `semantic-backfill-scheduler` 로 배선됨: **`profiles: ["backfill"]`(기본 `docker compose up` 미기동)·dry-run default(command --persist 부재)·preflight gated·단일 instance(replicas 미설정·`restart: "no"`)**. **worker 이미지 불가→backend 이미지 재사용**(workers/Dockerfile 은 services/tools/models 미COPY)·entrypoint override(entrypoint.sh 의 alembic+uvicorn 대신 scheduler 모듈)·`DATABASE_URL` env. **옵션 C(created_at index)·D(advisory lock)는 근거와 함께 DEFER**: C=backlog 0·prod 0003 에서 순수 미래-스케일 최적화인데 추가 시 test 하드코딩 head/카운트 churn → DDL(`ix_event_links_created_at_id (created_at,id)`) runbook 문서화(적용 시점=백로그 유의미); D=데이터 안전 이미 보장+단일 instance docker 가 중복 work 운영 차단 → lock 은 설계가 이미 막는 시나리오의 defense-in-depth(DB결합/test비용)·single-instance 요건 runbook 명시. **코드 변경 0**(docker-compose.dev.yml + compose 일관성 테스트 5만·파이썬 source 0). 측정(정직): backend 비-live(live-PG 2파일 제외) **459 passed/4 skipped/0 failed**(신규 compose 5 포함·`docker compose config` 로 default 목록 scheduler 부재·--profile 시 포함 실증)·ingestion 1353·frontend tsc0/test12/lint0; **live-PG(91p)는 docker(PG) 미가동으로 이번 턴 미재실행**(live-PG 코드 경로·기존 서비스 정의 미변경→회귀 risk 0). **단 scheduler 실가동 0**(profile 비활성·운영 DB 0003·flag off)·docker 정의 build/up 미검증(정적 일관성 테스트만). **adversarial-reality-critic: VALID(정직성 양호)·4대 안전계약 성립·HIGH 0·코드 버그 0**; **MEDIUM-1**(scheduler APP_ENV 부재+DATABASE_URL=dev event_intel→safe-target 이 이 경로엔 사실상 no-op·안전은 dry-run+preflight 책임·실 persist 가동 선결에 별도 운영 DB+APP_ENV=production+--allow-non-dev-db 필요)·**MEDIUM-2**("단일 instance 차단"→"단일 runner 규율 가정"·--scale/수동 CLI 병행 우회 가능·데이터 안전 무관) **정정 반영**.
- **부분진전(ADR#53 production scheduler activation VALIDATION — docker build/up dry-run 실측, 2026-06-25):** gap② docker **실행성 실측 입증**(ADR#52 "정적만" 한계 해소) — Docker daemon UP·옵션 A 실행: `docker compose --profile backfill build` 성공·`run --once --limit 5` **3경로 실측**(①DB down→부팅·import·safe-target 후 graceful **exit 2** ②미마이그레이션 DB→`BLOCKED block=readiness ready_for_stage3=False`→**exit 1**[write 0] ③dev DB head 마이그레이션 후→`cycle ran dry_run=True processed=0 pending 0->0 event_count 0->0 auto_merge=False`→**exit 0**)·`docker compose config` profile 격리(default 11·--profile 12). **🔴 정적 검증이 못 잡은 런타임 버그 발견·수정:** `backend/Dockerfile` 이 `ingestion/` 미COPY → adjudicator 의 `ingestion.orchestration.cross_source_dedup` 전이 import 가 컨테이너 런타임에 `ModuleNotFoundError`(compose config·5 테스트·build 통과·**run 만 죽음**) → `COPY ingestion/ ingestion/` 추가 + 회귀 테스트 2(`test_backend_image_copies_ingestion_for_adjudicator`·`test_scheduler_allow_non_dev_db_overrides_safe_target`). **live-PG `test_event_resolution_live_pg` 91 passed**(ADR#52 PG 미가동 미실행→이번 턴 `event_intel_test` head 대상 재실행). **정직(adversarial MEDIUM):** run#3 `event_count 0->0` 은 dev DB 가 비어서(pending 0)이지 read-only 입증 아님 — read-only 는 코드(`_persist_adjudication` adjudication-only)+live-PG 91p(Event count 불변)가 입증; live-PG 91 은 **DB orchestration 정확성** 입증이지 scheduler 주기 가동/실 백로그 아님. 검증 위해 dev event_intel 을 c3d4e5f6a7b8→head 마이그레이션(운영 DB 아님·additive). adversarial **CONDITIONAL VALID**(코드·안전계약 VALID·HIGH-1[ADR#53 문서 미반영]은 본 갱신·PROJECT_STATUS·_DECISIONS [#53] 로 해소). **여전히 scheduler 실가동 0**(one-shot dry-run 만·profile 비활성·운영 DB 0003·flag off)·production 백로그 0.
- **부분진전(ADR#54 production activation preflight + real-source identity smoke, 2026-06-25):** 운영 가동 전 통합 점검 + 단계별 진단 — `production_activation_preflight.py`(read-only·DDL/upgrade/persist 0)가 readiness+flag+safe_target+classify 를 **하나의 17필드 report** 로 묶어 `can_dry_run`/`can_persist`·`block_reasons`·`next_required_actions` 산출. `can_persist = persist ∧ ready ∧ (flag∨allow_flag_off) ∧ safe_target ∧ ¬destructive ∧ (consistent∨allow_non_dev)`. `db_target.classify_write_target` 신설(dev/test/staging/production/unknown named 분류 + APP_ENV↔URL mismatch — URL prod-marker 가 APP_ENV 보다 위험하면 채택·**dev event_intel safe-target no-op[MEDIUM-1]을 warning 으로 표면화**·은폐 금지). DATABASE_URL 원문 미로그(fingerprint 만). `real_source_identity_smoke.py`(기본 offline fake·network 0·DB 0·결정론)가 fetch(주입)→cluster→candidate 까지 write-free 진단 → source_role_distribution·failures_by_stage(body_missing/no_cluster/non_publishable_role/no_fingerprint)·publishable_anchor; DB 단계(created/held/withheld/adjudications/packet)는 offline **None**(정직·미도달)·`run_db_identity_smoke`(safe-target gated·test/dev 만·opt-in)가 기존 `ingest_records_to_events` 호출(thin adapter). **실 fetch 0 이면 RealSourceLoop 닫았다 주장 안 함**(real_fetch 플래그)·`no_auto_merge=True`·community anchor 금지. C(index)/D(lock) 계속 DEFER(persist 시 warning 표면화)·E(LLM/Agent) docs 진입 9조건만. **단 운영 DB 무변경(read-only)·smoke 기본 offline·scheduler 실가동 0·production 백로그 0.** 신규 테스트 2파일(classify+게이트+exit·offline 결정론·safe-target gate). adversarial 평결은 closeout 반영.
- Current mitigation: 도구가 backlog/exclusion report 로 0 의 원인을 수치화(조용한 "후보 없음" 금지)·**production activation preflight(can_persist/block_reasons/next_actions·target classification·APP_ENV↔URL mismatch·safe-target no-op 표면화)·real-source identity smoke(단계별 실패 분류·fake-default·DB offline None)**·read-only(자동 병합/write 0)·stage③ 배선(flag·shadow·멱등)·**incremental(only_unadjudicated/limit)·no-cluster backfill·backfill tool(dry-run)·keyset(after_link_id·SQL push)·backfill 운영 CLI·deploy checklist·readiness CLI·preflight(readiness/flag gate)·decide_exit_code(0/1/2/3)·created_at 시간순 cursor·scheduler 스크립트(gated)·docker scaffold(profile-gated·dry-run default·미가동)·docker build/up dry-run 실측(3경로 exit 2/1/0·ingestion COPY 버그 수정·live-PG 91p)**·migration readiness probe+runbook·ingest→③→packet E2E(live-PG·exclusion 1→0 감소 입증·동시 backfill 멱등).
- Remaining gap: ① 운영 DB(event_intel) alembic 0003→0009 마이그레이션·배포(배선 밖·배포 행위·runbook+deploy checklist 작성됨·실행 미승인) ② ~~단계 ③ 실제 주기 서비스 가동~~ **docker scaffold 됨(ADR#52·profile-gated·dry-run default)·실행성 실측 입증(ADR#53 build/up dry-run 3경로 exit 2/1/0·ingestion COPY 런타임 버그 발견·수정·live-PG 91p 재실행)** — 단 **실가동 0**(one-shot dry-run 만·while-loop 주기 가동 미입증·profile 비활성·운영 DB 0003·flag off·--persist 미지정·운영 DB migration+승인 후 게이트) ③ ~~cheap O(all-links) 전수 스캔~~ **bounded run 은 keyset 으로 완화(ADR#50)** — 단 `full_scan=True` 전수 report 경로(limit/cursor 미지정)는 여전히 전체 scan(`full_scan` 플래그로 표면화·대형 백로그 시 cursor 페이지네이션 권고)·cursor 시간순은 ADR#51 `cursor_mode=created_at` 로 가능(배치 간 정확·intra-batch tie→id)·**created_at 인덱스 미적용(ADR#52 ⓒ DEFER·DDL 문서화·대형 백로그 정렬 비용)** ④ ~~동시 backfill 직렬화 미명세~~ **멱등 안전 입증+권고 문서화(ADR#50)·docker 단일 runner 규율 가정(ADR#52·물리적 차단 아님 — `--scale`/수동 CLI 병행 우회 가능·데이터는 PK upsert 로 중복행 0 안전)** — 중복 work 직렬화(advisory lock)는 미구현(ⓓ DEFER·단일 runner/disjoint cursor 권고) ⑤ 실 cross-source 후보 누적(news/official 충분 볼륨·실 fetch — **ADR#54 real-source smoke 는 fake-default 진단[network 0·DB offline None]·실 network fetch 미수행**) ⑥ KO/hard-negative/mixed live bucket 충원. ⑦ 운영 DB boundary/safe-target 실효(ADR#54 preflight 가 점검·표면화하나 dev event_intel 경로는 여전히 no-op — 별도 운영 DB+APP_ENV=production 필요).
- Closure: 운영 DB 마이그레이션·배포(runbook/deploy checklist 실행) + 단계 ③ 실제 주기 서비스 가동(`run_recovery_scheduler` 식 docker 서비스·운영 DB 후) + 실 live-derived candidate/adjudication 백로그 누적(통계 규모) → packet pilot 이 synthetic/수동 주입 없이 live_selected>0 산출. **배선(능력) ≠ production(actuality)·도구 코드·E2E ≠ 실 운영 백로그** — 코드만으로 종결 금지(OVERCLAIM).

> **R-SourceCatalogFidelity** — **CLOSED 2026-06-24**(ADR#40, adversarial CLOSE-JUSTIFIED). catalog 6종(aladin/tmdb/kofic/kopis/tour/igdb, 전부 source_group `domain`)이 `_GROUP_TO_RECORD_TYPE` domain→official_record 로 publishable "official" Event 로 새던 누수를 **source-specific override**(`_record_type_for` 가 `source_content_type` 단일 출처로 catalog→catalog_metadata 비-publishable·non-catalog domain[culture_info=detail→official_record] 무변경) + `_VALID_RECORD_TYPES`·양쪽 `_RECORD_TYPE_TO_SOURCE_TYPE`(→"catalog" 비-publishable·authority 0 fail-closed)·`source_readiness_closure` catalog-aware(3중 drift 정합)로 차단. vendor route 없음 확인(우회 0). 테스트: ingestion catalog fidelity 10 + resolver catalog→WITHHELD + live-PG catalog 0 events. 흐름·근거는 `RISK_CLOSED.md`. **⚠ 범위 한정 — catalog 6종 한정.** domain group 의 group-단위 publishability 추정(culture_info 외 신규 domain 소스가 `source_content_type` 명시 분류 없이 official_record 가 되는 일반 패턴)은 본 RISK 밖 — **신규 domain 소스 추가 시 `source_content_type` 분류 의무를 규칙으로 둘 것**(관찰 메모, 별도 RISK 미등록 — 현재 실 누수원 0).

### R-DiscoveryCostStarvation · 발견 triage가 확장 LLM 예산 잠식  — Severity: MEDIUM (미래, 2026-06-20 신규 — adversarial)
- Area: Authority Discovery / budget / 발견 폭주
- Description: Change Detection의 비용 절감은 last_state가 있는 안정 소스 재폴링에만 적용. Authority Discovery(자기증식)가 매일 신규 엔티티/소스를 발견하면 **신규 URL은 last_state 부재→항상 CHANGED→LLM triage**. heat 우선순위 백프레셔는 "순서"만 조절(heat 알려면 일단 봐야 함=닭-달걀), 총량 미감소 → 발견 triage가 월 예산을 통째 소진해 핵심(고heat Event 확장) 예산 굶음.
- Current mitigation: (설계) heat 우선순위 큐 + 사람 승인 큐(순서 조절).
- Remaining gap: budget이 per-event/월 2축뿐, discovery 입구 쿼터 부재. cold triage 저가 사전필터 부재.
- Closure: budget 3축화(per-event + 월 + **신규 발견당 초기 triage 상한 + 일일 발견 승인 쿼터**) + cold triage 결정론/SLM 사전필터 테스트.

### R-AdModelFragility · 트래픽×광고 단일 모델의 콜드스타트·봇·brand-safety 취약성  — Severity: MEDIUM (2026-06-20 신규 — adversarial, commercialization 핸드오프)
- Area: commercialization / 수익 단일점 / 광고 정책
- Description: 구독 폐기(ADR#15)로 대체 수익경로 없음. ① 콜드스타트 — UGC 트래픽 루프는 사용자가 이미 있어야 돌아감(초기 신규 유입 채널 문서 부재). ② AI 자동생성 콘텐츠(에이전트 논쟁)가 광고 네트워크에서 "무효 트래픽/자동생성"으로 판정→계정 정지 위험. ③ brand-safety — 지정학/재난 사건 옆 광고는 광고주 기피(저RPM). ④ finance 도메인 투자권유 광고 유입 유인(원칙1 충돌).
- Current mitigation: (설계) §3.4 재배포금지=차별화근거(요약+UGC+시계열=전문 아님), AI 라벨링.
- Remaining gap: 초기 트래픽 채널 0, AI 콘텐츠 광고정책 사전검토 0, brand-safety 가드 0.
- Closure: 초기 트래픽 채널 1개(SEO/사건검색 랜딩) 검증 + AI 콘텐츠 라벨링/모더레이션 정책 + 광고 네트워크 정책 사전검토 + finance 광고 비투자 B2B 화이트리스트 + 페이지 비전문비율 게이트. (commercialization-strategist 핸드오프)

### R-ExpansionPartialFailure · 확장쿼리 batch fail-all (1후보 실패가 전체 확장 중단)  — Severity: LOW-MEDIUM (미래, 2026-06-20 신규 — adversarial)
- Area: ingestion/expansion / 운영 안정성
- Description: `query_generator.py:37` `generate_batch()`가 `generate()`를 무방비 루프 호출 → 배치 중 한 후보 LLM 실패(타임아웃/레이트리밋/파싱오류)가 전체 배치를 예외로 종료(부분 graceful 없음). LLM 단계에서 같은 구조면 외부 LLM 일시 오류 1건이 그 배치 모든 사건 확장을 산발적 정지.
- Current mitigation: (설계) `generate()` 내부 결정론 폴백(off 분기)은 명시되나 batch fail-all 구조는 미해소.
- 참고(C live wiring, 2026-06-22): **별개 모듈**에 격리 패턴 선례 생김 — `event_ingest_pipeline.ingest_records_to_events` 가 후보(클러스터) 단위 try/except + rollback + 계속 + `failed`/`failures` 집계를 구현(fake + live-PG 입증). **단 `query_generator.generate_batch`(LLM 확장)는 미수정** — 본 RISK 는 그 모듈 대상이므로 **종결/하향 아님**(동형 패턴 참조용).
- Remaining gap: `query_generator` 후보 단위 try/except 격리 + 후보 단위 결정론 폴백 degrade 부재(여전).
- Closure: `query_generator` batch 내 1후보 실패가 나머지 확장을 막지 않는 격리 테스트 + 폴백 발생을 audit trace `degraded_to_deterministic` 카운트.

> **기존 RISK 재평가 (2026-06-20, 새 방향 반영):**
> - **R-MockCard** — baseline→LLM 전환을 **Event/domains 모델 위에서** 수행해야 폐기 작업 없음(ADR#16 결합). 닫는 조건에 "domains 동적 부여" 추가.
> - **R-Integration** — "57소스 전수"는 P1 유효하나, 중기 목표가 "닫힌 목록"→"Entity/Authority 발견"으로 이동(범위 재정의, ADR#14·요구6).
> - **R-PromptInjection** — LLM이 수집 라우팅·에이전트 논쟁으로 **외부 텍스트에 더 노출** → 우선순위 상향. R-LLMCollectBoundary·R-AgentDebateSafety와 교차. 완화책에 "반복 unsafe 제안 카운터·escalation" 추가.
> - **R-FullText / R-Bypass** — 새 LLM/광고 경로에도 **HIGH 불변 유지**. 광고 모델이 전문 재배포 유발 안 함(요약+UGC+시계열=전문 아님, ADR#15 §3.4) + 페이지 비전문비율 게이트로 측정·강제.
> - **R-DcToS** — 커뮤니티 (b)층(사이트 UGC)은 우리 자산이라 무관. (a)층(소스 신호) ToS 검토 유지.
> - **R-Dedup** — R-FalseMerge로 분리·승격(위 참조). dedupe_key 임계 미정은 R-Dedup에 잔존.
> - **L5 정합성 갭** — Event 스냅샷 빈번 갱신으로 LOW→MEDIUM 재평가(R-EventModelMigration에 흡수).
>
> **불변 헌법 조항(흡수, MASTER §7.2 / §0):** ① 정보 제공이지 투자 조언 아님(매수/매도·가치판단 금지) ② 전문 저장·재배포 금지(요약+증거URL만) ③ 우회 전면 금지(robots/ToS/CAPTCHA/login/paywall/rate-limit/proxy) ④ `.env` 미열람/미수정/미커밋·비밀 미노출(길이/존재만) ⑤ 재현성(LLM은 LAYER P 한정, 제어흐름 결정론). 이 5조는 모든 RISK·기능의 상위 제약이다.

> **R-CodeReviewLivePath** 는 2026-06-19 **CLOSED**(→ `RISK_CLOSED.md`): harmless ingestion 변경 → `code_review` flag → `/code-review` 라이브 실호출 → CRLF finding → fix → stamp evidence 적재 1회 관찰.

> **R-EnvLoadAsymmetry** 는 2026-06-22 **CLOSED**(→ `RISK_CLOSED.md`): run_one_source(`run_source` funnel = run_one_source/run_phase/run_all_phases) + `run_production_orchestration.main()` 에 명시적 `load_env()` 배선 + 회귀 테스트(`test_entrypoint_env_bootstrap`) — .env 키 보유 시 precheck NEEDS_API 오판 제거. ingestion 1307 green.
> **R-GdeltMainLoopResume** 는 2026-06-22 **CLOSED**(→ `RISK_CLOSED.md`): 메인 플래너가 `EXTERNAL_RATE_LIMITED/COOLDOWN` 을 cooldown 만료 시 자동 재probe(`decide_production_strategy` now-gate + derive `cooldown_until`) — 429=외부제한 분류 유지·우회 0, 개별 spaced-probe 단일 의존 제거. 테스트 production_state/scheduler/orchestration_runner.
> **R-GdeltGovernorSplitBrain** 는 2026-06-22 **CLOSED**(→ `RISK_CLOSED.md`): 신규 `HostRateGate`(host 키 단일 출처, file-backed `host_rate_gate.json`, decide/record 시 파일 재읽기 = cross-process 가시성, record_call 호출 직전 즉시 영속) 도입 + gdelt host 3경로(메인루프 `run_production_orchestration` · `run_final_source_closure` · `run_last_chance_source_resurrection`) 동일 gate 공유 배선. source-level governor(900s/10s) 의미 보존, host floor만 추가(우회/병렬/tight-retry 0). 회귀 8(`test_host_rate_gate`: 공유·spaced-probe 보존·cooldown 자동재개 보존·호출직전 기록(성공/실패무관)·spacing 전 미호출·후 호출·429=외부제한). ingestion 1315 green.


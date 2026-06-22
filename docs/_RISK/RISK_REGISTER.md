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

### R-EventTimelineS2Hardening · S1 Event 토대의 S2 이전 확정 필요 항목  — Severity: LOW (신규 2026-06-22, S1 적대 감사 N5/N6 + legal 조건부)
- Area: data-model / Event 타임라인
- Description: S1(events/event_updates/event_cards.event_id nullable FK)은 비파괴·정합(architecture SOUND·게이트 1451 green·회귀 0)이나, S2(Event Resolution + CRUD 서비스) 착수 전에 확정할 정책 항목이 적대/법무 감사에서 식별됨.
- 잔여(S2 전 확정): ① `event_updates.event_id` ON DELETE CASCADE vs "append-only 감사 로그" 의도 긴장 — Event 삭제 시 변화분 통째 삭제(감사 목적이면 RESTRICT/soft-delete 검토, N5). ② Event/EventUpdate Pydantic↔ORM 경계의 tz-naive datetime·str↔UUID 방어 부재(카드 변환엔 있으나 Event엔 미구현 — S2 CRUD 변환 시 동반, N6). ③ `is_snapshot_bidirectional`은 app-level 헬퍼(DB 트리거/CHECK 아님)이며 현재 호출처 0(테스트뿐) — S2 이중쓰기 경로에서 실제 호출·강제 필요. ④ `evidence`/`source_refs`(자유 JSONB)를 채우는 ingestion/요약 단계에서 "전문 미저장·URL/요약만 + PII 가드"(legal 조건부 메모).
- Closure: S2 Event Resolution/CRUD 서비스에서 ①~④ 정책 확정 + 이중쓰기 경로가 is_snapshot_bidirectional 강제 + tz/UUID 변환 방어 추가 시 종결.

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
- Remaining gap(정직, adversarial): **"1517 green=비파괴"는 신규 경로(신규 테이블·재색인)를 커버하지 않음** — green은 기존 경로 무손상만 증명. 색인 swallow(MASTER L5)와 결합 시 검색-목록 불일치(신뢰 훼손).
- Closure: 1517 green + Event append E2E + **3엔진 동일 card_id 정합성 불변식 테스트 + 미전파 카드 메트릭(outbox SLO)**. ADR로 `cluster_event_map` 단일 진실원천 vs `event_cards.event_id` derived 결정 기록.

### R-FalseMerge · Union-Find transitive 오염이 영속 Event로 전파  — Severity: MEDIUM (R-Dedup LOW→MEDIUM 승격, 2026-06-20 — adversarial)
- Area: clustering / Event Resolution / 차별(교차검증 신뢰)
- Description: `cross_source_dedup.py:149`가 title Jaccard≥0.8(`_TITLE_JACCARD_THRESHOLD=0.8`)이면 union → Union-Find transitive 폐쇄(A–B 0.8, B–C 0.8이면 A–C 유사도 0이어도 같은 cluster). `:165-169` `has_strong=any(...)`라 클러스터에 강신호 edge 1개만 있어도 약신호로 끌려온 무관 레코드까지 전체가 CONF_DUPLICATE→자동 APPEND. 현재는 카드 1회성이라 오염이 갇히나, **Event append 라우팅(ADR#16) 도입 시 영속 Event에 누적·전파**.
- Current mitigation: (설계) 강신호 자동/약신호 possible 보류 — 단 cluster-level confidence만 봄(transitive 멤버 미보호).
- Remaining gap: clique(완전연결) 게이트·edge provenance 부재. 고heat Event가 무관 사건 흡수 시 1건의 명백한 오병합도 차별점(교차검증 신뢰) 붕괴.
- Closure: **transitive-only 클러스터 자동승격 금지 테스트** + clique 게이트 통과 E2E + 약신호 edge가 추가한 멤버에만 pairwise 검사(분모 축소) + event_links edge-level provenance(split 가역).

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
- Remaining gap: 후보 단위 try/except 격리 + 후보 단위 결정론 폴백 degrade 부재.
- Closure: batch 내 1후보 실패가 나머지 확장을 막지 않는 격리 테스트 + 폴백 발생을 audit trace `degraded_to_deterministic` 카운트.

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


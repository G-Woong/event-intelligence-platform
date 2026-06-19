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
- Current mitigation: 이 라운드에서 canonical 정렬 + SUPERSEDED 배너(06).
- Closure: 06 충돌목록 전부 배너/정정 완료(이 라운드에서 처리).

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

> **R-CodeReviewLivePath** 는 2026-06-19 **CLOSED**(→ `RISK_CLOSED.md`): harmless ingestion 변경 → `code_review` flag → `/code-review` 라이브 실호출 → CRLF finding → fix → stamp evidence 적재 1회 관찰.

# 05 — RISK REGISTER (위험 등록부)

> RISK는 단순 TODO와 분리한다. 종결조건이 충족돼야 닫힌다.

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

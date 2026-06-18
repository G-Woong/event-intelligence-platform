# 05 — RISK REGISTER (위험 등록부)

> RISK는 단순 TODO와 분리한다. 종결조건이 충족돼야 닫힌다.

---

### R-Integration · 두 수집 경로 미통합  — Severity: HIGH→MEDIUM (PARTIAL MITIGATED 2026-06-18)
- Area: source 수집 안정성 / 아키텍처
- Description: ingestion 엔진 출력→다운스트림 raw_events PG 배선.
- DONE: `ingestion/integration/` adapter(BackendApiRawEventsWriter) + `--raw-events-sink backend` 진입점.
  라이브 e2e 5타입(ingestion record→PG→Redis→worker→LangGraph→event_card) 통과, 멱등 collapse 확인.
- Remaining gap: ① production-validation 라이브 외부 probe→backend 실적재 1회 검증(미실행),
  ② 기본 sink는 여전히 mirror(backend는 opt-in) — 정식 production 스케줄에서 backend sink 채택.
- Closure: 라이브 외부 수집 사이클이 실 raw_events row를 idempotent 생성(backend sink 상시).

### R-MockCard · 생성 event_card 콘텐츠 mock  — Severity: HIGH (사용자 노출 전)
- Area: 정보 신뢰성(§1) / 상품성
- Description: LangGraph 6노드(entity_linking/sector_mapping/impact_analysis/evidence_check/
  fact_check/final_writer)가 mock → 생성 카드의 entity/sector/evidence/impact가 고정/가짜
  (예: 모든 입력을 geopolitics/energy/defense로 분류). raw_event 연결·status는 실제이나 알맹이는 mock.
- Evidence: `agents/nodes/entity_linking.py` 등 상수 반환. fact_check는 raw_text="" + LLM 실패 시 무조건 "pass".
- Current mitigation: `LLM_PROVIDER=mock` 기본이며 dev/검증 한정. community는 hold 봉인.
- Remaining gap: 04 T-AgtA(6노드 실연결), fact_check 빈 본문 pass 차단.
- Closure: 최소 entity/sector/evidence 실연결 전까지 카드 `published` 사용자 노출 금지.

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

### R-Auth · Admin 인증 bypass  — Severity: HIGH(운영 전)
- Area: monitoring/보안
- Description: `ADMIN_API_TOKEN` 빈 값이면 Admin API 허용(dev 편의). RBAC/OAuth 없음.
- Current mitigation: dev 한정. 토큰 설정 시 검사 활성. server-only 격리로 토큰 노출 차단.
- Remaining gap: RBAC/OAuth(04 T-OpB).
- Closure: 운영 배포 전 token 필수화 + RBAC.

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

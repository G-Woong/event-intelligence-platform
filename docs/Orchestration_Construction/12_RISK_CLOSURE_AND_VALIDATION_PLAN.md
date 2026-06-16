# 12 — Risk 폐쇄 및 검증 계획 (Risk Closure & Validation Plan)

> **목적**: 설계 세트 전체의 risk를 한 곳에서 닫는다. 각 risk는 **원인 / 영향 / 탐지 / 완화 / 검증 / status**로 닫는다. "나중에 생각"은 없다. DEFER는 반드시 trigger를 가진다.
> **status enum**: CLOSED_BY_DESIGN · CLOSED_BY_TEST_PLAN · USER_CONFIRMATION_REQUIRED · BLOCKED_BY_POLICY · DEFERRED_WITH_TRIGGER

---

## 0. 비개발자를 위한 설명

이 문서는 "무엇이 잘못될 수 있고, 그걸 어떻게 막을지"의 종합 목록이다. 각 위험에 대해 "왜 생기나 / 무슨 피해가 / 어떻게 알아채나 / 어떻게 막나 / 어떻게 확인하나"를 적어, **막연한 불안을 구체적 대비책으로** 바꾼다. 사용자가 결정해야 할 것은 `USER_CONFIRMATION_REQUIRED`로, 절대 우회 안 하는 것은 `BLOCKED_BY_POLICY`로 표시한다.

---

## 1. Risk inventory (전체 — 필수 항목 포함)

| risk | cause | impact | detection | mitigation | validation | owner agent | status |
|---|---|---|---|---|---|---|---|
| **source overcalling** | min_interval 위반/과빈도 | IP 차단, 약관 위반 | 429 카운트, 호출 로그 | min_interval+cooldown+지수(08) | test_rate_limited | operations-sre | CLOSED_BY_DESIGN |
| **provider 429** | rate limit 도달 | 수집 중단 | 429 응답 | 쿨다운+재시도 큐+fallback(08/04) | test_rate_limited | source-ingestion | CLOSED_BY_DESIGN |
| **body extraction failure** | 단일 전략 의존 | 빈 카드 | body_length | 11단계 cascade+캐시(04) | test_body_cascade | source-ingestion | CLOSED_BY_TEST_PLAN |
| **duplicate event amplification** | dedup 누락 | 같은 사건 도배 | dup_rate | content_hash+벡터(09) | test_dedup | data-quality | CLOSED_BY_TEST_PLAN |
| **low-quality community noise** | 저신뢰 다량 | 품질 저하 | relevance/noise | relevance 게이트+unconfirmed(09) | test_relevance | data-quality | CLOSED_BY_TEST_PLAN |
| **copyright / full-text risk** | full-text 저장/발행 | 법적 위험 | publication_policy | preview_only+internal_only(04/09) | test_preview | legal-safety | CLOSED_BY_DESIGN |
| **secret exposure** | .env/키 노출 | 자격증명 유출 | scan_secrets | 마스킹+scan gate(전체) | secret scan PASS | security-guardian | CLOSED_BY_TEST_PLAN |
| **prompt injection from web** | 수집 본문에 악성 지시 | LLM 오작동 | 입력 sanitize | LLM 입력 분리+도구 제한(07) | injection 테스트 | security-guardian | DEFERRED_WITH_TRIGGER(LLM 노드 구현 시) |
| **tool overreach** | 에이전트 무제한 접근 | 보안·비용 | 도구 감사 | quality_judge만 LLM+도구 제한(07) | test_no_unmediated_web | security-guardian | CLOSED_BY_DESIGN |
| **agent hallucinated source status** | LLM이 PASS 임의 | 거짓 상태 | 상태 출처 | 상태는 deterministic gate(07) | test_status_consistency | adversarial-critic | CLOSED_BY_DESIGN |
| **stale docs** | 문서 갱신 누락 | 혼란 | 교차검증 | DOCS_FINAL pointer+이 세트(00) | dangling ref grep | docs-curator | CLOSED_BY_DESIGN |
| **DB schema lock-in** | 조기 과설계 | 변경 비용 | 스키마 리뷰 | JSONL→점진 영속(05) | Phase A 표 0 | orchestrator-architect | CLOSED_BY_DESIGN |
| **LangGraph overengineering** | 불필요 도입 | 복잡도 | 코드 복잡도 | deterministic 우선, F 선택(06/07) | Phase A 단독 | orchestrator-architect | CLOSED_BY_DESIGN |
| **Celery premature complexity** | 조기 도입 | Windows 제약·복잡 | worker 起動 | Phase G로 분리(00/11) | V-4 | operations-sre | USER_CONFIRMATION_REQUIRED |
| **MCP/plugin reintroduction** | 13번 제약 위반 | tool poisoning | 설계 grep | future review만(06) | grep MCP install 0 | mcp-researcher | BLOCKED_BY_POLICY |
| **commercialization misfit** | 기술 과잉 | 출시 지연 | MVP 범위 | MVP/과잉 구분(10) | 사용자 피드백 | commercialization | CLOSED_BY_DESIGN |
| **cost explosion** | 유료 검색/LLM 남용 | 적자 | 비용 카운터 | on-demand+quota+게이트(08/10) | test_quota_skip | commercialization | CLOSED_BY_TEST_PLAN |
| **두 시스템 미연결** | 브리지 미구현 | 44소스 가치 미실현 | event_cards 소스 | Phase H 브리지(05/11) | e2e 1건 | orchestrator-architect | DEFERRED_WITH_TRIGGER(Phase H) |
| **google_trends PASS 오기** | 상태 왜곡 | 거짓 보고 | grep | CONFIRMED 고정(08 §9) | test_trends_not_pass | data-quality | CLOSED_BY_DESIGN |
| **provider 우회 유혹** | 429/차단 회피 | 약관·법 위반 | grep proxy/bypass | BLOCKED_BY_POLICY(08) | grep 0건 | legal-safety | BLOCKED_BY_POLICY |
| **asyncio 중첩** | playwright sync+async | 런타임 에러 | smoke | sync 노드/nest_asyncio(06) | Windows smoke | source-ingestion | DEFERRED_WITH_TRIGGER(Phase F/G) |
| **싱글톤 store fork** | prefork 별도 캐시 | 상태 불일치 | 워커 간 테스트 | local_file/redis backend(00/05) | roundtrip | operations-sre | CLOSED_BY_DESIGN |
| **gcp 키 노출** | 루트 secret 파일 | 자격증명 유출 | gitignore/`git ls-files` | **실측: `.gitignore` 포함 + 미추적 확인(2026-06-14)** | scan_secrets PASS(1807) + ls-files 미추적 | security-guardian | **CLOSED_BY_TEST_PLAN** (잔여: 디스크 파일 백업/권한 — 운영 권고) |
| **고수준 프레임워크 조기 도입** | Deep Agents/CrewAI/MS AF를 MVP에 도입 | 비결정성·비용·보안·복잡도 | 설계 grep | Layer 3로 분리, 지금 설치 0(06 §5b) | grep deepagents/crewai install 0 | orchestrator-architect | CLOSED_BY_DESIGN |
| **버전 업그레이드 회귀** | langgraph/langchain v1로 올림 | 다운스트림 11노드 깨짐 | 회귀 테스트 | 0.2.76 유지(D-3, 실측 핀 확인) | 108 회귀 | test-validation | CLOSED_BY_DESIGN |
| **rate-limit 인터페이스 오인(U-1)** | policy vs store | 잘못된 import | grep | VERIFY PATH(03/11) | 구현 직전 grep | source-ingestion | DEFERRED_WITH_TRIGGER |
| **create_raw_event 오인(U-3)** | 시그니처 미확인 | 브리지 실패 | 코드 확인 | VERIFY PATH(05) | 구현 직전 확인 | source-ingestion | DEFERRED_WITH_TRIGGER |

---

## 2. risk owner agent 요약

| owner | 담당 risk |
|---|---|
| operations-sre | overcalling, Celery complexity, 싱글톤 fork |
| source-ingestion | 429, body extraction, asyncio, U-1, U-3 |
| data-quality | duplicate, noise, trends PASS |
| legal-safety | copyright, 우회 |
| security-guardian | secret, prompt injection, tool overreach, gcp 키 |
| adversarial-critic | hallucinated status |
| orchestrator-architect | schema lock-in, overengineering, 미연결 |
| commercialization | misfit, cost |
| mcp-researcher | MCP 재도입 |
| docs-curator | stale docs |

---

## 3. validation command (검증 명령)

```powershell
# 설계 무결성(이번 턴)
git diff --check
python -m ingestion.tools.scan_secrets --paths docs .claude
python -m ingestion.tools.scan_secrets --paths ingestion docs plans .claude
Get-ChildItem docs\Orchestration_Construction -File -Filter *.md | Measure-Object
git status --short

# 구현 턴(Phase별 — 참고)
.\.venv\Scripts\python.exe -m pytest ingestion/tests -q          # 509 회귀
.\.venv\Scripts\python.exe -m ingestion.runners.run_runner_orchestration_readiness
```

---

## 4. pass criteria (이번 설계 턴)

- 13개 필수 md + README 생성.
- 각 핵심 문서에 USER_CONFIRMATION_REQUIRED / Agent Committee Review / Risk Closure / Commercialization Impact / Proposed diff(+DO NOT APPLY) 포함.
- secret scan PASS, diff --check PASS, git status clean(commit 후).
- google_trends_explore PASS 오기 0, proxy/CAPTCHA/paywall bypass 권장 0, .env 값 0, MCP/Plugin 설치 요구 0, LangGraph/Deep Agents 무조건 전제 0.
- system_overview 분석 반영.

---

## 5. unresolved ambiguity (남은 모호 — 전부 trigger/default 보유)

| id | 모호 | default | trigger |
|---|---|---|---|
| U-1 | rate-limit 함수 위치 | VERIFY PATH | Phase B/G 구현 직전 |
| U-3 | create_raw_event 시그니처 | VERIFY PATH | Phase H 직전 |
| V-4 | Windows Celery pool | deterministic 우선 | Phase G |
| D-6 | 브리지 방식 | 별도 어댑터 | Phase H 설계 시 |
| C2-1 | requires_api_key 29소스 키 readiness | live smoke 보수적 skip(.env 비검증) | 운영 전 V-1 키 확인 |
| C2-2 | google_trends_explore probe 미연결(registry/_SERVICE_CONFIGS 미등록) | profile verify_required, live 불가 | Phase D/별도 라운드 runner 연결 |

---

## 6. USER_CONFIRMATION_REQUIRED (종합)

| question | why | default | blocking |
|---|---|---|---|
| Phase A(설치 0)부터? | 빠른 증명 | 예 | No |
| langgraph 0.2.76 유지? | 회귀 위험 | 유지 | No |
| Deep Agents/MCP 도입? | 복잡도/정책 | 미도입/future review | Yes(정책) |
| Redis/Postgres 컨테이너 가동 가능? | Phase G/H | 환경 확인 | Phase G |
| 루트 gcp 키 gitignore 확인? | 자격증명 | ✅ **확인됨(gitignore+미추적)** — 디스크 파일 백업/권한만 운영 권고 | No(해소) |
| 브리지 별도 어댑터? | 결합도 | 예 | REVIEW |

---

## 7. BLOCKED_BY_POLICY (우회 불가 — 불변)

- provider 429 우회(proxy rotation / internal RPC / login).
- CAPTCHA/Turnstile/paywall 우회.
- google_trends_explore 429 우회 → CONFIRMED_EXTERNAL_RATE_LIMIT 유지.
- MCP/Plugin 재설치.
- .env 실제 키 값 출력.
- 투자 조언 출력(numeric → 매수/매도).

---

## 8. final implementation readiness verdict

| 항목 | 상태 |
|---|---|
| 설계 문서 완비 | ✅ 13 + README |
| 코드 분석 반영 | ✅ (01) |
| system_overview 반영 | ✅ (01 §11) |
| LangChain/LangGraph/Deep Agents 공식 조사 | ✅ (06, 버전 차이 명시) |
| risk closure | ✅ (이 문서, 25 risk) |
| 우회/정책 위반 | ✅ 0건 |
| 다음 구현 시작점 | Phase A (00 §7, 11 §9) |

**판정: 다음 구현 턴은 Phase A(deterministic local cycle, 신규 설치 0)부터 시작 가능. 차단 요소는 보안 확인(gcp 키, V-9)과 Phase G 진입 시 환경 확인(Redis/Postgres, Windows Celery)뿐이며, 둘 다 Phase A~E 진행을 막지 않는다.**

---

## 9. Agent Committee Review (전체 — 14 에이전트)

| agent | 종합 피드백 | status |
|---|---|---|
| orchestrator-architect | 두 시스템 bridge + Phase 단계화가 설계의 척추 | CLOSED_BY_DESIGN |
| source-ingestion-engineer | 수집 코드 무수정 + 호출만 원칙 일관 | CLOSED_BY_DESIGN |
| data-quality-auditor | 품질 게이트 + numeric 면제 + dedup 정합 | CLOSED_BY_TEST_PLAN |
| test-validation-agent | Phase별 회귀 0 게이트 명확 | CLOSED_BY_TEST_PLAN |
| adversarial-reality-critic | UNKNOWN/미연결을 숨기지 않음. 최대 리스크는 브리지(Phase H) | DEFERRED_WITH_TRIGGER |
| commercialization-strategist | 브리지=최대 ROI, 기술 절제로 런웨이 보호 | CLOSED_BY_DESIGN |
| legal-safety-compliance-reviewer | 우회 0 + preview + unconfirmed 라벨 — 승인 | BLOCKED_BY_POLICY |
| product-ux-strategist | 신뢰 라벨 UI가 제품 차별 | CLOSED_BY_DESIGN |
| docs-memory-curator | DOCS_FINAL 최소 변경, dangling ref 0 목표 | CLOSED_BY_DESIGN |
| security-permission-guardian | secret gate + gcp 키 점검 + 도구 제한 | USER_CONFIRMATION_REQUIRED |
| business-intelligence-analyst | 소스 다양성=경쟁 우위, 3층 구조 | CLOSED_BY_DESIGN |
| evaluation-benchmark-agent | 측정 가능 지표 + 임계 데이터 조정 | CLOSED_BY_TEST_PLAN |
| operations-sre-agent | 재시도 큐/격리/quota = 운영 안정. Windows pool 주의 | CLOSED_BY_DESIGN |
| frontend-integration-agent | event queue→API 기존 contract 재사용 | CLOSED_BY_DESIGN |

---

## 10. Commercialization Impact

risk를 닫는다는 것은 **사업 리스크를 닫는 것**이다. 우회 0(법무 안전) → B2B 계약 가능. quota guard(비용 상한) → 가격 모델 가능. 품질 게이트(신뢰) → 프리미엄 근거. 기술 절제(런웨이) → 출시 속도. 즉 이 risk closure 문서는 그 자체로 **투자/계약 시 제시할 수 있는 신뢰 자산**이다.

---

## 11. USER_CONFIRMATION_REQUIRED (이 문서)

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| prompt injection 방어를 LLM 노드 구현 시 추가? | 보안 | 예(DEFERRED trigger) | No(Phase F/G) |
| gcp 키 gitignore 점검? | 보안 | ✅ 확인됨(gitignore+미추적, §6) | No(해소) |
| Phase A부터 구현 시작? | 안전 진입 | 예 | No |

---

## Phase D Risk Closure (2026-06-14)

| risk | status | 근거 |
|---|---|---|
| requires_api_key 소스 키 비검증(V-1) | **CLOSED** | D-0 readiness(ready 23/ambiguous 5/missing 0) + D-1 live smoke로 28개 전부 live 성공 |
| article-level 분해 미구현 | **CLOSED** | artifact_parser 8포맷 + seed_expansion, fixture 15테스트 |
| 본문/snippet 혼동 | **CLOSED_BY_DESIGN** | body_state snippet_only=body_missing True, partial 분리 |
| canonical_url fabricate | **CLOSED_BY_DESIGN** | 정규화 불가 시 None, 없는 URL 생성 경로 0(adversarial 확인) |
| malformed에서 사건 silent drop | **CLOSED** | seed_expansion source-level fallback + parse_error 보존 |
| 키 값 노출 | **CLOSED** | security guardian SECURE, secret scan PASS, env_status 이름만 |
| REDIS_URL 설정 시 enqueue 실패 | **MITIGATED** | JSONL 명시(`EventQueue(redis_url="")`); Phase G Redis Stream에서 해소 |
| HTML 소스 기사 분해 불가 | **ACCEPTED/DEFERRED** | `html_unsupported` fallback 정직 처리, 본문은 04 cascade 책임 |
| article candidate dead-end | **DEFERRED_TO_PHASE_H** | bridge_to_raw_events 미구현(설계상 Phase H) |
| dedup/boilerplate/published_at 정규화 | **DEFERRED_TO_PHASE_E** | 09 Phase D 핸드오프 표 6항목 |
| Playwright 소스 live 미검증(4종) | **DEFERRED** | 장시간/불안정 → 별도 라운드(conservative) |

검증 명령 결과: 전체 회귀 776 passed, git diff --check PASS, secret scan PASS, outputs gitignore 확인.

## Phase D-P / E-0 Production Closure (2026-06-14)

실제 artifact 49소스 audit + 3관점 팀 리뷰(adversarial/data-quality/security) 결과. **VERDICT: PRODUCTION_CLOSURE_PARTIAL** (measurement-complete, expansion-incomplete).

| risk | status | 근거 |
|---|---|---|
| Phase D 보고 과장(artifact=expansion으로 위장) | **CLEANLY_CLOSED** | candidate_total/body_state 분리 집계 → present=0 그대로 노출(긍정편향 제거) |
| html_url/publication_date 미매핑 | **CLEANLY_CLOSED** | alias 보강, federal_register url/canonical 2/2·published 2/2 |
| rate-limit payload를 success로 위장 | **CLEANLY_CLOSED** | `possible_rate_limit_payload` 탐지(alpha_vantage `{"Note":...}`) |
| numeric을 본문 missing으로 오염 | **CLEANLY_CLOSED** | market missing=0, structured_signal 분리(data-quality PASS) |
| canonical_url fabricate/network 유출 | **CLEANLY_CLOSED** | 446/446, network_calls=0, none=0 |
| REDIS_URL enqueue 실패 | **MITIGATED** | 회귀 테스트로 JSONL 명시 방어 고정; Phase G 본구현 |
| 키 노출 | **CLEANLY_CLOSED** | security SECURE, secret scan PASS files_scanned=30 |
| 기사형 본문 추출 0(present=0, RSS=snippet) | **STILL_OPEN → Phase E** | canonical 446 fetch → readability 추출(launch blocker 아님, feature gap) |
| 21/49 소스 0분해(sec_edgar nested/hn id-list 등) | **STILL_OPEN → Phase E** | 소스별 파서 보강(`no_candidates_from_artifact`로 식별) |
| dedup collapse/near-dup/중복률 | **STILL_OPEN → Phase E** | pre-gate는 키만 생성, 제거 미실행 |
| published_at precision_lost(date-only/naive UTC) | **STILL_OPEN → Phase E** | 정직 고지(docstring), 정밀 정규화 Phase E |
| boilerplate 휴리스틱 오탐/미탐 | **MITIGATED → Phase E** | 본문 유입 전 거의 not_applicable, 정밀 분류 Phase E |
| candidate→raw_events dead-end | **DEFERRED → Phase H** | bridge_to_raw_events |
| Playwright 4종 live 미검증 | **DEFERRED → 별도 라운드** | 장시간/불안정 |

**launch blocker vs phase blocker**: 상용 출시의 phase blocker는 ①기사 본문 추출 ②21소스 분해 — 둘 다 Phase E. 보안/법무/우회/키 노출 등 **launch blocker는 없음**(전부 CLOSED/방어).

검증: 전체 회귀 **808 passed**, git diff --check PASS, secret scan PASS, outputs gitignore 확인, 신규 설치 0, no bypass.

### Phase E-1 — Risk Closure (2026-06-14)

| 위험 | 상태 | 근거 |
|---|---|---|
| present 길이-only 판정이 발췌를 본문 오인 | **CLEANLY_CLOSED** | excerpt 마커 탐지로 the_verge 9/10 강등(present 10→1) — 긍정편향 자가 교정 |
| 0분해 nyt/sec_edgar | **MITIGATED** | 중첩 컨테이너 파서(response.docs/hits.hits)로 분해 복구 |
| 에러 봉투 success 위장(opendart/bok_ecos) | **CLEANLY_CLOSED** | `api_error_payload` 분류 |
| candidate_total/pre_gate_pass 인플레 오독 | **MITIGATED** | group/body_state별 분리 보고, `list`/`row` 컨테이너 제외 |
| 뉴스 본문 추출(present≈0) | **STILL_OPEN → Phase E** | RSS=발췌/snippet, 전체 기사 fetch 미구현 |
| its 등 도메인 API 필드 매핑 | **STILL_OPEN → Phase E** | title/url 미매핑 → 31584 reject |
| candidate→raw_events | **STILL_OPEN → Phase H** | bridge 미구현 |

**launch blocker vs phase blocker(불변)**: launch blocker 없음(보안 SECURE/법무 CLOSED/우회 0/키 비노출). phase blocker = 뉴스 본문 fetch + 소스별 파서(Phase E).

검증: 전체 회귀 **843 passed**(808→+35), git diff --check PASS, secret scan PASS(131), outputs gitignore 확인(tmp_source_body_audit), 신규 설치 0, live 호출 0, no bypass.

### Phase E-2 — Risk Closure (2026-06-14, run 20260614T105328Z)

| 위험 | 상태 | 근거 |
|---|---|---|
| 뉴스 본문 추출(E-1 present≈0) | **MITIGATED** | live canonical-URL fetch로 ARTICLE_BODY_ALIVE 6(5건 실본문 trafilatura, sha256 보존). 단 fetch 실패 5종 잔존 |
| 0분해(hacker_news/opendart/coinbase) | **CLEANLY_CLOSED** | artifact 최적 선택(hacker_news) + source 어댑터(opendart/coinbase) → alive 복구 |
| numeric 인플레(binance 3600행→pre_gate_pass 3607) | **CLEANLY_CLOSED** | 단일-신호 어댑터 환원 → structured_signal 7·pre_gate_pass 8 |
| OFFICIAL_RECORD_ALIVE 루프홀(URL/시간 둘 다 없어도 alive) | **CLEANLY_CLOSED** | anchor(url 또는 date) 강제 → tmdb/culture_info 정직 강등(6→4) |
| alive 과대평가(full-body와 degraded 합산) | **MITIGATED** | fully_alive 22 / degraded_alive 2 분리 보고 |
| ALIVE 본문 증거 미보존 | **CLEANLY_CLOSED** | body_fetch_evidence(sha256+길이+head≤500자, gitignored) |
| robots/paywall/login 우회 | **CLEANLY_CLOSED** | urllib.robotparser 준수, httpx GET only, 제외 8소스 비호출 |
| sec_edgar title 매핑·NEEDS_PARSER 18 | **STILL_OPEN → Phase E** | hits.hits 분해되나 _source title 미매핑; 공공/도메인 필드 어댑터 |
| 뉴스 fetch 실패 5종(ap_news/nyt 등) | **STILL_OPEN → Phase E** | fetch 실패/excerpt — 소스별 fetch 튜닝 |
| opendart cp949 인코딩 | **STILL_OPEN → Phase E** | utf-8 가정, 인코딩 협상 미구현(품질 CAUTION) |
| candidate→raw_events | **STILL_OPEN → Phase H** | bridge 미구현 |

**팀 검토(9관점)**: Security=SECURE(scan PASS), Legal=APPROVED_WITH_CONDITIONS(robots fail-open 운영조건), Adversarial=PARTIAL(HIGH 2건[official 루프홀·alive 과대평가] 흡수), DataQuality=CONCERN(binance 인플레 흡수). + Source/Body/Adapter/Ops/Commercialization 자체 검토.
**launch blocker vs phase blocker(불변)**: launch blocker 없음. phase blocker = 소스별 필드 어댑터 + 뉴스 fetch 안정화(Phase E).

검증: 전체 회귀 **888 passed**(843→+45), git diff --check PASS, secret scan PASS(156), outputs gitignore 확인(tmp_full_source_revival + full_source_revival_event_queue.jsonl), 신규 설치 0, no bypass. **VERDICT: FULL_SOURCE_REVIVAL_PARTIAL**(NEEDS_PARSER/NEEDS_BODY_FETCH 23 잔존 → COMPLETE 금지).

> 다음 문서: `README.md` (진입점).


## Phase E-3 — Risk Closure (run 20260614T114401Z)

verdict `FULL_SOURCE_CLEAN_COMPLETE`: unresolved_after=0, UNKNOWN=0, NEEDS_*=0.

흡수한 리뷰 발견(긍정편향 차단):
- (Adversarial/DataQuality HIGH) cnbc가 Pro 프로모션 492자를 본문으로 둔갑 → confident_full+title-overlap
  게이트로 EXCERPT_ONLY→EXTERNAL_API_ERROR_WITH_EVIDENCE 강등.
- (HIGH) paywall/captcha 마커 무시 vs false-positive 강등 딜레마 → 마커 정밀화 + "서빙된 full body는
  SUCCESS, 짧고 무관하면 BLOCKED" 규칙.
- (HIGH) eventqueue_ready를 로컬 파일경로로 둔갑 → 외부 URL만 evidence 인정(product_hunt eq=0).
- (MED) product_hunt anchor 없는데 fully-alive → degraded(NO_STABLE_URL;NO_TIMESTAMP) 분리.

cleanly closed: NEEDS_PARSER 18(adapter), NEEDS_BODY_FETCH 5(ladder), fake-alive 3종.
terminal(우회 아님): nyt(HTTP_403)/kma(resultCode10)/cnbc(excerpt) external, gdelt/google_trends
rate-limit, its NOT_SERVICE_USEFUL, bok_ecos/eia vendor-route.
STILL_OPEN(Phase E): bok_ecos/eia 전용 route 구현, kma 파라미터 수정 후 재검증, hankyung 본문 중복 정제,
aladin URL 엔티티 디코딩, cnbc CNBC-Pro 비프로모션 경로. Phase H: candidate→raw_events bridge.
검증: 942 passed, secret scan PASS(165), git diff CLEAN, outputs gitignored.


## Phase F — Production Orchestration Closure

Phase F validation: dry-run(network 0) + bounded live(4 then 6 sources, real network) →
records→EventQueue→raw_events mirror, source_without_state=0, unknown=0, critical_alerts=0,
bridge_contract_pass=True.

Team review 흡수 사항:
1. quarantine이 dead-path였음 → runner에 WIRED(failure-count 누적 + 회귀 테스트).
2. is_due cadence 레이어 wired(last_run_at)를 2nd 게이트로.
3. structured_signal dedup label 수정(literal이 아닌 실제 signal type).
4. monitoring secret scan을 모든 record로 확대.

STILL OPEN(next):
- 실제 Postgres raw_events 채택(현재는 mirror + injectable/unit-tested db_writer).
- queue write와 dedup index save 사이 crash-window(plans/012에서 dedup_key DB unique constraint 강제).
- full body용 body fetch ladder 통합(현재 RSS snippet).
- cross-source possible_duplicate는 report-only(auto-collapse 안 함).

Launch blockers: ingestion contract에는 없음. raw_events DB migration이 Phase H 전제조건.

## Phase G — Force Production-Ready Source Closure

**최종 판정: PARTIAL_WITH_HARD_BLOCKERS** — ALL_READY 아님. Adversarial 리뷰가 과장 주장을 강제 하향했다.

상태 분포(총 57): PRODUCTION_READY 44 / PRODUCTION_READY_DEGRADED 2 / EXTERNAL_RATE_LIMITED 1 / POLICY_EXCLUDED 10. unknown=0, source_without_state=0, critical_alerts=0.

**HARD BLOCKERS(숨기지 않음)**:
1. **gdelt** — provider rate-limit(HTTP 429 "one every 5 seconds"). 라우트 wired·cooldown 자동관리·자가회복형이나 이번 런에 신선 데이터 0 → production_ready 주장 안 함, EXTERNAL_RATE_LIMITED 유지(우회 금지 정합).
2. **culture_info** — anchor 수정(seq→detail URL) 커밋됐으나 라이브 재검증 부재로 degraded 유지.
3. **product_hunt** — anchor 수정(slug→post URL) 커밋됐으나 재검증 부재 + slug 폴백 dedup-collapse 위험으로 degraded 유지(실제 url 선호).

**법무 조건(Legal APPROVED_WITH_CONDITIONS)**: nyt preview_only / non_commercial / commercial_license_required(evidence에 보존). guardian/newsapi/aladin 동일.

**STILL OPEN(next)**:
- culture_info / product_hunt를 토큰·쿼리로 라이브 재검증해 degraded 해소.
- gdelt를 provider non-throttled 윈도에서 재수집.
- 상업 런칭 전 nyt commercial license 확보.

검증: 전체 회귀 1098 passed, secret scan PASS(269), 신규 설치 0. 리뷰 — Security SECURE, Legal APPROVED_WITH_CONDITIONS, DataQuality CLEAN.

---

## Phase G-2 — Last-Chance Source Resurrection (dcinside / google_trends_explore / gdelt)

**판정: PARTIAL_MIXED_PENDING_AND_BLOCKERS** (3개 중 1 degraded-승격, 1 pending, 1 blocker). Phase F에서 일괄 제외했던 3개 소스의 risk를 status enum으로 정직하게 닫는다(dcinside는 clean READY가 아닌 DEGRADED).

| source | 원인 | 완화 | status |
|---|---|---|---|
| **dcinside** | robots/anti_bot 차단 추정(미실측) | robots 실측 → AI-학습 차단 섹션 별개, generic UA Allow:/ 확인. robots-allowed 갤러리만 generic UA static fetch, 차단 감지 시 `*_BLOCKED_NO_BYPASS` 중단. live 30 community_signal 실증. | PARTIAL_CLOSED (PRODUCTION_READY_DEGRADED: list-preview-only/no-body, AI-차단 robots를 generic UA로 통과, ToS automated-use UNVERIFIED → legal-safety review pending; scope=stockus only) |
| **gdelt** | provider 429(IP throttle) | RateLimitGovernor cooldown 영속 + non-throttled 윈도 재개. 0-record를 READY로 둔갑 금지(production_state 매핑). | DEFERRED_WITH_TRIGGER (non-throttled 윈도 재수집 시 재개) |
| **google_trends_explore** | 공식 API 부재 + anti-abuse 429 + 우회 금지 | 추측 disable → 검증된 evidence blocker로 격상. trending 역할은 google_trending_now가 커버. | BLOCKED_BY_POLICY (requires_official_api_or_contract) |

**정직성 보장**: gdelt fresh data 0건을 production_ready로 주장하지 않는다(EXTERNAL_RATE_LIMITED 유지). dcinside는 full body 미수집(저작권 보수)이며 clean READY가 아닌 DEGRADED로 강등. google_trends_explore는 우회 회피책을 채택하지 않는다.

**Known limitation(미해소, 정직히 명시)**:
- gdelt — 연속 pending에 대한 escalation 카운터가 없다. cooldown 만료 시 자동 재개만 하고, 동일 소스가 N회 연속 pending에 머무를 때 알림/격리로 escalate하는 카운터는 미구현이다(무한 pending 침묵 위험). 향후 supervisor에 consecutive_pending_count + threshold escalation을 추가해야 한다.

**NEXT_STEP**:
- dcinside — ToS 자동수집 조항 미검증(TOS_AUTOMATED_USE_UNVERIFIED) → **legal-safety-compliance-reviewer 핸드오프**로 ToS 자동수집 적법성 검토 후에야 DEGRADED→READY 승격 검토. 추가 갤러리는 각 robots 재확인 후에만 확장(일괄 확장 금지).
- gdelt — provider 비-throttle 윈도에서 단발 재수집 + 위 escalation 카운터 구현.
- google_trends_explore — 상용화 전 공식 API/계약 확보.

검증: 전체 회귀 **1130 passed**, secret scan **PASS(210)**, 신규 설치 0, no bypass(robots 허용 path·cooldown 존중·CAPTCHA/login/cloudflare 감지 시 중단), 전 outputs gitignored. 최종 상태 분포: PRODUCTION_READY 44 / PRODUCTION_READY_DEGRADED 3(culture_info, product_hunt, dcinside) / EXTERNAL_RATE_LIMITED 1(gdelt) / POLICY_EXCLUDED 9, non_excluded_not_ready 4(gdelt pending + culture_info/product_hunt/dcinside degraded).

## Phase G-3 — Final Source Closure

**판정: PARTIAL_WITH_VERIFIED_HARD_BLOCKERS**. 남은 비제외 4개 소스(POLICY_EXCLUDED 9 미접촉)의 risk를 status enum으로 최종 closure했다. culture_info/product_hunt는 합성/죽은 url을 실 url로 해소해 READY 승격, dcinside/gdelt는 검증된 하드 블로커로 정직히 닫았다.

| source | 원인 | 완화 | status |
|---|---|---|---|
| **product_hunt** | name 합성 slug url(NO_STABLE_URL/NO_TIMESTAMP) | GraphQL 확장(`url slug createdAt`)로 실 canonical url+createdAt 확보, 합성 제거. live 1건 실증. | CLOSED → PRODUCTION_READY |
| **culture_info** | 죽은 detailView shell(909B) 합성 | data.go.kr period2→detail2 실 전시 url + startDate + seq. placeUrl 폴백 제거(HIGH-3). live 5건. | CLOSED → PRODUCTION_READY |
| **dcinside** | 본문 ALIVE이나 정책/법무 리스크 | list community_signal만 수집·detail 미저장·AI 크롤러 robots를 generic UA로 존중·ToS 미검증·단일 갤러리. | PARTIAL_CLOSED (DEGRADED 유지) |
| **gdelt** | provider IP throttle(429) | Colab-parity 코드 동일 확인, RateLimitGovernor cooldown 영속 + pending_resume(자동 재개, 무한 retry 0). 응답 diff UNVERIFIED 정직표기. | DEFERRED_WITH_TRIGGER (자동 재개) |

**적대 리뷰 흡수**: (1) culture_info placeUrl(무관 venue url) 폴백 **제거**. (2) EvidenceGate를 "모든 신선도 보장"이 아닌 shape+known-dead 가드로 **정직 명명**(liveness는 fetcher). (3) gdelt 응답 diff 저장본 없음을 **UNVERIFIED로 정직화**(검증됐다고 과장 안 함).

**남은 launch blocker(미해소, 정직)**: (1) dcinside ToS 자동수집/재배포 조항 legal-safety 검토 → 통과 전 DEGRADED 유지. (2) **community_signal(dcinside/product_hunt) corroboration/펌핑 차단 게이트 미구현** — unconfirmed_until_corroborated 태그를 소비하는 하위 quality/safety 게이트 부재. 단일 소스 신호를 confirmed event로 게시 전 corroboration 게이트 구현 필수(투자 펌핑 직행 방지, CLAUDE.md 원칙1). (3) gdelt 비-throttle 윈도 재수집 + 연속 pending escalation 카운터.

**NEXT_STEP**: dcinside→legal-safety-compliance-reviewer 핸드오프. community_signal→corroboration 게이트 구현(quality/safety 계층). gdelt→비-throttle 재수집 + escalation 카운터.

검증: 전체 회귀 **1179 passed**, secret scan **PASS**, net-0 주입 9테스트, no bypass, 전 outputs gitignored. 최종 분포: PRODUCTION_READY 46 / PRODUCTION_READY_DEGRADED 1(dcinside) / EXTERNAL_RATE_LIMITED 1(gdelt) / POLICY_EXCLUDED 9 = 57. unknown 0, critical_alerts 0, non_excluded_not_ready 2(dcinside/gdelt).

---

## Phase G-4 — Final Closure of Remaining Non-Excluded Source Risks

**판정: PARTIAL_ONLY_IF_LEGAL_OR_PROVIDER_HARD_BLOCKER_WITH_FULL_EVIDENCE** — 비제외 소스 중 open 항목은 gdelt provider 429 하나뿐이다. G-3가 남긴 비제외 잔여 risk(dcinside DEGRADED의 애매함, gdelt escalation 카운터 미구현, community_signal corroboration 게이트 미구현, culture_info/product_hunt eq/raw=0 약점)를 status enum으로 최종 closure했다. gdelt single 429를 disable로 둔갑시키지 않고 escalation-capable scheduled state로 닫는다.

| source | 원인 | 완화 | status |
|---|---|---|---|
| **dcinside** | 애매한 DEGRADED(기술 결함처럼 보였던 본문 미수집) | DEGRADED 폐기 → **community preview signal 역할로 재정의**(신규 tier `PRODUCTION_READY_COMMUNITY_PREVIEW`, memory final_status `COMMUNITY_PREVIEW_SIGNAL_ALIVE`). detail body static audit는 DETAIL_BODY_ALIVE(best_body_chars=230, 짧아 보수적으로 preview 역할 유지), PII(작성자 닉네임) 미수집. live 30 community_signal, source-specific proof eq=30/raw=30 contract_pass=True. publish는 게이트로 봉인(publish_gated). | CLOSED_BY_DESIGN (역할 재정의; ToS publish 해제는 legal review 전제로 잔존) |
| **gdelt** | provider 429(cooldown 만료 후 정책 준수 spaced probe 실 재시도에서도 실제 provider 429) | 우회 금지 → 정직한 provider hard blocker. 단순 pending이 아닌 **escalation-capable scheduled state**: consecutive_pending 카운터(run마다 증가, threshold=3 도달 시 ESCALATE), host-level cooldown 영속(next_resume_at), query ladder profile(broad\|single_keyword\|narrow), 재현 커맨드(repro_cmd). RateLimitGovernor host-level min_interval 10s. colab parity는 코드 동일(endpoint+params+parse, test-verified), 응답 레벨 diff는 UNVERIFIED 정직 표기. single 429로 disabled 안 함. | DEFERRED_WITH_TRIGGER (자동 재개 + escalation 카운터; 비-throttle 윈도 fresh 확보 시 해소) |
| **CommunityCorroborationGate** | G-3 미구현이던 corroboration/펌핑 차단 게이트 | 신규 모듈 `community_corroboration_gate.py`: 익명 금융/투자 갤러리(stockus 등)→`internal_queue_only`, 펌핑/투자권유성 제목(매수/풀매수/가즈아/떡상/목표가 등)→`publish_blocked_until_corrob`, 그 외 커뮤니티→`preview_candidate`. 익명 source는 항상 `requires_external_confirmation=True`(CLAUDE.md 원칙1 info-not-advice 정렬). | CLOSED_BY_DESIGN (게이트 구현; publish 파이프라인 하위 wiring은 후속 과제) |
| **culture_info / product_hunt** | G-3 eq/raw=0(공유 dedup collapse) 약점 | 신규 `source_specific_proof.py`가 **격리 dedup namespace**로 source별 EventQueue/raw_events contract 통과 입증 → culture_info eq=5/raw=5, product_hunt eq=5/raw=5, contract_pass=True. 공유 production dedup의 collapse(eq=0)는 contract 실패가 아니라 정상 dedup임을 명확화. product_hunt 실 url/createdAt(합성 slug 거부), culture_info detail2 실 url+startDate. | CLOSED_BY_DESIGN (source-specific proof로 약점 제거) |

**적대 리뷰/정직성 흡수**:
- dcinside 본문 미수집은 degradation이 아니라 **역할 정의**임을 명확화(best_body_chars=230으로 짧아 보수적으로 preview 역할 유지). ToS-verified를 사칭하지 않는다 — 수집/큐 적재는 닫되 publish는 게이트로 봉인(publish_gated).
- gdelt single 429를 disable로 둔갑시키지 않음. 응답 레벨 diff 저장본 없음을 UNVERIFIED로 정직 표기(코드 parity는 test-verified로 분리).
- 공유 dedup의 eq=0 collapse를 "contract 실패"로 과장하지 않고 정상 dedup임을 격리 namespace proof로 분리 입증.

**남은 risk(미해소, 정직)**:
1. **gdelt provider 429** — 자동 재개 scheduled + escalation 카운터 구현됨. 비-throttle 윈도에서 fresh 확보 필요(여전히 open 비제외 항목).
2. **dcinside ToS legal review** — publish 해제 전제(수집은 닫힘). legal-safety-compliance-reviewer 검토 잔존.
3. **CommunityCorroborationGate publish 파이프라인 wiring** — 게이트는 구현됐으나 publish 파이프라인 하위에서 소비하는 wiring은 후속.

**LLM agent hints(StrategyMemory `llm_agent_hints` 필드)**: 소스별 안전 힌트 저장(dcinside: community_preview_signal_is_valid_role / corroboration_required / avoid_pii_author_collection / no_publish_without_external_confirmation; gdelt: never_disable_on_single_429 / use_host_level_rate_limit / replay_colab_success_profile_first / simplify_query_before_declaring_failure / save_next_resume_at; culture_info: require_real_detail_url_or_stable_id / reject_local_or_synthetic_evidence; product_hunt: require_actual_api_url_or_slug / reject_name_slug_synthetic_fallback / require_createdAt_or_observed_at). SourceSupervisor는 LLM이 우회(proxy_rotation 등)를 제안해도 AllowedStrategyRegistry 밖이면 거부한다.

**흡수 구조(나열식 if 금지)**: SourceCapability → PolicyProbe → StrategyGraph → ToolPlan → EvidenceGate → CommunityCorroborationGate → GdeltRateLimitProfile(RateLimitGovernor host-level) → SourceSpecificProof → StrategyMemory(+llm_agent_hints) → ProductionState(+PRODUCTION_READY_COMMUNITY_PREVIEW tier) → Monitoring → SourceSupervisorDecision(LLM-ready, unsafe 전략 거부).

**NEXT_STEP**:
- gdelt → provider 비-throttle 윈도에서 fresh 확보(escalation 카운터·next_resume_at 이미 구현).
- dcinside → legal-safety-compliance-reviewer 핸드오프(publish 해제 전제, 수집은 닫힘).
- CommunityCorroborationGate → publish 파이프라인 하위 소비 wiring.

검증: 전체 회귀 **1205 passed**, secret scan **PASS**, no bypass(robots 허용 path·cooldown 존중·CAPTCHA/login/cloudflare 감지 시 중단·proxy/anti-bot 0), 전 outputs gitignored. 신규 테스트 7개(test_g4_final_risk_closure, test_dcinside_detail_final_closure, test_community_corroboration_gate, test_gdelt_rate_limit_profile, test_source_specific_proof_mode, test_llm_agent_strategy_hints, test_gdelt_colab_parity_recovery). 최종 분포: PRODUCTION_READY 46 / PRODUCTION_READY_COMMUNITY_PREVIEW 1(dcinside) / EXTERNAL_RATE_LIMITED 1(gdelt) / POLICY_EXCLUDED 9 = 57. degraded_remaining 0, unknown 0, critical_alerts 0, non_excluded_not_ready 1(gdelt).

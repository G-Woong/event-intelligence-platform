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
| **gcp 키 노출** | 루트 secret 파일 | 자격증명 유출 | gitignore/scan | 사람 점검(V-9) | scan_secrets | security-guardian | USER_CONFIRMATION_REQUIRED |
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

---

## 6. USER_CONFIRMATION_REQUIRED (종합)

| question | why | default | blocking |
|---|---|---|---|
| Phase A(설치 0)부터? | 빠른 증명 | 예 | No |
| langgraph 0.2.76 유지? | 회귀 위험 | 유지 | No |
| Deep Agents/MCP 도입? | 복잡도/정책 | 미도입/future review | Yes(정책) |
| Redis/Postgres 컨테이너 가동 가능? | Phase G/H | 환경 확인 | Phase G |
| 루트 gcp 키 gitignore 확인? | 자격증명 | 즉시 확인 | **Yes(보안)** |
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
| gcp 키 gitignore 점검? | 보안 | 즉시 | Yes |
| Phase A부터 구현 시작? | 안전 진입 | 예 | No |

> 다음 문서: `README.md` (진입점).

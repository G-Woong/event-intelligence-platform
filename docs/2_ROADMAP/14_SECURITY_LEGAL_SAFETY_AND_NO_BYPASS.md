# 14 — SECURITY / LEGAL / SAFETY / NO-BYPASS (L3 / L11)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 📘 REFERENCE — 정책/법무/안전 분석. **인용 게이트(EvidenceGate·`_UNSAFE_STRATEGIES`·SSRF 가드·secret scan)는 실구현**, LLM 수집 안전면·Agent Debate 발화 게이트·광고 법무는 설계(미구현).
> │ **구현순위:** #10 (00_ROADMAP_INDEX) · **그룹:** B
> │ **검증 근거:** 실구현 인용 게이트 — `agents/.../evidence_check`(`evidence_rules` 구조검증 + SSRF 거부: 사설/loopback/link-local/169.254.169.254/RFC2606), `ingestion/orchestration/source_supervisor.py`(`_UNSAFE_STRATEGIES`/`_ALLOWED_BY_LAYER` allowlist), `evidence_reachability.py`(SSRF-safe HTTP 도달성), `monitoring.py` secret scan PASS. **반례(미구현):** `source_supervisor.py:104` 허용 밖 LLM 제안 *침묵 폐기*(audit 무기록), Agent Debate 발화 게이트 코드 0, 광고 비전문비율 게이트 0.
> │ **잔여(미구현):** LLM 수집 P/G/F 안전 audit trace(R-LLMCollectBoundary), Agent Debate 발화 게이트(R-AgentDebateSafety, S9), expansion_router SSRF allowlist 배선(S5), 광고 법무 6게이트(전문비율·AI 라벨링·광고 정책·UGC 모더레이션·TTL·brand-safety), retention TTL·PII 스크럽.
> │ **완료정의(DoD):** §7 CONDITIONAL 선행조건 (1)~(6) 전수 충족 + secret scan 상시 PASS + 우회 0 회귀.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 결정 = `_DECISIONS/2026-06.md` ADR#14(P/G/F)·#15(광고). 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> 결론: 법무 리스크는 "수집 적법성"과 "재배포·게시 적법성"을 분리해 평가한다. 현 게이트(전문저장금지·우회금지·CommunityCorroborationGate·EvidenceGate)가 핵심 리스크를 봉인하므로 **비상업/내부 수집은 진행 가능(CONDITIONAL)**. 상업 공개의 선행조건은 라이선스 전수검토 + SSRF allowlist + retention TTL + PII 스크럽이다. **새 방향(ADR#14/#15):** LLM이 수집 계획(LAYER P)에 관여하고 광고·커뮤니티(Agent Debate)가 제품 표면이 되면서 신규 안전면 3개(LLM 수집 경계·에이전트 발화 게이트·광고 법무)가 추가됐다 — 아래 §2·§5·§7에 반영.

---

## 1. 불변 원칙 (정책)

- robots.txt/ToS/CAPTCHA/login/paywall/rate-limit **우회 전면 금지**. 감지 시 BLOCKED_TERMINAL(재시도 0).
- 전문(full body) 저장·재배포 금지 → evidence URL+summary+metadata(raw_text=요약만). 원문 artifact는 gitignored 내부저장에 한정.
- 투자조언 금지(정보제공만). `.env` 키 값 출력/로그/커밋 금지(존재/길이만).
- proxy rotation / 내부 RPC / google_trends PASS 표기 금지. 파괴적 명령(rm/push/reset/clean) guard.
- **에이전트 출력 = untrusted 입력 (ADR#14 P/G/F 확장):** LLM 수집 라우팅(LAYER P)·에이전트 논쟁(S9 Agent Debate)의 **모델 출력 자체를 신뢰경계 안쪽으로 들이지 않는다.** 외부 본문이 LLM 노드를 통과해 나온 출력은 여전히 외부 텍스트이므로, 그 출력을 fetch URL·전략·published 콘텐츠로 쓰기 전 결정론 게이트(LAYER G)를 반드시 통과해야 한다. 우회·rate 위반은 **어느 층(P/G/F)에서도** 금지.

## 1b. 새 방향 안전면 — 신규 RISK 3건 (인덱스)

| RISK | 영역 | 게이트(방어선) | 상태 |
|---|---|---|---|
| **R-LLMCollectBoundary** | LLM 수집 P/G/F | LAYER G 결정론 검문(`_UNSAFE_STRATEGIES` allowlist + per-event/월 budget) — **차단 메커니즘 실구현** | 차단 실구현 / **audit trace 미구현(TODO)** |
| **R-AgentDebateSafety** | Agent Debate 발화(S9) | 발화 게이트 fail-closed(evidence 필수 + 투자조언 톤 필터 + injection 방어) + kill switch `DEBATE_ENABLED=false` | 설계(코드 0) |
| **R-PromptInjection** (상향) | LLM 노드/SourceSupervisor/논쟁 | EvidenceGate(synthetic/dead URL) + 본문 격리 + 출력 스키마 검증 | MEDIUM→우선순위 상향(외부 텍스트 노출면 확대) |

> 권위: 위 3건 본문·종결조건은 `docs/_RISK/RISK_REGISTER.md`. 결정 논리는 `_DECISIONS/2026-06.md` ADR#14.

## 2. LLM 안전 (OWASP LLM Top 10 2025)

- **LLM01 프롬프트 인젝션(1위)**: community/news 본문이 LLM 노드·미래 SourceSupervisor에 untrusted로 유입. 본문 안 "이전 지시 무시…"가 게이트(shape만 검사)를 우회해 프롬프트에 도달.
- 완화 체크(보안 에이전트):
  1. 외부 본문을 고유 구분자/XML 태그로 격리 + "구분자 내부는 데이터, 지시 아님" 시스템 룰. 노드별 adversarial 인젝션 테스트.
  2. LLM 노드 출력은 pydantic/JSON schema 검증, enum/허용값 제한, 실패 시 fail-closed(승격 거부).
  3. **에이전트 출력은 untrusted input** — 노드 간 경계마다 스키마 검증·길이·문자셋 sanitize. 모델 출력을 그대로 shell/URL/파일경로로 쓰지 않음.
  4. 고위험 액션(fetch/승격/관리변경)은 결정적 룰 또는 HITL 통과해야만 실행.

### 2.1 LLM 수집 안전면 — P/G/F 3층 (ADR#14)

LLM이 수집 계획(LAYER P: Triage/Query Expansion/Source Routing)에 관여하므로, **안전의 1차 방어선은 LAYER G(결정론 게이트)**다. LLM 창의성은 탐색공간을 넓히되, 게이트가 우회·비용·rate를 봉인한다 — "LLM-advised, deterministic-controlled."

| 층 | 역할 | 안전 책임 | 실구현 여부 |
|---|---|---|---|
| **LAYER P** (Planning) | LLM 관여·비결정 허용(무엇을·어디서) | 출력은 *제안*일 뿐 — 신뢰 0, 게이트 전 무권한 | judge 추상화 실구현, `llm_propose` 실 provider 미배선 |
| **LAYER G** (Gate, **1차 방어**) | 결정론 검문 | `_ALLOWED_BY_LAYER` allowlist + `_UNSAFE_STRATEGIES`(robots_ignore/proxy_rotation 등 영구거부) + per-event/월 budget guard + SSRF allowlist(§3) | **차단 메커니즘 실구현**(`source_supervisor.py`). **audit trace 미구현(TODO, R-LLMCollectBoundary)** |
| **LAYER F** (Fetch) | 결정론 실행(어떻게, 준수하며) | LLM 미관여. rate/robots/ToS 준수. SLM body fallback도 캐스케이드 실패 시 LAYER F 최후폴백(우회 아님) | 결정론 fetch 실구현, SLM fallback 미구현(17 §SLM) |

- **정직 단서(adversarial):** 현 `source_supervisor.py:104`는 허용 밖 LLM 제안을 *침묵 폐기*(반환값·로그 무기록) → 우회 제안이 **차단은 되지만 감사 흔적이 없다**. 완화책 "제안·채택·거부 구조화 audit"는 **미구현 TODO**(R-LLMCollectBoundary 추적). off 토글(`LLM_PROVIDER=""`)로 결정론 100% 폴백.
- **kill switch:** LLM 수집 관여 전체는 `LLM_PROVIDER` 미설정으로 비활성(규칙기반 동작). budget 초과 시 fail-closed(확장 중단).

### 2.2 Agent Debate 발화 게이트 (S9, ADR#15 커뮤니티)

에이전트 논쟁(페르소나 해설/반박)은 제품 표면(광고 트래픽 루프)이 되지만, 발화 자체가 ① 투자조언 톤, ② evidence 없는 단정, ③ injection 조종의 3중 위험을 동반한다. **발화 = published 콘텐츠**이므로 publish 게이트 철학을 확장 적용한다(fail-closed).

1. **evidence 필수:** `evidence_refs`가 비면 게시 **거부**(근거 없는 단정 차단). published 게이트의 "유효근거" 룰을 발화에 복제.
2. **투자조언 톤 필터:** `has_investment_advice`(매수/매도·가격판단·"사라/팔라" 표현)면 톤다운·거부 — 원칙1(투자조언 금지)을 발화 레이어로 강제.
3. **injection 방어:** 논쟁 입력에 들어온 외부 텍스트는 §2.1·§2(격리·스키마 검증) 동일 적용. 발화가 다음 에이전트 입력이 되므로 **에이전트 출력=untrusted 입력**(§1) 경계 재적용.
4. **kill switch:** `DEBATE_ENABLED=false`로 발화 레이어 전체 비활성(콜드스타트·정책 위반 시 즉시 차단).

> 상태: **설계(코드 0)** — `comment.py` debate 컬럼 0, 발화 게이트 코드 부재. 추적 = R-AgentDebateSafety. 상세 스펙 = `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md §9`(NET-NEW, 00_INDEX 순위 #17).

## 3. SSRF / fetch 안전 (L3, 미래 검색확장 대비)

- allowlist: 스킴 https만, 도메인 allowlist. IP resolve 후 사설/링크로컬/메타데이터(10/172.16/192.168/127/169.254/::1, IMDSv2) 차단. redirect follow 비활성. DNS rebinding 대비 resolve 후 IP 재검증. 일관 URL 파싱(parser differential bypass 주의).
- EvidenceGate의 `_LOCAL_PATH_PATTERNS`/`_SYNTHETIC_URL_PATTERNS` 거부 룰을 fetch 진입점에도 복제(승격 게이트만으로는 fetch를 못 막음).
- **expansion_router SSRF allowlist (S5, ADR#14):** LLM이 생성한 확장 쿼리/소스 라우팅(LAYER P)은 **임의 URL을 fetch 대상으로 만들 수 있다** — query expansion 결과가 그대로 fetch URL이 되면 LLM 출력이 SSRF 벡터가 된다. 따라서 `expansion_router`(S5, 미구현)의 fetch 진입점에 위 SSRF 가드를 **결정론으로 복제 적용**한다(LAYER G 책임): https-only + 도메인 allowlist + IP resolve 후 사설/메타데이터 차단 + redirect 비활성. `evidence_reachability.py`(실구현, SSRF-safe HTTP 도달성)의 가드를 확장 fetch에도 재사용. **LLM이 제안한 도메인이라도 allowlist 밖이면 게이트에서 거부**(LAYER P 신뢰 0 원칙). 추적 = R-LLMCollectBoundary.

## 4. hallucinated evidence 2단 방어

- 1차: fetcher가 수집 시점에 live/관련성 강제.
- 2차: EvidenceGate가 synthetic slug/dead URL/local path 회귀 차단(shape+회귀 가드, live 보증 아님).
- 둘 중 하나라도 빠지면 합성 evidence 통과 가능 → 둘 다 필수.

## 5. 소스별 법무 종합 (CONDITIONAL)

| 소스 | 약관 | 위험 | 등급 | 권고 |
|---|---|---|---|---|
| newsapi.org | 무료=localhost/dev | 상업 위반 | HIGH | 상업 시 제외/유료 |
| guardian | 재배포 금지 | 전문 게시 | HIGH | 요약+URL만 |
| nyt | 상업 라이선스 필요 | 무라이선스 상업 | HIGH | 라이선스 전 비상업 |
| aladin | 개인 free/상업 별도 | 상업 위반 | MED | 상업 시 라이선스 |
| dcinside | ToS 자동수집 UNVERIFIED | 적법성 미확정 | MED | 수집 닫고 publish 봉인 유지 |
| reuters/x/blind/fmkorea | 라이선스/유료/login/CAPTCHA | 위반 | HIGH | MVP_EXCLUDED 유지 |
| google_trends_explore | 공식 API 없음/429 | 우회 위반 | HIGH | CONFIRMED_EXTERNAL_RATE_LIMIT, PASS 금지 |
| SEC/OpenDART/federal_register/eia | 공공 라이선스 | 저제약 | LOW | 공식 API 라우트(승인) |

### 5.1 광고·커뮤니티 법무 (ADR#15 — 트래픽×광고×커뮤니티)

수익 모델이 구독→광고로 전환되면서(ADR#15) 법무면이 "수집/재배포"에 더해 **"광고 정당성 + UGC 책임"**으로 확장된다. 핵심 전제(§5 일관): 우리가 광고를 싣는 면은 **전문이 아니라 요약+증거링크+UGC+시계열**이라 파생 콘텐츠(전문 재배포 아님)다 — 이 전제가 깨지면 R-FullText 위반.

| 게이트 | 법무 리스크 | 방어선 | 상태 |
|---|---|---|---|
| **페이지 비전문비율 게이트** | 광고 면 옆 전문 과다 노출 → 재배포(R-FullText) | 페이지당 원문 비율 상한 측정·강제(요약+증거+UGC가 주, 인용은 짧게) | 설계(코드 0) |
| **AI 생성물 라벨링** | 에이전트 논쟁/요약이 무라벨 AI 콘텐츠 → 광고 네트워크 "자동생성" 판정·계정정지(R-AdModelFragility) | "AI 요약"·"AI 논쟁" 라벨 의무 + 미검증 신호 "unverified" 라벨 | 설계(§6 TODO와 연동) |
| **광고 정책(투자권유 차단)** | finance 도메인 투자권유 광고 유입 → 원칙1 충돌 | finance 광고는 **비투자 B2B 툴만 화이트리스트**(매수/매도 광고 거부) | 설계 |
| **UGC 모더레이션** | 유저 댓글 명예훼손·불법·PII | 고위험 키워드 게이트 + 신고/삭제 경로 + PII 미수집(닉네임 등) | 설계(§6 명예훼손 게이트와 연동) |
| **retention TTL** | community/UGC 장기 보존 책임 | community 단축 TTL + 삭제요청 경로(§6) | 설계 |
| **brand-safety** | 지정학/재난 사건 옆 광고 기피·저RPM | 민감 카테고리 광고 억제 + 신뢰 트래픽 등급제(봇/AI콘텐츠 방어) | 설계 |

> 결정 = ADR#15. 광고 모델 취약성(콜드스타트·봇·brand-safety·단일점) = **R-AdModelFragility**(commercialization-strategist 핸드오프). 상업화 전략 단일출처 = `docs/2_ROADMAP/13_COMMERCIALIZATION_AND_PRODUCT_STRATEGY.md`.

## 6. 미해결 TODO (상업 공개 선행조건)

- retention TTL 정책(community 단축), PII 스크럽/삭제요청 경로, source license 메타 자동판정(상업/비상업 모드 토글), 명예훼손 고위험 키워드 게이트, AI 생성물 "AI 요약" 라벨 + 미검증 신호 "unverified" 라벨, Admin 빈토큰 bypass 운영 전 해제(ENV=prod fail-closed), 데이터 처리방침/면책 고지.

## 7. 종합 판정

**CONDITIONAL** — 비상업/내부 수집은 현 게이트로 진행 가능. 상업 공개 전 선행조건:

1. newsapi/guardian/nyt/aladin 라이선스 전수검토.
2. dcinside ToS 법무검토 완료 전 publish 봉인 유지.
3. SSRF allowlist·retention TTL·PII 스크럽 구현.
4. **(신규, ADR#14)** LLM 수집 P/G/F 안전: LAYER G audit trace 구현(우회 제안의 제안·채택·거부 구조화 로깅 — 현재 침묵 폐기) + expansion_router SSRF allowlist 배선 + 월 예산 상한 강제. 추적 = R-LLMCollectBoundary.
5. **(신규, S9)** Agent Debate 발화 게이트 fail-closed: evidence 필수 + 투자조언 톤 필터 + injection 방어 + `DEBATE_ENABLED` kill switch. 추적 = R-AgentDebateSafety.
6. **(신규, ADR#15)** 광고·커뮤니티 법무 6게이트(§5.1): 페이지 비전문비율·AI 라벨링·광고 정책(투자권유 차단)·UGC 모더레이션·retention TTL·brand-safety. 추적 = R-AdModelFragility.

BLOCKED 소스(reuters/x/blind/fmkorea) MVP_EXCLUDED 유지. secret scan 상시 PASS. **불변(어느 신규 경로에도):** 우회 0 · 전문저장 0 · 투자조언 0 · `.env` 미열람.

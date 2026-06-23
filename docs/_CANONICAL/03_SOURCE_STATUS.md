# 03 — SOURCE STATUS (소스 현황 단일 출처)

- 근거: `ingestion/outputs/state/production_source_state.json` (기준 커밋 93e83b6)
- 총 **57** 소스, degraded 0, unknown 0, critical 0.

---

## 1. production-state 분포

| tier | 수 | 의미 | schedulable |
|---|---:|---|---|
| PRODUCTION_READY | **46** | 실데이터 + EvidenceGate 통과, caveat 없음 | ✅ |
| PRODUCTION_READY_COMMUNITY_PREVIEW | **1** | dcinside — community signal 역할로 닫힘(애매한 DEGRADED 아님) | ✅ (publish gated) |
| EXTERNAL_RATE_LIMITED | **1** | gdelt — provider 429, 자동재개 scheduled | ⏸ (cooldown) |
| POLICY_EXCLUDED | **9** | 의도적 제외(robots/ToS/login/정책) | ⛔ |
| **합계** | **57** | degraded 0 | |

## 1b. Source Role Taxonomy (역할 분류 — `source_role.py` 파생)

각 source 의 **본질적 역할**은 `source_profiles.yaml` 의 `source_group`/`is_community`/
`confirmation_policy` 에서 **결정론적으로 파생**한다(`ingestion/orchestration/source_role.py`,
새 데이터 하드코딩 0). 역할(무엇을 위한 source 인가)과 final_action(이번 run 운영 상태)은
**직교**한다 — excluded 된 reuters 도 본질은 ARTICLE_BODY 이고 단지 final_action=SKIPPED 일 뿐.

| source_role | 수 | 파생 기준(group/flag) | routing_mode | publication 규칙 | 예시 |
|---|---:|---|---|---|---|
| ARTICLE_BODY_SOURCE | 14 | group=news | backend_sink, body면 published·snippet이면 hold | published_if_body_and_evidence_else_hold | bbc, ap_news, yna |
| EXPANSION_SEARCH_SOURCE | 7 | group=search (is_community=false) | expansion candidate(증거 아님) | **never_direct_publish** (expansion only) | serper, tavily, exa, gnews, naver_news_search |
| OFFICIAL_RECORD_SOURCE | 8 | group=official | backend_sink, evidence_required | published_if_evidence_complete_else_hold | sec_edgar, gdelt, federal_register, opendart |
| STRUCTURED_SIGNAL_SOURCE | 6 | group=market (purpose=numeric) | structured signal 또는 expansion seed | signal_only_not_article_card | coinbase_market, binance_market, finnhub |
| COMMUNITY_EARLY_SIGNAL_SOURCE | 9 | is_community=true OR group=community | hold + corroboration 필요 | **never_direct_publish** (hold until corroborated) | hacker_news, dcinside, product_hunt, naver_blog_search |
| ENRICHMENT_ONLY_SOURCE | 13 | group∈{trend,domain} | enrichment, 대량 큐 투입 금지 | enrichment_no_direct_publish | google_trending_now, kma, tmdb, kofic |
| **합계** | **57** | | | | |

- **PERIODIC_EVENT_QUEUE_SOURCE**: news/official 에 부여되는 **보조 역할**(주기 수집 → EventQueue).
- **운영 상태(역할 아님, final_action)**: POLICY_EXCLUDED 9 / RATE_LIMITED_SCHEDULED 1(gdelt) /
  HELD_BY_POLICY 1(dcinside) / NEEDS_KEY(키 미설정 callable) / CALLABLE_NOT_PROBED 46.
  → `run_orchestration_source_validation` 이 role + final_action 을 한 표(SOURCE_ROLE_MATRIX +
  SOURCE_FINAL_ACTION_MATRIX)로 emit. 잠금: `tests/unit/test_source_role_taxonomy.py`(36).
- **헌법 3(역할별 연결) 보증**: search=expansion candidate(증거 승격 금지), community=hold(corroboration
  전 publish 금지)를 publication_policy 가 코드로 강제 — `EXPANSION_SEARCH`/`COMMUNITY_EARLY_SIGNAL` 은
  publication_policy 에 `never_direct_publish` 를 항상 포함(테스트로 잠금).
  - ⚠️ **범위 한정(ADR#32, 2026-06-23):** 이 강제는 **경로 A(event_cards 발행)** 의 publication_policy 다.
    **경로 B(Event 타임라인 / `event_resolver`)는 source_type 무관(signal 강도) 라우팅**이라 이 게이트를
    거치지 않는다 — pure-community/structured cross-source 클러스터가 **발행 Event 를 만들 수 있다**(검증
    재현: S5/S6/S7). 두 발행 경로의 게이트 불일치 → **R-SourceTypeFidelityGate**(미해소).

## 2. 비-excluded 4개 risk source 최종 상태 (Phase G-4)

| source | 역할 | successful_strategy | 비고 |
|---|---|---|---|
| dcinside | community preview signal | robots_allowed_static_list_community_preview | 본문 source 실패 → 신호 source로 역할 재정의. 금융 익명 갤러리는 `internal_queue_only`, 펌핑/투자권유 제목은 publish_blocked. **ToS 자동수집 적법성 UNVERIFIED → 수집은 닫고 publish는 게이트 봉인.** |
| culture_info | official record | period2_detail2_real_url | source-specific proof eq=5/raw=5 contract_pass |
| product_hunt | community signal | ph_graphql_real_url_createdAt | source-specific proof eq=5/raw=5 contract_pass |
| gdelt | official record(rate-limited) | host_rate_limit_spaced_probe | provider 429. host-level cooldown 영속, consecutive_pending 카운터(threshold=3 escalate), next_resume·repro_cmd·query_profile 기록. **단일 429로 disable 금지.** |

## 3. POLICY_EXCLUDED 9개 (불변, 미접촉)

login/CAPTCHA/paywall 벽 또는 ToS·정책상 자동수집 불가 소스(예: X/Twitter, Blind 등 login-required).
**우회 금지 원칙상 종결 상태이며, 사용자 명시 지시 없이는 손대지 않는다.**

## 4. 검증 방식 (eq/raw=0 약점 해소)

공유 production dedup이 collapse하면 eq=0이 될 수 있으나 이는 **정상 dedup이지 contract 실패가 아니다.**
`source_specific_proof.py`가 **격리 dedup namespace**에서 소스별 EventQueue/raw_events 계약을 독립 입증한다(`contract_pass`).
risk closure 판정(`classify_risk_closure`)은 공유 eq 카운트가 아니라 **role(final_status) + source-specific proof**를 권위 증거로 쓴다.

## 5. ⚠ 충돌 주의 — 두 개의 "소스" 개념

- **이 문서(ingestion 엔진)**: 57소스.
- `system_overview/`, `workers/collectors/`: RSS 3소스(bbc/reuters/yna) — **다운스트림 앱의 별도 수집 경로**.
  이 3소스는 stale가 아니라 *다른 서브시스템*이다. ingestion 57소스가 다운스트림으로 통합되면 정리 대상(04 T-IngA).
- `INGESTION_FINAL.md`의 "44 CORE_READY / 58 합계" 수치는 G-2 이전 값 → 현재 46 PRODUCTION_READY / 57 (06 C-2).
- `system_overview/09·10·11`의 "DART/SEC/trafilatura 미구현 TODO"는 **stale** — ingestion에
  `sources/opendart.py`, `sources/sec_edgar.py`, `tools/trafilatura_extractor.py` 이미 존재(06 C-3).

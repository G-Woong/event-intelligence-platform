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

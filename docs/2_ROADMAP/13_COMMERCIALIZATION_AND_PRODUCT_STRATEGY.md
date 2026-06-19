# 13 — COMMERCIALIZATION & PRODUCT STRATEGY (L0 / L13 / L14)

> **상업화 단일 출처 (2026-06-19):** 상업화·수익모델·가격 논의는 이 문서가 권위. 구 중복본 `Orchestration_Construction/10_COMMERCIALIZATION`(→ `3_ARCHIVE/2026-06_orchestration_design/`로 보관)과 `18_FINAL_EXECUTIVE_SUMMARY`의 상업화 단편은 여기로 통합됨. 전부 **미구현 ROADMAP**이다(현재 구현 사실은 `_CANONICAL/*`).

> 결론: 이 플랫폼은 검색엔진이 아니라 event intelligence platform이고, **1차 수익은 광고가 아닌 B2B alert/report/API**다. MVP는 단일 vertical로 좁히고, source coverage보다 event quality로 차별한다. 단, **P0 브리지(A→B)가 풀리기 전 영업은 공허**하다(데모 불가).

---

## 1. 상업화 10대 판단 기준

1. 검색엔진이 아니라 event intelligence platform이다.
2. 직접 웹 전체 크롤링은 비현실적이다.
3. core source + 검색 API + 자체 index + LLM judge + event graph 조합이 현실적.
4. 초기 MVP vertical을 좁혀야 한다.
5. source coverage보다 event quality가 중요하다.
6. full body 저장보다 evidence URL+summary+metadata가 안전하다.
7. community source는 early signal이지 verified evidence가 아니다.
8. B2B alert/report/API가 광고보다 현실적 수익화다.
9. 저작권/robots/API terms가 제품 범위를 결정한다.
10. LLM agent는 판단자이지 무제한 crawler가 아니다.

## 2. MVP vertical 평가 (1-5, Score 합산)

| Vertical | Source avail | WTP | Legal risk(낮을수록↑) | Differentiation | MVP feasibility | Score |
|---|---|---|---|---|---|---|
| **AI/tech 제품 incident** | 5 | 3 | 5 | 4 | 5 | **22** |
| 정책/규제(federal_register/EU/공시) | 4 | 4 | 5 | 4 | 4 | 21 |
| 금융/공시/시장(sec/opendart) | 5 | 5 | 2(투자조언 경계) | 4 | 4 | 20 |
| 반도체/배터리/전자 | 3 | 4 | 4 | 3 | 3 | 17 |
| 미디어/브랜드 리스크 | 4 | 3 | 3 | 4 | 3 | 17 |
| 글로벌위기/안보 OSINT | 3 | 4 | 2(오정보) | 4 | 3 | 16 |

**추천 1차 vertical: AI/tech 제품 incident(22)** — 소스가 가장 두껍고(전용 6+커뮤니티 반응) 투자조언/안보 오정보 지뢰가 없어 정책 불변조항과 충돌 최소. ICP: AI/SaaS 제품팀·DevRel·경쟁 모니터링 PM. **Phase 2 확장: 금융/공시(WTP 최고).**
> 적대적 비판 대안: "한국 규제/공시 vertical(opendart/krx/federal_register)"도 1인이 방어 가능한 해자 후보. 두 안 모두 좁은 vertical 집중이라는 점에서 일치.

## 3. 제품 표면 우선순위 (L13)

```text
alert > API > report > dashboard(이미 구현, lead-in) > community(후순위)
```

- **alert**(이벤트 push): retention/B2B 매출 1순위. confidence+evidence 인프라 재사용 → ROI 높음. 규칙 빌더(theme/sector/keyword), 채널(email/web/webhook), 빈도 제어.
- **API**: events/search를 외부 계약으로 노출 + 키 인증 + rate plan(usage 과금).
- **report**: themes/sectors 집계(PARTIAL 해소 선행), 주간 vertical 요약.
- **신뢰 UI(차별 핵심)**: evidence를 `string[]` → `{source_name, url, published_at, snippet, source_status}` 구조화. confidence는 근거 추적 tooltip + 가치판단 없는 중립 표기. 재배포 금지 소스(guardian/nyt)는 snippet+링크만.
- PARTIAL 처리: comments/ai_replies는 feature flag 뒤로(MVP 제외), themes/sectors는 "미검증" 라벨.

## 4. 가격 모델 (L14)

- 웹 리서치: 순수 per-seat 15%로↓, **61% hybrid(base+usage)**, 3-4 티어. AI가 seat-가치 상관을 깸 → usage 신호(alert 발송/API콜/레코드).
- 구조: Free(기본 피드+제한 alert) / Pro(무제한 alert+evidence 심층) / Team(다인+섹터필터) / Enterprise(API+custom+SLA). base seat + usage add-on.
- 진입가는 경쟁 최저가 이하(SMB 침투). enterprise는 custom.

## 5. 경쟁 차별 (4축) & 수익 경로 (3)

- 차별: ① 다중소스 교차검증 ② 증거체인(evidence link) ③ 사건중심 능동감지 ④ 정보제공 규제안전.
- 대비: Dataminr(가격 접근성)·AlphaSense(능동 alert vs 검색)·Recorded Future(범용 incident vs 사이버)·Meltwater/Talkwalker(증거검증)·Liveuamap(검증+요약 vs 지도).
- 수익 경로: ① alert 구독 ② B2B event queue API ③ 정기 리포트 구독.

## 6. 버려야 할 착각 / KPI / 검증기준

- 버릴 착각: "57소스 다 켜면 가치↑"(P0 전엔 무의미), "광고로 무료앱"(전재 금지+트래픽 부재), "google_trends/x로 실시간 우위"(차단/제외 소스).
- 6개월 KPI: 파일럿 LOI 3 + 유료 30 + MRR 검증. false alert rate·churn·LTV/CAC(≥3) 추적.
- 검증기준: P0 해소 → 단일 vertical 라이브 큐 → freemium → alert 구독(수익경로1) → 파일럿 LOI 3 → API 베타(수익경로2). 차별 4축 + hybrid 3-4티어 가격표 + bottom-up SOM 확정. **TAM은 bottom-up(ICP수×ARPU)만**, 근거 없는 top-down 금지.

> 주의: 본 문서는 정보 제공 목적이며 투자 조언이 아니다.

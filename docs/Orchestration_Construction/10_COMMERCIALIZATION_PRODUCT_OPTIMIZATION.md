# 10 — 상용화 / 제품 최적화 (Commercialization & Product Optimization)

> **목적**: 오케스트레이션을 "기술 과시"가 아니라 **제품 가치와 사업 지속성**의 관점에서 최적화한다. 어떤 데이터가 가치를 만들고, 무엇이 과잉인지 가른다.
> **원칙**: 이 시스템은 **정보 제공이지 투자 조언이 아니다**(CLAUDE.md 원칙 1). 가격을 "사라/팔라"로 변환하지 않는다.

---

## 0. 비개발자를 위한 설명

좋은 기술이 곧 좋은 제품은 아니다. 사용자는 "LangGraph를 썼는지"에 관심이 없다. 사용자는 **"내가 알아야 할 사건을, 믿을 수 있게, 남보다 빨리"** 알고 싶을 뿐이다.

이 문서는 우리가 만든 수집 오케스트레이션이 **그 사용자 가치로 어떻게 연결되는지**, 그리고 **출시를 늦추는 과잉 기능은 무엇인지**를 정리한다. 핵심 질문은 늘 하나다: **"이 기능이 사용자가 다시 찾아올 이유가 되는가?"**

---

## 1. 어떤 데이터가 제품 가치를 만드는가

| 데이터 | 사용자 가치 | 오케스트레이션 기여 |
|---|---|---|
| **다양한 소스의 사건** | "한 곳에서 다 본다" | 44개 소스 연결(시스템 A↔B 브리지) |
| **빠른 사건 발견** | "남보다 먼저 안다" | near_real_time bucket(시세·yna 5~15분) |
| **교차 검증된 사건** | "믿을 수 있다" | evidence_coverage + community/official balance(09) |
| **사건의 맥락** | "왜 중요한지 안다" | related_expansion + 공식 출처 연결 |
| **깨끗한 본문/요약** | "읽기 쉽다" | body cascade(04) + 다운스트림 요약 |

**1순위 가치 = 소스 다양성 × 신뢰성**. 이 둘이 무료 뉴스앱·단일소스 경쟁사와의 차별점이다.

---

## 2. event queue가 왜 재방문을 만드는가

- event queue는 "실시간으로 갱신되는 사건 흐름"이다. 사용자는 **새로고침할 이유**가 생긴다(재방문).
- 큐가 비면(소스 3개) 재방문 동기가 약하다. 큐가 풍부하면(44 소스) "늘 새로운 게 있다" → 체류·재방문 상승.
- **따라서 브리지(시스템 연결)는 단순 기술 작업이 아니라 핵심 retention 레버다.**

---

## 3. source evidence UI가 신뢰를 만드는 방법

- 각 사건 카드에 **출처 배지**(공식 공시 / 뉴스 / 커뮤니티 / 시세)를 단다.
- "공식 확인됨"(opendart/sec) vs "미확인 — 커뮤니티 발"(09 balance 게이트)을 **투명하게 라벨링**.
- evidence_links(05 §3.10)로 1차 출처 원문 링크 제공 → "직접 확인 가능"이 신뢰의 핵심.
- frontend-integration: 기존 event_cards의 `entities/sectors/source_url` 필드 + evidence를 카드에 노출.

---

## 4. 커뮤니티 반응 — 언제 가치, 언제 노이즈

| 상황 | 판단 |
|---|---|
| 사건 발생 **후** 반응 수집 | **가치** (여론·임팩트 신호) |
| 사건 **발견원**으로 커뮤니티 단독 사용 | **노이즈 위험** (허위·명예훼손) → official 확인 전 "unconfirmed" |
| 정기 폴링으로 커뮤니티 긁기 | **노이즈+비용** → on-demand만(02) |

원칙: 커뮤니티는 **반응 레이어**이지 **발견 레이어**가 아니다(09 community_vs_official_balance).

---

## 5. 공식 발표 vs 뉴스/커뮤니티 차이를 보여주는 법

- 같은 사건을 3층으로 제시: **① 공식(공시/규제 원문) → ② 보도(뉴스) → ③ 반응(커뮤니티)**.
- 사용자는 "공식은 뭐라 했고, 언론은 어떻게 보도했고, 사람들은 어떻게 반응했나"를 한눈에 → **단일 소스 앱이 못 주는 입체적 인텔리전스**.
- 이 3층 구조가 02(목적 라우팅)·09(balance 게이트)의 상업적 결실이다.

---

## 6. MVP에 반드시 필요한 것 vs 과한 것

| 반드시 필요(MVP) | 과함(후순위/제거) |
|---|---|
| 시스템 A↔B 브리지(44소스 연결) | 운영 dashboard(D-11) |
| event queue + 기본 품질 게이트 | KG-RAG / Graph RAG |
| 출처 라벨 UI(신뢰) | LangGraph 수집 그래프(Phase F, deterministic로 충분) |
| deterministic cycle(Phase A) | Deep Agents |
| rate-limit/격리/quota(안정성) | hybrid search 고도화(STEP 012, 별도) |
| 핵심 소스 카테고리(뉴스·공식·시세·트렌드) | 전체 domain 버티컬 동시 활성 |

**출시를 늦추는 과잉**: LangGraph/Celery를 1차 필수로 넣는 것, 모든 domain 소스 동시 활성, dashboard 선구축. 전부 후순위.

---

## 7. B2B / B2C 가능성

| 세그먼트 | 산출물 | 근거 |
|---|---|---|
| **B2C** | 실시간 사건 피드 앱(웹) | 다양한 소스 + 신뢰 라벨 |
| **B2B (API)** | "사건 피드 API"(event queue + evidence) | 큐가 안정적이면 외부 판매 |
| **B2B (버티컬)** | 산업별 인텔리전스(콘텐츠/금융인접/공공) | domain 소스(kofic/tmdb/opendart) |
| **B2B (리포트)** | 정기 사건 요약 리포트 | 다운스트림 요약 + evidence |

**주의**: 금융 인접 B2B라도 **투자 조언은 출력하지 않는다**(정보만). 이게 규제 리스크를 낮춰 오히려 판매 가능성을 높인다.

---

## 8. 비용 구조

| 비용 항목 | 크기 | 통제 수단 |
|---|---|---|
| 수집(대부분 무료 API) | 낮음 | rate-limit/quota guard(08) |
| 유료 검색(serper/tavily/nyt) | 중간 | on-demand + daily_quota(02/08) |
| LLM 추론(다운스트림 요약) | **가장 큼** | mock 기본 + 필요 시만 openai + 품질 게이트로 입력 절감(09) |
| 인프라(Redis/Postgres/Milvus) | 중간 | Phase별 점진 도입(설치 0 시작) |
| Playwright 렌더 | 중간(CPU) | 조건부 렌더 + 캐시(04) |

**비용 폭발 지점**: ① 유료 검색 정기 폴링(→ on-demand로 차단), ② 모든 항목 LLM 처리(→ 품질 게이트로 선별), ③ 매번 Playwright 렌더(→ 캐시).

---

## 9. premium feature 후보

- **알림(push)**: 특정 키워드/섹터 사건 즉시 알림 → 프리미엄.
- **evidence 심층**: 1차 출처 원문 + 모순 분석 → 프리미엄.
- **API 접근**: event queue 직접 구독 → B2B.
- **리포트**: 일/주 단위 사건 요약 → B2B.
- **버티컬 필터**: 산업별 큐 → 버티컬 구독.

기본(무료): 사건 피드 + 기본 검색. 프리미엄: 알림 + 심층 + API.

---

## 10. Implementation diff blueprint (상용화는 코드보다 데이터 설계)

```diff
# Proposed — DO NOT APPLY IN THIS TURN (대부분 다운스트림/프론트 영역, 별도 STEP)
# event 카드에 evidence/신뢰 라벨 노출 (프론트, 참고용)
diff --git a/ingestion/orchestration/event_seed_candidate.py b/...
@@
+# EventSeedCandidate에 trust_label 부여 (09 balance 결과)
+#   trust_label: official_confirmed | reported | unconfirmed_community
+#   → 다운스트림 event_card.theme/status로 매핑
```

> 실제 UI/API 변경은 스켈레톤 STEP(프론트)·07/04/05의 데이터 계약을 따른다. 이 문서는 **데이터가 어떤 가치로 환원되는지의 지침**이다.

---

## 11. Agent Committee Review

| agent | 피드백 | status |
|---|---|---|
| commercialization-strategist | 소스 다양성×신뢰가 1순위 가치. 브리지=retention 레버 식별 정확 | CLOSED_BY_DESIGN |
| business-intelligence-analyst | 3층(공식/보도/반응) 구조가 경쟁 차별점. API/버티컬 확장 경로 명확 | CLOSED_BY_DESIGN |
| product-ux-strategist | 출처 라벨 UI가 신뢰 핵심. MVP/과잉 구분 타당 | CLOSED_BY_DESIGN |
| adversarial-reality-critic | "LangGraph/Celery 1차 필수 아님"이 출시 지연 방지. 과잉 제거 양호 | CLOSED_BY_DESIGN |
| legal-safety-compliance-reviewer | 투자 조언 금지 유지가 오히려 B2B 판매성↑ | CLOSED_BY_DESIGN |
| commercialization-strategist(비용) | 비용 폭발 3지점 명시 + 통제 수단 연결 | CLOSED_BY_DESIGN |

---

## 12. Risk Closure

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| 상업적 미스핏 | 기술 과잉, 가치 미연결 | 출시 지연·이탈 | MVP 범위 검토 | MVP/과잉 구분(§6) | 사용자 피드백 | CLOSED_BY_DESIGN |
| 비용 폭발 | 유료 검색/LLM 남용 | 적자 | 비용 대시보드 | on-demand + quota + 게이트 | quota 테스트(08) | CLOSED_BY_TEST_PLAN |
| 투자조언화 | numeric → 매수/매도 | 규제 위험 | 출력 grep | 정보 환원(CLAUDE.md 1) | 톤 검사 | CLOSED_BY_DESIGN |
| 신뢰 훼손 | 미검증 사건 발행 | 평판 | balance 게이트 | unconfirmed 라벨(09) | balance 테스트 | CLOSED_BY_DESIGN |
| retention 약함 | 큐 빈약(소스 3개) | 재방문↓ | 큐 신선도 | 브리지로 44소스 | e2e 도달(Phase H) | DEFERRED_WITH_TRIGGER(Phase H) |

---

## 13. Commercialization Impact (메타)

이 문서 자체가 commercialization impact의 종합이다. 핵심 한 줄: **"이미 만든 44개 소스 수집 자산을 다운스트림에 연결(브리지)하고, 출처 신뢰 라벨을 붙이는 것"이 가장 적은 비용으로 가장 큰 제품 가치를 만든다.** 나머지(LangGraph/Celery/dashboard)는 그 가치를 확인한 뒤 얹는다.

### 13.1 재검토 확정 — 1차 ROI와 고급 에이전트 계층의 분리

> **1차 ROI(MVP)**: 신규 프레임워크 도입이 아니라, **ingestion의 44개 수집 소스를 다운스트림 사건 카드 파이프라인에 `bridge_to_raw_events`로 연결**하는 것. 코드 실측으로 이 명제가 뒷받침됨(수집 엔진·다운스트림 모두 동작, 연결만 없음).

| 계층 | 상업적 위치 | 시점 |
|---|---|---|
| Layer 1 수집 연결(브리지) + 신뢰 라벨 | **MVP 핵심 가치** — 소스 다양성×신뢰 | 지금 |
| Layer 2 LangGraph 사건 처리(mock→real) | 사건 분석 품질 향상 | STEP 014 |
| **Layer 3 고급 에이전트(Deep Agents 등)** | **premium analysis / B2B intelligence / research assistant** | **MVP·매출 검증 이후** |

- **Deep Agents/CrewAI 등 고수준 agent layer는 MVP 이후 부가가치 계층**이다. "사건 심층 확장 조사", "증거 자동 탐색", "맞춤 리서치 어시스턴트" 같은 **프리미엄/B2B 기능**으로 분리해 매출 검증 후 얹는다. MVP 비용에 넣지 않는다.
- **전문 재배포 금지 + evidence link 중심**: 제품 가치는 원문 전재가 아니라 "요약 + 출처 링크 + 근거"에서 나온다(저작권 안전 = B2B 판매 가능). 05 §4 원문 5계층의 내부/외부 분리가 이를 보장.
- **비용 상한(quota guard)**: 외부 API·LLM 일일 상한으로 최악 비용을 못 박아 가격·마진을 설계한다(08 §7).

---

## 14. USER_CONFIRMATION_REQUIRED

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| MVP 1차 타깃 B2C vs B2B? | 우선순위 | B2C 피드 먼저, API는 큐 안정 후 | No |
| 프리미엄 1순위 기능? | 수익화 | 알림(push) | No |
| MVP 소스 카테고리 범위? | 출시 속도 | 뉴스+공식+시세+트렌드(커뮤니티 반응 보조) | No |
| dashboard 1차 포함? | 출시 지연 | 후순위(D-11) | No |

> 다음 문서: `11_IMPLEMENTATION_DIFF_BLUEPRINT.md`.

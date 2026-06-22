# 02 — SEARCH ENGINE vs EVENT INTELLIGENCE (무엇을 만드는가)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 📘 REFERENCE — 최상위 포지셔닝 선언(검색엔진 ≠ event intelligence). 새 방향(ADR#14/#15/#16) 반영.
> │ **구현순위:** #9 (00_ROADMAP_INDEX) · **그룹:** B
> │ **검증 근거:** 코드 산출물 아님(포지셔닝 청사진). 현재 구현 사실은 `_CANONICAL/01·02`가 권위.
> │ **잔여(미구현):** 검색 API 확장(06)·Event Resolution(12/19)·LLM P/G/F(11/19)·Entity/Authority(17)·트래픽×광고(13).
> │ **완료정의(DoD):** N/A(설계 문서) — 가리키는 레이어 구현으로 충족.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> **방향(DIRECTION 우선):** 본 포지셔닝은 ADR#14(LLM 수집경계 P/G/F)·ADR#15(트래픽×광고×커뮤니티, 구독 폐기)·ADR#16(Event 타임라인 객체) 위에 선다(`docs/_DECISIONS/2026-06.md`). 핵심 갱신: ① 단위는 page/document가 아니라 **Event**(카드=snapshot 단면) ② LLM은 수집의 **두뇌(P/G/F)**이지 크롤러가 아님 ③ 수익은 **B2B 인용 신뢰 + 트래픽×광고** 균형이지 구독 아님.

> 결론: 우리는 구글 같은 범용 검색엔진을 만들지 않는다. 고신호 source·검색 API 확장(tiered)·자체 index·RAG·LLM P/G/F·**진화하는 Event 객체**를 결합한 **event intelligence platform**을 만든다.

> 📌 **포지셔닝 문서**: 논제는 유효하며 코드-상태 주장이 없다. 현재 구현 사실은 `docs/_CANONICAL/01·02`가 권위. 검색 API 확장/Event Resolution/P/G/F judge는 다수 **미구현 ROADMAP**(06·11·12·19 ideation, KG-RAG는 09 영구보류).

---

## 1. 본질적 차이

| 축 | 범용 검색엔진 | Event Intelligence Platform (우리) |
|---|---|---|
| 단위 | page/document | **Event**(시계열로 진화하는 사건 주제, 다중 소스 묶음). **카드 = Event의 현재 단면 snapshot**(1회성 산출물 아님, ADR#16) |
| 트리거 | 사용자 쿼리(pull) | 능동 감지(push) + 쿼리. 2번째 보도 → 새 카드 아닌 기존 Event에 update append |
| 전제 | 사용자가 무엇을 물을지 안다 | 묻기 전에 무엇이 일어나는지 알려준다 |
| 핵심가치 | 쿼리-문서 관련도 랭킹 | freshness · dedup · **교차검증 신뢰도** · 시계열 클러스터 · evidence 추적성 |
| 검색의 역할 | 제품 그 자체 | enrichment **보조수단**(확장/검증) |
| 수집 | 전체 웹 크롤·인덱스 | 고신호 seed source + 검색 API 보강 |
| 출력 | 링크 리스트 | evidence 링크가 달린 검증된 event card / alert |

## 2. 직접 웹 전체 크롤링이 비현실적인 이유

세 축에서 무너진다(적대적 비판·검색 엔지니어 합의):

1. **비용** — 전체 웹 크롤·재크롤·저장·인덱스는 인프라/대역폭이 천문학적이고, freshness 유지에 지속 재크롤이 필요하다. 1인/소규모가 감당 불가.
2. **법무** — robots.txt/ToS/저작권/개인정보(GDPR), 검색 API ToS. 직접 크롤링 소스(dcinside/fmkorea/naver/X)는 차단·법무 통지 후보다. 본 레포는 우회 전면 금지가 불변 제약이다.
3. **중복·잡음** — 웹 대부분은 event 정의와 무관한 noise. dedup·canonicalization 부담만 키운다.

→ **seed source + 검색 API + 자체 index 조합이 ROI상 유일하게 합리적이다.**

## 3. crawling ≠ discovery ≠ indexing ≠ ranking (책임 분리)

- **discovery**: 새 고신호 source 발굴 + robots/ToS 사전 판정(`source_policy_probe`). 후보 점수화. **중기: Entity Registry·Authority Source Graph 발견엔진**(어떤 엔티티가 어떤 권위 소스에서 보도되는지, →17 NET-NEW).
- **ingestion(crawling)**: 검증된 source의 결정적 수집(deterministic). **LLM은 P/G/F 경계 안에서만 관여** — LAYER P(triage·query expansion·source routing 계획) → LAYER G(allowlist+budget 게이트, 결정론) → LAYER F(페치, LLM 미관여). 우회 금지(ADR#14).
- **search expansion**: event candidate 1건에서 관련 웹문서를 검색 API로 확장(enrichment, pull). **tiered(무료→유료) + per-event/월 budget guard**.
- **indexing**: PG(SoT, **events/event_updates 포함**) + Milvus(의미) + OpenSearch(키워드).
- **ranking**: Event 단위 freshness/corroboration/diversity/impact/**heat**(시계열 활성도) 결합.

이 분리를 흐리면 "범용 검색엔진화"라는 scope creep에 빠진다. **LLM이 페치 제어흐름을 소유하면** 비결정성이 전 시스템에 전파되므로 P/G/F 경계로 막는다.

## 4. event candidate → 관련 문서 확장 방법

1. **Query formulation**: candidate의 entity(인물/조직/장소)+action+시간창을 추출해 구조화 쿼리 생성(언어/지역 변형 포함). LAYER P(LLM)가 expansion 쿼리를 계획.
2. **Citation/source expansion**: 1차 hit의 원출처(primary source)로 수렴, 2차 보도 중복은 Event에 append(corroboration).
3. **Source diversity**: 지역/성향/언어 분산 강제, corroboration count를 신뢰 신호로 사용.
4. **domains 2층 분류**: 사건이 어느 분야에 속하는지는 닫힌 8섹터가 아니라 **열린 2층(통제어휘 ~20 + free-form tags)**으로 라벨링(ADR#16). 한 Event가 다분야로 번지면(예: 호르무즈 봉쇄 → 에너지+지정학+물류) domains를 누적 add.

> 핵심: 검색은 candidate가 있을 때만 호출(pull) + budget guard 안에서. 무차별 검색은 비용 폭증.

## 5. "이길 수 있는 구조" (적대적 비판 반영)

자본화된 경쟁자(Dataminr/AlphaSense)와 범용 실시간 인텔리전스로 정면승부하면 진다(커버리지·신뢰성·법무·영업 열세). 이길 수 있는 곳:

- **좁은 vertical 정밀도**: 예) 한국 공시/규제 이벤트(opendart/krx/federal_register만으로 차별화), AI/tech 제품 incident.
- **교차검증 + evidence 추적성**: 점수만이 아니라 클릭 한 번으로 원본까지 내려가는 추적성 = **B2B 인용 가능성**. evidence graph 직접 판매는 불변원칙상 닫힌 길(전문·구독·투자조언 저촉) → 검증 위젯/SEO 허브로 **트래픽 증폭**(광고 면적)에 쓴다(ADR#15).
- **사건 중심 능동 감지**: 검색이 아니라 evidence-linked **Event stream**(시계열로 진화).
- **evidence 균형(B2B 신뢰 ↔ 광고 트래픽)**: 추적 가능한 증거는 B2B 인용 신뢰를 만들고, 그 신뢰가 만든 체류·재방문이 광고 트래픽이 된다. 둘은 상충이 아니라 동일 자산의 두 활용.

## 6. 우리가 만드는 것 / 만들지 않는 것

**만든다**: 고신호 source 수집기(LLM P/G/F) + 정책안전 게이트 + **Event 정규화/append/timeline/heat** + 교차검증 신뢰 라벨 + evidence pane + 4뷰 product surface + **커뮤니티 성장엔진**(유저 댓글 + Agent Debate Layer).

**만들지 않는다**: 전체 웹 크롤러, 범용 SERP, **per-seat 구독 가격경쟁 제품**(구독 폐기, ADR#15), "LLM이 알아서 다 하는" 만능 에이전트(P/G/F로 경계), 우회 기반 수집, 투자조언.

> **community = 성장 엔진(ADR#15)**: 고품질 사건추적(시계열·다분야) + **Agent Debate**(에이전트 해설/논쟁, 별개 신규 그래프) + 유저 상호작용 → 체류↑·재방문↑ → 페이지뷰↑ → 광고 노출↑. Agent 발화는 투자조언 금지·근거없는 단정 금지·prompt injection 격리(R-AgentDebateSafety).

## 7. 한 줄 선언

> source discovery → LLM P/G/F 수집 → tiered search expansion → evidence ranking → **Event resolution/append/timeline** → Agent analysis/debate → **4뷰 + 트래픽×광고** product surface.
> 수백 개 웹을 무식하게 연결하는 방향이 아니라, **고신호·검증·증거중심**으로 확장한다.

> **5대 자산 ↔ 매핑:** ① Event Resolution(진화하는 사건 객체, ADR#16) ② LLM Expansion Router(P/G/F, ADR#14) ③ Entity/Authority Discovery(중기, →17) ④ Evidence Graph(B2B 신뢰·트래픽 증폭) ⑤ Agent Debate(커뮤니티 성장엔진, →트래픽×광고, ADR#15). 상세 = `00_ROADMAP_INDEX §4`(S1~S11 임계경로) · `19`(NET-NEW 스펙).

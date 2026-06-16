# 02 — SEARCH ENGINE vs EVENT INTELLIGENCE (무엇을 만드는가)

> 결론: 우리는 구글 같은 범용 검색엔진을 만들지 않는다. 고신호 source·검색 API 확장·자체 index·RAG/KG-RAG·LLM judge·event graph를 결합한 **event intelligence platform**을 만든다.

---

## 1. 본질적 차이

| 축 | 범용 검색엔진 | Event Intelligence Platform (우리) |
|---|---|---|
| 단위 | page/document | **event**(사건 후보, 다중 소스 묶음) |
| 트리거 | 사용자 쿼리(pull) | 능동 감지(push) + 쿼리 |
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

- **discovery**: 새 고신호 source 발굴 + robots/ToS 사전 판정(`source_policy_probe`). 후보 점수화.
- **ingestion(crawling)**: 검증된 source의 결정적 수집(deterministic). 우회 금지.
- **search expansion**: event candidate 1건에서 관련 웹문서를 검색 API로 확장(enrichment, pull).
- **indexing**: PG(SoT) + Milvus(의미) + OpenSearch(키워드).
- **ranking**: cluster 단위 freshness/corroboration/diversity/impact 결합.

이 분리를 흐리면 "범용 검색엔진화"라는 scope creep에 빠진다.

## 4. event candidate → 관련 문서 확장 방법

1. **Query formulation**: candidate의 entity(인물/조직/장소)+action+시간창을 추출해 구조화 쿼리 생성(언어/지역 변형 포함).
2. **Citation/source expansion**: 1차 hit의 원출처(primary source)로 수렴, 2차 보도 중복은 접는다.
3. **Source diversity**: 지역/성향/언어 분산 강제, corroboration count를 신뢰 신호로 사용.

> 핵심: 검색은 candidate가 있을 때만 호출(pull). 무차별 검색은 비용 폭증.

## 5. "이길 수 있는 구조" (적대적 비판 반영)

자본화된 경쟁자(Dataminr/AlphaSense)와 범용 실시간 인텔리전스로 정면승부하면 진다(커버리지·신뢰성·법무·영업 열세). 이길 수 있는 곳:

- **좁은 vertical 정밀도**: 예) 한국 공시/규제 이벤트(opendart/krx/federal_register만으로 차별화), AI/tech 제품 incident.
- **교차검증 + evidence 추적성**: 점수만이 아니라 클릭 한 번으로 원본까지 내려가는 추적성 = B2B 인용 가능성.
- **사건 중심 능동 감지**: 검색이 아니라 evidence-linked event stream.

## 6. 우리가 만드는 것 / 만들지 않는 것

**만든다**: 고신호 source 수집기 + 정책안전 게이트 + event 정규화/dedup/clustering + 교차검증 신뢰 라벨 + evidence pane + vertical alert/report/API.

**만들지 않는다**: 전체 웹 크롤러, 범용 SERP, per-seat 가격경쟁 제품, "LLM이 알아서 다 하는" 만능 에이전트, 우회 기반 수집.

## 7. 한 줄 선언

> source discovery → search expansion → evidence ranking → event clustering → LLM analysis → commercial product surface.
> 수백 개 웹을 무식하게 연결하는 방향이 아니라, **고신호·검증·증거중심**으로 확장한다.

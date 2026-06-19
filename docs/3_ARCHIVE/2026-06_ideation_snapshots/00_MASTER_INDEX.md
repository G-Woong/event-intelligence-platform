# 00 — MASTER INDEX: 웹 인텔리전스 플랫폼 확장 전략 문서 세트

> 작성: 2026-06-16 · 성격: **전략/아이디어 문서**(코드 구현 아님) · 기준 커밋: `5491c02`
> 권위: 현재 구현 사실은 `docs/_CANONICAL/`가 단일 출처다. 본 세트는 그 위에 "어디로 확장할지"를 더한다.

> ⚠️ **STALE CODE-STATE (2026-06-18, Pre-Harness Cleanup Sprint)**: 본 세트의 "한 문장 결론"이 P0로
> 지목한 *ingestion↔다운스트림 배선*은 이후 커밋으로 **이미 구현·라이브 입증**됐다(357c717 배선,
> fda7538 baseline 노드, 0f44cf2 ap_news 라이브 E2E, b1bcbf8 수치 동기화). 즉 "지금 최우선은 배선"
> 문장은 더 이상 현재 상태가 아니다(기본 sink가 mirror라는 점만 잔존). 코드-상태 주장은
> `docs/_CANONICAL/01·09`로 교차확인하라. 전략/확장 방향 내용은 유효하다.

---

## 0. 한 문장 결론

이 레포는 **범용 검색엔진이 아니라 event intelligence platform**이다. 고신호 source 수집 → 검색 API 확장 → evidence 랭킹 → event 클러스터링 → LLM judge → 상용 product surface로 확장한다. **지금 최우선(P0)은 신기술 도입이 아니라 이미 만든 두 자산(ingestion 57소스 엔진 ↔ 다운스트림 raw_events/LangGraph 앱)을 연결하는 배선이다.**

## 1. 이 문서를 쓰는 이유

- docs는 `_CANONICAL/` 11개로 정리됐다(현재 구현 상태). 그러나 "상용 event intelligence로 가려면 무엇을 어떤 순서로 붙일지"의 전략은 흩어져 있었다.
- 이 세트는 **실제 코드 감사 + 광범위 웹 리서치(2026-06, 20개 검색·출처 포함) + 11개 팀 에이전트 다관점 평가 + 적대적 비판**을 근거로, layer별 책임·구현방향·비용·법무·검증기준을 한 곳에 모은다.
- 추상적 아이디어 나열이 아니라 **구현 우선순위를 결정하는 의사결정 문서**다.

## 2. 읽는 순서

| 순서 | 문서 | 목적 | 독자 |
|---|---|---|---|
| 0 | **00_MASTER_INDEX** | 이 문서. 진입점·결론·P0 | 전원 |
| 1 | **01_CURRENT_REPO_REALITY_AUDIT** | 코드 기준 실상태 감사(구현/미구현) | 전원 |
| 2 | **02_SEARCH_ENGINE_VS_EVENT_INTELLIGENCE_CONCEPT** | 무엇을 만드는가/아닌가 | 의사결정자 |
| 3 | **03_REAL_WORLD_CASES_AND_MARKET_PATTERNS** | 실제 사례 36개 + 시장 패턴 | 전략/제품 |
| 4 | **04_TARGET_ARCHITECTURE_LAYERS** | L0~L14 목표 아키텍처 | 아키텍트 |
| 5~12 | **05~12 layer 문서** | discovery/search/redis/RAG/KG-RAG/agent/supervisor/clustering | 엔지니어 |
| 13 | **13_COMMERCIALIZATION_AND_PRODUCT_STRATEGY** | 수익화·vertical·가격 | 경영/제품 |
| 14 | **14_SECURITY_LEGAL_SAFETY_AND_NO_BYPASS** | 보안·법무·우회금지 | 보안/법무 |
| 15 | **15_IMPLEMENTATION_ROADMAP** | Phase 0~10 로드맵 | 전원 |
| 16 | **16_LAYER_BY_LAYER_100_CHECKLISTS** | layer별 100항목(총 1500) | 엔지니어 |
| 17 | **17_TEAM_AGENT_REVIEW** | 11개 관점 리뷰·합의·충돌 | 전원 |
| 18 | **18_FINAL_EXECUTIVE_SUMMARY** | 경영자 요약 + 엔지니어 next tasks | 전원 |

비개발자/의사결정자는 **00 → 02 → 13 → 18**만 읽어도 핵심을 파악할 수 있다.
엔지니어는 **01 → 04 → 15 → 16**을 따라간다.

## 3. P0 (문서 최상단 고정)

```text
P0: ingestion 57소스 엔진을 실 raw_events Postgres에 연결한다.
    현재 bridge_to_raw_events 기본 db_writer=None → JSON mirror만 적재된다.
    이 mirror 중심 수집 결과를 downstream LangGraph/event_cards 파이프라인으로 흘린다.
    근거: ingestion/orchestration/bridge_to_raw_events.py (db_writer 미주입),
          ingestion/pipeline/event_queue.py (_redis_* 4개 NotImplementedError "Round 2").
```

우선순위 요약(상세 15):

| Pri | 작업 | 근거 |
|---|---|---|
| **P0** | ingestion→raw_events 실배선 | bridge db_writer=None, mirror만 |
| P1 | Redis Stream / DLQ / retry / monitoring 실배선 | event_queue Redis 스텁, Celery 미구현 |
| P1 | 6개 mock LangGraph 노드 중 결정론 가능분 실구현 | entity_linking/evidence_check 등 MOCK |
| P1 | dedup + cross-source event clustering | deduplicate.py PARTIAL, clustering 0건 |
| P2 | Search API expansion layer(provider-agnostic) | 검색확장 layer 부재 |
| P3 | hybrid search + reranker + nori | OpenSearch keyword only |
| P4 | LLM SourceSupervisor 실 provider 연결 | 인터페이스만, 규칙기반 동작 |
| P5 | event ranking / timeline | 미구현 |
| P6 | KG-RAG / GraphRAG (고가치 multi-hop 한정) | 미구현, 비용 3-5x |
| P7 | commercial dashboard / alert / report / API | dashboard만 구현 |

## 4. 절대 원칙(이 세트 전체 불변)

- 직접 웹 전체 크롤링 금지(비현실적). core source + 검색 API + 자체 index + LLM judge + event graph 조합.
- robots/ToS/CAPTCHA/login/paywall/rate-limit **우회 금지**. 전문(full body) 재배포 금지 → evidence URL+summary+metadata 중심.
- 투자조언 금지(정보제공만). `.env` 키 값 출력/로그/커밋 금지.
- 구현된 것과 아이디어를 섞지 않는다. 미검증 주장은 `hypothesis`로 표기.
- source coverage보다 **event quality**가 우선. 소스 100개 추가는 P0 배선 전엔 무의미.

## 5. 근거(웹 리서치 출처는 03·04·각 layer 문서에 인라인)

본 세트의 사실 주장은 (a) 실제 코드(`ingestion/`, `backend/`, `agents/`, `workers/`, `frontend/`) 직접 열람, (b) `docs/_CANONICAL/`, (c) 2026-06 웹 리서치(LangGraph/deepagents 공식 문서, OWASP LLM Top10, 벡터DB 벤치, 검색·뉴스 API 가격, 상용 제품 자료)에 근거한다. 코드와 어긋나는 외부 주장은 코드 기준으로 정정했다.

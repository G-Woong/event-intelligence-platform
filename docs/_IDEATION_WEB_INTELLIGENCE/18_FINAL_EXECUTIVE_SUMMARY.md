# 18 — FINAL EXECUTIVE SUMMARY

> 경영자용 요약 + 엔지니어용 next tasks. 기준 커밋 `5491c02`, 2026-06-16.

---

## A. 경영자 요약 (Executive Summary)

**우리가 만드는 것.** 구글 같은 범용 검색엔진이 아니라, 고신호 source 수집 + 검색 API 확장 + 자체 index + RAG + LLM judge + event graph를 결합한 **event intelligence platform**이다. 사용자가 묻기 전에 사건을 능동 감지하고, 다중 소스로 교차검증하며, 증거(evidence URL)를 붙여 신뢰할 수 있는 실시간 사건 스트림을 제공한다.

**지금 어디에 있나.** 두 개의 자산이 있다 — (A) 57개 소스를 정책 안전하게 수집하는 deterministic 엔진(구현 완료), (B) 사건을 카드로 만들어 검색·표시하는 다운스트림 앱(부분 구현). 문제는 **둘이 연결되어 있지 않다**는 것이다. A의 수집 결과는 JSON 파일에만 쌓이고 실제 DB·화면까지 도달하지 못한다. 즉 "엔진은 완성됐고 고급 기능만 얹으면 된다"는 인식은 사실과 다르다.

**가장 중요한 한 가지(P0).** ingestion 57소스 엔진을 실 raw_events Postgres에 연결하는 배선. 이것이 풀리기 전에는 소스를 100개 더 붙여도, GraphRAG를 얹어도, 영업을 시작해도 공허하다(데모 불가). 첫 목표는 화려한 기능이 아니라 **실데이터 사건 카드 1건을 end-to-end로 만드는 것**이다.

**어떻게 이기나.** 자본화된 경쟁자(Dataminr/AlphaSense, 수천 고객·수백M 자본)와 범용 실시간 인텔리전스로 정면승부하면 진다. 이길 수 있는 곳은 (1) **좁은 vertical 정밀도**(AI/tech 제품 incident 또는 한국 규제/공시), (2) **교차검증 + evidence 추적성**(클릭 한 번으로 원본까지 = B2B 인용 가능), (3) **사건 중심 능동 감지**다.

**수익화.** 광고가 아니라 **B2B alert/report/API**다. 가격은 시장 추세대로 hybrid(base + usage), 3-4 티어. 전문 재배포를 하지 않는 evidence 중심 모델이 오히려 저작권 안전성으로 엔터프라이즈 조달을 통과시킨다. 6개월 검증 목표: 파일럿 LOI 3 + 유료 30 + MRR 검증.

**리스크.** ① 통합 갭(P0)이 모든 가치의 병목, ② 프롬프트 인젝션(LLM 1위 위험, 외부 본문 유입), ③ 검색 API 무료티어 축소(단일 provider 의존 금지), ④ 법무(우회 금지·전문저장 금지·dcinside ToS 미확정), ⑤ 고급 layer(GraphRAG 등) 조기 도입의 비용/순서 역전. 이 문서 세트는 각 리스크에 봉인 조건과 우선순위를 부여했다.

**투자/조언 아님.** 본 플랫폼과 문서는 사건/이벤트 정보 전달이 목적이며 투자 권유·금융 조언이 아니다.

## B. 엔지니어 Next Tasks (즉시)

```text
1) P0 배선: bridge_to_raw_events에 db_writer 주입(workers POST 경유)
   → ingestion seed 1건이 raw_events PG에 실제 INSERT되는 것을 확인 (mirror→DB)
   검증: A→B e2e (enqueue → consume → raw_events row)

2) Redis 배선: event_queue.py의 _redis_* 4개(NotImplementedError) 구현
   → B의 redis.py 헬퍼(xadd/ensure_group/xreadgroup/xack)에 위임
   검증: REDIS_URL 설정 시 stream 왕복, PEL→DLQ 회수

3) mock 해제(결정론 우선): entity_linking=NER, evidence_check=URL/출처 검증
   + dedup→cross-source clustering(MinHash LSH + 임베딩 HDBSCAN) 착수
   검증: end-to-end 실데이터 카드 1건, cluster purity≥0.8
```

위 3개를 source-ingestion-engineer / orchestrator-architect / operations-sre-agent에 위임 가능. 이후 P2(검색확장)~P10(enterprise 보안)은 15 로드맵을 따른다.

## C. 한 줄

> 신기술을 얹기 전에, 이미 만든 두 자산을 연결하라. 실데이터 카드 1건이 1000개 소스보다 가치 있다.

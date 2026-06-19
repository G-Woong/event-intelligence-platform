# 03 — REAL-WORLD CASES & MARKET PATTERNS

> 2026-06 웹 리서치 기반 실제 사례 **36개**(6 카테고리 × ≥5). 마케팅 문구가 아니라 실제 운영 제한/가격/쿼터/법무를 분리해 기록. 미확정은 `hypothesis`.

---

## 형식
각 사례: What it does / Relevant capability / What we can learn / What we should NOT copy / Commercial model / Technical limitation / Legal-safety / How it maps to this repo / Implementation idea.

---

## 카테고리 1 — 범용 검색엔진 / 검색 API (6)

**CASE-01 Brave Search API** — 독립 인덱스 기반 웹 검색 API, AI용 "LLM Context" 엔드포인트 제공. *Learn*: AI 최적화 검색 컨텍스트 엔드포인트 패턴. *Not copy*: 무료 의존. *Commercial*: 무료티어 폐지(2026-02), ~$5/1k calls, $5/월 크레딧, Enterprise는 sales. *Limit/Legal*: 단가·정책 변동성. *Map*: L2 유료 fallback provider. *Idea*: provider-agnostic 추상화 뒤 유료 tier로만.

**CASE-02 Microsoft Bing Web Search API** — (구) 웹 검색 API. *Learn*: **단일 provider 의존 = 단일 장애점.** *Not copy*: 의존 금지. *Commercial*: **2025-08-11 폐지** → Grounding with Bing(Azure AI Foundry, 40~483% 비용↑, 플랫폼 락인). *Map*: L2 RISK 사례. *Idea*: 다중 fallback + graceful degradation 설계 근거.

**CASE-03 Google Programmable Search (CSE)** — 사용자 정의 검색. *Commercial*: 무료 쿼터 소량 + 유료. *Limit*: CX/key 설정 필요(레포 google_programmable_search 비활성). *Map*: L2 무료 보조. *Idea*: 일 쿼터 카운터 + 초과 차단.

**CASE-04 SerpAPI** — SERP 스크래핑 대행 API. *Learn*: 직접 스크랩 회피용 대행. *Not copy*: 단가 높아 routine 호출 부적합. *Commercial*: 종량/구독. *Map*: L2 최종 검증/감사 전용. *Idea*: per-event 상한 내에서만.

**CASE-05 Google(범용 검색)** — 웹 랭킹의 기준점. *Learn*: 쿼리-문서 관련도. *Not copy*: 전체 웹 크롤·인덱스(비현실적). *Map*: 02 "만들지 않는 것"의 기준. *Idea*: 우리는 event 단위, 검색은 보조.

**CASE-06 Perplexity (answer engine)** — 검색+LLM 합성 답변. *Learn*: 출처 인용 UX. *Not copy*: 범용 질의응답. *Commercial*: 구독(Pro). *Map*: 우리는 질의가 아닌 능동 event stream으로 차별. *Idea*: evidence 인용 UX 차용.

## 카테고리 2 — 뉴스 / 미디어 모니터링 (6)

**CASE-07 NewsData.io** — 97k+ 소스/206국/89언어 뉴스 API. *Learn*: **무료티어 상업이용 가능**(드묾). *Commercial*: 무료 200 credits/day, Basic $199.99/mo(20k credits). *Limit*: 무료 500/day급. *Map*: L2 1차 무료 뉴스 보강. *Idea*: 기본 provider 채택, 라이선스 조항 보존.

**CASE-08 NewsAPI.org** — 헤드라인 API. *Commercial*: 무료=localhost/dev only, 유료 $449/mo~. *Legal*: **상업 배포 시 무료 불가**(L3/L11 CONDITIONAL). *Map*: 프로토타입 외 의존 금지. *Idea*: 운영 코드에서 무료 가정 제거.

**CASE-09 Mediastack** — 저용량 뉴스 API. *Commercial*: $24.99 entry. *Limit*: 단순/저용량. *Map*: 저비용 유료 옵션 평가만.

**CASE-10 GNews** — 경량 뉴스 API. *Commercial*: 무료 100/day, 유료 $84/mo~. *Map*: L2 소량 무료 보조.

**CASE-11 Perigon** — AI 뉴스 인텔리전스 API, **1M articles/day** 분석. *Learn*: 대용량+엔티티 enrichment. *Commercial*: 유료. *Map*: 고용량 필요 시 후보(미채택 기본). *Idea*: 비용 대비 평가 후 결정.

**CASE-12 The Guardian Open Platform** — 무료 5000/day, 고품질 영문. *Legal*: **재배포 금지**(요약+URL만). *Map*: L2 영문 보강 + L11 CONDITIONAL. *Idea*: snippet+링크만 저장.

## 카테고리 3 — 금융/시장/공시 이벤트 인텔리전스 (6)

**CASE-13 AlphaSense** — 시장 인텔리전스 AI 검색엔진, 6000+ 기업/S&P100 85%. *Learn*: 능동 감지 아닌 "검색" 포지션 + Expert Calls. *Commercial*: Standard/Premium/Enterprise custom, API/전담 매니저. *Map*: 13 경쟁 분석. *Idea*: 우리는 alert 능동성으로 차별.

**CASE-14 Bloomberg / Refinitiv-type terminal** — 금융 단말. *Learn*: 고신뢰·고가. *Not copy*: 자본·라이선스 규모. *Map*: 금융 vertical 상한선 인지(hypothesis: 직접경쟁 불가).

**CASE-15 SEC EDGAR (efts.sec.gov)** — 미 공시 전문 검색. *Learn*: **무료·무키, 10 req/s, User-Agent(이름+이메일) 필수**, 초과시 IP 10분 차단. *Map*: L1 고신호 공식 소스(레포 sec_edgar.py 보유). *Idea*: UA 준수 운영, 8-K 등 filing seed.

**CASE-16 OpenDART (한국 공시)** — 금융감독원 공시 API. *Learn*: 한국 공시 차별화. *Commercial*: 무료 키. *Map*: L1 한국 vertical 코어(레포 opendart.py 보유). *Idea*: 공시 event seed.

**CASE-17 GDELT 2.0 (DOC/Context API)** — 글로벌 이벤트 무료 DB. *Learn*: 광역 event 1차 그물. *Commercial*: 무료. *Limit*: ES 보호 rate-limit, Web NGrams 3.0 대체. *Legal*: 우회 금지(레포 gdelt=scheduled 429). *Map*: L2 광역 탐지. *Idea*: 백오프 client + 최소 2 provider corroboration.

**CASE-18 Signal AI / Factiva / LexisNexis** — 미디어·법률 인텔리전스(엔터프라이즈). *Learn*: 라이선스 콘텐츠 + 분석. *Not copy*: 콘텐츠 라이선스 비용. *Commercial*: enterprise custom. *Map*: 전문 저장 금지 정책의 반례(그들은 라이선스 보유). *Idea*: 우리는 evidence 링크 중심.

## 카테고리 4 — OSINT / 위험 탐지 (5)

**CASE-19 Dataminr** — 실시간 incident/threat 탐지, X firehose 파트너십, 550+ 보안팀. *Learn*: 멀티모달 실시간 alert + Live Briefs. *Not copy*: X firehose 의존(레포 X=MVP_EXCLUDED, 우회 불가). *Commercial*: per-seat + add-on. *Map*: 13 경쟁, alert 제품 벤치. *Idea*: 좁은 vertical + evidence로 차별.

**CASE-20 Recorded Future** — 사이버 위협 인텔리전스, ML+NLP, Mastercard 인수(2024). *Learn*: OSINT 수집+actionable TI. *Map*: 범용 incident로 차별(그들은 사이버 특화). *Idea*: vertical 폭 강조.

**CASE-21 Liveuamap** — 지정학/분쟁 실시간 지도. *Learn*: 시각화 단일 pane. *Not copy*: 지도 중심. *Map*: 우리는 검증+요약 라벨 우위. *Idea*: 타임라인/지도는 후순위 viz.

**CASE-22 Liferaft / SOCRadar / ShadowDragon** — OSINT 플랫폼/도구. *Learn*: 출처 다양성 sweep. *Legal*: 수집 적법성 경계. *Map*: discovery 다중 모달 차용. *Idea*: by-source 다각 탐색.

**CASE-23 OSINT-MONITOR(오픈소스)** — 실시간 글로벌 이벤트 모니터·자동 브리핑. *Learn*: 자동 briefing 생성. *Map*: report 상품 아이디어. *Idea*: vertical 일/주 요약 자동화.

## 카테고리 5 — RAG / GraphRAG / 엔터프라이즈 검색 (7)

**CASE-24 Milvus 2.5** — 벡터 DB, hybrid search ES 대비 ~30x, 50M+ 강함. *Map*: 레포 현행 벡터엔진(1536 IVF_FLAT). *Idea*: 대규모 전망이면 유지, 2.5 hybrid 평가.

**CASE-25 pgvector 0.9** — Postgres 확장, HNSW 50M까지 경쟁력. *Learn*: **별도 인프라 0**(PG가 SoT+벡터). *Map*: L5 인프라 단순화 후보. *Idea*: PoC 벤치 후 ADR.

**CASE-26 Qdrant** — ACORN 필터 HNSW. *Learn*: 필터+벡터 동시 강함. *Map*: L5 옵션. **CASE-27 Weaviate** — 내장 임베딩 모듈. **CASE-28 LanceDB** — 임베디드/엣지. *Map*: 엣지·로컬 옵션.

**CASE-29 Microsoft GraphRAG** — community summarization GraphRAG. *Learn*: 전체 코퍼스 요약 질의 강함. *Not copy*: 실시간 스트림과 인덱싱 주기 충돌, **vector 대비 3-5x 비용(구축 10-100x)**. *Map*: L7 고가치 multi-hop 한정. *Idea*: <1000 엔티티면 미도입.

**CASE-30 LlamaIndex PropertyGraphIndex** — 라벨 노드+속성 그래프, kg_extractors. *Learn*: 저비용 그래프 프로토타입. *Map*: L7 PoC 진입점. **CASE-31 Neo4j / Memgraph** — 그래프 DB(성숙 vs 인메모리/스트리밍). *Map*: L7 규모 확대 시 승격. *Idea*: 수요 실측 후.

## 카테고리 6 — Agent orchestration / AI research·coding agent (6)

**CASE-32 LangGraph 1.0** — durable execution/checkpointing/HITL, 기본 에이전트 런타임(2025-10 GA). *Learn*: stateful·감사·규제 최적, LangSmith 관측. *Map*: 레포 0.2.76 유지(L10). *Idea*: redis checkpointer 전환 시 1.0 동시 평가.

**CASE-33 LangChain deepagents** — create_deep_agent, write_todos 플래닝, 격리 subagent, context offloading → 컴파일된 LangGraph 반환. *Learn*: 장기 task 플래닝/위임. *Not copy*: 현 단계 불필요(규칙기반 충분). *Map*: L10 미도입 결정 문서화.

**CASE-34 OpenAI Agents SDK** — Swarm 계승, 프로덕션, sandbox 실행. *Learn*: 1-2툴 경량. *Map*: 벤더 SDK 비교. **CASE-35 CrewAI** — 역할기반 팀, 비즈니스 워크플로 쉬움. **CASE-36 AutoGen / AG2** — 멀티에이전트 대화, 프로덕션 검증. *Map*: L10 비교표; 우리는 LangGraph 일관성 유지(관측·감사).

> 본 ideation 문서 자체가 **CASE 패턴의 실증**이다: 12개 팀 에이전트가 격리 컨텍스트로 병렬 분해(deepagents subagent 패턴) 후 단일 통합점(이 세트)이 종합 — LangGraph류 다관점 오케스트레이션의 축소판.

---

## 시장 패턴 종합

| 패턴 | 근거 사례 | 시사점 |
|---|---|---|
| 검색 API 무료티어 축소 | Brave 폐지, Bing 폐지 | 단일 provider 의존 = 위험. 다중 fallback 필수 |
| 뉴스 API 상업 라이선스 상이 | NewsData.io(가능) vs NewsAPI.org(localhost) vs Guardian(재배포금지) | ToS가 곧 제품범위 |
| GraphRAG 고비용 | MS GraphRAG 3-5x | 고가치 multi-hop 한정, 기본은 vector RAG |
| 가격 모델 전환 | per-seat 15%로↓, 61% hybrid | usage 신호(API콜/액션) 과금 |
| 인텔리전스 제품 = alert/report/API | Dataminr/AlphaSense/Meltwater | 광고 아닌 B2B 산출물 |
| evidence 추적성 = 신뢰 차별 | AlphaSense/Dataminr 대비 후발 전략 | 출처 클릭 가능성이 B2B 인용 근거 |

# 07 — ENHANCEMENT BACKLOG (고도화 backlog)

> 미구현 필수기능(04)과 구분되는 **고도화**. 동작은 하지만 더 좋게 만드는 항목.

---

### E-1 · Hybrid search (BM25 + 벡터 rerank)
- Current: OpenSearch keyword only / Milvus top-k 별도.
- Desired: BM25 + dense rerank 결합 검색.
- Why: 검색 관련성 향상.
- Sketch: `backend/app/services/search_service.py`에 rerank 단계, `agents/tools/reranker.py` 신규.
- Priority: Mid.

### E-2 · KG-RAG / Graph RAG
- Current: 없음.
- Desired: 엔티티/관계 그래프 기반 검색·추론.
- Sketch: `agents/graph_store/` 신규 모듈.
- Priority: Low(연구성).

### E-3 · LangGraph 고도화 (조건부 엣지 + 서브그래프)
- Current: 단일 선형 11노드.
- Desired: deduplicate→skip 단축, impact_analysis 재시도 루프, collection/validation/writing/search 서브그래프 분해.
- Sketch: `agents/graphs/event_processing_graph.py` 재설계.
- Priority: Mid(6 mock 노드 실연결[04 T-AgtA] 이후).

### E-4 · LLM SourceSupervisor 실 provider 연결
- Current: 수집은 deterministic, LLM은 quality 판단 지점만. SourceSupervisor 인터페이스는 존재(`source_supervisor.py`)하고 strategy_memory에 `llm_agent_hints` 축적.
- Desired: SourceSupervisor가 실 LLM provider로 전략 선택·복구 제안(우회 제안은 거부 유지).
- Why: 신규/막힌 소스 자동 복구.
- Priority: Mid(08 연계).

### E-5 · Deep Agents / Layer 3 (고급 에이전트)
- Current: 미설치(Deep Agents 우선, CrewAI 비교, MS Agent Framework 장기).
- Desired: MVP 이후 심층 추론 레이어.
- Constraint: `INSTALL_CANDIDATE_REQUIRES_USER_APPROVAL`. 지금 설치 안 함.
- Priority: Low(DEFERRED_WITH_TRIGGER: MVP 이후).

### E-6 · cross-source event clustering
- Current: cross_source_dedup(중복 제거)까지.
- Desired: 동일 사건의 다중 소스 클러스터링·corroboration 신뢰도 산출.
- Why: 신뢰가능 실시간 인텔리전스 핵심.
- Priority: Mid.

### E-7 · monitoring/대시보드 시각화
- Current: `monitoring.py` 산출(JSON) + rate-limit 근거.
- Desired: 운영 대시보드(소스 상태/429/cooldown/escalation 가시화).
- Priority: Mid.

### E-8 · 한국어 nori analyzer
- Current: OpenSearch 기본 분석기.
- Desired: nori 형태소 분석으로 한국어 검색 품질 향상.
- Priority: Mid.

### E-9 · 상업화 (B2B API / B2C 웹앱)
- Current: 설계 문서만(`Orchestration_Construction/10`).
- Desired: 3레이어 포지셔닝(Layer1 MVP / Layer2 beta / Layer3 enterprise), 비용구조, 판매경로.
- Constraint: **투자 조언 금지** — 정보 전달 전용(CLAUDE.md 원칙 1).
- Priority: Low(제품 단계 결정).

### E-10 · 프론트엔드 디자인 시스템(shadcn/ui) / i18n
- Current: 기본 Tailwind, 국제화 없음.
- Priority: Low.

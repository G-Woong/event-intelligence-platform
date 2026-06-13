# 07. Web Intelligence Pipeline Environment

> **생성일**: 2026-06-13
> **목적**: 웹 인텔리전스 파이프라인의 단계별 필요 환경, tool, MCP, skill, agent 설계.
> **현재 상태**: ingestion 레이어(수집) 완성. 다음 단계: event queue → clustering → narrative.

---

## 파이프라인 전체 흐름

```
[Source Ingestion]
       │
       ▼
[Candidate Extraction]
       │
       ▼
[Body Extraction]
       │
       ▼
[Related Expansion]     ← google_trends_explore fallback chain 적용
       │
       ▼
[Event Clustering]      ← 예정 (오케스트레이션 이후)
       │
       ▼
[Evidence Graph]        ← 예정
       │
       ▼
[Contradiction/Claim Graph] ← 예정 (LangGraph)
       │
       ▼
[Narrative Generation]  ← 예정 (LLM)
       │
       ▼
[UI/API Handoff]        ← 예정 (FastAPI)
       │
       ▼
[Monitoring]            ← 예정 (LangSmith + Celery Flower)
```

---

## 단계 1: Source Ingestion (수집 레이어)

### 현재 상태: COMPLETED

| 항목 | 상태 |
|------|------|
| API 소스 수집 | 구현 완료 (`ingestion/sources/`) |
| Playwright 소스 수집 | 구현 완료 (`ingestion/probes/playwright_probe.py`) |
| RSS 수집 | 구현 완료 (feed_discovery.py) |
| rate-limit 게이트 | 구현 완료 (rate_limit_policy.yaml + store) |
| body extraction cascade | 구현 완료 (trafilatura → readability → dom_heuristic) |
| artifact 저장 | 구현 완료 (ingestion/core/artifact_store.py) |

### 필요 환경

| 컴포넌트 | 필요 | 현재 상태 |
|----------|------|----------|
| Python 3.11 venv | 필수 | 완료 |
| httpx | 필수 | 완료 |
| Playwright (chromium) | 필수 | 완료 |
| Selenium | fallback | 완료 |
| trafilatura | 필수 | 완료 |
| readability-lxml | 필수 | 완료 |
| .env API 키 세트 | 필수 | 완료 (38개 CORE_READY) |
| rate_limit_policy.yaml | 필수 | 완료 |

### 담당 에이전트

- **source-ingestion-engineer**: 소스 코드 구현/수정
- **data-quality-auditor**: 수집 품질 검증
- **legal-safety-compliance-reviewer**: 약관 검토

### 운영 주의사항

```
gdelt: min_interval 60s, cooldown 900s (빠른 연속 호출 soft-429 실측)
google_trends_explore: CONFIRMED_EXTERNAL_RATE_LIMIT → fallback chain으로 대체
reddit: MVP_DEFERRED (rate limit 변동성)
Phase 1 뉴스 6개 소스 (zdnet_korea, etnews, yna, hankyung, maekyung, aljazeera): UNKNOWN (재프로브 필요)
```

---

## 단계 2: Candidate Extraction (후보 추출)

### 현재 상태: 부분 구현

| 컴포넌트 | 파일 | 상태 |
|----------|------|------|
| EventSeedCandidate schema | `ingestion/schemas/event_candidate.py` | 완료 |
| discovery_collector | `ingestion/pipeline/discovery_collector.py` | scaffold 완료 |
| event_candidate_extractor | `ingestion/pipeline/event_candidate_extractor.py` | scaffold 완료 |
| query_generator | `ingestion/pipeline/query_generator.py` | scaffold 완료 |

### 필요 환경

```
Python ingestion.pipeline 모듈 (scaffold 완료)
EventSeedCandidate 최소 필드: title_or_keyword, source_url, timestamp
numeric_signal 소스는 별도 경로 (NUMERIC_SIGNAL_SOURCES)
```

### 담당 에이전트

- **orchestrator-architect**: pipeline 연결 설계
- **data-quality-auditor**: candidate 품질 검증
- **test-validation-agent**: schema 검증

---

## 단계 3: Body Extraction (본문 추출)

### 현재 상태: COMPLETED

| 컴포넌트 | 파일 | 상태 |
|----------|------|------|
| trafilatura 추출 | `ingestion/tools/trafilatura_extractor.py` | 완료 |
| readability 추출 | `ingestion/tools/readability_extractor.py` | 완료 |
| DOM heuristic | `ingestion/tools/dom_candidate_extractor.py` | 완료 |
| markdown 추출 | `ingestion/tools/markdown_extractor.py` | 완료 |
| site-specific selector | `playwright_probe_sites.yaml` | 완료 |

### 추출 cascade 순서

```
1. site_selector (playwright_probe_sites.yaml의 body_selector)
2. trafilatura (본문 우선 추출)
3. readability-lxml (fallback)
4. dom_heuristic (마지막 fallback)
```

### 주의사항

```
guardian/nyt/newsapi: 본문 전문 재배포 금지 → snippet만 저장
reuters: MVP_EXCLUDED (라이선스)
paywall 페이지: 추출 불가 → 원본 URL + snippet만 저장
```

---

## 단계 4: Related Expansion (연관 확장)

### 현재 상태: fallback chain 완료

| 컴포넌트 | 파일 | 상태 |
|----------|------|------|
| fallback chain | `run_trend_fallback_enrichment_audit.py` | 완료 |
| search enrichment | `ingestion/pipeline/search_enrichment_collector.py` | scaffold 완료 |
| related candidates | `extract_related_candidates` 함수 | 완료 |

### Related Expansion 전략

```
트렌드 소스 (hot seed → related query):
  A. google_trending_now (primary)
  B. google_trends_trending_now_export (RSS fallback)
  C. serper/tavily/naver 검색 enrichment

뉴스 소스 (event candidate → related articles):
  serper, tavily, exa, naver_news_search, gnews, guardian, nyt

커뮤니티 반응:
  hacker_news, reddit (MVP_DEFERRED), naver_blog_search
```

### 일일 budget (enrichment_live_audit 실측)

```
naver_news_search / naver_blog_search: ≤200 queries/day
serper: ≤30 (일회성 크레딧 보존)
tavily / exa: ≤30 (1000/month)
guardian: ≤100 (5000/day)
nyt: ≤50 (500/day)
gnews / newsapi: ≤20 (100/day)
```

---

## 단계 5: Event Clustering (이벤트 클러스터링) — 예정

### 현재 상태: 미구현 (오케스트레이션 이후)

### 필요 환경

```
LangGraph (plans/012 도입 예정)
Milvus 벡터 DB (docker-compose.dev.yml 추가 예정)
embedding 모델 (OpenAI text-embedding 또는 로컬)
Redis (중간 상태 저장)
```

### 설계 방향 (추정)

```
1. EventSeedCandidate → embedding 생성
2. Milvus에 저장 + 코사인 유사도 검색
3. 임계값 이상 유사도 → 동일 클러스터
4. 클러스터별 canonical event 생성
5. 중복 제거 (duplicate amplification 방지)
```

### 담당 에이전트

- **orchestrator-architect**: LangGraph state machine 설계
- **data-quality-auditor**: 클러스터 품질 검증
- **evaluation-benchmark-agent**: relevance metric 설계

---

## 단계 6: Evidence Graph (증거 그래프) — 예정

### 현재 상태: 미구현

### 설계 방향

```
각 event에 대해:
- primary_seed (발견 소스) 1~N개
- enrichment (검증 소스) 1~M개
- official_evidence (공식 데이터) 0~K개
- community_signal (커뮤니티 반응) 0~J개

evidence_score = f(소스 다양성, 소스 신뢰도, 본문 추출 성공 여부)
```

### 담당 에이전트

- **data-quality-auditor**: evidence 완전성 검증
- **legal-safety-compliance-reviewer**: 소스 attribution 정책
- **evaluation-benchmark-agent**: evidence_score metric

---

## 단계 7: Contradiction/Claim Graph (모순/주장 그래프) — 예정

### 현재 상태: 미구현 (LangGraph 도입 후)

### 설계 방향

```
LangGraph node:
1. Claim Extractor: 기사에서 주요 주장 추출
2. Claim Validator: 다른 소스와 교차 검증
3. Contradiction Detector: 모순되는 주장 감지
4. Confidence Scorer: 주장별 신뢰도 점수

출력: event_id → [claim, source, confidence, contradicts[]]
```

### 법무 주의사항

```
AI가 생성한 "모순 감지"는 오류 가능성 있음
명예훼손 위험: 특정 소스/인물을 "거짓말쟁이"로 표기 금지
표현: "소스 A와 소스 B가 다른 수치를 보고함" (중립적)
투자 조언 금지: "이 정보를 기반으로 매수/매도 권장" 금지
```

---

## 단계 8: Narrative Generation (내러티브 생성) — 예정

### 현재 상태: 미구현 (LangGraph 이후)

### 필요 환경

```
OpenAI API (OPENAI_API_KEY 존재)
LangChain/LangGraph LLM 호출
LangSmith 관측 (LANGSMITH_API_KEY 존재)
```

### 정책

```
출력 규칙:
- 사건/이벤트 정보 제공 (투자 조언 아님)
- "이 주식을 사라" 등 가치 판단 금지
- 출처 반드시 표시 (attribution)
- 불확실한 정보는 "소스 X에 따르면" 형식으로 표기
- 전문 재배포 금지 소스는 snippet만 인용
```

---

## 단계 9: UI/API Handoff — 예정

### 현재 상태: 미구현

### 필요 환경

```
FastAPI (plans/012 이후)
PostgreSQL (event 저장, docker-compose.dev.yml)
Redis (캐시, docker-compose.dev.yml)
Celery (비동기 수집, plans/012)
```

### API 계약 초안

```
GET /api/events?limit=20&offset=0      ← 최신 이벤트 목록
GET /api/events/{event_id}             ← 이벤트 상세 (증거 포함)
GET /api/sources/health                ← 소스 상태
GET /api/trends                        ← 실시간 트렌드
WS  /api/events/stream                 ← 실시간 스트리밍
```

### 담당 에이전트

- **frontend-integration-agent**: API 계약 정의
- **product-ux-strategist**: UI/UX 설계
- **operations-sre-agent**: 성능/확장성

---

## 단계 10: Monitoring (모니터링) — 부분 예정

### 현재 상태: rate-limit 모니터링만 존재

| 컴포넌트 | 상태 | 예정 |
|----------|------|------|
| rate_limit_cache.json | 완료 (local_file backend) | Redis 전환 (plans/012) |
| artifact JSONL 감사 | 완료 | Celery 통합 |
| LangSmith trace | 설정 있음 (미연결) | LangGraph 이후 |
| Celery Flower | 미설치 | plans/012 이후 |
| Prometheus/Grafana | 미설치 | 운영 안정화 이후 |

---

## 환경 구성 요약 (단계별)

| 단계 | 필요 컴포넌트 | 현재 상태 | 다음 단계 |
|------|------------|----------|----------|
| 1. 수집 | Python, Playwright, httpx, .env | ✅ 완료 | 유지 |
| 2. 후보 추출 | ingestion.pipeline | 부분 완료 | Celery 연결 |
| 3. 본문 추출 | trafilatura, readability | ✅ 완료 | 유지 |
| 4. 연관 확장 | search APIs, fallback chain | ✅ 완료 | Celery 연결 |
| 5. 클러스터링 | LangGraph, Milvus, embedding | ❌ 미구현 | plans/012 |
| 6. 증거 그래프 | Python graph logic | ❌ 미구현 | plans/012 이후 |
| 7. 모순 그래프 | LangGraph | ❌ 미구현 | plans/012 이후 |
| 8. 내러티브 | LLM (OpenAI), LangChain | ❌ 미구현 | plans/012 이후 |
| 9. UI/API | FastAPI, PostgreSQL, Redis | ❌ 미구현 | plans/012 이후 |
| 10. 모니터링 | Redis, LangSmith, Flower | 부분 | plans/012 이후 |

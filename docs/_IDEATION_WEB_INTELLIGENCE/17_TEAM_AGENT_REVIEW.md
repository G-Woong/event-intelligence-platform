# 17 — TEAM AGENT REVIEW (11개 관점 다방면 평가)

> 11개 팀 에이전트가 독립 관점으로 레포(read-only)와 2026-06 웹 리서치를 평가한 결과 요약 + 합의/충돌 + 통합 판단. 각 관점의 IMPLEMENTED 주장은 코드 열람 근거.

> ⚠️ **STALE CODE-STATE (2026-06-18, Pre-Harness Cleanup Sprint)**: 본 리뷰는 특정 시점(기준 커밋 `5491c02`)
> 기록이다. "P0 = bridge db_writer 배선"(7.2), "mock 엔티티 위 그래프 무가치"(7.4) 등 일부 전제는 이후
> 커밋으로 변동됐다(bridge 배선·라이브 입증, 5 mock 노드 → baseline). 합의/방향 판단은 유효하나 코드-상태는
> `docs/_CANONICAL/01·09`로 교차확인하라. ARCHIVE_ONLY 기록물(10 Group E).

---

## 1. 관점별 요약

**7.1 Search Engine Architect / Search Expansion Engineer** — 범용 검색엔진과 event intelligence는 단위(page vs event)가 다르다. 직접 전체 웹 크롤링은 비용·법무·중복으로 무너진다. event candidate→query formulation→citation/source-diversity 확장. Bing 폐지·Brave 무료티어 폐지 → **단일 provider = 단일 장애점**, provider-agnostic + 다중 fallback 필수.

**7.2 Source Ingestion Architect** — 강점은 "57소스 수집"이 아니라 **결정적 정책안전 라우팅 + 전략 메모리**가 코드로 실재한다는 것. "connector 100개 더"는 착각(병목은 품질·정책·배선). P0 = bridge db_writer 배선. discovery↔ingestion 분리, LLM supervisor는 결정적 레일 위 제안자.

**7.3 RAG Architect** — 3엔진 분리는 명확하나 검색이 의미·키워드로 분리돼 융합 안 됨 + swallow silent drift. hybrid(RRF)→reranker→nori 순서. Milvus 유지 vs pgvector 통합(규모/인력 전제 의존). 카드 단위 chunk, freshness/diversity 신호.

**7.4 KG-RAG Architect** — mock 엔티티 위 그래프는 무가치. GraphRAG는 3-5x 비용, multi-hop 한정. RDB 투영으로 설계, entity resolution이 최대 부담. **도입 미뤄야**(P0·hybrid RAG 먼저).

**7.5 Redis/Queue Engineer** — B의 Streams/heartbeat/AOF는 IMPLEMENTED. A의 EventQueue Redis는 `NotImplementedError`. Celery(스케줄) + Redis Streams(소비) 하이브리드, Temporal은 과함. DLQ=PEL 재사용, retry/cooldown은 rate_limit_policy.yaml 단일 출처.

**7.6 Agent Orchestration Architect** — LangGraph 0.2.76 유지가 옳다(무상태 단발 invoke). Deep Agents/벤더SDK 불필요. judge(단기)↔supervisor(장기) 분리. allowed-strategy 게이트 + unsafe 영구차단을 정식 계약으로 승격.

**7.7 LLM Safety / Security Reviewer** — 프롬프트 인젝션(OWASP LLM01)이 1위 표면(community/news 본문→LLM 노드). 외부 콘텐츠 격리·표시, 출력 schema 검증, "에이전트 출력=untrusted", 고위험 액션 HITL/결정적 룰. Admin 빈토큰 bypass 운영 전 해제, secret no-log. SSRF allowlist + EvidenceGate 룰 fetch 진입점 복제.

**7.8 Legal / Commercial Risk Reviewer** — 수집 적법성과 재배포 적법성 분리. 전문저장금지+evidence 중심이 저작권 안전. community=early signal≠evidence. newsapi/guardian/nyt/aladin CONDITIONAL, dcinside UNVERIFIED(봉인 유지). 종합 CONDITIONAL.

**7.9 Data Quality / Clustering** — content_hash/dedupe_key는 exact-match만. corroboration은 제거 아닌 신뢰 신호. dedup→cluster→timeline→rank 5단계 분리(LSH+HDBSCAN). corroboration과 diversity 분리(재게재 부풀림 방지).

**7.10 Product / UX Strategist** — evidence를 구조화 타입으로 승격(출처/날짜/링크 필수)이 신뢰 차별의 핵심. alert>API>report>dashboard>community. comments/ai_replies flag 뒤로, themes/sectors "미검증" 라벨. confidence 색상 임계(70/40)가 투자신호로 오인될 위험.

**7.11 Adversarial Reality Critic** — "엔진 완성+고급 RAG만 얹으면 됨"이 **가장 위험한 자기기만**(데이터가 mock 그래프 미통과, e2e 카드 0건). 버릴 것 5: GraphRAG/직접크롤링 확장/검색확장 욕심/per-seat 가정/범용 글로벌 야망. 살릴 것 3: 공식 API 수집기/이벤트 정규화 스키마/dedup·clustering. 살길: 소스 좁히고 P0부터, 야망을 좁은 vertical로 축소.

## 2. 합의점 (전 관점 수렴)

1. **P0(A→B 배선)가 모든 것의 선행조건**이다. connector 추가·고급 RAG·상용화 모두 그 다음.
2. **수집은 deterministic, LLM은 가치지점에만.** allowed-strategy 게이트 + unsafe 영구차단 유지.
3. **evidence 중심**(전문 저장 금지)이 저작권 안전 + 신뢰 차별을 동시에 준다.
4. **GraphRAG는 지금 아니다.** mock 엔티티 해제 + hybrid RAG가 먼저.
5. **단일 provider 의존 금지**(검색·LLM·임베딩 추상화).
6. **source coverage < event quality.** dedup/clustering이 모든 다운스트림의 전제.

## 3. 충돌점 / 미해결

| 충돌 | A측 | B측 | 처리 |
|---|---|---|---|
| Milvus 유지 vs pgvector 통합 | 대규모/고QPS면 Milvus | 50M 미만·인력 제한이면 pgvector | ADR로 규모 전제 명시 후 결정 |
| LangGraph 1.0 전환 시점 | redis checkpointer와 동시 | 0.2.76에 redis saver만 | redis 전환 시 함께 평가 |
| SourceSupervisor 실 provider 시점 | deterministic로 충분 | unresolved 소스 학습 가속 위해 조기 | 옵션화(끄면 규칙기반 동작) |
| 1차 vertical | AI/tech incident(소스 두께) | 금융/공시(WTP)·한국 규제(해자) | 좁은 vertical 집중엔 합의, 선택은 WTP 인터뷰로 |
| B2C 피드 vs B2B alert 우선 | 피드(retention) | B2B alert/API(매출 현실성) | B2B alert 우선 권고 |
| confidence 색상 임계 | 직관적 | 투자신호 오인 | 중립 표기 + 추적 tooltip |

## 4. 통합 판단

- **방향 승인**: event intelligence platform(검색엔진 아님), 고신호 source + 검색 API + evidence 랭킹 + clustering + LLM judge + product surface.
- **순서 강제**: P0(배선) → P1(큐/mock해제/dedup) → P2~P3(검색확장/hybrid) → P4~P7(supervisor/clustering/상용) → P8(GraphRAG 조건부) → P10(enterprise 보안).
- **최대 리스크**: "토대가 끝났다"는 자기기만. 실제는 e2e 카드 0건 경로. 첫 목표는 **실데이터 카드 1건 end-to-end**.
- **가장 큰 자산**: 정책안전 수집 라우팅·게이트·전략메모리(A) + evidence 추적성. 이것이 자본화된 경쟁자 대비 좁은 vertical에서 이길 지점.

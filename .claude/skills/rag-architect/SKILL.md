---
name: rag-architect
description: 검색(retrieval)·요약 품질을 RAG 지표로 평가·설계할 때 사용. Milvus(1536d) 벡터검색 recall/precision, 요약 faithfulness, MRR/NDCG 기준점을 세울 때. MASTER L6(hybrid/rerank)·요약 충실도 게이트의 수치 기준. (evaluation-benchmark-agent와 계층 분리: 이 skill=설계 패턴/임계값.)
license: MIT (upstream)
upstream: https://github.com/Jeffallan/claude-skills/tree/main/skills/rag-architect
adapted_for: WEB_INTELLIGENCE_HARNESS_EVOLUTION.md S5
---

# rag-architect (검색/요약 품질 기준 — Milvus 적응)

> upstream `Jeffallan/claude-skills/rag-architect`(MIT) 적응. **예제의 Qdrant → 본 프로젝트 Milvus(pymilvus)로 치환** 필수.
> "느낌"이 아니라 임계값으로 검색·요약 품질을 잡는다.

## 언제 쓰나
- `retrieve_past_context`(Milvus top-k) 품질 회귀를 수치로 잡고 싶을 때.
- 요약(final_writer) 충실도(faithfulness)를 평가/게이트화할 때.
- L6 hybrid(RRF)·rerank 도입 전후 효과를 비교할 때.

## 평가 지표(기준점)
- **context_precision ≥ 0.7**, **context_recall ≥ 0.6** (retrieval).
- **faithfulness**(요약이 증거에 근거하는가 — 환각 0 지향, 본 프로젝트 fail-closed 정합).
- **MRR / NDCG@k** (랭킹 품질).

## 절차
1. **골든셋:** 사건·질의·정답 근거 URL 소규모 셋 구성(전문 저장 금지 — URL+요약만).
2. **파이프라인 측정:** Chunking → Embedding(1536d) → Milvus 검색 → (요약) 각 단계 지표 산출.
3. **임계 게이트:** 위 임계 미달 시 회귀로 표시. evaluation-benchmark-agent로 정식 벤치마크 라우팅.
4. **개선:** hybrid/rerank/nori 도입을 지표 개선폭으로 정당화(ROI 추적).

## 안전·제약
- 임베딩/평가 LLM 키는 `.env` 경유(`${VAR}`)만 — 비밀 미노출. 외부 전문 저장 금지(URL+요약만).
- Qdrant 예제 코드는 그대로 쓰지 말고 **pymilvus로 치환**(미치환 시 스택 충돌).

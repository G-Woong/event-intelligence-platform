# 12 — EVENT CLUSTERING / RANKING / DEDUP LAYER (L8)

> 결론: 현재 dedup은 **exact-match만**(content_hash UNIQUE, dedupe_key)이라 같은 사건을 다른 소스가 다른 제목으로 보도하면 별개 카드로 통과한다. 이벤트 인텔리전스에서 "같은 사건 N개 소스 보도"는 제거 대상이 아니라 **신뢰도 신호(corroboration)**다. cross-source 클러스터링이 없으면 피드는 near-dup로 범람하고 corroboration 랭킹·타임라인이 불가능하다.

---

## 1. 현재 상태

- `agents/nodes/deduplicate.py` PARTIAL: `dedupe_key = normalized.hash`만, 벡터 유사도 비교는 TODO.
- `raw_events.content_hash UNIQUE(ON CONFLICT DO NOTHING)`: 바이트 동일 재수집만 차단.
- `event_cards`: confidence_score/impact_path/theme/sectors. `community_corroboration_gate`는 익명 publish 등급화.
- **클러스터링/타임라인/랭킹: `agents/` 내 grep 0건(미구현).**

## 2. 목표 파이프라인 (5단계 분리)

```text
① Exact dedup (content_hash, 유지)
② Near-dup 억제 (MinHash LSH: 제목+요약 n-gram 후보 → 같은 article 병합)
③ Cross-source clustering (임베딩 유사도 + HDBSCAN: 같은 사건 묶기, 멤버 source 보존)
④ Cluster → timeline (published_at 정렬 + First Story Detection origin)
⑤ Rank (cluster 단위 점수)
```

> 핵심 원칙: **article-level dedup(같은 글)과 event-level cluster(같은 사건)는 다른 layer.** event_cards는 article이 아니라 **cluster 대표**를 발행한다.

## 3. 알고리즘 선택 (웹 리서치)

- **LSH**: 저비용 1차 필터(O(N²) 임베딩 비교 회피).
- **임베딩 + HDBSCAN**: k 사전지정 불필요, noise(단발 사건) 별도 처리 → 불균등 클러스터 크기에 적합.
- **임계**: hard cutoff 대신 시간창 내 상대 임계(예: 48h 윈도우, cosine≥0.82 후보, min_cluster_size=2). 단일 상수 하드코딩 금지(설정값 노출).
- 참고 사례: Chronicle(임베딩+MinHash LSH+HDBSCAN→타임라인), RevDet(반복 클러스터링), First Story Detection.

## 4. 랭킹 신호

```text
cluster_score = w1·freshness(최신 멤버 시간 감쇠)
              + w2·corroboration(독립 outlet 수, 같은 매체 중복 제거)
              + w3·source_diversity(소스 카테고리 엔트로피)
              + w4·impact(significance/sectors)
```

> corroboration과 source diversity는 **분리**(한 통신사 재게재가 N으로 부풀지 않게, outlet ownership 매핑). 가중치는 설정 + 학습 여지.

## 5. 위험 / event quality 측정

- 위험: corroboration 부풀림(재게재), cluster drift(주제 혼합 → homogeneity 모니터), 펌핑 신호 cluster 진입(corroboration_gate 선적용), freshness 과중으로 중요 사건 침몰, §1 info-not-advice(impact 톤 제한).
- 지표(coverage 아닌 quality): cluster purity/homogeneity(≥0.8), duplicate leakage rate(<10%), FSD latency, corroboration precision.

## 6. 검증기준

content_hash exact dedup(유지) + MinHash LSH near-dup 억제 + 임베딩 HDBSCAN cross-source 클러스터링이 article/event level 분리 동작, 각 cluster가 4신호로 결정적·설명가능하게 랭킹, cluster→timeline(FSD origin)이 단조 정렬, gold set 기준 purity≥0.8·leakage<10%·schema validation E2E 통과, community_corroboration_gate publish_level과 §1 톤 위반 0.

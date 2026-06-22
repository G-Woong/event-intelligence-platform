# 12 — EVENT CLUSTERING / RANKING / DEDUP LAYER (L8)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 📘→🔲 — exact dedup + `cross_source_dedup`(Union-Find) 토대만 실재. Event append/timeline/heat/rank/event_resolver는 **미구현**. **임계경로(Event 라우팅 합류점, S1~S2).**
> │ **구현순위:** #12 (00_ROADMAP_INDEX) · **그룹:** C
> │ **검증 근거:** `ingestion/orchestration/cross_source_dedup.py`(Union-Find + exact/약신호 union 실재) · `raw_events.content_hash UNIQUE`. **반례:** 클러스터링/타임라인/랭킹/Event append는 `agents/` grep 0건(미구현). heat/rank/event_resolver 코드 부재.
> │ **잔여(미구현):** ⑥ Event Resolution(event_resolver), heat 4신호+half-life, merge_score 3축, append-only Event/EventUpdate, cluster_event_map/event_links, R-FalseMerge clique 게이트.
> │ **완료정의(DoD):** "2번째 보도 → 새 카드 아닌 기존 Event에 Update append" E2E + 1517 green(비파괴) + 3엔진 card_id 정합성 불변식 + transitive-only 클러스터 자동승격 금지 테스트 + gold set purity≥0.8·leakage<10%.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> 결론: 현재 dedup은 **exact-match 토대 + `cross_source_dedup`(Union-Find) 토대만 실재**(content_hash UNIQUE, dedupe_key). 같은 사건을 다른 소스가 다른 제목으로 보도하면 별개 카드로 통과한다. 이벤트 인텔리전스에서 "같은 사건 N개 소스 보도"는 제거 대상이 아니라 **신뢰도 신호(corroboration)**다. **그리고 ADR#16(Event 타임라인) 이후, cross-source 클러스터 출력은 "카드 dedup"이 아니라 "진화하는 Event 객체로의 append"로 라우팅돼야 한다** — 두 번째 보도는 새 카드가 아니라 기존 Event의 새 Update다. 이 라우팅(event_resolver)·heat·랭킹은 모두 **미구현**이다.

---

## 1. 현재 상태

- `agents/nodes/deduplicate.py` PARTIAL: `dedupe_key = normalized.hash`만, 벡터 유사도 비교는 TODO.
- `raw_events.content_hash UNIQUE(ON CONFLICT DO NOTHING)`: 바이트 동일 재수집만 차단.
- `event_cards`: confidence_score/impact_path/theme/sectors. `community_corroboration_gate`는 익명 publish 등급화.
- **클러스터링/타임라인/랭킹: `agents/` 내 grep 0건(미구현).**

## 2. 목표 파이프라인 (6단계 분리 — ⑥ Event Resolution 신설)

```text
① Exact dedup (content_hash, 유지)
② Near-dup 억제 (MinHash LSH: 제목+요약 n-gram 후보 → 같은 article 병합)
③ Cross-source clustering (임베딩 유사도 + HDBSCAN: 같은 사건 묶기, 멤버 source 보존)
④ Cluster → timeline (published_at 정렬 + First Story Detection origin)
⑤ Rank (cluster/Event 단위 점수 = heat)
⑥ Event Resolution (cluster → 영속 Event 라우팅: APPEND/HOLD/CREATE)  ◄ ADR#16 신설·임계경로
```

> 핵심 원칙: **article-level dedup(같은 글)과 event-level cluster(같은 사건)는 다른 layer.** 그리고 ADR#16 이후 **cluster는 최종 산출물이 아니다** — cluster를 **영속 Event 객체로 해소(resolve)**해 append한다. event_cards는 article이 아니라 **Event의 한 스냅샷 뷰**를 발행한다(카드 = 한 단면 snapshot).

## 2.1 ⑥ Event Resolution (event_resolver — ADR#16 / SPEC §2)

> **카드 dedup → Event append 전환.** `cross_source_dedup` 출력(cluster)을 카드 중복제거가 아니라 **기존 Event에 Update를 append하거나, 모호하면 보류하거나, 미매핑이면 새 Event를 생성**하는 라우터(`event_resolver`, 미구현). 전부 **append-only**(가역성·감사).

| 신호 강도 | 판정 | 동작 |
|---|---|---|
| **강신호**(canonical_url/official_id/signal key 일치 = `has_strong`) | APPEND | 매핑된 Event에 `event_updates` 1행 append + heat_delta 반영 |
| **약신호**(title Jaccard만, FSD 모호) | HOLD | `event_links.status='possible'` 보류(자동병합 금지, reason 기록) → 사람/추가신호로 확정 |
| **미매핑**(어느 Event에도 안 붙음) | CREATE | 신규 `events` 1행 생성(FSD origin = first_seen_at) |

- **라우팅 영속화:** `cluster_event_map(cluster_id → event_id)` 가 단일 진실원천(`event_cards.event_id`는 derived). cluster가 어떤 Event로 갔는지를 영속 기록해 재실행 시 같은 라우팅.
- **FSD origin 표준:** 더 이른 보도가 나중에 발견되면 `first_seen_at`을 **과거로만 당긴다**(미래로 밀지 않음 = 단조). origin source_ref 보존.
- **가역성:** append-only + `event_links`(possible/confirmed/rejected/merged)로 split/unmerge 가능. in-place mutable 금지(감사성·롤백 경계 보존).
- 스키마 토대: `5_REFERENCE/EVENT_SCHEMA.md` Part 2(events/event_updates/cluster_event_map/event_links DDL). 결정: ADR#16. 위험: R-EventModelMigration(3엔진 정합성)/R-FalseMerge(transitive 오염).

## 3. 알고리즘 선택 (웹 리서치)

- **LSH**: 저비용 1차 필터(O(N²) 임베딩 비교 회피).
- **임베딩 + HDBSCAN**: k 사전지정 불필요, noise(단발 사건) 별도 처리 → 불균등 클러스터 크기에 적합.
- **임계**: hard cutoff 대신 시간창 내 상대 임계(예: 48h 윈도우, cosine≥0.82 후보, min_cluster_size=2). 단일 상수 하드코딩 금지(설정값 노출).
- 참고 사례: Chronicle(임베딩+MinHash LSH+HDBSCAN→타임라인), RevDet(반복 클러스터링), First Story Detection.

## 4. 랭킹 신호 — heat (시계열 활성도, ADR#16 / SPEC §2.4)

ADR#16 이후 랭킹은 1회성 cluster_score가 아니라 **Event의 시계열 활성도 `heat`**다. half-life 감쇠로 단조 누적 폭주를 막고, append되는 Update마다 heat_delta를 누적한다.

```text
heat(t) = heat(t-1)·exp(-Δt/half_life)              ← 시간 감쇠(단조 누적 폭주 방지)
        + Σ heat_delta(신규 Update)
heat_delta = w1·recency + w2·update_frequency
           + w3·corroboration_diversity + w4·domain_spread
```

- 기본 가중치 0.4 / 0.3 / 0.2 / 0.1 (설정값, `.env.example` 빈값=DEFAULT 계약). `HEAT_HALF_LIFE_HOURS` 빈값=감쇠없음.
- **corroboration = 출처 수가 아니라 `source_role` 다양성 엔트로피**(orchestrator #3): 같은 통신사 재게재 N건이 부풀지 않게, 또 OFFICIAL+NEWS 조합 > COMMUNITY×5(에코챔버 방지). 즉 corroboration과 source diversity를 **엔트로피 1지표로 통합**(outlet ownership/role 매핑). 이전 cluster_score의 "corroboration과 source diversity 분리" 의도는 role 엔트로피로 흡수.
- **domain_spread (added_domains 누적 = 전이 통계):** domains는 닫힌 8섹터가 아니라 **열린 2층**(통제어휘 ~20 `domains` + free-form `tags`). 각 Update의 `added_domains`를 시계열로 누적해 "사건이 어느 분야로 번졌나"를 사후 빈도로 기록(예측 아님, BI 인사이트 #1).
- **heat → 차등 폴링:** `base_interval / (1 + heat·k)`. 단 **rate-limit 하한(gdelt 60s 등)은 절대 clamp**(우회 금지 불변, R-Bypass).
- impact(significance/sectors)는 §1 info-not-advice 톤 제한 하에서 보조 신호(가치판단·투자조언 0).

## 4.1 merge_score 3축 — 양자화 문제 교정 (orchestrator #2)

> **현 코드 보존(문제 명시):** `cross_source_dedup.py:165-169`의 `has_strong=any(...)`는 클러스터에 강신호 edge가 **1개라도** 있으면 클러스터 전체를 `CONF_DUPLICATE`로 판정한다. 그리고 `:149`는 title Jaccard≥0.8(`_TITLE_JACCARD_THRESHOLD`) 연속값을 **1비트(has_strong)로 양자화**해 폐기한다 — Jaccard 0.81과 0.99가 동일 취급. Event append(ADR#16)로 라우팅되면 이 거친 1비트 판정이 영속 Event 병합을 좌우한다.

병합 해상도는 시간창 1축이 아니라 **3축 점수**로 한다(시간창은 `EVENT_MERGE_TIME_WINDOW_HOURS` 4번째 보조축):

```text
merge_score = entity_overlap × domain_distance × signal_strength
```

| 축 | 의미 | 비고 |
|---|---|---|
| **entity_overlap** | primary_entity_ids 교집합 비율 | Entity Registry(17) 앵커 기반 |
| **domain_distance** | domains 간 거리 행렬 | **거버넌스 산출물**(통제어휘 ~20 사이 거리 = ADR로 관리, 임의 상수 금지) |
| **signal_strength** | Jaccard 연속값 보존(1비트 양자화 폐기) | `:149` 연속값을 점수로 살림 |

- domain distance 행렬은 단일 상수 하드코딩 금지(거버넌스 ADR 산출물, `UNKNOWN`: 도메인별 θ 튜닝값 = 00_ROADMAP_INDEX §6).
- 병합 임계 θ는 설정값 + 학습 여지(현재 미정 = UNKNOWN).

## 4.2 R-FalseMerge — Union-Find transitive 오염 (adversarial #1)

> **차별점(교차검증 신뢰)을 붕괴시키는 핵심 위험.** `cross_source_dedup.py:149`가 title Jaccard≥0.8이면 `uf.union(i, j)` → Union-Find **transitive 폐쇄**: A–B 0.8, B–C 0.8이면 A–C 유사도가 0이어도 같은 클러스터. `:165-169` `has_strong=any(...)`라 그 클러스터에 강신호 edge 1개만 있으면 **약신호로 끌려온 무관 레코드까지 전체가 CONF_DUPLICATE → 자동 APPEND**.

- 현재는 카드 1회성이라 오염이 갇히나, **Event append 라우팅(ADR#16) 도입 시 영속 Event에 누적·전파** → 고heat Event가 무관 사건을 흡수하면 1건의 명백한 오병합도 교차검증 신뢰를 붕괴.
- **완화책(설계):** ① **clique(완전연결) 게이트** — transitive-only로 묶인 클러스터는 자동승격 금지(`event_links.status='possible'` HOLD). ② **edge provenance** — 어떤 edge가 멤버를 추가했는지 기록(split 가역). ③ 약신호 edge가 추가한 멤버에만 **pairwise 재검사**(분모 축소).
- 추적: `R-FalseMerge`(R-Dedup LOW→MEDIUM 승격, `_RISK/RISK_REGISTER.md`). dedupe_key 임계 미정은 R-Dedup에 잔존.

## 5. 위험 / event quality 측정

- 위험: corroboration 부풀림(재게재), cluster drift(주제 혼합 → homogeneity 모니터), 펌핑 신호 cluster 진입(corroboration_gate 선적용), freshness 과중으로 중요 사건 침몰, §1 info-not-advice(impact 톤 제한), **R-FalseMerge transitive 오염**(§4.2), **3엔진 정합성 드리프트**(R-EventModelMigration: Event 스냅샷 빈번 재생성 시 PG/Milvus/OpenSearch card_id 색인 불일치).
- 지표(coverage 아닌 quality): cluster purity/homogeneity(≥0.8), duplicate leakage rate(<10%), FSD latency, corroboration precision.

## 5.1 BI 인사이트 (Event 모델 위에서만 성립 — ADR#15 트래픽×광고 연결)

> 모두 ADR#16 Event/Update 토대 위에서만 가능. **불변:** 예측이 아니라 사후 빈도+증거, 투자조언/가치판단 톤 0(§1), 전문 재배포 0(요약+증거링크만).

- **#1 Spillover Map** — `added_domains`(Update별) 집계 = **분야 전이 통계**. "호르무즈 사건이 defense→energy→finance→insurance로 번짐"을 사후 빈도+증거로 시각화. **예측 아님**(과거 전이 빈도일 뿐), **투자조언 톤 금지**(어느 섹터를 사라/팔라 0).
- **#5 Live Index** — `heat` 정렬 큐레이션 피드(실시간 핫 사건). 단 **corroboration 하한**(role 다양성 엔트로피 최소치)으로 **미검증 핫이슈·펌핑 신호 차단**(community_corroboration_gate 선적용). heat만 높고 corroboration 낮은 단일출처 사건은 Live Index 진입 차단.
- **#7 Event Replay** — 종료(closed) 사건의 **append-only 완결 타임라인 아카이브**. event_updates가 INSERT-only라 사건의 전 생애가 보존됨 → 사용자향 `retrieve_past_context`(과거 맥락 검색)로 노출. 구독 없는 리텐션(무료 웹 알림·재점화, ADR#15 §2 미수렴 쟁점 회수).

> 광고 면적 정당성: 이 3종은 모두 **요약+증거링크+시계열 시각화**(파생 콘텐츠)이지 전문 재배포가 아니다(ADR#15 §3.4, R-FullText 불변 유지). 페이지 비전문비율 게이트(BI #6)로 측정·강제.

## 6. 검증기준

content_hash exact dedup(유지) + MinHash LSH near-dup 억제 + 임베딩 HDBSCAN cross-source 클러스터링이 article/event level 분리 동작, 각 cluster가 heat 4신호로 결정적·설명가능하게 랭킹, cluster→timeline(FSD origin)이 단조 정렬, **⑥ Event Resolution이 "2번째 보도 → 새 카드 아닌 기존 Event에 Update append" E2E 통과**(강신호 APPEND·약신호 HOLD·미매핑 CREATE 라우팅 결정적), append-only 불변식(event_updates INSERT-only) + transitive-only 클러스터 자동승격 금지(R-FalseMerge) + 3엔진 동일 card_id 정합성 불변식(R-EventModelMigration) + **1517 green(비파괴)**, gold set 기준 purity≥0.8·leakage<10%·schema validation E2E 통과, community_corroboration_gate publish_level과 §1 톤 위반 0.

- 링크: `R-EventModelMigration`/`R-FalseMerge`/`R-MockCard`(`_RISK/RISK_REGISTER.md`), `2_ROADMAP/19`(Event Resolution·SPEC §2, NET-NEW — 00_ROADMAP_INDEX 순위#17), `5_REFERENCE/EVENT_SCHEMA.md` Part 2(events/event_updates/heat/cluster_event_map/event_links/domains DDL), 결정=`_DECISIONS/2026-06.md` ADR#16.

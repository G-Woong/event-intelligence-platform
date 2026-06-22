# 05 — DISCOVERY & SOURCE EXPANSION LAYER (L1)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 🟡 PARTIAL — registry57·SourceCapability·StrategyGraph·EvidenceGate·정책게이트 인프라는 실코드 토대. P0 기본 sink는 mirror(bridge db_writer 미주입)·Entity/Authority 발견은 NET-NEW 미구현.
> │ **구현순위:** #1 (00_ROADMAP_INDEX) · **그룹:** A
> │ **검증 근거:** `source_registry`(57소스 단일선언)·`SourceCapability`·`StrategyGraph`(`UNSAFE_STRATEGIES` 11종 reject)·`EvidenceGate`·`CommunityCorroborationGate`·`SourcePolicyProbe`·`SourceStrategyMemory`·`derive_production_state` total function 실코드 라이브. 정밀 file:line은 `_CANONICAL/01·03`이 권위.
> │ **잔여(미구현):** ① A→B bridge `db_writer=None`(P0 기본 sink가 mirror, PG 미도달) ② SourceCapability 4소스만 선언(53 미선언) ③ Entity Registry → Authority Discovery 발견 엔진 NET-NEW 부재(→ 17 위임) ④ EventQueue Redis 미배선.
> │ **완료정의(DoD):** A→B bridge db_writer 주입→raw_events PG 1건+ 적재 · schedulable 소스 100% capability+graph 선언 · 2회+ 지속검증 READY 확정 · 모든 우회 전략 reject + secret 0 · (중기) Entity·Authority 발견엔진 라이브.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> 결론: 병목은 "소스 발견"이 아니라 **품질·정책·배선**이다. connector를 100개 더 붙여도 P0(A→B)가 안 뚫리면 PG row는 0이다. 소스 수는 허영 지표다.
>
> **시간축(경쟁 아니라 페이즈):** **P1(단기) = 57소스 안정화**(A→B 배선·capability 전수·지속검증) → **요구6(중기) = Entity·Authority 발견엔진**(§3 발견 레이어). 두 페이즈는 *동시 경쟁이 아니라 순차*다 — P1이 PG row를 뚫어야 발견엔진이 쌓을 토대가 생긴다(`00_ROADMAP_INDEX §4` 임계경로 S4 Entity Registry는 S1 Event 토대 이후).

---

## 1. 현재 상태 (IMPLEMENTED, 코드 근거)

- `source_registry` 57소스 단일 선언. `SourceCapability`(능력 선언) → `StrategyGraph`(안전 전략 빌드, `UNSAFE_STRATEGIES` 11종 reject) → `EvidenceGate`(shape 린터) → `CommunityCorroborationGate`(dcinside 봉인).
- `SourcePolicyProbe`: robots longest-match, AI 크롤러 토큰 차단, paywall/login 마커.
- `SourceStrategyMemory`: 소스별 `successful_strategy`/`failed_strategies`/`llm_agent_hints` 누적, `preferred_strategy_for`/`is_known_dead_end`.
- `derive_production_state` total function(UNKNOWN=0), `SCHEDULABLE_STATES` 분리. rate governance(`rate_limit_policy.yaml`).

> **정직 경계(GroundTruth):** 위 §1 인프라(registry57·정책게이트·StrategyGraph·EvidenceGate)는 **실코드 토대**다(검증 근거 = 스탬프). 그러나 **P0 기본 sink는 mirror**(bridge `db_writer` 미주입 → seed가 PG 미도달)이며, **Entity Registry / Authority Discovery 발견 엔진은 NET-NEW 미구현**이다(§3 신설 목표·17 위임). 인프라 존재 ≠ 발견 레이어 완성. 미구현을 구현됨으로 적지 않는다.

## 2. 한계 / 갭

| 갭 | 근거 | 영향 |
|---|---|---|
| **A→B bridge db_writer 미주입(P0)** | `bridge_to_raw_events.py` db_writer=None | seed가 PG에 미도달, mirror만 |
| EventQueue Redis 미배선 | `event_queue.py` `_redis_*` NotImplementedError | 멀티워커 공유 큐 부재 |
| 단발 LIVE_SUCCESS를 READY로 계상 | registry status 근거 | READY 46 과대평가 위험 |
| SourceCapability 4소스만 선언 | 53소스 미선언 | 라우팅 입력 불완전 |
| discovery↔ingestion 경계 미문서화 | — | 책임 혼선 |

## 3. 목표 / 구현방향

1. **P0: bridge에 db_writer 주입** — workers POST 경유로 raw_events PG 적재. mirror→DB 전환. (acceptance: ingestion seed 1건 PG row 확인)
2. **지속 검증** — 단발 probe를 `PROBED_ONLY` 중간 등급으로 두고, 2회+ 연속 성공 시 READY 확정.
3. **discovery 분리** — `source_policy_probe` 기반 신규 고신호 소스 후보 자동 평가(robots/ToS 사전판정 → 점수화 → registry 제안). ingestion 실행 경로는 결정적 유지.
4. **capability 확장** — schedulable 소스 전부 SourceCapability 선언.
5. **고신호 공식 소스 우선** — SEC EDGAR(무료/무키, 10 req/s, UA 필수), OpenDART, Guardian, federal_register. 직접 크롤링 소스는 차단·법무 리스크 후보.
6. **Entity Registry → Authority Discovery 발견 엔진 (중기 발견 레이어 목표, NET-NEW)** — registry57은 *선언된* 소스 집합일 뿐 "사건의 주체(Entity)로부터 권위 출처(Authority)를 *발견*"하는 메커니즘은 부재다. 발견 레이어 목표는 2단:
   - **Entity Registry**: 정규화 파이프 NER 재사용 + 앵커 매칭으로 사건 주체(기관·기업·인물·지명)를 candidate로 적재, 자동승격/병합은 *분리*(승격은 결정론 게이트). 소비 표면 = `entities`(EVENT_SCHEMA, ADR#16 확장 예정).
   - **Authority Discovery**: Entity → 그 주체의 1차 권위 출처(공식 IR/규제공시/정부 도메인) 후보를 robots/ToS 사전판정(§3-3 `source_policy_probe`)으로 점수화 → registry 제안. **우회 불변금지**: 발견은 allowlist·정책게이트를 통과한 후보만, 직접 크롤링·proxy·RPC 스크래핑 제안 0.
   - **상세 스펙(스키마·승격게이트·Change Detection·Sitemap·SLM Body Fallback)은 17로 위임** — `2_ROADMAP/17_AUTHORITY_DISCOVERY_AND_SLM_BODY_FALLBACK.md`(NET-NEW, 00_ROADMAP_INDEX 순위 16 등재). 본 문서는 *발견 레이어 목표*만 선언, 구현 상세는 17 단일출처.

## 4. 비용 / 위험

- 비용: 공식 API 위주는 거의 무료(SEC/OpenDART/GDELT/federal_register). 유료 검색·뉴스 API는 L2에서 통제.
- 위험: dcinside ToS UNVERIFIED(수집 닫고 publish 봉인 유지), gdelt scheduled 429(우회 금지·cooldown), POLICY_EXCLUDED 9 영구 제외, 단발 probe 과신.

## 5. LLM SourceSupervisor 역할 (미래)

- 코드 작성이 아니라 **결정적 레일 위의 제안자**: `reject_unsafe`로 우회 제안을 거른 뒤 allowed registry 안에서만, `llm_agent_hints`를 읽어 제안. discovery 후보 점수화에만 관여, ingestion 실행은 결정적.

> **P/G/F 경계 교차참조 (ADR#14):** 위 SourceSupervisor의 "제안"은 **LAYER P(Planning, LLM 관여·비결정 허용)**에 속하고, allowlist·`_UNSAFE_STRATEGIES`·정책게이트 통과는 **LAYER G(Gate, 결정론 검문)**, 실제 fetch는 **LAYER F(Fetch, LLM 미관여)**다. 즉 발견엔진(§3-6)의 Authority 후보 제안도 동일 P/G/F를 따른다 — "LLM은 *무엇을·어디서*를 계획하고, 결정론 엔진이 *어떻게(준수하며)*를 실행한다. 우회·rate 위반은 어느 층에서도 금지." 경계 권위 = `11_LLM_SOURCE_SUPERVISOR_AND_JUDGE_LAYER.md` §3 + `_DECISIONS/2026-06.md` ADR#14.

## 7. BI #3 — Entity Dossier (엔티티 소비 표면, 트래픽 자산)

- **무엇:** Entity Registry(§3-6)가 적재한 각 주체에 대해 **영구 랜딩 페이지 `/entity/{id}`**를 제공한다. 그 주체와 연결된 Event 타임라인(ADR#16)·증거링크·관련 도메인을 한 면에 모은 **엔티티 소비 표면(dossier)**.
- **왜(상용화 정합, ADR#15):** dossier는 SEO 롱테일 영구 랜딩이다 — "특정 기관/기업/지명 + 사건" 검색 진입을 흡수해 체류·재방문·페이지뷰를 만든다(트래픽×광고 모델의 콜드스타트 채널 후보). **구독 표면이 아니라 무료 공개 트래픽 표면**이다.
- **불변 준수:** dossier는 **요약+증거링크+엔티티 메타**만 노출(전문 재배포 0, 투자조언 0). 광고 정당성은 비전문 파생 콘텐츠(요약·시계열·관계)로 확보(`13` 광고 모델 §, ADR#15).
- **링크:** 데이터 토대 = Entity(EVENT_SCHEMA `entities`, ADR#16 확장 예정)·발견엔진(§3-6·17). 상용화 연결 = `13_COMMERCIALIZATION_AND_PRODUCT_STRATEGY.md`.

---

## 관련 문서 (링크)

- `2_ROADMAP/17_AUTHORITY_DISCOVERY_AND_SLM_BODY_FALLBACK.md` — Entity Registry·Authority Source Graph·Change Detection·SLM Body Fallback 상세(NET-NEW, `00_ROADMAP_INDEX` 순위 16).
- `2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md` — Event Resolution·Entity 스키마·단계 S1~S11(NET-NEW, `00_ROADMAP_INDEX` 순위 17).
- `2_ROADMAP/06_SEARCH_API_AND_WEB_EXPLORATION_LAYER.md` — P/G/F + tiered router(검색 확장 L2).
- `2_ROADMAP/11_LLM_SOURCE_SUPERVISOR_AND_JUDGE_LAYER.md` — P/G/F 경계·judge/supervisor 분리.
- `5_REFERENCE/EVENT_SCHEMA.md` — `entities` 필드(ADR#16 Entity/Event 확장 예정).
- `_DECISIONS/2026-06.md` — ADR#14(LLM 수집경계 P/G/F)·ADR#15(트래픽×광고)·ADR#16(Event 타임라인).

## 6. 검증기준 (완전 달성)

(1) A→B bridge db_writer 주입 → seed 1건+ raw_events PG 적재, (2) schedulable 소스 capability+graph 100% 선언, (3) LIVE_SUCCESS 2회+ 지속검증으로 READY 확정, (4) 모든 우회 전략 빌드/제안 시 reject + secret scan 키 0건.

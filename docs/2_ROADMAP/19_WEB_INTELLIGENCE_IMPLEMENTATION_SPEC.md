# 19 — WEB INTELLIGENCE IMPLEMENTATION SPEC (5대 신규자산 구현 청사진)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 🔲 NOT_DONE (NET-NEW) — 설계 청사진(≠ 최종코드). event_resolver/expansion_router/agent_debate/alembic 0004~0007 전부 부재.
> │ **구현순위:** #17 (00_ROADMAP_INDEX) · **그룹:** D (신규 NET-NEW)
> │ **검증 근거:** GroundTruth — 해당 모듈 ls 실패·grep 0건. comment.py debate컬럼 0.
> │ **잔여(미구현):** S1~S11 전부. 권장순서 S1→S5→S2/S3→S4→S7→S8→S9→S10→S11.
> │ **완료정의(DoD):** S1~S11 각 DoD(SPEC §20) + 6대 무조건게이트(1517green/secret scan/git diff clean/우회0/투자조언0/전문저장0).
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> **이 문서의 지위:** 방향 결정(`_DECISIONS/2026-06.md` ADR#14/#15/#16)이 합의한 새 방향을, **실제 스키마·모듈 시그니처·데이터 흐름·단계 계획·수용 기준**으로 구체화하는 구현 스펙이다. ADR#16이 "무엇을 바꿀지", `2_ROADMAP/12`가 "Event 라우팅을 어디에 얹을지"라면, 이 문서는 **"코드로 무엇을 어떤 형태로 짓는지"** 다.
>
> **권위·범위:** 본 문서의 스키마/시그니처는 **설계 청사진**이지 최종 코드가 아니다(실제 구현은 각 atomic task에서). 모든 신규 구조는 **기존 코드와 비파괴 통합**(additive)을 제1 제약으로 한다 — 기존 1,517 테스트 green 유지가 모든 단계의 무조건적 acceptance다.
>
> **DDL 단일 출처:** 테이블 DDL 상세(컬럼·타입·인덱스)는 **`5_REFERENCE/EVENT_SCHEMA.md` Part 2**가 권위다. 본 문서는 거기로 포인터 + 핵심만 재수록하고, **흐름·라우팅·의사코드·단계·테스트**에 집중한다.
>
> **설계 5대 지렛대(SESSION_CONCEPT §18 도출):** ① Change Detection으로 LLM 비용 제어, ② Event 2층 모델로 병합 해상도 제어, ③ Entity 앵커로 발견 안전, ④ 경량 JSONB로 그래프 비용 제어, ⑤ 점진 결선으로 빅뱅 회피. 이 다섯이 아래 모든 모듈의 설계 제약이다.
>
> **불변 가드(전 모듈 공통, 타협 불가):** 우회 금지(robots/ToS/CAPTCHA/login/paywall/rate-limit/proxy)· 전문 저장·재배포 금지·투자조언 금지·`.env` 미열람/미수정/미커밋·비밀 미노출(길이/존재만)·재현성.

---

## 목차

- §0. 아키텍처 한눈에 — 새 토대의 전체 그림
- §1. [토대] Event 타임라인 스키마 (events / event_updates / 카드=스냅샷)
- §2. [자산①] Event Resolution Engine (문서 → 사건 객체)
- §3. [자산②] Entity Registry (URL → 엔티티)
- §4. [요구3] 열린 domains + free-form tags 2층 분류
- §5. [자산⑤] LLM Expansion Router (Query Planning + tiered + budget)
- §6. [요구1] Source Routing 배선 (supervisor llm_propose)
- §7. [자산③] Authority Discovery 통합 파이프라인 (→ 상세는 `2_ROADMAP/17`)
- §8. [자산④] Evidence Graph (evidence JSONB 승격 + 관계)
- §9. [요구2] Agent Debate Layer (comment 확장 + 논쟁 그래프)
- §10. [요구1 P-3] SLM Body Fallback (통신서버 추론)
- §11. 단계 계획 (Phase·의존성·순서 S1~S11)
- §12. 마이그레이션 안전 (비파괴 전략)
- §13. 테스트·수용 매트릭스
- §14. 비용·운영 가드 종합
- §15. 데이터 예시 (실제 JSON)
- §16. End-to-End 플로우 — "호르무즈"
- §17. 모듈별 엣지케이스·실패 경로
- §18. API 계약 변경 (frontend 영향, 비파괴)
- §19. 운영 메트릭·대시보드
- §20. 단계별 "정의된 완료(DoD)"
- §21. 엔진별 상세 의사코드 (5종)
- §22. Alembic 마이그레이션 스케치 (0004~0007)
- §23. 설정 키 (10키, `.env.example` 추가 제안)
- §24. 테스트 케이스 열거 (단계별)
- §25. 구현 착수 체크리스트 (S1 예시)

> **상호참조 지도:** 본 문서가 가리키는 권위·인접 문서 — 결정=`_DECISIONS/2026-06.md`(ADR#14/#15/#16) · DDL=`5_REFERENCE/EVENT_SCHEMA.md` Part 2 · 진입 지도=`2_ROADMAP/00_ROADMAP_INDEX` · Event 라우팅=`2_ROADMAP/12` · tiered router=`2_ROADMAP/06` · P/G/F 경계=`2_ROADMAP/11` · Authority/Entity/Change/SLM 상세=`2_ROADMAP/17`(등재됨, 본 문서와 형제) · GraphRAG 보류=`2_ROADMAP/09` · 광고=`2_ROADMAP/13` · 위험=`_RISK/RISK_REGISTER.md`.

---

## §0. 아키텍처 한눈에 — 새 토대의 전체 그림

```
                         ┌──────────────── DISCOVERY (중기, 요구1·6) ────────────────┐
                         │  Entity Registry ─► Authority Source Graph ─► Sitemap       │
                         │        │                    │                  Discovery     │
                         │        └────────────────────┴──────► Change Detection ──────┤
                         └───────────────────────────────────────────────│────────────┘
                                                                          ▼ (변화 시에만)
   57소스 결정론 수집 ──► raw_events ──► [LLM Triage] ──► Candidate Event Queue
        (APPLIED)            (APPLIED)      (요구1)              │
                                                                 ▼
                                              ┌──── Event Resolution Engine (자산①, 요구3) ────┐
                                              │  dedup(Union-Find) ─► event_id 라우팅          │
                                              │  같은 사건? ─ yes ─► event_updates APPEND        │
                                              │              ─ no  ─► events INSERT (new)        │
                                              └───────────────────────│─────────────────────────┘
                                                                       ▼
                          ┌──── domains/tags 2층 ────┐      ┌──── Evidence Graph (자산④) ────┐
                          │ 상위 통제어휘 + 하위 tag  │      │ evidence 노드/엣지 (JSONB)      │
                          └───────────│──────────────┘      └──────────│──────────────────────┘
                                      ▼                                 ▼
   [LLM Expansion Router (자산⑤,요구1)] ◄─── 확장 필요 판단 ───►  Event (살아있는 사건)
     query_generator ─► expansion_router(tiered+budget) ─► 외부검색 ─► raw_events 재유입
                                      │
                                      ▼
                         Event 뷰: ① 스냅샷 카드  ② 타임라인  ③ 다분야 그래프  ④ 논쟁 스레드
                                                                              │
                                                          [Agent Debate Layer (요구2)]
                                                          comment(user/agent) + claim/counter/evidence
                                                                              │
                                                                    ▼ 트래픽 → 광고 (요구2)
```

**읽는 법:** 왼쪽 아래(57소스→raw_events→Triage)는 **이미 APPLIED**. 가운데(Event Resolution→Event)가 **요구 3의 새 토대**. 위쪽 점선(Discovery)은 **중기 신규(요구 1·6, 상세 = `2_ROADMAP/17`)**. 오른쪽(Evidence Graph·Expansion·Debate)은 Event 위에 얹히는 **요구 1·2 레이어**. 모든 LLM 호출은 Change Detection·budget guard 뒤에 있어 비용이 제어된다.

---

## §1. [토대] Event 타임라인 스키마

요구 3의 핵심: 사건을 1회성 카드가 아니라 **진화하는 객체**로(ADR#16). `event_cards`(불변)는 유지하되 의미를 "Event의 현재 스냅샷"으로 격하하고, 그 위에 **`events`(주제)·`event_updates`(변화분)** 2층을 신설한다.

> **DDL 권위:** 아래 §1.1~§1.4는 핵심 요약이다. 컬럼·타입·인덱스·NULL·기본값의 완전한 DDL은 **`5_REFERENCE/EVENT_SCHEMA.md` Part 2 §Event / §EventUpdate / §event_cards 의미 전환 / §cluster_event_map·event_links** 가 단일 출처다.

### §1.1 `events` 테이블 (안정 주제) — 핵심 컬럼
`id`(UUID PK) · `canonical_title` · `status`(active/dormant/closed, heat 감쇠로 자동 전이) · `first_seen_at`(FSD, 과거로만 당김) · `last_update_at` · `heat`(0~1, §2.4) · `domains` JSONB(상위 통제어휘) · `tags` JSONB(free-form) · `primary_entity_ids` JSONB(Entity FK) · `snapshot_card_id`(현재 노출 카드).
인덱스: `heat DESC`, `status`, `last_update_at DESC`, `domains` GIN, `first_seen_at`.

### §1.2 `event_updates` 테이블 (append-only 변화분) — 핵심 컬럼
`id` · `event_id`(FK→events.id CASCADE) · `observed_at` · `delta_summary`("유가 +4% 반응") · `evidence` JSONB(EvidenceNode[], §8) · `added_domains` JSONB · `source_refs` JSONB(raw_events.id[]/cluster_id) · `heat_delta`.
인덱스: `(event_id, observed_at DESC)`. **append-only**(수정·삭제 없음 → 가역성·감사).

### §1.3 `event_cards` 의미 전환 (비파괴)
- 기존 컬럼 전부 유지. **추가만**: `event_id UUID NULL`(FK → events.id).
- 의미: 카드 = "특정 Event의 한 스냅샷". 공개 API(`/api/events`)는 당분간 **현행 동작 유지**(event_cards 조회) → 점진적으로 events.snapshot_card_id 경유로 전환.
- **호환성:** event_id가 NULL인 기존 카드도 정상 동작(단독 카드 = Event 1개짜리 degenerate case).

### §1.4 Pydantic 스키마 추가
```text
Event:        id, canonical_title, status, first_seen_at, last_update_at,
              heat, domains[], tags[], primary_entity_ids[], snapshot_card_id
EventUpdate:  id, event_id, observed_at, delta_summary, evidence[], added_domains[],
              source_refs[], heat_delta
```

**수용 기준(§1):** additive 마이그레이션 적용 후 기존 1,517 테스트 green / events·event_updates CRUD 단위테스트 / event_id NULL 카드 정상 조회.

> ┌─ 심화 보강 (adversarial #5) — "1517 green = 비파괴"는 이중쓰기 정합성을 보장하지 않는다 ─
> │ event_cards(스냅샷)·events(주제)·event_updates(변화분)는 같은 사건의 **3중 진실원천**이 될 수 있다. 기존 1,517 테스트는 *카드 단독* 경로만 검증하므로, 신규 이중쓰기(카드 갱신 + Event append)의 **정합성은 미검증 영역**이다.
> │ **요구 불변식(R-EventModelMigration):** ① `events.snapshot_card_id`가 가리키는 카드의 `event_id`는 그 event를 역참조해야 한다(쌍방향 일관). ② **3엔진(Postgres/Milvus/OpenSearch) card_id 불변식** — 같은 카드가 색인되면 세 엔진의 식별자가 동일 card_id로 수렴해야 한다(드리프트 0). ③ `cluster_event_map`을 단일 진실원천으로 두어 카드↔이벤트 매핑 분기를 차단.
> │ **DoD 병기:** S1·S2에 "이중쓰기 정합성 테스트"를 회귀로 추가(1517 green과 별개 게이트).
> └────────────────────────────────────────────────────────

---

## §2. [자산①] Event Resolution Engine (문서 → 사건 객체)

SESSION_CONCEPT §5/§4. dedup이 만든 "같은 사건 묶음"을 **새 카드 생성이 아니라 Event append**로 라우팅한다.

### §2.1 현재 재사용 토대
- `ingestion/orchestration/cross_source_dedup.py:91-180` — Union-Find, 강신호(canonical_url/official_id/structured)·약신호(title Jaccard>0.8 + date bucket) → `cluster_id` + `confidence`(CONF_DUPLICATE/CONF_POSSIBLE).
- `ingestion/orchestration/eventqueue_dedup.py:80-122` — 6-tier dedup key.

### §2.2 라우팅 로직 (신규 `event_resolver.py`)

```text
resolve(candidate, cluster_result) -> EventRoutingDecision:
  if cluster_result.cluster_id maps to existing event_id (via cluster_event_map):
      if cluster_result.confidence == "duplicate":   # 강신호
          -> APPEND event_update to that event_id
      else:  # "possible" 약신호
          -> HOLD as possible_link (분리 보류, 검수/논쟁 큐)   # false merge 방지
  else:
      -> CREATE new event (FSD: first_seen_at = candidate.observed_at)
         register cluster_id -> event_id in cluster_event_map
```

- **`cluster_event_map` 테이블**(신규): `cluster_id → event_id` 라우팅 영속화.
- **possible_link 처리:** 약신호는 자동 병합 금지. `event_links`(신규, status=possible/confirmed/rejected)에 적재 → 고heat이면 논쟁 레이어(§9)가 사람에게 "같은 사건인가?" 표면화.

### §2.3 FSD (First Story Detection)
- 새 Event 생성 시 `first_seen_at` = 후보의 가장 이른 observed_at. 이후 더 이른 보도가 발견되면 `first_seen_at` 갱신(과거로만 당김, append-only 원칙 유지).

### §2.4 heat 산식 (시계열 활성도)
```text
heat(t) = heat(t-1)·exp(-Δt/half_life)              ← 시간 감쇠(단조 누적 폭주 방지)
        + Σ heat_delta(신규 Update)
heat_delta = w1·recency + w2·update_frequency
           + w3·corroboration_diversity + w4·domain_spread
```
- 가중치는 설정값(빈값=DEFAULT 계약 준수, §23). 기본 0.4/0.3/0.2/0.1.
- heat은 랭킹·섹터 진입("호르무즈가 섹터로 자리잡음")·차등 폴링 주기(§7)에 사용.
- 완전한 산식·corroboration 엔트로피 정의는 `5_REFERENCE/EVENT_SCHEMA.md` Part 2 §heat 산식 권위.

### §2.5 트레이드오프·해결 (SESSION_CONCEPT §5)
- false merge/split → 강신호 자동·약신호 보류 + append-only 가역성 + 논쟁 검수.
- 해상도 모호 → 2층(Event/Update) + spawn child Event 허용(향후) + 임계 파라미터화.

**수용 기준(§2):** 같은 사건 2번째 보도가 **새 카드 아닌 기존 Event에 Update append**됨 E2E / 약신호는 possible_link로 보류(자동병합 안 함) 테스트 / heat 단조성 테스트.

> ┌─ 심화 보강 (orchestrator #2) — 해상도를 시간창 1축이 아니라 merge_score 3축으로 ─
> │ **문제:** `cross_source_dedup.py:164-180`은 클러스터 멤버 쌍의 강신호 존재 여부를 `has_strong`(line 165-169)이라는 **1비트로 양자화**한 뒤 `CONF_DUPLICATE`/`CONF_POSSIBLE`만 산출한다. 약신호 경로의 reason은 `title_date_similarity`(line 170)인데, 그 판정에 쓰인 **Jaccard 실측값(연속값)이 폐기**된다 — 해상도가 시간창·제목유사도 1축에 갇힌다.
> │ **보강:** `EVENT_MERGE_TIME_WINDOW_HOURS`(§23) 단일 시간창 대신 **merge_score 3축**으로 승격: `merge_score = entity_overlap × domain_distance × signal_strength`.
> │   - `entity_overlap` = primary_entity_ids 교집합/합집합(앵커 매칭 후, §3).
> │   - `domain_distance` = 두 후보 domains의 통제어휘 거리(같은 통제어휘일수록 병합 우호).
> │   - `signal_strength` = dedup이 폐기한 **Jaccard 연속값**을 보존해 입력(1비트가 아니라 [0,1]).
> │ **착지점:** dedup 출력을 `(cluster_id, confidence, jaccard_raw)`로 확장(비파괴 추가 필드) → event_resolver가 merge_score로 APPEND/HOLD 임계 θ를 도메인별 튜닝(UNKNOWN, §0 인덱스 §6-3/4).
> │ **위험:** R-FalseMerge — 아래 #1 박스 참조.
> └────────────────────────────────────────────────────────

> ┌─ 심화 보강 (orchestrator #3) — heat을 명시적 half-life·엔트로피·rate clamp로 ─
> │ ① **half-life 감쇠:** §2.4의 `exp(-Δt/half_life)`를 **명시적**으로 — 단조 누적이면 오래된 사건이 영원히 hot으로 남아 랭킹·폴링 예산을 잠식한다. `status`(active→dormant→closed) 자동 전이를 heat 임계와 연동.
> │ ② **corroboration = role 다양성 엔트로피:** "출처 *수*"가 아니라 **source_role(7종) 분포의 섀넌 엔트로피**. OFFICIAL_RECORD+ARTICLE_BODY 2종 > COMMUNITY_EARLY_SIGNAL ×5(에코챔버 방지). `EVENT_SCHEMA.md` Part 2 §heat와 일치.
> │ ③ **폴링 주기 rate-limit 하한 clamp:** 차등 주기 `base_interval/(1 + heat·k)`는 hot 사건을 더 자주 폴링하나, **소스별 rate-limit 하한(gdelt 60s 등)은 절대 clamp**한다 — 우회·rate 위반은 불변 금지(어떤 heat에서도 하한을 못 뚫는다).
> │ **위험:** R-DiscoveryCostStarvation(cold triage 예산), R-LLMCollectBoundary(rate 준수).
> └────────────────────────────────────────────────────────

> ┌─ 심화 보강 (adversarial #1) — Union-Find transitive 오염(R-FalseMerge) ─
> │ **문제:** Union-Find는 추이적 병합(A~B, B~C ⇒ A~C)이라, 약한 연결 하나가 **무관한 두 사건을 영속 Event로 오염**시킬 수 있다(transitive false merge). `has_strong`이 클러스터 전체를 duplicate로 승격(line 165-169)하면, 강신호 쌍 1개가 약신호로 끌려온 멤버까지 자동 APPEND로 흡수한다.
> │ **완화(clique 게이트):** event_resolver는 cluster를 **무조건 신뢰하지 않고**, APPEND 전 "강신호가 cluster 내 **clique(상호 강결합)**를 이루는가"를 검문한다. clique 미달 멤버는 `event_links(possible)`로 분리 보류(자동 병합 금지). 영속 Event 오염은 append-only 가역성(event_links status=rejected)으로 되돌릴 수 있다.
> │ **승격:** R-Dedup LOW → **R-FalseMerge MEDIUM**(`_RISK/RISK_REGISTER.md`).
> └────────────────────────────────────────────────────────

---

## §3. [자산②] Entity Registry (URL → 엔티티)

SESSION_CONCEPT §12. 엔티티를 카드의 문자열 필드가 아니라 **1급 영속 객체**로. (테이블 상세 = `2_ROADMAP/17` + `EVENT_SCHEMA.md` Part 2 §Entity.)

### §3.1 `entities` 테이블 (신규) — 핵심 컬럼
`id`(UUID PK) · `canonical_name`("Anthropic") · `entity_type`(company/gov_agency/product/person/place/regulation) · `aliases` JSONB · `external_ids` JSONB(wikidata QID/공식 도메인 = 앵커) · `domains` JSONB · `official_sources` JSONB(Authority 노드[], §7) · `status`(active/candidate/merged).
인덱스: `canonical_name`, `entity_type`, `aliases` GIN, `external_ids` GIN.

### §3.2 엔티티 해소(resolution) — 점진 전략
1. **추출 재사용:** `agents/nodes/baselines.py`의 regex NER을 레지스트리 **입력**으로(추출 로직 신규 0).
2. **앵커 우선 매칭:** external_ids(공식 도메인/QID)가 있으면 그것으로 동일성 판정(고신뢰).
3. **별칭 테이블:** 앵커 없으면 aliases 정규화 매칭. 모호하면 **candidate**로 적재(자동 병합 안 함).
4. **2층:** 상위 통제 엔티티(검증된 주요 행위자) vs 하위 free-form 멘션(tags).

### §3.3 Event/domain 연결
- `events.primary_entity_ids` ↔ `entities.id`. 엔티티가 사건·도메인·증거의 **연결 노드**.
- "호르무즈" 엔티티(place)가 energy·shipping·finance 도메인·관련 회사 엔티티와 엮여 요구 3의 "범용 다분야 연결"을 데이터로 실현.

**수용 기준(§3):** NER → entities upsert(별칭 병합) / 앵커 동일성 매칭 / candidate 자동병합 금지 / event ↔ entity 연결 조회.

---

## §4. [요구3] 열린 domains + free-form tags 2층 분류

DIRECTION §4.3. 닫힌 8섹터(`baselines.py:47-63` `_SECTOR_KEYWORDS`)를 2층으로 확장.

### §4.1 2층 구조
- **상위 `domains` (통제 어휘, ~20개 안정):** 기존 8 `energy, finance, defense, technology, health, politics, commodities, transport` + 신규 12 `insurance, diplomacy, shipping, agriculture, labor, climate, telecom, regulation, semiconductor, biotech, cybersecurity, media`. 필터·네비·섹터 페이지의 축. 닫힌(통제) 집합이라 UX 일관성. (카탈로그 권위 = `EVENT_SCHEMA.md` Part 2 §domains.)
- **하위 `tags` (free-form 무제한):** 엔티티·키워드. 정밀 연관·검색용. 무제한이라 표현력.

### §4.2 매핑 진화 (`sector_mapping.py` → `domain_mapping.py`)
- **baseline 단계:** 키워드 사전 확장 + `general` 폴백 보존(현행 비파괴). domains는 통제어휘 매칭, tags는 NER 엔티티.
- **LLM 단계(걸음1 결합):** LLM이 사건을 읽고 domains(통제어휘 중 N개) + tags(자유) 동적 부여. 닫힌 enum 강제 아님 → 새 도메인 필요 시 통제어휘에 추가(거버넌스 ADR).
- **시계열 결합:** Update마다 `added_domains` 누적 → 호르무즈가 energy→finance→insurance→diplomacy로 번지는 흐름이 데이터로 남음(§2.2 event_updates.added_domains).

### §4.3 트레이드오프·해결
- 열린 분류의 일관성 저하 → **2층(통제 상위 + 자유 하위)** 으로 일관성과 표현력 동시 확보.
- 통제어휘 확장 거버넌스 → 도메인 추가는 `_DECISIONS` ADR로 기록(임의 증식 방지).

**수용 기준(§4):** baseline domains/tags 분리 산출 / general 폴백 유지 / Update added_domains 누적 / 기존 sector 소비처(themes/sectors API) 비파괴.

---

## §5. [자산⑤] LLM Expansion Router (Query Planning + tiered + budget)

SESSION_CONCEPT §2/§3/§8. 가장 저렴(스텁 존재). DIRECTION §2.1 LAYER P/G/F 경계 준수(ADR#14). tiered router 상세 = `2_ROADMAP/06`.

### §5.1 재사용 토대
- `ingestion/pipeline/query_generator.py:17` `generate()` 스텁(`NotImplementedError`, line 29).
- `ingestion/pipeline/search_enrichment_collector.py:26` `enrich()` 스텁.
- provider 6종(`source_registry.yaml`: google_programmable_search/serper/tavily/exa/naver×2).
- `ingestion/agents/llm_judge.py` `create_judge_client()`(LLM 호출 인프라 재사용 — 신규 0).

### §5.2 `query_generator.generate()` 구현 (LAYER P)
```text
generate(event_candidate) -> list[ExpansionQuery]:
  입력:  title, entities[], domains[], event_id
  LLM:   create_judge_client() 재사용. 시스템 프롬프트="사건 확장 검색어 생성기"
  출력:  최대 K개 쿼리 (dedup 후). 각 쿼리에 의도 라벨(official/community/news/regulation)
  off:   LLM_PROVIDER 빈값 → entities 기반 규칙 쿼리(결정론 폴백, 현행 보존)
```
- 무한확장 금지: 한 사건당 쿼리 K개 상한, 확장 홉 깊이 1~2 고정.

### §5.3 `expansion_router.py` 신규 (LAYER G + F)
```text
route(queries: list[ExpansionQuery], budget: ExpansionBudget) -> list[RawEvent]:
  for q in queries (예산 내에서):
     tier1 무료(google_programmable_search) 실행
     hit 부족 시 tier2 유료(tavily/exa/serper)  ── budget guard 차감
     결과 URL → 정책 게이트(robots/ToS/SSRF allowlist/POLICY_EXCLUDED) 통과분만
     통과분 → 기존 수집 파이프라인 → raw_events (재유입)
  audit_trace: 생성쿼리·실행tier·비용·차단사유 전량 로깅
```
- **`ExpansionBudget`:** per-event 상한 + 월 상한(설정값). 초과 시 graceful 중단(예외 아님).
- **Change Detection 결합(§7):** 이미 본 URL(content_hash 동일)은 재수집 skip(비용 0).

### §5.4 트레이드오프·해결 (SESSION_CONCEPT §18 T1)
- 비용 폭주 → budget guard + 무료 우선 tiered + Change Detection skip + 쿼리 K개 상한.
- 비결정성 → off 결정론 폴백 + audit trace(재현·감사).
- noise/법무 → 확장 결과도 dedup·evidence·정책 게이트 통과(LAYER G).

**수용 기준(§5):** off 시 1,517 green / candidate→확장쿼리→tiered검색→raw_events 1건 E2E / 예산초과 graceful 중단 / 정책 제외 URL 차단 / audit trace 적재.

> ┌─ 심화 보강 (adversarial #6) — generate_batch fail-all → 후보단위 폴백 격리 ─
> │ **문제:** `query_generator.py:31-41` `generate_batch`는 line 38-41 루프에서 후보마다 `self.generate(c)`(line 40)를 호출하는데, `generate`가 line 29에서 `NotImplementedError`(또는 미래의 LLM 호출 실패)를 raise하면 **1개 후보의 실패가 batch 전체를 중단**시킨다(fail-all). 즉 한 사건의 확장 실패가 같은 배치의 다른 사건 확장까지 모두 죽인다.
> │ **보강(후보단위 격리):** `generate_batch`는 후보별 try/except로 **격리** — 실패 후보는 `result[key] = deterministic_fallback(c)`(entities 기반 규칙 쿼리, §5.2 off 경로)로 대체하고 `audit_trace`에 `"generate_failed", candidate_key, fallback_used` 기록. 한 후보의 실패가 다른 후보의 확장을 막지 않는다(graceful degrade).
> │ **위험:** R-ExpansionPartialFailure(LOW-MEDIUM, `_RISK/RISK_REGISTER.md`).
> └────────────────────────────────────────────────────────

---

## §6. [요구1] Source Routing 배선 (supervisor llm_propose)

SESSION_CONCEPT §9. 게이트 이미 존재 → 콜백만 연결. P/G/F 경계 = `2_ROADMAP/11`.

### §6.1 재사용 토대
- `ingestion/orchestration/source_supervisor.py:69-108` `decide(llm_propose=..., llm_available=False)`.
- `_ALLOWED_BY_LAYER`(허용 전략) + `_UNSAFE_STRATEGIES`(proxy/captcha/robots_ignore 등 차단) — **구현됨**.
- `source_role.py` 7 roles(라우팅 타깃).

### §6.2 배선
```text
llm_propose 콜백 = create_judge_client() 래퍼 (llm_judge 재사용)
llm_available = (LLM_PROVIDER != "")   # 빈값=off=현행 결정론 100% 보존
decide() 내부:
  결정론 기본 전략 산출 (현행)
  if llm_available: LLM 제안 받음 → _UNSAFE_STRATEGIES/allowed 게이트 검문 → 통과분만 채택
  audit_trace: 제안·채택·거부 구조화 로깅
사건유형 → role 매핑 테이블(신규, 명시적):
  service_outage -> [OFFICIAL_RECORD(status), COMMUNITY_EARLY_SIGNAL]
  regulation     -> [OFFICIAL_RECORD(gov)]
  tech_launch    -> [OFFICIAL_RECORD(blog), ARTICLE_BODY]
  (LLM은 이 매핑을 보강 제안만, 결정론 테이블이 기본 — 하이브리드)
```

**수용 기준(§6):** off 시 기존 supervisor 테스트 green / on 시 unsafe 제안 차단(test_llm_agent_strategy_hints 확장) / 사건유형→role 매핑 단위테스트 / audit trace.

> ┌─ 심화 보강 (orchestrator #5) — audit_trace를 decision replay record로 승격 ─
> │ **문제:** `source_supervisor.py:104`는 허용 밖 LLM 제안을 **"조용히 무시"**(주석 그대로: "허용 밖 제안은 조용히 무시 → deterministic fallback 유지")한다 — 반환값·로그에 *무기록*(침묵 폐기). 따라서 "LLM이 무엇을 제안했고 왜 거부됐는가"가 사후 재현 불가하고, R-LLMCollectBoundary의 완화책(audit)이 현재 미구현(TODO)이다.
> │ **보강(replay record):** audit_trace의 각 엔트리를 **결정 재현 레코드**로 — 단순 로그가 아니라 `{input_fingerprint(관측실패+allowed 집합 해시), llm_proposed, accepted/rejected, reason, deterministic_fallback_would_be(LLM 없었으면 무엇이었나)}`. 이로써 ① 거부된 unsafe 제안도 *증거로 남고*(침묵 폐기 종결), ② 동일 input_fingerprint로 결정을 **replay**해 재현성 검증(LLM 출력은 비결정이나 게이트 결정은 결정론), ③ deterministic_fallback_would_be가 "LLM이 실제로 다른 결정을 유도했는가"를 감사.
> │ **착지점:** `source_supervisor.decide`가 `SourceSupervisorDecision`에 audit 필드 추가(비파괴), line 104 침묵 경로를 명시적 reject 기록으로 교체.
> │ **위험:** R-LLMCollectBoundary(audit TODO), R-PromptInjection(반복 unsafe 제안 카운터·escalation).
> └────────────────────────────────────────────────────────

---

## §7. [자산③] Authority Discovery 통합 파이프라인

SESSION_CONCEPT §11~§16. 중기(요구 1·6). `Entity Registry → Authority Source Finder → Sitemap → Change Detection`. Entity 앵커로 안전 확보. **상세 설계·엣지케이스·승인 큐는 형제 문서 `2_ROADMAP/17`(등재됨)가 권위**이고, 본 절은 Event/Expansion 결합 관점만 요약한다.

### §7.1 `authority_source_graph` (엔티티 → 공식 소스)
```text
discover(entity) -> list[AuthoritySource]:
  앵커 도메인(external_ids/공식 도메인)에서 출발
  표준 경로 탐색: /sitemap.xml /rss.xml /atom.xml /feed.xml /blog /docs /legal /status /changelog
  각 후보: 정책 게이트(robots/ToS/rate) 통과 → candidate AuthoritySource
  활성화: 초기엔 사람 승인 큐(자동 활성 금지) → 점진 자동화
```

### §7.2 `sitemap_discovery` (자동 소스 도출)
- sitemap/feed에서 최근·관련 섹션(news/blog/changelog) lastmod 기반 신규 URL만 도출.
- robots 준수·rate gate(기존 supervisor 안전전략 재사용). 대형 sitemap은 부분 파싱.
- 폴백: sitemap 없음 → feed → 없음 → 등록 제외(무리한 발견 금지).

### §7.3 `change_detector` (변화 감지 — T1 비용 지렛대)
```text
check(source_url, last_state) -> ChangeVerdict:
  ETag 비교 → Last-Modified 비교 → (둘 다 불가) 본문추출 후 정규화 content_hash 비교
  변화 없음 → SKIP (수집·LLM 호출 0)        # 비용 제어의 근본
  변화 있음 → 수집 트리거 → LLM Triage
  정규화 해시 = article_body_extractor 결과 기준(광고/타임스탬프 noise 제외)
차등 주기: heat 높은 엔티티/소스 자주, 나머지 드물게(rate 하한 clamp, §2.4 #3)
```

### §7.4 트레이드오프·해결
- 가짜 권위 → Entity 앵커 출발 + 정책 게이트 상속.
- 발견 폭주 → 사람 승인 큐 + heat 우선순위 백프레셔.
- stale → Change Detection으로 변화만 처리, 부분 파싱.

**수용 기준(§7):** 앵커 엔티티 1개 → sitemap/feed 후보 도출(정책 통과분만) / change_detector "변화 없음→skip" 비용 0 검증 / candidate 자동 활성 금지(승인 큐) / robots 위반 0.

> ┌─ 심화 보강 (orchestrator #4) — S11(Change Detection) 자기모순 해소: read-only 절반을 S1.5로 ─
> │ **문제:** 단계 계획에서 Change Detection을 후순위(S7)로 두면 **자기모순**이 생긴다 — Change Detection은 *비용 지렛대*인데, 그것을 S2~S6(Resolution·Expansion·Routing)보다 **나중에** 켜면 그 사이 LLM 호출이 무방비로 폭주한다. 비용 제어 장치를 비용 발생 *뒤에* 켜는 순서다.
> │ **보강(S1.5 동시 착수):** Change Detection의 **read-only 절반**(ETag/Last-Modified/norm_hash → SKIP verdict 산출, 발견 결선은 제외)을 **S1.5로 분리해 S1과 동시 착수**한다. 즉 `seen_content_hash` skip 인프라를 **선행 구축**해 S5 Expansion이 "이미 본 URL"을 곧장 skip(비용 0)할 수 있게 한다. 발견 결합(authority→sitemap→자동 활성)이 필요한 *write* 절반만 S7/S10으로 남긴다.
> │ **착지점:** `2_ROADMAP/00_ROADMAP_INDEX §4`의 임계경로에 이미 "S1.5 Change Detection 동시 착수 권장"으로 반영됨 — 본 문서 §11 표의 S7을 read-only(S1.5)/write(S7)로 분할.
> │ **위험:** R-DiscoveryCostStarvation(cold triage 예산).
> └────────────────────────────────────────────────────────

---

## §8. [자산④] Evidence Graph (evidence JSONB 승격 + 관계)

SESSION_CONCEPT §10. 평면 URL 리스트 → 구조화 증거 노드(경량 JSONB부터, T4). (EvidenceNode DDL = `EVENT_SCHEMA.md` Part 2 §EvidenceNode.)

### §8.1 evidence 노드 구조 (기존 `evidence: list[str]` → `list[EvidenceNode]`)
```text
EvidenceNode:
  url: str
  source_type: official | community | news | government | structured | historical   # source_role 매핑
  role: str             # 기존 7 roles에서 도출 (신규 분류 0)
  confidence: float      # 0~1
  relation: supports | refutes | duplicates | context     # 사건↔증거 관계
  observed_at: datetime
```
- **비파괴:** 문자열 리스트도 계속 허용(degrade), 신규는 구조화. 마이그레이션은 점진.
- **role 재사용:** source_type을 `source_role.py` 7 roles에서 매핑(분류 신규 0).

### §8.2 관계(엣지)는 단계적
- 1단계: "사건 ↔ 증거"만(JSONB 노드).
- 2단계: "증거 ↔ 증거(지지/반박)"는 **Agent Debate Layer(§9)** 가 생성 — 에이전트 논쟁이 곧 증거 관계의 자연어 표면.
- **GraphRAG 조건부:** `2_ROADMAP/09` 원칙 — <1000 엔티티엔 도입 금지, vector RAG 커버리지 실측 후. 지금은 풀 그래프 DB 도입 안 함(JSONB로 충분).

### §8.3 B2B/광고 신뢰 가치 (ADR#15, `2_ROADMAP/13`)
- 모든 주장에 증거 노드 → 클릭으로 원본 도달 → 인용 가능. 이것이 요약+증거+UGC가 "전문 재배포가 아닌 파생 콘텐츠"로서 광고 면적이 되는 근거. **단 evidence graph 직접 판매는 불변원칙상 닫힌 길**(구독·전문·투자조언 저촉) — 트래픽 증폭만(ADR#15 BI 인사이트 ③).

**수용 기준(§8):** evidence 구조화 노드 생성·조회 / 문자열 evidence 비파괴 호환 / source_type↔role 매핑 / relation 태깅.

---

## §9. [요구2] Agent Debate Layer (comment 확장 + 논쟁 그래프)

DIRECTION §3.2/§3.3, ADR#15. 커뮤니티 (b)층(성장). 현재 `backend/app/models/comment.py` author 1칸 + `ai_replies.py` mock 스텁(debate 컬럼 0건 — GroundTruth). (Comment 확장 DDL = `EVENT_SCHEMA.md` Part 2 §Comment 확장.)

### §9.1 Comment 모델 확장 (비파괴 additive)
`author_type` VARCHAR(8)('user'/'agent', 기본 'user' → 기존 비파괴) · `agent_persona` VARCHAR(64) NULL("energy-analyst"/"skeptic"/"geopolitics-desk") · `reply_to` UUID NULL(부모 comment 스레드) · `stance` VARCHAR(12) NULL(claim/counter/evidence/question) · `evidence_refs` JSONB(발화 근거 EvidenceNode[]).

### §9.2 에이전트 페르소나·소환
- 사건 domains에 따라 관련 분야 에이전트 자동 소환(energy 사건 → energy-analyst + skeptic).
- 페르소나 = LLM 시스템 프롬프트 + 해당 도메인 evidence 구독. `agents/` 측 논쟁 그래프(신규).

### §9.3 논쟁 프로토콜 (claim → counter → evidence → 수렴/미수렴)
```text
debate(event) -> thread:
  analyst가 claim (evidence_refs 필수)
  skeptic가 counter (반박 + evidence_refs)
  상호 evidence 제시 → 유저 끼어들기 허용(질문/반박)
  수렴 태그(합의) 또는 미수렴 태그(쟁점 표면화)
  → 이 과정이 §8 "증거↔증거 관계"를 자연어로 생성
```

### §9.4 안전 가드 (불변 원칙 → 댓글 레이어 확장)
- **투자조언 차단:** 매수/매도/가격판단 톤 필터(CLAUDE.md 원칙1). fail-closed.
- **근거 필수:** 에이전트 claim/counter는 evidence_refs 없으면 게시 불가.
- **injection 방어:** 외부 텍스트가 페르소나를 조종 못 하게(EvidenceGate 확장, R-PromptInjection).
- **UGC = 우리 자산:** 전문 재배포 아님(ADR#15) → 광고 면적 정당.

**수용 기준(§9):** author_type/persona/reply_to/stance 마이그레이션(기존 댓글 비파괴) / 논쟁 스레드 claim→counter→evidence E2E / 투자조언 표현 차단 회귀테스트 / evidence 없는 에이전트 발화 차단.

---

## §10. [요구1 P-3] SLM Body Fallback (통신서버 추론)

DIRECTION §2.3 P-3. MASTER_OVERVIEW "통신서버에 적절 size SLM". **최후 폴백 한정**(비용 제어). 인프라 상세 = `2_ROADMAP/17`.

### §10.1 위치
- `article_body_extractor.py:76-101` 캐스케이드(trafilatura→readability→DOM)가 **모두 실패(200자 미만) 한 경우에만** 호출. 1차 아님.

### §10.2 `slm_body_fallback.py` (신규)
```text
extract(rendered_dom, url) -> body | None:
  통신서버(별도 추론 서버)의 7B급 SLM 호출
  입력: rendered DOM(추출 난항 페이지)
  출력: 본문 영역 텍스트 (실패 시 None → 기존대로 폴백 종료)
  메트릭: 폴백 호출률, 회수율(실패분 중 SLM 성공), 비용
```
- **우회 없음:** SLM은 본문 "식별"만, fetch는 기존 결정론 경로(robots/rate 준수).
- **전문 저장 금지 유지:** 추출 본문도 정책대로(요약/summary만 영속, 전문 미저장).

### §10.3 트레이드오프·해결
- 인프라/지연 비용 → 캐스케이드 실패분 한정(분모의 일부) + 통신서버 분리(앱 부하 격리).

**수용 기준(§10):** 캐스케이드 실패 케이스에서만 호출(1차 호출 0) / 회수율·비용 대시보드 / 실패 시 graceful None.

---

## §11. 단계 계획 (Phase·의존성·순서 S1~S11)

SESSION_CONCEPT §19 위상 정렬 반영. **각 단계는 "기존 1,517 green 유지"를 무조건 acceptance로 가진다.**

| 순서 | 단계 | 내용 | 의존 | 요구 | 위험 |
|---|---|---|---|---|---|
| S1 | Event 토대 | §1 events/event_updates/카드 event_id(additive) | — | 3 | 중 |
| **S1.5** | **Change Detection (read-only)** | **§7.3 ETag/Last-Modified/norm_hash→SKIP verdict + seen_content_hash skip 인프라** | **S1 동시** | **1** | **중** |
| S2 | Event Resolution | §2 dedup→Event append 라우팅, heat, FSD, merge_score 3축 | S1 | 3 | 중상 |
| S3 | domains/tags 2층 | §4 sector→domain_mapping, baseline 보존 | S1 | 3 | 중 |
| S4 | Entity Registry | §3 entities, NER 재사용, 앵커 매칭 | S1 | 3·6 | 중상 |
| S5 | LLM Expansion Router | §5 query_generator+expansion_router+budget | (독립) | 1 | 중상 |
| S6 | Source Routing | §6 supervisor llm_propose 배선 + replay audit | S5 인접 | 1 | 중 |
| S7 | Change Detection (write) | §7.1/7.2 발견 결선(authority→sitemap→자동 활성) | S5·S4 | 1·6 | 중 |
| S8 | Evidence Graph | §8 evidence JSONB 승격 | S1·S4 | 2·3 | 중 |
| S9 | Agent Debate | §9 comment 확장 + 논쟁 그래프 | S8 | 2 | 중상 |
| S10 | Authority Discovery | §7.1/7.2 graph+sitemap(승인 큐) | S4·S7 | 6 | 상 |
| S11 | SLM Body Fallback | §10 통신서버 SLM | (독립, 고도화) | 1 | 상(인프라) |

> **S11 자기모순 해소(orchestrator #4):** 원안은 Change Detection이 S7 단일이었으나, **read-only 절반(S1.5)을 S1과 동시 착수**해 비용 지렛대를 S2~S6 폭주 *전에* 켠다. write 절반(발견 결선)만 S7/S10에 남긴다. `2_ROADMAP/00_ROADMAP_INDEX §4` 임계경로와 일치.

**권장 착수:** S1 → S1.5(동시) → S5(P-1 라우팅 저렴) → S2/S3 → S4 → S7 → S8 → S9 → S10 → S11.
**이유:** Event 토대(S1) 먼저 고정해야 걸음1(카드 AI 품질)이 폐기될 스키마 위에 안 쌓인다(ADR#16).

---

## §12. 마이그레이션 안전 (비파괴 전략)

- **모든 신규 컬럼 nullable 시작 / 신규 테이블 additive.** 기존 쓰기 경로 무수정.
- **event_cards 의미 전환은 데이터 이동 없음** — event_id 추가만, NULL 허용(기존 카드 = 단독 Event).
- **공개 API 동작 보존** — `/api/events`는 현행 유지하다 점진적으로 events 경유 전환(피처 플래그).
- **`.env` 비파괴** — 신규 설정(heat 가중치/budget 상한/LLM_PROVIDER)은 "빈값=코드 기본" 계약 준수(`config.py` model_validator가 빈 문자열 제거 — ADR#12). `.env`는 열람/수정/커밋 안 함, 필요 시 `.env.example` diff 제안만.
- **롤백:** 각 단계 마이그레이션은 alembic downgrade 제공(§22).
- **이중쓰기 정합성(R-EventModelMigration):** §1 심화 박스의 불변식 테스트를 마이그레이션과 함께 병기 — "1517 green"만으로는 신규 이중쓰기 정합성을 보장하지 않는다.

---

## §13. 테스트·수용 매트릭스

| 단계 | 단위 | 통합/E2E | 회귀(불변) |
|---|---|---|---|
| S1 | events/updates CRUD | — | 1,517 green, event_id NULL 카드 조회, **이중쓰기 정합성** |
| S1.5 | change verdict(read-only) | seen_hash skip(비용 0) | rate/robots 위반 0 |
| S2 | 라우팅 분기, heat 단조, merge_score 3축 | 2번째 보도→append(새카드 아님), clique 게이트 | dedup 기존 테스트 |
| S3 | domain/tag 분리, general 폴백 | Update added_domains 누적 | themes/sectors API 비파괴 |
| S4 | NER upsert, 앵커 매칭, candidate 보류 | event↔entity 연결 | — |
| S5 | off 폴백, K상한, **batch 후보단위 격리** | candidate→검색→raw_events | off 시 1,517 green |
| S6 | unsafe 차단, 유형→role, **replay record** | — | supervisor 기존 테스트 |
| S7 | change verdict 분기(write) | 변화없음→skip(비용0) | rate/robots 위반 0 |
| S8 | evidence 노드, source_type↔role | — | 문자열 evidence 호환 |
| S9 | stance/persona, 투자조언 차단 | claim→counter→evidence | 기존 댓글 비파괴 |
| S10 | sitemap 파싱, 승인큐 | 앵커→후보 도출 | robots 준수 |
| S11 | 캐스케이드 실패 시만 호출 | 회수율 측정 | 1차 호출 0, 전문 미저장 |

**전 단계 공통 게이트:** secret scan PASS / git diff clean(`.env` 무변경) / 투자조언 표현 0 / 우회 0.

---

## §14. 비용·운영 가드 종합

| 가드 | 적용 | 메커니즘 |
|---|---|---|
| LLM 호출 비용 | S5·S6·S7·S9 | budget guard(per-event/월) + **Change Detection skip** + 무료 우선 tiered + off 폴백 |
| 발견 폭주 | S7·S10 | heat 우선순위 백프레셔 + 사람 승인 큐 + 부분 sitemap 파싱 |
| 병합 오류 | S2·S4 | 강신호 자동·약신호 보류 + append-only 가역성 + 논쟁 검수 + **clique 게이트** |
| 그래프 비용 | S8 | 경량 JSONB + 관계 단계적 + GraphRAG 조건부(<1000 금지, 09) |
| 안전·법무 | 전 단계 | 우회 금지·전문 미저장·투자조언 필터·정책 게이트 상속·SSRF allowlist·injection 방어 |
| 재현성 | 전 단계 | LLM은 LAYER P 한정, 제어흐름은 결정론, **replay record(audit)**, off 토글 |

> **마무리:** 본 스펙은 5대 핵심 자산을, **기존 부품(dedup·NER·roles·content_hash·provider·llm_judge)을 영속 객체(Event/Entity)와 발견 루프로 승격**하는 비파괴 단계 계획으로 구현한다. 요구 1(LLM 수집 관여, P/G/F 경계)·요구 2(커뮤니티·광고·논쟁)·요구 3(사건=진화하는 다분야 시계열 객체)은 각각 S5~7·S9·S1~4/S8로 토대에 새겨진다. 다섯 트레이드오프는 다섯 지렛대(Change Detection·Event 2층·Entity 앵커·경량 JSONB·점진 결선)로 해소되며, 모든 단계는 "기존 1,517 green + 우회 0 + 비밀 0"을 무조건 통과 기준으로 한다. 타협 없이, 우회 없이.

---

# PART B — 심화: 데이터 예시 · end-to-end 플로우 · 엣지케이스 · API 계약

§1~§14의 스키마/시그니처를 **실제 JSON·동작 플로우·실패 경로**로 내려, 곧장 구현 가능한 수준으로 고정한다.

## §15. 데이터 예시 (실제 JSON)

### §15.1 Event + EventUpdate (호르무즈, §1·§2)
```json
// events 1행
{
  "id": "evt-7a3f...",
  "canonical_title": "호르무즈 해협 긴장 고조",
  "status": "active",
  "first_seen_at": "2026-06-18T08:00:00Z",
  "last_update_at": "2026-06-20T09:00:00Z",
  "heat": 0.61,
  "domains": ["defense", "energy", "finance", "diplomacy", "insurance", "shipping"],
  "tags": ["tanker-seizure", "oil-price", "lloyds"],
  "primary_entity_ids": ["ent-hormuz", "ent-iran", "ent-usnavy"],
  "snapshot_card_id": "card-v4-9b2c..."
}
```
```json
// event_updates (append-only, 위 Event에 4건)
[
 {"id":"upd-1","event_id":"evt-7a3f...","observed_at":"2026-06-18T08:00:00Z",
  "delta_summary":"유조선 1척 나포","added_domains":["defense","energy"],
  "evidence":[{"url":"reuters.com/...","source_type":"news","relation":"supports","confidence":0.85}],
  "source_refs":["raw-001","raw-002"],"heat_delta":0.40},
 {"id":"upd-2","event_id":"evt-7a3f...","observed_at":"2026-06-18T11:00:00Z",
  "delta_summary":"유가 +4% 반응","added_domains":["finance"],
  "evidence":[{"url":"finnhub/...","source_type":"structured","relation":"supports","confidence":0.90}],
  "source_refs":["raw-014"],"heat_delta":0.21},
 {"id":"upd-3","event_id":"evt-7a3f...","observed_at":"2026-06-19T10:00:00Z",
  "delta_summary":"관련국 외교 성명","added_domains":["diplomacy"],"heat_delta":0.10,
  "evidence":[{"url":"gov/...","source_type":"government","relation":"supports","confidence":0.92}],
  "source_refs":["raw-031"]},
 {"id":"upd-4","event_id":"evt-7a3f...","observed_at":"2026-06-20T09:00:00Z",
  "delta_summary":"보험료 인상 보도","added_domains":["insurance","shipping"],"heat_delta":0.08,
  "evidence":[{"url":"lloyds/...","source_type":"news","relation":"supports","confidence":0.80}],
  "source_refs":["raw-052"]}
]
```

### §15.2 Entity (§3)
```json
{
  "id": "ent-anthropic",
  "canonical_name": "Anthropic",
  "entity_type": "company",
  "aliases": ["앤트로픽", "Anthropic PBC", "anthropic"],
  "external_ids": {"domain": "anthropic.com", "wikidata": "Q..."},
  "domains": ["technology"],
  "official_sources": [
    {"label":"blog","url":"anthropic.com/news","discovered_via":"sitemap","status":"active"},
    {"label":"status","url":"status.anthropic.com","discovered_via":"feed","status":"candidate"}
  ],
  "status": "active"
}
```

### §15.3 EvidenceNode (§8)
```json
{
  "url": "https://openai.com/index/gpt-6",
  "source_type": "official",
  "role": "OFFICIAL_RECORD",
  "confidence": 0.95,
  "relation": "supports",
  "observed_at": "2026-06-20T08:00:00Z"
}
```

### §15.4 Comment (에이전트 논쟁, §9)
```json
[
 {"id":"c1","event_id":"evt-7a3f...","author":"energy-analyst","author_type":"agent",
  "agent_persona":"energy-analyst","reply_to":null,"stance":"claim",
  "body":"유가 반응은 공급 차질 우려가 과대평가됐을 수 있습니다.",
  "evidence_refs":[{"url":"finnhub/...","relation":"supports"},{"url":"iea/...","relation":"context"}]},
 {"id":"c2","event_id":"evt-7a3f...","author":"skeptic","author_type":"agent",
  "agent_persona":"skeptic","reply_to":"c1","stance":"counter",
  "body":"과거 봉쇄 위협 시 +4%는 평균 이하였고, 이번엔 실제 나포까지 갔습니다.",
  "evidence_refs":[{"url":"internal://event/evt-past-1","relation":"refutes"}]},
 {"id":"c3","event_id":"evt-7a3f...","author":"user-8821","author_type":"user",
  "agent_persona":null,"reply_to":"c1","stance":"question",
  "body":"이번엔 실제 나포까지 갔는데 그래도 과대평가인가요?","evidence_refs":[]}
]
```
> 주의: 에이전트 발화(c1,c2)는 `evidence_refs` 비면 **게시 거부**(§9.4). 유저(c3)는 면제.

## §16. End-to-End 플로우 — "호르무즈" 신규 토대 통과 (전체)

```
[1] 수집(APPLIED)        Reuters RSS → raw_events(raw-001..) status=collected
[2] Triage(S5/§6)        llm_quality_judge: candidate{type=geopolitical_incident, conf=0.55}
                         publish 게이트: 본문 있음 + 단일이지만 official급 → published 후보
[3] Resolution(S2/§2)    cross_source_dedup: cluster_id=C1 (+ jaccard_raw 보존, merge_score)
                         event_resolver: C1 미매핑 → Event evt-7a3f 신규 생성(FSD=08:00)
                         cluster_event_map[C1]=evt-7a3f
[4] domains(S3/§4)       domain_mapping: domains=[defense,energy] tags=[tanker-seizure]
[5] Entity(S4/§3)        NER → entities upsert: 호르무즈(place)/이란(gov)/US Navy(org)
                         event.primary_entity_ids 연결
[6] Evidence(S8/§8)      evidence 노드화: [{reuters, news, supports, 0.85}]
[7] 카드 렌더            FinalEventCard v1 생성 event_id=evt-7a3f, snapshot_card_id 갱신
[8] 11:00 유가 신호      finnhub raw-014 → [3] cross_source_dedup 같은 cluster
                         → event_resolver: clique 게이트 통과 → 기존 evt-7a3f에 Update#2 APPEND (새 카드 아님!)
                         → added_domains=[finance], heat 0.40→0.61, 카드 v2 갱신
[9] 확장(S5/§5, 선택)    heat 상승 + 불확실 → query_generator 확장쿼리 → expansion_router
                         (budget guard, seen_hash skip) → 추가 출처 raw_events 재유입 → [3] 루프
[10] 논쟁(S9/§9)         domains=[energy,finance] → energy-analyst+skeptic 소환 → 논쟁 스레드
[11] 노출               /api/events: evt-7a3f의 현재 스냅샷 + 타임라인 + 다분야 + 논쟁
                         → 트래픽(체류·재방문) → 광고(요구2, ADR#15)
```

**핵심:** [8]에서 두 번째 신호가 **새 카드가 아니라 기존 Event에 append**된 것이 요구 3의 본질이다. [9]의 확장은 budget·Change Detection 뒤에 있어 비용이 제어된다(요구 1).

## §17. 모듈별 엣지케이스·실패 경로

각 신규 모듈이 **실패할 때 어떻게 동작하는가**(fail-closed 원칙). 실제 발생 가능한 경우만 다룬다(CLAUDE.md: 발생 불가 상황 위한 에러처리 금지).

| 모듈 | 엣지케이스 | 처리(fail-closed/graceful) |
|---|---|---|
| event_resolver(§2) | cluster_id 충돌(두 Event가 같은 cluster 주장) | 더 이른 first_seen Event로 병합, 다른 쪽은 event_links(merged) 기록(가역) |
| event_resolver | 약신호만 있음(possible) / clique 미달 | 자동병합 금지 → event_links(possible) 보류, 고heat이면 논쟁 큐 |
| domain_mapping(§4) | 통제어휘 매칭 0 | `general` 폴백(현행 보존), tags만 채움 |
| entity_resolver(§3) | 앵커 없고 별칭 모호 | status=candidate(자동병합 안 함), 검수 큐 |
| query_generator(§5) | LLM off / 호출 실패 | entities 기반 규칙 쿼리 폴백(결정론, 현행 동작) |
| query_generator | batch 中 1후보 실패 | **후보단위 격리**(deterministic_fallback 대체), audit 기록 — 전체 중단 안 함 |
| expansion_router(§5) | budget 초과 | graceful 중단(예외 아님), audit_trace에 "budget_exceeded" |
| expansion_router | 결과 URL이 POLICY_EXCLUDED | 차단, 차단사유 로깅(수집 안 함) |
| change_detector(§7) | ETag/Last-Modified 둘 다 없음 | 본문 정규화 content_hash 폴백 비교 |
| change_detector | 서버가 거짓 ETag(매번 변함) | 정규화 본문 해시로 false change 억제 |
| authority(§7) | sitemap 없음 | feed(rss/atom) 폴백 → 없으면 등록 제외(무리한 발견 금지) |
| agent_debate(§9) | 에이전트 발화 evidence_refs 빈값 | 게시 거부(fail-closed) |
| agent_debate | 발화에 투자조언 톤 감지 | 차단·톤다운(원칙1) |
| slm_fallback(§10) | SLM 서버 무응답 | None 반환 → 기존 캐스케이드 종료(본문 없음→hold) |

## §18. API 계약 변경 (frontend 영향, 비파괴)

기존 `/api/events`·`/api/events/{id}`·`/api/events/{id}/comments`는 **현행 응답 유지**하되, 신규 필드를 **additive**로 더한다(프런트가 모르면 무시, 깨지지 않음). (계약 권위 = `5_REFERENCE/API_CONTRACT.md` 참조.)

| 엔드포인트 | 현재 | 추가(비파괴) |
|---|---|---|
| `GET /api/events` | 카드 목록 | `event_id`, `heat`, `domains[]` (정렬/필터용) |
| `GET /api/events/{id}` | 카드 1건 | `timeline:[EventUpdate...]`, `entities:[Entity...]`, `evidence:[EvidenceNode...]` |
| `GET /api/domains/{d}` | (sectors API) | domain별 Event 타임라인(heat 정렬) — 호르무즈가 energy·shipping 양쪽 노출 |
| `GET /api/events/{id}/comments` | 댓글 목록 | `author_type`, `agent_persona`, `reply_to`, `stance`, `evidence_refs` |
| `POST /api/events/{id}/debate` | (신규) | 에이전트 논쟁 트리거(domains 기반 페르소나 소환) |

**전환 전략:** 피처 플래그로 events 경유를 점진 활성. 기존 `event_cards` 직접 조회 경로는 플래그 off 시 그대로 동작 → 프런트 마이그레이션과 백엔드 마이그레이션을 분리(독립 배포).

## §19. 운영 메트릭·대시보드 (요구 1·2 가드 가시화)

| 메트릭 | 단계 | 목적 |
|---|---|---|
| LLM 호출 수 / 비용 (per-event, 월) | S5·S6·S9 | budget guard 가시화, 폭주 조기탐지 |
| Change Detection skip 율 | S1.5·S7 | "변화 없음→호출 0" 절감 효과(T1 지렛대 검증) |
| 확장쿼리 수 / tier1·tier2 비율 | S5 | 무료 우선 tiered 효과, 유료 의존도 |
| Event append vs 신규 생성 비율 | S2 | "사건 저장소화" 진척(높을수록 문서→사건 압축 성공) |
| possible_link 보류 수 / 해소율 | S2 | false merge 방지 작동, 검수 부하 |
| merge_score 분포 / θ 경계 오분류 | S2 | merge_score 3축 캘리브레이션(orchestrator #2) |
| entity candidate 수 / 승격율 | S4 | 엔티티 해소 품질 |
| 발견 후보 수 / 승인율 (authority) | S10 | 자동 발견 폭주 여부, 사람 승인 부하 |
| 논쟁 스레드 수 / 평균 깊이 / 체류시간 | S9 | 트래픽 성장(요구 2 북극성, Monetizable Dwell) |
| 투자조언 차단 수 / injection 차단 수 | S9 | 안전 게이트 작동(R-AgentDebateSafety) |
| audit replay 일치율 (게이트 결정) | S6 | 결정론 게이트 재현성(orchestrator #5) |
| 광고 노출 / RPM / 재방문율 | 전체 | 수익(요구 2, ADR#15) |

## §20. 단계별 "정의된 완료(Definition of Done)"

각 단계가 "끝났다"의 객관 정의(DIRECTION §8 acceptance를 단계로 분해).

- **S1 DoD:** 마이그레이션 up/down 동작, events·event_updates CRUD 테스트 green, 기존 1,517 green, event_id NULL 카드 조회 정상, **이중쓰기 정합성 불변식 테스트**(R-EventModelMigration).
- **S1.5 DoD:** change verdict(read-only) SKIP 산출, seen_content_hash skip(비용 0) 검증, rate/robots 위반 0.
- **S2 DoD:** "2번째 보도 → 기존 Event append(새 카드 0)" E2E green, 약신호 possible_link 보류 테스트, heat 단조성 테스트, cluster_event_map 영속, **clique 게이트·merge_score 3축**(R-FalseMerge).
- **S3 DoD:** domains/tags 분리 산출, general 폴백 유지, Update added_domains 누적, themes/sectors API 비파괴.
- **S4 DoD:** NER→entity upsert(별칭 병합), 앵커 매칭, candidate 자동병합 금지, event↔entity 연결 조회.
- **S5 DoD:** off 시 1,517 green, candidate→확장→tiered→raw_events E2E, budget 초과 graceful, 정책 제외 차단, audit_trace 적재, **batch 후보단위 격리**(R-ExpansionPartialFailure).
- **S6 DoD:** off 시 supervisor 기존 테스트 green, on 시 unsafe 제안 차단, 사건유형→role 매핑 테스트, **replay record(input_fingerprint+deterministic_fallback_would_be)**(R-LLMCollectBoundary).
- **S7 DoD:** change "없음→skip(호출 0)" 검증, false change 억제(정규화 해시), robots/rate 위반 0.
- **S8 DoD:** evidence 구조화 노드 생성·조회, 문자열 evidence 호환, source_type↔role 매핑, relation 태깅.
- **S9 DoD:** comment 확장 마이그레이션(기존 비파괴), 논쟁 claim→counter→evidence E2E, 투자조언 차단 회귀, evidence 없는 에이전트 발화 차단.
- **S10 DoD:** 앵커→sitemap/feed 후보 도출(정책 통과분), candidate 자동활성 금지(승인 큐), robots 준수.
- **S11 DoD:** 캐스케이드 실패 시에만 호출(1차 0), 회수율·비용 메트릭, 전문 미저장, graceful None.

> **전 단계 무조건 게이트(재확인):** ① 기존 1,517 테스트 green ② secret scan PASS ③ git diff clean(`.env` 무변경) ④ 우회 0(robots/ToS/rate/SSRF) ⑤ 투자조언 표현 0 ⑥ 전문 저장 0. 이 6개를 못 넘으면 그 단계는 "완료"가 아니다. 타협 없음.

---

# PART C — 엔진별 상세 의사코드 · 마이그레이션 · 설정 키 · 테스트 케이스

PART A가 스키마, PART B가 데이터·플로우라면, PART C는 **구현자가 곧장 손댈 의사코드·alembic·config· 테스트 목록**이다.

## §21. 엔진별 상세 의사코드

### §21.1 `event_resolver.resolve` (§2 핵심)
```python
# 의사코드 (실제 코드 아님). 비파괴·fail-closed.
def resolve(candidate, cluster_result, db):
    mapped = db.cluster_event_map.get(cluster_result.cluster_id)
    if mapped:
        # merge_score 3축 + clique 게이트(orchestrator #2 / adversarial #1)
        if cluster_result.confidence == "duplicate" and clique_ok(cluster_result):  # 강신호 clique
            upd = make_update(candidate, event_id=mapped.event_id)
            db.event_updates.append(upd)                      # append-only
            recompute_heat(mapped.event_id, db)               # §2.4 half-life
            update_first_seen_if_earlier(mapped.event_id, candidate.observed_at)
            refresh_snapshot_card(mapped.event_id, db)
            return Decision(APPEND, mapped.event_id)
        else:                                                  # 약신호/clique 미달 → 보류
            db.event_links.insert(possible_link(cluster_result, mapped.event_id))
            return Decision(HOLD_POSSIBLE, mapped.event_id)
    else:
        ev = create_event(candidate)                          # FSD
        db.cluster_event_map.put(cluster_result.cluster_id, ev.id)
        return Decision(CREATE, ev.id)
```
- **불변:** `event_updates`는 INSERT만(UPDATE/DELETE 없음) → 가역성·감사.
- **충돌(두 cluster가 같은 Event 주장):** 더 이른 first_seen으로 병합, 패자는 `event_links(merged)`.

### §21.2 `expansion_router.route` (§5 핵심, LAYER G/F)
```python
def route(queries, budget, policy_gate, db):
    out = []
    for q in dedup(queries)[:budget.max_queries_per_event]:
        if budget.exceeded():
            audit("budget_exceeded", q); break               # graceful 중단
        hits = provider_tier1_free(q)                         # google_programmable_search
        if len(hits) < q.min_hits and budget.allows_paid():
            hits += provider_tier2_paid(q); budget.charge(q)  # tavily/exa
        for url in hits:
            if not policy_gate.ok(url):                       # robots/ToS/SSRF/POLICY_EXCLUDED
                audit("policy_blocked", url); continue
            if db.seen_content_hash(url):                     # Change Detection skip (S1.5)
                continue
            out.append(ingest(url))                           # 기존 수집 파이프라인 재유입
        audit("expansion", q, tier_used, cost)
    return out
```

### §21.3 `change_detector.check` (§7.3, T1 지렛대)
```python
def check(source, last_state):
    head = http_head(source.url)                              # rate gate 준수(하한 clamp)
    if last_state.etag and head.etag == last_state.etag:
        return SKIP                                           # 호출 0
    if last_state.last_modified and head.last_modified <= last_state.last_modified:
        return SKIP
    body = extract_body(fetch(source.url))                    # article_body_extractor 재사용
    norm_hash = sha256(normalize(body))                       # 광고/타임스탬프 제거 후
    if norm_hash == last_state.norm_hash:
        return SKIP                                           # false change 억제
    save_state(source, head.etag, head.last_modified, norm_hash)
    return CHANGED                                            # → LLM Triage
```

### §21.4 `entity_resolver.upsert` (§3)
```python
def upsert(mention, db):
    # 1) 앵커 우선 (공식 도메인/QID)
    if mention.external_id:
        ent = db.entities.find_by_external_id(mention.external_id)
        if ent: return merge_alias(ent, mention.surface)
    # 2) 별칭 매칭
    ent = db.entities.find_by_alias(normalize(mention.surface))
    if ent: return ent
    # 3) 모호 → candidate (자동병합 금지)
    return db.entities.insert(Entity(canonical=mention.surface, status="candidate"))
```

### §21.5 `agent_debate.run` (§9, fail-closed 발화 게이트)
```python
def run(event, db):
    personas = summon_personas(event.domains)                 # energy-analyst, skeptic ...
    thread = []
    claim = personas.analyst.speak(event, stance="claim")
    if not gate_ok(claim): return thread                      # evidence 필수 + 투자조언 필터
    thread.append(persist(claim))
    counter = personas.skeptic.speak(event, reply_to=claim, stance="counter")
    if gate_ok(counter): thread.append(persist(counter))
    return thread

def gate_ok(utterance):
    if not utterance.evidence_refs: return False              # 근거 없는 단정 차단
    if has_investment_advice(utterance.body): return False    # 원칙1
    if injection_detected(utterance): return False            # R-PromptInjection
    return True
```

> **참고(원본 표기 보존):** 원본 SPEC §21.5는 `soummon_personas`로 표기됐다(오타). 본 문서는 `summon_personas`로 정정해 수록한다(의미·시그니처 동일, 손실 없음).

## §22. Alembic 마이그레이션 스케치 (additive·가역)

```text
0004_events_timeline.py:
  create_table events (... §1.1 / EVENT_SCHEMA Part 2 §Event ...)        # 신규
  create_table event_updates (... §1.2 / EVENT_SCHEMA Part 2 §EventUpdate ...) # 신규
  create_table cluster_event_map(cluster_id PK, event_id FK)
  create_table event_links(id, event_id, linked_event_id, status, reason)
  add_column event_cards.event_id UUID NULL FK->events.id   # 비파괴
  downgrade: drop_column event_cards.event_id; drop 4 tables

0005_entities.py:
  create_table entities (... §3.1 / EVENT_SCHEMA Part 2 §Entity ...)
  downgrade: drop_table entities

0006_evidence_nodes.py:
  # evidence는 JSONB라 컬럼 변경 없음 — 애플리케이션 레벨 구조 승격(문자열 호환)
  # 인덱스만 추가(필요 시): event_cards.evidence GIN

0007_comment_debate.py:
  add_column comments.author_type VARCHAR(8) NOT NULL DEFAULT 'user'   # 기존 비파괴
  add_column comments.agent_persona VARCHAR(64) NULL
  add_column comments.reply_to UUID NULL FK->comments.id
  add_column comments.stance VARCHAR(12) NULL
  add_column comments.evidence_refs JSONB NOT NULL DEFAULT '[]'
  downgrade: drop 5 columns
```
- **원칙:** 모든 신규 컬럼 nullable 또는 server_default → 기존 행 무영향. 모든 마이그레이션 downgrade 제공.
- **GroundTruth:** 현재 alembic 0004~0007 **부재**(미구현). 위는 작성 스케치다.

## §23. 설정 키 (`.env.example`에 추가 제안, 빈값=DEFAULT 계약)

> `.env`는 열람/수정/커밋하지 않는다. 아래는 **`.env.example`에 추가할 키 이름 제안**(별도 diff로 사용자 승인). 모두 "빈값=코드 기본"이 되도록 `config.py` model_validator 계약(ADR#12)을 따른다. (키 카탈로그 단일 출처 = `5_REFERENCE/ENV_KEYS.md`.)

| 키 | 기본(코드) | 용도 |
|---|---|---|
| `LLM_PROVIDER` | "" (=off, mock) | LLM 수집 관여 on/off (이미 존재) |
| `EXPANSION_MAX_QUERIES_PER_EVENT` | 5 | 확장쿼리 K 상한(§5.2) |
| `EXPANSION_MONTHLY_BUDGET_USD` | 0 (=무료만) | 유료검색 월 예산(§5.3) |
| `EXPANSION_PER_EVENT_BUDGET_USD` | 0 | 사건당 유료 상한 |
| `HEAT_W_RECENCY/FREQ/CORROB/SPREAD` | 0.4/0.3/0.2/0.1 | heat 가중치(§2.4) |
| `CHANGE_POLL_INTERVAL_HOT/COLD_SEC` | 1800 / 86400 | heat별 차등 폴링(§7.3, rate 하한 clamp) |
| `DEBATE_ENABLED` | false | 에이전트 논쟁 on/off(§9) |
| `DEBATE_MAX_DEPTH` | 4 | 논쟁 스레드 깊이 상한 |
| `SLM_BODY_FALLBACK_URL` | "" (=off) | 통신서버 SLM 엔드포인트(§10) |
| `EVENT_MERGE_TIME_WINDOW_HOURS` | 48 | Event 병합 시간창(§2, merge_score 1축 — 3축 보강 시 시간 weight) |

## §24. 테스트 케이스 열거 (단계별 핵심 케이스)

> 기존 테스트 분포(grounded): ingestion 1293 / backend 106 / agents 86 / workers 32 / frontend 8 = 1,517 + 5 skipped. 아래는 단계별 **신규 추가** 핵심 케이스(회귀는 기존 green 유지로 커버).

- **S1:** events_crud / event_updates_append_only(UPDATE 시도 거부) / card_event_id_nullable_query / **dual_write_consistency_invariant**.
- **S1.5:** etag_same_read_only_skips / seen_content_hash_skip_zero_cost.
- **S2:** second_report_appends_not_new_card / weak_signal_holds_possible / heat_monotonic / cluster_conflict_merges_to_earliest / first_seen_pulls_earlier_only / **clique_gate_rejects_transitive_merge / merge_score_three_axis**.
- **S3:** domains_tags_split / general_fallback_on_no_match / added_domains_accumulate / themes_sectors_api_unchanged.
- **S4:** ner_upsert_merges_alias / anchor_match_dedups_variants / ambiguous_stays_candidate / event_entity_link_query.
- **S5:** off_falls_back_deterministic / candidate_to_raw_events_e2e / budget_exceeded_graceful / policy_excluded_url_blocked / seen_hash_skipped / audit_trace_persisted / **batch_one_failure_isolated_to_fallback**.
- **S6:** off_supervisor_unchanged / unsafe_strategy_rejected(test_llm_agent_strategy_hints 확장) / event_type_to_role_mapping / **rejected_proposal_recorded_not_silent / replay_record_deterministic**.
- **S7:** etag_same_skips / last_modified_skips / false_etag_norm_hash_skips / changed_triggers_triage / robots_rate_respected.
- **S8:** evidence_node_create_query / string_evidence_backward_compat / source_type_role_mapping / relation_tagging.
- **S9:** comment_columns_additive_existing_unchanged / debate_claim_counter_evidence_e2e / investment_advice_blocked / agent_utterance_without_evidence_rejected / injection_blocked.
- **S10:** sitemap_parse_candidates / candidate_not_auto_activated / robots_respected / no_sitemap_feed_fallback.
- **S11:** called_only_on_cascade_failure / not_called_first / recovery_rate_metric / full_text_not_stored / graceful_none_on_server_down.

## §25. 구현 착수 체크리스트 (S1 첫 단계 예시)

S1(Event 토대)을 실제로 시작할 때의 atomic 체크리스트 — 다른 단계의 템플릿.

```
[ ] PLAN: events/event_updates 스키마 확정(§1.1/§1.2 + EVENT_SCHEMA Part 2), 사용자 검토
[ ] alembic 0004 작성(additive, downgrade 포함)
[ ] ORM 모델 Event/EventUpdate (backend/app/models/event_timeline.py)
[ ] Pydantic 스키마 (backend/app/schemas/) + EVENT_SCHEMA.md 갱신
[ ] event_cards.event_id FK 추가(nullable)
[ ] CRUD 서비스 + 단위테스트(append-only 거부 포함)
[ ] 이중쓰기 정합성 불변식 테스트(R-EventModelMigration)
[ ] VERIFY: 기존 1,517 green / 신규 테스트 green / migration up·down 동작
[ ] VERIFY: event_id NULL 기존 카드 조회 정상(비파괴)
[ ] 보고(한국어): 무엇을/무엇을 검증/WARNING·UNKNOWN
```

> **PART C 결론:** 의사코드 5종은 fail-closed·append-only·게이트 검문(+clique 게이트·replay record·후보단위 격리)을 코드 형태로 못박았고, alembic 4종은 비파괴·가역을, config 10키는 "빈값=기본" 계약을, 테스트 열거는 단계별 검증을 고정했다. 이로써 세 입력(방향 ADR#14-16·개념 원자분해·구현 SPEC)은 "왜→무엇→어떻게→검증"의 완결 체인을 이룬다. 모든 단계는 6대 무조건 게이트(기존 green·secret·diff·우회 0·투자조언 0·전문 0)를 통과해야 완료다. 타협 없이, 우회 없이.

---

> **흡수 출처 명시:** 본 문서는 `WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md`(927줄)를 손실 0으로 흡수하고, orchestrator 인사이트 #2~#5 + adversarial 인사이트 #1·#5·#6을 '심화 보강' 박스로 근거(코드 file:line)와 함께 추가했다. 권위 정점은 `_CANONICAL/*`, 결정은 `_DECISIONS/2026-06.md`, DDL은 `5_REFERENCE/EVENT_SCHEMA.md` Part 2, 위험은 `_RISK/RISK_REGISTER.md`다. 본 문서는 ROADMAP(미래 계획)이며 구현 사실이 아니다.

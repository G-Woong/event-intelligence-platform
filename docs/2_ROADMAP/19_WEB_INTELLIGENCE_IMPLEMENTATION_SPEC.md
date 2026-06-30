# 19 — WEB INTELLIGENCE IMPLEMENTATION SPEC (5대 신규자산 구현 청사진)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 🟡 PARTIAL — **S1 토대 + S2(Event Resolution) 전 단계 구현됨**: S1(events/event_updates + event_cards.event_id FK + alembic 0004, turn8) · S2a(cluster_event_map/event_links + alembic 0005) · S2b(cross_source_dedup clique 게이트+signal_strength) · S2c(event_resolver 라우팅) · S2d(event_timeline_service CRUD 영속+apply_routing, ADR#19) · **S2e(event_resolution_pipeline 통합 배선 + 통합 E2E + ADR#20 삭제정책 + alembic 0006 FK RESTRICT + ✅ live-PG 검증)** — 2026-06-22. live-PG: 0001~0006 실 Postgres up/down·2-세션 동시 CREATE orphan 0·FK RESTRICT 삭제 차단(`test_event_resolution_live_pg` 14). **✅ C live wiring(ADR#22) + D-1 운영 결선(ADR#23)** 2026-06-22 — `event_ingest_pipeline`(수집→cross_source_dedup→resolver→events/event_updates) + `backend/app/tools/run_event_orchestration.py`(backend-side composition root, NullPool 엔진 생명주기, sink 주입; ingestion→backend import 0) + live-PG 로 실 sink CREATE→APPEND 입증. **✅ D-2a Event 타임라인 read API(ADR#24)** — `/api/events/timeline*` additive endpoint(flag·held degenerate 제외·레거시 무영향) → Event 가 웹 레이어로 처음 노출. **✅ D-2b frontend 렌더(ADR#25)** — Next.js `/events/timeline` 목록/상세 page+컴포넌트+타입/메서드+nav, 안전 evidence 렌더(http/https 게이트·allowlist 6키·source_refs 미렌더), flag off→graceful; 기존 event_cards 무변경(tsc 0·test 12·lint 0). **✅ D-2b 하드닝(ADR#26):** 테스트 provider mock 격리(conftest, `.env` 비의존)·공개 read 스키마 분리(PublicEventUpdate, source_refs wire 제외)·에러표현 통일. **✅ D-2c 데모(ADR#27, 2026-06-23):** `seed_event_timeline`(합성 Event 4·자연어 delta_summary·멱등·오프라인) + `db_target`(2중 fail-closed 가드, R-EventSinkDbTarget 종결) + compose flag on → **로컬(uvicorn+next dev) live-PG seed→API + Playwright 브라우저 스크린샷(목록/상세 렌더) + event_cards graceful 회귀로 제품 북극성("웹에서 Event 타임라인을 본다") 첫 실거동 가시화(full compose 빌드 E2E 잔여).** **✅ REAL_SOURCE_LOOP_AUDIT(ADR#28):** 경로 A(수집→raw_events) 실데이터 PROVEN, 경로 B(수집→Event 타임라인) **코드 배선 완료이나 실데이터 0회**(synthetic만) → **D-2c=화면 능력 검증≠실 파이프라인 검증, R-RealSourceLoopUnproven(MEDIUM); 방향=full compose 보다 실 소스 검증 우선.** **잔여:** full `docker compose up --build` 빌드 E2E·delta_summary 자연어화(상류)·주기 auto-trigger·실 production-validation 1회·3엔진 색인 정합·heat(S2.5)·merge_score entity/domain(S4)·event_cards 자동연결·LLM 보조 레이어(경계만). expansion_router/agent_debate/alembic 0007 부재(S5~).
> │ **구현순위:** #17 (00_ROADMAP_INDEX) · **그룹:** D (신규 NET-NEW)
> │ **검증 근거:** GroundTruth — 해당 모듈 ls 실패·grep 0건. comment.py debate컬럼 0.
> │ **잔여(미구현):** S3~S11(**S1 + S2-core(a~c) + S2d + S2e(통합 로직 E2E) 완료** 2026-06-22; live-PG E2E 이월). 권장순서 (S1✓·S2✓)→S5/S1.5→S3→S4→S7→S8→S9→S10→S11.
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

> **ADR#90 cross-ref (contract-only · runtime No-Go):** 이 §9 Agent Debate / community 상호작용의 미래 계약은 `5_REFERENCE/HOT_INTELLIGENCE_POST_CONTRACT.md`·`AGENT_HOTNESS_REASONING_CONTRACT.md`·`COMMUNITY_INTERACTION_FUTURE_GATE.md`(ADR#90 신설)에 고정됐다 — Hot Intelligence Post·agent hotness·community interaction 은 **runtime 비활성**이며, public Hot Post / comment-reply runtime 은 **R1 gold + MERGE_GATE + public-IU gate + 11 community-interaction 요구** 충족 후에만 개방(community reaction=`reaction_to` 전용·event anchor 아님).
>
> **ADR#91 cross-ref (contract-only · runtime No-Go):** 위 계약을 게이트/순서로 결속 — `5_REFERENCE/HOT_POST_GATE_ALIGNMENT.md`(public_readiness 를 R1 gold·R2 MERGE_GATE·official/news evidence·source-role·community 11요구에 결속·runtime_enabled=False)·`5_REFERENCE/COMMUNITY_POSTING_ROADMAP_CONTRACT.md`(stage_0 evidence→stage_1 gold/merge→stage_2 draft→stage_3 public readiness→stage_4 reaction→stage_5 moderation→stage_6 comment reply gate→stage_7 followup·comment reply runtime disabled). + operator payload sourcing workflow·official×news overlap diagnostics·R1 label return operational bridge(`intake_command` + gold_promotion_status·synthetic/single/unsure 미승격). frontier parity 68→78·**R1 = FAIL·R2~R7 = No-Go 불변.**

> **ADR#92 cross-ref (contract/guard-only · runtime No-Go):** 실전 데이터 흐름을 다음 시도로 잇는 5 모듈 — `5_REFERENCE/LIVE_ATTEMPT_PACK_CONTRACT.md`(real payload 부재 시 operator-fillable 후보 묶음·후보 live 트리거 불가)·`news_breadth_trigger.py`(news-side 수율 0→source 확장 판정·GDELT 실행 0)·`first_freeze_package_hardening.py`(freeze worklist reviewer-safe 검사)·`5_REFERENCE/R1_FIRST_CONTACT_PROTOCOL.md`(8단계 freeze→contact→label→gold·전송 0)·`5_REFERENCE/HOT_POST_PREVIEW_GUARD.md`(internal-only preview·public 차단·R1/R2 후 게시). frontier parity 78→88·**R1 = FAIL·R2~R7 = No-Go 불변.**

> **ADR#93 cross-ref (contract/planning-only · runtime No-Go):** 실 live/freeze 시도 경로를 실행 가능하게 만드는 6 모듈 — `5_REFERENCE/REAL_PAYLOAD_PROMOTION_WORKFLOW.md`(pack 후보→draft 승격·발생 확인 FIRST·real path 미작성)·`5_REFERENCE/OPERATOR_LIVE_COMMAND_PACK.md`(validate/dry-run/live-run 분리·network 0·fidelity probe 미경유)·`5_REFERENCE/FREEZE_TO_R1_EXECUTABLE_CHECKLIST.md`(freeze→contact→dropbox→intake 명령·batch_id 정합·gold gated)·`5_REFERENCE/HOT_POST_ACTIVATION_MAP.md`(9 stage·public publish 는 R1 AND R2 후·runtime 0)·`5_REFERENCE/COMMUNITY_FEEDBACK_LOOP_CONTRACT.md`(11 loop step·moderation/privacy/audit/citation 필수·reply runtime 0)·`5_REFERENCE/NEXT_PROVIDER_EXPANSION_PACK.md`(no-yield→provider 권고·GDELT 실행 0·KO lane 분리). frontier parity 88→104·**R1 = FAIL·R2~R7 = No-Go 불변.**

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

### §19.1 reviewer pilot ops UI seed contract (ADR#70, internal ops dashboard 착수 게이트)

ADR#70 `reviewer_pilot_handoff.build_ops_ui_contract` 가 **미래 internal ops dashboard** 가 읽을 workflow-state contract 를 산출한다. 이는 reviewer pilot/label 회수 운영 상태를 시각화하기 위한 것이지 **public Intelligence Unit 이 아니다**.

```
OpsReviewBatchStatus (internal ops UI seed):
- contract: "OpsReviewBatchStatus"
- batch_id
- pilot_status         (8-state: not_ready/ready_to_contact/awaiting_reviewer_return/
                         partial_returned/invalid_returned/conflict_pending/
                         calibration_pending/imported_ready_for_merge_gate_review)
- followup_status      (ADR#69 7-state)
- intake_status        (ADR#68 5-state)
- expected_label_count / returned_label_count / missing_label_count
- invalid_label_count / conflict_pair_count
- production_gold_count / calibration_ready / merge_gate_ready
- next_action          (operator 한 줄 액션)
- flags: { no_merge, no_public_iu, pii_safe, no_llm, no_db_write }   # 전부 True
```

### §19.2 reviewer pilot **execution** status contract (ADR#71, internal ops dashboard execution 축)

ADR#71 `reviewer_pilot_execution` 가 ADR#70 OpsReviewBatchStatus 위에 **pilot 실행 추적** 축을 더한다. handoff readiness(번들 배포 가능)와 **실 pilot 실행**(operator 가 실제로 reviewer 에게 contact 했는가·첫 returned label 이 들어왔는가)을 분리하는 별도 contract:

```
InternalOpsPilotExecutionStatus (internal ops UI · execution 축):
- contract: "InternalOpsPilotExecutionStatus"
- batch_id
- pilot_status            (ADR#70 8-state)
- execution_status        (8-state: not_started/awaiting_operator_contact/
                           contacted_waiting_return/partial_returned/invalid_returned/
                           conflict_pending/calibration_pending/
                           labels_returned_ready_for_merge_gate_review)
- contact_evidence_present
- real_reviewers_contacted   (roster ∩ contact_status=contacted 만·evidence 없으면 0)
- returned_label_count / missing_label_count / invalid_label_count / invalid_file_count
- conflict_pair_count / overdue_count
- production_gold_count / synthetic_gold_count
- production_gold_provenance_verified   (현재 False·선언 기반)
- calibration_ready / merge_gate_ready
- next_action            (operator 한 줄 액션)
- flags: { internal_only, no_public_truth, no_merge, no_public_iu,
           pii_safe, no_llm, no_db_write, gold_provenance_verified }   # 전부 True 또는 안전쪽
```

**execution 축의 정직성**: `execution_status` 는 pilot_status 의 "회수 경로" 축과 **직교**한다 — operator contact evidence(operator 가 수동으로 수행한 접촉의 *기록*·시스템 전송 0)가 없으면 `awaiting_operator_contact` 를 정직하게 유지하고, `real_reviewers_contacted` 는 `contact_status=contacted` evidence(roster 내)만 카운트한다(prepared/declined/unavailable 분리·둔갑 차단). `internal_only`/`no_public_truth` flags 와 same_event/label/verdict truth 미노출로 R-OpsUIPrematureTruth 를 가드한다. **단 contact evidence 는 자기보고(self-attested)** — 실 contact 의 독립 확인은 returned label 회수가 사후 실증(R-ContactEvidenceIntegrity).

**착수 게이트(§20 web UI 시점)**: internal ops dashboard 는 이 contract 위에서 **지금 착수 가능**하다 — workflow state(누가 무엇을 빠뜨렸는지·회수 진행)를 시각화할 뿐 unverified truth 를 노출하지 않기 때문이다(`flags.no_public_iu=True`·pseudonym only·PII-safe). 반면 **public Intelligence Unit UI 는 여전히 No-Go** — source identity/gold/MERGE_GATE(`RAG_KG_AGENT_READINESS` 9조건 중 1·4·5·7 미충족)를 통과하기 전까지 raw source→즉시 public output 은 금지다. **위험**: ops UI 필드(pilot_status·gold_count 등)가 public truth 로 오인될 수 있음(R-OpsUIPrematureTruth) → internal/public surface 물리적·시각적 분리가 구현 시 강제되어야 한다.

**ADR#72 — 이 contract 의 첫 물질화(actual backend read-only API + frontend seed):**

ADR#72 가 위 contract 를 실제 backend read-only API 와 frontend seed 로 구현한다. `reviewer_actual_input_gate.py`(ADR#71 `run_reviewer_pilot_execution` 단일 호출 dispatch·재구현 0)가 gitignored 입력 디렉터리(`outputs/reviewer_batch/<batch>/`)를 **스캔만**(생성·날조 0)해 실 contact evidence/returned label 유무를 5-state `actual_input_status`(no_actual_input/contact_evidence_only/returned_labels_present/invalid_returned_labels/labels_imported)로 산출하고, 없으면 `external_input_required=production_gold_count==0` 으로 정직히 멈추며, 있으면 intake→followup→handoff end-to-end 로 태운다.

- **backend** `GET /api/internal/ops/pilot-execution`: **이중 게이트** = admin-token(`require_admin_token`·production/staging 토큰 미설정 시 503 fail-closed·dev/test bypass) + `INTERNAL_OPS_DASHBOARD_ENABLED` flag(기본 off→404). read-only·sync `def`(FastAPI threadpool·event loop 미차단)·DB/LLM/embedding/network 0·`response_model=InternalOpsPilotExecutionStatus`(sanitized 화이트리스트 — same_event/score/rationale/predicted_status/raw PII 필드 부재로 구조적 미노출).
- **frontend** `/internal/ops-pilot`(`app/internal/ops-pilot/page.tsx`): server-only env `INTERNAL_OPS_DASHBOARD_ENABLED` 미설정→`notFound()`(404·**NEXT_PUBLIC 아님**·클라이언트 미전송)·nav(`layout.tsx` 하드코딩) 미노출·데이터는 server-side `adminFetch`(X-Admin-Token)·read-only·no-go 배너("Internal operations status"/"Not public truth"/"No merge allowed"/"Gold not verified yet"/"Requires MERGE_GATE before public IU")·순수 view helper(`opsPilotExecutionView.ts`)의 `FORBIDDEN_OPS_FIELDS` 재귀 가드(표시층이 forbidden 필드 re-introduce 차단).
- **4중 게이트(R-InternalOpsAuthBoundary)**: admin-token(prod fail-closed) + flag-404 + nav 미노출 + server-env `notFound()`. **internal ops(workflow state·`no_public_truth`) ↔ public IU(verified truth·source identity/gold/MERGE_GATE 통과 후만·No-Go)** 분리 유지. RAG/KG/Entity/LLM 은 `RAG_KG_AGENT_READINESS` 의 gated roadmap(Stage R1~R7)이며 merge 에는 No-Go.

**ADR#73 — auth/deploy preflight + R1~R7 readiness matrix (배포 안전성 봉인 + product bridge):**

ADR#73 이 위 4중 게이트의 "선언"을 **테스트 가능한 preflight + read-only product bridge** 로 봉인한다. `internal_ops_preflight.py`(ADR#72 `run_actual_input_gate` 단일 호출·재구현 0):

- **auth/deploy posture(5-state)** `evaluate_internal_ops_posture`(순수·settings 주입·admin token **존재 여부만**·값 미열람): `disabled_safe`(flag off→404·가장 안전) / `enabled_internal_safe`(flag on+token→auth 강제) / **`unsafe_public_exposure`**(flag on+무토큰+비-prod→`require_admin_token` bypass→**무인증 reachable**·`endpoint_open_unauthenticated=True`) / `misconfigured`(flag on+무토큰+prod-like→503/기동거부) / `unknown`. `auth_boundary_status`(hardened_partial/no_go) 롤업·`deployment_proven=False` 불변(per-user auth 미구현+물리 reachability 미증명).
- **`GET /api/internal/ops/preflight`**: 이중 게이트(기존과 동일)·read-only·`response_model=InternalOpsPreflightStatus`(sanitized — admin token **값** 필드 부재·존재 여부 bool 만)·503 sanitize(경로/내용 미노출).
- **frontend** posture 테이블·경고 배너(unsafe/external-input/deployment)·**R1~R7 readiness 요약**(stage/goal/status/blocker/next-action)·operator next-action checklist(전부 read-only·기존 server-env gate 유지).
- **R1~R7 readiness matrix**(머신리더블 `R1_R7_READINESS` 7-stage·`SOURCE_ROLE_INVARIANTS`): gold→MERGE_GATE→embedding→entity→KG→GraphRAG→IU·각 단계 input/gate/blocker/forbidden_shortcut/next_action/test·community=reaction·market=signal·catalog=enrichment·search=URL·unknown=fail-closed·KG edge=provenance 필수·public IU=No-Go(R1 부터 막힘·gold 0). 상세는 `RAG_KG_AGENT_READINESS §6b-R`.
- **잔여(R-InternalOpsAuthBoundary·OVERCLAIM 방지)**: preflight 는 config posture 를 봉인할 뿐 **물리 network reachability·per-user auth 는 미증명**(`deployment_proven=False`)·실 배포 경계 검증 전까지 완전종결 금지.

**ADR#74 — R1 gold acquisition operating plan + internal ops R1 gap visibility + source storage strategy:**

ADR#74 가 R1~R7 matrix 의 R1(FAIL) 행을 **실 라벨 수집 운영 plan** 으로 물질화한다. `r1_gold_acquisition_plan.py`(ADR#72 `run_actual_input_gate` 단일 호출·재구현 0):

- **R1 target floor(operating floor≠production truth)**: live decisive gold ≥200 / KO ≥50(canonical `GOLD_MERGE_MIN_LIVE_GOLD`/`GOLD_MERGE_MIN_KOREAN_GOLD` 재사용)·balanced positive ≥67·negative ≥67(ADR#74 파생 = `ceil(200/3)`·balance ratio≥0.5 충족 최소 class)·hard-negative gold ≥20(evaluator floor·FP=0 의미있는 측정 표본)·pair 당 reviewer ≥2(`DEFAULT_REVIEWERS_PER_PAIR`)·two-reviewer agreement+human-only conflict adjudication.
- **R1 status(4-state)** + **gap 산술**(required−current·label/korean/positive/negative/hard_negative/reviewer): **현재 production_gold_count 0 → blocked_no_labels·모든 gap=전체 target**. R1 satisfied 는 calibration_ready 일 때만·synthetic/test/model→production gold 0.
- **`GET /api/internal/ops/r1-gold-acquisition`**(이중 게이트·read-only·`response_model=InternalOpsR1AcquisitionStatus`·sanitized)+frontend R1 gap 패널(current/required/gap·operator next manual action·"R1 is blocked by actual returned labels"/"Gold count is 0 until human production labels are imported"/"R2~R7 remain No-Go" copy).
- **source-specific storage strategy(§6b-S·docs only·runtime No-Go)**: official/news=anchor·community=reaction·market=signal·catalog=enrichment·search=URL·unknown=fail-closed storage shape+KG edge eligibility+risk·모든 KG edge=provenance+confidence+source role 필수·GraphRAG=verified graph 전 금지·storage runtime/schema=R4~R5 gate 전 미구현(R-SourceStoragePrematureSchema).
- **잔여(R-GoldAcquisitionPlanOnly·OVERCLAIM 방지)**: plan/gap surface 는 *무엇을 모아야 하는가* 를 명시할 뿐 **실 returned labels 를 만들지 않는다**(production_gold_count 0·gate exact passthrough)·실 회수 전까지 완전종결 금지.

**ADR#75 — R1 first reviewer pilot batch freeze + operator launch handoff + internal ops launch readiness:**

ADR#75 가 ADR#74 R1 *plan* 을 **실제 reviewer 에게 넘길 첫 동결 pilot batch** 로 물질화한다. `r1_reviewer_pilot_batch.py`(ADR#74 frozen·`run_actual_input_gate` 단일 호출 re-check·순수 builder freeze·재구현 0):

- **actual input re-check(옵션 A)**: 게이트 단일 호출로 `no_actual_input`/`external_input_required`/production_gold_count 0 정직 산출(재호출 0·입력 날조 0).
- **frozen pilot batch(옵션 B)**: 결정적·오프라인 후보 worklist(`build_captured_overlap_fixture`→`discover_overlap`→`build_near_match_reviewer_queue`·**합성**·LLM 0·network 0)를 순수 builder 로 동결 — **frozen 5 pair**·reviewer-facing(pair_id/source_role/title/canonical_url/observed_at/language·score/rationale/predicted_status/same_event/raw body/PII 구조적 부재[template allowlist])·`_batch_signature` deterministic sha256(정렬 pair 정체성+batch config·PII/score/rationale 제외)·`target_pair_count=200`→**frozen 5<<target=pilot_n**. **합성 fixture→production 후보 둔갑 0**: `candidate_provenance=synthetic_fixture`·`pilot_batch_is_production_candidate=False`·실 production 후보는 live source overlap(이번 턴 No-Go) 필요·라벨 회수해도 dataset_source=synthetic→production gold 미승격(machinery 강제). frozen batch 가 production_gold_count 미증가·same_event 미함의.
- **operator launch package(옵션 C)**: `build_operator_launch_checklist`(수동 배포/회수/검증 단계+manual-only contact 지시+PII/secret 금지 reminder+no-go 경고·**전송 0·label/contact evidence/roster 생성 0**)·handoff bundle 재사용·expected label files·placement guide·validation command(intake_dir=게이트 스캔 경로 단일 수렴).
- **launch readiness(옵션 D·제한적)**: **launch_status 5-state**(blocked_no_candidates/ready_for_manual_launch[현재]/awaiting_manual_launch/awaiting_returned_labels/labels_present)·`GET /api/internal/ops/r1-pilot-batch`(이중 게이트·read-only·`response_model=InternalOpsR1PilotBatchStatus`·sanitized)·frontend launch-readiness 패널(batch_frozen/provenance/pilot_n/expected files/launch_status/R1 gap/R2~R7 No-Go·"Frozen batch is a reviewer worklist, not truth"/"Manual launch required"/"Returned labels are still missing"/"Production gold remains 0 until human labels are imported"/"R2~R7 remain No-Go" copy).
- **잔여(R-BatchFreezeAsTruth·R-GoldAcquisitionPlanOnly·OVERCLAIM 방지)**: frozen batch 는 reviewer worklist 동결이지 **event truth 가 아니다**(production_gold_count 0·합성 provenance·pilot_n<<target)·실 production candidate(live overlap)→실 reviewer contact→actual returned labels 회수 전까지 완전종결 금지.

**ADR#76 — R1 live production candidate acquisition gate + production-candidate batch readiness + internal ops dual-track:**

ADR#76 가 ADR#75 합성 dry-run batch 너머 **실 production candidate** 로 한 단계 — R1 production gold 의 실제 시작점은 합성 batch 가 아니라 live-derived production candidate 다. `r1_production_candidate_acquisition.py`(ADR#75 frozen·acquisition gate + 조건부 freeze orchestrator·재구현 0):

- **actual input re-check(옵션 A)**: 게이트 단일 호출 re-check — returned/imported labels 가 이미 있으면 그 처리가 acquisition 보다 우선(`returned_labels_take_precedence`). 이번 턴 `no_actual_input`/`external_input_required`.
- **live production candidate acquisition(옵션 B)**: credential presence(`build_provider_readiness_report`·**secret-safe**·present/missing·값 0·network 0)+live 후보 획득(`cross_source_live_overlap_smoke`·Guardian×NYT adapter·**opt-in `live_query`·기본 시도 0**·실 HTTP 는 transport=None+양 credential present 일 때만). **6-state `production_candidate_status`**: blocked_no_credentials/blocked_no_live_opt_in[현재·credential present·남은 차단=opt-in]/blocked_no_live_overlap/blocked_no_publishable_pairs/live_candidates_found/production_batch_frozen. **live call 미실행**(자율 턴 per-turn opt-in 없음·결정론)→머신러리 구축+테스트·blocked 정직.
- **production-candidate batch freeze(옵션 C·조건부)**: live publishable×publishable 후보가 있을 때만 동결(`build_label_template(dataset_source=SOURCE_LIVE)`·ADR#75 `_frozen_pair_list`/`_batch_signature`/`build_operator_launch_checklist` 재사용). **source role guard `_is_publishable_production_pair`**(official/article/news 만·community/market/catalog/search/unknown anchor 거부·fail-closed·약화 0). **합성→production 둔갑 0**: `candidate_provenance=live_derived` AND live_call_performed AND publishable ≥1 일 때만 production_candidate_batch_ready=True(합성 절대 불가)·production_gold_count 미증가·same_event 미함의. 이번 턴 live 후보 0→미동결.
- **internal ops dual-track(옵션 D)**: synthetic dry-run batch 와 live production-candidate batch 를 **분리** 표시 — `GET /api/internal/ops/r1-production-candidates`(이중 게이트·read-only·`response_model=InternalOpsR1ProductionCandidateStatus`·**live_query=False 고정**[read API 시도 0]·sanitized)·frontend dual-track 패널(synthetic_dry_run_batch_ready/synthetic_batch_not_production vs production_candidate_batch_ready/candidate_provenance/production_candidate_status·"Synthetic dry-run batch is not production"/"Production candidate batch requires live-derived publishable pairs"/"Candidate worklist is not truth"/"Returned human labels are still required"/"R2~R7 remain No-Go" copy).
- **잔여(R-ProductionCandidateScarcity·R-SyntheticProductionContamination·OVERCLAIM 방지)**: live-derived publishable candidate pair 0(R1 시작점 부재)·production candidate 도 reviewer worklist 동결이지 event truth 아님·실 live 호출→실 후보→실 reviewer→actual returned labels 전까지 완전종결 금지. synthetic↔production provenance 분리는 기계 강제이나 실 production gold path 미가동.

**ADR#77 — R1 live query executed + cross-source near-match gap[원인 미확정] + blocked-reason honesty fix:**

ADR#76 opt-in gate 를 **user 명시 opt-in 으로 실제 실행**(`r1_production_candidate_acquisition --live-query` 1회·bounded Guardian×NYT 각 1회·rate cooldown 강제·secret-safe·raw body 0). live→discover **경로가 실데이터로 1회 실행**됐고(usable 산출 0), 다음 frontier 가 **deterministic near-match 단계의 0**(100 publishable 비교쌍 중 near-match 0)임이 드러났다 — 단 그 **원인은 단일 broad-topic 1회로 미확정**(범위=근거기반 최소증분).

- **live run 결과(실측·1회)**: `live_call_performed=True`·providers_ready=[guardian,nyt]·**`live_candidate_count=100`**(cross-source same-date **publishable 비교쌍**·≈10×10 Cartesian·≠same-event match)·**`publishable_pair_count=0`**(near-match 후보)·`production_candidate_status=blocked_no_publishable_pairs`·root cause **`no_title_overlap`**(near 0·fingerprint 0). 그 0 의 **원인 미확정** — (i) same-event cross-source paraphrase 의 결정적 recall 한계, 또는 (ii) broad topic 아래 서로 다른 사건/측면(ADR#64 가 "100 쌍=비교대상·n=2 로도 구분 불가" 명시). **detectable same-event overlap 은 여전히 0**(near/fingerprint)→scarcity 재확인(해소 아님).
- **adjudicator-zone 연결(§4 ④·조건부)**: **(i)이면** 이 갭은 §6b-R matrix **R3 embedding scorer** / INTELLIGENCE_UNIT_CONTRACT §4 **④ semantic adjudicator**(embedding/LLM/KG)가 메우도록 설계된 영역, **(ii)이면** targeted same-event 좁은 쿼리가 레버 — 어느 쪽인지 미해결·runtime 은 여전히 No-Go(MERGE_GATE/gold 전·embedding/LLM 실호출 0·자동 same_event 0). live run 은 near-match 0 을 **실측**할 뿐 원인을 확정하지 않는다.
- **분류 정직성 fix(test-locked·adversarial 근거)**: `blocked_no_publishable_pairs` primary next_action(`next_manual_action`)을 `live_candidate_count>0`+`no_title_overlap` 시 **원인 양가(paraphrase OR different-events·미확정)** vs role 거부로 분기(`_primary_next_action`·테스트 3종)→운영자 "source role guard 약화" 오안내 교정하되 단정적 paraphrase 도 회피.
- **Lane C/D(근거기반 최소증분·신규 파일 0)**: acquisition strategy(**좁은 same-event-targeted topic/time-window 변주로 (i)/(ii) 구분**·provider depth·(i) 확인 시에만 gated R3 adjudicator 가 lever·source role guard 유지). Lane D 계약(LLM evidence packet/RAG ingestion gate/KG edge eligibility/community reaction/public IU)은 §6b-R matrix/§6b-S table/§4 에 **기존 존재→grounding 만**. **public IU·merge·운영 DB·embedding/LLM runtime 0**.
- **잔여(R-CrossSourceNearMatchGap·R-ProviderPairNarrowness·R-ProductionCandidateScarcity·OVERCLAIM 방지)**: near-match 0 의 원인 (i)/(ii) 구분→해당 lever·실 reviewer contact·actual returned labels 전까지 완전종결 금지(detectable same-event overlap 0·scarcity 미해소). internal ops UI read API live_query=False 고정→UI 는 마지막 비-live 상태(Q10 gap·정직 표기·다음 증분).

**ADR#78 — targeted live acquisition + near-match gap diagnostic[양가·미확정] + LLM/RAG/KG product bridge contracts:**

- **near-match gap 진단(Lane B·양가 보존·단정 0)**: ADR#77 broad-topic near-match 0(원인 미확정·100쌍 제목 미보존)을 가르려고 smoke `emit_band_diagnostic`(band 분포·max title Jaccard·최고중첩 below-floor 샘플=**공유 정규화 토큰만**·raw body 0)을 입력으로 `classify_near_match_gap` 가 8-class root cause 를 **다수 가설+confidence=indeterminate** 로 산출(같은/다른 사건 단정 0·`same_event_truth_asserted=False`). near 는 reviewer 라우팅 gate≠merge gate(merge=fingerprint+gold+MERGE_GATE)→recall 개선 false-merge 위험 0.
- **targeted live 실측(§6·user opt-in·bounded·governed·1 seed 유효)**: fed_rate("Federal Reserve interest rate decision"·7d)=guardian ok 10/nyt ok 10·cross-source 비교쌍 **30**·band 전부 below_floor·**max title Jaccard 0.0526**·최고 쌍이 generic 토큰("it"/"over"/"day")·entity 아님. scotus_ruling·ukraine_war=host_gate_blocked(반복 host min-spacing·no-bypass). `all_below_hard_floor`·indeterminate·`blocked_no_publishable_pairs`·freeze 0·gold 0·r1_gap 200. **정직 해석**: 단일 기관·7d로 좁혀도 hard band 0·entity 미공유→(ii)약하게 기울되 **단정 불가**(n=1 유효 seed·2 host-gate 차단·(i)recall/normalization 생존). 미실행 실험=단일 discrete event·1d·당일 동시보도(host floor→seed turn/scheduled 분산).
- **Lane D(provider/Korean expansion plan·기계 산출)**: Guardian/NYT 외 wired query-capable publishable=GDELT(429)·SEC EDGAR·Federal Register; key-free 다출처 RSS fleet(영문+KO·feed-only); Naver/NewsAPI=cataloged not-wired(adapter wiring=lever); **search(Serper/Tavily/Exa)=URL candidate only·truth 아님·community/market/catalog=anchor 0**. Korean: KO floor ≥50·**KO live-query source 미배선**(RSS feed-only)·community reaction-only·KO Jaccard 형태소 미분절로 더 어려움·KO floor 영문쌍으로 해결 불가.
- **Lane E(product bridge contracts·runtime No-Go)**: `LLM_EVIDENCE_PACKET_CONTRACT.md`(LLM 가 볼/추론/인용/단정 못하는 것·uncertainty·**same_event=MERGE_GATE dependency**)·`RAG_KG_ENTITY_GATE_CONTRACT.md`(RAG ingestion gate·KG edge eligibility[same_event=MERGE_GATE·**community=reaction_to only**·mentions=entity provenance·caused_by=high evidence+uncertainty]·public IU gate). `*_contract_ready=True`=계약 정의됨·**runtime 0**(llm/embedding/merge/public IU 0). internal ops `GET /api/internal/ops/r1-acquisition-frontier`(read API live 0→insufficient_debug_artifact 정상)+frontier view(§11 필수 정직 copy: "Near-match 0 does not prove no same event" 등). page.tsx render 후순위(Q10 gap).
- **잔여(R-CrossSourceNearMatchGap·R-DeterministicNearMatchRecall·R-KoreanR1SourceGap·R-LiveAcquisitionRateBudget)**: (i)/(ii) 추가 분리(단일 discrete event·1d)→normalization recall+provider breadth→실 reviewer contact→actual returned labels 전까지 완전종결 금지. 실 production candidate freeze 0·실 gold 0.

**ADR#79 — discrete-event acquisition + deterministic recall probe(reviewer-routing recall·merge 분리) + provider breadth:**

- **deterministic recall probe(Lane C·핵심)**: 신규 `near_match_recall_probe.py` 가 reviewer-routing 후보 recall 을 높이는 **feature-attributed 결정론 정규화**(case fold·organization phrase alias[federal reserve→federalreserve·다토큰 인접]·acronym alias[fed/scotus/ecb…·모호 단어 who/us/un/eu 제외]·light stemming[rates→rate·operations→operation·shipping→ship]·number normalize·routing stopword)를 적용하고 **어느 정규화가 공유 토큰을 만들었나(feature attribution)** 를 보고한다. **merge 경로 미호출**(`cluster_records`/`semantic_identity_fingerprint` import/참조 0·AST 테스트로 물리 분리 잠금)·`recall_probe_applies_to_merge=False`·`merge_allowed=False`·score internal-only·body-free 요약. `fake_semantic`(char-bigram 블랙박스)와 달리 정규화 출처를 보고해 (i)/(ii) 판별 레버가 됨.
- **recall probe 실측(synthetic known-paraphrase·network 0·결정론)**: fed_acronym("Fed raises rates"↔"Federal Reserve lifts interest rates") baseline Jaccard **0.125**(merge-path 놓침)→probe **0.333**(routing 올림)·entity 공유 federalreserve·features [acronym_alias,phrase_alias,stem]·newly_routed True. scotus_phrase(SCOTUS↔Supreme Court) 0.111→0.286·entity supremecourt. diff_control(Fed↔Hurricane) 0.0→**0.0**·newly_routed False(**false lift 차단**·(ii) 판별). newly_routed 2·둘 다 entity 공유=**알려진 below-floor 같은-사건을 baseline 이 놓친 것을 probe 가 routing 으로 올림=(i) recall-miss 레버 경험적 시연**.
- **discrete-event acquisition(Lane B)**: 신규 `r1_discrete_event_acquisition.py`(op `r1_discrete_event_acquisition_and_recall_probe`)가 discrete seed 를 엄격 검증(단일 이산사건·tight window 1d/2d·named entity+event phrase 요구·broad umbrella[federal reserve/ukraine war] 거부·community/market/catalog 거부)하고 ADR#78 gate/diagnostic/provider/Korean 을 재사용하며 `refine_root_cause_with_recall_probe` 로 (i)/(ii) 분리를 **구조적 진전**(단정 0·indeterminate 보존)시킨다. **user opt 'synthetic only'→live 미실행**(dry: seed 3 valid[code_proposed_shape]·gold 0·gap 200·merge/llm/embedding/db/전송 0).
- **internal ops 배선(Lane E)**: `InternalOpsDiscreteAcquisitionFrontier`(22 field·same_event truth/per-pair score/rationale/predicted_status/raw body/PII/secret 필드 부재)+`GET /api/internal/ops/r1-discrete-acquisition`(read API live 0·flag off 404·503 no path leak)+TS interface+view(`toR1DiscreteFrontierDisplayRows`/`r1DiscreteFrontierWarnings`·§9 copy "Recall probe is reviewer-routing only, not merge" 등). dict==pydantic==TS **22==22==22**.
- **정직 해석(§5·단정 0)**: recall probe 는 **synthetic 에서 (i) 레버 실재·작동 증명**일 뿐, 실 ADR#77/#78 live below-floor 쌍의 (i)/(ii)는 discrete-event 1d LIVE pair 적용 전까지 미분리. same_event 단정 0·merge 불변. **신규 R-NormalizationRecallLeakage(LOW·probe score 누출 위험·테스트로 차단)**.
- **잔여(R-DeterministicNearMatchRecall·R-CrossSourceNearMatchGap·R-KoreanR1SourceGap)**: discrete-event 1d LIVE run + recall probe 를 live pair 에 적용해 (i)/(ii) 경험적 분리→provider breadth(RSS fleet·GDELT)·Naver adapter(KO floor)→실 reviewer contact→actual returned labels 전까지 완전종결 금지. recall probe 는 **synthetic 에서만 검증**(live 미적용).

**ADR#80 — live discrete-event run + recall probe를 LIVE pair에 적용 + 3분류 + provider breadth:**

- **live pair recall probe(Lane C·핵심·전부 additive)**: `cross_source_live_overlap_smoke` 에 additive `emit_recall_probe`+`_build_recall_probe_diagnostic` 가 **title 이 사는 레이어**의 cross-source `disc["candidate_pairs"]` 에 `summarize_recall_probe` 를 적용(body-free·제목 전문 노출 0)→ `recall_probe_diagnostic`. `r1_targeted_live_acquisition` 가 seed별 `_aggregate_recall_probe_diagnostic`→`live_recall_probe_diagnostic`. `r1_discrete_event_acquisition` 가 `_classify_live_recall_lift` 로 **3분류**(`live_recall_lift_found`/`live_no_recall_lift`/`live_blocked_by_rate_or_opt_in`·코드 실패 vs provider/data 실패 분리)·`refine_root_cause_with_recall_probe` 로 live verdict 갱신. **merge_allowed=False·recall_probe_applies_to_merge=False·same_event 단정 0·per-pair score reviewer/public 미노출** 전 경로 불변.
- **🔴 실 LIVE RUN(§4·user 승인 opt 2·측정·flaky)**: seed=SCOTUS "Supreme Court ruling"·1d·Guardian+NYT·**2 calls·host_gate 준수**(guardian 5s/nyt 12s·no-bypass)·raw body 0·secret 0(credential present/missing boolean 만·값 미열람). 결과 `RESULT_CLASS: LIVE_OK`(코드 정상): **comparison_pair_count=100**(publishable cross-source 비교쌍)·max_title_jaccard 0.1765·`all_below_hard_floor`·**`live_recall_probe_applied=True`**·**`live_recall_lift_status=live_no_recall_lift`**·`max_live_recall_probe_score=0.1765`(<0.2 routing floor)·**`live_pairs_newly_routed_by_probe=0`**·`blocked_no_publishable_pairs`·freeze 0·gold 0·gap 200·merge/llm/embedding/db False·exact "score" 키 0.
- **internal ops 배선(Lane E)**: `InternalOpsDiscreteAcquisitionFrontier` +4 필드(`max_live_recall_probe_score`·`live_pairs_newly_routed_by_probe`·`live_recall_lift_status`·`live_frontier_verdict`·**aggregate only·per-pair score 미노출**)+TS+view·필수 문구("Recall probe is reviewer-routing only, not merge"·"Newly routed does not mean same event"·"Production gold remains 0 until human labels are returned"·"R2~R7 remain No-Go"). dict==pydantic==TS **26==26==26**.
- **정직 해석(§5·단정 0)**: synthetic 에서 작동한 (i) recall-miss 레버가 **100개 실 SCOTUS 1d pair 에서 lift 0** → synthetic 성공(0.333)이 이 live seed(0.1765)에 **일반화되지 않음 실측**. comparison_pair=100>0 → overlap 부재 아님·(ii) different-events 또는 정규화 사전 한계 쪽이나 **reviewer 라벨 없이 단정 0**. broad-lean seed → 더 좁은 single-ruling seed 재측정 필요. merge 불변·코드 실패 아님(data 결과). **신규 R-LiveRecallProbeGeneralization(MEDIUM·실측)·R-DiscreteEventSeedBias/R-AcquisitionFrontierPersistence/R-KOAnalyzerDependency(LOW)**.
- **잔여**: live lift 0 의 (i)/(ii) 분리는 **provider breadth(GDELT cooldown·RSS 다출처·Naver KO) + 더 좁은 same-event seed** → 실 reviewer contact → actual returned labels(R1) 전까지 완전종결 금지. production_gold_count 0 불변.

**ADR#81 — provider breadth + named single-event seed + KO source path (acquisition support·실 live 미실행):**

- **provider breadth inventory(Lane B·전부 additive)**: `provider_breadth_inventory` 가 `source_registry.yaml`(`load_registry`)을 **57 소스=9 카테고리**로 분류 — query_capable_publishable 7·feed_only_publishable 7·official_source 5·search_url_candidate 4·ko_official_news 6·community_reaction_only 9·market_signal_only 6·catalog_enrichment_only 9·unknown_quarantine 4·anchor_eligible **25**. curated anchor-eligibility ∩ registry type(registry 에 query-capable flag 부재·분석 §2). `source_role_guard_preserved`=non-anchor 카테고리(`search_url_candidate`/`community_reaction_only`/`market_signal_only`/`catalog_enrichment_only`/`unknown_quarantine`) `anchor_eligible=False` 강제. credential secret-safe(`env_status`·present/missing 만·값 0). **breadth=acquisition support≠truth·search URL candidate=fetch 전 truth 아님.**
- **named single-event seed bank(Lane C)**: `named_event_seed_bank` 가 category seed("Supreme Court ruling")를 **named single-event seed** 로 교체 — validator(필수 필드+broad denylist+placeholder reject)가 fomc_rate_decision·ecb_rate_decision **accepted**·scotus/M&A/sanction 템플릿 placeholder reject·broad 자가검증 5/5 reject. `same_event_asserted=False`·`event_occurrence_verified=False`·provenance=code_proposed_named_shape. **named seed=candidate generation≠same-event proof.**
- **KO source path(Lane E)**: `ko_source_readiness` 가 KO 소스 14종(news 5 LIVE key-free·Naver 어댑터 2·KO official·community reaction·trend quarantine) status·credential secret-safe(`probe_env_var`)·**KO tokenization risk**(`[0-9A-Za-z가-힣]+` Hangul-aware 이나 형태소 분절/KO stemming/KO org alias 부재→KO-KO undercount·breadth-only until analyzer[KoNLPy/Mecab deferred]·crash-safe)·KO floor plan(human label 이 hard blocker·`ko_floor_solved=False`·gold 0). **KO official/news 만 anchor·KO community reaction-only·KO search URL candidate only.**
- **orchestrator + internal ops(Lane F)**: `r1_provider_breadth_acquisition` 가 discrete base(ADR#80)+3 도구 합성→§4 output+§10 sanitized frontier `InternalOpsProviderBreadthFrontier`(dict==pydantic==TS **30==30==30**·per-pair score/same_event/PII/secret 미노출)·`GET /api/internal/ops/r1-provider-breadth`(read API live 0). 필수 copy: "Provider breadth is acquisition support, not truth"·"Named seed is candidate generation, not same-event proof"·"Community reaction is not an event anchor"·"Production gold remains 0 until human labels are returned"·"R2~R7 remain No-Go".
- **live 정책(§7·미실행)**: /compact 에 이번 턴 live 명시 승인 없음 → `live_query_executed=False`·`live_run_status=blocked_no_live_opt_in`·`next_action=ask_for_bounded_live_run_approval`·selected_seed=**fomc_rate_decision** queued·secret 0·raw body 0·merge/llm/embedding/db/전송/public IU 0.
- **community reaction contract(§9·docs only)**: `RAG_KG_ENTITY_GATE_CONTRACT §4a` 신설(reaction_to verified event 만·anchor/same_event proof/rumor/PII/ToS 위반 금지·rumor amplification guard). 검증된 event 0 → runtime 부착 0.
- **잔여**: 신규 R-ProviderBreadthScopeCreep/R-SearchCandidateTruthLeakage/R-NamedSeedSelectionBias/R-LiveRunReproducibility(LOW)·부분진전 R-ProviderPairNarrowness/R-KoreanR1SourceGap/R-ProductionCandidateScarcity·종결 0. **다음 hard blocker=승인된 bounded live run(named seed)→reviewer contact→actual returned labels.** production_gold_count 0 불변.

**ADR#82 — bounded live breadth run + named-event date-pin gate + production candidate freeze attempt (실 live 미실행·date pin 미충족 차단):**

- **date-pin 게이트(§5)**: `validate_date_pinned_named_event` 가 named single-event SHAPE + occurrence_date ISO(YYYY-MM-DD) + placeholder 아님일 때만 `date_pinned=True`. fomc_rate_decision 은 occurrence_date 부재→`not_pinned:missing_occurrence_date`. **date_pinned=True 여도 `event_occurrence_verified=False`·`same_event_asserted=False`**(날짜는 operator 주장·발생/같은 사건은 MERGE_GATE 영역). **date-pin=operator gate≠occurrence proof.**
- **bounded live pool(§6)**: `build_bounded_live_provider_pool` 가 breadth inventory 의 anchor_eligible 을 `adapter_wired ∩ credential_present = live_runnable_now` 로 정직 산출 — 실 registry `providers_in_pool=[guardian,nyt]`·`provider_breadth_used=2`·key-free 0·credential 2·gdelt/sec_edgar/federal_register=`query_capable_not_yet_wired`(미배선). **provider breadth anchor_eligible 25 ≠ 실행가능 pool**·community/market/catalog/search 는 anchor_eligible=False 라 pool 진입 불가(source role guard 약화 0).
- **freeze 시도(§7·base passthrough)**: live-derived ∧ cross-source ∧ publishable×publishable ∧ reviewer_queue 일 때만 freeze. live 미실행→live-derived pair 0→`production_frozen_pair_count=0`·gold 0. **freeze=reviewer worklist≠same-event truth.**
- **KO source lane(§8)**: `build_ko_source_lane` 가 KO lane 을 EN named-seed run 과 **분리**(KO news RSS feed-only=topic query 불가·언어 mismatch·형태소 분석기 부재→`ko_named_seed_needed`·tokenizer/alias 요건·KO floor 0/50·solved=False). **KO×EN cross-language pair 금지(R-KOEnglishPairMismatch).**
- **orchestrator + internal ops(§9)**: `r1_bounded_live_breadth_run` 가 ADR#81 base+date-pin+pool+freeze+KO lane 합성→§4 output(50+필드)+sanitized frontier `InternalOpsBoundedLiveBreadthFrontier`(dict==pydantic==TS **30==30==30**·per-pair score/same_event/PII/secret 미노출)·`GET /api/internal/ops/r1-bounded-live-breadth`(read API live 0). 필수 copy 7(breadth=support not truth·named seed≠proof·bounded live run requires operator-confirmed date-pinned event·community≠anchor·freeze=reviewer worklist not truth·gold 0·R2~R7 No-Go).
- **live 정책(§5·§7·미실행)**: date pin 미충족(fomc occurrence_date 부재)→`blocked_reason=missing_date_pinned_named_event`·`next_action=provide_or_select_date_pinned_event`·`live_query_executed=False`·sanitized snapshot 미작성·secret 0·raw body 0·merge/llm/embedding/db/전송/public IU 0.
- **잔여**: 신규 R-DatePinnedEventAvailability/R-KOEnglishPairMismatch(LOW)·부분진전 R-ProviderPairNarrowness/R-NamedSeedSelectionBias/R-ProductionCandidateScarcity/R-KoreanR1SourceGap/R-LiveRunReproducibility·종결 0. **다음 hard blocker=operator date-pinned event+승인된 bounded live run→reviewer contact→actual returned labels.** production_gold_count 0 불변.

**ADR#83 — date-pinned live query plumbing + bounded live run + production candidate freeze attempt (operator event 미제공·실 live 미실행):**

- **query target wiring(§B·§6)**: 신규 `live_query_target.build_live_query_target`(PURE·network 0)가 operator named_entity+event_phrase→정확 `query_text`·occurrence_date(D)→절대 윈도우 [D, D+1](`as_of_anchor=D+1`·time_window 1d)·검증 실패(broad/placeholder/비-ISO/pool empty/미wired) fail-closed. **query_hint 는 기록만**(실행 query 는 항상 entity+phrase 포함→anchor 유실 방지). **date_pinned=True 여도 `event_occurrence_verified=False`·`same_event_asserted=False`**(occurrence_date=operator 주장·발생/같은 사건은 MERGE_GATE).
- **isolated executor(§7·§8)**: `execute_date_pinned_bounded_live_run` hard guard — target 미wired/`query_text` 빈값이면 live 실행 0(**curated fallback 으로 떨어지지 않음**·fail-closed). wired 시에만 검증된 targeted-layer 패턴 미러[`cross_source_live_overlap_smoke`(topic=query_text·today=as_of_anchor·emit_recall_probe)→`run_r1_production_candidate_acquisition(acquire_fn=lambda:smoke)`]로 live-derived publishable×publishable freeze 시도. `cross_source_live_overlap_smoke` 에 `today` 절대 윈도우 스레딩(additive·기본 None=기존 동작). **`LIVE_QUERY_TARGET_WIRED=True`(plumbing test-locked 후)**·단 live 실행은 여전히 operator event valid ∧ live_query 승인 ∧ pool≥2 요구.
- **orchestrator + internal ops(§11)**: `r1_bounded_live_breadth_run` 에 `operator_event` 배선+§7 binding classifier(missing_operator_event/invalid_date_pin/target_not_wired/no_opt_in/no_credentials/host_gate/no_results/no_cross_source/no_routing/candidates/frozen)+`InternalOpsDatePinnedLiveRunFrontier`(dict==pydantic==TS **30==30==30**·named_entity/event_phrase 전문·per-pair score/same_event/PII/secret 미노출)·`GET /api/internal/ops/r1-date-pinned-live-run`(read API live 0). 필수 copy 7(operator event 필요·occurrence=operator 주장≠fact·date-pin≠발생 증명·live query=operator event≠curated fallback·freeze=worklist≠truth·gold 0·R2~R7 No-Go).
- **live 정책(§1·§5·미실행)**: 이번 /compact 에 구체적 operator date-pinned event 미제공→`operator_event_provided=False`·`blocked_reason=missing_operator_date_pinned_event`·`live_query_executed=False`·snapshot 미작성(`not_written_no_live_run`)·secret 0·raw body 0.
- **잔여**: 신규 R-LiveQueryTargetDrift(LOW)·부분진전 R-DatePinnedEventAvailability(operator event validation·date≠발생 증명·종결 금지)/R-ProviderPairNarrowness(target wired guardian/nyt)/R-ProductionCandidateScarcity(freeze 실행 경로 완성·live-derived 0)/R-LiveRunReproducibility(snapshot 설계만)·종결 0. **다음 hard blocker=operator 가 date-pinned event 제공+bounded live run 승인→live-derived freeze→reviewer contact→actual returned labels.** production_gold_count 0 불변.

**ADR#84 — date-pinned bounded live run + production candidate freeze attempt + reviewer handoff bridge (첫 실 live run 실행·provider date-window fidelity 결손 발견):**

- **첫 실 live run(§B)**: operator 가 첫 구체 date-pinned event(U.S. Supreme Court asylum metering·2026-06-25·live_approved) 제공 → `build_live_query_target` wired + credential present(secret-safe) 검증 후 `execute_date_pinned_bounded_live_run(host_gate=real)` → **executed·call 2**(guardian/nyt ok·`credential_value_exposed=False`·raw body 0·host/rate 준수)·cross-source publishable(article×article) 비교쌍 **100**·near/hard/fingerprint 0·max jaccard 0.0625·routing candidate 0→`production_candidate_status=blocked_no_publishable_pairs`(§5 `live_no_routing_candidates`)·freeze 0.
- **근본 원인 분해(§2·"원인을 분해하라")**: 간결 query_hint 재실행→동일 결과(query 장문성 아님)→반환 헤드라인 직접 확인→전부 2026-06-28 당일(asylum 판결 무관)→오프라인 URL 캡처→`from-date=2026-06-25&to-date=2026-06-26`(guardian)·`begin_date=20260625&end_date=20260626`(nyt) **정확** → **provider 가 정확한 date window 를 받고도 응답이 window 를 벗어나 out-of-window·**주제 무관** 기사 반환**(plumbing 정상·요청 window 가 응답 제약 못 함은 확정). **단 메커니즘 미확정**(adversarial MEDIUM-1): 주제까지 무관한 점은 date-filter 무시뿐 아니라 order-by=newest 지배·느슨한 q OR-매칭·in-window 보도 0 도 동등 시사·**통제실험(date-param 유/무·order-by 제거) 미수행**(신규 R-ProviderDateWindowFidelity·enforce_window 는 date 증상만·100 비교쌍은 무관한 동일자 뉴스).
- **보정/신규(§4·additive)**: `run_provider_query(enforce_window=)`(published_at 으로 [from_date,to_date] 밖 record drop·전부 drop→`no_in_window_records`로 진짜 0 과 구분·기본 False=ADR#62~#82 byte-보존·date-pinned executor opt-in True)·신규 `reviewer_handoff_bridge.py`(freeze→contact **직전** package·freeze 없으면 `reviewer_handoff_ready=False`+blocker·**actual_sending_performed=False 불변**·PII/score 0)·신규 `sanitized_live_snapshot.py`(named_entity/event_phrase **hash**·aggregate(max_*)만·`outputs/live_snapshots/` **gitignored**·첫 live run snapshot 실작성·미실행 시 `not_written_no_live_run`)·orchestrator 배선·frontier +2 필드(`date_window_enforced`·`reviewer_handoff_ready`) **dict==pydantic==TS==mjs 32==32==32==32**·API allowed 32.
- **잔여**: 신규 R-ProviderDateWindowFidelity(MEDIUM·provider date window 무시·완화 enforce_window·in-window 수율 미측정·종결 금지)·부분진전 R-DatePinnedEventAvailability(첫 실 dated event+live 실행)/R-ProductionCandidateScarcity(100 비교쌍·out-of-window→freeze 0)/R-LiveRunReproducibility(첫 snapshot 실작성)/R-LiveQueryTargetDrift(operator query+enforce_window)·종결 0. **다음 hard blocker=window-honoring source(enforce_window 재실행 가능 event 또는 GDELT/Federal Register 어댑터 배선 ADR#85)→live-derived freeze→reviewer contact→actual returned labels.** **live 실행 성공 ≠ production candidate 확보**·freeze 0·production_gold_count 0 불변·R2~R7 No-Go.

**ADR#85 — provider date-window fidelity 통제실험(메커니즘 분해) + window-honoring source readiness + live-derived freeze 재시도:**

- **분석(§4)**: 호출 체인 원자 분해 — `_guardian_url`/`_nyt_url` 가 `order-by=newest`/`sort=newest` **하드코딩**(newest-지배 1순위 정황)·GDELT/Federal Register endpoint 는 registry `_SERVICE_CONFIGS` 에 이미 존재(`_registry_endpoint` 읽음·adapter 잔여=url+parser+등록)·GDELT `rate_limit_policy` min_interval 60s·실측 429 storm(rate-fragile).
- **통제실험(§8·paced·gate-respected·실 live)**: `provider_date_window_fidelity.py` 5-variant(original/no_date/relevance_order/exact_phrase/enforce_window)·`pace_seconds` 사전 대기(host floor 정직 준수·**bypass 아님**). Guardian 5·NYT 4 전부 실행(secret 0·raw body 0·11 governed 호출). **결과 전 비교 variant 동일**(반환 전부 당일 2026-06-29·요청 window [06-25,06-26] 밖·overlap 0.107/0.044·in-window 0): date_param **weak**(original==no_date)·order_newest **weak**(relevance==newest)·query_relevance **weak**(exact_phrase==original)·coverage zero_in_returned → **order-by=newest·loose-q 약화(이 run 비차별 lever·newest-dominance 미배제)**·**`date_filter_ignored` leading 가설(medium·cross-provider Guardian+NYT 일관)**·zero_in_window_coverage 잔존(low·date_filter_ignored 와 미분리·**confidence 절대 high 아님**). enforce_window 전부 drop→comparison_pair_count 0→**production candidate freeze 0·reviewer_handoff_ready False·gold 0·gap 200**.
- **구현(additive·byte-보존)**: 가산 knob `omit_date_window`/`order`(default byte-identical)·신규 `window_honoring_source_readiness.py`(GDELT/FR/SEC EDGAR 평가·**Federal Register 권고**·role guard 보존·adapter_wired_this_turn=False)·snapshot `control_experiment` block(aggregate·variant→class·제목 0)·frontier +6 필드 **dict==pydantic==TS==mjs 38==38==38==38**.
- **신규 blocker**: R-ControlExperimentRateBudget(LOW·host gate min_spacing 이 multi-variant probing 차단→pace_seconds 보정)·R-WindowHonoringSourceScarcity(MEDIUM·FR=official role-bridge 필요·GDELT rate-fragile/aggregator).
- **잔여**: 부분진전 R-ProviderDateWindowFidelity(통제실험 실행·order/q 제거·date_filter_ignored medium 로 좁힘·단 date_filter_ignored vs zero_coverage 미분리·**종결 금지**)·R-ProductionCandidateScarcity·R-LiveRunReproducibility. **다음 hard blocker=window-honoring source(Federal Register adapter·ADR#86) 또는 in-window 보도 실재 event→date_filter_ignored vs zero_coverage 최종 분리+same-event 수율 실측→live-derived freeze→reviewer contact→actual returned labels.** **통제실험 실행 ≠ 메커니즘 완전 확정**·freeze 0·production_gold_count 0 불변·R2~R7 No-Go.

**ADR#86 — Federal Register window-honoring adapter 실배선 + official×news role-bridge (구현 완료·live_verified):**

- **adapter(`provider_query_adapters.py` additive)**: `FEDERAL_REGISTER_ADAPTER`(provider_id="federal_register"·query_capable=True·**auth_required=False**·required_env_vars=()·fetch_implemented=True·supports_time_window=True·max_records=25·rate_limit_policy_id="federal_register"·host="www.federalregister.gov"·host_min_spacing_seconds=**3**). endpoint 는 registry `_SERVICE_CONFIGS` 에 이미 존재(`https://www.federalregister.gov/api/v1/articles.json`·key-free). **byte-보존 2-set 분리**: `ALL_ADAPTER_PROVIDERS`(dispatch 전체·+federal_register)/`ADAPTER_WIRED_PROVIDERS`(news-pairing·official 제외=`frozenset(_ADAPTERS)-_OFFICIAL_ROLE_ADAPTERS`) → guardian×nyt URL/news pool/executor 무변경.
- **url builder `_federal_register_url`**: params `conditions[term]=topic`·`conditions[publication_date][gte]=from_date`·`conditions[publication_date][lte]=to_date`(omit_date_window 시 제외)·`per_page=max_records`·`order=newest|relevance`(order knob)·`fields[]=title,html_url,publication_date,abstract,document_number`. urlencode 가 bracket 을 percent-encode 하나 FR API 수용(실측). **명시 범위 필터 → date-honoring live_verified(아래)**.
- **parser `parse_federal_register_items`**: `data["results"][].{title, html_url, publication_date}` → `_rec(record_type="official_record", source_id="federal_register", title≤512, canonical=html_url, published=publication_date, body_state="present")`·role=**official**(event_ingest_pipeline `official_record`→official·authority 5·anchor-eligible)·abstract/본문 미저장. **버그 수정(실측)**: FR 은 count==0 시 "results" 키를 생략({count,description}만)→count 키 존재 시 `[]`(no_records)·count 도 없으면 None(parser_error). `_ADAPTERS`/`_URL_BUILDERS`/`_PARSERS` 등록.
- **FR live smoke(`federal_register_live_smoke.py`·§10)**: bounded·key-free·governed·raw body 0. status 어휘(fr_live_not_run/ok_in_window/ok_no_records/out_of_window/parse_error/http_error/rate_blocked)·date_filter_capability(documented_unverified→live_verified/live_weak/live_no_records). **실 live 결과**: operator window [06-25,06-26] — "asylum metering" 31건(필터 미적용)→**0건(필터 적용)**·"enforcement" **25/25 in-window·out-of-window 0 → live_verified**. → **FR date filter 가 응답을 실제 제약**(Guardian/NYT date_filter_ignored 와 정반대).
- **official×news role-bridge(`official_news_role_bridge.py`·별도 모듈·guard 약화 금지)**: `discover_overlap`(news×news title-Jaccard)에 섞지 않고 **별도 PURE 모듈**로 격리. official(FR) × news(guardian/nyt) 중 **date 근접 + entity/action token 공유**(title-Jaccard 미사용·둘 다 floor 이상)면 `bridge_candidate`(reviewer-routing only). `same_event_asserted/merge_allowed/kg_edge_allowed/public_iu_allowed=False`·**단일 score 미생성**(feature 만)·official 단독 production candidate 금지·freeze_eligible 은 양측 in-window 일 때만. community/market/catalog/search anchor 금지 불변.
- **tests(실구현)**: test_provider_query_adapters +8(FR url date params/order/omit·no-auth key-free·parser shape·count=0·enforce_window)·test_official_news_role_bridge 9·test_federal_register_live_smoke 9(+2 host_gate_blocked/max_records)·test_r1_bounded_live_breadth_run +1. frontier +8 dict==pydantic==TS==mjs 46·API allowed 46. backend 전체 1732p·secret 0.
- **risk(실측)**: FR 반환물=규제문서(rules/notices/enforcement)라 일반 news event 와 topical match 희소(date-honoring 은 live_verified 이나 official×news same-event 수율 0·R-OfficialNewsDomainMismatch)·GDELT 는 rate/attribution 미해소로 ADR#87+ 범위.

**ADR#87 — regulatory-class event seed bank + official×news live acquisition + production candidate freeze 경로 (구현 완료·실 live 미실행·freeze 경로 결정론 검증):**

- **seed bank(`regulatory_event_seed_bank.py`·신규)**: `validate_regulatory_seed` 가 official_provider=federal_register·publishable news provider(guardian/nyt·community/market/catalog reject)·named agency/entity(placeholder `<...>`/operator fills 거부)·action_phrase·ISO date_window(start≤end)·allowed regulatory domain(10종: federal enforcement action·agency final/proposed rule·major settlement·public health/safety·environmental/financial enforcement·consumer protection·immigration/asylum notice·trade/sanction notice)·non-broad topic(broad denylist + generic 규제어휘 enforcement/immigration/rule/settlement/sanction 등)을 **모두** 요구·결정론 reject. **official_query≠news_query 분리**(FR 공식 어휘 vs journalistic 보도 어휘). `_curated_regulatory_seed_bank`: EPA final rule emissions(live-selectable·제안 window)·SEC enforcement/FDA safety/OFAC sanction(respondent/product/target 미특정 template·operator fill 필요). broad reject 자가검증 6/6·provenance=code_proposed_regulatory_shape·operator_must_confirm_actual_event·same_event 0. 17 test.
- **acquisition(`official_news_live_acquisition.py`·신규)**: `run_official_news_live_acquisition(seed, *, live_approved=False, ...)` — 기본 시도 0(blocked_no_live_opt_in·network 0). live_approved=True 일 때만: ① FR official(`run_federal_register_live_smoke`·key-free·in-window 필터)·② guardian/nyt news(`run_provider_query`·**enforce_window=True**·Guardian/NYT date_filter_ignored hedge)·③ `build_official_news_bridge`·④ `iter_freeze_eligible_record_pairs`. **9-state 분류**: invalid_regulatory_seed/blocked_no_live_opt_in/provider_unavailable/blocked_host_gate/blocked_rate_limit/official_no_records/news_no_records/no_in_window_news/no_official_news_overlap/official_news_bridge_candidates_found/production_batch_frozen. freeze-eligible 후보면 official×news smoke(packet_rows: source_type_left=official·right=article·title 포함) → `run_r1_production_candidate_acquisition(acquire_fn=)` **무수정 freeze**(official+article 둘 다 `_PUBLISHABLE_PRODUCTION_ROLES`) → `build_reviewer_handoff_bridge`. `build_official_news_reviewer_instruction`(official=authoritative evidence·news=public reporting·broad topic/agency 만으로 same_event 금지·date+specific action 필요). `sanitized_official_news_acquisition`(aggregate count/status only·title/url/instruction 본문 제외). 14 test(freeze 통합 포함).
- **bridge freeze iterator(`official_news_role_bridge.py` additive)**: `_evaluate_official_news_pair`(per-pair 술어를 build_official_news_bridge 와 공유·출력 byte-identical)·`iter_freeze_eligible_record_pairs`(freeze worklist 입력·진단 candidate[title-free]이 아니라 원본 record[title 포함] 반환·reviewer 가 official 증거 title vs news 보도 title 직접 비교 필요·snapshot/frontier 에는 안 감). +4 test.
- **orchestrator/frontier(+5·`r1_bounded_live_breadth_run.py`·`internal_ops.py`)**: `official_news_acquisition_result` 주입 param + `build_regulatory_event_seed_bank`(network 0·항상 산출) → `InternalOpsDatePinnedLiveRunFrontier` +5 필드(regulatory_seed_bank_status·selected_regulatory_seed_id·official_news_live_status·official_news_production_candidate_status·official_news_reviewer_handoff_ready) **dict==pydantic==TS==mjs 51==51==51==51**·API allowed 51·required_copy +2("Official record alone is not a production cross-source candidate"·"A regulatory-class seed needs an agency/entity, an action, and a confirmed date window"). acq 주입 시 FR live + bridge sub-result 가 ADR#86 필드도 파생.
- **freeze 결과(정직)**: 실 live 미실행(operator 가 실 FR+news 동시 보도 regulatory event 미제공)→실 official×news in-window same-event pair 0→실 freeze 0·gold 0·gap 200·reviewer_handoff_ready False(실 live). **freeze 경로는 fake transport 로 결정론 검증**(production_candidate_batch_ready=True·candidate_provenance=live_derived·production_gold_count 0).
- **tests(실구현)**: regulatory_event_seed_bank 17·official_news_role_bridge +5(iter_freeze_eligible+golden byte-identity)·official_news_live_acquisition 15·r1_bounded_live_breadth_run +1. **backend 전체 1770p/101skip/0fail**·frontend tsc0/lint0/test81·secret 0·ruff 0.
- **risk(실측)**: 실 same-subject regulatory live run 미실행→실 yield 0(R-OfficialNewsDomainMismatch 부분진전)·curated seed↔real event 대응 미검증(신규 R-RegulatorySeedQuality)·GDELT 는 rate/attribution 미해소로 ADR#88+ 범위.

**ADR#88 — operator-confirmed regulatory event intake + reviewer contact readiness + official×news label intake readiness (구현 완료·실 operator event 미제공·intake/contact/label readiness 경로 결정론 검증):**

- **operator intake(`operator_regulatory_event_intake.py`·신규)**: `validate_operator_confirmed_event(payload)` 가 §8 필드(seed_id·operator_confirmed·confirmed_by·confirmed_at[ISO date/datetime]·agency_or_entity[placeholder/generic reject]·action_phrase[generic reject]·date_window_start/end[ISO·start≤end]·official_query·news_query·expected_news_angle·live_approved[키 존재])를 결정론 검증·operator same_event 단정 reject. `build_confirmed_seed_from_event`(provenance=operator_confirmed_event·bank_seed 에서 regulatory_domain/provider 기본값·event_occurrence_verified_by_code=False). `run_operator_regulatory_event_intake(payload=None, ...)`: payload None→not_provided(이번 턴 기본)·operator_confirmed≠true→blocked_operator_not_confirmed·무효(필드/shape)→blocked_invalid_confirmation·valid∧!live_approved→blocked_no_live_opt_in·valid∧live_approved→confirmed seed build 후 `run_official_news_live_acquisition` **무수정** 호출(ADR#87 engine byte-보존). operator confirmation=live-run 승인 게이트일 뿐 same_event/발생 truth 아님. 17 test.
- **contact readiness(`reviewer_contact_readiness.py`·신규)**: `build_reviewer_contact_readiness(handoff)` 가 reviewer_handoff_bridge 산출물(freeze 성공 시)을 contact-PRE readiness package(batch_id·candidate_count·official×news instruction·label_schema[core+optional annotation 분리·accepted_labels 단일출처]·expected_returned_file_names·validation_command·placement_guide·operator_checklist·manual_contact_steps)로 재패키징. **reviewer_contact_ready ≠ actual_sending_performed(=False)**·score/rationale/predicted_status/same_event truth/raw body hidden 구조적 강제·reviewer roster/raw PII/actual email 미포함(`_assert_pii_safe`). freeze 없으면 ready=False+blocked_reason. 15 test.
- **label intake readiness(`official_news_label_intake_readiness.py`·신규)**: synthetic official×news fixture(source_type official/article·dataset_source=synthetic·marked_synthetic)→`run_production_label_intake`(label_source=synthetic) 3 sub-scenario(multi 만장일치→synthetic gold·single→gold 아님·unsure→non-decisive)→schema 수용 증명 + **production_gold_count 0**(synthetic≠production·single/unsure≠gold). `validate_official_news_label_record`(§12: batch_id·pair_id·label[accepted+needs_more_context alias]·reviewer_id_or_anonymous_code + optional evidence_notes/role_confusion_flag/uncertain_flag·score/rationale/predicted_status/raw body/same_event truth 누출 reject). label 날조 0·actual_label_fabricated=False. 9 test.
- **orchestrator/frontier(+6·`r1_bounded_live_breadth_run.py`·`internal_ops.py`)**: `operator_event_intake_result`/`reviewer_contact_readiness_result`/`official_news_label_intake_readiness_result` 주입 param + contact readiness(handoff 파생·항상)/label intake readiness(network 0·항상) → `InternalOpsDatePinnedLiveRunFrontier` +6 필드(operator_event_status·operator_confirmed·confirmation_valid·confirmation_blocked_reason·reviewer_contact_ready·label_intake_readiness_status) **dict==pydantic==TS==mjs 57==57==57==57**·API allowed 57·required_copy +2("Operator confirmation is required before live regulatory acquisition"·"Reviewer contact readiness is not actual sending").
- **결과(정직)**: 실 operator-confirmed event 미제공→operator_event_status=not_provided·실 live 0·실 freeze 0·reviewer_contact_ready False·gold 0·gap 200. **intake→freeze→contact/label readiness 경로는 fake transport 로 결정론 검증**(test_18 engine 호출·operator-confirmed seed 전달·test_42~54 contact readiness·전송 0·test_55~63 label intake·gold 0).
- **tests(실구현)**: operator_regulatory_event_intake 17·reviewer_contact_readiness 15·official_news_label_intake_readiness 9·r1_bounded_live_breadth_run +1. **backend 전체 1812p/101skip/0fail**·frontend tsc0/lint0/test84·secret 0·ruff 0.
- **risk(실측)**: 실 operator-confirmed payload 미제공이 진전 hard gate(신규 R-OperatorConfirmedEventScarcity MEDIUM)·contact readiness≠sending 경계(신규 R-ReviewerContactPrematureLaunch LOW)·synthetic label fixture↔production gold 경계(신규 R-SyntheticLabelFixtureLeakage LOW)·GDELT 는 ADR#89+ 범위.

**ADR#89 — operator payload entrypoint(real↔example 분리·gitignored·PII fail-closed) + returned label dropbox readiness + reviewer contact launch checklist (구현 완료·실 operator payload 미제공·수신/접촉 직전 경계 봉인):**

- **operator payload entrypoint(`operator_regulatory_event_payload.py`·신규)**: `load_operator_regulatory_event_payload`(real gitignored JSON·없으면 not_provided·forbidden[secret/PII/score] 키 fail-closed 폐기·키명 카운트만)·`resolve_operator_payload_entrypoint`(load→intake gate·`is_example_payload` 로 example dummy 를 real 로 오인 차단·raw payload 본문 미재임베드)·committed `examples/operator_regulatory_event_payload.example.json`(operator_confirmed=false·live_approved=false·real 아님)·`.gitignore += inputs/operator_events/`.
- **returned label dropbox readiness(`returned_label_dropbox_readiness.py`·신규)**: dropbox(`outputs/reviewer_batch/<batch>/intake`·gitignored)·expected files/validation command 단일 출처(`build_intake_plan`)·실 `*.jsonl` 스캔(`scan_actual_reviewer_input`)·`actual_returned_label_count` 실 파일만(없으면 0)·`production_gold_count` 0·synthetic/single/unsure ≠ gold·`agreement_required_for_gold`.
- **reviewer contact launch checklist(`reviewer_contact_launch_checklist.py`·신규)**: contact readiness(ADR#88) ∧ dropbox readiness → `launch_ready`(freeze 없으면 False)·manual contact steps 7·`reviewer_roster_required_but_not_committed`·`actual_email_included=False`·**`actual_sending_performed=False`**·score/rationale/predicted/same_event/raw body hidden.
- **orchestrator/frontier(+5·`r1_bounded_live_breadth_run.py`·`internal_ops.py`)**: `operator_payload_entrypoint_result`/`returned_label_dropbox_readiness_result`/`reviewer_contact_launch_checklist_result` 주입 param(read API 는 real path 미독·default not_provided→GET 가 live 실행 0) → `InternalOpsDatePinnedLiveRunFrontier` +5(operator_payload_status·operator_payload_path_status·label_dropbox_ready·actual_returned_label_count·reviewer_contact_checklist_ready) dict==pydantic==TS==mjs **62**·API allowed 62·required_copy +2("Provide an operator-confirmed regulatory event payload before live acquisition"·"Returned label dropbox readiness is not production gold").
- **결과(정직)**: 실 operator payload 미제공(`inputs/operator_events/` ABSENT)→operator_payload_status=not_provided·실 live 0·실 freeze 0·reviewer_contact_checklist_ready False·actual_returned_label_count 0·gold 0·gap 200. **entrypoint→gate→engine→freeze→contact/dropbox 경로는 fake acquisition_fn/scan_fn 로 결정론 검증**(test_16 engine 1회 호출·operator-confirmed seed 전달·test_08/09 secret/PII payload fail-closed·test_37 freeze→launch ready·test_46~54 dropbox 실 label 0·gold 0).
- **tests(실구현)**: operator_regulatory_event_payload 16·returned_label_dropbox_readiness 12·reviewer_contact_launch_checklist 13·r1_bounded_live_breadth_run +1. backend +42·frontend node:test ops view 84→**87**(+3 ADR#89)·npm test 99·parity **62==62==62==62**.
- **risk(실측)**: 부분진전 R-OperatorConfirmedEventScarcity/R-ReviewerContactPrematureLaunch/R-SyntheticLabelFixtureLeakage/R-ProductionCandidateScarcity(전부 실 operator payload/labels 전까지 종결 금지)·신규 LOW R-OperatorPayloadPIILeakage/R-ReturnedLabelDropboxExposure/R-ExamplePayloadAsRealEventLeakage·종결 0.

**ADR#90 — operator payload authoring helper + live no-yield taxonomy + operator-confirmed live runner + Hot Intelligence Post / agent hotness / community interaction future-gate 계약 (구현 완료·contract-only·runtime 비활성·실 operator payload 미제공·실 live 0):**

- **operator payload authoring helper(`operator_payload_authoring_helper.py`·신규)**: operator 가 실 payload 를 *작성*하도록 안내(template readiness·next action·forbidden[secret/PII/score] 키 가드)·raw payload 본문 미재임베드·실 payload 없으면 not_provided.
- **live no-yield taxonomy(`live_no_yield_taxonomy.py`·신규)**: live run 이 0 산출일 때 원인을 결정론 분류(no operator payload·no in-window·no official×news overlap·no freeze 등)·`live_no_yield_taxonomy_status` 단일 출처.
- **operator-confirmed live runner(`operator_confirmed_live_runner.py`·신규)**: payload→intake gate→live acquisition→freeze 를 한 경로로 묶되 operator 미확인/미제공이면 fail-closed(실 live 0·network 0).
- **Hot Intelligence Post / agent hotness / community interaction 계약(`hot_intelligence_post_contract.py`·`agent_hotness_reasoning_contract.py`·`community_interaction_future_gate.py`·신규·contract-only·runtime No-Go)**: 이 제품이 "raw news feed 가 아니라 community-style intelligence web product"임을 계약으로 고정 — community reaction=`reaction_to` 전용(절대 event anchor 아님)·Hot Post/comment-reply runtime 은 evidence/gold/merge gate 통과 전 비활성. docs `5_REFERENCE/HOT_INTELLIGENCE_POST_CONTRACT.md`·`AGENT_HOTNESS_REASONING_CONTRACT.md`·`COMMUNITY_INTERACTION_FUTURE_GATE.md`.
- **fix + orchestrator/frontier(+6)**: `reviewer_contact_launch_checklist` + `returned_label_dropbox_readiness` batch_id 일관성 수정(GAP4/§15). frontier +6 필드(operator_payload_template_ready·operator_payload_next_action·live_no_yield_taxonomy_status·hot_intelligence_post_contract_status·agent_hotness_contract_status·community_interaction_gate_status) → `InternalOpsDatePinnedLiveRunFrontier` **dict==pydantic==TS==mjs 68==68==68==68**(was 62).
- **결과(정직)**: 실 operator payload 미제공(`inputs/operator_events/` ABSENT)→실 live 0·official/news records 0·bridge 0·freeze 0·production_gold_count 0·current_r1_gap 200·R1 FAIL·R2~R7 No-Go. 3 계약은 contract-only(LLM/embedding/merge/public IU/comment-reply runtime 0)·public Hot Post/comment-reply runtime 은 R1 gold + MERGE_GATE + public-IU gate + 11 community-interaction 요구 충족 후에만 개방.
- **risk(실측)**: 부분진전 R-OperatorConfirmedEventScarcity/R-ProductionCandidateScarcity(실 operator payload/labels 전까지 종결 금지)·contract-only 계약은 runtime 비활성으로 신규 runtime risk 0·**계약 정의 ≠ runtime 활성·helper/taxonomy/runner 머신 무장 ≠ 실 operator payload.**

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
- **GroundTruth:** alembic **0004 구현됨**(S1: events/event_updates/event_cards.event_id, 2026-06-22). 0005~0007 **부재**(S2~). 위는 0005~ 작성 스케치다.

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

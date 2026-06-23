# Event Schema

## RawEvent

| 필드 | 타입 | 설명 |
|---|---|---|
| source | str | 수집 소스 식별자 (e.g. "reuters-rss") |
| url | str | 원본 URL |
| fetched_at | datetime | 수집 시각 (UTC) |
| raw_text | str | 원문 텍스트 |
| raw_metadata | dict | 소스별 추가 메타데이터 |
| raw_event_id | Optional[str] | DB raw_events.id. stream payload → agent pipeline 추적 키 (STEP 008A) |

```json
{
  "source": "reuters-rss",
  "url": "https://example.com/news/1",
  "fetched_at": "2026-05-23T10:00:00Z",
  "raw_text": "Tensions rise in the Strait of Hormuz as...",
  "raw_metadata": {"category": "world"}
}
```

## NormalizedEvent

| 필드 | 타입 | 설명 |
|---|---|---|
| id | str (uuid4) | 고유 식별자 |
| source | str | 소스 식별자 |
| title | str | 정규화된 제목 |
| body | str | 본문 |
| occurred_at | datetime | 사건 발생 시각 |
| language | str | 언어 코드 (기본 "en") |
| hash | str | 중복 탐지용 SHA-256 prefix (16자) |

```json
{
  "id": "a1b2c3d4-...",
  "source": "reuters-rss",
  "title": "Tensions rise in the Strait of Hormuz",
  "body": "...",
  "occurred_at": "2026-05-23T09:55:00Z",
  "language": "en",
  "hash": "a3f1e9d2c7b4..."
}
```

## FinalEventCard

| 필드 | 타입 | 설명 | PG 컬럼 타입 |
|---|---|---|---|
| id | str (uuid4) | 고유 식별자 | UUID PK |
| title | str | 최종 제목 | VARCHAR |
| summary | str | 요약문 | VARCHAR |
| theme | str | 주제 (geopolitics/economics/technology/climate/health) | VARCHAR, INDEX |
| sectors | list[str] | 관련 섹터 목록 | JSONB, GIN INDEX |
| entities | list[str] | 주요 엔티티 목록 | JSONB |
| impact_path | str | 영향 경로 설명 | VARCHAR |
| evidence | list[str] | 근거 출처 목록 | JSONB |
| confidence_score | float (0–1) | 신뢰도 점수 | FLOAT, CHECK(0..1) |
| status | "published"\|"hold" | 게시 상태 | VARCHAR, INDEX |
| created_at | datetime (tz-aware) | 생성 시각 | TIMESTAMPTZ, INDEX DESC |

ORM 전용 추가 컬럼: `updated_at` (TIMESTAMPTZ) — Pydantic 스키마 미포함.

## Milvus Vector Schema (STEP 006)

collection: `event_embeddings`, dim: 1536, index: IVF_FLAT / COSINE / nlist=128

| 필드 | 타입 | 설명 |
|---|---|---|
| pk | INT64, auto_id, primary | Milvus 내부 PK |
| event_id | VARCHAR(64) | FinalEventCard.id |
| card_id | VARCHAR(64) | 현재 event_id 동일; 향후 분리 대비 |
| text_hash | VARCHAR(64) | sha256(title+summary)[:32] |
| theme | VARCHAR(64) | 단일 string |
| source_type | VARCHAR(32) | 현재 "agent" 고정 |
| created_at | INT64 | unix timestamp |
| metadata_json | VARCHAR(2048) | sectors/entities JSON |
| embedding | FLOAT_VECTOR(1536) | cosine 검색 벡터 |

```json
{
  "id": "x9y8z7w6-...",
  "title": "Tensions rise in the Strait of Hormuz",
  "summary": "Military vessels from multiple nations...",
  "theme": "geopolitics",
  "sectors": ["energy", "defense"],
  "entities": ["Iran", "US Navy", "Strait of Hormuz"],
  "impact_path": "medium-term oil supply disruption risk",
  "evidence": ["reuters.com/...", "bbc.com/..."],
  "confidence_score": 0.82,
  "status": "published",
  "created_at": "2026-05-23T10:01:00+00:00"
}
```

## raw_events Table (STEP 007)

| 컬럼 | 타입 | NULL | 기본값 | 비고 |
|---|---|---|---|---|
| id | UUID | NO | uuid.uuid4 | PK |
| source_type | VARCHAR(32) | NO | — | "rss" / 미래: dart/sec/web |
| source_name | VARCHAR(128) | NO | — | feed 식별자 (e.g. bbc_world) |
| external_id | VARCHAR(512) | YES | NULL | RSS guid/link fallback |
| url | VARCHAR(2048) | NO | — | canonical link |
| title | VARCHAR(1024) | YES | NULL | RSS title |
| raw_text | TEXT | NO | '' | HTML 제거된 summary — 본문 저장 금지 |
| published_at | TIMESTAMPTZ | YES | NULL | UTC 변환 |
| collected_at | TIMESTAMPTZ | NO | now() | |
| content_hash | VARCHAR(64) | NO | — | sha256(dedup key) |
| theme_hint | VARCHAR(64) | YES | NULL | sources config에서 주입 |
| status | VARCHAR(16) | NO | 'collected' | collected→enqueued→processed\|failed (STEP 008A 완료) |
| enqueued_msg_id | VARCHAR(64) | YES | NULL | Redis XADD msg id |
| error_reason | VARCHAR(512) | YES | NULL | failed status 시 |
| event_card_id | UUID | YES | NULL | 처리 완료 후 생성된 FinalEventCard.id (STEP 008A) |
| processed_at | TIMESTAMPTZ | YES | NULL | processed/failed 전이 시각 (STEP 008A) |
| raw_metadata | JSONB | NO | '{}' | RSS tags/feed metadata |
| created_at | TIMESTAMPTZ | NO | now() | |
| updated_at | TIMESTAMPTZ | NO | now() | |

**UNIQUE 제약**: `content_hash` + partial `(source_type, external_id) WHERE external_id IS NOT NULL`

**인덱스**: collected_at DESC, status, source_type, published_at DESC NULLS LAST, raw_metadata GIN, event_card_id, processed_at

## OpenSearch Document: `event_cards` (STEP 009)

OpenSearch에 색인되는 document 구조 (source of truth는 Postgres).

| 필드 | OpenSearch 타입 | 내용 |
|---|---|---|
| `card_id` | keyword | FinalEventCard.id (UUID string) |
| `title` | text + keyword subfield | 제목 |
| `summary` | text | 요약 |
| `text_all` | text | title + summary + entities + sectors 합산 (검색 전용) |
| `theme` | keyword | 테마 (e.g. geopolitics) |
| `status` | keyword | published / hold |
| `sectors` | keyword[] | 섹터 배열 |
| `entities` | keyword[] | 엔티티 배열 |
| `confidence_score` | float | 신뢰도 0.0-1.0 |
| `created_at` | date | ISO 8601 |

인덱스 이름: `event_cards` (설정: `OPENSEARCH_EVENT_INDEX`).
Analyzer: standard (기본). 한국어 nori는 STEP 010+ TODO.

## Comment

| 필드 | 타입 | 설명 | PG 컬럼 타입 |
|---|---|---|---|
| id | str (uuid4) | 고유 식별자 | UUID PK |
| event_id | str (uuid4) | 연관 이벤트 ID | UUID FK → event_cards.id ON DELETE CASCADE |
| author | str | 작성자 | VARCHAR |
| body | str | 댓글 내용 | VARCHAR |
| created_at | datetime (tz-aware) | 작성 시각 | TIMESTAMPTZ |

인덱스: `ix_comments_event_id_created` (event_id, created_at)

---

# Part 2 — Event 타임라인 모델 (🟡 S1 토대 구현됨 / S2~ 설계)

> ⚠️ **상태 배너:** **§Event / §EventUpdate / §event_cards 의미 전환은 ✅ S1 구현됨**(events/event_updates 테이블 + event_cards.event_id nullable FK + alembic 0004, 2026-06-22 turn8 · `backend/app/models/event_timeline.py` + 회귀 17). **§cluster_event_map / §event_links 도 ✅ S2a 구현됨**(alembic 0005 + `backend/app/models/event_resolution.py` + ORM/Pydantic, 2026-06-22). **CRUD 영속층(event_timeline_service)은 ✅ S2d 구현됨**(create/append-only/get/set_snapshot 쌍방향강제/cluster_event_map 조회·기록/event_links possible 적재/apply_routing — `backend/app/services/event_timeline_service.py`, ADR#19). **통합 파이프라인(event_resolution_pipeline)은 ✅ S2e 구현됨**(실 cross_source_dedup→resolver→apply_routing 배선; 통합 로직 E2E 입증=in-memory fake session: 2번째 보도→append·transitive 약신호 보류·멱등·FSD·sanitize·동시 CREATE rollback). **삭제 정책 ADR#20**(app no-delete + status 라이프사이클 + **FK RESTRICT**: events.status·event_links.status 전환, hard-delete 미제공). **✅ live-PG 검증됨(S2e, ADR#21):** alembic 0001~**0006** 실 Postgres up/down + S2e E2E(CREATE/APPEND/HOLD·멱등·FSD·sanitize)·**2-세션 동시 CREATE orphan 0**·**FK RESTRICT 삭제 차단** 실 DB 입증(`test_event_resolution_live_pg` 14). 아래 §Entity ~ §Config(entities/EvidenceNode/Comment 확장 등) + alembic 0007 은 **S4~/S8/S9 미구현 설계**다. Part 1(RawEvent/NormalizedEvent/FinalEventCard/raw_events/Comment)도 현재 DB 사실이다. 권위: 결정=`_DECISIONS/2026-06.md` ADR#16/#18/#19/#20/#21/#22/#23, 구현스펙=`2_ROADMAP/19`, 위험=`_RISK`(R-EventModelMigration/R-FalseMerge/R-EventTimelineS2Hardening). 모든 신규 컬럼 nullable, 마이그레이션 additive(downgrade 제공). **합산 green + 정합성 불변식**이 무조건 acceptance. **✅ C live wiring(ADR#22, 2026-06-22):** `event_ingest_pipeline`(수집 후보→cross_source_dedup→candidate_for→resolver→events/event_updates; flag `EVENT_RESOLUTION_ENABLED` 기본 off; 후보 격리; 본문/PII 차단) + orchestration `event_resolution_sink` 주입 seam. event_cards **무변경 병행**, `event_cards.event_id` 자동연결은 이월(set_snapshot 명시 연결만). **✅ D-1 운영 결선(ADR#23, 2026-06-22):** `backend/app/tools/run_event_orchestration.py`(backend-side composition root: 전용 NullPool 엔진 생명주기 + sink 주입 → ingestion `main(event_resolution_sink=)` 위임; ingestion→backend import 0) + `--event-resolution`/`EVENT_RESOLUTION_ENABLED` 게이트 + live-PG 로 실 sink CREATE→APPEND 입증 → 운영 runner 가 Event 영속 *능력* 확보. **✅ D-2a Event 타임라인 read API(ADR#24, 2026-06-23):** `/api/events/timeline`(list[Event])·`/api/events/timeline/{id}`(EventTimelineResponse=event+updates) additive endpoint(`EVENT_TIMELINE_API_ENABLED` flag·held degenerate(cluster_event_map 미매핑) 제외·레거시 event_cards 무영향). **✅ D-2b frontend 렌더(ADR#25, 2026-06-23):** Next.js `/events/timeline` 목록/상세 page+컴포넌트가 read API 소비(안전 evidence: http/https 게이트·allowlist 6키·source_refs 미렌더; flag off→graceful). 스키마 DDL 무변경(렌더 전용). 기존 event_cards UI 무변경. **렌더 능력 확보·실제 노출은 flag on+데이터(D-2c) 전제.** **✅ D-2b 하드닝(ADR#26, 2026-06-23):** 공개 read 응답에 `PublicEvent`(primary_entity_ids/snapshot_card_id 제외)·`PublicEventUpdate`(source_refs 제외)·`PublicEventTimelineResponse` 도입 — `/timeline`·`/timeline/{id}` 가 내부 식별자(source_refs·entities FK·event_cards FK)를 wire 에서 구조적 차단(allowlist 별도 스키마; 비공개 `EventTimelineResponse` 제거; heat 유지). 내부 `Event`/`EventUpdate` 는 해당 필드 보유(write/내부 조회용). + 테스트 provider mock 격리(conftest, embedding+LLM 캐시, `.env` 비의존). **잔여:** Docker 데모(D-2c)·주기 auto-trigger·실 production-validation 1회 Event 누적·event_cards↔Event 자동연결·약신호 cluster_id 안정키·3엔진 색인 정합 · heat 4신호(S2.5) · merge_score entity/domain 축(S4) · LLM 보조 레이어(경계만 개방).

## Event (events 테이블 — ✅ 구현됨 S1, 안정 주제, ADR#16 / SPEC §1.1)

| 컬럼 | 타입 | NULL | 기본 | 설명 |
|---|---|---|---|---|
| id | UUID | NO | uuid4 | PK, 사건 영속 식별자 |
| canonical_title | VARCHAR(1024) | NO | — | 대표 제목(최신 Update가 갱신 가능) |
| status | VARCHAR(16) | NO | 'active' | active / dormant / closed (heat 감쇠로 자동 전이) |
| first_seen_at | TIMESTAMPTZ | NO | now() | 최초 보도(FSD). 더 이른 보도 발견 시 과거로만 당김 |
| last_update_at | TIMESTAMPTZ | NO | now() | 마지막 Update 시각 |
| heat | FLOAT | NO | 0.0 | 시계열 활성도(0~1), §heat 산식 |
| domains | JSONB | NO | '[]' | 상위 통제어휘 도메인[] (§domains) |
| tags | JSONB | NO | '[]' | free-form 엔티티/태그[] |
| primary_entity_ids | JSONB | NO | '[]' | entities.id FK[] |
| snapshot_card_id | UUID | YES | NULL | 현재 노출 스냅샷 카드(event_cards.id) |
| created_at / updated_at | TIMESTAMPTZ | NO | now() | |

인덱스: `heat DESC`, `status`, `last_update_at DESC`, `domains` GIN, `first_seen_at`.

## EventUpdate (event_updates 테이블 — ✅ 구현됨 S1, **append-only** 변화분, SPEC §1.2)

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| id | UUID | NO | PK |
| event_id | UUID | NO | FK → events.id (**RESTRICT**, 0006 — 감사 이력 보호) |
| observed_at | TIMESTAMPTZ | NO | 이 변화가 관측된 시각 |
| delta_summary | VARCHAR | NO | "유가 +4% 반응" 같은 변화 요약 |
| evidence | JSONB | NO | 이 Update의 EvidenceNode[] (§EvidenceNode) |
| added_domains | JSONB | NO | 이 Update로 새로 엮인 도메인[] |
| source_refs | JSONB | NO | raw_events.id[] / cluster_id |
| heat_delta | FLOAT | NO | 이 Update의 heat 기여분 |
| created_at | TIMESTAMPTZ | NO | |

인덱스: `(event_id, observed_at DESC)`. **불변식: INSERT만(UPDATE/DELETE 금지)** → 가역성·감사.

## event_cards 의미 전환 (비파괴, SPEC §1.3)
- 기존 컬럼 전부 유지. **추가만**: `event_id UUID NULL` (FK → events.id).
- 의미: 카드 = "특정 Event의 한 스냅샷". `event_id` NULL인 기존 카드 = Event 1개짜리 degenerate case(정상 동작).

## cluster_event_map / event_links (SPEC §2.2 — ✅ **S2a 구현됨: alembic 0005**)

> ✅ 아래 두 테이블은 **alembic 0005(S2a, 2026-06-22)에서 생성됨**(`backend/app/models/event_resolution.py` ClusterEventMapORM/EventLinkORM + Pydantic ClusterEventMap/EventLink). S2c `event_resolver` 가 라우팅 결정을, **S2d `event_timeline_service.apply_routing` 이 영속 적용**(map_cluster=단일출처 on_conflict_do_nothing, hold_link=event_links possible)을 수행한다. event_links 는 약신호/clique 미달 멤버를 자동병합 금지로 보류(possible→사람/추가신호로 confirmed/rejected/merged, 가역 — ADR#19).

| cluster_event_map | 타입 | 설명 |
|---|---|---|
| cluster_id | VARCHAR | PK (cross_source_dedup 출력) |
| event_id | UUID | FK → events.id (라우팅 영속화) |

| event_links | 타입 | 설명 |
|---|---|---|
| id | UUID | PK |
| event_id / linked_event_id | UUID | 연결 양단 |
| status | VARCHAR(12) | possible / confirmed / rejected / merged |
| reason | VARCHAR | 약신호 보류 사유(자동병합 금지) |

## Entity (entities 테이블 — 1급 객체, SPEC §3.1)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | UUID | PK |
| canonical_name | VARCHAR | 정규 명칭("Anthropic") |
| entity_type | VARCHAR | company / gov_agency / product / person / place / regulation |
| aliases | JSONB | 별칭/표기변형[] |
| external_ids | JSONB | 신뢰 식별자(wikidata QID, 공식 도메인) — **앵커** |
| domains | JSONB | 이 엔티티가 속한 상위 도메인[] |
| official_sources | JSONB | Authority Source Graph 노드[] (17 §Authority) |
| status | VARCHAR | active / candidate(미검수) / merged |
| created_at / updated_at | TIMESTAMPTZ | |

인덱스: `canonical_name`, `entity_type`, `aliases` GIN, `external_ids` GIN.
> **해소 전략(SPEC §3.2 + orchestrator 인사이트):** 앵커 우선 매칭 → 별칭 정규화 → 모호 시 candidate(자동병합 금지). candidate **활성화**(한 candidate→active, 저위험: role 다양성≥2 권위 + change-confirmed 앵커로 결정론 자동승격)와 **병합**(여러 surface→한 엔티티, 고위험: 사람 검수)을 분리.

## EvidenceNode (evidence JSONB 승격, SPEC §8.1 — 문자열 비파괴 호환)

기존 `evidence: list[str]` → `list[EvidenceNode]`(문자열도 계속 허용=degrade).

| 필드 | 타입 | 설명 |
|---|---|---|
| url | str | 증거 URL |
| source_type | str | official / community / news / government / structured / historical (source_role 7종 매핑, 신규분류 0) |
| role | str | 기존 7 roles에서 도출 |
| confidence | float | 0~1 |
| relation | str | supports / refutes / duplicates / context |
| observed_at | datetime | |

> 2단계 "증거↔증거(지지/반박)" 관계는 **Agent Debate Layer(19 §9)** 가 자연어로 생성. GraphRAG는 조건부(<1000 엔티티 금지, 09).

## Comment 확장 (5컬럼 additive, SPEC §9.1 — S9)

위 Part 1 Comment(author 1칸)에 **additive 추가**(기존 댓글 비파괴, server_default):

| 추가 컬럼 | 타입 | 설명 |
|---|---|---|
| author_type | VARCHAR(8) | 'user' / 'agent' (기본 'user') |
| agent_persona | VARCHAR(64) NULL | "energy-analyst" / "skeptic" / "geopolitics-desk" |
| reply_to | UUID NULL | 부모 comment(스레드) FK → comments.id |
| stance | VARCHAR(12) NULL | claim / counter / evidence / question |
| evidence_refs | JSONB | 발화 근거 EvidenceNode[] (게이트: 에이전트 발화는 비면 게시 거부) |

> 미수렴 쟁점은 `unresolved_pending_evidence` 상태로 — 새 Update append 시 재점화(무료 웹 알림 = 구독 없는 리텐션, BI 인사이트 #2).

## heat 산식 (SPEC §2.4 + orchestrator 인사이트 #3)

```text
heat(t) = heat(t-1)·exp(-Δt/half_life)              ← 시간 감쇠(단조 누적 폭주 방지)
        + Σ heat_delta(신규 Update)
heat_delta = w1·recency + w2·update_frequency
           + w3·corroboration_diversity + w4·domain_spread
```
- 기본 가중치 0.4 / 0.3 / 0.2 / 0.1 (설정값, 빈값=DEFAULT).
- **corroboration = 출처 수가 아니라 source_role 다양성 엔트로피**(에코챔버 방지: OFFICIAL+NEWS > COMMUNITY×5).
- heat → 차등 폴링 주기 = base_interval / (1 + heat·k), **단 rate-limit 하한(gdelt 60s 등)은 절대 clamp**(우회 금지).

## domains 통제어휘 카탈로그 (~20, 거버넌스 ADR로 확장, SPEC §4)

기존 8: `energy, finance, defense, technology, health, politics, commodities, transport`
신규 12: `insurance, diplomacy, shipping, agriculture, labor, climate, telecom, regulation, semiconductor, biotech, cybersecurity, media`
- 상위 = 통제어휘(닫힌 ~20, 필터·네비 일관성). 하위 `tags` = free-form 무제한(정밀 연관). `general` 폴백 보존.

## 데이터 예시 JSON (SPEC §15)

```json
// events 1행 (호르무즈)
{"id":"evt-7a3f","canonical_title":"호르무즈 해협 긴장 고조","status":"active",
 "first_seen_at":"2026-06-18T08:00:00Z","last_update_at":"2026-06-20T09:00:00Z","heat":0.61,
 "domains":["defense","energy","finance","diplomacy","insurance","shipping"],
 "tags":["tanker-seizure","oil-price","lloyds"],
 "primary_entity_ids":["ent-hormuz","ent-iran","ent-usnavy"],"snapshot_card_id":"card-v4-9b2c"}
```
```json
// event_updates (append-only, 위 Event에 1건 예시)
{"id":"upd-2","event_id":"evt-7a3f","observed_at":"2026-06-18T11:00:00Z",
 "delta_summary":"유가 +4% 반응","added_domains":["finance"],"heat_delta":0.21,
 "evidence":[{"url":"finnhub/...","source_type":"structured","relation":"supports","confidence":0.90}],
 "source_refs":["raw-014"]}
```
```json
// entities 1행 (Anthropic)
{"id":"ent-anthropic","canonical_name":"Anthropic","entity_type":"company",
 "aliases":["앤트로픽","Anthropic PBC","anthropic"],
 "external_ids":{"domain":"anthropic.com","wikidata":"Q..."},"domains":["technology"],
 "official_sources":[{"label":"blog","url":"anthropic.com/news","discovered_via":"sitemap","status":"active"}],
 "status":"active"}
```
```json
// Comment (에이전트 논쟁) — evidence_refs 비면 게시 거부(에이전트 한정)
{"id":"c1","event_id":"evt-7a3f","author":"energy-analyst","author_type":"agent",
 "agent_persona":"energy-analyst","reply_to":null,"stance":"claim",
 "body":"유가 반응은 공급 차질 우려가 과대평가됐을 수 있습니다.",
 "evidence_refs":[{"url":"finnhub/...","relation":"supports"},{"url":"iea/...","relation":"context"}]}
```

## Config 키 (`.env.example` 추가 제안, 빈값=DEFAULT 계약 — SPEC §23)

> `.env`는 열람/수정/커밋 안 함. 아래는 **`.env.example`에 추가할 키 이름 제안**(별도 diff로 사용자 승인). 모두 `config.py` model_validator "빈값=코드 기본" 계약 준수.

| 키 | 기본(코드) | 용도 |
|---|---|---|
| `LLM_PROVIDER` | "" (=off, mock) | LLM 수집 관여 on/off (이미 존재) |
| `EXPANSION_MAX_QUERIES_PER_EVENT` | 5 | 확장쿼리 K 상한 |
| `EXPANSION_MONTHLY_BUDGET_USD` | 0 (=무료만) | 유료검색 월 예산 |
| `EXPANSION_PER_EVENT_BUDGET_USD` | 0 | 사건당 유료 상한 |
| `DISCOVERY_DAILY_APPROVAL_QUOTA` | 0 (=발견 off) | 발견 입구 일일 쿼터(R-DiscoveryCostStarvation) |
| `HEAT_W_RECENCY/FREQ/CORROB/SPREAD` | 0.4/0.3/0.2/0.1 | heat 가중치 |
| `HEAT_HALF_LIFE_HOURS` | "" (=감쇠없음) | heat 시간 감쇠 |
| `CHANGE_POLL_INTERVAL_HOT/COLD_SEC` | 1800 / 86400 | heat별 차등 폴링 |
| `DEBATE_ENABLED` | false | 에이전트 논쟁 on/off (kill switch) |
| `DEBATE_MAX_DEPTH` | 4 | 논쟁 스레드 깊이 상한 |
| `SLM_BODY_FALLBACK_URL` | "" (=off) | 통신서버 SLM 엔드포인트 |
| `EVENT_MERGE_TIME_WINDOW_HOURS` | 48 | Event 병합 시간창(merge_score 4번째 축) |
| `AD_PAGE_NONSOURCE_RATIO_MIN` | "" (=게이트 off) | 광고 게재 페이지 비전문비율 하한(BI 인사이트 #6) |

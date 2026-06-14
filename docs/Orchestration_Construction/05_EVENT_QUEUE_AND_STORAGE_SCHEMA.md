# 05 — 이벤트 큐 및 저장 스키마 설계 (Event Queue & Storage Schema)

> **목적**: 수집 결과를 담는 **이벤트 큐**와, 그 상태/증거/시도를 기록하는 **저장 계층**을 설계한다. 이미 동작하는 `EventQueue`(JSONL) 위에 점진적으로 영속성을 더한다.
> **핵심 결정**: 새 DB를 처음부터 다 만들지 않는다. **다운스트림은 기존 Postgres 스켈레톤(raw_events/event_cards)을 재사용**하고, ingestion 자체 상태는 **JSONL → local_file → (선택)Redis/SQLite** 순으로 점진 영속화한다.

---

## 0. 비개발자를 위한 설명

"이벤트 큐"는 식당의 **주문 전표 꽂이**다. 수집기가 "이런 사건이 있었다"는 전표(사건 후보)를 꽂으면, 다음 일꾼(AI 분석)이 하나씩 빼서 처리한다. 전표 꽂이가 필요한 이유:

- 수집(빠름)과 분석(느림)의 **속도 차이**를 흡수한다.
- 일꾼이 잠깐 쉬어도 전표는 쌓여 있어 **유실되지 않는다**.
- 여러 일꾼이 동시에 일해도 **같은 전표를 두 번 처리하지 않는다**.

"저장 스키마"는 그 전표와 처리 기록을 **어떤 표(table)에 어떤 칸으로 적을지**의 설계다. 우리는 이미 다운스트림에 Postgres 표(raw_events, event_cards)가 있으므로, **그걸 재사용**하고 수집 쪽에는 가벼운 표만 추가한다.

---

## 1. 초기 저장소 결정 — SQLite vs Postgres (D-1 상세)

| 후보 | 장점 | 단점 | 권고 |
|---|---|---|---|
| **기존 Postgres 재사용** (다운스트림) | 이미 raw_events/event_cards 스키마+Alembic 존재, 컨테이너 정의됨 | 컨테이너 가동 필요(V-3) | **다운스트림 저장은 이것** |
| **JSONL** (현재 EventQueue) | 설치 0, 즉시 동작, 개발/테스트 동일 | 동시성 약함, 대량 비효율 | **Phase A~B 큐는 이것** |
| **local_file** (rate-limit/health) | 재기동 후 상태 유지, 설치 0 | 단일 노드 | **ingestion 상태는 이것** |
| **SQLite** (선택) | 단일 파일, 트랜잭션, 동시 읽기 | 동시 쓰기 약함 | LangGraph checkpointer가 필요해질 때만 |
| **Redis** (선택) | 워커 간 공유, TTL, sorted set | 컨테이너 필요(V-2) | Phase G(Celery) 진입 시 |

**결론(기본 권장)**:
- **이벤트 큐 본체**: Phase A~B는 `EventQueue`(JSONL). Phase G에서 Redis Stream으로 전환(이미 stub 존재).
- **다운스트림 영속**: 기존 Postgres raw_events/event_cards 재사용(새 DB 안 만듦).
- **수집 상태(rate-limit/health)**: local_file 고정 → Phase G에서 Redis.

> 이 결정의 미덕: **Phase A~E를 신규 인프라 0으로 시작**할 수 있다. DB/Redis는 나중에 얹는다.

---

## 2. 이벤트 큐 스키마 (EventSeedCandidate)

큐에 들어가는 최소 항목(D-5):

```python
# EventQueue.enqueue(item: dict) — 현재 구현이 dict를 받으므로 스키마는 dict 계약
EventSeedCandidate = {
    # ── MVP 필수 (Phase A — 이것만으로 큐 동작) ──
    "title_or_keyword": str,    # 필수
    "source_url": str,          # 필수
    "timestamp": str,           # 필수 (ISO8601)
    "source_id": str,           # 필수 (브리지 source_type 매핑)
    "_status": str,             # 필수 — pending|processing|done (EventQueue 내부 부여)
    # ── 권장 확장 (Phase B~ — 근거 추적/품질/디버깅) ──
    "_id": str,                 # uuid4 (EventQueue 내부 부여)
    "purpose": str,             # 02 §2 purpose
    "canonical_url": str | None,        # url_resolver 결과 (Google News 등 원본)
    "body_excerpt": str | None,         # preview_only 길이 준수 (전문 아님)
    "body_missing": bool,               # 본문 미확보 여부 (04 §10 — 사건은 보존)
    "collection_status": str,           # LIVE_SUCCESS|RATE_LIMITED|BLOCKED|...
    "items_found": int,                 # 수집 항목 개수 (Phase A/B 구현 반영)
    "items_extracted": int | None,      # ProbeResult.items_extracted (없으면 None)
    "strategy_used": str,               # api|playwright_site_spec|... (라우팅 결과)
    "error_type": str | None,           # ErrorType (실패 시)
    "raw_artifact_path": str | None,    # 계층1 raw payload reference (internal_only)
    "extracted_text_ref": str | None,   # 계층1 extracted reference (internal_only)
    "canonical_url": str | None,        # 개별 기사 URL (Phase C/D url_resolver, 현재 None)
    "significance": float,              # 0~1 (numeric/trend 신호 강도, Phase D~)
    "language": str | None,             # (Phase D~)
}

> **Phase A/B 구현 노트**: 위 필드 중 `title_or_keyword~error_type, raw_artifact_path,
> extracted_text_ref, items_extracted, canonical_url(None), cycle_id`는 실제 적용됨
> (`ingestion/orchestration/event_seed.py`). `significance`/`language`는 개별 사건 분해가
> 들어오는 Phase D~ 대상이다. `_id`/`_status`는 EventQueue가 부여한다.
```

> **D-5 판정: APPROVE(확장 보강).** MVP 필수 5필드만으로 Phase A 큐가 돈다(무겁지 않음). 단 **근거 추적**(B2B evidence link, 09 게이트 참조)을 위해 `raw_artifact_path`/`extracted_text_ref`/`canonical_url`/`body_missing`/`error_type`을 Phase B부터 채운다. 사건 후보만 저장하고 원문 reference가 없으면 나중에 근거를 못 단다.

`ingestion/schemas/event_candidate.py:EventCandidate`(이미 존재: source_id, url, title, summary, event_type, entities, regions, sectors, significance, confidence, published_at, extraction_strategy, llm_judged)는 **다운스트림 후보**다. 큐 항목은 그보다 가벼운 seed이고, 다운스트림에서 EventCandidate로 승격된다.

---

## 3. 저장 테이블 설계 (점진 영속 — 필요할 때만 생성)

> 원칙: **Phase A~B는 표를 거의 안 만든다**(JSONL/local_file). 아래 표들은 영속이 필요해지는 Phase에서 점진 추가. 다운스트림 raw_events/event_cards와 **중복 생성하지 않는다**.

### 3.1 event_candidates (큐 영속 — Phase B, 선택)
| column | type | 비고 |
|---|---|---|
| id | uuid PK | |
| source_id | text | |
| title_or_keyword | text | |
| source_url | text | UNIQUE(source_url, source_id) 중복 방지 |
| timestamp | timestamptz | |
| purpose | text | |
| body_status | text | success/partial/body_missing/signal_only |
| significance | real | |
| status | text | pending/processing/done/failed |
| created_at | timestamptz | |
- **retention**: 처리 완료 후 N일 보관 → 다운스트림 event_cards로 승격되면 archive.
- **migration**: 다운스트림 Alembic에 `0004_event_candidates` 추가 또는 ingestion 전용 경량 스토어.

### 3.2 source_runs (수집 실행 기록 — Phase B)
| column | type | 비고 |
|---|---|---|
| id | uuid PK | |
| source_id | text | |
| cycle_id | uuid | orchestration_cycles FK |
| strategy_used | text | CollectionStrategy |
| status | text | LIVE_SUCCESS/RATE_LIMITED/BLOCKED/... |
| items_found | int | |
| started_at, ended_at | timestamptz | |
| error_category | text | ErrorType |
- 현재는 `append_result_row()`가 JSONL로 이 역할 → 표는 영속이 필요할 때.

### 3.3 source_health (이미 코드 존재 — source_health.py)
- `get_health_store()` (LocalFileSourceHealthStore, `outputs/state/source_health.json`). 6상태 전이.
- **표로 옮길 필요 없음** — local_file로 충분. Phase G에서 Redis 검토.

### 3.4 body_artifacts (artifact 인덱스 — 04 연계)
| column | type | 비고 |
|---|---|---|
| url_hash | text PK | `artifact_store.url_hash` |
| source_id | text | |
| raw_html_path | text | internal_only |
| extracted_text_path | text | |
| body_length | int | |
| boilerplate_ratio | real | |
| legal_storage_policy | text | full/preview_only/signal_only |
- raw 파일 자체는 `.gitignore` 디스크. 표는 **경로 인덱스만**(artifact_manifest 정책).

### 3.5 related_candidates (확장 수집 — Phase D)
- 사건 후보의 related expansion 결과. source_url, parent_event_id, relation_type(news/community/official/numeric).

### 3.6 numeric_signals (시세 신호 — Phase E)
- symbol, source_id, value, ts. **body 없음 정상**. 투자판단 금지(정보만).

### 3.7 agent_actions / orchestration_cycles (운영 추적 — Phase F/G)
- orchestration_cycles: cycle_id, started_at, sources_attempted, sources_succeeded, sources_blocked.
- agent_actions: (LLM 판단을 쓸 경우) action, input_ref, output_ref, model_used — 감사 추적.

### 3.8 rate_limit_state (이미 코드 존재 — rate_limit_store.py)
- `get_store()` (memory/local_file/redis). next_retry_at 영속. **표 불필요** — 기존 store.

### 3.9 extraction_attempts (본문 시도 — 04 연계)
- url, strategy, status, error_category, attempted_at. body cascade 디버깅용. JSONL로 충분(영속 선택).

### 3.10 evidence_links (증거 연결 — Phase H)
- event_id, evidence_url, evidence_type(filing/news/numeric), source_id. 사건↔근거 다대다.

---

## 4. 원문 저장소 5계층 (재검토 확정)

수집 원문·사건 데이터는 **목적이 다른 5개 계층**에 산다. 내부 보관과 외부 공개를 혼동하면 저작권 사고가 난다.

| # | 계층 | 위치 | 내용 | 공개 정책 |
|---|---|---|---|---|
| 1 | **artifact_store** | `ingestion/core/artifact_store.py` (디스크, `.gitignore`) | raw payload(`save_raw_html/save_raw_payload`) + extracted(`save_extracted_text/save_extracted_payload/save_raw_signal`) | **internal_only** (외부 재배포 아님) |
| 2 | **EventQueue (JSONL)** | `ingestion/pipeline/event_queue.py` → `outputs/jsonl/event_queue.jsonl` | 사건 후보 대기열 + artifact **reference** | internal, Phase A 사용 |
| 3 | **raw_events (Postgres)** | 다운스트림 | 사건 처리 입력. `raw_text`는 **preview/요약**(전문 아님 권장) | internal |
| 4 | **event_cards (Postgres)** | 다운스트림 | LangGraph 처리 후 사용자 화면용 결과 | 화면 노출(요약/evidence/source_url) |
| 5 | **Milvus / OpenSearch** | 다운스트림 | 벡터 유사도 / 키워드 색인 | 검색용 |

> **원칙(불변)**: 원문 **내부 저장**과 원문 **외부 공개**는 다르다. 사용자 화면은 **전문 재배포가 아니라 preview/summary/evidence link/source_url 중심**이어야 한다. raw_html/raw_payload(계층 1)는 절대 외부로 노출하지 않는다. full-text 저장/노출은 `publication_policy.yaml`을 따른다(09 §legal_safety_risk, 04 §7).

artifact reference는 계층 2(EventQueue)와 계층 3(raw_events) 사이를 잇는다 — 사건 후보만 저장하고 원문 reference가 없으면 나중에 근거 추적이 불가능하므로, **확장 필드(§2)에 `raw_artifact_path`/`extracted_text_ref`를 둔다.**

## 4b. 다운스트림 브리지 (event queue → raw_events) — 정확한 contract

> 두 시스템을 잇는 핵심(D-6). **별도 어댑터 강력 권장** — 코드 실측으로 직접 결합 불가가 확인됨.

**실측 시그니처(2026-06-14, U-3 RESOLVED)**:
```python
# backend/app/services/raw_event_service.py:49
async def create_raw_event(session: AsyncSession, payload: RawEventCreate) -> RawEventCreateResponse
# backend/app/schemas/raw_events.py:9  RawEventCreate 필드:
#   source_type: str = "rss"   url: str   title: Optional[str]
#   raw_text: str = ""         published_at: Optional[datetime]   content_hash: str
```

→ **async 함수 + pydantic 모델 + AsyncSession**을 요구한다. dict 직접 전달 불가. 따라서 어댑터가 스키마 변환·dedup·body_missing·preview 절단·로그를 담당해야 한다.

```python
# Proposed adapter contract — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY: 신규 ingestion/orchestration/bridge_to_raw_events.py
async def bridge_to_raw_events(item: dict, session) -> str:
    payload = RawEventCreate(
        source_type = item["source_id"],
        url         = item["source_url"],
        title       = item.get("title_or_keyword"),
        raw_text    = _preview(item.get("body_excerpt", ""), policy),  # preview_only 절단
        published_at= _parse_ts(item["timestamp"]),
        content_hash= _sha256(item["title_or_keyword"], item["source_url"]),  # dedup 키
    )
    resp = await create_raw_event(session, payload)   # 기존 함수, ON CONFLICT 멱등
    # producer.xadd("stream:raw_events", resp.id)  # 기존 큐(Phase H, Redis 가동 시)
    return resp.id
```

이후는 **기존 다운스트림 파이프라인이 그대로 처리**(정규화 → LangGraph 11노드 → event_cards → 색인 → UI). 즉 어댑터 하나로 44개 소스가 다운스트림에 연결된다.

> ⚠️ 어댑터는 **async 컨텍스트**가 필요하다(create_raw_event가 async). Phase A(동기 cycle)에서는 `asyncio.run()`으로 감싸거나, 브리지를 Phase H의 async 경로로 둔다. `psycopg` 직접 사용 대신 **기존 backend AsyncSession을 경유**하면 신규 드라이버 설치를 피할 수 있다(00 §4).

---

## 5. 저장 계층 의사결정 트리

```
수집 결과를 어디 둘까?
 ├─ Phase A~B (설치 0)       → EventQueue(JSONL) + local_file(상태)
 ├─ 워커 여러 개 공유 필요    → Redis (Phase G, 컨테이너 가동 V-2)
 ├─ 다운스트림 사건 카드      → 기존 Postgres raw_events/event_cards (V-3)
 └─ LangGraph 크래시 복구     → SQLite checkpointer (선택, 패키지 설치)
```

---

## 6. Implementation diff blueprint

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY

# (Phase G) EventQueue Redis Stream 구현 — 기존 stub 채우기
diff --git a/ingestion/pipeline/event_queue.py b/ingestion/pipeline/event_queue.py
--- a/ingestion/pipeline/event_queue.py
+++ b/ingestion/pipeline/event_queue.py
@@ def _redis_enqueue(self, item):
-        raise NotImplementedError("Redis Stream wired in Round 2")
+        client = self._redis_client()
+        item_id = client.xadd("stream:event_queue", _flatten(item))
+        return item_id
@@ # _redis_dequeue/_redis_peek/_redis_mark_done 동일 패턴 (XREADGROUP/XACK)

# (Phase H) 브리지 어댑터 신규
diff --git a/ingestion/orchestration/bridge_to_raw_events.py b/ingestion/orchestration/bridge_to_raw_events.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/bridge_to_raw_events.py
@@
+def bridge_to_raw_events(item: dict) -> str:
+    """event queue 항목 → 다운스트림 raw_events. §4."""
+    ...  # VERIFY create_raw_event signature (U-3)

# (Phase B, 선택) event_candidates 마이그레이션
diff --git a/backend/alembic/versions/0004_event_candidates.py b/backend/alembic/versions/0004_event_candidates.py
new file mode 100644
--- /dev/null
+++ b/backend/alembic/versions/0004_event_candidates.py
@@
+def upgrade(): ...  # §3.1 table
```

**수정하지 않는 파일**: 기존 `raw_event_service.py`, `producer.py`, Alembic 0001~0003. event_queue.py는 stub 채우기만(인터페이스 불변).

---

## 7. test plan

```
test_event_queue_jsonl_roundtrip          # enqueue→dequeue→mark_done (기존 동작 회귀)
test_event_queue_redis_roundtrip          # Phase G, fakeredis
test_event_queue_redis_fallback_to_jsonl  # REDIS_URL 미설정 시 JSONL
test_bridge_creates_raw_event             # §4, create_raw_event 호출(mock)
test_bridge_dedup_by_content_hash         # 중복 URL → ON CONFLICT NOTHING
test_seed_candidate_minimal_fields        # title/url/timestamp 필수 검증
test_preview_only_excerpt_truncated       # 저작권 길이 준수
```

---

## 8. Agent Committee Review

| agent | 피드백 | status |
|---|---|---|
| orchestrator-architect | "기존 Postgres 재사용 + JSONL 큐 점진 영속"이 과설계를 피함 | CLOSED_BY_DESIGN |
| source-ingestion-engineer | EventQueue stub 채우기 + 브리지 어댑터가 코드 무수정 원칙 충족 | CLOSED_BY_DESIGN |
| data-quality-auditor | content_hash 중복 방지 + body_status 추적이 품질 게이트와 연결 | CLOSED_BY_TEST_PLAN |
| frontend-integration-agent | event_candidates → event_cards → API가 기존 contract 재사용 | CLOSED_BY_DESIGN |
| adversarial-reality-critic | U-3(create_raw_event 시그니처) 미확인이 브리지 최대 리스크 | DEFERRED_WITH_TRIGGER |
| operations-sre-agent | Redis Stream consumer group + PEL 재처리는 다운스트림 패턴 재사용 | CLOSED_BY_DESIGN |
| legal-safety-compliance-reviewer | raw artifact internal_only + preview_only excerpt 유지 | CLOSED_BY_DESIGN |

---

## 9. Risk Closure

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| DB 스키마 lock-in | 조기 과설계 | 변경 비용 | 스키마 리뷰 | JSONL→점진 영속, 최소 스키마 | Phase A 표 0개 | CLOSED_BY_DESIGN |
| 브리지 시그니처 오인(U-3) | create_raw_event 미확인 | 브리지 실패 | grep/코드 확인 | VERIFY PATH 표기 | 구현 직전 확인 | DEFERRED_WITH_TRIGGER |
| 중복 사건 증폭 | content_hash 누락 | 같은 사건 다중 | dedup 카운트 | UNIQUE(url) + content_hash | dedup 테스트 | CLOSED_BY_TEST_PLAN |
| 큐 유실 | JSONL 동시 쓰기 경합 | 사건 손실 | 큐 길이 모니터 | Phase G Redis Stream + PEL | roundtrip 테스트 | CLOSED_BY_TEST_PLAN |
| raw 저작권 노출 | full-text 공개 | 법적 위험 | publication_policy | internal_only + preview excerpt | preview 테스트 | CLOSED_BY_DESIGN |

---

## 10. Commercialization Impact

- **event queue = 제품의 심장**: "실시간 사건 피드"라는 핵심 가치가 큐에서 나온다. 큐가 안정적이면 재방문·체류가 늘고, API로 외부 판매도 가능(B2B).
- **점진 영속 = 빠른 출시**: JSONL로 즉시 MVP를 띄우고, 트래픽이 늘면 Redis/Postgres로 전환 → 초기 인프라 비용 0에 가깝게 시작.
- **증거 링크(evidence_links) = 신뢰 차별화**: 사건마다 1차 출처(공시/규제)를 연결하면, "근거 있는 인텔리전스"로 프리미엄/B2B 포지셔닝.

---

## 11. USER_CONFIRMATION_REQUIRED

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| 다운스트림 저장을 기존 Postgres로 재사용? | 중복 DB 회피 | 예(재사용) | No |
| 이벤트 큐 1차를 JSONL로? | 설치 0 시작 | 예, Phase G에서 Redis | No |
| 브리지를 별도 어댑터 task로? | 결합도 최소화 | 예(bridge_to_raw_events) | **REVIEW(D-6)** |
| event_candidates 표를 만들까(Phase B)? | 큐 영속 필요 시점 | 필요해질 때만(기본 JSONL) | No |

> 다음 문서: `06_LANGCHAIN_LANGGRAPH_DEEPAGENTS_RESEARCH.md`.

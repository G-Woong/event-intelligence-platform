# 06 — CONFLICTS AND SUPERSEDED (문서 충돌·구버전 정리)

> 충돌 문서를 방치하지 않는다. canonical source of truth를 명시한다.

---

## A. 충돌(CONFLICT)

### C-1 · "두 수집 경로가 같은 시스템처럼 보임"
- Files: `system_overview/03·05·12`, `COLLECTOR_DESIGN.md` ↔ `ingestion/*`, `Orchestration_Construction/*`
- Old statement: 수집 = workers RSS 3소스(bbc/reuters/yna)가 raw_events를 채움.
- Current: ingestion 57소스 엔진이 별개로 존재하며, 다운스트림과는 `BackendApiRawEventsWriter`
  (`--raw-events-sink backend`)로 **배선됨**(C-9 참조, ap_news 라이브 E2E 입증). 단 **기본 sink는 여전히
  mirror**(backend opt-in)이므로 평시 경로는 JSON mirror다.
- Resolution: 둘은 **별개 서브시스템**이고 수집 로직은 동일 시스템이 아니다. 단 "통합 미구현"은 stale —
  bridge는 구현·라이브 입증됨(04 T-IngA PARTIAL DONE). 남은 것은 기본 sink 채택·46소스 전수 sweep.
- Canonical: `02_CURRENT_ARCHITECTURE §1`, `01_IMPLEMENTED_FLOW`, `06 C-9`.

### C-2 · 소스 수 / 테스트 수 불일치
- Files: `DOCS_FINAL.md`("509 passed", "PASS 14/15"), `INGESTION_FINAL.md`("44 CORE_READY / 58"), `IMPLEMENTATION_TRACE_FINAL.md`("635"), `ENVIRONMENT_SETUP_FINAL.md`("648")
- Old vs Current: 44 CORE_READY → **46 PRODUCTION_READY / 57 총**; 509/635/648 → **ingestion 1293 passed**(2026-06-18, role taxonomy 라운드 후; G-4 기준 1205→1293).
- Resolution: 수치 stale. Canonical: `03_SOURCE_STATUS`, `09_VALIDATION_AND_TESTS`.
- Action: 원본 수치는 정정(04 T-DocA) 또는 canonical 포인터.

### C-3 · DART/SEC/trafilatura "미구현 TODO" (실제 구현됨)
- Files: `system_overview/09·10·11`
- Old statement: dart_collector/sec_collector/trafilatura = STEP 013 TODO(없음).
- Current: `ingestion/sources/opendart.py`, `ingestion/sources/sec_edgar.py`, `ingestion/tools/trafilatura_extractor.py` **존재**.
- Resolution: stale. Canonical: `03_SOURCE_STATUS`. Action: 해당 3파일 SUPERSEDED 배너.

### C-4 · Orchestration_Construction README "설계 전용, 미구현"
- Files: `Orchestration_Construction/README.md`
- Old statement: "이 폴더는 설계다. 구현 코드는 아직 적용되지 않았다."
- Current: Phase A~G-4가 `ingestion/orchestration/`에 **실제 구현**됨(strategy_graph/tool_plan/evidence_gate/community_corroboration_gate/bridge_to_raw_events/production_state 등).
- Resolution: 가장 심각한 stale 선언. Canonical: `01_IMPLEMENTED_FLOW`. Action: README SUPERSEDED 배너.

### C-5 · LangGraph mock 노드 수
- Files: `ARCHITECTURE.md`("8/11 mock", STEP 005) ↔ `SKELETON_COMPLETION_CHECKLIST.md`/`system_overview/09`("6/11 mock", STEP 011)
- Resolution: STEP별 시점차. Current = **6/11 mock**(5 REAL). Canonical: `08_LLM_AGENT_ORCHESTRATION_HANDOFF`.

### C-6 · LLM_PROVIDER 기본값
- Files: `COMPATIBILITY_NOTES.md`(설정표 "openai") ↔ `ARCHITECTURE.md`/docker-compose("mock")
- Resolution: 실제 기본 = **mock**(docker-compose.dev.yml). Canonical: `02 §6`.

### C-7 · Next.js 버전
- Files: `FRONTEND_DESIGN.md`("15.0.x") ↔ package.json(^15.5.18)
- Resolution: 실제 **15.5.18**(CVE-2025-29927 대응). Canonical: `02 §7·§8`.

### C-8 · 컨테이너 수
- Files: `ARCHITECTURE.md`(서비스표 7) ↔ 실제 10(+ etcd/minio/opensearch)
- Resolution: 실제 **10**. Canonical: `02 §2`.

### C-9 · U-3 "RESOLVED" 표기 vs AsyncSession 미구현
- Files: `Orchestration_Construction/01·05`
- Statement: bridge async+pydantic+AsyncSession 계약 "RESOLVED".
- Current: bridge 는 `BackendApiRawEventsWriter`(HTTP POST `/api/admin/raw-events`)로 backend PG upsert +
  Redis XADD 를 수행한다(AsyncSession 직접 주입이 아니라 **backend API 경유**). 라이브 입증됨(ap_news E2E).
- Resolution: "AsyncSession 직접 주입 대신 backend API 경유로 실 PG 적재, 라이브 E2E 관찰. 기본 sink 는
  여전히 mirror(backend opt-in)"로 정정. Canonical: `04 T-IngA`, `05 R-Integration`.

### C-10 · gdelt PASS vs EXTERNAL_RATE_LIMITED
- Files: `INGESTION_FINAL.md`/`IMPLEMENTATION_TRACE_FINAL.md`("PASS/CORE_READY") ↔ production_state("EXTERNAL_RATE_LIMITED")
- Resolution: **레이어 차이** — 수집계층 view(과거 성공)와 오케스트레이션 view(현재 scheduled 429)가 다름. Current 권위 = production_state. Canonical: `03 §2`.

---

## B. 구버전(SUPERSEDED) — 배너 부착, 삭제 안 함

| 원본 | 상태 | canonical 대체 | 사유 |
|---|---|---|---|
| `Orchestration_Construction/README.md` | SUPERSEDED(부분) | 01, 06 C-4 | "설계 전용" 선언 stale |
| `system_overview/09_CURRENT_IMPLEMENTATION_STATUS.md` | SUPERSEDED | 03, 04, 09 | STEP 011 기준, 수집계층 stale |
| `system_overview/10_STUB_MOCK_TODO_MAP.md` | SUPERSEDED | 04, 06 C-3 | DART/SEC/trafilatura 오TODO |
| `system_overview/11_NEXT_ENHANCEMENT_ROADMAP.md` | SUPERSEDED(부분) | 07, 03 | Axis B/C(수집) 폐기, A/D 유효 |
| `ARCHITECTURE.md` | SUPERSEDED(부분) | 02, 01 | STEP 005 스냅샷(7컨테이너/8mock) |
| `COLLECTOR_DESIGN.md` | SUPERSEDED(부분) | 01 B, 03 | workers RSS 3소스 전용(legacy 경로) |
| `TRD.md` | SUPERSEDED(부분) | 02, 04 | STEP 006~010 시점별 핀(현재값은 02) |
| `DOCS_FINAL.md` | 포인터 갱신 | 00 | 구 진입점 → `_CANONICAL/00` 안내 배너 |

> 배너는 정보를 지우지 않는다. 상세 설계·이력은 원본과 git history에 보존된다.
> KEEP/MERGED로 분류된 나머지 문서는 내용이 canonical에 반영됐고 참조용으로 유효하다(배너 없음). 전체 매핑은 10.

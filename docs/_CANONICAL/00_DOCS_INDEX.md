# 00 — DOCS INDEX (canonical 단일 진입점)

- 생성: 2026-06-16 (docs 전수 원자분해·통폐합 라운드)
- 기준 커밋: `93e83b6` (Phase G-4 완료 후)
- 목적: `docs/` 전체를 현재 구현 상태 기준으로 재정렬한 **단일 출처 index**.
  신규 세션은 이 폴더(`docs/_CANONICAL/`)를 최우선으로 읽는다.

---

## 0. 한 문장 요약

레포에는 **두 개의 자산**이 있고, 이제 **브리지로 연결돼 라이브 E2E가 관찰됐다.**
① `ingestion/` 57소스 수집 엔진(Phase A~G-4 **구현 완료**) ②
`backend`/`workers`/`agents`/`frontend` 다운스트림 앱(STEP 011 **구현 완료**).
①→② 배선은 `BackendApiRawEventsWriter`(`--raw-events-sink backend`)로 구현·**라이브 입증**됨:
ap_news 100 records → `raw_events` PG → Redis `stream:raw_events` → worker → LangGraph →
`event_cards` 100(무본문이라 fail-closed hold). **남은 경계**: 기본 sink는 여전히 mirror(backend
opt-in), 46소스 **전수** 라이브 sweep·LLM급 카드 콘텐츠 미완(상세 03·05 R-Integration).

---

## 1. canonical 문서 읽는 순서

| # | 문서 | 무엇을 담나 |
|---|---|---|
| 00 | **00_DOCS_INDEX.md** | (이 파일) 전체 지도 + 읽기 순서 |
| 01 | **01_IMPLEMENTED_FLOW.md** | 구현 완료된 두 서브시스템의 흐름(짧게) |
| 02 | **02_CURRENT_ARCHITECTURE.md** | 현재 아키텍처 단일 출처(컨테이너·API·DB·검색·LLM·프론트) |
| 03 | **03_SOURCE_STATUS.md** | 57소스 production-state 분포 + tier 정의 + **role taxonomy(§1b)** |
| 04 | **04_OPEN_TASKS_BY_FOLDER.md** | 폴더별 미구현 TASK |
| 05 | **05_RISK_REGISTER.md** | RISK 등록부(심각도·종결조건) |
| 06 | **06_CONFLICTS_AND_SUPERSEDED.md** | 문서 충돌·구버전 정리 |
| 07 | **07_ENHANCEMENT_BACKLOG.md** | 고도화 backlog |
| 08 | **08_LLM_AGENT_ORCHESTRATION_HANDOFF.md** | LLM 에이전트 handoff 상태 |
| 09 | **09_VALIDATION_AND_TESTS.md** | 검증·테스트 현황 |
| 10 | **10_DOCS_COVERAGE_MANIFEST.md** | 원본 MD 50개 전수 처리 증명 |

비개발자/의사결정자: **00 → 03 → 05 → 07**.
구현자: **00 → 01 → 02 → 04**.

---

## 2. 권위 순서(상충 시 무엇을 믿나)

1. **코드 + 최신 산출물**(`ingestion/outputs/state/production_source_state.json` 등) — 최종 진실.
2. `docs/_CANONICAL/*` — 이 라운드에서 코드와 대조해 정렬한 문서.
3. `docs/ingestion/INGESTION_FINAL.md`, `docs/Orchestration_Construction/00·11·12` — 영역별 상세(일부 수치 stale, 06 참조).
4. 기타 루트 설계문서·`system_overview/` — 설계 참조용. **수치/상태가 02·03과 어긋나면 02·03을 따른다.**

---

## 3. 기존 docs 폴더와의 관계

- 원본 50개 MD는 **삭제하지 않았다.** 구버전/충돌 문서에는 상단 `SUPERSEDED` 배너를 붙이고
  canonical 대체본을 가리킨다. 전체 매핑은 `10_DOCS_COVERAGE_MANIFEST.md`.
- `system_overview/`는 다운스트림 앱(②) 설명은 유효하나 **수집 계층 설명은 폐기**됐다(ingestion 엔진이 대체).
- `Orchestration_Construction/`는 설계 청사진이었고 **Phase A~G-4가 실제로 구현**됐다(README의 "설계 전용" 문구는 stale → 06).
- `_IDEATION_WEB_INTELLIGENCE/`(19개, 2026-06-16 신설)는 **확장 전략·로드맵** 세트로 "현재 구현"이 아니다.
  전수 분류는 `10 Group E` 참조. code-state stale 4개(00·01·16·17)에는 STALE 배너를 부착했다. 현재 구현 사실은 항상 본 canonical이 권위.

# 00 — START HERE (docs 단일 진입점)

> 생성: 2026-06-19 (07 리팩토링 실행 라운드). **이 파일이 docs 의 최상위 진입점이다.**
> 정렬 기준(단일): **생애주기** — "지금 사실인가 / 나중 계획인가 / 과거 기록인가".

---

## 0. 한 문장

전세계 실시간 사건/이벤트 인텔리전스 웹앱. `ingestion` 57소스 수집 엔진 →(`BackendApiRawEventsWriter`)→ `raw_events` → Redis → worker → LangGraph agents → `event_cards` → API/frontend. 현재 라이브 E2E 관찰됨(ap_news), 남은 경계는 기본 sink mirror·46소스 전수 sweep·LLM급 카드.

---

## 1. 생애주기별 폴더 지도 (어디를 읽나)

| 생애주기 | 폴더 | 무엇 | 누가 먼저 |
|---|---|---|---|
| **현재 사실** | `_CANONICAL/` (00~10) | 오늘 구현된 시스템의 단일 출처(흐름·아키텍처·소스·오픈태스크·검증·충돌) | **전원 1순위** |
| **거버넌스** | `_RISK/` · `_DECISIONS/` | 열린/종결 RISK 등록부 · 월별 의사결정 ledger(ADR) | 의사결정자 |
| **미래 계획** | `2_ROADMAP/` | 확장 전략·레이어 로드맵(ideation 02·04~15·18). **미구현**, 방향 참조 | 아키텍트/제품 |
| **과거 기록** | `3_ARCHIVE/` | 빌드 히스토리(plans)·구설계·실패시도·인사이트. **시간순 정렬**(폴더명=시점) | 맥락 복원 시 |
| **하네스** | `Harness_Construction/` | 이 레포 턴-마감 운영도구 설계(제품과 별개) | 하네스 작업 시 |
| **안정 참조** | `5_REFERENCE/` | 스키마·API·런북·정책·용어집(상태중립) | 구현 시 lookup |
| (영역 상세 ③) | `ingestion/` · `Environment_setup/` · `Implementation_Instructions/` | `*_FINAL` 영역 상세(하네스 skill/agent 연동) | 영역 깊이 |

> **권위 순서(상충 시):** ① 코드 + 최신 산출물 → ② `_CANONICAL/*` → ③ 영역 `*_FINAL`(INGESTION/ENVIRONMENT/TRACE) → ④ `5_REFERENCE`·기타 설계. 수치/상태가 `_CANONICAL/02·03·09`와 어긋나면 canonical 을 따른다.

---

## 2. 목적별 빠른 진입

- **비개발자/의사결정자:** `_CANONICAL/00 → 03 → 07`, `2_ROADMAP/18_FINAL_EXECUTIVE_SUMMARY`.
- **구현자:** `_CANONICAL/01 → 02 → 04`, `5_REFERENCE/`(API_CONTRACT·EVENT_SCHEMA·FILE_MAP).
- **운영/리스크:** `_RISK/RISK_REGISTER`, `_DECISIONS/2026-06`.
- **하네스 작업:** `Harness_Construction/00_HARNESS_BLUEPRINT_INDEX`.

---

## 3. 2026-06-19 구조 리팩토링 요약 (07 실행)

`07_REPO_REFACTOR_AND_CONSOLIDATION_SPEC` 실행으로 docs/ sprawl 을 정리했다.
- **삭제(history 보존):** 순수중복/stale 설계문서 10 + dead/dup config yaml 6 + dead 패키지 스텁.
- **ARCHIVE 이관(시간순):** 루트 `plans/` 빌드히스토리 35 + `ingestion/plans/` 8 + ideation 스냅샷 5 + Orchestration 설계 11 + system_overview legacy 3 → `3_ARCHIVE/`.
- **REFERENCE 통합:** 루트 설계문서 12 + system_overview 참조 6 → `5_REFERENCE/`.
- **ROADMAP 통합:** ideation 레이어 14 → `2_ROADMAP/`.
- **유지(live 연동):** `_CANONICAL/`·`_RISK/`·`_DECISIONS/`·`Harness_Construction/`·`ingestion/`·`Environment_setup/`·`Implementation_Instructions/` 는 하네스 skill/agent/코드가 직접 참조하므로 제자리(rename 안 함).
- 복구: `git tag pre-refactor-2026-06-19`. 상세 맵: `Harness_Construction/07`.

> `_ARCHIVE_SUPERSEDED/`·`_TRASH/` 는 **하네스가 자동 관리하는 tombstone**(turn-closeout 이 superseded doc 을 이동). 사람이 읽는 과거 기록은 `3_ARCHIVE/`.

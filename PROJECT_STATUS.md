# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** ① D-2b(Event 타임라인 frontend 렌더)를 커밋(`c439e78`)으로 안정화하고, ② **테스트가 외부 OpenAI를 타지 않도록 mock으로 격리**하고, ③ **웹 응답에서 내부 식별자(source_refs·엔티티 ID·카드 ID)를 빼고** 에러 화면이 내부 메시지를 안 흘리도록 정리했습니다.
- **이번 턴에 실제로 끝낸 것:** provider 격리(`backend/tests/conftest.py` — 전역 설정을 mock으로 고정 + embedding·LLM 캐시 reset; **`.env`에 openai를 다시 넣어도 결정론 테스트는 mock**) + 공개/내부 read 스키마 분리(`PublicEvent`/`PublicEventUpdate` — 내부 FK·source_refs를 wire에서 구조적 제외) + 에러 표현 전역 통일(raw 메시지 미노출). **측정: backend 242 passed(0 fail; pre-existing embedding 실패 해소·live-PG 21 동일 실행 포함) + ingestion 1331 = 1573 green · frontend tsc 0/test 12/lint 0.** 4-감사단(architecture SOUND; code/adversarial/legal가 잡은 LLM 캐시 누락·Event 내부 FK 잔존·error.tsx raw 노출 3건 전부 반영).
- **지금 막힌 것:** 없음(BLOCKED 0). 단 **D-2c 미실행**(Docker로 Event가 실제 화면에 보이는 데모) + **delta_summary 자연어화**(현재 `"0.83:strong_clique"` 디버그 라벨 — 상류 생성 책임)는 이월. Event 타임라인이 사용자에게 실제로 보이려면 여전히 flag on + 데이터 seed/runner가 필요합니다.

## 📋 자동 수집 사실 (machine_status.json)
- HEAD `c439e78`(D-2b 커밋) 위 **미커밋 변경 = code 9(신규 conftest 1 + 수정 8) + docs 8**. (machine_status 스냅샷은 이전 턴 기준 stale — Stop 훅 재스캔.)
- 신규: `backend/tests/conftest.py`. 수정(code): `backend/app/{api/events.py,schemas/events.py}`·`backend/tests/test_event_timeline_api.py`·`frontend/src/app/error.tsx`·`frontend/src/app/events/timeline/{page.tsx,[eventId]/page.tsx}`·`frontend/src/lib/api/types.ts`·`.env.example`. docs 8.
- 열린 RISK 29: R-EventTimelineRenderHardening(**①③ 종결·② delta_summary 잔여**, LOW) · R-EventTimelineApiScale·R-EventSinkDbTarget·R-EventTimelineS2Hardening·R-EventModelMigration·R-FalseMerge·R-ExpansionPartialFailure 유지.

## ✅ 이번 턴에 달성한 것 (D-2b 커밋 + provider 격리 + 공개 스키마 분리)
- **D-2b 커밋(`c439e78`):** frontend 10 + docs 8(+420/−38), secret PASS·closeout EXACT MATCH·docs_lifecycle 0 확인 후 커밋. working tree clean(push 안 함).
- **provider 결정론 격리(ADR#26):** `backend/tests/conftest.py`(신규) autouse fixture가 전역 `settings.LLM_PROVIDER`/`EMBEDDING_PROVIDER`를 mock으로 pin + **embedding·LLM 캐시 둘 다 reset**(각 모듈 별도 싱글톤 — adversarial P1 반영). **os.environ 미오염**이라 자체 Settings 쓰는 env-contract 테스트·`provider="openai"` 명시 테스트 무영향. **범위=backend suite**(ingestion은 `os.getenv` 기본 mock, 별개). → **dirty-env 시뮬(`EMBEDDING_PROVIDER=openai` 강제)에서도 `test_get_embedding_client_singleton` 통과** = `.env` 비의존 입증. pre-existing embedding 결합 해소.
- **공개/내부 read 스키마 분리(ADR#26):** `PublicEvent`(primary_entity_ids=entities FK·snapshot_card_id=event_cards FK 제외, heat=제품신호 유지)·`PublicEventUpdate`(source_refs 제외)·`PublicEventTimelineResponse` 신규 — `/timeline`·`/timeline/{id}` **양쪽**이 공개 뷰 반환(내부 식별자 wire 구조적 차단; allowlist 별도 스키마라 내부 모델에 신규 필드 추가돼도 자동 누출 0). 비공개 `EventTimelineResponse` 제거. 변환은 **API 경계**(`_to_public_event`)에서만 → 서비스 계층 무변경 → live-PG 무영향. frontend 타입도 내부 FK·source_refs 제거.
- **에러 표현 전역 통일(ADR#26):** 목록·상세 비-404를 raw 없이 일반 안내 + **전역 `error.tsx`도 raw message 미렌더**(render 단계 throw까지 차단, adversarial P2-C). → backend 장애 시 내부 메시지(스택/경로/DB 힌트) 노출 전역 차단.
- **`.env.example` 정리:** provider=openai 라인 제거(사용자) + provider 미선언=mock 기본값("empty=DEFAULT") 설명 주석(openai는 LLM/RAG 단계에서만 명시).
- **4-감사단:** architecture **SOUND**(0 blocking; allowlist 별도 스키마·API 경계 변환=비파괴) · code-review(LLM 캐시·중복키 등 지적→수정) · adversarial(P1 LLM 캐시·P2-B Event FK·P2-C error.tsx·P2-D 2회 실행 정직성→전부 반영) · legal **CONDITIONAL→충족**(source_refs 실질 제외·에러 마스킹·테스트 egress 0; primary_entity_ids/snapshot_card_id도 PublicEvent로 제외해 조건 해소).
- **검증:** **backend 242 passed/4 skipped/0 failed**(단일 실행에 live-PG 21 포함; embedding fail 해소; 4 skip=milvus 3·openai smoke 1, env-gated) · ingestion **1331** · = **1573 green**(+1) · frontend **tsc 0·test 12·lint 0**.

## ❌ 달성하지 못한 것 & 왜
- **delta_summary 자연어화(R-EventTimelineRenderHardening ② 잔여):** 현재 결선(`event_ingest_pipeline`)이 `"{confidence}:{reason}"` 디버그 라벨을 넣음 → 데이터가 있어도 타임라인 본문이 사용자용 서술 아님. 상류 생성 책임이라 이번 범위 밖(억지로 닫지 않음).
- **D-2c Docker 데모 미실행:** flag on + 데이터 결선 + 브라우저 E2E 미수행(다음 단계 후보).
- **R-EventSinkDbTarget 구조 가드:** 운영 DB target 혼동 가드는 D-2c(운영 DB 다루는 시점)에서 함께가 적절 → 이월(과장 종결 안 함).
- **evidence read-time sanitize(legal LOW):** sanitize는 write 경로 전제 — 미정제 레거시 행 직출력 가능(단일 write 경로라 LOW). public evidence 재sanitize는 후속.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 실데이터 노출 시 타임라인 가독성(delta_summary 자연어화 후)·브라우저 E2E 실거동(compose 실행 전)·대규모 응답 plan(R-EventTimelineApiScale)·실 evidence/entity 데이터 PII 여부(상업 배포 전 실DB 1회 샘플).
- pre-existing embedding 실패는 **해소**(conftest mock 격리). 단 "해소"=결정론 스위트에서 openai 경로를 격리한 것(openai 동작 증명이 아니라 `RUN_OPENAI_EMBED_SMOKE` 게이트로 분리).

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-EventTimelineRenderHardening(LOW, 부분종결):** ③ 내부 식별자 wire 노출(source_refs·primary_entity_ids·snapshot_card_id) → Public* 스키마로 **구조적 제외 종결**. ① 상세 비-404 에러표현 → 페이지+전역 error.tsx raw 미노출 **종결**. **② delta_summary 자연어화만 잔여**(상류).
- **pre-existing embedding/provider test 결합:** 정식 RISK 항목은 아니었고(PROJECT_STATUS known-issue) conftest로 **해소** — RISK_CLOSED 이관 대상 없음.
- **유지:** R-EventTimelineApiScale(단건 페이지네이션·EXPLAIN)·R-EventSinkDbTarget(구조 가드, D-2c 동반)·R-EventTimelineS2Hardening·R-EventModelMigration·R-FalseMerge·R-ExpansionPartialFailure. **거짓 종결 0.**

## 👉 다음 할 일
1. **[다음 단계 판정 보고]** docs/2_ROADMAP 재독 + 코드 실측으로 **D-2c Docker 데모가 맞는지** 분석 보고(이번 턴 마지막). 후보: D-2c · D-2b+ 사용성(delta_summary 자연어화) · D-1.5 운영 보강 · event_cards↔Event 자동연결.
2. **[D-2c 후보]** flag on + synthetic seed/D-1 runner → compose up → 브라우저로 Event 타임라인 확인(webapp-testing). **선행 가치:** delta_summary 가독성.
3. (이월) 단건 updates 페이지네이션 · R-EventSinkDbTarget APP_ENV 가드 · heat(S2.5) · event_cards 자동연결.

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/tests/conftest.py`(provider 격리) · `backend/app/schemas/events.py`(PublicEvent/PublicEventUpdate/PublicEventTimelineResponse) · `backend/app/api/events.py`(_to_public_event) · `frontend/src/app/error.tsx`·`events/timeline/*`·`lib/api/types.ts`.
- 테스트: `backend/tests/test_event_timeline_api.py`(내부 ID wire 미노출 assert: source_refs·primary_entity_ids·snapshot_card_id).
- 문서: `_DECISIONS/2026-06.md`(ADR#26) · `_RISK/RISK_REGISTER.md`(R-EventTimelineRenderHardening 부분종결) · _CANONICAL/02·EVENT_SCHEMA·2_ROADMAP/{00,15,19}·`.env.example`.

---
_as_of: 2026-06-23 · D-2b 커밋(`c439e78`) + provider 결정론 격리(conftest: 전역 settings mock pin·embedding+LLM 캐시 reset·`.env` 비의존; dirty-env 시뮬 통과) + 공개/내부 read 스키마 분리(`PublicEvent`/`PublicEventUpdate` — source_refs·primary_entity_ids·snapshot_card_id wire 구조적 제외, allowlist 별도 스키마, API 경계 변환=서비스/live-PG 무변경; 비공개 EventTimelineResponse 제거) + 에러 표현 전역 통일(error.tsx raw 미노출). 측정 **backend 242 passed/0 fail(embedding 해소·live-PG 21 동일실행) + ingestion 1331 = 1573 green · frontend tsc 0/test 12/lint 0.** 4-감사단(architecture SOUND; adversarial P1 LLM캐시·P2-B Event FK·P2-C error.tsx 반영; legal source_refs 실질제외). **R-EventTimelineRenderHardening ①③ 종결·② delta_summary 잔여.** 미커밋(커밋 지시 대기). 잔여: D-2c Docker 데모·delta_summary 자연어화·R-EventSinkDbTarget 가드_

# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 사건을 1회성 카드 → **진화하는 Event 타임라인 객체**로 만드는 **DB 토대(S1)**를 깔았습니다(events/event_updates 테이블 + 카드↔Event 연결). 기존 카드는 그대로 동작(비파괴)하고, 5개 감사단으로 검증해 적대 감사가 찾은 **실제 결함 2건을 즉시 수정·테스트로 잠갔습니다**.
- **이번 턴에 실제로 끝낸 것:** alembic **0004**(additive+downgrade) + `events`/`event_updates` ORM·Pydantic + `event_cards.event_id` nullable FK + 이중쓰기 정합성 불변식·DB-미연결 형상/DDL 회귀. **측정 게이트 backend+ingestion 1451 passed**(회귀 0). 적대 blocking 2(순환 FK·인덱스 드리프트) 수정. cluster_event_map/event_links는 **S2로 이월**(스코프 준수).
- **지금 막힌 것:** 없음(BLOCKED 0). 단 backend 전체에 **pre-existing 환경 실패 1건**(`test_get_embedding_client_singleton` — `.env` EMBEDDING_PROVIDER=openai + os.getenv 키 부재) — **S1과 무관**(S1 이전부터 동일 실패, 범위 밖이라 미수정).

## 📋 자동 수집 사실 (machine_status.json)
- session 4e61… turn 8 · 변경 7건 = **code 6 + other 1**. code_py_loc 49.
- code_files: `0004_event_timeline.py`, `models/{__init__,event,event_timeline}.py`, `schemas/events.py`, `tests/test_event_timeline.py`.
- audit_types(권위): **architecture_review · code_review · test_review** → 전부 라우팅·완료(+ evidence_review·risk_closure_review 선제). 열린 RISK **25 → 26**(신규 LOW 1 = `R-EventTimelineS2Hardening`, 종결 0).

## ✅ 이번 턴에 달성한 것
- **S1 토대(최소 스코프, ADR#16/#17):**
  - `backend/app/models/event_timeline.py`(신규): `EventORM`(canonical_title/status/first_seen/last_update/heat/domains/tags/primary_entity_ids/snapshot_card_id + 인덱스) · `EventUpdateORM`(append-only: observed_at/delta_summary/evidence/added_domains/source_refs/heat_delta) · `is_snapshot_bidirectional`(이중쓰기 정합성 불변식 헬퍼).
  - `backend/app/models/event.py`: `EventCardORM.event_id` nullable FK(→events.id, SET NULL) — 카드 = "Event의 한 스냅샷", NULL = degenerate(기존 카드 비파괴). **순환 FK는 `use_alter`로 create_all 안전**.
  - `backend/app/schemas/events.py`: `Event`/`EventUpdate` Pydantic(status Literal, heat/list 기본값).
  - `backend/alembic/versions/0004_event_timeline.py`(신규): additive(events/event_updates 생성 + event_cards.event_id + 인덱스) + downgrade(역순 제거). down_revision=0003(`c3d4e5f6a7b8`).
  - **S2 이월 준수:** cluster_event_map/event_links 미생성(grep 0) — 문서 19 §2.2 경계.
- **이중쓰기 정합성 회귀 + DB-미연결 형상 검증:** `backend/tests/test_event_timeline.py`(신규 17 테스트) — ORM 메타데이터(컬럼/FK/nullable/인덱스 정합)·Postgres DDL dialect 컴파일·Pydantic round-trip·정합성 불변식(쌍방향/빈 문자열/UUID-str 혼용)·degenerate 카드 호환·0004 revision 체인/additive·**순환 FK sorted_tables 무에러**.
- **5-감사단 검증:**
  - architecture(orchestrator) **SOUND**(blocking 0) — S1 스코프/EVENT_SCHEMA 정합/비파괴 3축 PASS.
  - code(adversarial) **CONCERNS→해소**: blocking 2 수정 — **B1**(순환 FK→create_all `CircularDependencyError`)을 `use_alter=True`로, **B2**(`ix_event_cards_event_id` ORM↔마이그레이션 드리프트)를 ORM `__table_args__` 인덱스 추가로. non-blocking N3(빈 문자열 거짓양성)·N7(테스트 docstring 과대표현)도 수정. 전부 신규 테스트로 잠금.
  - test **PASS** — **backend+ingestion 1451 passed**(backend 128=기존 113+신규 15, ingestion 1323, 회귀 0) + B1/B2 수정 후 변경표면 재검증 43 passed.
  - evidence(legal-safety) **APPROVED** — 외부 수집/전문저장/PII/투자조언 표면 0(순수 DB 토대). 조건부: evidence/source_refs를 채우는 S2 단계에서 "URL/요약만·PII 가드".
  - risk_closure(adversarial) — 종결 0·신규 1(R-EventTimelineS2Hardening 근거 검증).

## ❌ 달성하지 못한 것 & 왜
- **실 Postgres 마이그레이션 라이브 실행 미검증:** backend 테스트 관례가 mock 기반(실 DB 미연결)이라 `alembic upgrade`를 실 DB에 돌리지 않음. 형상(메타데이터)·DDL dialect 컴파일·revision 체인은 검증하나 "실 Postgres가 이 DDL을 수용"은 범위 밖(정직 표기). S2 CRUD 착수 시 실 DB E2E 권장.
- **embedding 환경 실패 1건 미수정:** S1 범위 밖(`.env` 설정 이슈), 손대지 않음.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 실 Postgres에서 0004 up/down 동작(다음 S2 실 DB 라운드에서 확인). embedding 실패는 `.env` EMBEDDING_PROVIDER 설정 소관.

## ⚠️ 이번 턴 종결/갱신 RISK
- **신규 1:** `R-EventTimelineS2Hardening`(LOW) — S2 전 확정 항목: ① event_updates CASCADE vs append-only 긴장 ② Event tz/UUID 경계 방어 ③ is_snapshot_bidirectional 실 호출/강제 ④ evidence/source_refs 전문 미저장·PII 가드. **종결 0.** 순 open 25 → **26**.

## 👉 다음 할 일
1. **[S2 — Event Resolution]** `cross_source_dedup` 출력을 Event append로 라우팅(`cluster_event_map`/`event_links` 별도 migration 0005) + Event/EventUpdate **CRUD 서비스**(이중쓰기 시 is_snapshot_bidirectional 강제 + tz/UUID 방어) + heat/FSD + merge_score 3축 + clique 게이트(R-FalseMerge).
2. (S2 동반) `R-EventTimelineS2Hardening` ①~④ 정책 확정.
3. (이월) `R-ContentTypeGateDormant`, `R-Gdelt429`.

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/app/models/event_timeline.py`(신규), `backend/app/models/event.py`(event_id FK+use_alter+인덱스), `backend/app/models/__init__.py`, `backend/app/schemas/events.py`(Event/EventUpdate), `backend/alembic/versions/0004_event_timeline.py`(신규), `backend/tests/test_event_timeline.py`(신규 17).
- 문서: `docs/_RISK/RISK_REGISTER.md`(신규 R-EventTimelineS2Hardening), `PROJECT_STATUS.md`. 권위: `EVENT_SCHEMA.md` Part 2, `19 §1`, ADR#16/#17.
- 감사: architecture SOUND · code(adversarial) 2 blocking→수정·잠금 · test 1451 green · evidence APPROVED · risk_closure 신규 1 검증.

---
_as_of: 2026-06-22 · S1 Event 토대(events/event_updates/event_cards.event_id FK + ORM/Pydantic + alembic 0004 additive) · 측정 게이트 backend+ingestion 1451 green(회귀 0) · 5-감사단(architecture SOUND·code 2 blocking→수정·test green·evidence APPROVED·risk_closure) · cluster_event_map/event_links S2 이월 · 신규 LOW risk 1 open 26 · pre-existing embedding 실패 1(S1 무관) · 커밋 보류(지시 대기)_

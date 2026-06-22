# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 그동안 가짜(in-memory) 환경에서만 검증하던 Event 토대(S1~S2e)를 **진짜 PostgreSQL에 올려 실제로 동작하는지 검증**했습니다. 같은 사건이 거의 동시에 두 번 들어와도 **이벤트가 하나만 생기고 쓰레기 데이터(orphan)가 안 남는지**, 사건 이력이 실수로 **삭제되지 않게 DB가 막아주는지**를 실제 DB로 입증했습니다.
- **이번 턴에 실제로 끝낸 것:** Docker Postgres + disposable 테스트 DB로 **alembic 0001~0006 실 마이그레이션(up/down)** + **실 DB E2E 15**(CREATE/APPEND/HOLD·멱등·FSD·sanitize·**2-세션 동시 CREATE orphan 0**·**FK RESTRICT 삭제 차단**·confdeltype 직접 단언). 감사 보호용 **alembic 0006(FK CASCADE→RESTRICT)** 신설·검증. 적대 감사 보강(confdeltype 회귀 고정·헤더 톤다운·xdist 직렬 명시) 반영. **측정 게이트 backend 202 + ingestion 1328 = 1530 green**(회귀 0).
- **지금 막힌 것:** 없음(BLOCKED 0). 검증은 **disposable 테스트 DB** 기준(운영 배포·실시간 수집 흐름 결선은 아직 — 다음 단계 live wiring). LLM/RAG/Entity는 이번 턴 미구현(원칙대로 deterministic 토대 우선). pre-existing embedding 환경 실패 1(live-PG 무관) 유지.

## 📋 자동 수집 사실 (machine_status.json)
- HEAD `5718df5`(S2e) 위 미커밋 변경 = **code 5 + docs 8**.
- code: `0006_fk_restrict_audit.py`(신규)·`test_event_resolution_live_pg.py`(신규 14)·`event_timeline.py`/`event_resolution.py`(FK RESTRICT)·`test_event_timeline.py`/`test_event_resolution.py`/`test_event_timeline_service.py`(DDL·chain 갱신).
- 열린 RISK: **R-EventTimelineS2Hardening ① DB 레벨 종결**(④ 상류만 잔여)·**R-FalseMerge 동시성 live 입증**(held 승격만 잔여)·R-EventModelMigration migration 부분 입증(3엔진 잔여).

## ✅ 이번 턴에 달성한 것 (A. live-PG E2E)
- **live-PG 인프라(ADR#21):** `docker compose up -d postgres`(기존 정의) + 선언 드라이버(asyncpg/psycopg/alembic, `requirements/serve.txt`) .venv 설치 + **disposable 테스트 DB `event_intel_test`**(운영 `event_intel` 미오염) + async engine fixture(테스트별 TRUNCATE 격리) + **psycopg 도달성 실패 시 모듈 graceful skip**(미연결 CI 비차단, fake 로 대체 안 함).
- **alembic 0001~0006 실 Postgres up/down:** 5+1 마이그레이션이 텍스트 파싱이 아니라 **실 DB DDL** 로 적용·downgrade 가역 확인. 테이블 7종·event_cards.event_id nullable·cluster_event_map PK·event_links CheckConstraint·6 인덱스 실 형상 검증.
- **실 DB E2E 15:** 첫 CREATE→events+cluster_event_map · 2번째 보도→APPEND(**새 카드 0**) · transitive 약신호→event_links(possible) 보류 · 재실행 멱등 · FSD(**실 LEAST/GREATEST**) 단조 · evidence/source_refs sanitize(**실 JSONB**) · append-only 누적 · tz-naive→timestamptz aware · UUID/str 경계 · set_snapshot 쌍방향+탈취 거부 · FK 4개 confdeltype='r' 직접 단언.
- **★ 2-세션 동시 CREATE race 실증 ★:** `asyncio.gather` 2 세션이 동일 cluster CREATE → 실 Postgres unique(cluster_event_map PK) + apply_routing rollback 으로 **최종 Event 1·cluster_event_map 1·orphan 0·event_updates 중복/누락 0**. fake/mock 으로 불가했던 핵심 동시성 입증.
- **alembic 0006(FK RESTRICT, ADR#20):** event_updates/cluster_event_map/event_links FK CASCADE→**RESTRICT** + ORM 정합 + live-PG up/down + **`DELETE FROM events`(감사 이력 보유)가 IntegrityError 로 차단**됨(`test_live_fk_restrict_blocks_event_delete_with_history`) → 적대 B-2(감사 보호 app 한정·DB 미보호) **해소**, DB 레벨 감사 보호 달성.
- **7-감사단:** architecture **SOUND**(naming_convention 부재·transactional DDL 확인 → 0006 constraint 이름 정합 검증) · pipeline **SOUND** · evidence **APPROVED**(공개 사건 정보=개인데이터 아님·creds dev 기본값·외부 호출 0) · code+risk_closure(adversarial) **CONDITIONAL→보강**: confdeltype 4 FK 직접 단언 테스트 추가(A-3 사각 종결)·"DB 레벨 종결→test-DB 입증"/"동시성 실증→결과 불변식" 헤더 톤다운(B-1/B-2)·xdist 직렬 명시(A-2).
- **검증:** backend **202**(187 + live-PG 15) + ingestion **1328** = **1530 green**(회귀 0) · 1 pre-existing 환경 실패(embedding, live-PG 무관) · Event 단위 75(DDL RESTRICT 갱신 반영).

## ❌ 달성하지 못한 것 & 왜
- **live wiring(수집→Event) 미배선:** `event_resolution_pipeline` production 호출 여전히 0 — 라이브 흐름은 event_cards 직접 생성(Event 아님). live-PG 는 **토대가 실 DB 에서 동작함**을 입증했지만 **실 수집 데이터가 Event 로 흐르는 결선은 다음 단계**(C. live wiring).
- **3엔진(PG/Milvus/OpenSearch) 색인 정합 미검증:** live-PG 는 PG 만. Event 스냅샷↔3엔진 card_id 드리프트(R-EventModelMigration)는 색인 경로 미결선이라 잔여.
- **heat(S2.5)·merge_score entity/domain(S4)·LLM 보조(S5/S6):** 승인 스코프 밖, 이월(deterministic 토대 우선 원칙).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 운영 DB 0006 배포·실 수집 데이터의 Event 라우팅 정확도(live wiring 후 입증)·3엔진 정합. embedding 실패는 `.env` 소관.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-EventTimelineS2Hardening:** ①②③ **종결**(① FK RESTRICT 0006 live-PG·DB 레벨 감사 보호 달성, ②③ live-PG 입증). **④ 상류(candidate_for/delta_summary 전문·PII 가드)만 잔여** → LOW 유지.
- **R-FalseMerge:** **2-세션 동시 CREATE orphan 0 + 통합 E2E live-PG 실증**. clique+HOLD+동시성 방어 입증 → LOW 유지, **held event 중복/승격 정책만 open**.
- **R-EventModelMigration:** alembic 0001~0006 실 DB up/down + Event append live-PG **부분 입증**. **3엔진 색인 정합 잔여**(MEDIUM 유지).
- 신규 0 · 완전 종결 0(부분 종결/하향) · open 카운트 유지 · GDELT/DcToS/ContentTypeGate 무변경.

## 👉 다음 할 일
1. **[C. live wiring]** `event_resolution_pipeline`을 실 수집 흐름(raw_events/candidate queue → cross_source_dedup → pipeline → **Event**)에 결선 + candidate_for 매퍼 + 상류 evidence/PII 가드(R-EventTimelineS2Hardening ④ closure).
2. **[D. frontend/Docker 데모]** `/api/events` Event 경유(피처 플래그) + frontend Event timeline 렌더 + 주기 수집 결선 → "주기적으로 Event 가 쌓이고 업데이트되는 웹" 가시화.
3. (이월) heat 4신호(S2.5) · merge_score entity/domain(S4) · LLM 보조 레이어(S5/S6) · 3엔진 색인 정합 · 운영 DB 0006 배포.

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/tests/test_event_resolution_live_pg.py`(live-PG 14) · `backend/alembic/versions/0006_fk_restrict_audit.py` · `event_timeline.py`/`event_resolution.py`(FK RESTRICT).
- 문서: `_DECISIONS/2026-06.md`(ADR#20 갱신·ADR#21 신설) · `_RISK/RISK_REGISTER.md`(R-EventTimelineS2Hardening ①종결·R-FalseMerge 동시성·R-EventModelMigration) · EVENT_SCHEMA·_CANONICAL/02·2_ROADMAP/{00,15,19}.
- 인프라: docker-compose postgres + event_intel_test(disposable) + alembic 0001~0006 실 DB.

---
_as_of: 2026-06-22 · A. live-PG E2E 검증 — Docker Postgres + disposable test DB(ADR#21)로 S1~S2e 를 실 PostgreSQL 검증: alembic 0001~0006 up/down · E2E 15(CREATE/APPEND/HOLD·멱등·FSD 실 LEAST/GREATEST·sanitize 실 JSONB·**2-세션 동시 CREATE orphan 0**·set_snapshot·confdeltype 직접 단언) · **alembic 0006 FK RESTRICT**(ADR#20 DB 레벨 감사 보호, DELETE 차단 입증) · 측정 게이트 1530 green(회귀 0) · 7-감사단(adversarial 보강: confdeltype 회귀 고정·헤더 톤다운) · R-EventTimelineS2Hardening ①②③ test-DB 입증·R-FalseMerge 동시 결과 불변식 live 입증·R-EventModelMigration migration 부분 · 다음=live wiring(수집→Event)/frontend Docker 데모 · 미커밋(S2e=5718df5 위) · pre-existing embedding 실패 1(무관)_

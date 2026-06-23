# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** D-2c — **합성(synthetic) Event 데이터 seed**를 만들어 **로컬에서 사용자가 웹 브라우저로 Event 타임라인을 실제로 보는 것**을 처음으로 보여줬습니다(제품 북극성의 첫 실거동 가시화). + 운영/seed 가 **잘못된 DB(운영/prod)에 쓰는 것을 구조적으로 차단**하는 가드를 추가했습니다.
- **이번 턴에 실제로 끝낸 것:** ① `seed_event_timeline.py`(합성 Event 4건·자연어 변화요약·멱등·외부호출 0) + ② `db_target.py`(**2중 fail-closed** 가드: APP_ENV allowlist[dev/test만]+dbname prod-마커 교차검증 → R-EventSinkDbTarget **종결**) + ③ compose `EVENT_TIMELINE_API_ENABLED` 데모 on. **실증(로컬·비-컨테이너):** live-PG(event_intel_test) seed → uvicorn `/api/events/timeline` 4건(내부 식별자 미노출) → **Next.js `next dev`+Playwright 브라우저 스크린샷**(목록 4 카드·상세 4 update+evidence 렌더) → 기존 `/events`(event_cards) graceful 회귀 무사. **측정: backend 261 passed/4 skipped/0 failed(변경 표면 72 green 포함) + ingestion 1331 = 1592 green · frontend tsc 0/test 12/lint 0.** 4-감사단(architecture SOUND·legal PASS; adversarial/code-review 가 가드의 denylist fail-open·APP_ENV 단일 신뢰 지적 → allowlist+dbname 교차검증으로 보강).
- **지금 막힌 것:** 없음(BLOCKED 0). **D-2c 미커밋(커밋 지시 대기).** full `docker compose up --build` 빌드 E2E 는 미수행(로컬 uvicorn+next dev 로 대체 실증 — 잔여) · delta_summary 자연어화(현재 디버그 라벨, 상류 책임)는 이월.

## 📋 자동 수집 사실 (machine_status.json)
- HEAD `180a866`(provider 격리 커밋, 직전 턴) 위 **D-2c 미커밋 변경 = code 3신규+1수정 + docs 8**.
- 신규(code): `backend/app/tools/{seed_event_timeline.py,db_target.py}` · `backend/tests/test_seed_event_timeline.py`. 수정(code): `backend/app/tools/run_event_orchestration.py`(_target_db_label 위임). 수정(설정): `docker-compose.dev.yml`. docs 8: `_DECISIONS/2026-06`(ADR#27)·`_RISK/{RISK_REGISTER,RISK_CLOSED}`·`_CANONICAL/02`·`5_REFERENCE/EVENT_SCHEMA`·`2_ROADMAP/{00,15,19}`.
- 열린 RISK **28**(직전 29 → R-EventSinkDbTarget 종결로 −1): R-EventTimelineRenderHardening(② delta_summary 잔여, LOW)·R-EventTimelineApiScale·R-EventTimelineS2Hardening·R-EventModelMigration·R-FalseMerge·R-ExpansionPartialFailure 유지.

## ✅ 이번 턴에 달성한 것 (D-2c 데모 — 합성 seed + DB target 가드 + 브라우저 E2E)
- **합성 Event seed(ADR#27):** `backend/app/tools/seed_event_timeline.py`(신규) — Event 4건(AI 접근정책/반도체 공급망/공공데이터 API 장애/기상 특보) × update 3~4개. `event_timeline_service` **직접** 영속(create_event→**map_cluster**[매핑 게이트 통과]→append_update; 이벤트당 단일 원자 commit). **외부 API/LLM/embedding 호출 0**(전 경로 결정론). 자연어 `delta_summary`·example.com evidence(allowlist 키)·**멱등**(cluster_id 안정키 재실행 시 skip). write flag(EVENT_RESOLUTION_ENABLED) **불필요**(seed 는 ingestion sink 가 아니라 service 직접 영속 → read flag 만 필요 — 데모 표면 최소).
- **DB target 2중 fail-closed 가드(ADR#27, R-EventSinkDbTarget 종결):** `backend/app/tools/db_target.py`(신규) — `assert_safe_write_target`: ① **APP_ENV allowlist**(dev/test 만 무명시 허용; staging/production·오타·미지 환경 모두 거부 — denylist 의 fail-open 회귀 차단), ② **dbname prod-마커 교차검증**(APP_ENV=dev 오설정 + DATABASE_URL→prod 우회 차단 — APP_ENV 단일 신뢰 회피). `--allow-non-dev-db` opt-in 으로만 우회. `target_db_label`(host:port/dbname, 자격증명 제외). runner `_target_db_label` 도 이 단일 출처로 위임(seed/runner 동일 정책).
- **compose 데모 flag:** `docker-compose.dev.yml` backend 에 `EVENT_TIMELINE_API_ENABLED=${...:-true}`(데모 on, write flag 와 분리). `.env.example` 은 이미 키 보유(무변경).
- **실증(로컬·비-컨테이너):** ① live-PG(event_intel_test) seed→`list_events`(4건 매핑 노출)·`get_public_event`(읽을 수 있는 updates) 통합테스트 3 + 가드 단위 16 = **seed 스위트 19 passed**. ② 로컬 uvicorn(flag on) `/api/events/timeline` 4건·`/timeline/{id}` 4 updates JSON 확인(**primary_entity_ids·snapshot_card_id·source_refs wire 미노출** 재확인). ③ **Next.js `next dev`+Playwright 브라우저 스크린샷** — 목록(4 카드: 제목·활성·domains/tags·업데이트일)·상세(타임라인 4 update: 시각·자연어 본문·evidence 링크+source_type·role 렌더). ④ 기존 `/events`(event_cards) graceful 빈상태(회귀 0).
- **4-감사단:** architecture **SOUND**(0 blocking; flag 직교·매핑 게이트·원자성·decoupling 보존) · legal **PASS**(투자조언/실기업/PII/전문 0·example.com 합성·내부 식별자 구조적 차단) · adversarial **CONDITIONAL→충족**(가드 denylist fail-open·APP_ENV 단일 신뢰·"북극성 최초" 과장 지적 → allowlist+dbname 교차검증 보강·"로컬 첫 가시화"로 톤다운) · code-review(F4 denylist→allowlist 전환 반영, make_url import 정리·ISO evidence round-trip·멱등 트랜잭션 clear).
- **검증:** **backend 261 passed/4 skipped/0 failed**(변경 표면 runner/api/timeline/live-PG/seed 72 green 포함; 4 skip=milvus_wrapper 3[RUN_MILVUS_INTEGRATION env-gated]·openai smoke 1[env-gated]) · ingestion **1331** = **1592 green** · frontend **tsc 0·test 12·lint 0** · secret PASS(13 파일)·docs_lifecycle conflicts 0.

## ❌ 달성하지 못한 것 & 왜
- **full `docker compose up --build` 빌드 E2E 미실행:** 검증은 live-PG(event_intel_test) + 로컬 uvicorn/`next dev` + Playwright 로 수행(이미지 빌드·컨테이너 네트워크 SSR fetch 경로는 미수행). compose flag/문서만 추가 → **closure condition 으로 남김**(과장 안 함). 또한 dev DB(`event_intel`)는 timeline 테이블 미마이그레이션이라 compose 데모는 `alembic upgrade head`+seed 선행 필요.
- **delta_summary 자연어화(R-EventTimelineRenderHardening ② 잔여):** 실 수집 결선은 `"{confidence}:{reason}"` 디버그 라벨 → 합성 seed 로 **데모 품질**만 확보(실 데이터 본문 가독성=상류 `event_ingest_pipeline` 생성 책임, 별개 이월).
- **seed 는 합성 데이터:** 실 수집 아님. 실 데이터 타임라인 가독성은 delta_summary 자연어화 이후.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: full compose 빌드 E2E 실거동(컨테이너 SSR fetch `INTERNAL_API_BASE_URL` 경로·production 빌드)·실데이터 타임라인 가독성(delta_summary 자연어화 후)·대규모 응답 plan(R-EventTimelineApiScale).
- **가드 잔여 한계(정직):** prod 마커 없는 DB명 + APP_ENV 오설정이 동시 발생하는 극단 케이스는 휴리스틱 밖 — 배포 환경변수 규율이 최종 방어선(R-Auth 동일 한계).

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-EventSinkDbTarget → CLOSED(2026-06-23):** APP_ENV allowlist + dbname prod-마커 교차검증 2중 fail-closed 가드(`db_target.py`) + seed/runner 단일 출처 공유 + 테스트(dev/test 허용·staging/prod·오타 env 거부·dev+prod dbname 거부·자격증명 미노출). 흐름은 `RISK_CLOSED.md`. (adversarial 의 "APP_ENV 단일 신뢰" 지적을 dbname 교차검증으로 보강해 CLOSED 정당화.)
- **유지(거짓 종결 0):** R-EventTimelineRenderHardening(② delta_summary 자연어화 잔여)·R-EventTimelineApiScale(단건 페이지네이션)·R-EventTimelineS2Hardening·R-EventModelMigration·R-FalseMerge·R-ExpansionPartialFailure. delta_summary 자연어화·event_cards↔Event 자동연결·약신호 cluster_id 안정키는 각 선행 전까지 유지.

## 👉 다음 할 일
1. **[커밋 대기]** D-2c 변경(code 3신규+1수정 + docs 8) 커밋 여부 사용자 지시 대기. push 금지.
2. **[다음 단계 후보]** ① full `docker compose up --build` 빌드 E2E(컨테이너 SSR fetch 경로 입증·R-EventTimelineRenderHardening 잔여와 별개) · ② 주기 auto-trigger(Celery beat — R-EventTimelineS2Hardening) · ③ event_cards↔Event 자동연결(R-EventModelMigration) · ④ delta_summary 자연어화(상류, 실데이터 가독성).
3. (이월) 단건 updates 페이지네이션 · heat 4신호(S2.5) · 약신호 cluster_id 안정키.

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/app/tools/{seed_event_timeline.py,db_target.py}`(신규)·`run_event_orchestration.py`(위임)·`backend/tests/test_seed_event_timeline.py`·`docker-compose.dev.yml`.
- 실증: live-PG seed 스위트 19 green·변경 표면 72 green·로컬 uvicorn API 4건·Playwright 브라우저 스크린샷(목록/상세).
- 문서: `_DECISIONS/2026-06`(ADR#27)·`_RISK/{RISK_REGISTER(R-EventSinkDbTarget 제거),RISK_CLOSED(종결 이관)}`·`_CANONICAL/02`·`5_REFERENCE/EVENT_SCHEMA`·`2_ROADMAP/{00,15,19}`.

---
_as_of: 2026-06-23 · D-2c 데모(합성 Event seed `seed_event_timeline` — 자연어 delta_summary·example.com evidence·멱등·외부호출 0, service 직접 영속 create_event→map_cluster→append_update + DB target 2중 fail-closed 가드 `db_target`[APP_ENV allowlist+dbname prod-마커 교차검증, R-EventSinkDbTarget 종결] + compose `EVENT_TIMELINE_API_ENABLED` on). **실증(로컬·비-컨테이너): live-PG seed→uvicorn `/api/events/timeline`(내부ID/source_refs 미노출)→Next.js `next dev`+Playwright 브라우저 스크린샷(목록 4카드·상세 4 update+evidence)→event_cards graceful 회귀 = 제품 북극성("웹에서 Event 타임라인을 본다") 첫 실거동 가시화.** 측정 **backend 261 passed/4 skip/0 fail(변경 표면 72 green) + ingestion 1331 = 1592 green · frontend tsc 0/test 12/lint 0 · secret PASS · docs_lifecycle 0.** 4-감사단(architecture SOUND·legal PASS; adversarial/code-review 가드 보강[denylist→allowlist+dbname]·"북극성" 톤다운[로컬 첫 가시화]). **R-EventSinkDbTarget 종결, 열린 28.** **D-2c 미커밋(커밋 지시 대기). full compose 빌드 E2E·delta_summary 자연어화 이월. push 안 함._
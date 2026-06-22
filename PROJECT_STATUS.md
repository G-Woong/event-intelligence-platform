# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** ① 직전에 깔아둔 "여러 소스의 같은 사건을 하나의 Event 타임라인으로 누적하는" 경로(C live wiring)를 **커밋(`4585a25`)으로 안정화**했고, ② 그 경로를 **운영 수집 도구가 실제로 켤 수 있게 결선(D-1)**했습니다. 이제 운영 러너를 `--event-resolution`으로 돌리면 수집 후보가 카드 남발이 아니라 **Event로 쌓이고 두 번째 보도는 업데이트로 붙는** 흐름이 실제 PostgreSQL에 기록됩니다(실DB로 CREATE→APPEND 입증).
- **이번 턴에 실제로 끝낸 것:** D-1 운영 결선 — `backend/app/tools/run_event_orchestration.py`(backend가 수집 도구를 재사용하면서 Event 영속 sink를 만들어 주입하는 **단일 결선 지점**) + 전용 DB 엔진 생명주기 소유 + feature flag(기본 꺼짐) + 운영자가 어느 DB에 쓰는지 보이는 가드. **측정 게이트 backend 232 + ingestion 1331 = 1563 green**(회귀 0). 7-감사단(적대 감사가 지적한 "운영/테스트 DB 혼동"·"통합 0-커버리지"·"sink 실패 가림"을 출력 가드·통합 테스트·관찰성 수정으로 보강).
- **지금 막힌 것:** 없음(BLOCKED 0). 단 **주기 자동 실행은 아직**입니다 — 러너를 정기적으로 깨우는 스케줄러(Celery beat/cron)는 미배선이라, "사람이 켜면 쌓이는 능력"은 확보했으나 "스스로 주기적으로 쌓는" 단계는 D-2/Phase 2 이월. 실 소스 수집(production-validation)으로 Event를 1회 쌓아보는 운영 입증도 이월. event_cards↔Event 자동연결도 다음. pre-existing embedding 환경 실패 1(아래, D-1 무관).

## 📋 자동 수집 사실 (machine_status.json)
- HEAD `4585a25`(C live wiring 커밋) 위 **미커밋 D-1 변경 = code 5(신규 3 + 수정 2) + docs 7**. (machine_status 스냅샷은 C 시점이라 turn=41·head=33f019c로 stale — Stop 훅이 재스캔.)
- 신규: `backend/app/tools/run_event_orchestration.py`·`backend/app/tools/__init__.py`·`backend/tests/test_run_event_orchestration.py`. 수정: `ingestion/tools/run_production_orchestration.py`(main seam)·`backend/app/services/event_ingest_pipeline.py`(docstring 정정)·`backend/tests/test_event_resolution_live_pg.py`(+D-1 sink live-PG).
- 열린 RISK 27: **신규 R-EventSinkDbTarget**(운영/테스트 DB 혼동, LOW-MEDIUM·완화됨) · R-EventTimelineS2Hardening(D-1 composition root DONE, 주기 트리거/운영배포 잔여) · R-EventModelMigration·R-FalseMerge·R-ExpansionPartialFailure 유지(미종결).

## ✅ 이번 턴에 달성한 것 (C 커밋 + D-1 운영 결선)
- **C live wiring 커밋(`4585a25`):** code 6 + docs 6, secret PASS·docs_lifecycle green 확인 후 커밋. working tree clean(push 안 함).
- **docs 권위 재판정 → D-1 확정:** 00_ROADMAP_INDEX §4("CLI 결선")·15 Phase S1("CLI/runner sink 결선 이월")·PROJECT_STATUS 다음할일#1이 **모두 D-1을 S2 즉시 잔여로 일치**. S5(Expansion) acceptance가 "candidate→확장→**Event append**"라 Event 영속 경로가 먼저 살아야 함 → D-1 선행 일관. "S5를 먼저 하라"는 문서 없음. 코드 대조: `run_production_orchestration.main()`이 sink 미주입 = 운영 자동경로 영속 0 확정.
- **불일치 보고 + 사용자 결정:** PROJECT_STATUS 문자 plan(ingestion CLI에 `--event-resolution`)은 **decoupling 불변식**(ingestion 런타임 backend import 0)과 충돌(첫 ingestion→backend import). 사용자가 **backend-side composition root** 선택.
- **D-1 결선(ADR#23):** `backend/app/tools/run_event_orchestration.py` — backend→ingestion(허용 방향)으로 `run_production_orchestration.main` 재사용 + `make_orchestration_event_sink` 주입. **전용 NullPool async engine 생명주기를 backend가 소유**(API 풀 엔진 미재사용 — sink가 호출당 asyncio.run 구동이라 loop 간 커넥션 누수 차단). ingestion `main(argv, *, event_resolution_sink=None)`으로 seam을 main 레벨까지 연장(**Callable만 받음 — ingestion→backend import 0, decoupling 보존**).
- **flag/운영 옵션:** `EVENT_RESOLUTION_ENABLED`(기본 false) 또는 `--event-resolution`. 둘 다 꺼지면 sink=None → orchestration core byte-identical(DB 미접근, event_cards 경로 보존). ON이면 **대상 DB host:port/dbname를 stdout에 명시**(자격증명 제외 — 운영/테스트 DB 혼동 방어).
- **CREATE/APPEND/HOLD 운영 결선:** live-PG로 **실 sink(make_orchestration_event_sink + 실 DB factory)** → candidate records → CREATE(첫 배치)→APPEND(2번째 배치 새 Event 0) 입증. end-to-end 통합 테스트(실 ingestion_main dry-run → 실 orchestration → 주입 sink 실제 호출)로 결선 경로 입증.
- **7-감사단:** architecture **CONDITIONAL**(0 blocking; decoupling 보존·NullPool 생명주기 타당; allow_abbrev 권고 반영) · adversarial **1 BLOCKING→보강**(운영/테스트 DB 혼동→대상 DB 출력 가드+RISK 등재 · 통합 0-커버리지→통합 테스트 추가 · sink 실패 all-None 가림→WIRED_BUT_FAILED 출력 · live-PG PASS not skip 확인 · "byte-identical" 문구 정정) · evidence **APPROVED**(LLM 0·network 0(Event path)·.env 미노출·sanitize 보존·투자조언 0) · code **3건→보강**(dead logger 제거·sink 실패 관찰성 수정·`--` 엣지 low 잔존) · pipeline **SOUND**(seam 1회 호출·후보 단위 격리·부분영속 orphan 0) · test/risk_closure 통과.
- **검증:** backend **232**(+9 D-1 tool) · ingestion **1331** = **1563 green**(회귀 0) · live-PG D-1 sink **PASS**(skip 아님) · 1 pre-existing embedding 환경 실패(아래) · 4 skipped.

## ❌ 달성하지 못한 것 & 왜
- **주기 자동 가동 미배선(정직):** D-1은 러너의 결선 *능력*을 만든다 — 그러나 러너를 주기적으로 자동 실행하는 스케줄러(Celery beat/cron)는 코드에 없다(Phase 2). "운영 자동 경로가 스스로 Event를 쌓는다"는 (능력) + (주기 트리거) + (실 production-validation) + (운영 DB alembic 적용)이 모두 필요. 현재는 수동 실행 결선까지.
- **실 production-validation 미실행:** live-PG 입증은 synthetic records(테스트 DB) 기준 — 실 소스 probe→Event 누적은 운영 배포 시 입증(이월).
- **event_cards.event_id 자동연결 이월:** Event와 card 분리 운영(R-EventModelMigration).
- **약신호 cluster_id 안정성·heat(S2.5)·merge_score(S4)·LLM 보조(S5/S6):** 승인 스코프 밖, 이월(deterministic 토대 우선).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 실 수집 데이터의 Event 라우팅 정확도(실 production-validation 후 입증)·주기 자동 가동 운영 안정성·약신호 cluster_id 운영 안정성·3엔진 정합.
- **pre-existing embedding 실패(live wiring/D-1 무관):** `test_get_embedding_client_singleton` 1건 FAIL — `monkeypatch` 없이 실 `settings.EMBEDDING_PROVIDER`(.env=openai)로 실 OpenAI provider 인스턴스화(테스트 격리 결함). full backend 런타임(~16분)도 이 1건이 아니라 여러 backend 테스트가 실 `.env`(LLM/EMBEDDING=openai)로 외부 provider를 호출하는 환경 결합. 둘 다 pre-existing·환경 결합이고 D-1 Event path는 deterministic·network 0(evidence APPROVED). 수정안(차기): conftest에서 LLM/EMBEDDING=mock 강제 + 네트워크 차단.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-EventSinkDbTarget(신규, LOW-MEDIUM):** `--event-resolution`이 `settings.DATABASE_URL`(기본 dev DB)에 바인딩. **완화:** ON 시 대상 DB stdout 명시 + off-by-default. **잔여:** 구조적 가드(APP_ENV/명시 확인) 미배선.
- **R-EventTimelineS2Hardening(LOW 유지):** **D-1 composition root DONE**(운영 결선 능력 확보, live-PG 입증). 잔여: 주기 auto-trigger·실 production-validation·운영 DB 0006 배포 + ④ 영속층 title/delta passthrough 가드.
- **R-EventModelMigration(MEDIUM 유지)·R-FalseMerge(LOW 유지)·R-ExpansionPartialFailure(미종결):** D-1이 손대지 않음 → 유지(event_cards 자동연결·약신호 split·query_generator는 별개).
- 신규 1(R-EventSinkDbTarget) · 완전 종결 0 · GDELT/DcToS/ContentTypeGate 무변경.

## 👉 다음 할 일
1. **[D-2 frontend/Docker 데모]** `/api/events` Event 경유(피처 플래그) + frontend Event timeline 렌더 → "사건이 카드·타임라인으로 보이는 웹" 가시화.
2. **[Phase 2 주기 트리거]** Celery beat/cron으로 `run_event_orchestration --event-resolution` 주기 실행(sink는 sync task 강제 — asyncio.run 제약) → 운영 자동 가동. + 실 production-validation 1회 Event 누적 입증.
3. **[보강]** event_cards↔Event 자동연결(ADR) · R-EventSinkDbTarget 구조적 DB 가드 · 약신호 cluster_id 안정키 · 영속층 title/delta passthrough 가드.
4. (이월) heat 4신호(S2.5) · merge_score entity/domain(S4) · LLM 보조 레이어(S5/S6) · 3엔진 색인 정합.

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/app/tools/run_event_orchestration.py`(composition root+sink+CLI) · `ingestion/tools/run_production_orchestration.py`(main seam+관찰성) · `backend/app/services/event_ingest_pipeline.py`(docstring 정정).
- 테스트: `backend/tests/test_run_event_orchestration.py`(9: flag OFF/ON·engine dispose·예외 dispose·CM 게이트·main 위임·off-default·**end-to-end 통합**) · `test_event_resolution_live_pg.py`(+D-1 sink live-PG: 실 DB CREATE→APPEND).
- 문서: `_DECISIONS/2026-06.md`(ADR#23) · `_RISK/RISK_REGISTER.md`(R-EventSinkDbTarget 신규·R-EventTimelineS2Hardening D-1) · EVENT_SCHEMA·_CANONICAL/02·2_ROADMAP/{00,15,19}.

---
_as_of: 2026-06-23 · D-1 운영 결선 — `backend/app/tools/run_event_orchestration.py`(backend-side composition root: 전용 NullPool 엔진 생명주기 소유 + `make_orchestration_event_sink` 주입 → ingestion `main(event_resolution_sink=)` 위임; **ingestion→backend import 0, decoupling 보존**). flag(`EVENT_RESOLUTION_ENABLED`/`--event-resolution`, 기본 off)·대상 DB stdout 가드·후보 단위 격리. live-PG: 실 sink candidate→CREATE→APPEND · end-to-end 통합(실 orchestration이 주입 sink 호출). 측정 게이트 backend 232 + ingestion 1331 = **1563 green**(회귀 0). 7-감사단(adversarial blocking: 운영/테스트 DB 혼동 → 대상 DB 출력 가드+RISK; code: dead logger 제거·sink 실패 관찰성 수정). **잔여: 주기 auto-trigger(Celery beat)·실 production-validation·event_cards↔Event 자동연결·R-EventSinkDbTarget 구조적 가드.** C live wiring 커밋 `4585a25`. D-1 미커밋(커밋 지시 대기). pre-existing embedding 실패 1(테스트 격리 결함, D-1 무관)_

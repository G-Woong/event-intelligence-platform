# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 그동안 "수집된 사건이 곧장 카드(event_cards)로 한 장씩 박히던" 구조 옆에, **같은 사건을 여러 소스에서 모아 하나의 Event 타임라인으로 누적하는 새 경로**를 깔았습니다. 두 번째 보도가 새 카드가 아니라 **기존 사건에 업데이트로 붙고**, 무관한 사건이 잘못 합쳐지지 않으며, 애매한 후보는 보류되는 흐름을 **실제 PostgreSQL로 검증**했습니다.
- **이번 턴에 실제로 끝낸 것:** Event live wiring 경로(`event_ingest_pipeline`: 수집 후보 → 중복제거 → 매퍼 → 사건 라우팅 → events/event_updates) + 주기 수집 도구에 **주입형 결선구(sink)** 추가(기존 동작 무변경). feature flag(`EVENT_RESOLUTION_ENABLED`, 기본 꺼짐)로 분리, 본문/PII 차단, 후보 단위 실패 격리. **측정 게이트 backend 223 + ingestion 1331 = 1554 green**(회귀 0). 7-감사단(적대 감사가 지적한 "sink ON 경로 미검증·단일소스 사건 silent 누락"을 테스트·집계로 보강).
- **지금 막힌 것:** 없음(BLOCKED 0). 단 **운영 자동 실행(CLI)은 아직 이 경로를 켜지 않음**(결선구만 열림 — Event 자동 영속은 배포 단계 이월). event_cards는 그대로 병행, 사건↔카드 자동 연결은 다음 단계. pre-existing embedding 환경 실패 1(아래 진단, live wiring 무관).

## 📋 자동 수집 사실 (machine_status.json)
- HEAD `33f019c`(live-PG) 위 미커밋 변경 = **code 6(신규 2 + 수정 4) + docs 6**.
- 신규: `backend/app/services/event_ingest_pipeline.py`·`backend/tests/test_event_ingest_pipeline.py`. 수정: `config.py`·`run_production_orchestration.py`·`test_production_orchestration_runner.py`·`test_event_resolution_live_pg.py`·`.env.example`.
- 열린 RISK: R-FalseMerge(약신호 cluster_id split 신규 잔여 추가)·R-EventModelMigration(event_cards↔Event 자동연결 이월)·R-EventTimelineS2Hardening(④ 기본 매퍼 가드 완료, 임의 주입 passthrough+운영배포 잔여)·R-ExpansionPartialFailure(별개 모듈, 미종결).

## ✅ 이번 턴에 달성한 것 (C. live wiring)
- **Ground Truth 판정:** 라이브 카드 경로(agent graph→`upsert_card`)는 event_cards 직접 생성, `cross_source_dedup`·`event_resolution_pipeline` production 호출 **0**. ingestion↔backend 는 HTTP/주입형 콜러블(`db_writer`)로 결합(backend 직접 import 안 함). `cluster_records` 는 `run_production_orchestration:354` 에서 이미 호출(보고용).
- **wiring 합성층(ADR#22):** `event_ingest_pipeline.py` — `cross_source_dedup`(순수 stdlib)과 `event_resolution_pipeline`(결정·영속)을 잇는 **유일한 backend/app 합성층**(순수 결정/영속 계층의 ingestion-비의존 보존, 순환 import 0). `candidate_from_cluster` 매퍼(primary record→ResolvedCandidate; **title 상한 512·provenance delta·allowlist evidence·짧은 source_refs = 본문/PII 차단**) + `build_record_index`(cross_source_dedup 와 동일 `compute_record_key` 로 member key 역매핑) + `ingest_records_to_events`(flag 게이트 + **후보 단위 try/except 격리** + `singletons_dropped` 가시화).
- **production 삽입점:** `run_production_orchestration(event_resolution_sink=None)` 주입 seam(`db_writer` 패턴과 동일, cross_source_dedup 직후 호출, try/except 격리, 기본 None=기존 동작 byte-identical, result["event_resolution"]).
- **CREATE/APPEND/HOLD 실증:** 첫 배치→CREATE(events+cluster_event_map) · 같은 사건 2번째 배치→**APPEND(새 Event 0)** · transitive 약신호→event_links(possible) 보류 · 재실행 멱등 · 강신호 cluster_id 입력순서 불변(APPEND 누적 안정).
- **event_cards 호환:** Event 경로는 events/event_updates 에만 write(event_cards **무변경 병행**, `s.cards=={}` 입증). `event_cards.event_id` 자동연결은 이월(set_snapshot 명시 연결만).
- **flag 게이트:** off 면 DB 미접근(영속 0) — `_ExplodingSession`·settings 경로·live-PG count 0 으로 입증. 기존 event_cards 경로만 동작.
- **live-PG 입증:** 수집 후보 records→Event CREATE→APPEND(실 DB)·flag off 영속 0·**실 DB 후보 단위 격리**(한 클러스터 실패 rollback 이 다른 클러스터 commit 훼손 0)·evidence 실 JSONB sanitize.
- **7-감사단:** architecture **SOUND**(0 blocking; seam=db_writer 일관·경계 1곳·flag DB 미접근) · evidence **APPROVED**(본문/PII 미저장·투자조언 0·외부호출 0·LLM 0·secret 0·event_cards 병행) · adversarial **CONDITIONAL→보강**: blocking(`make_orchestration_event_sink` ON 경로 0-커버리지)→**ON 경로 테스트 추가** + CLI 미결선 정직 표기 + 단일소스 silent drop→`singletons_dropped` 집계 + 약신호 cluster_id split→RISK 등재.
- **검증:** backend **223**(187 비-live + live-PG 18 + wiring 18) + ingestion **1331** = **1554 green**(회귀 0) · 1 pre-existing embedding 환경 실패(아래) · 4 skipped.

## ❌ 달성하지 못한 것 & 왜
- **운영 자동 경로 Event 영속 0(정직):** orchestration sink seam 은 검증됐으나 CLI `main()` 은 아직 backend-bound sink 를 주입하지 않는다 — session/engine 생명주기·flag 결선은 배포 단계(D/operational) 이월. production 자동 실행은 현재 Event 영속 0(seam 만 열림).
- **event_cards.event_id 자동연결 이월:** Event 와 card 가 당분간 분리 운영(카드↔Event 매칭 정책 ADR 필요, R-EventModelMigration).
- **약신호 cluster_id 안정성 미보장:** 강신호(canonical_url)는 입력순서 불변(테스트 입증) 이나 약신호(meta: 키)는 `members[0]` 최소인덱스 의존 → 배치 간 멤버집합 변동 시 같은 사건 split 가능. 약신호 Event 활성화 전 순서불변 회귀 필수(R-FalseMerge 신규 잔여).
- **단일소스 사건 미생성:** cross_source_dedup 단일멤버 제외로 단독 보도는 Event 미생성(`singletons_dropped` 로 가시화만). 제품 정책 결정 이월.
- **heat(S2.5)·merge_score entity/domain(S4)·LLM 보조(S5/S6)·3엔진 색인 정합:** 승인 스코프 밖, 이월(deterministic 토대 우선).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 운영 자동 경로의 실 수집 데이터 Event 라우팅 정확도(CLI 결선 후 입증)·3엔진 정합·약신호 cluster_id 운영 안정성.
- **pre-existing embedding 실패 + backend 지연 진단(live wiring 무관):** `test_get_embedding_client_singleton` 1건 FAIL — `monkeypatch` 없이 실 `settings.EMBEDDING_PROVIDER`(.env=openai)를 읽어 실 OpenAI provider 를 인스턴스화(테스트 격리 결함). **별개로 full backend 런타임(~16분)은 이 1건이 아님** — embedding 테스트를 deselect 해도 비-live 205개가 15:48 소요 확인 → **실 `.env`(LLM_PROVIDER/EMBEDDING_PROVIDER=openai + OPENAI_API_KEY)를 로드해 여러 backend 테스트가 실 외부 provider/evidence-reachability 를 호출**하는 환경 결합이 원인(suite 가 mock 을 강제 안 함). 둘 다 **pre-existing·환경 결합**이고 Event live wiring 은 deterministic·네트워크 0(evidence_review LLM 0 확인) — blocker 아님. 수정안(차기): 테스트 conftest 에서 `LLM_PROVIDER=EMBEDDING_PROVIDER=mock` 강제 + 네트워크 차단.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-FalseMerge(LOW 유지):** C wiring 에서도 clique+HOLD 동작(fake+live-PG). 강신호 cluster_id 입력순서 불변 회귀 고정. **신규 잔여 추가**: 약신호 cluster_id split(입력순서 변동 시 같은 사건 재-CREATE) — 약신호 활성화 전 회귀 필수.
- **R-EventTimelineS2Hardening(LOW 유지):** **④ candidate_for 매퍼 배선 + 본 경로 가드 완료**(title 512·provenance delta·sanitize, legal APPROVED·live-PG 실 JSONB). 잔여: 임의 `candidate_for` 주입 시 title/delta passthrough(영속층 상한 가드) + 운영 DB 0006 배포.
- **R-EventModelMigration(MEDIUM 유지):** Event 경로 event_cards 무변경 병행(비파괴) 입증. 잔여: 3엔진 정합 + **event_cards.event_id 자동연결 이월**(카드↔Event 역참조 공백).
- **R-ExpansionPartialFailure(미종결):** event_ingest 가 후보 단위 격리 패턴 선례 구현했으나 원 대상 `query_generator.generate_batch` 는 미수정 → **종결/하향 아님**(별개 모듈).
- 신규 RISK 0(약신호 split 은 R-FalseMerge 에 흡수) · 완전 종결 0 · GDELT/DcToS/ContentTypeGate 무변경.

## 👉 다음 할 일
1. **[D-1 운영 결선]** `run_production_orchestration` CLI/runner 에 `make_orchestration_event_sink(async_sessionmaker(engine))` 결선(session 생명주기·`--event-resolution` 플래그) → 운영 자동 경로에서 Event 가 실제로 쌓이게.
2. **[D-2 frontend/Docker 데모]** `/api/events` Event 경유(피처 플래그) + frontend Event timeline 렌더 → "주기적으로 Event 가 쌓이고 업데이트되는 웹" 가시화.
3. **[보강]** event_cards↔Event 자동연결 정책(ADR) · 약신호 cluster_id 안정 키 · 단일소스 사건 정책 · 영속층 title/delta passthrough 가드.
4. (이월) heat 4신호(S2.5) · merge_score entity/domain(S4) · LLM 보조 레이어(S5/S6) · 3엔진 색인 정합.

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/app/services/event_ingest_pipeline.py`(매퍼+ingest+sink) · `ingestion/tools/run_production_orchestration.py`(sink seam) · `backend/app/core/config.py`(flag) · `.env.example`.
- 테스트: `backend/tests/test_event_ingest_pipeline.py`(18) · `test_production_orchestration_runner.py`(sink 3) · `test_event_resolution_live_pg.py`(wiring live-PG 3).
- 문서: `_DECISIONS/2026-06.md`(ADR#22) · `_RISK/RISK_REGISTER.md`(R-FalseMerge/R-EventTimelineS2Hardening/R-EventModelMigration/R-ExpansionPartialFailure) · EVENT_SCHEMA·_CANONICAL/02·2_ROADMAP/{00,15}.

---
_as_of: 2026-06-22 · C. live wiring — 수집 후보 records → cross_source_dedup → candidate_for 매퍼 → event_resolver → events/event_updates 경로(`event_ingest_pipeline`) + `run_production_orchestration(event_resolution_sink=)` 주입 seam. feature flag(`EVENT_RESOLUTION_ENABLED` 기본 off)·후보 단위 격리·본문/PII 차단·singletons 가시화. event_cards **무변경 병행**(자동연결 이월). live-PG: candidate→CREATE→APPEND·flag off 영속 0·실 DB 후보 격리. 측정 게이트 backend 223 + ingestion 1331 = **1554 green**(회귀 0). 7-감사단(adversarial blocking: sink ON 경로 0-커버리지 → ON 경로 테스트 추가·CLI 미결선 정직표기·singletons 집계·약신호 split RISK 등재). **잔여: CLI/runner sink 결선(운영 자동경로 영속 0, 이월)·event_cards↔Event 자동연결·약신호 cluster_id 안정키.** pre-existing embedding 실패 1(테스트 격리 결함, live wiring 무관)_

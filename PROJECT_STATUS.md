# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 같은 사건의 여러 보도를 **하나의 진화하는 Event로 라우팅**하는 결정층(S2-core a~c)을 깔았습니다 — 강한 증거는 합치고(APPEND/CREATE), 약한 연결은 자동 병합하지 않고 보류(HOLD)합니다. 적대 감사가 "무관한 두 사건이 약한 제목 유사성으로 잘못 합쳐지는" **실제 결함(B1)을 잡아 즉시 교정**했습니다.
- **이번 턴에 실제로 끝낸 것:** S2a(alembic 0005: cluster_event_map/event_links + ORM/Pydantic) · S2b(cross_source_dedup에 clique 게이트 + Jaccard 연속값 보존, additive) · S2c(event_resolver 순수 라우팅). **측정 게이트 backend+ingestion 1477 green**(회귀 0). heat·merge_score 2축·CRUD 영속은 **분리 이월**(S2d/S4).
- **지금 막힌 것:** 없음(BLOCKED 0). 단 결정층만 구현 — 라우팅 결정을 실제 DB에 적용(held_members→event_links, S2d)하는 영속층은 아직 미배선(의도된 단계 분리). backend pre-existing 환경 실패 1건(embedding, S2 무관) 유지.

## 📋 자동 수집 사실 (machine_status.json)
- session 4e61… turn 14 · 변경 11건 = **code 10 + other 1**. code_py_loc 160.
- code_files: `0005_event_resolution.py`, `models/{__init__,event_resolution}.py`, `schemas/events.py`, `services/event_resolver.py`, `cross_source_dedup.py`, 테스트 4.
- audit_types(권위): **architecture·code·pipeline·test_review** → 전부 라우팅·완료. 열린 RISK **26 유지**(R-FalseMerge MEDIUM→LOW-MEDIUM 하향, 종결/신규 0).

## ✅ 이번 턴에 달성한 것
- **S2a — Event Resolution 토대(alembic 0005):** `ClusterEventMapORM`(cluster_id→event_id 단일 진실원천) + `EventLinkORM`(event↔event, status possible/confirmed/rejected/merged + CheckConstraint, 약신호 자동병합 금지) + ORM/Pydantic. additive+downgrade, FK events CASCADE, sorted_tables 순환 0.
- **S2b — cross_source_dedup 확장(additive, R-FalseMerge):** `CrossSourceDedupResult`에 `signal_strength`(Jaccard 연속값 보존, 1비트 양자화 폐기) + `clique_ok` + `weak_only_members`(edge provenance) 추가. 기존 소비처(summarize_clusters/run_production_orchestration) 비파괴.
- **S2c — event_resolver 순수 라우팅:** `resolve_routing` → APPEND(강신호+clique) / HOLD(약신호·clique 미달 → possible_link) / CREATE(미매핑). ingestion 비의존(문자열 값 계약 + N3 contract 테스트).
- **적대 blocking B1 교정(핵심):** clique_ok를 "강신호 끝점인가" → **강신호 단일 연결성분이 전체 멤버를 덮는가**로 수정. 두 강성분(A-B강, C-D강)이 약신호(B-C)로만 브릿지된 오병합을 차단 + 회귀(`test_two_strong_components_bridged_by_weak_is_not_clique`). B2(테스트 사각)·N3(값 계약 drift) 동반 수정.
- **5-감사단:** architecture(orchestrator) **SOUND** · pipeline(orchestrator) **SOUND** · evidence(legal) **APPROVED**(수집/전문/PII/투자조언 표면 0) · code(adversarial) **CONCERNS→B1/B2/N3 수정·잠금** · test **PASS**(1477 green).
- **검증:** backend+ingestion **1477 passed**(backend 149=기존+S2 28, ingestion 1328=S1 1323+S2 5, 회귀 0) · 1 pre-existing 환경 실패(embedding, S2 무관) · 직접 영향 재검증 dedup 12/resolver 9.

## ❌ 달성하지 못한 것 & 왜
- **영속 적용층(S2d) 미구현:** resolver 결정(`held_members`→event_links possible, mapped_event_id→cluster_event_map 조회/기록)을 DB에 적용하는 `event_timeline_service`는 의도된 분리 이월. 현재 dedup·resolver 양쪽 단위 테스트만(입력 직접 주입) — 실 dedup 출력을 resolver에 먹이는 **통합 E2E는 S2e**.
- **merge_score entity_overlap/domain_distance·heat 4신호 이월:** entity_overlap=S4(Entity Registry), domain_distance=거버넌스 ADR(θ UNKNOWN), heat=S2.5. 승인된 스코프(signal_strength+clique만).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 실 dedup→resolver 통합 시 라우팅 정확성(S2e E2E에서 입증), 실 Postgres 0005 up/down. embedding 실패는 `.env` 소관.

## ⚠️ 이번 턴 종결/갱신 RISK
- **하향 1:** `R-FalseMerge` MEDIUM→**LOW-MEDIUM** — clique 게이트(강신호 단일 연결성분, B1 교정) + signal_strength + provenance를 decision layer에 구현, transitive/두-강성분 브릿지 차단 회귀. 잔여 = S2d 영속 + 통합 E2E. **신규/종결 0, open 26 유지.** `R-EventTimelineS2Hardening` ①~④는 S2d로 명시.

## 👉 다음 할 일
1. **[S2d — CRUD 영속]** `event_timeline_service`(create_event/append_update append-only/get/set_snapshot) — `is_snapshot_bidirectional` 강제 + tz-aware/UUID 방어(R-EventTimelineS2Hardening ②③) + resolver `held_members`→`event_links(possible)` 적재 + `cluster_event_map` 조회/기록.
2. **[S2e — FSD + 통합 E2E]** first_seen_at 단조 + "2번째 보도→기존 Event Update append"(실 cluster_records→resolver→영속) + transitive-only 자동승격 0 입증(R-FalseMerge closure).
3. (이월) heat 4신호(S2.5) · merge_score entity/domain 축(S4/ADR) · 실 Postgres migration E2E.

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/app/models/event_resolution.py`·`alembic 0005`·`backend/app/services/event_resolver.py`·`ingestion/orchestration/cross_source_dedup.py`(clique+B1) + Pydantic + 테스트 4.
- 문서: `docs/_RISK/RISK_REGISTER.md`(R-FalseMerge 하향+DONE), `docs/_DECISIONS/2026-06.md`(ADR#18), `PROJECT_STATUS.md`. 권위: `12 §2.1·§4.2`, `19 §2.2`, EVENT_SCHEMA Part 2.
- 감사: architecture SOUND · pipeline SOUND · evidence APPROVED · code(adversarial) B1/B2/N3 수정 · test 1477 green.

---
_as_of: 2026-06-22 · S2-core(a~c) Event Resolution decision layer — alembic 0005(cluster_event_map/event_links) + cross_source_dedup clique 게이트(B1 교정: 강신호 단일 연결성분) + event_resolver 라우팅 · 측정 게이트 1477 green(회귀 0) · 5-감사단(adversarial B1 오병합 차단) · R-FalseMerge MEDIUM→LOW-MEDIUM · S2d(CRUD 영속)/S2e(통합 E2E) 이월 · 미커밋(S1=87807ea 위) · pre-existing embedding 실패 1(S2 무관)_

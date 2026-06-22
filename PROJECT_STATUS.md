# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 여러 소스가 같은 사건을 보도할 때, **실제 중복판정(dedup)→사건 라우팅(resolver)→DB 영속(apply_routing)을 하나로 잇는 통합 파이프라인(S2e)**을 깔았습니다. 같은 사건의 2번째 보도는 새 카드가 아니라 **기존 Event에 업데이트로 붙고**, 약하게만 닮은 후보는 자동 병합하지 않고 보류합니다 — 상용 웹앱이 제공할 "사건 타임라인"의 토대.
- **이번 턴에 실제로 끝낸 것:** `event_resolution_pipeline`(실 dedup→resolver→apply 배선, ingestion 비의존) + 통합 로직 E2E 11(2번째 보도→append·transitive 약신호 보류·재실행 멱등·FSD 단조·sanitize 유지·동시 CREATE 패배+held 결합) + apply_routing **동시 CREATE rollback**(orphan 0) + **삭제정책 ADR#20**. 적대 감사가 잡은 **2 blocking(rollback 트랜잭션 소유 계약·ADR#20 감사보호 과대주장) 즉시 교정**. **측정 게이트 backend 187 + ingestion 1328 = 1515 green**(회귀 0).
- **지금 막힌 것:** 없음(BLOCKED 0). 통합은 **in-memory fake session**으로 로직을 입증했고 **실 Postgres E2E(migration/FK/2-세션 동시성)는 이월**(DB fixture 부재 — 정직 표기). LLM은 본경로에 넣지 않고 보조 레이어 경계만 열어둠. backend pre-existing 환경 실패 1(embedding, S2e 무관) 유지.

## 📋 자동 수집 사실 (machine_status.json)
- session 4e61… · HEAD `0b7c1d8`(S2d) 위 미커밋 변경 = **code 3 + docs 8**.
- code: `event_resolution_pipeline.py`(신규), `event_timeline_service.py`(apply_routing 동시성 하드닝), `test_event_resolution_pipeline.py`(신규 통합 10).
- audit_types(권위): 변경 기준 라우팅. 열린 RISK — R-FalseMerge **LOW-MEDIUM→LOW 하향(미종결)**, R-EventTimelineS2Hardening ① 정책 결정(ADR#20). 신규/종결 카운트는 closeout 에서 확정.

## ✅ 이번 턴에 달성한 것
- **S2e — 통합 파이프라인(`event_resolution_pipeline`):** 실 `cross_source_dedup.cluster_records` → `event_resolver.resolve_routing` → `event_timeline_service.apply_routing` 배선. **ingestion 비의존**(클러스터 duck-typed `.cluster_id/.confidence/.clique_ok/.duplicate_group/.weak_only_members`, candidate_for 콜백). LLM 경계만 개방(현재 전 경로 결정론 — raw truth 덮어쓰기 금지).
- **통합 로직 E2E(in-memory fake session, 실 상태 전이):** ① 첫 클러스터→CREATE+cluster_event_map ② **2번째 보도→기존 Event APPEND(새 카드 0)** ③ transitive 약신호 멤버(blog) 자동병합 0→event_links(possible) 보류 ④ 두-강성분 약신호 브릿지 둘 다 보류 ⑤ 동일 cluster 재실행 멱등(Event 1개) ⑥ **FSD: first_seen 과거로만·last_update 미래로만** ⑦ evidence/source_refs sanitize 파이프라인 통과 후 유지.
- **동시성 하드닝:** apply_routing CREATE 가 cluster_event_map 매핑 패배 시 **rollback 으로 orphan event 폐기 + 승자로 append degrade**(orphan 0). mock 단위 입증(실 2-세션은 live-PG 이월).
- **ADR#20 — 삭제정책:** "app-layer hard-delete 미제공 + status 라이프사이클". R-EventTimelineS2Hardening ① 정책 결정(FK RESTRICT migration 은 live-PG 이월).
- **7-감사단:** architecture **SOUND** · pipeline **SOUND**(non-blocking 3, 정직 이월) · evidence **APPROVED** · code+risk_closure(adversarial) **2 blocking 적발→교정**: (A-1) apply_routing rollback 이 전체 tx rollback(SAVEPOINT 아님)이라 외부 공유 tx 미사용 계약 명시 + held+패배 결합 테스트 추가, (B-2) ADR#20 "감사 보호"가 FK CASCADE 그대로라 **app 경로 한정**으로 정정(DB 레벨 미보호 명시) · test **PASS**(1515 green).
- **검증:** backend **187**(176 + 통합 11) + ingestion **1328** = **1515 green**(회귀 0) · 1 pre-existing 환경 실패(embedding, S2e 무관) · 직접 영향 재검증 Event 계열·dedup 12.

## ❌ 달성하지 못한 것 & 왜
- **live-PG 통합 E2E 미실행:** backend 테스트가 mock 기반·DB fixture 부재라, 통합을 in-memory fake session 으로 입증했다(실 Postgres migration/FK CASCADE/2-세션 동시성은 미실증). "실 DB 검증 완료"라 쓰지 않는다 — live-PG 이월.
- **FK RESTRICT migration(0006)·held event 중복/승격 정책:** ADR#20 가 정책(app no-delete)은 결정했으나 FK 전환 migration 은 live-PG 검증 시점 이월. held member 가 나중에 강신호로 자기 resolution 시 중복 Event 가능성은 S2e+ 재평가.
- **heat 4신호(S2.5)·merge_score entity/domain(S4):** 승인 스코프 밖, 이월. merge_score = signal_strength+clique만 실제 구현 유지.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 실 Postgres 에서 migration up/down·FK 동작·2-세션 동시 CREATE 멱등(현재 cluster_event_map PK + rollback 로직으로 방어, 라이브 미입증). embedding 실패는 `.env` 소관.

## ⚠️ 이번 턴 종결/갱신 RISK
- **하향 1(미종결):** `R-FalseMerge` LOW-MEDIUM→**LOW** — 실 dedup→resolver→apply 통합 로직 E2E 로 transitive-only 자동병합 0 입증. **단 live-PG 2-세션 동시성·held 승격 정책 잔여로 open 유지**(사용자 기준7).
- **정책 결정 1:** `R-EventTimelineS2Hardening` ① — ADR#20 으로 app no-delete + status 라이프사이클 결정(FK migration 이월). ②③④ 는 S2d 처리.
- **유지(범위 밖, 무변경):** R-EventModelMigration(3엔진 드리프트), R-Gdelt429·R-DcToS·R-ContentTypeGateDormant 상태 그대로. 신규 0.

## 👉 다음 할 일
1. **[live-PG E2E]** 실 Postgres(또는 테스트 DB fixture)에서 alembic 0004/0005 up/down · FK CASCADE 동작 · **2-세션 동시 CREATE 멱등(orphan 0)** 실증 → R-FalseMerge·R-EventTimelineS2Hardening ① 완전 종결.
2. **[FK RESTRICT migration 0006]** event_updates FK CASCADE→RESTRICT(감사 보호) + cluster_event_map/event_links per-table 삭제정책(ADR#20 후속).
3. (이월) heat 4신호(S2.5) · merge_score entity/domain(S4) · LLM 보조 레이어(중요도/확장계획/요약 — 결정론 토대 위에).

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/app/services/event_resolution_pipeline.py`(통합 배선) · `event_timeline_service.py`(apply_routing 동시성) · `backend/tests/test_event_resolution_pipeline.py`(통합 10).
- 문서: `docs/_DECISIONS/2026-06.md`(ADR#20) · `docs/_RISK/RISK_REGISTER.md`(R-FalseMerge 하향·R-EventTimelineS2Hardening ① 결정) · EVENT_SCHEMA·_CANONICAL/02·2_ROADMAP/{00,15,19}. 권위: `19 §2.2·§21.1·§16`, EVENT_SCHEMA Part 2.
- 감사: architecture·pipeline·code·test·evidence·risk_closure·adversarial(closeout).

---
_as_of: 2026-06-22 · S2e Event Resolution 통합 파이프라인 — `event_resolution_pipeline`(실 dedup→resolver→apply 배선, ingestion 비의존) + 통합 로직 E2E 11 + apply_routing 동시 CREATE rollback + ADR#20 삭제정책(app 경로 한정) · 측정 게이트 1515 green(회귀 0) · 7-감사단(adversarial 2 blocking: rollback tx 계약·ADR#20 과대주장 교정) · R-FalseMerge LOW 하향(미종결, live-PG 잔여)·R-EventTimelineS2Hardening ① app-layer 정책만 결정(DB CASCADE 미보호) · live-PG E2E/FK migration/heat/merge_score 이월 · 미커밋(S2d=0b7c1d8 위) · pre-existing embedding 실패 1(S2e 무관)_

# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 같은 사건의 여러 보도를 하나의 진화하는 Event로 라우팅하는 **결정(S2-core)을 실제 DB에 저장하는 영속층(S2d)**을 깔았습니다 — 새 카드 대신 기존 Event에 변화분 append, 약한 연결은 자동 병합 않고 보류(possible 링크), 카드↔Event 양방향 정합을 강제합니다.
- **이번 턴에 실제로 끝낸 것:** `event_timeline_service`(create/append-only/get/set_snapshot/cluster_event_map/event_links/apply_routing) + 방어(tz·UUID·전문/PII 차단). **측정 게이트 backend+ingestion 1504 green**(회귀 0). 적대 감사가 잡은 **실제 결함 3종(쌍방향 단언이 형식뿐·apply_routing 비원자성 orphan·sanitize 누수)을 즉시 교정**했습니다.
- **지금 막힌 것:** 없음(BLOCKED 0). 단 영속층까지만 — 실 dedup→resolver→영속을 잇는 통합 E2E와 교차-트랜잭션 동시성 멱등성은 **S2e 이월**(의도된 단계 분리). backend pre-existing 환경 실패 1건(embedding, S2d 무관) 유지.

## 📋 자동 수집 사실 (machine_status.json)
- session 4e61… turn 21 · HEAD `1487a2a`(S2-core) 위 미커밋 변경 = **code 2 + docs 7 + PROJECT_STATUS**.
- code_files: `services/event_timeline_service.py`(신규), `tests/test_event_timeline_service.py`(신규 27 회귀).
- audit_types(권위): **architecture·code·evidence·risk_closure·test_review** → 전부 라우팅·완료. 열린 RISK **26 유지**(신규/종결 0; R-EventTimelineS2Hardening·R-FalseMerge severity 서술만 갱신).

## ✅ 이번 턴에 달성한 것
- **S2d — `event_timeline_service` CRUD 영속층(ADR#19):** `create_event`(FSD) · `append_update`(**append-only** INSERT만 + last_update GREATEST/first_seen LEAST) · `get_event`(Event+updates) · `set_snapshot`(카드 탈취 거부 + **실제 영속값 재조회**로 is_snapshot_bidirectional 검증) · `get_cluster_event`/`map_cluster`(on_conflict_do_nothing=단일 진실원천) · `hold_link`(event_links possible) · `apply_routing`.
- **resolver 결정 → 영속 연결:** CREATE→events INSERT+cluster_event_map / APPEND→event_updates append(새 카드 0) / HOLD→append 0(오병합 금지). `held_members`→degenerate held event + `event_links(possible→primary)` 보류(가역).
- **ADR#19 — held_members 영속 설계:** event↔event 스키마(양단 NOT NULL FK→events) vs held_members(record key) 충돌을 degenerate held event materialize로 해소(대안 self-link/별도테이블/생략 대비 정당).
- **방어(R-EventTimelineS2Hardening ②③④ 처리):** tz-naive→UTC · UUID/str 경계 · evidence/source_refs는 **allowlist 키 + scalar 값만** 영속(전문 본문·중첩 dict/list 은닉·임의 PII 차단).
- **적대 감사 blocking 3종 즉시 교정:** ① set_snapshot 단언이 trivially-true(자기 의도값 비교)였던 것 → **실제 영속값 재조회 검증**으로. ② apply_routing이 sub-op마다 개별 commit→부분 실패 orphan → **단일 원자 트랜잭션**(commit=False+1회 commit)+CREATE get-first 가드. ③ `_sanitize_evidence`가 str 길이만 검사→非scalar 누수 → **scalar-only**.
- **5-감사단:** architecture(orchestrator) **SOUND** · evidence(legal) **APPROVED**(전문/PII/투자조언/우회 표면 0) · code+risk_closure(adversarial) **CONCERNS→3 blocking 교정·잠금** · test **PASS**(1504 green).
- **검증:** backend **176**(149 기존+S2d 27, 격리 모듈 import 0 확인) + ingestion **1328** = **1504 passed**(회귀 0) · 1 pre-existing 환경 실패(embedding, S2d 무관) · alembic 0001→0005 체인 무결성 테스트.

## ❌ 달성하지 못한 것 & 왜
- **통합 E2E(S2e) 미배선:** 실 `cross_source_dedup`→`resolver`→`apply_routing` end-to-end("2번째 보도→기존 Event append", transitive-only 자동승격 0)는 단위(mock 세션) 검증만. 원자성·단조성의 **실 DB 동작은 mock으로 미커버** → S2e.
- **교차-트랜잭션 동시 CREATE race:** apply_routing 단일 tx + get-first 가드는 *순차 재실행* orphan만 제거. *동시* CREATE(둘 다 미매핑 조회 후 각자 create)는 DB unique 제약/advisory lock 필요 → S2e 이월(정직 기록).
- **heat 4신호(S2.5)·merge_score entity/domain(S4)·실 Postgres migration up/down:** 승인된 스코프 밖, 이월.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 실 dedup→resolver 통합 시 라우팅 정확성(S2e E2E), 교차-tx 동시성 멱등성(DB 제약 필요), 실 Postgres 0004/0005 up/down. embedding 실패는 `.env` 소관.

## ⚠️ 이번 턴 종결/갱신 RISK
- **신규/종결 0, open 26 유지.** 서술 갱신 2건: `R-EventTimelineS2Hardening` ②③④ S2d 처리(③ 실 재조회 검증·④ scalar-only로 교정 반영; 잔여 = ① CASCADE 결정 + delta_summary 상류 가드). `R-FalseMerge` apply_routing 영속+원자성 DONE 추가, 잔여 = 교차-tx 동시성·통합 E2E(S2e). severity 부당 하향 없음(adversarial risk_closure 확인).

## 👉 다음 할 일
1. **[S2e — FSD + 통합 E2E]** 실 `cluster_records`→`resolver`→`apply_routing` 통합("2번째 보도→append" 입증) + first_seen 단조 + transitive-only 자동승격 0 입증(R-FalseMerge closure) + 교차-tx 동시 CREATE 멱등성 DB 제약.
2. **[정책 결정]** `event_updates`/cluster_event_map/event_links ON DELETE CASCADE vs RESTRICT(감사 로그 의도, R-EventTimelineS2Hardening ①) — ADR.
3. (이월) heat 4신호(S2.5) · merge_score entity/domain(S4/ADR) · 실 Postgres migration E2E.

## 📁 근거 (이번 턴 핵심)
- 코드: `backend/app/services/event_timeline_service.py`(CRUD+apply_routing+방어) + `backend/tests/test_event_timeline_service.py`(27).
- 문서: `docs/_DECISIONS/2026-06.md`(ADR#19), `docs/_RISK/RISK_REGISTER.md`(R-EventTimelineS2Hardening·R-FalseMerge 갱신), `docs/5_REFERENCE/EVENT_SCHEMA.md`·`docs/_CANONICAL/02`·`docs/2_ROADMAP/{00,15,19}`(S2a/S2d 구현 반영). 권위: `19 §2.2·§21.1`, EVENT_SCHEMA Part 2.
- 감사: architecture SOUND · evidence APPROVED · code+risk_closure(adversarial) blocking 3종 교정 · test 1504 green.

---
_as_of: 2026-06-22 · S2d Event 타임라인 CRUD 영속층 — `event_timeline_service`(create/append-only/get/set_snapshot 실검증/cluster_event_map 단일출처/event_links possible/apply_routing 단일 원자 tx) + ADR#19(held_members materialize) · 측정 게이트 1504 green(회귀 0) · 5-감사단(adversarial blocking 3종 즉시 교정) · R-EventTimelineS2Hardening ②③④·R-FalseMerge 갱신 · S2e(통합 E2E·동시성) 이월 · 미커밋(S1=87807ea·S2-core=1487a2a 위) · pre-existing embedding 실패 1(S2d 무관)_

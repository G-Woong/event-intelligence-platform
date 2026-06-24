# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** RAG/지식그래프를 얹기 전에 "사건 데이터가 배치·소스를 넘나들어도 오염되지 않도록" 하부를 다졌습니다. ① **영화/도서/박스오피스 같은 카탈로그 메타가 "공식 사건"으로 잘못 발행되던 누수를 막았고**(완전 종결), ② **같은 사건이 배치마다 새로 쪼개지지 않도록** 사건 고유 식별 층을 새로 만들었습니다(같은 기사 재등장은 해결, 다른 기사가 같은 사건 보도하는 의미 기반은 다음 단계).
- **이번 턴에 실제로 끝낸 것:** ADR#39 문서 커밋(`4ee90a6`) → **ADR#40 구현**: catalog→비발행 override(R-SourceCatalogFidelity **종결**) + cross-batch Event Identity Layer(신규 `event_identity_map` 테이블, R-CrossBatchEventIdentity **부분종결**). 측정: **live-PG 36/36 · backend 329p/4s/0f · ingestion 1342 · frontend tsc0/test12/lint0**.
- **정직한 한계:** cross-batch는 **같은 기사(같은 URL)가 재등장하는 경우만** 닫혔습니다. **다른 기사가 같은 사건을 보도하는 경우(의미 기반 동일성)는 아직 미해결** — 의미 식별(임베딩/LLM/KG)이 필요한데 미구축이라 **R-CrossBatchEventIdentity는 OPEN(부분)으로 정직하게 남겼습니다**(adversarial: 완전 종결은 OVERCLAIM). push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `4ee90a6`**(ADR#39 docs, 본 턴 첫 커밋) 위 **ADR#40 = 미커밋 code 9 + tests 4 + migration 1 + docs 8**.
- code: `run_production_orchestration(_record_type_for)`·`source_content_type`(참조)·`full_source_revival(_VALID_RECORD_TYPES)`·`bridge_to_raw_events`·`source_readiness_closure`·`event_ingest_pipeline(identity_keys)`·`event_resolution_pipeline(identity 승격)`·`event_timeline_service(map/find identity)`·`event_resolution(EventIdentityMapORM)`. migration: `0007_event_identity_map`. tests: `test_event_resolution_live_pg`(+cross-batch 6)·`test_event_ingest_pipeline`(+identity 3·_FakeSession)·`test_event_resolver`(+catalog)·`test_event_timeline_service`(chain 0007)·신규 `test_source_catalog_fidelity`. docs 8: ADR#40·RISK_REGISTER·RISK_CLOSED·CANONICAL/02·ROADMAP{00,15}·EVENT_SCHEMA·RAG_KG_AGENT_READINESS·PROJECT_STATUS.
- 열린 RISK: R-SourceCatalogFidelity **CLOSED**(−1) · R-CrossBatchEventIdentity **부분종결 유지**(open). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (substrate hardening — ADR#40)
- **① ADR#39 docs 커밋**: 8파일 → `4ee90a6`(secret PASS·docs_lifecycle 0·closeout EXACT MATCH 검증 후, push 0).
- **② R-SourceCatalogFidelity 완전 종결**(adversarial CLOSE-JUSTIFIED): `_record_type_for` 가 `source_content_type`(분류 단일 출처)으로 catalog 6종(aladin/tmdb/kofic/kopis/tour/igdb)을 **catalog_metadata 비-publishable**("catalog" source_type, fail-closed)로 둠 — domain→official_record 누수 차단. `_VALID_RECORD_TYPES`·양쪽 source_type 맵·`source_readiness_closure` catalog-aware(3중 drift 정합). non-catalog domain(culture_info=detail) 무변경·vendor route 없음. 범위 한정: catalog 6종(domain group 일반 추정은 범위 밖, 신규 domain 소스 분류 의무 규칙).
- **③ R-CrossBatchEventIdentity 부분종결**(deterministic Event Identity Layer): 신규 `event_identity_map(identity_key→event_id, alembic 0007, FK RESTRICT)` 가 cluster_id 와 분리된 cross-batch 동일성 단일 출처. publishable 강신호 core(weak_only/held 제외) 멤버의 canonical_url/official_id record_key 를 anchor 로 claim(CREATE/APPEND), 미매핑 cluster 가 같은 anchor 면 기존 Event APPEND(분열 방지), 모호(2개+)면 승격 안 함. held anchor 제외로 ADR#38 회귀 0.
- **adversarial 평결**: catalog **CLOSE-JUSTIFIED** · cross-batch **PARTIAL-JUSTIFIED**(FULL-CLOSE=OVERCLAIM). 신규 false-merge hole 0(anchor=기존 record_key 재사용). 신규 잔여: fragment-strip same-URL 오APPEND(모니터링).

## 🧭 cross-batch identity — 닫힌 범위 vs 미해결(정직)
- **닫힌 범위(deterministic):** publishable core 가 **동일 canonical_url/official_id** 재등장(syndicated wire: AP→여러 매체 재게재). live-PG 검증(same→APPEND·different→CREATE·ambiguous→no-merge·idempotent·ingest E2E shared-article no-split).
- **미해결(OPEN):** **공유 anchor 없는** 같은-사건 분열 — 다른 URL 두 기사가 같은 사건을 다른 배치에 보도. semantic/entity identity(임베딩/LLM/KG) 필요·미구현. Description 의 "새 corroborating 기사" 다수가 여기 → **종결 아님**.

## 🔎 source orchestration / 제품 계약
- catalog=**비-publishable catalog_metadata**(KG/entity enrichment 역할 라벨 보존)·news/article=publishable·official=publishable·market/community/search=비발행(signal/corroborator/URL후보)·unknown=fail-closed.
- **제품 계약(raw≠public)**: raw article/catalog/market/community 를 그대로 public 으로 내보내지 않는다. public 단위=사건 Event(향후 Intelligence Unit). 코드로 강제(publish gate+catalog fidelity+cross-batch identity+held 정책). 문서: `RAG_KG_AGENT_READINESS.md §4b`.

## ⚠️ 이번 턴 종결/갱신 RISK
- **종결: R-SourceCatalogFidelity CLOSED**(ADR#40, catalog 6종, RISK_CLOSED 이관).
- **부분종결 유지: R-CrossBatchEventIdentity**(deterministic shared-anchor DONE·live-PG; semantic-only 독립보도 분열+fragment 오APPEND open; RAG/KG 이전 필수 gate).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **cross-batch semantic identity**: 공유 anchor 없는 같은-사건 동일성은 entity/embedding 층 필요(미구축). 별도 RISK 분리 시 ADR 논거 선행(분리가 종결 구실 금지).
- **실 fetch APPEND·실 cross-source 비뉴스 Event·주기 auto-trigger·운영 DB 0007 배포**(검증=event_intel_test).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- UNKNOWN: cross-batch semantic identity 기준(entity+time+domain vs embedding — eval/cost/회귀) → ADR 결정 필요. fragment-strip same-URL=다른 사건 모니터링.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#40 code 9 + tests 4 + migration 1 + docs 8 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** cross-batch **semantic** event identity(entity/embedding 층 ADR — RAG/KG 이전 마지막 substrate gate). 그 다음 실 cross-source 비뉴스 Event·주기 auto-trigger·RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `4ee90a6`(ADR#39 docs). 코드: `event_identity_map`(0007)·`_record_type_for`(catalog override)·identity_keys/map/find.
- 검증: live-PG **36/36**(cross-batch 6+catalog) · backend **329p/4s/0f** · ingestion **1342**(catalog 10) · frontend tsc0/test12/lint0.
- 문서: ADR#40(`_DECISIONS`)·R-SourceCatalogFidelity CLOSED(`_RISK/RISK_CLOSED`)·R-CrossBatchEventIdentity 부분종결(`_RISK/RISK_REGISTER`)·`EVENT_SCHEMA`(event_identity_map)·`RAG_KG_AGENT_READINESS §4/4b`·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-24 · ADR#40 substrate hardening — ① **R-SourceCatalogFidelity CLOSED**(catalog 6종→catalog_metadata 비-publishable source-specific override·`source_content_type` 단일 출처·fail-closed·vendor route 없음·live-PG 0 events·3중 drift 정합; adversarial CLOSE-JUSTIFIED) ② **R-CrossBatchEventIdentity 부분종결**(deterministic Event Identity Layer=신규 `event_identity_map`[alembic 0007, cluster_id 와 분리]·publishable 강신호 core anchor[canonical_url/official_id]→event claim·미매핑 cluster 같은 anchor→APPEND·모호→no-merge·held anchor 제외로 ADR#38 회귀 0; **닫힌 범위=shared-anchor live-PG 6 검증·미해결=semantic-only 독립보도 분열+fragment 오APPEND**; adversarial PARTIAL-JUSTIFIED·FULL-CLOSE=OVERCLAIM). 제품 계약 raw≠public 문서화. **live-PG 36/36 · backend 329p/4s/0f · ingestion 1342 · frontend tsc0/test12/lint0**. ADR#39 docs 커밋 `4ee90a6` 위 ADR#40 미커밋(code 9+tests 4+migration 1+docs 8)·커밋 지시 대기·push 안 함._

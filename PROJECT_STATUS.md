# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** "같은 사건이 잘못 **합쳐지는**(서로 다른 사건이 하나로 뭉치는)" 위험을 실제 DB로 끝까지 검증해 **완전히 닫았습니다**(R-FalseMerge). 보류됐던 근거가 강한 증거로 다시 나타나도 제목이 같으면 기존 사건에 잇고(중복 0) 다르면 별개로 둡니다 — 실 Postgres 30개 테스트로 입증.
- **이번 턴에 실제로 끝낸 것:** ① ADR#38을 `2fd372a`로 커밋 → ② Docker 가동 → **live-PG 30/30 green**(held 승격 3 실증) → ③ **R-FalseMerge 완전 종결**(과대 종결 검증가 JUSTIFIED). 측정: **backend 319p/4s/0f · ingestion 1332 · frontend tsc0/test12/lint0**.
- **정직한 한계:** 닫은 건 "**잘못 합치는**(OVER-merge)" 한 방향뿐입니다. **"같은 사건이 배치마다 새로 쪼개지는"(UNDER-merge)** 문제는 아직 안 닫혔고 **R-CrossBatchEventIdentity**로 새로 등록했습니다. 또 **카탈로그(영화/도서/박스오피스) 메타가 "공식" 사건으로 잘못 발행될 수 있는 누수**를 발견해 **R-SourceCatalogFidelity**로 등록(코드 미수정 — 설계 ADR 필요). RAG/KG/에이전트 층은 대부분 미구축·mock 기본값. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `2fd372a`**(ADR#38 held promotion, 본 턴 첫 커밋) 위 **본 턴 = docs-only 미커밋**(코드 변경 0 — ADR#38 코드는 이미 커밋됨).
- 변경(미커밋): `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#39)·`_RISK/{RISK_REGISTER(R-FalseMerge CLOSED 포인터+신규 2 RISK),RISK_CLOSED(R-FalseMerge)}`·`_CANONICAL/02`·`2_ROADMAP/{00,15}` + 신규 `docs/5_REFERENCE/RAG_KG_AGENT_READINESS.md`. **코드/테스트 변경 0**(본 턴은 종결 검증·문서).
- 열린 RISK: R-FalseMerge **CLOSED**(−1) · 신규 **R-CrossBatchEventIdentity·R-SourceCatalogFidelity**(+2) → 순증 +1. throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (R-FalseMerge 완전 종결 — ADR#39)
- **① ADR#38 커밋**: code 4 + tests 3 + docs 6 = 13파일 → `2fd372a`(secret PASS·docs_lifecycle 0·closeout EXACT MATCH 검증 후 커밋, push 0).
- **② live-PG 실증**: Docker Desktop 가동 → `docker compose up -d postgres` → event_intel_test alembic head → `test_event_resolution_live_pg.py` **30 passed/0 fail/0 skip**(77.6s). **held 승격 3 실 Postgres green**: same-title→parent APPEND(created 0·events 불변=중복 0)·different-title→독립 CREATE(events+1=거짓병합 0)·재처리 멱등(created 0). `find_held_parents` 신규 SQL(aliased self-join+cluster_event_map subquery) 실 DB 실행. + 동시 CREATE orphan 0·FK RESTRICT·transitive weak held·FSD 회귀 동반.
- **③ R-FalseMerge CLOSED**(OVER-merge 한정): clique 게이트 + held-dedup + 입력순서 불변 + held 승격 title-judge(record_key exact AND title-Jaccard 2단 게이트). RISK_CLOSED 이관.
- **adversarial(직전 2턴 OVERCLAIM 잡은 동일 critic) → JUSTIFIED**: 조건 (a) live-PG MET·(b) cross-batch 분리 MET·P1 차단 0·신규 거짓병합 표면 0. **정직성 요건**: 종결 문구에 "OVER-merge 한정·cross-batch UNDER-merge 이월" 명시(반영함).

## 🔎 source orchestration 점검 + 🔴 신규 발견 (catalog fidelity)
- **🔴 catalog 누수 확인(R-SourceCatalogFidelity)**: `run_production_orchestration._GROUP_TO_RECORD_TYPE` 가 **domain→official_record**. catalog 6종(aladin/tmdb/kofic/kopis/tour/igdb) 전부 source_group `domain` → official_record → **publishable "official" Event 로 발행 가능**(영화/도서 메타가 권위 사건화). `source_readiness_closure._GROUP_RECORD_TYPE`(domain→structured_signal)·`source_content_type`(catalog_metadata)와 **3중 drift**. **미수정 사유**: `OFFICIAL_RECORD_ALIVE` 상태 taxonomy 에 박힌 의도된 설계 → hasty-patch 가 status 회귀 위험 → **정책 ADR 필요**(catalog→structured_signal / 별도 비-publishable type / KG enrichment 전용).
- 소스군 상태: news/domain(article)=**LIVE VERIFIED**·official=**PARTIAL**(실 cross-source 비뉴스 미관측)·search/community=**차단(gate)**·market/structured=**signal-only**·unknown=**fail-closed**. 상세 표 `docs/5_REFERENCE/RAG_KG_AGENT_READINESS.md §3`.

## 🧭 cross-batch event identity (Section 4 결정)
- **문제**: `cluster_id=xcluster:{min(member record_keys)}` → 같은 사건에 새 corroborator 가 다음 배치에 추가돼 최소 record_key 가 바뀌면 cluster_id 변경 → 미매핑 → **새 Event 분열**(UNDER-merge). ADR#38 held 승격은 held member 만 커버(비-held mapped core 재등장은 fix 밖).
- **결정: candidate B** — R-FalseMerge(OVER-merge)와 **반대 실패모드**라 별도 **R-CrossBatchEventIdentity(MEDIUM)** 신규 분리·등록. 작은 deterministic guard 도 syndication false-merge 분석 선행 필요 → **Event identity 층 ADR 우선**(hasty guard 금지). **RAG/KG 이전 필수 gate**.

## 📈 RAG/KG/Entity/LLM routing readiness (Section 6 정직 평가)
- **대부분 NOT BUILT/PARTIAL·mock 기본값**(`EMBEDDING_PROVIDER=mock`·`LLM_PROVIDER=mock`). RAG grounded answer/chunking/citation=NOT BUILT, entity canonical/KG edge=NOT BUILT, expansion agent/scheduler=NOT BUILT, LLM router=PARTIAL(llm_propose 테스트 람다). Event substrate(쓰기/발행/타임라인)만 견고. 정직 평가표 신규 문서 `docs/5_REFERENCE/RAG_KG_AGENT_READINESS.md`.
- **신규 RISK 남발 금지**: 미구축 미래층은 roadmap 사실(launch blocker 아님). 실 substrate 차단요인만 RISK 화(R-CrossBatchEventIdentity·R-SourceCatalogFidelity).

## ⚠️ 이번 턴 종결/신규 RISK
- **종결(−1): R-FalseMerge CLOSED**(OVER-merge 한정, live-PG 30/30 실증, adversarial JUSTIFIED, RISK_CLOSED 이관).
- **신규(+2)**: **R-CrossBatchEventIdentity**(MEDIUM, UNDER-merge·같은 사건 배치별 분열·RAG/KG 이전 필수 gate) · **R-SourceCatalogFidelity**(MEDIUM, catalog→official_record 누수·코드 미수정·ADR 필요).
- 유지: RealSourceLoop·S2Hardening·ModelMigration·ExpansionPartialFailure·ApiScale 등.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **cross-batch event identity**: Event identity 가 cluster 멤버십 의존 → 배치 간 동일성 미보장. Event identity 층 ADR(record_key/entity 기반) + live-PG cross-batch 분열 방지 테스트 필요(R-CrossBatchEventIdentity).
- **catalog fidelity**: domain→official_record 누수 코드 미수정(의도된 taxonomy라 ADR 선행). catalog record_type 정책 ADR + 회귀 테스트 + 3중 drift 정합 필요.
- **실 fetch APPEND·실 cross-source 비뉴스 Event·주기 auto-trigger·운영 DB 0006 배포**(R-RealSourceLoopUnproven).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- UNKNOWN: cross-batch event identity 기준(record_key 역인덱스 vs entity+time semantic — syndication false-merge trade-off) → ADR 결정 필요. catalog record_type 정책(structured_signal vs 별도 type vs KG-only) → ADR 결정 필요.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 docs-only(7파일: 6 수정 + 1 신규) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** R-CrossBatchEventIdentity(Event identity 층 ADR)·R-SourceCatalogFidelity(catalog record_type ADR) — **RAG/KG 이전 필수 gate**. 그 다음 실 cross-source 비뉴스 Event·실 fetch APPEND·주기 auto-trigger.

## 📁 근거 (이번 턴 핵심)
- 커밋: `2fd372a`(ADR#38). 검증: live-PG **30/30**(held 승격 3) · backend **319p/4s/0f** · ingestion 1332 · frontend tsc0/test12/lint0.
- 발견: `run_production_orchestration._GROUP_TO_RECORD_TYPE`(domain→official_record 누수) · readiness(mock-default).
- 문서: ADR#39(`_DECISIONS`) · R-FalseMerge CLOSED(`_RISK/RISK_CLOSED`) · R-CrossBatchEventIdentity·R-SourceCatalogFidelity(`_RISK/RISK_REGISTER`) · `RAG_KG_AGENT_READINESS.md`(신규) · `_CANONICAL/02` · `2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-24 · ADR#39 — R-FalseMerge 완전 종결(OVER-merge 한정): ADR#38 커밋(`2fd372a`)→Docker 가동→**live-PG 30/30 green(held 승격 3 실증: same→parent APPEND·중복 0/different→독립 CREATE/멱등)**→R-FalseMerge CLOSED(clique+held-dedup+입력순서불변+held 승격 title-judge[record_key exact AND title-Jaccard 2단 게이트], RISK_CLOSED 이관, adversarial JUSTIFIED). cross-batch UNDER-merge(같은 사건 배치별 분열→결과적 중복)=**R-CrossBatchEventIdentity**(MEDIUM) 분리·등록·catalog(domain)→official_record 누수 발견=**R-SourceCatalogFidelity**(MEDIUM, 미수정·ADR 필요) 등록. RAG/KG/agent 대부분 NOT BUILT/PARTIAL·mock-default(`RAG_KG_AGENT_READINESS.md` 신규). **backend 319p/4s/0f · ingestion 1332 · frontend tsc0/test12/lint0 · live-PG 30/30**. 본 턴 코드 변경 0(docs-only 7파일)·커밋 지시 대기·push 안 함._

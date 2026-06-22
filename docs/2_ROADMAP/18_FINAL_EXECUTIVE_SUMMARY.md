# 18 — FINAL EXECUTIVE SUMMARY

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 📘 REFERENCE — 경영자 요약 + 엔지니어 next tasks. **섹션별 기준일 상이**(A=전략, B=2026-06-18 P0배선 PARTIAL 실사실, 수익화=ADR#15 개정).
> │ **구현순위:** #5 (00_ROADMAP_INDEX) · **그룹:** A
> │ **검증 근거:** §B P0 배선 PARTIAL DONE은 실사실(`_CANONICAL/01`·`_RISK` R-Integration, ap_news 100 카드 라이브 E2E). 수익화 단락은 ADR#15로 **전면 재작성**(구독 4티어 = 레거시 허위방향, 교정 완료).
> │ **잔여(미구현):** Event 토대(S1)·P/G/F 실배선·광고/커뮤니티 표면 전부. 본 문서는 전략 서사이지 구현 사실 아님.
> │ **완료정의(DoD):** 구현 사실 갱신은 `_CANONICAL/*`에서만(미구현을 구현됨으로 적지 않음). 본 문서는 방향·우선순위 정합 유지.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 결정 = `_DECISIONS/2026-06.md` ADR#14/#15/#16. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> 경영자용 요약 + 엔지니어용 next tasks. 기준 커밋 `main`(현재), 1,517 passed/5 skip. (이전 `5491c02`/2026-06-16 기준은 stale — 갱신.)
> 💵 상업화·수익모델·가격 상세는 단일 출처 `2_ROADMAP/13_COMMERCIALIZATION_AND_PRODUCT_STRATEGY.md` 참조(ADR#15 트래픽×광고×커뮤니티 개정 반영).

> 📌 **경영 요약(ABSORB, 10 Group E E19)**: §B는 self-reconcile됨. 단 "두 자산이 아직 미연결"이라는 프레이밍은 **stale** — 배선·라이브 E2E 완료(canonical `01`·`05 R-Integration`, ap_news 100 카드). 현재 구현 사실은 canonical이 권위. 수익화·가격은 **미구현 ROADMAP**이며, 레거시 "B2B 구독 4티어" 방향은 **ADR#15로 폐기**(아래 '수익화' 단락 = 트래픽×광고×커뮤니티 개정본).

---

## A. 경영자 요약 (Executive Summary)

**우리가 만드는 것.** 구글 같은 범용 검색엔진이 아니라, 고신호 source 수집 + 검색 API 확장 + 자체 index + RAG + LLM judge + event graph를 결합한 **event intelligence platform**이다. 사용자가 묻기 전에 사건을 능동 감지하고, 다중 소스로 교차검증하며, 증거(evidence URL)를 붙여 신뢰할 수 있는 실시간 사건 스트림을 제공한다. **핵심 데이터 모델(ADR#16):** 사건은 1회성 카드가 아니라 **진화하는 Event 타임라인 객체**다 — 호르무즈 봉쇄처럼 하나의 주제가 시계열로 계속 변화하고 다분야로 번진다. Event(안정 주제) + EventUpdate(append-only 변화분)로 분리하고, 카드는 "Event의 최신 단면 스냅샷"으로 격하된다. 2번째 보도가 오면 새 카드가 아니라 **기존 Event에 Update가 append**된다.

**지금 어디에 있나.** 두 개의 자산이 있다 — (A) 57개 소스를 정책 안전하게 수집하는 deterministic 엔진(구현 완료), (B) 사건을 카드로 만들어 검색·표시하는 다운스트림 앱(부분 구현). 문제는 **둘이 연결되어 있지 않다**는 것이다. A의 수집 결과는 JSON 파일에만 쌓이고 실제 DB·화면까지 도달하지 못한다. 즉 "엔진은 완성됐고 고급 기능만 얹으면 된다"는 인식은 사실과 다르다.

**가장 중요한 한 가지 — 다음 관문(P0 배선은 PARTIAL DONE).** P0 배선(ingestion→raw_events PG)은 라이브 E2E로 **이미 연결됐다**(ap_news 100 카드, §B). 따라서 다음 관문은 배선이 아니라 **Event 토대(S1) 선행**이다(ADR#16, 00_ROADMAP_INDEX §4 임계경로). 카드 알맹이 AI 품질(NER/분류기/도달성)을 올리기 전에 **Event/Update 타임라인 형태를 먼저 고정**하지 않으면, 그 품질 작업이 곧 폐기될 1회성 카드 스키마 위에 쌓인다(코딩 전 판단 원칙). 첫 목표는 화려한 기능이 아니라 **"2번째 보도 → 새 카드 아닌 기존 Event Update append"를 비파괴(1517 green)로 입증하는 것**이다. 그 위에서만 검색고도화·상용화가 모래성이 아니게 된다.

**어떻게 이기나.** 자본화된 경쟁자(Dataminr/AlphaSense, 수천 고객·수백M 자본)와 범용 실시간 인텔리전스로 정면승부하면 진다. 이길 수 있는 곳은 (1) **좁은 vertical 정밀도**(AI/tech 제품 incident 또는 한국 규제/공시), (2) **교차검증 + evidence 추적성**(클릭 한 번으로 원본까지 = 인용 가능), (3) **사건 중심 능동 감지**, (4) **LLM을 수집의 두뇌로 쓰되 우회는 결정론으로 봉인**(P/G/F 경계, ADR#14)다. LLM은 무엇을·어디서를 계획(LAYER P)하고 결정론 엔진이 어떻게(준수하며)를 실행(LAYER G/F)한다 — "LLM-advised, deterministic-controlled." LLM은 crawler가 아니라 planner라, 탐색공간은 넓히되 robots/ToS/rate 위반은 어느 층에서도 못 한다.

**수익화 (ADR#15 — 방향 전환, 레거시 구독 폐기).** 수익은 B2B 구독이 아니라 **트래픽 기반 광고 + 커뮤니티식 운영**이다. 사용자가 새로 못박은 방향: "커뮤니티식 운영으로 트래픽을 늘리고 광고로 간다. 구독형으로 진화 안 함." 성장 루프 = 고품질 사건추적(시계열·다분야 Event) + 에이전트 해설/논쟁 + 유저 상호작용 → 체류↑·재방문↑ → 페이지뷰↑ → 광고 노출↑. **레거시 우려("전문 재배포 금지 → 광고 트래픽 모델 성립 안 함")는 거짓 전제다:** 우리가 노출하는 것은 전문이 아니라 **요약 + 증거링크 + UGC(유저 댓글·에이전트 논쟁) + 시계열 다분야 시각화**이며, 이는 파생 콘텐츠라 광고 면적이 된다(구글뉴스·Techmeme·Liveuamap 동일 구조). 고도화: ① 광고 **수요측** self-serve 도메인 직판(오디언스 정밀도 판매), ② 북극성 = **Monetizable Dwell + 광고주 갱신율**(구 LOI3/유료30 KPI 폐기), ③ evidence graph 직접 판매(구독)는 불변원칙상 닫힌 길 → 검증 위젯/SEO 허브/Live Index로 트래픽 증폭만. **보존:** 원칙1 투자조언 금지 · 전문저장 금지 · vertical 좁히기. 상세 = `2_ROADMAP/13`.

> ⚠️ **교정 노트(허위방향 제거):** 본 단락의 이전 판("광고가 아니라 B2B alert/report/API 구독 4티어, 파일럿 LOI 3 + 유료 30")은 **ADR#15로 폐기된 레거시 방향**이었다. 사용자 새 방향과 정반대였으므로 전면 재작성했다. 구현 사실이 아니라 **미구현 ROADMAP**이며, 권위는 `13`(상업화 단일출처)·ADR#15다.

**리스크.** ① 통합 갭(P0)이 모든 가치의 병목(P0 배선 PARTIAL DONE, 잔여 LLM급 품질), ② 프롬프트 인젝션(LLM 1위 위험, 외부 본문 유입 — LLM 수집 라우팅·에이전트 논쟁으로 **노출면 확대, 우선순위 상향**, R-PromptInjection), ③ 검색 API 무료티어 축소(단일 provider 의존 금지), ④ 법무(우회 금지·전문저장 금지·dcinside ToS 미확정), ⑤ 고급 layer(GraphRAG 등) 조기 도입의 비용/순서 역전, ⑥ **LLM 수집 경계 위반**(우회·rate·비용폭주 제안 — LAYER G 차단은 실구현이나 audit 미구현, R-LLMCollectBoundary), ⑦ **광고 모델 단일점**(콜드스타트·봇·brand-safety — 구독 폐기로 대체 수익경로 없음, R-AdModelFragility), ⑧ **Event 전환 정합성**(카드↔Event 이중쓰기·3엔진 색인 드리프트, R-EventModelMigration·R-FalseMerge). 이 문서 세트는 각 리스크에 봉인 조건과 우선순위를 부여했다(`_RISK/RISK_REGISTER.md`).

**투자/조언 아님.** 본 플랫폼과 문서는 사건/이벤트 정보 전달이 목적이며 투자 권유·금융 조언이 아니다.

## B. 진행 상황 (2026-06-18 갱신) — P0 배선 PARTIAL DONE

```text
[DONE] 1) P0 배선: ingestion/integration/ adapter(BackendApiRawEventsWriter = bridge db_writer,
       backend POST 경유 PG+Redis) + run_production_orchestration --raw-events-sink backend 진입점.
       라이브 e2e 5 record_type green(record→PG→Redis→worker→LangGraph→event_card), 멱등 collapse,
       community 카드 hold 봉인. 신규 테스트 37 PASS.
[DONE] 2) Redis: event_queue.py _redis_* 4개 구현(Stream+group+PEL ack).
       (P0 핵심 전달경로는 backend stream:raw_events. 이 스트림은 A측 EventQueue durable 백엔드.)
```

### P0 하드닝 (2026-06-18 추가) — 노출경로 봉인 + 운영 안전 부품

```text
[DONE] mock 카드 published 차단(fail-closed): evidence_check 실 source URL 채택(evidence_rules 구조검증),
       publish_or_hold = 유효근거+fact_check pass+본문 게이트, final_writer 기본 hold,
       공개 GET /api/events = published-only. 라이브 proof: 유효URL→published+노출, synthetic→hold+비노출.
[DONE] DLQ/PEL 부품: workers/queue/dlq.py(route_failure 재시도/DLQ, reap_pending XAUTOCLAIM),
       consumer 실패시 DLQ 라우팅(silent leak 제거), run_dlq_reaper CLI, requeue_failed_xadd(poison 한도).
[DONE] Orchestration 하드닝(2026-06-18): mock 5노드 → 결정론적 baseline(agents/nodes/baselines.py),
       publish_or_hold 합성마커 백스톱. 라이브: 실URL→실 entity/sector/추출요약 published, synthetic→hold+404.
[DONE] admin auth 운영 fail-closed(APP_ENV: prod 토큰 미설정→503+기동거부). 복구 주기 드라이버
       run_recovery_scheduler(reconcile+requeue-failed-xadd+PEL reap) + requeue-failed-xadd 엔드포인트.
[DONE] 적대적 리뷰 REAL_BUG 수정: openai 모드 [fallback] 상수 게이트 우회노출 → 백스톱+baseline 복귀.
```

### 남은 즉시 과제 (P0 complete까지)

```text
1) production-validation 라이브 외부 probe→backend 실적재 1회 검증 + 기본 sink를 backend로. (미실행)
2) 복구 드라이버 라이브 배포: run_recovery_scheduler를 compose service/cron으로 띄워 주기 tick 입증
   + DLQ depth 알림. (드라이버·엔드포인트·테스트는 DONE, 배포/라이브 tick만 남음. 04 T-Ops-DLQ)
3) LLM급 콘텐츠: entity_linking=NER, sector_mapping 분류기, evidence_check URL **도달성**(HTTP) 검증,
   impact LLM. (mock 상수는 제거·baseline화 완료; 현재는 결정론적 baseline이라 LLM급 정밀도가 다음 관문.)
```

위는 source-ingestion-engineer / orchestrator-architect / operations-sre-agent에 위임 가능. P2~P10·S1은 15 로드맵, 임계경로는 00_ROADMAP_INDEX §4.

### 신규 4작업축 (새 방향 ADR#14/#15/#16 + 발견 → ROADMAP 연결)

```text
요구1 (Event 모델, ADR#16)   → S1 Event/Update 토대 [임계경로 최우선]  · 15 'Event 토대 Phase' · 12 · 19 §1·§2 · EVENT_SCHEMA
요구2 (LLM 수집 P/G/F, ADR#14)→ S5 Expansion + S6 Source Routing(audit) · 15 Phase4/6 · 11 P/G/F절 · 06 tiered · 14 §2.1
요구3 (트래픽×광고, ADR#15)   → P9 수익화 전환 + PD Agent Debate         · 15 Phase9/PD · 13 · 14 §5.1
발견   (Entity/Authority, 요구6)→ S4/S7/S10/S11 자기증식 발견 엔진          · 17 (NET-NEW) · 05 · 00_ROADMAP_INDEX §4
```

> 4축은 Event 객체에서 합류한다 — Event 토대(S1)가 안 서면 나머지가 1회성 스키마 위에 쌓인다. RISK: R-EventModelMigration·R-FalseMerge(S1) · R-LLMCollectBoundary·R-PromptInjection(P/G/F) · R-AdModelFragility·R-AgentDebateSafety(광고/논쟁) · R-DiscoveryCostStarvation(발견).

## C. 한 줄

> 배관은 연결됐고(5타입 e2e, ap_news 100 카드), 카드 **알맹이의 mock 상수는 결정론적 baseline으로 제거**됐다(라이브 입증).
> 이제 **Event 타임라인 토대(S1)를 먼저 고정**하고, 그 위에서 baseline을 **LLM급 정밀도**(NER/분류기/도달성)로 끌어올리는 것이 다음 관문이다. 수익은 **구독이 아니라 트래픽×광고×커뮤니티**(ADR#15). 모든 단계 우회 0·전문저장 0·투자조언 0.

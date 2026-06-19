# 18 — FINAL EXECUTIVE SUMMARY

> 경영자용 요약 + 엔지니어용 next tasks. 기준 커밋 `5491c02`, 2026-06-16.
> 💵 상업화·수익모델·가격 상세는 단일 출처 `2_ROADMAP/13_COMMERCIALIZATION_AND_PRODUCT_STRATEGY.md` 참조.

> 📌 **경영 요약(ABSORB, 10 Group E E19)**: §B는 self-reconcile됨. 단 "두 자산이 아직 미연결"이라는 프레이밍은 **stale** — 배선·라이브 E2E 완료(canonical `01`·`05 R-Integration`, ap_news 100 카드). 현재 구현 사실은 canonical이 권위. 수익화·가격 등은 **미구현 ROADMAP**.

---

## A. 경영자 요약 (Executive Summary)

**우리가 만드는 것.** 구글 같은 범용 검색엔진이 아니라, 고신호 source 수집 + 검색 API 확장 + 자체 index + RAG + LLM judge + event graph를 결합한 **event intelligence platform**이다. 사용자가 묻기 전에 사건을 능동 감지하고, 다중 소스로 교차검증하며, 증거(evidence URL)를 붙여 신뢰할 수 있는 실시간 사건 스트림을 제공한다.

**지금 어디에 있나.** 두 개의 자산이 있다 — (A) 57개 소스를 정책 안전하게 수집하는 deterministic 엔진(구현 완료), (B) 사건을 카드로 만들어 검색·표시하는 다운스트림 앱(부분 구현). 문제는 **둘이 연결되어 있지 않다**는 것이다. A의 수집 결과는 JSON 파일에만 쌓이고 실제 DB·화면까지 도달하지 못한다. 즉 "엔진은 완성됐고 고급 기능만 얹으면 된다"는 인식은 사실과 다르다.

**가장 중요한 한 가지(P0).** ingestion 57소스 엔진을 실 raw_events Postgres에 연결하는 배선. 이것이 풀리기 전에는 소스를 100개 더 붙여도, GraphRAG를 얹어도, 영업을 시작해도 공허하다(데모 불가). 첫 목표는 화려한 기능이 아니라 **실데이터 사건 카드 1건을 end-to-end로 만드는 것**이다.

**어떻게 이기나.** 자본화된 경쟁자(Dataminr/AlphaSense, 수천 고객·수백M 자본)와 범용 실시간 인텔리전스로 정면승부하면 진다. 이길 수 있는 곳은 (1) **좁은 vertical 정밀도**(AI/tech 제품 incident 또는 한국 규제/공시), (2) **교차검증 + evidence 추적성**(클릭 한 번으로 원본까지 = B2B 인용 가능), (3) **사건 중심 능동 감지**다.

**수익화.** 광고가 아니라 **B2B alert/report/API**다. 가격은 시장 추세대로 hybrid(base + usage), 3-4 티어. 전문 재배포를 하지 않는 evidence 중심 모델이 오히려 저작권 안전성으로 엔터프라이즈 조달을 통과시킨다. 6개월 검증 목표: 파일럿 LOI 3 + 유료 30 + MRR 검증.

**리스크.** ① 통합 갭(P0)이 모든 가치의 병목, ② 프롬프트 인젝션(LLM 1위 위험, 외부 본문 유입), ③ 검색 API 무료티어 축소(단일 provider 의존 금지), ④ 법무(우회 금지·전문저장 금지·dcinside ToS 미확정), ⑤ 고급 layer(GraphRAG 등) 조기 도입의 비용/순서 역전. 이 문서 세트는 각 리스크에 봉인 조건과 우선순위를 부여했다.

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

위는 source-ingestion-engineer / orchestrator-architect / operations-sre-agent에 위임 가능. P2~P10은 15 로드맵.

## C. 한 줄

> 배관은 연결됐고(5타입 e2e), 카드 **알맹이의 mock 상수는 결정론적 baseline으로 제거**됐다(라이브 입증).
> 이제 baseline을 **LLM급 정밀도**(NER/분류기/도달성)로 끌어올리는 것이 다음 관문이다.

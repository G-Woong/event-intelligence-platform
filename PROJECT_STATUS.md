# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** ① D-2a(Event 타임라인 read API)를 커밋(`fc0efb9`)으로 안정화하고, ② **그 API를 웹 화면(frontend)에서 소비하는 D-2b를 구현**했습니다. 이제 코드 상으론 `/events/timeline` 페이지가 사건 목록과 사건별 업데이트(타임라인)를 그릴 수 있고, 기존 카드 화면(`/events`)은 그대로입니다.
- **이번 턴에 실제로 끝낸 것:** D-2b — Next.js `/events/timeline`(목록)·`/events/timeline/[id]`(상세) 페이지 + 컴포넌트 3종 + API 타입/호출 + nav "타임라인" 1줄. **안전 렌더**(출처 링크는 http/https만·`rel=noopener noreferrer nofollow`, 허용된 6개 메타키만 표시, 내부 식별자·본문 미노출) + flag 꺼짐(404)·데이터 없음·에러 상태를 graceful 처리. **기존 event_cards UI 무변경**(회귀 0). 측정: **tsc 0 · node:test 12 pass · next lint 0**. 4-감사단(code-review가 잡은 도메인·태그 중복 React key 2건 → `new Set` dedup 수정; adversarial가 "웹에서 본다" 과장 지적 → 아래처럼 정직 정정).
- **지금 막힌 것:** 없음(BLOCKED 0). 단 **현재 사용자는 빈 화면을 봅니다** — backend flag `EVENT_TIMELINE_API_ENABLED`가 기본 꺼짐(404)이고 dev DB에 Event 데이터도 없기 때문입니다. 즉 "타임라인을 *그릴 수 있는 능력*"은 확보했으나 "사용자에게 실제로 보임"은 **(a) flag 켜기 + (b) D-2c 데이터 결선(매핑된 실 Event)** 두 전제가 필요합니다. 또한 현재 업데이트 본문(delta_summary)이 `"0.83:strong_clique"` 같은 내부 라벨이라, 데이터가 있어도 자연어 서술이 아닙니다(상류 결선 책임, 별도).

## 📋 자동 수집 사실 (machine_status.json)
- HEAD `fc0efb9`(D-2a 커밋) 위 **미커밋 D-2b 변경 = frontend code 9 + docs 8**. (machine_status 스냅샷은 이전 턴 기준 stale — Stop 훅이 재스캔.)
- 신규(frontend): `app/events/timeline/{page.tsx,[eventId]/page.tsx}` · `components/{EventTimelineCard,EventTimelineList,EventUpdateItem}.tsx` · `lib/api/__tests__/timeline.test.mjs`. 수정: `lib/api/{types.ts,client.ts}` · `app/layout.tsx` · `package.json`.
- 열린 RISK 29: **신규 R-EventTimelineRenderHardening**(상세 에러표현·delta_summary 본문품질·source_refs wire 노출, LOW) · 기존 R-EventTimelineApiScale·R-EventSinkDbTarget·R-EventTimelineS2Hardening·R-EventModelMigration·R-FalseMerge·R-ExpansionPartialFailure 유지.

## ✅ 이번 턴에 달성한 것 (D-2a 커밋 + D-2b frontend 렌더)
- **D-2a 커밋(`fc0efb9`):** code 7 + docs 8, secret PASS·closeout EXACT MATCH(17 sig)·docs_lifecycle conflicts 0·unresolved 0 확인 후 커밋(15 files +326/−41). working tree clean(push 안 함).
- **docs/2_ROADMAP 재판정 + frontend/docker 실측(병렬 Explore):** 로드맵 §4 임계경로 + _CANONICAL 모두 **D-2b 를 다음으로 지시**. D-2c(Docker 데모)는 frontend가 timeline UI를 안 그리므로 **D-2b 선행 필요**. D-1.5(운영 보강)는 compose 격리 컨테이너 DB(`event_intel`)·mock 기본·`_target_db_label`·APP_ENV 가드가 모두 존재해 **데모 blocker 아님**. **문서 불일치 0**(로드맵이 이미 D-2b 지시).
- **D-2b frontend 렌더(ADR#25, additive):** 신규 라우트 `/events/timeline`(목록)·`/events/timeline/[eventId]`(상세) + `EventTimelineCard`/`EventTimelineList`/`EventUpdateItem` + `lib/api` 타입(Event/EventUpdate/EventUpdateEvidence/EventTimelineResponse, backend Pydantic 1:1)·메서드(`buildTimelineUrl`/`listEventTimeline`/`getEventTimeline`) + nav 1줄. 기존 `/events`(event_cards)·EventCard·EventList **무변경**.
- **안전 렌더:** evidence url 은 `isSafeHttpUrl`(http/https 만 링크화 → javascript:/data: 스킴주입 차단) + `rel="noopener noreferrer nofollow"`·`target="_blank"`. allowlist 6키(url/source_type/role/confidence/relation/observed_at)만 렌더, **source_refs·heat·primary_entity_ids·snapshot_card_id 미렌더**(내부 식별자/본문/PII 미노출). web read path 에 **LLM/network 0**.
- **graceful 상태:** flag off → 목록은 "아직 활성화되지 않았습니다" 빈상태(에러 아님), 상세는 `notFound()`. 데이터 없음 → 빈 목록 안내. updates 0 → "아직 업데이트가 없습니다".
- **4-감사단:** architecture **SOUND**(0 blocking; 라우트 비충돌(정적 `timeline`>동적 `[id]`)·타입 1:1·flag-off 일관) · legal **APPROVED**(전문/PII 0·링크 안전·source_refs 미노출·정보제공 톤·held 게이트 의존 정합) · adversarial **코드 0 blocking**("웹에서 본다" 과장→"렌더 능력, 실 노출은 flag+데이터 전제"로 정정; delta_summary 디버그라벨·상세 에러표현 지적→R-EventTimelineRenderHardening) · code-review **2 CONFIRMED→수정**(`[...domains,...tags]` 를 `key={l}` 로 렌더 시 도메인·태그 교집합에서 React 중복 키 → `new Set` dedup, 목록·상세 양쪽).
- **검증:** frontend **tsc --noEmit 0** · **node:test 12 pass**(buildTimelineUrl 기본/명시 페이지네이션 · isSafeHttpUrl http/https 허용·javascript:/data:/빈값 거부) · **next lint 0 warnings**. backend는 D-2b가 손대지 않음(frontend 전용) → backend 241 + ingestion 1331 = 1572 green 유지(회귀 0).

## ❌ 달성하지 못한 것 & 왜
- **현재 사용자는 빈 화면(정직):** `EVENT_TIMELINE_API_ENABLED` 기본 off(404) + dev DB Event 0 → `/events/timeline`은 빈 상태만 표시. 실제 노출은 flag on + D-2c 데이터 결선 전제. "렌더 *능력* 확보"이지 "사용자 노출 완료"가 아님.
- **delta_summary 자연어화 미결(D-2c+ 상류):** 현재 결선(`event_ingest_pipeline`)이 `"{confidence}:{reason}"` 디버그 라벨을 delta_summary 에 넣음 → 데이터가 있어도 타임라인 본문이 사용자용 서술이 아님(상류 생성 책임).
- **Docker 데모 미실행(D-2c 이월):** 풀스택 compose는 있으나 Event 데이터 흐름(seed/scheduler 결선)+flag on+브라우저 E2E 미실행. "주기적으로 Event가 쌓이는 웹" 가시화는 다음.
- **상세 페이지 비-404 에러 표현(R-EventTimelineRenderHardening):** 기존 `/events/[eventId]` 패턴 답습(throw→error.tsx) — backend 장애 시 raw 메시지 노출 가능. 전역 `error.tsx` 영향이라 별도(이번 범위 밖).
- **주기 auto-trigger·실 production-validation·event_cards 자동연결·heat(S2.5)·페이지네이션 UI:** 이월.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 실 데이터 노출 시 타임라인 가독성(delta_summary 자연어화 후 재평가)·브라우저 E2E 실거동(compose 실행 전까지 미검증, tsc/lint/test 는 통과)·대규모 응답 plan(R-EventTimelineApiScale).
- **pre-existing embedding 실패(D-2b 무관):** `test_get_embedding_client_singleton` 1 FAIL(실 `.env` provider 결합) — backend 테스트 격리 결함, Event/타임라인 경로와 무관. 차기: conftest LLM/EMBEDDING=mock 강제.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-EventTimelineRenderHardening(신규, LOW):** D-2b 렌더 잔여 — ① 상세 비-404 에러 표현(목록과 비대칭·기존 패턴 답습) ② delta_summary 디버그 라벨(상류) ③ source_refs read API 응답 wire 노출(화면 미렌더). **완화:** 링크 스킴 게이트·allowlist 6키·source_refs 미렌더·ApiError 마스킹. **잔여:** 상세 에러 통일·delta_summary 자연어화·public 스키마 source_refs 제외 결정.
- **R-EventTimelineApiScale·R-EventSinkDbTarget·R-EventTimelineS2Hardening·R-EventModelMigration·R-FalseMerge·R-ExpansionPartialFailure:** D-2b가 손대지 않음 → 유지.
- 신규 1(R-EventTimelineRenderHardening) · 완전 종결 0 · GDELT/DcToS/ContentTypeGate 무변경.

## 👉 다음 할 일
1. **[D-2c Docker 데모]** Event seed 또는 scheduler(interval) 결선 → `docker compose up`(+`EVENT_TIMELINE_API_ENABLED=true`·`EVENT_RESOLUTION_ENABLED=true`) → 브라우저로 "Event가 쌓이고 업데이트되는 웹" 확인(webapp-testing/Playwright E2E). **선행:** delta_summary 자연어 서술 결선(가독성).
2. **[보강]** 상세 비-404 에러 표현 통일(R-EventTimelineRenderHardening) · 단건 updates 페이지네이션(R-EventTimelineApiScale) · 주기 auto-trigger(Phase 2 interval scheduler) · event_cards↔Event 자동연결.
3. (이월) heat 4신호(S2.5) · merge_score(S4) · LLM 보조(S5/S6) · 3엔진 색인 정합.

## 📁 근거 (이번 턴 핵심)
- 코드(frontend): `app/events/timeline/{page.tsx,[eventId]/page.tsx}` · `components/{EventTimelineCard,EventTimelineList,EventUpdateItem}.tsx` · `lib/api/{types.ts,client.ts}`(Event/EventUpdate/EventTimelineResponse + listEventTimeline/getEventTimeline) · `app/layout.tsx`(nav).
- 테스트: `lib/api/__tests__/timeline.test.mjs`(buildTimelineUrl·isSafeHttpUrl 순수검증, 4 case) + `package.json` test 등록.
- 문서: `_DECISIONS/2026-06.md`(ADR#25) · `_RISK/RISK_REGISTER.md`(R-EventTimelineRenderHardening) · 2_ROADMAP/{00,15,19} · EVENT_SCHEMA · _CANONICAL/02.

---
_as_of: 2026-06-23 · D-2b Event 타임라인 frontend 렌더 — Next.js `/events/timeline`(목록 list[Event])·`/events/timeline/[id]`(상세 event+updates) page+컴포넌트(EventTimelineCard/List/EventUpdateItem) + lib/api 타입·메서드 + nav 1줄. 안전 evidence 렌더(url http/https 게이트+rel, allowlist 6키, source_refs 미렌더). flag off→graceful 빈상태/notFound. 기존 event_cards UI **무변경**(회귀 0). 측정 tsc 0·node:test 12·next lint 0. 4-감사단(code-review: 도메인·태그 중복 React key→`new Set` dedup; adversarial: "웹에서 본다" 과장→"렌더 능력, 실 노출은 flag on+D-2c 데이터 전제"로 정정). **현재 빈 화면**(flag 기본 off+dev DB Event 0); delta_summary 자연어화는 상류 잔여. D-2a 커밋 `fc0efb9`. D-2b 미커밋(커밋 지시 대기). pre-existing embedding 실패 1(무관)_

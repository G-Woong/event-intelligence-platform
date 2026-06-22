# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** "본문 추출 기대치(어떤 소스가 산문 본문을 가지는가)" 판정을 라이브 복구(rescue) 라우팅에 **단일 출처로 배선**하고, 5개 감사단(code/test/pipeline/evidence/적대)으로 검증했습니다. 코드는 깨끗(회귀 0)하고, 적대 감사가 짚은 "효과 과대표현"을 **정직하게 가드레일로 재서술**했습니다.
- **이번 턴에 실제로 끝낸 것:** 턴1 — `source_content_type`을 `rescue_router`의 body 판정에 게이트 배선(카탈로그 메타데이터형은 본문 ladder로 안 보내고 "메타 완성"으로, 산문형 기사만 ladder). ingestion **1323 green**(회귀 0) · secret PASS · `.env`/outputs 무변경. 감사 4종(test PASS·pipeline SOUND·code 버그 0·적대 1 blocking→정직 재서술로 해소).
- **지금 막힌 것:** 없음(BLOCKED 0). 단 이 게이트는 **현 운영 데이터에서 트리거 0건**(카탈로그가 BODY_FETCH 경로를 받지 않음) — 즉 라이브 즉효가 아니라 **미래 회귀/오분류 방어용 가드레일**입니다. 이 한계를 `R-ContentTypeGateDormant`(LOW)로 정직히 등록했습니다.

## 📋 자동 수집 사실 (machine_status.json)
- session 4e61… turn 3 · 변경 9건 = **code 3 + docs 4 + other 2**. code_py_loc 30.
- code_files: `rescue_router.py`, `test_rescue_router.py`, `run_source_readiness_closure.py`.
- audit_types(권위): **code_review · pipeline_review · test_review** → 전부 라우팅·완료. 열린 RISK **24 → 25**(신규 LOW 1 = `R-ContentTypeGateDormant`, 종결 0).

## ✅ 이번 턴에 달성한 것
- **턴1 배선(최소 변경 3파일):**
  - `rescue_router.decide_rescue` (+9): `BODY_LADDER_FETCH` 전략이어도 `body_ladder_eligible()=False`(카탈로그/구조화/검색)면 → `STRUCTURED_SIGNAL_REDUCE`(reason=`metadata_complete_no_prose_body`). vendor route override는 게이트 **뒤**에 두어 우선순위 보존.
  - `run_source_readiness_closure._execute_rescue` (+6): 신규 `STRUCTURED_SIGNAL_REDUCE` 분기 — body ladder 미적용, live 검증 없으니 promote 안 함(둔갑 금지), note=`metadata_complete_body_not_applicable`.
  - `test_rescue_router.py` (+15): 회귀 2 — 카탈로그(tmdb)@BODY_FETCH→`structured_signal_reduce`, 산문형(cnbc)@BODY_FETCH→`body_ladder_fetch`(불변).
- **단일 출처 확립:** 라이브 라우팅·probe(`body_ladder_probe`)·audit(`body_extraction_audit`)이 모두 `source_content_type` 한 모듈을 공유(평행 구현 0) — orchestrator 감사 확인.
- **5-감사단 검증:**
  - test-validation **PASS** — ingestion 1323(직전 1321+신규 2, 회귀 0)·secret PASS(5538)·`.env`/outputs 무변경. 사용자 검증 V1(카탈로그→reduce)·V2(cnbc→ladder 유지)·V3(미지 group→article 안전) 전부 PASS.
  - orchestrator **SOUND**(blocking 0) — vendor route 순서 보존, no-promote 정직성, 누락 경로 부재.
  - code-review **버그 0** — diff 5앵글(정확성/제거동작/교차파일/언어함정/규약) 깨끗, 순환 import 없음.
  - legal-safety(evidence) **APPROVED** — 우회 0·전문 저장 영향 0·신규 수집/소스 0. body fetch를 **줄이는** 방향(카탈로그는 ladder 미진입), 기존 no-bypass 게이트(robots/paywall/login/captcha) 온존.
  - adversarial(risk_closure) **CONCERNS→해소** — B-1(게이트 라이브 트리거 0건, "배선 완료" 과대표현)을 **가드레일로 정직 재서술 + `R-ContentTypeGateDormant` 등록**으로 처리. 종결 0·신규 1 검증.

## ❌ 달성하지 못한 것 & 왜
- **게이트 라이브 즉효 0:** 적대 감사 B-1 — 카탈로그 소스는 PRODUCTION_READY라 gap matrix에서 제외되고, BODY_FETCH layer는 `EXTERNAL_API_ERROR`+EXCERPT에서만 발생(현재 해당 소스 0). 따라서 게이트는 단위테스트로만 행사되고 라이브 경로엔 아직 안 오름. **이는 결함이 아니라 방어 가드레일의 정직한 현황**(미래 오분류/회귀 대비). 단일 출처 원칙을 라이브에 확정한 가치는 유효.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: 카탈로그 소스가 실제 BODY_FETCH 경로를 받는 시나리오(예: memory가 EXTERNAL_API_ERROR로 후퇴)가 운영 중 발생할지 — 발생 시 게이트가 정확히 작동함은 단위테스트로 입증됨.

## ⚠️ 이번 턴 종결/갱신 RISK
- **신규 1:** `R-ContentTypeGateDormant`(LOW) — 라이브 게이트 트리거 0건(가드레일), 신규 카탈로그 소스 `_CATALOG` 등록 의무(N-1), 활성화 시 `still_not_ready` 표기 모순(N-4) 추적. **종결 0.** 순 open 24 → **25**.

## 👉 다음 할 일
1. **[턴2 — S1 토대]** alembic **0004**(additive) + `events`/`event_updates` ORM·Pydantic + `event_cards.event_id` nullable FK + **이중쓰기 정합성 회귀**(카드↔Event 쌍방향 + 3엔진 card_id 불변식). 측정 게이트는 **backend+ingestion 합산 green**. (사용자 승인 — closeout 통과 후 착수.)
2. (이월) `R-ContentTypeGateDormant`: 카탈로그 BODY_FETCH 라이브 경로 관찰 시 게이트 트리거 1건 확인 + monitoring `metadata_complete_holdover` 분리.
3. (이월) `R-Gdelt429` 비-throttle 재probe, 조건부 48소스 분할 재probe.

## 📁 근거 (이번 턴 핵심)
- 코드: `ingestion/orchestration/rescue_router.py`(게이트), `ingestion/tools/run_source_readiness_closure.py`(STRUCTURED_SIGNAL_REDUCE 처리), `ingestion/tests/unit/test_rescue_router.py`(회귀 2). 재사용: `ingestion/orchestration/source_content_type.py`(단일 출처).
- 문서: `docs/_RISK/RISK_REGISTER.md`(신규 R-ContentTypeGateDormant), `PROJECT_STATUS.md`.
- 감사(5종): test-validation PASS · orchestrator SOUND · code-review 버그 0 · legal-safety(evidence) APPROVED · adversarial(risk_closure) B-1→가드레일 재서술+risk 등록으로 해소.

---
_as_of: 2026-06-22 · 턴1 source_content_type 라이브 배선(rescue_router body 게이트, 단일 출처) + 5-감사단(test PASS·pipeline SOUND·code 0버그·evidence APPROVED·adversarial B-1 해소) · ingestion 1323 green · secret PASS · `.env`/outputs 무변경 · 신규 LOW risk 1(가드레일 정직 등록) open 25 · 커밋 보류(사용자 지시)_

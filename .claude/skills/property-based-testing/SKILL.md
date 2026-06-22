---
name: property-based-testing
description: 입력 공간이 넓은 파서·검증 함수에 Hypothesis 기반 property-based test를 추가할 때 사용. rate gate, URL 파서, article_body_extractor, config.py의 ".env 빈값=기본값" 계약 등. 예시 기반 단위테스트가 놓치는 엣지케이스를 자동 생성해 기존 1,517 green을 보강. (표준 검증 루프는 test-validation-skill.)
license: CC BY-SA 4.0 (upstream) — 내부 사용 자유, 외부 재배포 시 동일 라이선스 유지
upstream: https://github.com/trailofbits/skills (property-based-testing, companion: modern-python)
adapted_for: WEB_INTELLIGENCE_HARNESS_EVOLUTION.md S4
---

# property-based-testing (Hypothesis)

> upstream `trailofbits/skills`(CC BY-SA 4.0) 적응. 스택이 이미 uv/Py3.11로 일치. test-validation-skill이
> 안 다루는 PBT 영역을 보완. **결정론 수집 엔진의 파서류는 PBT가 가장 효과적**(입력 공간이 큼).

## 언제 쓰나
- 파서/직렬화/검증 로직 추가·수정 시(특히 입력 형태가 다양한 함수).
- "빈값=DEFAULT" 같은 **계약(contract)** 을 속성으로 못박고 싶을 때.

## 절차
1. **불변식 식별:** 함수의 속성을 문장으로(예: "config 파서는 어떤 빈 문자열 키도 제거하고 기본값을 쓴다", "URL 파서는 정규화 후 멱등이다").
2. **Hypothesis 전략:** 입력 도메인에 맞는 `st.text()/st.from_regex()/st.dictionaries()` 구성.
3. **속성 작성:** `@given(...)`으로 불변식을 assert. round-trip(직렬화↔역직렬화), 멱등, 예외 안전성 우선.
4. **수렴:** 실패 케이스 minimization 결과를 회귀 단위테스트로 고정.
5. `uv run pytest` 로 기존 1,517과 함께 green 확인. (modern-python: ruff/ty 컴플라이언스 동반.)

## 우선 대상(본 프로젝트)
- `backend/app/core/config.py` env 파서 계약(빈 문자열 제거→기본값, CSV CORS).
- `ingestion` rate gate/cooldown 산식, URL 정규화, `article_body_extractor` 경계(200자 임계).

## 안전·제약
- 외부 호출 0(순수 함수 대상). `.env` 미열람. 네트워크 의존 함수는 PBT 대상에서 제외(결정론 입력만).
